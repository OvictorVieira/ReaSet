# ReaSet Changelog

---

# English

---

## v3.0 — Armed transport, and a new licence
*August 11, 2026*

### Licence

- **ReaSet is now proprietary and free to use** — see [`LICENSE`](./LICENSE).
  You may use it for anything, including commercially, on as many machines as
  you like, and share unmodified copies. Selling it or distributing modified
  versions needs written permission.
- **This is not retroactive.** Versions up to v2.x were GPL v3 and stay GPL v3
  for anyone who has them, permanently.
- The change was possible because `Reaset.lua` never actually derived from the
  X-Raym scripts its header claimed to inherit from: a line-by-line comparison
  finds 18 identical lines out of 119, and every one of them is `end` or
  `break`. Zero shared functions. The header over-declared an obligation the
  code never contracted, and has been corrected. Full evidence in
  [`docs/RELICENSING.md`](./docs/RELICENSING.md).
- X-Raym's own scripts in `Legacy/` keep their GPL v3 and their authorship, now
  declared explicitly in [`Legacy/LICENSE-NOTICE.md`](./Legacy/LICENSE-NOTICE.md).
- New [`CONTRIBUTING.md`](./CONTRIBUTING.md) with a contributor licence
  agreement, so contributions can be used in ReaSet Pro.

### Transport — arm, don't detect

The end of a song used to be *detected* by the browser, which then *sent* a
stop. That path can never be punctual, and the reason is worth writing down:
~60 ms poll, plus a 72-107 ms round-trip, plus — the part that took longest to
find — **`Main_OnCommand` does not stop the transport on the spot. It stops it
on the next audio block.** A reposition landing in that gap runs while the
transport is still rolling, so it seeks *playback* into the next song.

- **Auto-stop is now armed in advance.** ReaSet tells REAPER where to stop
  before it matters, so REAPER stops in its own audio engine at the exact
  sample and no command travels at the critical moment. Measured on a real
  region transition: stops 10.7 ms before the boundary, never crossing it.
  **Fixes the next song being briefly audible at the end of the current one.**
- It lives next to the loop engine on purpose: the loop time range is one
  range and both features want it, so there is a single arbiter instead of two
  that fight. A song marked to loop does not auto-stop.
- If arming is not possible (no SWS, for instance) the browser's old detection
  stays as the fallback. Losing precision is acceptable; losing auto-stop is
  not.
- **MIDI Init redesigned.** It used to jump to the *start of the next song* and
  play ~100 ms there so plugins would receive transport — which made that
  song's opening audible every single time, whether or not the regions were
  contiguous. Now the transport simply starts 5 ms before the song you asked
  for. Five is enough because the MIDI is quantised to the grid; the old 100 ms
  was margin for a case that no longer exists.
- **Position extrapolation** (`getExtrapolatedPos`), and the end-of-region
  trigger now uses it instead of a position up to a poll interval stale.
- Repositioning after a stop waits for the transport to **confirm** it stopped,
  instead of guessing with a timer that was shorter than the measured
  round-trip.

### Fixed

- **Director→Player setlist sync silently dropped most edits.** It triggered on
  the chunk *count* changing, and toggling a skip flag moves the payload by
  three characters — so the count stayed identical, the shared file was never
  rewritten, and Players kept showing the old setlist with no sign anything had
  failed. Only edits that happened to cross a chunk boundary got through, which
  is why it looked like it worked. Now gated on a monotonic revision.
- **The web-interface directory was hardcoded** to `<resource>/Plugins/reaper_www_root`.
  On installs where that is not the right path, `io.open` fails silently: the
  file is never written, the browser gets a 404, and nobody returns an error.
  It is now resolved by looking for where `ReaSet.html` itself lives.

---

## v2.2 — Live Lyrics Carousel, Reaset.lua Unification & Director/Player Mode
*July 28, 2026*

