<p align="center"><a href="../README.md">← ReaSet overview</a> · <a href="USER_GUIDE.es.md">Español</a></p>

# ReaSet User Guide

> Complete reference for installation, setup and live operation. For the fastest path, start with the [README quick start](../README.md#quick-start).

---

## 📌 Table of Contents
- [💛 Support this project](#-support-this-project)
- [1) What is ReaSet?](#1-what-is-reaset)
- [2) Main features](#2-main-features)
- [3) Credits and acknowledgements](#3-credits-and-acknowledgements)
- [4) Requirements](#4-requirements)
- [5) Tools](#5-tools)
- [6) Installation](#6-installation)
- [7) Usage setup](#7-usage-setup)
- [8) Usage Manual](#8-interactive-usage-manual)
  - [Lyrics & Chords Track Naming](#lyrics--chords-track-naming)
  - [Display Filters](#display-filters)
  - [MIDI Learn](#-midi-learn)
  - [Region Name Command Reference](#region-name-command-reference)
- [9) Keyboard Shortcuts](#9-keyboard-shortcuts)
- [10) Quick troubleshooting](#10-quick-troubleshooting)

---

## 💛 Support this project
If this project helps you, you can support development here:

<a href="https://ko-fi.com/W7W81VLW05" target="_blank">
  <img src="https://storage.ko-fi.com/cdn/kofi3.png?v=6" alt="Buy Me a Coffee at ko-fi.com" height="36" style="border:0px;height:36px;" />
</a>

📜 [Changelog](../CHANGELOG.md) · 🗺️ [Roadmap](../ROADMAP.md)

---

## 1) What is ReaSet?
**ReaSet** is a web interface for **REAPER**, designed for live setlist management.

Project foundation:
- Inspired by **ReaSetlistManager** by `suckyble`.
- Extended with **lyrics and chords** display based on **X-Raym** scripts/logic.

Main goals:
- Organize and run songs (regions) during live shows.
- Control transport (play/stop/cue/next).
- Manage multiple setlists, stored with the REAPER project itself.
- Display synced lyrics/chords from dedicated tracks.

---

## 2) Main features
- ✅ Setlist management (create/delete/switch).
- 🔀 Drag & drop song reordering.
- 🎯 Song states: active, queued, skipped, loop, chain.
- ⏯️ On-screen transport controls.
- 💾 JSON export/import.
- 🗄️ Setlists stored in `<project folder>/reaset/setlists/`, one file each — they travel with the `.rpp`. Other preferences stay in `localStorage`, isolated per project.
- 🎤 Lyrics panel + 🎸 chords panel.
- 🎨 Visual customization (themes/fonts/sizes/chord color/display filters).
- 🗂️ Nested sub-regions with individual loop, skip, color and notes overrides.
- 🏷️ Inline command system — control behavior directly from REAPER region names.
- 🔢 Fractional loop counter badge (e.g. `2/4`) shown live on the active section.
- 🖥️ Live View with sub-region progress bar, next section indicator and loop counter.
- 🌗 Real-time display filters: brightness, contrast and saturation via sidebar sliders.
- 🎬🎧 Director/Player mode — read-only instances for musicians that can never send REAPER
  a command, with a shared setlist synced from the Director.

Main file:
- `ReaSet.html`

Included dependencies:
- `Sortable.min.js`
- Legacy Lua bridge scripts under `Legacy/` (optional/advanced — see [Requirements](#4-requirements))

---

## 3) Credits and acknowledgements
### Base project
- **suckyble / ReaSetlistManager**  
- https://github.com/suckyble/ReaSetlistManager

### Lyrics/chords integration
- **X-Raym / REAPER-ReaScripts**  
- https://github.com/X-Raym/REAPER-ReaScripts/tree/master/Web%20Interfaces
- Reference script:  
  `Convert Lyrics track items notes for the dedicated web browser interface.lua`

### Sorting library
- **SortableJS** (`Sortable.min.js`)

### AI-assisted development process
This project was iterated, debugged, and tested with:
- **Claude (cowork)**
- **Google (Antigravity)**

Final functional validation was performed in REAPER with real setlist usage tests.

> ⚖️ Legal note: ReaSet v3.0+ is proprietary and free to use — see [`LICENSE`](../LICENSE).
> Versions up to v2.x were GPL v3 and remain so. Third-party scripts kept in
> `Legacy/` have their own licences: see [`Legacy/LICENSE-NOTICE.md`](../Legacy/LICENSE-NOTICE.md).

---

## 4) Requirements
### Software
1. **REAPER** (v5+ recommended; latest preferred).
2. A web browser (desktop/tablet/mobile).
3. A REAPER project with regions (typically one region per song).

### Minimum files
- `ReaSet.html`
- `Sortable.min.js`
- `Reaset.lua` — **single unified companion script** (loop engine + lyrics + chords).

> **Legacy / advanced:** the three original scripts are still bundled under
> `Legacy/` (`ReaSet_NativeLoop.lua` and the two X-Raym Lyrics/Chords
> converters). You only need them if you prefer running the subsystems
> separately. For a normal setup, `Reaset.lua` replaces all three.
> Note that the legacy scripts require the **exact** track names `lyrics` / `chords` —
> prefix support (`*Lyrics`) exists only in `Reaset.lua`.

### Required tracks for lyrics/chords
- A track whose name is `lyrics` — feeds the 🎤 Lyrics panel.
- A track whose name is `chords` — feeds the 🎸 Chords panel.
- Each item must contain text in **Item Notes**.

Name matching is **case-insensitive** and tolerates prefixes/suffixes such as
`*Lyrics`, `#Chords` or `01 Lyrics`. Both tracks are **optional**.
See [Lyrics & Chords Track Naming](#lyrics--chords-track-naming) for the full rules.

### Script compatibility
Scripts use `reaper.ULT_GetMediaItemNote`.
- If your REAPER build does not recognize it, install a compatible scripting/API environment (e.g., Ultraschall API) or adapt note reading.

---

## 5) Tools
Optional standalone scripts under `Tools/`. Neither is required to run ReaSet
itself — the always-on setup is just `Reaset.lua` + `ReaSet.html` — these are
conveniences you reach for occasionally: one for authoring content, one for
diagnosing the lyrics/chords bridge when a panel stays empty.

### 🎤 Lyrics Tapper — `Tools/Lyrics_Tapper.lua`
A standalone REAPER/ReaImGui tool for **building** the `lyrics`/`chords`/`notes`
items ReaSet reads. Paste a block of text, press **ARM**, then tap along
(mouse or **Space**) as the song plays: each tap closes the previous line's
item and opens the next one at the current position, teleprompter-style.
For N lines, that's N taps to place all of them, plus **one more tap** to close
the last item and finish the take right there — no separate Stop needed for a
clean finish, though Stop is still available any time to end early.
It auto-detects the target track with the same flexible naming rules as
`Reaset.lua`, creates the track if missing, and filters out section headers
("Chorus", "Verse 2", "[Coro]", …) so they don't become lyric items.

- Requires the **ReaImGui** extension (separate from SWS).
- Load via Actions → ReaScript: Load… → `Tools/Lyrics_Tapper.lua` → Run.

### 🔍 ReaSet Diagnose — `Tools/ReaSet_Diagnose.lua`
A read-only, one-shot diagnostic report for the lyrics/chords bridge — reach
for it when the [in-app status message](#10-quick-troubleshooting) isn't
enough on its own. It prints every track with its normalised name and item
count, which track each bridge would pick, whether SWS is present, the cursor
position, and a per-item dump of the Notes field, pinpointing shadowed tracks
(two tracks matching the same keyword) and empty Notes immediately. It also
self-tests the lookup pipeline at a known-good position, so a badly
positioned playhead can never look like a broken bridge.

- Load via Actions → ReaScript: Load… → `Tools/ReaSet_Diagnose.lua` → Run.

### 🗄️ Library Doctor — `Tools/ReaSet_LibraryDoctor.lua`
The same idea for the setlist library. Also read-only. It prints the project's
`/reaset/setlists` folder with every setlist file and its song count, which
`reaper_www_root` actually holds `ReaSet.html` (and whether it is writable),
whether the index the browser fetches exists, and what `Reaset.lua` last
published. Between them you can see exactly which link broke in the chain
browser → `Reaset.lua` → disk — instead of a setlist that just quietly does not
save.

- Load via Actions → ReaScript: Load… → `Tools/ReaSet_LibraryDoctor.lua` → Run.

---

## 6) Installation

### Recommended — Install with ReaBoot

[**Install ReaSet with ReaBoot**](https://www.reaboot.com/install/https%3A%2F%2Fraw.githubusercontent.com%2Fdjenttleman%2FReaSet%2Fmain%2Freaboot.json)

ReaBoot installs ReaPack (if needed), registers `Reaset.lua` in REAPER's Main
Action List and puts the web files in `reaper_www_root`. The installer also
offers the optional ReaSet tools, ReaImGui and the recommended SWS extension.

After installation, open **Actions > Show action list**, find **Reaset** and run
it. ReaBoot deliberately does not change user preferences, so enabling it as a
REAPER Startup Action remains a manual, recommended step.

### Manual installation

#### Step 1 — Copy web interface files
Copy to REAPER web folder (where `main.js` is located):
- `ReaSet.html`
- `Sortable.min.js`

#### Default paths (REAPER Resource Path)
> In REAPER: **Options > Show REAPER resource path in explorer/finder**.

**macOS**
- Resource Path: `~/Library/Application Support/REAPER/`
- Web root: `~/Library/Application Support/REAPER/reaper_www_root/`

**Windows**
- Resource Path: `%APPDATA%\REAPER\`
- Web root: `%APPDATA%\REAPER\reaper_www_root\`

**Linux**
- Resource Path: `~/.config/REAPER/`
- Web root: `~/.config/REAPER/reaper_www_root/`

> `main.js` is provided by REAPER Web Interface (not included in this project).

#### Step 2 — Install the Lua script (one script only)
1. Open REAPER.
2. Go to **Actions > Show action list**.
3. Use **ReaScript: Load...** and load **`Reaset.lua`**.
4. Find **"Reaset"** in the action list and **Run** it once.
5. (Recommended) Add it to **Options > Preferences > General > Startup actions**
   (or an SWS *Global startup action*) so it launches with REAPER automatically.

> `Reaset.lua` is a single persistent background script that runs the native
> loop engine and the lyrics/chords bridges together. There is **no Action ID
> to paste** into `ReaSet.html` — the web interface auto-detects the script.
>
> Lyrics/chords tracks are optional: if a `lyrics` or `chords` track is missing,
> that panel simply stays idle and transport/loop control keeps working.

#### Default script paths
- **macOS:** `~/Library/Application Support/REAPER/Scripts/`
- **Windows:** `%APPDATA%\REAPER\Scripts\`
- **Linux:** `~/.config/REAPER/Scripts/`

#### Step 3 — Prepare project
1. Create/rename track `lyrics`.
2. Create/rename track `chords`.
3. Add lyrics/chords into item notes.
4. Verify song regions in timeline.

#### Step 4 — Launch interface
1. Open REAPER + project.
2. Open web interface and load `ReaSet.html`.
3. Run `Reaset.lua`.

---

## 7) Usage setup
### Recommended live workflow
1. Verify regions.
2. Run Lyrics/Chords scripts.
3. Open `ReaSet.html`.
4. Create/select setlist.
5. Reorder songs and set states (skip/loop/chain).
6. Test transport before showtime.
7. Export `.json` backup.

### Persistence and backups
- **Setlists live with the project**, in `<project folder>/reaset/setlists/`,
  one JSON file each, written by `Reaset.lua`. The disk is the source of truth:
  every device reading that project sees the same setlists, with no merge step.
  Open ReaSet on a second machine or a tablet and your show is simply there.
- This requires the project to have been **saved at least once** — an unsaved
  project has no folder to write to, and ReaSet says so in the setlist dropdown
  rather than pretending to save.
- Setlists you already had in a browser migrate themselves on first open.
- Other state (themes, sizes, panel preferences) is still browser-local
  (`localStorage`).
- Use Export/Import JSON for backup/migration.
- Recommended: dated backups before major edits.

### Best practices
- Keep consistent region naming.
- Keep a dedicated “Show-Ready” project.
- Test on the same device/browser used on stage.

---

## 8) Usage Manual
### Top Bar & Visualization
- **Grid View**: Toggles between a detailed hierarchical list or large card blocks for touch-friendly usage.
- **Hide Skipped**: Visually removes currently "skipped" songs from the view (great for decluttering during a show).
- **Auto-Scroll**: Automatically locks and scrolls the viewport to the currently playing active region/song.
- **Edit Sets**: Opens the administrative management panel for creating, renaming, cloning, or deleting Setlists.

### Display Modes & Canvas
- **Live View**: Triggers a performance-focused layout showing a gigantic track name, progress bar, time remaining, the next queued song, and localized transport controls.
- **Lyrics & Chords (Floating Widgets)**: You can overlay floating widgets dynamically synced to the `Lyrics` and `Chords` text tracks on REAPER. They contain a contextual toolbar to adjust font sizes, typeface, and colors mapping locally on your screen.

#### Lyrics panel — three-line view
The lyrics panel shows the **previous verse above** and the **next verse below** the
current one, both smaller and dimmed so the active line stays dominant. Missing
neighbours (start of a song, or a gap between items) keep their space reserved, so the
current line never jumps around while you are reading it.

Context lines are **clamped to the song currently playing**: a verse from the previous
or next song never bleeds into this one's context lines. At the start of a song the
"previous" slot stays blank rather than showing the last line of whatever played before
it; at the end of a song the "next" slot shows **"Siguiente: <song name>"** instead of
the next song's first lyric — a heads-up, not a spoiler. This needs `Reaset.lua` to
publish each neighbour's position (added alongside its text); an older `Reaset.lua`
simply doesn't clamp, matching the behaviour before this feature existed.

A discreet **⚙ gear** in the panel header opens a small popover to adjust:

| Setting | Options |
|---|---|
| **Tamaño global** | 16–120 px slider — the base size everything else scales from |
| **Línea principal** | 50–150% of the global size, current line only |
| **Letras secundarias** | 10–100% of the global size, previous/next lines only |
| **Grosor** | Fino · Medio · Negrita · Black |
| **Color** | 5 presets + a custom colour picker |
| **Context lines** | Toggle the previous/next verses off entirely |

**Tamaño global**, **Línea principal** and **Letras secundarias** are three independent
sliders: the global size sets the overall scale everything is measured against, while
principal/secundario each control their own line(s) as a percentage of it — e.g. you can
shrink the context lines down to 10% for a near-invisible hint, or bring them up to 100%
to match the current line exactly, without moving the current line's own size at all.
Defaults (100% / 44%) reproduce the original look.

All six persist in `localStorage`, so your reading setup survives a reload.

#### Chords panel — three-across view
The chords panel uses the same neighbour logic, laid out **horizontally**: the previous
chord sits to the **left** and the next chord to the **right** of the current one, both
smaller and dimmed. Equal space is reserved on both sides, so the current chord stays
optically centred no matter how long the neighbouring chord names are.

> **One item = no neighbours.** The sides read the *previous* and *next* **items** on the
> `chords` track. If a single item spans the whole song, there are no neighbours to show
> and the sides stay blank — that is correct, not a fault. Split the chords into one item
> per change to get the left/right context.

#### Transitions and the status strip
Verses live on a **vertical 3D carousel**, like iOS Cover Flow turned 90°. The three lines
are positions on a drum: they follow its **curved path** and **recede into the distance**,
but are **never tilted** — the text always stays square to the viewer so it reads at a
glance.

Advancing a verse turns the drum by **exactly one position**:

| Line | Travel |
|---|---|
| Current | Slot `0` → `-1`: arcs up and back, shrinking |
| Previous | `-1` → `-2`: continues past the top edge and is gone |
| Next | `+1` → `0`: arcs up to neutral depth, growing |
| New verse | `+2` → `+1`: arcs into view from below |

**Wrap-aware spacing.** Slot positions are computed assuming a single-line current
verse; a verse that wraps onto two lines would otherwise crowd — or nearly touch —
the smaller context lines above and below it, since their fixed offset doesn't grow
with it. ReaSet measures the current line's actual rendered height on every change
and pushes prev/next further away by half a line's height for each extra wrapped
line, so the clearance stays constant whether the current verse is one line or several.

Expressing it as "every line moves one slot" is what makes it read as **a single rotation**
rather than four separate animations. The drum radius is in `em`, so the carousel scales
with the font size you pick in the gear popover.

Chords use **the same drum laid on its side**: previous chord to the left, next to the
right, following the same curve and receding the same way, likewise never tilted. Changing
chord turns the drum by one position exactly as the lyrics one does.

The turn is **deliberately quick — 100 ms**, covering 90% of the distance in the first
~40 ms and then decelerating hard into place. On stage you should register that the line
changed without having to watch it move: sustained motion in the reading area is tiring,
so the animation is there to keep you oriented, not to be looked at.

Only a genuine one-step move earns the turn. A seek, a song change or an edit is not a step
around the drum, so those **crossfade** instead — turning would imply a continuity that did
not happen. `prefers-reduced-motion` is honoured: if your system asks for less motion,
nothing animates at all.

Diagnostics never occupy the reading area — they live in a very faint strip at the bottom
of the panel, with two visibility levels:

| Situation | Visibility |
|---|---|
| Working, but no lyric/chord at this point | Barely visible (16%) — a **normal** state, not a fault |
| Something needs fixing (script stopped, frozen, no track, no SWS) | Readable (55%), still unobtrusive |

While content is on screen the strip stays empty. An instrumental gap still shows the
previous and next verse, which is exactly what is useful at that moment.

### Lyrics & Chords Track Naming
ReaSet reads lyrics and chords from **two dedicated REAPER tracks**, identified by their
name. `Reaset.lua` scans the project and looks for these two keywords:

| Panel | Track keyword |
|---|---|
| 🎤 Lyrics | `lyrics` |
| 🎸 Chords | `chords` |

**The rule:** matching is case-insensitive, and any *symbol* decoration or *numbering*
around the keyword is ignored. Strip the leading symbols/numbers and the trailing
symbols — whatever remains must be **exactly** the word `lyrics` or `chords`.

| Track name | Detected | Why |
|---|---|---|
| `lyrics` · `Lyrics` · `LYRICS` | ✅ | case is ignored |
| `*Lyrics` · `**Chords**` | ✅ | asterisk decoration stripped |
| `#Chords` · `-- Lyrics` · `[Chords]` · `>Lyrics` | ✅ | any leading/trailing symbols stripped |
| `01 Lyrics` · `3 - Chords` | ✅ | leading numbering stripped |
| `* 01 - Lyrics` | ✅ | mixed prefixes unwind in any order |
| `Backing Lyrics` · `Lyrics Bus` · `Chords Gtr` | ❌ | an extra **word** remains |

Extra words never match — that is deliberate, so ordinary audio tracks that happen to
contain the word "lyrics"/"chords" are left alone. If two tracks match the same keyword,
the **topmost** one in the track list wins.

The text itself lives in **Item Notes** (double-click an item → *Notes*), one item per
lyric/chord block; the item's position on the timeline is what syncs it to playback.

Both tracks are **optional**: if `lyrics` or `chords` is missing, that panel simply stays
idle and everything else (transport, loops, setlist) keeps working.

### Track List Interaction
- Tracks containing sub-sections will display a dropdown button (Chevron). Expanding it allows individual targeting of nested sub-regions (e.g. Intro, Chorus, Outro).
- The progress bar backing each track will dynamically map to the closest UI-color assigned to its native REAPER Region.
- **PLAY NEXT**: Actively loads the specified song under the REAPER playhead cue and stops playback, eagerly awaiting you to hit Play.

### Action Commands
- **&#9632; / &#8677; (Follow Action)**: Toggles whether playback stops at the end of the song or flows seamlessly into the next un-skipped track.
- **&#8635; (Loop)**: Activates infinite looping over the bounded region or currently selected sub-section segment.
- **&#10005; (Skip)**: Strikethroughs the track, completely ignoring it from linear continuous playback chains.

### Phone layout — view tabs move to the sidebar
On a phone, the five view tabs (SHOW / LYRICS / CHORDS / LIVE / CANVAS) move out of the top
bar and into a **Views** grid at the top of the sidebar. This isn't only about saving space:
five tabs at their minimum width plus the menu button plus the timer readout add up to
438px of content in a 375px-wide screen, so the timer and song count were being pushed
**63px off the right edge** — invisible on a phone. With the tabs relocated everything fits,
and the bar itself slims from 56px to 46px since it no longer has to house stacked
icon-over-label tabs.

The swap is driven purely by screen size, not by Director/Player mode — a Director on a
phone has the same screen. **Tablets and desktops keep the tabs on top**, unchanged. The
rule covers phones in portrait *and* landscape (`max-width: 600px` or `max-height: 520px`);
an iPad is at least 744px in both directions either way round, so it never matches. An iPad
in a narrow Split View pane does get the phone layout, which is correct — the pane really is
phone-sized.

Both sets of tabs always exist in the DOM and stay in sync, so rotating a phone or resizing
a window switches between the two layouts instantly with no stale highlight.

### Appearance modal
Everything that changes how ReaSet *looks* lives in one modal, opened from the sidebar's
**Appearance** button, split into three tabs:

| Tab | Contains |
|---|---|
| **General** | Display filters (luminance / contrast / saturation), layout, theme, language and full screen |
| **Lyrics** | Typeface, global size, main-line and context-line sizes, weight, colour, and the prev/next context toggle |
| **Chords** | Typeface, size and colour |

These used to be seven separate sidebar sections — 742px of a 1626px sidebar on a phone, so
nearly half the drawer was styling knobs you set once and forget. The sidebar is down to
985px now and reads as what it is: navigation and show controls.

Each tab uses the same control kit, full width and aligned: typefaces are dropdowns rather
than a wrapping grid of buttons, every slider shares one look, and the size presets are no
longer a separate row of pills — they're **marks on the slider's own scale**, so you can see
where S/M/L/XL sit before you drag, and they stay clickable. The mark matching the current
size lights up; a value between marks lights none.

The **gear popover inside the lyrics panel stays**, and it is not a second, competing copy:
both it and the modal drive the same functions, and those write through to every control on
screen. Change the size from the gear while reading lyrics and the modal's slider is already
moved when you open it, and vice versa. The gear is the quick, in-context adjustment while
you're looking at the words; the modal is the complete set (it also carries the typeface,
which the gear never had).

### Layout — song durations and full-screen views
Two display switches in **Appearance → General → Layout**, both remembered per device.

**Song durations** (on by default) hides the per-song time on the right of every setlist row
— and with it the section times under an expanded song and the times on the grid cards, since
they are the same information in three places. Off, the rows carry only what identifies the
song. Useful on a phone, where every pixel the name gets back is worth having.

**Full-screen views** (off by default) decides whether Lyrics, Chords and Canvas cover the
top bar. They used to, always. Now the bar stays put by default, which keeps the clock, the
show progress and the mode pill readable while you're reading words or chords — and on tablet
and desktop it keeps the **view tabs** reachable, so going from Lyrics to Chords no longer
needs a round trip through SHOW.

The switch is not the only way in: each of those three views carries a **⤢ button** next to
its close button (glyph only on a phone, worded on wider screens) that does the same thing
from inside the view. It is **one setting behind two controls**, not two settings — flip it
in the view and the modal's switch has already moved, and it survives a reload, so a choice
made at soundcheck is still there at showtime.

### Language — English / Spanish
ReaSet ships in both languages. The switch lives in **Appearance → General**, right under
Theme: a two-cell **EN / ES** control that applies immediately, with no reload.

On a device that has never chosen, ReaSet follows the browser's own language (Spanish if
`navigator.language` starts with `es`, English otherwise), so a Spanish-speaking musician
isn't greeted in English by a device that already stated its preference. Once you pick, the
choice is remembered per device.

Translation works by matching the strings themselves rather than by tagging every element
with a key: each entry in the table is simply `[english, spanish]` and **both sides act as a
lookup key**, so switching is symmetric and re-running it is harmless. Views that JS builds
as the show runs — the setlist, section rows, MIDI mappings — are re-rendered on a switch
and then swept, so nothing is left behind in the old language.

### Full screen — launching from the home screen
ReaSet can run without the browser's address bar and toolbar, which on a phone is the
difference between reading a song name and squinting at it. The control lives in
**Appearance → General → Full screen**, and it shows only the route that actually works on
the device looking at it.

**iPhone / iPad — Add to Home Screen.** Safari on iPhone has no element-fullscreen API at
all, so no button can help; the route is Share → **Add to Home Screen**, then open ReaSet
from the new icon. It launches standalone: no address bar, no bottom toolbar. As a bonus the
swipe-back gesture and pull-to-refresh are disabled, so a stray thumb mid-show can't navigate
away. The modal spells the three steps out on screen.

**Android / desktop — a button.** These browsers do expose the Fullscreen API, and crucially
it is *not* gated on a secure context: it works over the plain HTTP that REAPER serves. One
tap per session gives true full screen, hiding the system bars too. The button turns green
and switches to *Exit full screen* while it's active.

> **No HTTPS, no service worker, no manifest, no extra files.** A "real" PWA install would
> need all of those, and they need a secure context that REAPER's plain-HTTP LAN server can
> never provide (`navigator.serviceWorker` does not even exist there). The `apple-mobile-web-app-*`
> meta tags carry no such requirement, so ReaSet stays a **single file** you drop next to
> `main.js`. The icon is embedded in the page as a data URI rather than shipped as a separate
> image, for the same reason.

**What this does not give you** is offline launch. Without a service worker nothing is
cached, so if REAPER is off or unreachable the icon opens on an error page. And note that in
standalone mode there is no reload button and no address bar — the way out is to close the
app and reopen it.

### Display Filters
Located under **Settings — Appearance** in the sidebar. Three independent real-time sliders apply a CSS filter to the setlist body:
- **Luminance** — 50% to 150% (default 100%)
- **Contrast** — 50% to 150% (default 100%)
- **Saturation** — 0% to 200% (default 100%)

Values persist across sessions. A "Reset" button restores all three to default.

### 🎹 MIDI Learn
Located in the sidebar (**MIDI Learn** button). Maps notes/CC messages from a
connected MIDI controller to Play, Stop, Play/Pause, next/previous song,
next/previous section, toggle loop, restart song, and toggle skip. Click
**Escuchar siguiente nota / CC…**, send the message from your controller,
and the mapping is saved; multiple mappings can be active at once, and can
be cleared individually or all at once.

> ⛔ **Currently disabled in the app.** The whole MIDI module is commented out
> for now — see below for why — and will come back when ReaSet becomes an
> installable app with real MIDI access ([Roadmap](../ROADMAP.md)).

> ⚠️ **Not supported by Safari (macOS, iPadOS, iOS).** MIDI Learn
> is built on the **Web MIDI API** (`navigator.requestMIDIAccess`), which
> Safari has never implemented, on any Apple platform. The MIDI Learn panel
> will show no available devices there — this isn't a bug to report, it's a
> missing browser API. Use a Chromium-based browser (Chrome, Edge) instead,
> or route the controller through REAPER itself rather than the browser
> (REAPER's own MIDI mapping isn't affected by this at all). See the
> [Roadmap](../ROADMAP.md) for the longer-term plan here.

### Smooth Seek
**Smooth Seek** is enabled by default under **Show Options** and is saved separately for each REAPER project. When playback is already running, selecting a song or section manually — including MIDI **Next/Previous Section** and **Restart Song** — sends only the new position to REAPER. This lets REAPER honour its own *Do not change playback position immediately when seeking (smooth seek)* preference.

Turn Smooth Seek off when a controller needs an immediate, hard jump instead. Selecting a song while stopped still starts playback either way. Queue Mode, Cue, loops, and automatic transitions retain their existing behaviour.

### Region Name Command Reference
ReaSet parses special inline commands written directly in REAPER region and marker names. Multiple commands can be combined freely. The remaining text after parsing is the display name.

**Example:**
```
Chorus {pre-chorus} +LOOP:4 [green] [.bold] [1:20]
```

#### `+` Commands — Playback behavior

| Command | Description |
|---|---|
| `+PAUSE` | Pauses playback at the end of the section. |
| `+SKIP` | Marks the section as skipped by default. Appears struck through. |
| `+LOOP` | Enables infinite looping for the section. |
| `+LOOP:N` | Repeats the section exactly **N** times, then continues. Shows a live `X/N` badge. |
| `+LOOPFULL` | Loop with absolute priority — any queued region waits until the loop finishes. |

#### `[]` Square brackets — Appearance & duration

| Command | Description |
|---|---|
| `[colorname]` | Assigns a palette color to the card. |
| `[mm:ss]` | Overrides the displayed duration of the section. |
| `[nosong]` | Excludes the item from song count and numbering. Shown dimmed. |
| `[.classname]` | Applies a CSS style class to the name. |

Available colors: `gray` · `red` · `orange` · `amber` · `yellow` · `lime` · `green` · `emerald` · `teal` · `cyan` · `sky` · `blue` · `indigo` · `violet` · `purple` · `fuchsia` · `pink` · `rose`

Available classes: `.bold` · `.dim` · `.italic` · `.loud`

#### `{}` Curly braces — Informational text

| Command | Description |
|---|---|
| `{text}` | Displays auxiliary italic text next to the section name. Not shown in Live View or Canvas. |

#### Special prefixes — Markers only

| Command | Description |
|---|---|
| `>` | Converts the marker into a sub-section of the active song. |
| `*` | Ignores the marker entirely — it will not appear in the app. |
| `>>> TargetName` | Auto-jumps to the region whose name matches `TargetName` when this section ends. |

#### Reserved names

| Name | Description |
|---|---|
| `STOP` | Stop playback marker. |
| `SONG END` | Alias for `STOP`. |

---

### Director / Player Mode
Every ReaSet instance talks to REAPER directly through the same Web Interface — there is
no server of ReaSet's own, so control and display share one channel. That means two
devices open at once can genuinely fight over REAPER (both auto-advancing at a song's end,
for instance). Director/Player mode exists to make that impossible for a device that
isn't supposed to be controlling the show in the first place — a musician's tablet, say.

**On first load (or after clearing `localStorage`), ReaSet forces a choice:**

| Mode | What it can do |
|---|---|
| 🎬 **Director** | Everything ReaSet already does: transport, cue/queue, loops, skip/chain, MIDI, reordering. |
| 🎧 **Player (Músico)** | Read-only: live song/section/progress, lyrics, chords. Local display prefs (canvas, colours, fonts, filters) are still yours to change — none of that reaches REAPER. |

The choice is **remembered** (`localStorage`, not per-session) — a refresh, an app restart or
a device reboot does not re-ask. This is deliberate: recalling a stored mode grants no new
privilege (the device already chose Director once, on purpose), and re-forcing the picker on
every accidental refresh would just strand a Director mid-show behind a modal at the worst
possible moment. A small badge in the top-right corner always shows the current mode; click
it any time to switch (no confirmation needed going Director → Player, since that only
narrows what the device can do).

**How it's enforced:** every command this page could ever send to REAPER passes through one
function (`wwr_req`). In Player mode that function drops anything that isn't a plain read —
so even a stray click, a leftover keyboard shortcut, or a reconnect racing the mode check
cannot move REAPER's transport. Buttons and shortcuts are *additionally* dimmed/disabled in
Player mode for honesty (so a tap doesn't look like it silently failed), but that's a
courtesy layer — the network-level block is what actually holds.

**The setlist looks different in Player mode**, because a musician's screen has a different
job than a Director's. Controls that a Player can never use are *removed* rather than
dimmed — the drag handle, the ⋮ edit menus, the "Play Song" button — which on a phone hands
roughly 217px of a 347px-wide row back to the song name (it was getting 18px, about one
letter of a title). The skip/loop/chain toggles collapse to compact badges that appear only
when the flag is set: a Player can't press them, but *does* need to know a song loops or
chains into the next. Skipped songs stay clearly greyed out, the currently-playing row
renders at full strength, and the rest of the rows are only lightly dimmed so the names,
times and progress stay easy to read on stage.

**The sidebar is filtered the same way.** A Player keeps everything that only changes their
own screen — Display Filters, Theme, lyrics/chords fonts, sizes and colours, plus
**Auto-Scroll, Hide Skips and Grid View**, which are view toggles that never reach REAPER
(Auto-Scroll is a plain `scrollIntoView()`; the other two only re-render the list). What
goes is what steers the *show*: Queue Mode and Smooth Seek change how a click seeks, and a
Player can't click; Auto-Stop and Init Song MIDI send REAPER commands outright; Stop Hold
tunes a transport button that isn't there in Player mode; and MIDI Learn maps a controller
onto those same blocked commands, so a Player could bind a pedal and then watch it do
nothing. The three view toggles stay on purpose — they're the same ones Player mode already
leaves working on the keyboard, so hiding their switches would contradict shortcuts that
still respond.

The footer transport follows the same rule. PLAY / STOP / Loop are gone in Player mode —
they do nothing, and PLAY was the worst of them, since its label is the *action* rather
than the state, so it read "PAUSE" while playing on a screen where nothing can be paused.
Transport state is already on screen and clearer: the active row's progress fill moves and
its time counts down. **SYNC stays** — it restarts the polling connection, which is a read,
and it's the one recovery a musician has if a venue's wifi drops mid-show and auto-reconnect
doesn't catch it. (It used to be blocked by the bar's own click-through guard, so a Player's
only working button down there was unreachable; it works now.)

> **Not a security boundary.** REAPER's own Web Interface has no authentication — anyone on
> the same network who knows the endpoint can already control it directly, with or without
> ReaSet. Player mode stops *ReaSet* from being a way in; it does not lock the network down.

#### Director PIN (optional)
By default, choosing **Director** in the picker (or switching a badge from Músico to
Director) needs nothing but a tap — fine for a solo user, less fine once a band shares one
REAPER session and you don't want a curious tap on someone's phone to hand them the
transport. A Director can set a PIN from the sidebar (**Setlist Sync → Set/Change Director
PIN**); once set, *any* device actively choosing Director — not one recalling its already-
stored choice on a refresh — is asked for it first.

- The PIN itself is never sent anywhere as plain text: only a small hash is stored, in
  REAPER's own persisted ExtState (survives a REAPER restart, same mechanism the native-loop
  feature already relies on), so every device checks against the same value with no server.
- Leave the prompt empty when setting it to remove the PIN entirely.
- Like Player mode's own write-block, **this is a deterrent, not real security** — the hash
  algorithm is intentionally simple, and REAPER's Web Interface still has no authentication
  underneath any of this (see the box above). It stops an idle tap, not a determined person
  with network access.

#### Two Directors at once
ReaSet now watches for this instead of staying silent about it: each Director quietly
re-announces "I'm active" every few seconds while it holds the mode. If a second device
actively *chooses* Director while another one is already announcing itself, it's warned
before the switch completes and can back out. If a second Director appears later — mid-show,
on an already-stored device that skipped that prompt on boot — a red banner says so for as
long as the conflict lasts, then clears itself the moment the other Director closes its tab
or its own heartbeat goes stale. Nothing is blocked either way; REAPER is still yours to
choose to share on purpose (a fill-in Director covering a song, for instance) — you just
can't end up in that state *by accident* without knowing it.

The warning names the other device — *"El dispositivo 'X' ya está activo como
Director"* — instead of just "another one". Every device has a name: a rough
OS+browser guess (*"iPad · Safari"*) by default, or a custom one you set from
the sidebar (**This device: ... → Rename this device**), which is worth doing
once per tablet before a show so a conflict warning is actually useful.

#### Shared setlist sync (Director → Players)
Order, and each song's skip/loop/chain flags, live in the browser's own `localStorage` —
normally private to that one device. So that Players see the *Director's actual* setlist
instead of their own stale/default one, a Director can push a snapshot that Reaset.lua
writes to a file (`reaset_setlist_sync.json`) next to `ReaSet.html`; Players read it.

- **Push is automatic**, debounced ~1s after any edit (reorder, skip/loop/chain toggle,
  import). You don't need to remember to sync before a show.
- **Pull is manual** for a Director (sidebar → *Pull setlist from shared*) — adopting
  another device's shared setlist overwrites local, unsynced edits, so it asks first.
  Players pull automatically every few seconds in the background; nothing to click.
- A pulled setlist that doesn't match the **currently open REAPER project** (checked via
  the same project fingerprint used for per-project storage) is rejected rather than
  applied — you'll see a warning instead of a garbled setlist.
- **Known limits, by design, for this first pass:** only the active setlist's order and
  flags sync — not the full named-setlist library, and not the live queue/cue target
  (that's transient UI state; the actually-playing song already reaches Players for free
  via REAPER's own transport). Two Directors pushing at nearly the same moment still means
  last push wins — the conflict banner above warns you it's happening, but doesn't merge
  the two pushes. A dropped chunk (rare, needs a mid-push network hiccup) self-heals within
  about a second as the next tick retries — worst case, that one push is silently skipped
  and the next edit's push supersedes it.

---

## 9) Keyboard Shortcuts
ReaSet inherently supports the following global keyboard bindings to streamline command operations in rigid setups:

| Key | Action |
| --- | --- |
| **`Space`** | Play / Pause (Global transport toggle) |
| **`Enter`** | Smart Stop (Puts playhead at the beginning of the current active region) |
| **`Escape`** | Closes Live View overlay. If already closed, it immediately aborts an active 'Loop' state. |
| **`V`** | Toggles Live View overlay open/close |
| **`L`** | Toggles Lyrics floating widget visibility |
| **`C`** | Toggles Chords floating widget visibility |
| **`G`** | Toggles between List View and Grid View |
| **`O`** | Toggles Loop state over the currently playing Region/Sub-Region |
| **`Right Arrow`** | Cues the next valid (unskipped) track in the list |
| **`Left Arrow`** | Jumps playhead to the direct start locus of the currently playing track |
| **`Up Arrow`** | Cues the previous valid track in the list |
| **`Down Arrow`** | Resets cue to the very first song in the setlist |

---

## 10) Quick troubleshooting
### ❌ Lyrics or chords not showing
The panel's empty-state message tells you the **actual** cause — read it before
changing anything. `Reaset.lua` reports its status live:

| Message | Meaning | Fix |
|---|---|---|
| *"Reaset.lua is not running"* | The script isn't loaded, or you're on the legacy `Legacy/` scripts | Actions → ReaScript: Load… → `Reaset.lua` → Run |
| *"No track named lyrics/chords found"* | Script alive, but no track matched | Check the name against [the naming rules](#lyrics--chords-track-naming) |
| *"SWS extension missing"* | `ULT_GetMediaItemNote` unavailable | Install [SWS](https://www.sws-extension.org/) |
| *"Track X detected — no item under the cursor"* | Everything works | Move the playhead over an item that has **Item Notes** |

The last one is the most common false alarm: the track is found, but the playhead
is not over an item, or the item's **Notes** field is empty.

#### 🔍 Diagnostic script
If the message is not enough, run **`Tools/ReaSet_Diagnose.lua`** — see
[Tools](#5-tools) for what it reports.

### ❌ `ULT_GetMediaItemNote` error
- Missing compatible scripting/API environment; install dependency or adapt script.

### ❌ No interface data/control
- Verify Web Interface is enabled and reachable.
- Verify `main.js` loads from the same folder.

### ❌ The home-screen icon opens with an HTTPS error
Safari 18.2 added *"Warn before connecting to a website over HTTP"*, which on many devices
**blocks instead of warning**. REAPER's Web Interface serves plain HTTP, so the icon fails to
open with a message about HTTPS. Turn the option off in **Settings → Apps → Safari** (under
Privacy & Security). Adding ReaSet to the Home Screen itself does not require HTTPS — only
this Safari setting stands in the way.

### ❌ MIDI Learn shows no devices / doesn't respond
**Not currently supported in Safari — macOS, iPadOS, or iOS**, on any Apple
device. This is not a bug: Safari has never implemented the Web MIDI API
that the feature is built on, so there is no in-browser MIDI to detect.
Use a Chromium-based browser (Chrome, Edge), or map the controller directly
in REAPER instead of through ReaSet. See the [Roadmap](../ROADMAP.md).

---

