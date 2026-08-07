# Plan: OSC Tracks híbrido (ReaScript Python + ReaLearn) para ReaSet

> **For Hermes / agentes:** implementar este plan task-by-task. Ver skill `subagent-driven-development`.
> **Para revertir si algo falla durante la implementación:**
> ```bash
> git checkout tags/before-osc-tracks
> ```

**Goal:** Permitir que REAPER (vía ReaSet) dispare comandos OSC desde el timeline — un track `OSC` con items — hacia QLab, consolas de luces (EOS) u otros destinos, combinando authoring en la sesión (Opción A) con routing flexible vía ReaLearn (Opción B).

**Architecture:** Un script Python `ReaSet_OSCTrack.py` corre en `reaper.defer()` y detecta cuándo el playhead cruza el inicio de un item del track `OSC`. Cada item = **evento lógico** (ej. `INTRO`, `BLACKOUT`). El script tiene dos modos de puente:

1. **`direct`** — envía OSC por UDP al host:puerto configurado (funciona sin ReaLearn; ideal para un destino único).
2. **`realearn`** — envía el evento a ReaLearn por loopback (o dispara acciones REAPER), y ReaLearn hace el **routing/transformación** hacia N destinos.

La integración con ReaSet (opcional) publica el evento actual en ExtState para mostrarlo en el Live View.

**Tech Stack:** REAPER 7.78 (macOS, Apple Silicon) · Python 3.13 (framework del sistema, runtime ReaScript) · ReaLearn 2 (vía ReaPack) · UDP/OSC · QLab (puerto 53000) · EOS (puerto 8000)

**Idioma del plan:** español (documento de trabajo interno). El README/CHANGELOG del repo son bilingües — traducir al documentar (Task 7).

---

## Contexto y por qué este diseño

AbleSet (Ableton Live) tiene **OSC Tracks**: clips MIDI en un track que emiten comandos OSC temporizados a luces/video/QLab. REAPER **no tiene items de tipo OSC nativos** — su OSC nativo es de control surface (protocolo fijo `.ReaperOSC`, útil para faders/transport, no para mensajes arbitrarios por item).

Este plan replica la funcionalidad con dos capas:

```
Track "OSC" en REAPER (items = eventos lógicos: INTRO, CHORUS2, BLACKOUT)
        │
        ▼  ReaSet_OSCTrack.py (defer loop, solo lectura)
   Cruce de item → evento lógico
        │
        ├─ modo "direct"   → UDP OSC crudo a host:puerto (QLab/EOS directo)
        └─ modo "realearn" → evento a ReaLearn (loopback OSC o acción REAPER)
                             → ReaLearn transforma y rutea a N destinos
```

**Principios:**
- **Authoring en el timeline:** el *cuándo* vive en la sesión de REAPER (visible, editable, con undo nativo, dentro de las regiones del show). Se escribe un evento donde se ve.
- **Routing desacoplado:** el script NO sabe a dónde va cada evento. Los destinos/IPs/mensajes se configuran en ReaLearn (UI gráfica) o en ExtState — sin tocar la sesión.
- **Un evento, N gatillos:** en modo acciones, `OSC:INTRO` es también asignable a teclado/MIDI/pedal — el mismo evento lógico se dispara desde el timeline o manualmente.
- **Cero riesgo de sesión:** el script solo lee (posición + nombres de items). No modifica nada → undo de REAPER intacto.

---

## Protocolo de eventos (especificación)