### Installation & reliability
- **`Reaset.lua`: one script instead of three.** Merges the native-loop engine, the lyrics bridge and the chords bridge into a single persistent background script. Lyrics/chords tracks are now optional — no error box if absent — and `ULT_GetMediaItemNote` is called defensively so a missing SWS install no longer breaks transport/loop control. No Action ID setup needed; the web UI auto-detects it. The original three scripts remain under `Requirements/` as a legacy/advanced path.
- **Wi-Fi drop / reconnect phantom-seek fix.** ReaSet issues absolute `SET/POS` commands based on its last polled position. If the poll stream cuts out (a tablet losing Wi-Fi) while REAPER keeps playing, the first fresh reply on reconnect used to trigger a stale loop/boundary decision that seeked REAPER *backward* to the pre-outage position — indistinguishable from a phantom tap. ReaSet now detects the gap (plus browser online/offline events) and suppresses only its own *automatic* transport commands for a short guard window while silently adopting REAPER's real position; explicit user taps are never suppressed.
- **Decorated track names.** Lyrics/chords tracks no longer need to be named exactly `lyrics`/`chords` — prefixes, numbering and symbol decoration are stripped before matching (`*Lyrics`, `01 - Chords`, `[Lyrics]`, etc.), while names with an extra word (`Backing Lyrics`) are deliberately left alone.
- **Real per-bridge status.** Instead of one generic "make sure you have a track named lyrics" hint for four different causes, the empty-state message now reports the actual one: script not running, no track matched, SWS missing, or track found with no item under the cursor.
- **Fixed two real detection bugs.** A divider/folder track above the real one (e.g. `=== LYRICS ===`) could silently shadow it forever; the bridge now prefers a track that actually has items. Renaming a track used to have no effect until REAPER restarted; it now re-scans every ~2s when the latched track stops matching.
- **Dead-bridge detection.** A crashed (not just absent) script used to keep reporting stale, frozen values as if they were live — nothing distinguished a hung script from a working one. A live tick counter plus error capture now catches this and reports it before any stale data is shown.
- **`ReaSet_Diagnose.lua`**, a new read-only diagnostic script: lists every track with its normalised name and item count, which track each bridge would pick, SWS availability, cursor position, a per-item Notes dump, and a self-test that proves the lookup pipeline works independent of where the playhead happens to sit.

### Live Lyrics & Chords — Cover Flow carousel
- **Three-line verse context.** The lyrics panel now shows the previous and next verse above/below the current one, each independently sized via a new gear-icon settings popover (size, weight, colour, context on/off).
- **Chords get the same context**, laid out horizontally either side of the current chord.
- **A proper 3D carousel**, not a flat slide: verses and chords sit on a drum and turn into place — lyrics vertically, chords horizontally — always facing the viewer square-on (no distracting tilt on the context lines). Tuned down from an initial 380ms turn to a snappy 100ms with a hard landing.
- **Independent size controls**: Global, Principal (current line) and Secundario (context lines) can now be adjusted separately instead of one shared scale.
- **Song-boundary clamping.** Previous/next context lines no longer bleed across song boundaries — the "previous" line from the last song vanishes rather than lingering at the next song's start, and "next" at a song's end shows the upcoming song's name instead of the next lyrics item on the timeline, whatever song that happens to belong to.
- **Constant spacing on wrap.** A two-line current verse no longer crowds its neighbours — spacing now accounts for the verse's actual rendered height.
- **Quieter status messaging.** An empty panel (an instrumental passage, a gap between verses) no longer shows a large centred "no data" block that reads like an error; a faint status strip at the bottom reports it instead, brightening only when something genuinely needs fixing.

