<p align="center"><a href="../README.es.md">← Descripción de ReaSet</a> · <a href="USER_GUIDE.md">English</a></p>

# Guía de usuario de ReaSet

> Referencia completa de instalación, configuración y operación en vivo. Para comenzar rápido, usa el [inicio rápido del README](../README.es.md#inicio-rápido).

---

## 📌 Índice (ES)
- [💛 Apoya el proyecto](#-apoya-el-proyecto)
- [1) ¿Qué es ReaSet?](#1-qué-es-reaset)
- [2) Funcionalidades principales](#2-funcionalidades-principales)
- [3) Créditos y agradecimientos](#3-créditos-y-agradecimientos)
- [4) Requisitos](#4-requisitos)
- [5) Herramientas](#5-herramientas)
- [6) Instalación](#6-instalación)
- [7) Configuración de uso](#7-configuración-de-uso)
- [8) Manual de uso](#8-manual-de-uso-interactivo)
  - [Nombres de las pistas de Letras y Acordes](#nombres-de-las-pistas-de-letras-y-acordes)
  - [Filtros de pantalla](#filtros-de-pantalla)
  - [MIDI Learn](#-midi-learn-1)
  - [Referencia de comandos en nombres de región](#referencia-de-comandos-en-nombres-de-región)
- [9) Atajos de teclado](#9-atajos-de-teclado)
- [10) Solución rápida de problemas](#10-solución-rápida-de-problemas)

---

## 💛 Apoya el proyecto
Si este proyecto te sirve, puedes apoyar su desarrollo aquí:

<a href="https://ko-fi.com/W7W81VLW05" target="_blank">
  <img src="https://storage.ko-fi.com/cdn/kofi3.png?v=6" alt="Invítame un café en Ko-fi" height="36" style="border:0px;height:36px;" />
</a>

📜 [Changelog](../CHANGELOG.md)

---

## 1) ¿Qué es ReaSet?
**ReaSet** es una interfaz web para **REAPER** orientada a shows en vivo y gestión de setlists.

Base del proyecto:
- Inspirado en **ReaSetlistManager** de `suckyble`.
- Extendido con visualización de **letras y acordes** usando lógica/script de **X-Raym**.

Objetivo principal:
- Ordenar y ejecutar canciones (regiones) durante un show.
- Controlar transporte (play/stop/cue/next).
- Administrar múltiples setlists, guardados junto al proyecto de REAPER.
- Mostrar letras y acordes sincronizados desde pistas dedicadas.

---

## 2) Funcionalidades principales
- ✅ Gestión de setlists (crear/eliminar/cambiar).
- 🔀 Drag & drop para reordenar canciones.
- 🎯 Estado por canción: activa, en cola, omitida, loop, chain.
- ⏯️ Controles de transporte en pantalla.
- 💾 Exportación/importación de setlists en JSON.
- 🗄️ Setlists guardados en `<carpeta del proyecto>/reaset/setlists/`, un archivo cada uno — viajan con el `.rpp`. El resto de las preferencias sigue en `localStorage`, aislado por proyecto.
- 🎤 Panel de letras + 🎸 panel de acordes.
- 🎨 Personalización visual (temas, tipografías, tamaños, color de acordes, filtros de pantalla).
- 🗂️ Regiones anidadas con loop, skip, color y notas individuales por sección.
- 🏷️ Sistema de comandos inline — controla comportamiento directamente desde los nombres de región en REAPER.
- 🔢 Badge de loop fraccionario (ej. `2/4`) visible en tiempo real sobre la sección activa.
- 🖥️ Live View con barra de progreso de sub-región, indicador de sección siguiente y contador de loops.
- 🌗 Filtros de pantalla en tiempo real: luminancia, contraste y saturación desde la sidebar.
- 🎬🎧 Modo Director/Player — instancias de solo lectura para músicos que nunca pueden
  mandarle un comando a REAPER, con setlist compartido sincronizado desde el Director.

Archivo principal:
- `ReaSet.html`

Dependencias incluidas:
- `Sortable.min.js`

---

## 3) Créditos y agradecimientos
### Proyecto base
- **suckyble / ReaSetlistManager**  
- https://github.com/suckyble/ReaSetlistManager

### Integración de letras y acordes
- **X-Raym / REAPER-ReaScripts**  
- https://github.com/X-Raym/REAPER-ReaScripts/tree/master/Web%20Interfaces
- Script de referencia:  
  `Convert Lyrics track items notes for the dedicated web browser interface.lua`

### Librería de ordenamiento
- **SortableJS** (`Sortable.min.js`)

### Proceso de desarrollo asistido por IA
Este proyecto fue iterado, depurado y testeado con apoyo de:
- **Claude (cowork)**
- **Google (Antigravity)**

La validación funcional final se hizo en REAPER con pruebas reales de uso en setlist.

> ⚖️ Nota legal: ReaSet v3.0+ es propietario y de uso gratuito — ver [`LICENSE`](../LICENSE).
> Las versiones hasta la v2.x fueron GPL v3 y lo siguen siendo. Los scripts
> históricos de terceros ya no forman parte de la distribución actual; las
> versiones publicadas siguen disponibles en los tags y el historial de Git.

---

## 4) Requisitos
### Software
1. **REAPER** (v5+ recomendado; ideal versión reciente).
2. Navegador web (desktop/tablet/móvil).
3. Proyecto REAPER con regiones (normalmente una región por canción).

### Archivos mínimos
- `ReaSet.html`
- `Sortable.min.js`
- `Reaset.lua` — **script único unificado** (motor de loop + letras + acordes).

> `Reaset.lua` es el único script complementario soportado. Reemplaza los
> antiguos helpers separados de loop, letras y acordes.

### Pistas requeridas para letras/acordes
- Una pista llamada **exactamente** `Lyrics` — alimenta el panel 🎤 Letras.
- Una pista llamada **exactamente** `Chords` — alimenta el panel 🎸 Acordes.
- Cada item debe llevar su texto en **Item Notes**.

El nombre **es** el comando, y es exacto: con mayúscula inicial y nada
alrededor de la palabra. `lyrics`, `LYRICS` y `01 - Lyrics` **no** coinciden —
pero una pista que está a un solo renombrado de distancia se reconoce y se
nombra en el panel, así te dice qué corregir en vez de dejarte con una pantalla
vacía. Ambas pistas son **opcionales**.
Ver [Nombres de las pistas de Letras y Acordes](#nombres-de-las-pistas-de-letras-y-acordes)
para las reglas completas.

### Compatibilidad de scripting
Los scripts usan `reaper.ULT_GetMediaItemNote`.
- Si tu REAPER no reconoce esa función, instala entorno/API compatible (ej. Ultraschall API) o adapta el método de lectura de notas.

---

## 5) Herramientas
Scripts independientes opcionales en `Tools/`. Ninguno hace falta para que
ReaSet funcione — la instalación siempre activa es solo `Reaset.lua` +
`ReaSet.html` — son utilidades a las que recurrís de vez en cuando: una para
crear contenido, otra para diagnosticar el puente de letras/acordes.

### 🎤 Lyrics Tapper — `Tools/Lyrics_Tapper.lua`
Herramienta independiente para REAPER/ReaImGui que sirve para **construir**
los items de `lyrics`/`chords`/`notes` que ReaSet lee. Pega un bloque de
texto, presioná **ARM** y luego marcá el ritmo (mouse o **Space**) mientras
suena la canción: cada tap cierra el item de la línea anterior y abre el
siguiente en la posición actual, al estilo teleprompter. Con N líneas, son N
taps para colocarlas todas, más **un tap más** para cerrar el último item y
terminar ahí mismo — no hace falta un Stop aparte para terminar limpio,
aunque Stop sigue disponible en cualquier momento para acabar antes de tiempo.
Detecta la pista destino con las mismas reglas de nombre flexibles que
`Reaset.lua`, la crea si no existe, y filtra encabezados de sección ("Coro",
"Verso 2", "[Chorus]", …) para que no terminen como items de letra.

- Requiere la extensión **ReaImGui** (aparte de SWS).
- Cárgalo con Actions → ReaScript: Load… → `Tools/Lyrics_Tapper.lua` → Run.

### 🔍 ReaSet Diagnose — `Tools/ReaSet_Diagnose.lua`
Informe de diagnóstico de solo lectura, de una sola pasada, para el puente de
letras/acordes — recurrí a él cuando el
[mensaje de estado in-app](#10-solución-rápida-de-problemas) no alcanza por
sí solo. Imprime cada pista con su nombre normalizado y cantidad de items,
qué pista elegiría cada puente, si SWS está presente, la posición del cursor,
y un volcado de las notas item por item — detectando al instante pistas que
se pisan entre sí (dos coincidiendo con la misma palabra clave) y notas
vacías. También se autotestea en una posición conocida como válida, así un
playhead mal ubicado nunca puede parecer un puente roto.

- Cárgalo con Actions → ReaScript: Load… → `Tools/ReaSet_Diagnose.lua` → Run.

### 🗄️ Library Doctor — `Tools/ReaSet_LibraryDoctor.lua`
La misma idea para la biblioteca de setlists. También de solo lectura. Imprime
la carpeta `/reaset/setlists` del proyecto con cada archivo de setlist y su
cantidad de canciones, cuál `reaper_www_root` tiene realmente `ReaSet.html` (y
si es escribible), si existe el índice que el navegador consulta, y qué fue lo
último que publicó `Reaset.lua`. Entre los dos se ve exactamente en qué eslabón
se cortó el camino navegador → `Reaset.lua` → disco — en vez de un setlist que
simplemente no se guarda y no dice nada.

- Cárgalo con Actions → ReaScript: Load… → `Tools/ReaSet_LibraryDoctor.lua` → Run.

---

## 6) Instalación

### Recomendado — Instalar con ReaBoot

[**Instalar ReaSet con ReaBoot**](https://www.reaboot.com/install/https%3A%2F%2Fraw.githubusercontent.com%2Fdjenttleman%2FReaSet%2Fmain%2Freaboot.json)

ReaBoot instala ReaPack (si hace falta), registra `Reaset.lua` en la lista de
acciones Main de REAPER y coloca los archivos web en `reaper_www_root`. El
instalador también ofrece las herramientas opcionales de ReaSet, ReaImGui y la
extensión SWS recomendada.

Después de instalar, abre **Actions > Show action list**, busca **Reaset** y
ejecútalo. ReaBoot no modifica preferencias del usuario deliberadamente, por
lo que activarlo como Startup Action de REAPER sigue siendo un paso manual
recomendado.

### Instalación manual

#### Paso 1 — Copiar interfaz web
Copiar en la carpeta web de REAPER (donde existe `main.js`):
- `ReaSet.html`
- `Sortable.min.js`

#### Rutas por defecto (REAPER Resource Path)
> En REAPER: **Options > Show REAPER resource path in explorer/finder**.

**macOS**
- Resource Path: `~/Library/Application Support/REAPER/`
- Web root: `~/Library/Application Support/REAPER/reaper_www_root/`

**Windows**
- Resource Path: `%APPDATA%\REAPER\`
- Web root: `%APPDATA%\REAPER\reaper_www_root\`

**Linux**
- Resource Path: `~/.config/REAPER/`
- Web root: `~/.config/REAPER/reaper_www_root/`

> `main.js` lo provee REAPER Web Interface (no viene en este proyecto).

#### Paso 2 — Instalar el script Lua (un solo script)
1. Abrir REAPER.
2. Ir a **Actions > Show action list**.
3. Usar **ReaScript: Load...** y cargar **`Reaset.lua`**.
4. Buscar **"Reaset"** en la lista de acciones y **ejecutarlo** una vez.
5. (Recomendado) Añadirlo en **Options > Preferences > General > Startup actions**
   (o como *Global startup action* de SWS) para que arranque solo con REAPER.

> `Reaset.lua` es un único script de fondo persistente que corre el motor de
> loop nativo y los puentes de letras/acordes a la vez. **No hay Action ID que
> pegar** en `ReaSet.html` — la interfaz web lo detecta automáticamente.
>
> Las pistas de letras/acordes son opcionales: si falta la pista `lyrics` o
> `chords`, ese panel queda inactivo y el control de transporte/loop sigue
> funcionando.

#### Rutas por defecto para scripts
- **macOS:** `~/Library/Application Support/REAPER/Scripts/`
- **Windows:** `%APPDATA%\REAPER\Scripts\`
- **Linux:** `~/.config/REAPER/Scripts/`

#### Paso 3 — Preparar proyecto
1. Crear/renombrar pista `lyrics`.
2. Crear/renombrar pista `chords`.
3. Escribir letras/acordes en notas de items.
4. Verificar regiones de canciones en timeline.

#### Paso 4 — Abrir interfaz
1. Abrir REAPER + proyecto.
2. Abrir interfaz web y cargar `ReaSet.html`.
3. Ejecutar `Reaset.lua`.

---

## 7) Configuración de uso
### Flujo recomendado (en vivo)
1. Verificar regiones.
2. Ejecutar scripts Lyrics/Chords.
3. Abrir `ReaSet.html`.
4. Crear/seleccionar setlist.
5. Reordenar canciones y definir estados (skip/loop/chain).
6. Probar transporte antes del show.
7. Exportar `.json` de respaldo.

### Persistencia y backups
- **Los setlists viven con el proyecto**, en `<carpeta del proyecto>/reaset/setlists/`,
  un archivo JSON cada uno, escritos por `Reaset.lua`. El disco es la fuente de
  verdad: todos los dispositivos que lean ese proyecto ven los mismos setlists,
  sin ningún paso de merge. Abrís ReaSet en otra máquina o en una tablet y tu
  show simplemente está ahí.
- Esto requiere que el proyecto se haya **guardado al menos una vez** — un
  proyecto sin guardar no tiene carpeta donde escribir, y ReaSet lo avisa en la
  lista de setlists en vez de aparentar que guarda.
- Los setlists que ya tenías en un navegador se migran solos al primer abrir.
- El resto del estado (temas, tamaños, preferencias de panel) sigue siendo local
  del navegador (`localStorage`).
- Respaldos/migración vía Export/Import JSON.
- Recomendado: backup por fecha antes de cambios grandes.

### Buenas prácticas
- Nombres consistentes de regiones.
- Proyecto “Show-Ready” separado del de producción.
- Testear en el mismo dispositivo/navegador que usarás en vivo.

---

## 8) Manual de uso
### Barra superior y visualización
- **Grid View (Cuadrícula)**: Alterna entre diseño de lista detallada o tarjetas grandes para uso rápido.
- **Hide Skipped**: Oculta visualmente las canciones marcadas para "saltar" (útil en vivo para no confundirse).
- **Auto-Scroll**: Centra automáticamente la región/canción activa a medida que avanza la reproducción.
- **Edit Sets**: Abre el panel de administración donde puedes crear, renombrar, duplicar y eliminar Setlists.

### Modos y herramientas (Canvas)
- **Live View (Modo Directo)**: Activa una interfaz enfocada para performance con nombre gigante de la canción actual, progreso, siguiente canción y botones de transporte.
- **Letras y Acordes (Widgets fltantes)**: Puedes activar la visión superpuesta de pistas de Letras (`Lyrics`) y Acordes (`Chords`). En la esquina superior derecha del widget dispones de un selector de fuentes, tamaño, y personalización de color para adaptarlo a tu pantalla. 

#### Panel de letras — vista de tres líneas
El panel de letras muestra el **verso anterior arriba** y el **verso siguiente abajo** del
actual, ambos más pequeños y atenuados para que la línea activa siga siendo la dominante.
Cuando falta un vecino (inicio de la canción, o un hueco entre items) su espacio se
reserva igualmente, así la línea actual **no salta** mientras la estás leyendo.

Las líneas de contexto quedan **limitadas a la canción que suena en ese momento**: un
verso de la canción anterior o siguiente nunca se cuela en el contexto de la actual. Al
empezar una canción, el hueco "anterior" queda en blanco en vez de mostrar la última línea
de lo que sonaba antes; al terminar, el hueco "siguiente" muestra **"Siguiente: <nombre de
la canción>"** en vez del primer verso de la próxima — un aviso, no un spoiler. Esto
necesita que `Reaset.lua` publique la posición de cada vecino (se agregó junto a su texto);
con una versión anterior de `Reaset.lua` simplemente no se limita, igual que antes de
existir esta función.

Un **⚙ engranaje** discreto en la cabecera del panel abre un popover para ajustar:

| Ajuste | Opciones |
|---|---|
| **Tamaño global** | Slider de 16–120 px — el tamaño base sobre el que escala todo lo demás |
| **Línea principal** | 50–150% del tamaño global, solo la línea actual |
| **Letras secundarias** | 10–100% del tamaño global, solo las líneas anterior/siguiente |
| **Grosor** | Fino · Medio · Negrita · Black |
| **Color** | 5 presets + selector de color personalizado |
| **Versos de contexto** | Interruptor para ocultar el anterior/siguiente |

**Tamaño global**, **Línea principal** y **Letras secundarias** son tres sliders
independientes: el tamaño global fija la escala base sobre la que se mide todo, mientras
que principal/secundario controlan cada uno su(s) propia(s) línea(s) como porcentaje de
esa base — por ejemplo, puedes achicar las líneas de contexto hasta un 10% para que sean
apenas una pista, o subirlas a 100% para que igualen a la línea actual, sin mover el
tamaño de la línea actual en absoluto. Los valores por defecto (100% / 44%) reproducen el
aspecto original.

Los seis ajustes se guardan en `localStorage`, así que tu configuración de lectura
sobrevive a una recarga.

#### Panel de acordes — vista de tres en línea
El panel de acordes usa la misma lógica de vecinos, pero en **horizontal**: el acorde
anterior a la **izquierda** y el siguiente a la **derecha** del actual, ambos más pequeños
y atenuados. Se reserva el mismo espacio a ambos lados, así el acorde actual queda
ópticamente centrado por largos que sean los nombres de los acordes vecinos.

> **Un solo item = sin vecinos.** Los laterales leen el item *anterior* y *siguiente* de la
> pista `chords`. Si un único item abarca toda la canción, no hay vecinos que mostrar y los
> laterales quedan en blanco — eso es correcto, no un fallo. Divide los acordes en un item
> por cambio para tener el contexto izquierda/derecha.

#### Transiciones y franja de estado
Los versos viven en un **carrusel 3D vertical**, al estilo del Cover Flow de iOS girado 90°.
Las tres líneas son posiciones sobre un tambor: recorren su **trayectoria curva** y
**retroceden en profundidad**, pero **nunca se inclinan** — el texto siempre queda de frente
para que se lea de un vistazo.

Al avanzar un verso, el tambor **gira exactamente una posición**:

| Línea | Recorrido |
|---|---|
| Actual | Posición `0` → `-1`: asciende y retrocede, encogiendo |
| Anterior | `-1` → `-2`: continúa más allá del borde superior y desaparece |
| Siguiente | `+1` → `0`: asciende a profundidad neutra, creciendo |
| Nuevo verso | `+2` → `+1`: entra en escena desde abajo |

**Espaciado consciente del salto de línea.** La posición de cada slot se calcula
asumiendo que el verso actual ocupa una sola línea; uno que salta a dos líneas, sin
más, terminaría apretando —o casi tocando— las líneas de contexto más pequeñas
arriba y abajo, porque su desplazamiento fijo no crece con él. ReaSet mide la altura
real renderizada de la línea actual en cada cambio y aleja el anterior/siguiente medio
alto de línea por cada línea extra que salte, así el espacio se mantiene constante sin
importar si el verso actual ocupa una línea o varias.

Que todo se exprese como "cada línea avanza una posición" es lo que hace que se lea como
**una sola rotación** y no como cuatro animaciones sueltas. El radio del tambor está en
`em`, así que el carrusel escala con el tamaño de letra que elijas en el engranaje.

Los acordes usan **el mismo tambor tumbado de lado**: el acorde anterior a la izquierda y el
siguiente a la derecha, recorriendo la misma curva y retrocediendo igual, también sin
inclinarse. Al cambiar de acorde, el tambor gira una posición exactamente igual que el de
las letras.

El giro es **deliberadamente rápido — 100 ms**, cubriendo el 90% del recorrido en los
primeros ~40 ms y frenando con fuerza al final. En el escenario debes notar que la línea
cambió sin tener que verla moverse: el movimiento sostenido en el área de lectura cansa, así
que la animación está para mantenerte ubicado, no para ser observada.

Solo un avance real de un paso merece el giro. Un salto de posición, un cambio de canción o
una edición no son un paso en el tambor, así que esos hacen **fundido** — girar implicaría
una continuidad que no ocurrió. Se respeta `prefers-reduced-motion`: si tu sistema pide
menos movimiento, no se anima nada en absoluto.

Los mensajes de diagnóstico **no ocupan el área de lectura**: viven en una franja muy
tenue al pie del panel, con dos niveles de visibilidad.

| Situación | Visibilidad |
|---|---|
| Todo bien, pero no hay letra/acorde en ese punto | Apenas visible (16%) — es un estado **normal**, no un fallo |
| Algo hay que arreglar (script parado, congelado, sin track, sin SWS) | Legible (55%), sigue siendo discreto |

Cuando sí hay contenido en pantalla, la franja queda vacía. Un hueco instrumental sigue
mostrando el verso anterior y el siguiente, que es justo lo útil en ese momento.

### Nombres de las pistas de Letras y Acordes
ReaSet lee las letras y los acordes desde **dos pistas dedicadas de REAPER**, identificadas
por su nombre. `Reaset.lua` recorre el proyecto buscando estas dos palabras clave:

| Panel | Palabra clave |
|---|---|
| 🎤 Letras | `lyrics` |
| 🎸 Acordes | `chords` |

**La regla: el nombre es exacto.** Mayúscula inicial, el resto en minúsculas,
nada alrededor de la palabra. Hay una sola grafía y es la de arriba.

| Nombre de pista | ¿Detectada? | Por qué |
|---|---|---|
| `Lyrics` · `Chords` | ✅ | exactamente el comando |
| `lyrics` · `LYRICS` | ❌ | mayúsculas incorrectas — se reporta como casi-acierto |
| `*Lyrics` · `01 - Lyrics` · `[Chords]` | ❌ | la decoración no es parte del nombre — se reporta como casi-acierto |
| `Backing Lyrics` · `Lyrics Bus` · `Chords Gtr` | ❌ | pista de audio normal; no se ofrece como casi-acierto |

Antes era permisivo — ignoraba mayúsculas, quitaba símbolos y numeración — así
que ocho grafías funcionaban. Fue el intercambio equivocado: una convención que
acepta ocho grafías no es una convención, nadie converge en una, y la regla que
decide qué es una pista de letras se vuelve algo que hay que leer en el código
para saber.

Ser estricto solo sirve si equivocarse es **ruidoso**, así que un
**casi-acierto** se reconoce y se nombra. Una pista llamada `lyrics` hace que el
panel diga *«hay una pista «lyrics» — renómbrala a «Lyrics»»* en vez de reportar
"sin pista". El Lyrics Tapper hace lo mismo: se niega y te dice que renombres,
en vez de crear una segunda pista `Lyrics` al lado de la que ya tienes.

Si dos pistas se llaman `Lyrics`, gana la que **tiene items** — así una pista
divisoria o de carpeta no puede tapar silenciosamente a la real.

Ambas pistas son **opcionales**: si falta `Lyrics` o `Chords`, ese panel
simplemente queda inactivo y todo lo demás (transporte, loops, setlist) sigue
funcionando.

#### ¿Qué tipo de item?

**Un item vacío** — sin take, sin audio, sin MIDI. Es el equivalente en REAPER
de un clip MIDI vacío en Ableton, y es lo que crea el Lyrics Tapper
(`AddMediaItemToTrack`). Un item MIDI o de audio también sirve: el puente nunca
mira *dentro* del item, solo tres cosas —

| Qué | Decide |
|---|---|
| **Posición** | cuándo aparece la línea |
| **Duración** | cuánto se queda — un hueco entre items no muestra nada |
| **Item Notes** | el texto |

El texto va en las **notas del item** (doble clic en el item → *Notes*), un item
por bloque de letra o acorde.

#### Acordes dentro de la letra

Los acordes pueden escribirse **dentro del texto de la letra**, en la convención
ChordPro, y se dibujan encima de la sílaba donde caen:

```
[Am]Cuando te [F]vi, el [C]mundo se [G]paró
```

Se reconocen fundamentales, alteraciones, cualidades, extensiones y bajos con
barra — `C`, `Am`, `F#m7`, `Bb`, `Gsus4`, `Dadd9`, `G/B`. Un corchete que **no**
es un acorde se deja tal cual, así que `[intro]` y `[2x]` siguen legibles.

### Interacción de Canciones (Filas)
- Canciones con sub-secciones mostrarán un botón desplegable (Chevrón). Expándelo para ver/operar sobre las sub-regiones individualmente (Intro, Coro, etc.).
- La barra de progreso de cada canción heredará dinámicamente el color configurado a esa Región dentro del archivo de REAPER.
- **PLAY NEXT**: Activa una canción específica en la cola de REAPER y detiene la reproducción allí, esperando a que presiones Play.

### Comandos de región
- **&#9632; / &#8677; (Follow Action)**: Alterna si la canción se detiene al final o continúa sin pausas hacia la siguiente en la lista.
- **&#8635; (Loop)**: Bloquea un ciclo infinito sobre la región actual o la sub-sección seleccionada.
- **&#10005; (Skip)**: Marca la canción con una línea tachada y se la saltará de la lista de reproducción continua.

### Layout en teléfono — las pestañas se van a la sidebar
En un teléfono, las cinco pestañas de vista (SHOW / LYRICS / CHORDS / LIVE / CANVAS) salen
de la barra superior y pasan a una grilla **Views** al tope de la sidebar. No es solo por
ganar espacio: cinco pestañas en su ancho mínimo, más el botón de menú, más el bloque de
timer suman 438px de contenido en una pantalla de 375px, así que el timer y el contador de
canciones quedaban empujados **63px fuera del borde derecho** — invisibles en un teléfono.
Con las pestañas reubicadas entra todo, y la barra baja de 56px a 46px porque ya no tiene
que alojar pestañas con ícono sobre etiqueta.

El cambio lo dispara el tamaño de pantalla, no el modo Director/Player — un Director en
teléfono tiene la misma pantalla. **Tablets y escritorio conservan las pestañas arriba**,
sin cambios. La regla cubre teléfonos en vertical *y* en horizontal (`max-width: 600px` o
`max-height: 520px`); un iPad mide al menos 744px en ambas direcciones en cualquier
orientación, así que nunca entra. Un iPad en un panel angosto de Split View sí recibe el
layout de teléfono, que es lo correcto — ese panel realmente tiene tamaño de teléfono.

Los dos juegos de pestañas siempre existen en el DOM y se mantienen sincronizados, así que
rotar el teléfono o redimensionar la ventana cambia entre layouts al instante y sin dejar un
resaltado viejo.

### Modal de apariencia
Todo lo que cambia cómo se *ve* ReaSet vive en un solo modal, que se abre desde el botón
**Appearance** de la sidebar, dividido en tres pestañas:

| Pestaña | Contiene |
|---|---|
| **General** | Filtros de pantalla (luminancia / contraste / saturación), disposición, tema, idioma y pantalla completa |
| **Lyrics** | Tipografía, tamaño global, tamaño de línea principal y de contexto, grosor, color y el toggle de versos anterior/siguiente |
| **Chords** | Tipografía, tamaño y color |

Antes eran siete secciones sueltas de la sidebar — 742px de una sidebar de 1626px en un
teléfono, o sea casi la mitad del cajón eran perillas de estilo que configurás una vez y no
tocás más. La sidebar quedó en 985px y se lee como lo que es: navegación y controles de show.

Cada pestaña usa el mismo kit de controles, a ancho completo y alineado: las tipografías
son listas desplegables en vez de una grilla de botones que se parte en filas, todos los
sliders comparten un mismo estilo, y los presets de tamaño ya no son una fila aparte de
pastillas — son **marcas sobre la escala del propio slider**, así ves dónde caen S/M/L/XL
antes de arrastrar, y siguen siendo clickeables. La marca que coincide con el tamaño actual
se enciende; un valor entre marcas no enciende ninguna.

**El popover del engranaje dentro del panel de letras se queda**, y no es una segunda copia
que compita: tanto él como el modal manejan las mismas funciones, y esas escriben en todos
los controles que estén en pantalla. Cambiás el tamaño desde el engranaje mientras leés las
letras y el slider del modal ya está movido cuando lo abrís, y al revés. El engranaje es el
ajuste rápido y en contexto mientras mirás la letra; el modal es el set completo (además
tiene la tipografía, que el engranaje nunca tuvo).

### Disposición — duración por canción y vistas en pantalla completa
Dos interruptores en **Appearance → General → Disposición**, ambos recordados por dispositivo.

**Duración por canción** (encendido por defecto) oculta el tiempo a la derecha de cada fila
del setlist — y con él los tiempos de sección de una canción expandida y los de las tarjetas
de la grilla, porque son la misma información en tres lugares. Apagado, las filas llevan solo
lo que identifica a la canción. Sirve sobre todo en teléfono, donde cada píxel que recupera
el nombre vale.

**Vistas en pantalla completa** (apagado por defecto) decide si Letras, Acordes y Canvas
tapan la barra superior. Antes la tapaban siempre. Ahora la barra se queda por defecto, así
el reloj, el progreso del show y el pill de modo siguen legibles mientras leés letras o
acordes — y en tablet y escritorio deja alcanzables las **pestañas de vista**, así que ir de
Letras a Acordes ya no obliga a pasar por SHOW.

El interruptor no es la única puerta: cada una de esas tres vistas lleva un **botón ⤢** al
lado del de cerrar (solo el glifo en teléfono, con texto en pantallas anchas) que hace lo
mismo desde adentro de la vista. Es **un ajuste con dos controles**, no dos ajustes — lo
cambiás en la vista y el switch del modal ya se movió, y sobrevive a una recarga, así que lo
que decidiste en la prueba de sonido sigue ahí en el show.

### Idioma — Inglés / Español
ReaSet viene en ambos idiomas. El selector está en **Appearance → General**, justo debajo de
Theme: un control de dos celdas **EN / ES** que se aplica al instante, sin recargar.

En un dispositivo que nunca eligió, ReaSet sigue el idioma del propio navegador (español si
`navigator.language` empieza con `es`, inglés si no), así un músico hispanohablante no
recibe la app en inglés desde un dispositivo que ya declaró su preferencia. Una vez que
elegís, la decisión queda guardada por dispositivo.

La traducción funciona haciendo coincidir las cadenas mismas, no etiquetando cada elemento
con una clave: cada entrada de la tabla es simplemente `[inglés, español]` y **ambos lados
sirven como clave de búsqueda**, así el cambio es simétrico y volver a ejecutarlo es
inofensivo. Las vistas que el JS construye durante el show — el setlist, las filas de
sección, las asignaciones MIDI — se vuelven a renderizar al cambiar y después se barren, así
que nada queda en el idioma anterior.

### Pantalla completa — lanzar desde la pantalla de inicio
ReaSet puede correr sin la barra de direcciones ni la barra inferior del navegador, que en un
teléfono es la diferencia entre leer el nombre de una canción y adivinarlo. El control está en
**Appearance → General → Pantalla completa**, y muestra solamente el camino que realmente
funciona en el dispositivo que lo está mirando.

**iPhone / iPad — Añadir a pantalla de inicio.** Safari en iPhone no tiene API de pantalla
completa para elementos, así que ningún botón puede ayudar; el camino es Compartir →
**Añadir a pantalla de inicio** y después abrir ReaSet desde el ícono nuevo. Se lanza en modo
standalone: sin barra de direcciones ni barra inferior. De regalo, se desactivan el gesto de
volver atrás y el tirar-para-recargar, así que un dedo perdido a mitad del show no puede
navegar a otro lado. El modal explica los tres pasos en pantalla.

**Android / escritorio — un botón.** Estos navegadores sí exponen la Fullscreen API, y lo
importante es que *no* está detrás del muro del contexto seguro: funciona sobre el HTTP plano
que sirve REAPER. Un toque por sesión da pantalla completa real, ocultando también las barras
del sistema. El botón se pone verde y pasa a decir *Salir de pantalla completa* mientras está
activo.

> **Sin HTTPS, sin service worker, sin manifest, sin archivos extra.** Una instalación PWA "de
> verdad" necesitaría todo eso, y eso necesita un contexto seguro que el servidor HTTP plano de
> REAPER en la LAN no puede dar nunca (ahí `navigator.serviceWorker` ni siquiera existe). Las
> meta tags `apple-mobile-web-app-*` no tienen ese requisito, así que ReaSet sigue siendo **un
> solo archivo** que dejás al lado de `main.js`. El ícono va embebido en la página como data URI
> en vez de ir como imagen aparte, por la misma razón.

**Lo que esto no te da** es arranque offline. Sin service worker no se cachea nada, así que si
REAPER está apagado o fuera de alcance el ícono abre en una página de error. Y ojo: en modo
standalone no hay botón de recargar ni barra de direcciones — la salida es cerrar la app y
volver a abrirla.

### Filtros de pantalla
Disponibles en **Settings — Appearance** dentro de la sidebar. Tres sliders independientes aplican un filtro CSS en tiempo real al cuerpo del setlist:
- **Luminancia** — 50% a 150% (por defecto 100%)
- **Contraste** — 50% a 150% (por defecto 100%)
- **Saturación** — 0% a 200% (por defecto 100%)

Los valores persisten entre sesiones. El botón "Restablecer valores" devuelve todo al 100%.

### 🎹 MIDI Learn
Está en la sidebar (botón **MIDI Learn**). Mapea notas/mensajes CC de un
controlador MIDI conectado a Play, Stop, Play/Pause, canción siguiente/anterior,
sección siguiente/anterior, toggle loop, reiniciar canción y toggle skip.
Hacé click en **Escuchar siguiente nota / CC…**, mandá el mensaje desde tu
controlador, y la asignación queda guardada; podés tener varias activas a la
vez, y borrarlas de a una o todas juntas.

> ⛔ **Desactivado en la app por ahora.** El módulo MIDI completo está
> comentado —abajo el motivo— y vuelve cuando ReaSet sea una app instalable
> con acceso MIDI real.

> ⚠️ **No soportado por Safari — macOS, iPadOS o iOS**, en
> ningún dispositivo de Apple. MIDI Learn está construido sobre la **Web
> MIDI API** (`navigator.requestMIDIAccess`), que Safari nunca implementó,
> en ninguna plataforma de Apple. El panel de MIDI Learn no va a mostrar
> dispositivos ahí — no es un bug para reportar, es una API de navegador
> que falta. Usá un navegador basado en Chromium (Chrome, Edge), o mapeá el
> controlador directamente en REAPER en vez de por el navegador (el mapeo
> MIDI nativo de REAPER no se ve afectado por esto para nada).

### Smooth Seek
**Smooth Seek** está activado por defecto en **Show Options** y se guarda de forma independiente para cada proyecto de REAPER. Cuando la reproducción ya está en curso, al seleccionar manualmente una canción o sección —incluidos los controles MIDI **Siguiente/Anterior sección** y **Reiniciar canción**— ReaSet envía a REAPER solo la nueva posición. Así REAPER puede respetar su propia preferencia *No cambiar inmediatamente la posición de reproducción al buscar (smooth seek)*.

Desactiva Smooth Seek cuando un controlador necesite un salto inmediato. Al seleccionar una canción mientras REAPER está detenido, la reproducción sigue iniciándose en ambos casos. Queue Mode, Cue, los loops y las transiciones automáticas conservan su comportamiento actual.

### Referencia de comandos en nombres de región
ReaSet interpreta comandos especiales escritos directamente en los nombres de región y marcadores de REAPER. Se pueden combinar libremente. El texto que queda tras parsear todos los comandos es el nombre que se muestra en la app.

**Ejemplo:**
```
Chorus {pre-coro} +LOOP:4 [green] [.bold] [1:20]
```

#### Comandos `+` — Comportamiento de reproducción

| Comando | Descripción |
|---|---|
| `+PAUSE` | Pausa la reproducción al llegar al final de la sección. |
| `+SKIP` | Marca la sección como omitida por defecto. Aparece tachada. |
| `+LOOP` | Activa el loop infinito de la sección. |
| `+LOOP:N` | Repite la sección exactamente **N** veces y luego continúa. Muestra un badge `X/N` en vivo. |
| `+LOOPFULL` | Loop con prioridad absoluta — si hay una canción en cola, espera a que el loop termine. |

#### `[]` Corchetes — Apariencia y duración

| Comando | Descripción |
|---|---|
| `[color]` | Asigna un color de la paleta a la tarjeta. |
| `[mm:ss]` | Sobreescribe la duración mostrada de la sección. |
| `[nosong]` | Excluye el elemento del conteo y numeración de canciones. Aparece en opacidad reducida. |
| `[.clase]` | Aplica una clase CSS de estilo al nombre. |

Colores disponibles: `gray` · `red` · `orange` · `amber` · `yellow` · `lime` · `green` · `emerald` · `teal` · `cyan` · `sky` · `blue` · `indigo` · `violet` · `purple` · `fuchsia` · `pink` · `rose`

Clases disponibles: `.bold` · `.dim` · `.italic` · `.loud`

#### `{}` Llaves — Texto informativo

| Comando | Descripción |
|---|---|
| `{texto}` | Muestra texto auxiliar en cursiva junto al nombre de la sección. No aparece en Live View ni Canvas. |

#### Prefijos especiales — Solo marcadores

| Comando | Descripción |
|---|---|
| `>` | Convierte el marcador en una sub-sección de la canción activa. |
| `*` | Ignora completamente el marcador — no aparece en la app. |
| `>>> NombreDestino` | Salta automáticamente a la región cuyo nombre coincida con `NombreDestino` al terminar esta sección. |

#### Palabras reservadas

| Nombre | Descripción |
|---|---|
| `STOP` | Marcador de parada de reproducción. |
| `SONG END` | Alias de `STOP`. |

---

### Modo Director / Player
Toda instancia de ReaSet habla directo con REAPER a través del mismo Web Interface — no hay
servidor propio de ReaSet, así que control y visualización comparten un solo canal. Eso
significa que dos dispositivos abiertos a la vez pueden pelearse de verdad por REAPER (los
dos auto-avanzando al terminar una canción, por ejemplo). El modo Director/Player existe
para hacer eso imposible en un dispositivo que no debería estar controlando el show — la
tablet de un músico, por ejemplo.

**Al cargar por primera vez (o después de limpiar `localStorage`), ReaSet exige elegir:**

| Modo | Qué puede hacer |
|---|---|
| 🎬 **Director** | Todo lo que ReaSet ya hace: transporte, cola, loops, skip/chain, MIDI, reordenar. |
| 🎧 **Player (Músico)** | Solo lectura: canción/sección/progreso en vivo, letras, acordes. Las preferencias de pantalla locales (canvas, colores, fuentes, filtros) siguen siendo tuyas para cambiar — nada de eso llega a REAPER. |

La elección se **recuerda** (`localStorage`, no por sesión) — un refresco, un reinicio de la
app o del dispositivo no vuelve a preguntar. Es deliberado: recordar un modo guardado no
otorga ningún privilegio nuevo (ese dispositivo ya eligió Director una vez, a propósito), y
volver a forzar el selector en cada refresco accidental dejaría a un Director trabado detrás
de un modal justo en el peor momento. Un pequeño badge en la esquina superior derecha
siempre muestra el modo actual; hacé click en cualquier momento para cambiarlo (sin
confirmación al pasar de Director a Player, ya que eso solo reduce lo que el dispositivo
puede hacer).

**Cómo se hace cumplir:** todo comando que esta página pueda llegar a mandarle a REAPER pasa
por una sola función (`wwr_req`). En modo Player, esa función descarta cualquier cosa que no
sea una lectura simple — así que ni un click perdido, ni un atajo de teclado que quedó
activo, ni una reconexión que gane la carrera contra la verificación de modo pueden mover el
transporte de REAPER. Los botones y atajos además se ven atenuados/deshabilitados en modo
Player por honestidad (para que un tap no parezca que falló en silencio), pero esa es una
capa de cortesía — el bloqueo a nivel de red es lo que realmente sostiene la garantía.

**El setlist se ve distinto en modo Player**, porque la pantalla de un músico tiene otro
trabajo que la de un Director. Los controles que un Player nunca va a poder usar se
*eliminan* en vez de atenuarse — el drag handle, los menús ⋮ de edición, el botón "Play
Song" — lo que en un teléfono le devuelve unos 217px de una fila de 347px al nombre de la
canción (venía recibiendo 18px, más o menos una letra del título). Los toggles de
skip/loop/chain se colapsan a badges compactos que aparecen solo cuando el flag está
activo: un Player no puede presionarlos, pero *sí* necesita saber que una canción loopea o
engancha con la siguiente. Las canciones skipeadas quedan claramente grises, la fila que
está sonando se muestra a intensidad plena, y el resto se atenúa apenas para que los
nombres, tiempos y progreso se lean bien en escena.

**La sidebar se filtra con el mismo criterio.** Un Player conserva todo lo que solo cambia
su propia pantalla — Display Filters, Theme, fuentes/tamaños/colores de letras y acordes,
más **Auto-Scroll, Hide Skips y Grid View**, que son toggles de vista que nunca llegan a
REAPER (Auto-Scroll es un `scrollIntoView()` pelado; los otros dos solo re-renderizan la
lista). Lo que se va es lo que dirige el *show*: Queue Mode y Smooth Seek cambian cómo
busca un click, y un Player no puede clickear; Auto-Stop e Init Song MIDI mandan comandos a
REAPER directamente; Stop Hold ajusta un botón de transporte que en modo Player ni existe;
y MIDI Learn mapea un controlador contra esos mismos comandos bloqueados, así que un Player
podría asignar un pedal y después verlo no hacer nada. Los tres toggles de vista se quedan a
propósito — son los mismos que el modo Player ya deja funcionando por teclado, así que
esconder sus switches contradiría atajos que sí responden.

La barra de transporte inferior sigue la misma regla. PLAY / STOP / Loop desaparecen en
modo Player — no hacen nada, y PLAY era el peor de los tres, porque su etiqueta es la
*acción* y no el estado: mientras REAPER reproducía decía "PAUSE" en una pantalla donde
nada se puede pausar. El estado del transporte ya está en pantalla y más claro: la fila
activa tiene el relleno de progreso avanzando y su tiempo en cuenta regresiva. **SYNC se
queda** — reinicia la conexión de sondeo, que es una lectura, y es la única recuperación
que tiene un músico si el wifi del lugar se cae en medio del show y la reconexión
automática no alcanza. (Antes quedaba bloqueado por el propio guard de clicks de la barra,
así que el único botón que le servía a un Player ahí abajo era inalcanzable; ahora funciona.)

> **No es un límite de seguridad.** El propio Web Interface de REAPER no tiene autenticación
> — cualquiera en la misma red que conozca el endpoint ya puede controlarlo directamente, con
> o sin ReaSet. El modo Player evita que *ReaSet* sea una puerta de entrada; no cierra la red.

#### PIN de Director (opcional)
Por defecto, elegir **Director** en el selector (o pasar el badge de Músico a Director) no
pide nada más que un tap — está bien para un solo usuario, menos bien cuando una banda
comparte una sesión de REAPER y no querés que un tap curioso en el teléfono de alguien le
entregue el transporte. Un Director puede poner un PIN desde el sidebar (**Setlist Sync →
Set/Change Director PIN**); una vez configurado, cualquier dispositivo que elija Director
activamente — no uno que recuerda su elección ya guardada en un refresco — lo pide primero.

- El PIN en sí nunca viaja en texto plano: solo se guarda un hash pequeño, en el ExtState
  persistido del propio REAPER (sobrevive un reinicio de REAPER, el mismo mecanismo que ya
  usa la función de loop nativo), así que cada dispositivo verifica contra el mismo valor sin
  necesidad de servidor.
- Dejá el prompt vacío al configurarlo para quitar el PIN por completo.
- Igual que el bloqueo de escritura del modo Player, **esto es un disuasivo, no seguridad
  real** — el algoritmo de hash es deliberadamente simple, y el Web Interface de REAPER
  sigue sin tener autenticación debajo de todo esto (ver el recuadro de arriba). Frena un tap
  distraído, no a alguien decidido con acceso a la red.

#### Dos Directores a la vez
ReaSet ahora vigila esto en vez de quedarse callado al respecto: cada Director se
reanuncia "estoy activo" cada pocos segundos mientras sostiene el modo. Si un segundo
dispositivo *elige* Director mientras otro ya se está anunciando, se le avisa antes de
completar el cambio y puede dar marcha atrás. Si un segundo Director aparece más tarde —
en medio de un show, en un dispositivo que ya tenía el modo guardado y se saltó ese aviso al
arrancar — un banner rojo lo indica mientras dure el conflicto, y se limpia solo en el
momento en que el otro Director cierra su pestaña o su propio heartbeat queda obsoleto.
Nada se bloquea en ningún caso — REAPER sigue siendo tuyo para compartir a propósito si
querés (un Director de reemplazo cubriendo una canción, por ejemplo) — solo que ya no podés
terminar en ese estado *por accidente* sin saberlo.

El aviso nombra al otro dispositivo — *"El dispositivo 'X' ya está activo como
Director"* — en vez de solo "otro dispositivo". Todo dispositivo tiene un
nombre: por defecto una estimación de OS+navegador (*"iPad · Safari"*), o uno
propio que definís desde el sidebar (**This device: ... → Rename this
device**), algo que conviene hacer una vez por tablet antes de un show para
que el aviso de conflicto sirva de algo.

#### Sincronización de setlist compartido (Director → Players)
El orden y las banderas de skip/loop/chain de cada canción viven en el `localStorage` del
propio navegador — normalmente privado a ese dispositivo. Para que los Players vean el
setlist *real del Director* en vez del suyo propio (viejo o por defecto), un Director puede
empujar una foto que `Reaset.lua` escribe en un archivo (`reaset_setlist_sync.json`) al lado
de `ReaSet.html`; los Players lo leen.

- **El push es automático**, con debounce de ~1s después de cualquier edición (reordenar,
  toggle de skip/loop/chain, importar). No hace falta acordarse de sincronizar antes de un show.
- **El pull es manual** para un Director (sidebar → *Pull setlist from shared*) — adoptar el
  setlist compartido de otro dispositivo sobreescribe ediciones locales no sincronizadas, así
  que primero pregunta. Los Players hacen pull automático cada pocos segundos en segundo
  plano; no hay nada que clickear.
- Un setlist compartido que no coincide con el **proyecto de REAPER actualmente abierto**
  (verificado con el mismo fingerprint de proyecto que usa el almacenamiento por proyecto) se
  rechaza en vez de aplicarse — vas a ver una advertencia en vez de un setlist mezclado.
- **Límites conocidos, a propósito, para esta primera versión:** solo sincronizan el orden y
  las banderas del setlist activo — no toda la biblioteca de setlists nombrados, ni el
  objetivo de cola en vivo (es estado de UI transitorio; la canción realmente sonando ya le
  llega gratis a los Players vía el transporte de REAPER). Dos Directores empujando casi al
  mismo tiempo sigue significando que gana el último push — el banner de conflicto de arriba
  te avisa que está pasando, pero no combina los dos pushes. Un chunk perdido (raro, necesita
  un corte de red justo en medio de un push) se autorepara en aproximadamente un segundo
  cuando el siguiente tick reintenta — en el peor caso, ese push se salta en silencio y el
  push de la siguiente edición lo reemplaza.

---

## 9) Atajos de teclado
ReaSet soporta los siguientes comandos de teclado globales para mejorar el control en entornos rígidos:

| Tecla | Acción |
| --- | --- |
| **`Space`** | Play / Pause (Alternar estado general) |
| **`Enter`** | Smart Stop (Detiene en el inicio de la región activa actual) |
| **`Escape`** | Cierra la vista Live View. Si ya está cerrada, desactiva un "Loop" activo temporalmente. |
| **`V`** | Alterna abrir/cerrar la vista "Live View" |
| **`L`** | Alterna abrir/cerrar el widget flotante de Letras (Lyrics) |
| **`C`** | Alterna abrir/cerrar el widget flotante de Acordes (Chords) |
| **`G`** | Alterna entre vista de Lista (List View) y Cuadrícula (Grid View) |
| **`O`** | Activa/Desactiva Loop en la Región/Sub-región en curso en vivo |
| **`Flecha Derecha`** | Carga la siguiente canción válida en la cola (Cue) |
| **`Flecha Izquierda`** | Salta directamente al punto de reproducción de la canción actual en curso |
| **`Flecha Arriba`** | Carga la canción válida anterior en la cola |
| **`Flecha Abajo`** | Reinicia la cola a la primera canción del Setlist completo |

---

## 10) Solución rápida de problemas
### ❌ No aparecen letras o acordes
El mensaje del panel vacío te dice la causa **real** — léelo antes de cambiar nada.
`Reaset.lua` publica su estado en vivo:

| Mensaje | Significado | Solución |
|---|---|---|
| *"Reaset.lua no está corriendo"* | El script complementario soportado no está cargado | Actions → ReaScript: Load… → `Reaset.lua` → Run |
| *"No se encontró ningún track llamado lyrics/chords"* | El script vive, pero ninguna pista coincidió | Revisa el nombre según [las reglas](#nombres-de-las-pistas-de-letras-y-acordes) |
| *"Falta la extensión SWS"* | `ULT_GetMediaItemNote` no está disponible | Instala [SWS](https://www.sws-extension.org/) |
| *"Track X detectado — no hay item bajo el cursor"* | Todo funciona | Mueve el playhead sobre un item que tenga **notas** |

El último es la falsa alarma más común: la pista se encontró, pero el playhead no
está sobre ningún item, o el campo **Notes** del item está vacío.

#### 🔍 Script de diagnóstico
Si el mensaje no basta, ejecutá **`Tools/ReaSet_Diagnose.lua`** — ver
[Herramientas](#5-herramientas) para saber qué informa.

### ❌ Error `ULT_GetMediaItemNote`
- Falta entorno/API compatible; instalar dependencia o adaptar script.

### ❌ Interfaz sin datos/control
- Verificar Web Interface habilitada y accesible.
- Verificar carga correcta de `main.js` en la misma carpeta.

### ❌ El ícono de la pantalla de inicio abre con un error de HTTPS
Safari 18.2 agregó *«Avisar antes de conectarse a un sitio web por HTTP»*, que en muchos
dispositivos **bloquea en vez de avisar**. El Web Interface de REAPER sirve HTTP plano, así que
el ícono no abre y muestra un mensaje sobre HTTPS. Desactivá esa opción en **Ajustes → Apps →
Safari** (en Privacidad y seguridad). Agregar ReaSet a la pantalla de inicio no requiere HTTPS
por sí mismo — lo único que estorba es ese ajuste de Safari.

### ❌ MIDI Learn no muestra dispositivos / no responde
**No soportado actualmente en Safari — macOS, iPadOS o iOS**, en ningún
dispositivo de Apple. Esto no es un bug: Safari nunca implementó la Web
MIDI API sobre la que está construida la función, así que no hay MIDI
disponible en el navegador para detectar. Usá un navegador basado en
Chromium (Chrome, Edge), o mapeá el controlador directamente en REAPER en
vez de por ReaSet.