| Elemento | Regla |
|---|---|
| Track | Se llama `OSC` (case-insensitive). Se reutiliza la normalización decorada de `Reaset.lua`: `*OSC`, `01 - OSC`, `[OSC]` son válidos; `Backing OSC` no (palabra extra). |
| Item: evento lógico | El **nombre del item** es el evento. Ej.: `INTRO`, `CHORUS2`, `BLACKOUT`, `CUE:3` |
| Item: OSC crudo | Si el nombre del item **empieza con `/`**, se envía tal cual como path OSC directo (modo `direct`), sin pasar por router. Ej.: `/cue/2/go` |
| Disparo | Cuando `playstate & 1` y el playhead cruza el `D_POSITION` del item entre dos ticks. Se ignora al cargar el script (no dispara items pasados). |
| ExtState | `ReaSetOSC / enabled` (`1`/`0`), `ReaSetOSC / mode` (`direct`/`realearn`), `ReaSetOSC / direct_host`, `ReaSetOSC / direct_port`, `ReaSetOSC / realearn_port`, `ReaSetOSC / last_event` (publica el último evento + timestamp) |

**Ejemplo de sesión (RDV.rpp):**
```
Región: "01 - Intro"        (0:00.000 – 0:12.000)
  ├─ item OSC: "INTRO"      → ReaLearn → /cue/1/go a QLab + /light/cue/5 a EOS
Región: "02 - Never Gonna Give You Up"
  ├─ item OSC: "CHORUS1"    → ReaLearn → /cue/3/go (efecto)
  └─ item OSC: "/cue/9/go"  → directo, sin router
```

---

## Tareas

### Task 0: Checkpoint y setup

**Objective:** Punto de rollback claro + rama de trabajo + verificar que REAPER usa Python.

**Files:** ninguno (repo + preferencias REAPER)

**Step 1 — Tag de checkpoint**
```bash
cd ~/dev/ReaSet-gh   # o donde esté el repo
git tag -a before-osc-tracks -m "Checkpoint antes de implementar OSC Tracks (híbrido A+B)"
```

**Step 2 — Rama de trabajo (nunca main)**
```bash
git checkout -b testing/Auri
```

**Step 3 — Verificar runtime Python de REAPER**
1. REAPER → Preferences → Plug-ins → ReaScript → pestaña **Python**.
2. Si no detecta Python 3.13: apuntar manualmente a `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3`.
3. Verificación: crear `Scripts/Reaset Scripts/_py_probe.py` con:
```python
import reaper, sys
reaper.ShowConsoleMsg("Python OK: " + sys.version + "\n")
```
4. Actions → ReaScript: Load… → `_py_probe.py` → Run. Esperado: consola muestra `Python OK: 3.13.x`. Luego borrar `_py_probe.py`.

**Step 4 — Commit**
```bash
git add -A && git commit -m "docs: checkpoint antes de OSC tracks"   # solo si hubo cambios de doc
```

---

### Task 1: Instalar ReaLearn 2

**Objective:** Tener ReaLearn 2 disponible (mapping OSC gráfico).

**Files:** extensiones de REAPER (vía ReaPack)

**Step 1 — Instalar desde ReaPack**
1. REAPER → Extensions → ReaPack → **Browse Packages…**
2. Buscar `ReaLearn` → clic derecho → **Install** (paquete oficial de Helgoboss).
3. Apply. Reiniciar REAPER si lo pide.

**Step 2 — Verificar**
1. Actions → buscar `ReaLearn: Open ReaLearn 2 window`.
2. Esperado: la acción existe y abre la ventana de ReaLearn 2.

**Step 3 — Verificar soporte OSC de ReaLearn**
- ReaLearn 2 ≥ v2.12 tiene entrada/salida OSC nativa. En la ventana de ReaLearn, crear un **instance** (pestaña Instances → Add) y en sus *input ports* debe poder elegirse un puerto UDP local además de MIDI. Si solo aparecen puertos MIDI → versión vieja, actualizar por ReaPack.

> ⚠️ **Pitfall:** ReaLearn 2 es un .dylib en `UserPlugins/` + scripts de ReaPack. Si REAPER no lo carga, revisar consola de REAPER (Help → About → Extensions).

---

### Task 2: Script v1 — detección de eventos (consola)

**Objective:** Detectar cruce de items del track `OSC` y loguear el evento.

**Files:**
- Create: `Scripts/Reaset Scripts/ReaSet_OSCTrack.py`

**Step 1 — Escribir el script (v1 completo, listo para correr)**