### New tool: `Lyrics_Tapper.lua`
- A companion authoring tool for building the lyrics/chords/notes items ReaSet reads: paste text, arm, tap along (mouse or Space) to place one item per line — teleprompter-style, in the spirit of Ableset's lyrics tool.
- Restyled with a dark, Ableset-inspired theme; the tapping/timing logic itself is untouched.
- Fixed three real runtime bugs surfaced by actually running it: two ReaImGui API mismatches (`CreateFont`/`PushFont` argument counts) and a color-packing bug (ARGB vs. the RGBA REAPER's ReaImGui actually expects) that was producing an unreadable pink/transparent UI.
- **One more tap now finishes the take.** Tapping through the last line used to require a separate "Stop & Save" click; the (N+1)th tap now closes the last item and finishes automatically.

### Director / Player mode
- **A mode picker on first load.** Every device choosing to open ReaSet picks **Director** (full control) or **Player/Músico** (read-only: live song, progress, lyrics, chords — nothing that reaches REAPER). The choice is remembered per device and doesn't re-ask on a refresh.
- **Enforced at the network layer**, not just the UI: every command ReaSet could send to REAPER passes through one function, and Player mode drops anything that isn't a plain read — a stray click or leftover keyboard shortcut cannot move REAPER's transport.
- **Shared setlist sync.** A Director's setlist (order, skip/loop/chain flags) auto-pushes to a small file `Reaset.lua` writes next to `ReaSet.html`; Players read it automatically, Directors pull manually with a confirmation. A pulled setlist that doesn't match the currently open REAPER project is rejected rather than silently applied.
- **Optional Director PIN.** A Director can set a PIN from the sidebar; from then on, actively choosing Director (not recalling an already-stored choice) asks for it first. Stored as a hash in REAPER's own persisted state — no server, survives a REAPER restart.
- **Two-Directors-at-once warning.** Each Director quietly re-announces itself every few seconds; a second device choosing Director while one is already active is warned before switching, and a banner appears if a second Director shows up later, mid-show.
- None of this is a real security boundary — REAPER's own Web Interface has no authentication — and the README says so explicitly.

### Also
- **Smooth Seek preference**, per project: toggle whether manual song/section/MIDI navigation lets REAPER apply its own smooth-seek behaviour while playing, or always forces an immediate hard jump.

---

# Español

---

## v3.0 — Transporte armado, y licencia nueva
*11 de agosto de 2026*

### Licencia

- **ReaSet pasa a ser propietario y de uso gratuito** — ver [`LICENSE`](./LICENSE).
  Podés usarlo para lo que quieras, incluso comercialmente, en las máquinas que
  quieras, y compartir copias sin modificar. Venderlo o distribuir versiones
  modificadas requiere permiso escrito.
- **No es retroactivo.** Las versiones hasta la v2.x fueron GPL v3 y lo siguen
  siendo para quien las tenga, para siempre.
- El cambio fue posible porque `Reaset.lua` nunca derivó realmente de los
  scripts de X-Raym que su cabecera decía heredar: la comparación línea a línea
  da 18 líneas idénticas sobre 119, y todas son `end` o `break`. Cero funciones
  compartidas. La cabecera declaraba una obligación que el código no contrajo, y
  se corrigió. La evidencia completa está en
  [`docs/RELICENSING.md`](./docs/RELICENSING.md).
- Los scripts de X-Raym en `Legacy/` conservan su GPL v3 y su autoría, ahora
  declaradas explícitamente en [`Legacy/LICENSE-NOTICE.md`](./Legacy/LICENSE-NOTICE.md).
- Nuevo [`CONTRIBUTING.md`](./CONTRIBUTING.md) con acuerdo de contribución, para
  que las contribuciones puedan usarse en ReaSet Pro.

### Transporte — armar, no detectar

El fin de una canción lo *detectaba* el navegador, que entonces *mandaba* un
stop. Ese camino no puede ser puntual, y la razón vale escribirla: poll de
~60 ms, más 72-107 ms de ida y vuelta, más —lo que más costó encontrar—
**`Main_OnCommand` no detiene el transporte en el acto: lo detiene en el próximo
bloque de audio.** Una reposición que caiga en ese hueco se ejecuta con el
transporte todavía rodando, así que hace un seek *de reproducción* a la canción
siguiente.

- **El auto-stop ahora se arma por adelantado.** ReaSet le dice a REAPER dónde
  parar antes de que importe, así que para en su propio motor de audio, en el
  sample exacto, y en el instante crítico no viaja ningún comando. Medido sobre
  una transición de región real: para 10,7 ms antes del borde, sin cruzarlo
  nunca. **Arregla que se escuchara un instante de la canción siguiente al
  terminar la actual.**
- Vive junto al motor de loop a propósito: el rango de loop es uno solo y las
  dos features lo quieren, así que hay un único árbitro en vez de dos que se
  pisen. Una canción marcada para loopear no auto-para.
- Si armar no es posible (sin SWS, por ejemplo), la detección vieja del
  navegador queda como respaldo. Perder precisión es aceptable; perder el
  auto-stop no.
- **MIDI Init rediseñado.** Antes saltaba al *inicio de la canción siguiente* y
  reproducía ~100 ms ahí para que los plugins recibieran transporte — lo que
  hacía sonar el arranque de ese tema todas las veces, fueran o no contiguas las
  regiones. Ahora el transporte simplemente arranca 5 ms antes de la canción que
  pediste. Cinco alcanzan porque el MIDI está cuantizado a la grilla; los 100 ms
  viejos eran margen para un caso que ya no existe.
- **Extrapolación de posición** (`getExtrapolatedPos`), y el disparo de fin de
  región ahora la usa en vez de una posición hasta un intervalo de poll vieja.
- La reposición tras un stop espera a que el transporte **confirme** que paró,
  en vez de adivinar con un temporizador más corto que la ida y vuelta medida.

### Arreglado

- **El sync de setlist Director→Player descartaba en silencio casi toda
  edición.** Se disparaba con el cambio del *conteo* de chunks, y togglear un
  skip mueve el payload tres caracteres — así que el conteo quedaba igual, el
  archivo compartido nunca se reescribía, y los Players seguían mostrando el
  setlist viejo sin ninguna señal de falla. Solo pasaban las ediciones que
  casualmente cruzaban un límite de chunk, que es por qué parecía funcionar.
  Ahora se dispara con una revisión monotónica.
- **El directorio del web interface estaba hardcodeado** a
  `<resource>/Plugins/reaper_www_root`. En instalaciones donde esa no es la ruta
  correcta, `io.open` falla en silencio: el archivo nunca se escribe, el
  navegador recibe 404, y nadie devuelve un error. Ahora se resuelve buscando
  dónde vive el propio `ReaSet.html`.

---


## v2.2 — Carrusel de letras en vivo, unificación de Reaset.lua y modo Director/Player
*28 de julio de 2026*

### Instalación y fiabilidad
- **`Reaset.lua`: un script en vez de tres.** Combina el motor de loop nativo, el puente de letras y el puente de acordes en un único script de fondo persistente. Los tracks de letras/acordes ahora son opcionales — sin cuadro de error si no existen — y `ULT_GetMediaItemNote` se llama defensivamente para que la falta de SWS ya no rompa el control de transporte/loop. No requiere configurar un Action ID; la web lo detecta sola. Los tres scripts originales siguen disponibles en `Requirements/` como ruta legacy/avanzada.
- **Corrección del salto fantasma al reconectar Wi-Fi.** ReaSet emite comandos `SET/POS` absolutos basados en la última posición sondeada. Si el flujo de sondeo se corta (una tablet que pierde Wi-Fi) mientras REAPER sigue reproduciendo, la primera respuesta fresca al reconectar solía disparar una decisión de loop/límite obsoleta que saltaba REAPER *hacia atrás* a la posición previa al corte — indistinguible de un tap fantasma. Ahora ReaSet detecta el corte (además de los eventos online/offline del navegador) y suprime solo sus propios comandos de transporte *automáticos* durante una ventana breve, adoptando en silencio la posición real de REAPER; los taps explícitos del usuario nunca se suprimen.
- **Nombres de track decorados.** Los tracks de letras/acordes ya no necesitan llamarse exactamente `lyrics`/`chords` — prefijos, numeración y símbolos decorativos se eliminan antes de comparar (`*Lyrics`, `01 - Chords`, `[Lyrics]`, etc.), mientras que nombres con una palabra extra (`Backing Lyrics`) se dejan intencionalmente sin marcar.
- **Estado real por puente.** En vez de un único aviso genérico "asegurate de tener un track llamado lyrics" para cuatro causas distintas, el mensaje de estado vacío ahora informa la causa real: script no corriendo, ningún track coincide, falta SWS, o track encontrado sin ítem bajo el cursor.
- **Dos bugs de detección reales corregidos.** Un track divisor/carpeta por encima del real (ej. `=== LYRICS ===`) podía taparlo para siempre en silencio; el puente ahora prefiere un track que realmente tenga ítems. Renombrar un track no tenía efecto hasta reiniciar REAPER; ahora se re-escanea cada ~2s cuando el track enganchado deja de coincidir.
- **Detección de puente muerto.** Un script crasheado (no solo ausente) seguía reportando valores obsoletos y congelados como si estuvieran en vivo — nada distinguía un script colgado de uno funcionando. Un contador de tick en vivo más captura de errores detecta esto ahora y lo reporta antes de mostrar cualquier dato obsoleto.
- **`ReaSet_Diagnose.lua`**, un nuevo script de diagnóstico de solo lectura: lista cada track con su nombre normalizado y cantidad de ítems, qué track elegiría cada puente, disponibilidad de SWS, posición del cursor, un volcado de Notes por ítem, y un self-test que prueba que el pipeline de búsqueda funciona sin importar dónde esté el cursor.

### Letras y acordes en vivo — carrusel Cover Flow
- **Contexto de tres líneas.** El panel de letras ahora muestra la estrofa anterior y la siguiente arriba/abajo de la actual, cada una ajustable independientemente desde un nuevo popover de configuración (ícono de engranaje): tamaño, peso, color, contexto on/off.
- **Los acordes reciben el mismo contexto**, distribuidos horizontalmente a los lados del acorde actual.
- **Un carrusel 3D real, no un slide plano**: las estrofas y acordes viven en un tambor y giran hasta su lugar — letras verticalmente, acordes horizontalmente — siempre de frente al espectador, sin inclinación que distraiga en las líneas de contexto. Afinado desde un giro inicial de 380ms hasta uno rápido de 100ms con aterrizaje firme.
- **Controles de tamaño independientes**: Global, Principal (línea actual) y Secundario (líneas de contexto) ahora se ajustan por separado en vez de una escala compartida.
- **Límite de canción respetado.** Las líneas de contexto previa/siguiente ya no se filtran entre canciones — la línea "previa" de la canción anterior desaparece en vez de seguir apareciendo al inicio de la siguiente, y "siguiente" al final de una canción muestra el nombre de la próxima canción en vez del siguiente ítem de letra en la línea de tiempo, sin importar a qué canción pertenezca.
- **Espaciado constante al hacer wrap.** Una estrofa actual de dos líneas ya no se amontona con sus vecinas — el espaciado ahora considera la altura real renderizada de la estrofa.
- **Mensajes de estado más discretos.** Un panel vacío (un pasaje instrumental, un hueco entre estrofas) ya no muestra un bloque grande centrado de "sin datos" que parece un error; una franja de estado tenue al pie lo informa en su lugar, aclarándose solo cuando algo realmente necesita corrección.

### Nueva herramienta: `Lyrics_Tapper.lua`
- Herramienta complementaria de autoría para construir los ítems de letras/acordes/notas que ReaSet lee: pegá el texto, armá, tapeá al ritmo (mouse o Space) para colocar un ítem por línea — estilo teleprompter, en la línea de la herramienta de letras de Ableset.
- Reestilizada con un tema oscuro inspirado en Ableset; la lógica de tapeo/timing en sí no se tocó.
- Corregidos tres bugs reales de runtime detectados al correrla de verdad: dos incompatibilidades de la API de ReaImGui (cantidad de argumentos de `CreateFont`/`PushFont`) y un bug de empaquetado de color (ARGB en vez del RGBA que realmente espera el ReaImGui de REAPER) que producía una interfaz rosa/transparente ilegible.
- **Un tap más ahora termina la toma.** Tapear la última línea antes requería un click aparte en "Stop & Save"; el tap N+1 ahora cierra el último ítem y termina automáticamente.

### Modo Director / Player
- **Selector de modo al cargar por primera vez.** Todo dispositivo que abre ReaSet elige **Director** (control total) o **Player/Músico** (solo lectura: canción en vivo, progreso, letras, acordes — nada que llegue a REAPER). La elección se recuerda por dispositivo y no vuelve a preguntar en cada refresco.
- **Aplicado a nivel de red**, no solo en la interfaz: todo comando que ReaSet pudiera mandarle a REAPER pasa por una sola función, y el modo Player descarta cualquier cosa que no sea una lectura simple — un click perdido o un atajo de teclado que quedó activo no puede mover el transporte de REAPER.
- **Sincronización de setlist compartido.** El setlist del Director (orden, banderas de skip/loop/chain) se empuja automáticamente a un archivo chico que `Reaset.lua` escribe junto a `ReaSet.html`; los Players lo leen automáticamente, los Directores lo traen manualmente con confirmación previa. Un setlist compartido que no coincide con el proyecto de REAPER actualmente abierto se rechaza en vez de aplicarse en silencio.
- **PIN de Director opcional.** Un Director puede fijar un PIN desde el sidebar; a partir de ahí, elegir Director activamente (no recordar una elección ya guardada) lo pide primero. Se guarda como hash en el estado persistido del propio REAPER — sin servidor, sobrevive un reinicio de REAPER.
- **Aviso de dos Directores a la vez.** Cada Director se reanuncia discretamente cada pocos segundos; un segundo dispositivo que elige Director mientras uno ya está activo recibe un aviso antes de cambiar, y aparece un banner si un segundo Director surge más tarde, en medio de un show.
- Nada de esto es una barrera de seguridad real — el propio Web Interface de REAPER no tiene autenticación — y el README lo dice explícitamente.

### También
- **Preferencia de Smooth Seek**, por proyecto: alterna si la navegación manual de canción/sección/MIDI deja que REAPER aplique su propio comportamiento de seek suave mientras reproduce, o siempre fuerza un salto duro inmediato.