```python
#!/usr/bin/env python3
# =============================================================================
# ReaSet_OSCTrack.py — OSC Tracks para ReaSet (híbrido A+B)
# Detecta items en el track "OSC" y dispara eventos lógicos.
# v0.1 — detección + consola. v0.2+ agrega UDP OSC (Task 3).
# Solo lectura: NO modifica la sesión.
# =============================================================================
import reaper
import time

SEC = "ReaSetOSC"

# ---- configuración por defecto (extensible vía ExtState en Task 3) ---------
TRACK_KEYWORD = "osc"
FIRE_ON_STOPPED = False      # True: dispara también con transporte parado al pasar el cursor

# ---- estado interno ---------------------------------------------------------
_last_pos = None             # posición del tick anterior
_armed_items = {}            # {item: nombre} caché ligera

def norm_track_name(name):
    """Misma normalización decorada que Reaset.lua: quita prefijos/números/símbolos."""
    if not name:
        return ""
    n = name.strip().lower()
    # quitar decoradores comunes: * # [ ] - números iniciales
    for ch in "*#[](){}":
        n = n.replace(ch, "")
    n = n.strip(" -_.")
    return n

def get_osc_track():
    """Devuelve el primer track cuyo nombre normalizado == 'osc'."""
    for i in range(reaper.CountTracks(0)):
        tr = reaper.GetTrack(0, i)
        ok, name = reaper.GetTrackName(tr, "")
        if isinstance(name, tuple):
            name = name[0] if name else ""
        if norm_track_name(name) == TRACK_KEYWORD:
            return tr
    return None

def fire_event(event_name):
    """Punto único de salida: aquí se conectará el envío OSC (Task 3)."""
    reaper.ShowConsoleMsg("[ReaSetOSC] EVENTO: %s\n" % event_name)
    reaper.SetExtState(SEC, "last_event", event_name, True)

def run():
    global _last_pos
    time.sleep(0.05)  # ~20 ticks/s, CPU despreciable
    try:
        play = reaper.GetPlayState() & 1
        pos = reaper.GetPlayPosition()

        # arranque: adoptar posición sin disparar nada
        if _last_pos is None:
            _last_pos = pos
            reaper.defer(run)
            return

        tr = get_osc_track()
        if tr is not None and (play or FIRE_ON_STOPPED):
            n = reaper.CountTrackMediaItems(tr)
            for i in range(n):
                item = reaper.GetTrackMediaItem(tr, i)
                start = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
                # cruce: estaba antes del start en el tick anterior, ahora >= start
                if _last_pos < start <= pos:
                    nm = reaper.GetSetMediaItemInfo_Str(item, "P_NAME", "")
                    if isinstance(nm, tuple):
                        nm = nm[0] if nm else ""
                    if nm and nm.strip():
                        fire_event(nm.strip())

        _last_pos = pos
    except Exception as e:
        reaper.ShowConsoleMsg("[ReaSetOSC] error: %s\n" % e)
    reaper.defer(run)

run()
```

**Step 2 — Verificar**
1. En REAPER: crear un track llamado `OSC`, agregar 2 items MIDI vacíos con nombres `INTRO` y `CHORUS1` (propiedades del item → Name).
2. Actions → ReaScript: Load… → `ReaSet_OSCTrack.py` → Run.
3. Poner el playhead antes del primer item → Play.
4. Esperado en consola: `[ReaSetOSC] EVENTO: INTRO` y luego `EVENTO: CHORUS1` al cruzar cada item.
5. Parar, mover el cursor sobre items, **no** debe loguear nada (sin FIRE_ON_STOPPED).

**Step 3 — Commit**
```bash
git add "Scripts/Reaset Scripts/ReaSet_OSCTrack.py"
git commit -m "feat: OSC track detector v0.1 (eventos a consola)"
```

---

### Task 3: Script v2 — envío OSC directo (modo `direct`)

**Objective:** Enviar eventos por UDP/OSC al destino configurado, sin ReaLearn.

**Files:**
- Modify: `Scripts/Reaset Scripts/ReaSet_OSCTrack.py`

**Step 1 — Agregar encode OSC + envío UDP**

```python
import socket

_sock = None

def _pad(b):
    return b + b"\x00" * ((4 - len(b) % 4) % 4)

def osc_send(host, port, path, value=None):
    """Enviar un mensaje OSC: path + opcional string value. Sin dependencias."""
    global _sock
    if _sock is None:
        _sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    msg = _pad(path.encode("utf-8"))
    if value is not None:
        msg += _pad(b",s")
        msg += _pad(value.encode("utf-8"))
    else:
        msg += _pad(b",")
    try:
        _sock.sendto(msg, (host, port))
    except OSError as e:
        reaper.ShowConsoleMsg("[ReaSetOSC] UDP error: %s\n" % e)

def cfg(key, default):
    v = reaper.GetExtState(SEC, key)
    return v if v else default
```

**Step 2 — Integrar en `fire_event` (modo direct + items crudos)**

```python
def fire_event(event_name):
    reaper.ShowConsoleMsg("[ReaSetOSC] EVENTO: %s\n" % event_name)
    reaper.SetExtState(SEC, "last_event", event_name, True)

    if cfg("enabled", "1") != "1":
        return

    mode = cfg("mode", "direct")
    if mode == "direct":
        # item crudo: el nombre empieza con "/" → path OSC directo
        if event_name.startswith("/"):
            host = cfg("direct_host", "127.0.0.1")
            port = int(cfg("direct_port", "53000"))
            osc_send(host, port, event_name)
        else:
            host = cfg("direct_host", "127.0.0.1")
            port = int(cfg("direct_port", "53000"))
            osc_send(host, port, "/reaset/" + event_name)
    elif mode == "realearn":
        host = cfg("realearn_host", "127.0.0.1")
        port = int(cfg("realearn_port", "9002"))
        osc_send(host, port, "/reaset/" + event_name)
```

**Step 3 — Verificar con un monitor OSC**

Monitor UDP sin dependencias (terminal 1):
```bash
# escucha en 53000 y muestra paquetes crudos
python3 -c "
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind(('0.0.0.0', 53000))
print('escuchando 53000...')
while True:
    d, a = s.recvfrom(4096)
    print(a, d)
"
```

1. REAPER: Actions → Reascript → *Re-run last script* (o recargar el script).
2. Play. Esperado: el monitor imprime `/reaset/INTRO\0,s\0...` (o el path crudo `/cue/9/go`).
3. Probar `mode=realearn` con `realearn_port=9002` → monitor en 9002 (para Task 4).

**Step 4 — Commit**
```bash
git add "Scripts/Reaset Scripts/ReaSet_OSCTrack.py"
git commit -m "feat: OSC UDP directo (modo direct + crudo)"
```

---

### Task 4: ReaLearn — modo router loopback

**Objective:** ReaLearn recibe los eventos por UDP loopback y los rutea/transforma a destinos reales (QLab, EOS).

**Files:** configuración en REAPER/ReaLearn (no repo, salvo documentación)

**Step 1 — Configurar ReaLearn**
1. Abrir `ReaLearn: Open ReaLearn 2 window`.
2. **Instances** → Add instance → elegir el proyecto de show (o Global).
3. En el instance, **Input ports**: agregar puerto UDP local **9002** (el mismo `realearn_port` del script).
4. **Main mappings** → Add mapping.
5. **Source** = `OSC input` → path `/reaset/*` (wildcard; en ReaLearn 2 se captura el valor/etiqueta del path con `$` placeholders según versión).
6. **Target** = `OSC` → host `127.0.0.1`, port `53000`, path `/cue/1/go` (QLab) — o el destino que corresponda (EOS: port 8000).

**Step 2 — Verificar**
1. Monitor OSC en 53000 (comando de Task 3).
2. REAPER → Play con item `INTRO` en el track OSC.
3. Esperado: monitor muestra `/cue/1/go` (no `/reaset/INTRO`): ReaLearn transformó el evento.
4. Probar con 2 destinos: duplicar el mapping con target EOS `/light/cue/5`.

> ⚠️ **Pitfall ReaLearn:** el wildcard de path y el nombre del source varía entre versiones de ReaLearn 2. Si `OSC input` no aparece como source: actualizar ReaLearn (ReaPack) y revisar la doc oficial de Helgoboss para la versión instalada.

**Step 3 — Commit (documentación de referencia)**
```bash
git add README.md   # si se documentó la config en README
git commit -m "docs: configuración ReaLearn para router OSC"
```

---

### Task 5: ReaLearn — puente por acciones REAPER (opcional, v2)

**Objective:** Disparar ReaLearn mediante acciones de REAPER (`OSC:INTRO`) en vez de loopback — habilita teclado/pedal como gatillos alternativos del mismo evento.

**Files:**
- Modify: `Scripts/Reaset Scripts/ReaSet_OSCTrack.py` (modo `action`)

**Step 1 — Crear acciones custom**
1. REAPER → Actions → **New action…** → Custom action… (vacía) por cada evento del show: `OSC:INTRO`, `OSC:CHORUS1`, etc. (Se pueden crear con *ReaScript: Load…* si se prefiere un generador.)
2. Anotar el Command ID de cada una (columna ID en Action List, ej. `_RSabc123`).

**Step 2 — Script: disparar acción en vez de UDP**

```python
def fire_action(event_name):
    cmd = reaper.NamedCommandLookup("OSC:" + event_name)   # no resuelve custom actions vacías; ver nota
    if cmd == 0:
        # fallback: buscar por nombre no es directo; documentar el Command ID en ExtState
        cmd = int(cfg("action_id_" + event_name, "0"))
    if cmd:
        reaper.Main_OnCommand(cmd, 0)
```

> **Nota de diseño:** `NamedCommandLookup` resuelve acciones con nombre de script/extensiones. Para custom actions vacías, lo fiable es guardar el Command ID en ExtState (`ReaSetOSC / action_id_INTRO`). Alternativa más limpia: usar las **propias acciones que ReaLearn registra** (`ReaLearn: <instance>: <mapping>`) — esas SÍ las resuelve `NamedCommandLookup`; configurar cada mapping de ReaLearn con un **source = Action** que escuche `OSC:<evento>` como *nombre de acción* — depende de la versión.

**Step 3 — ReaLearn: source = Action**
1. En el mapping de ReaLearn: **Source** = `Action` → elegir la acción `OSC:INTRO`.
2. **Target** = OSC → QLab/EOS (igual que Task 4).
3. Verificar: disparar la acción manualmente desde Action List → el OSC sale; desde el timeline (script) → igual.

**Step 4 — Bonus: pedal/teclado**
- Asignar la acción `OSC:INTRO` a un atajo de teclado o a MIDI CC en REAPER → el mismo evento lógico ahora tiene 3 gatillos: timeline, acción manual, pedal.

**Step 5 — Commit**
```bash
git add "Scripts/Reaset Scripts/ReaSet_OSCTrack.py"
git commit -m "feat: puente OSC tracks por acciones REAPER (opcional)"
```

---

### Task 6: Integración con ReaSet (opcional)

**Objective:** Mostrar el evento OSC actual en el Live View de ReaSet.

**Files:**
- Modify: `Reaset.lua` (publicar evento actual)
- Modify: `ReaSet.html` (mostrar badge)

**Step 1 — Reaset.lua publica el estado**
- En el tick loop de `Reaset.lua`, leer `ReaSetOSC / last_event` (ExtState) y publicarlo en el ExtState de ReaSet (ej. `ReaSet / osc_event`) o exponerlo en el JSON que ya sirve a `ReaSet.html` (mismo canal de poll del transporte).

**Step 2 — ReaSet.html muestra el badge**
- En el Live View (o junto al loop counter), un badge discreto `OSC: <último evento>` que se apaga a los ~5s sin nuevo evento (timestamp).

**Step 3 — Verificar**
- Reproducir con items OSC → el badge aparece en el iPad del director y en los Players (llega por el canal de estado ya existente, sin tráfico extra).

**Step 4 — Commit**
```bash
git add Reaset.lua ReaSet.html
git commit -m "feat: badge de evento OSC en Live View"
```

---

### Task 7: Documentación, pruebas finales y rollback

**Objective:** Documentar en el repo y validar en condiciones de show.

**Files:**
- Modify: `README.md` (nueva sección "OSC Tracks")
- Modify: `CHANGELOG.md`
- Modify: `ROADMAP.md` (marcar como hecho lo que se implemente)

**Step 1 — README**
- Nueva sección: qué es el track `OSC`, protocolo de eventos (tabla de Task "Protocolo"), los dos modos (`direct`/`realearn`), instalación de ReaLearn, ejemplo RDV.rpp.

**Step 2 — CHANGELOG**
- Entrada `v2.3 — OSC Tracks (híbrido ReaScript + ReaLearn)` con bullet por tarea completada (EN + ES, como el resto).

**Step 3 — Prueba de show (no el show real)**
1. Workspace de prueba de QLab abierto (no el show).
2. Sesión de prueba con 3 regiones + items OSC.
3. Verificar: cruce correcto, sin dobles disparos, sin lag, transporte detenido no dispara.
4. Prueba de stress: 10 items en una canción → todos disparan en orden.

**Step 4 — Rollback documentado**
- Quitar el script: Actions → ReaScript → *Close current script* (o desactivar `ReaSetOSC / enabled = 0`).
- Desactivar ReaLearn: desmarcar el instance.
- Repo: `git checkout tags/before-osc-tracks`.

**Step 5 — Commit**
```bash
git add README.md CHANGELOG.md ROADMAP.md
git commit -m "docs: OSC tracks — README, CHANGELOG, ROADMAP"
```

---

## Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| REAPER no detecta Python 3.13 | Task 0 Step 3 (apuntar manual al framework). Fallback: reescribir en Lua usando `reaper.ExecProcess` para un sender externo — lento, última opción. |
| Lua no tiene sockets UDP | No usar Lua para UDP. js_ReaScriptAPI **no** expone UDP. Python es el runtime correcto. |
| ReaLearn sin soporte OSC (versión vieja) | Task 1 Step 3: verificar ≥ 2.12; actualizar por ReaPack. |
| Firewall macOS bloquea UDP | System Settings → Network → Firewall: permitir REAPER y Python en puertos usados (53000, 8000, 9002). |
| Doble disparo (seek + play) | El script usa cruce entre ticks (`_last_pos < start <= pos`) y no dispara al arrancar. Probar seek durante play en Task 7. |
| Wildcard de path de ReaLearn varía por versión | Task 4 Step 2: consultar doc de la versión instalada; documentar la que funcione. |
| Items OSC movidos/renombrados durante el show | El script relee `P_NAME` en cada cruce (sin caché persistente) — cambios se reflejan al instante. |

## Criterios de aceptación (Definition of Done)

- [ ] `ReaSet_OSCTrack.py` corre en defer loop y loguea eventos al cruzar items (Task 2)
- [ ] Envía OSC directo a QLab y lo confirma un monitor UDP (Task 3)
- [ ] ReaLearn recibe eventos por loopback y los rutea transformados a ≥ 2 destinos (Task 4)
- [ ] (Opcional) El mismo evento se dispara por timeline y por acción/pedal (Task 5)
- [ ] Badge de evento actual visible en Live View (Task 6, si se hace)
- [ ] README + CHANGELOG actualizados, EN + ES (Task 7)
- [ ] Prueba de stress superada sin dobles disparos ni lag (Task 7)

---

*Plan creado: 2026-08-07 · Autor: Auri · Repo: djenttleman/ReaSet · Rama sugerida: testing/Auri*
