# Stage Reliability — Implementation Plan

Epic: [#2](https://github.com/OvictorVieira/ReaSet/issues/2)
Children: [#3](https://github.com/OvictorVieira/ReaSet/issues/3) ·
[#4](https://github.com/OvictorVieira/ReaSet/issues/4) ·
[#5](https://github.com/OvictorVieira/ReaSet/issues/5) ·
[#6](https://github.com/OvictorVieira/ReaSet/issues/6) ·
[#7](https://github.com/OvictorVieira/ReaSet/issues/7) ·
[#8](https://github.com/OvictorVieira/ReaSet/issues/8) ·
[#9](https://github.com/OvictorVieira/ReaSet/issues/9) ·
[#10](https://github.com/OvictorVieira/ReaSet/issues/10)

Out of scope for this epic: #1.

This document is the **pre-work audit** required by #2. It records what the code
does *today*, before any change, so that every later commit can be read against
a fixed baseline. Line numbers refer to `ReaSet.html` at commit `9a3c568`
(`Merge pull request #14 from djenttleman/testing/Auri`).

---

## 0. Architecture as it stands

```text
┌────────────────────┐   wwr_req / wwr_req_recur (HTTP)   ┌──────────────────┐
│  ReaSet.html (JS)  │ ─────────────────────────────────► │ REAPER Web Remote │
│  Director / Player │ ◄───────────────────────────────── │  (transport, ext) │
└────────────────────┘        wwr_onreply(results)        └──────────────────┘
          │                                                        ▲
          │ SET/EXTSTATE ReaSet/setlistChunkN + setlistRev          │ GetExtState
          ▼                                                        │
   ┌──────────────────────────────────────────────────────────────────┐
   │  Reaset.lua  (reaper.defer loop — one tick drives everything)     │
   │  loop_tick · autostop_tick · bridge_tick(lyrics/chords)           │
   │  sync_tick  → writes  <webroot>/reaset_setlist_sync.json          │
   │  library_tick → <project>/reaset/setlists/*.json + index          │
   └──────────────────────────────────────────────────────────────────┘
                                   │  plain HTTP GET (fetch)
                                   ▼
                      ┌────────────────────────────┐
                      │ Player device (ReaSet.html)│
                      └────────────────────────────┘
```

There is **no server**. Every device talks to the same REAPER Web Interface.
The only shared, cross-device storage is REAPER `ExtState` plus the two files
`Reaset.lua` writes into the web root / project folder.

---

## 1. Transport — current map

### 1.1 Observed state (produced by REAPER)

| Symbol | Where | Meaning today |
|---|---|---|
| `currentPos` | set in `wwr_onreply` `case "TRANSPORT"` (7160) | last position REAPER reported, polled at 33 ms |
| `isPlaying` | same (7193) | `playState & 1` |
| `wasPlayingLast` | 7192 | edge detector for the session clock |
| `_lastTransportTs` | 7180 | timestamp of the last TRANSPORT reply |
| `getExtrapolatedPos()` | 9255 | `currentPos + elapsed`, used only by the end-of-region trigger |
| `activeIdx` / `activeRegion` | recomputed **locally in six different places** | first `displayList[i]` whose `[start,end)` contains `currentPos` |

`activeRegion` is *not* a variable. It is re-derived ad hoc in
`updatePlaybackUI` (8589), `togglePlay` (9362), `smartStop` (9353),
`liveNav` (10414), `midiGetActiveIdx` (10698) and `toggleCurrentLoop` (8521).
Every one of those derivations reads the possibly-stale `currentPos`.

### 1.2 Intent state (produced by the user)

| Symbol | Where | Meaning today |
|---|---|---|
| `queuedRegion` | global, assigned in `playRegion` (9319/9322) | next song, **only while `queueModeToggle` is checked** |
| `window._playIntent` | `playRegion` (9313) | `{id, start}` — a *display* clamp for the MIDI-init pre-roll, cleared by TRANSPORT (7167) |
| `window._playRegionLocked` | `playRegion` (9307), `cueRegion` (9345) | `Date.now()+500` — suppresses the auto-stop STOP only |
| `window._pendingCuePos` | set by auto-stop (9032/9088), consumed by TRANSPORT (7184) | deferred `SET/POS` that waits for playState 0 |

**There is no `selectedRegion`.** Explicit "the user chose this song while
stopped" has no representation at all. This is the root of #3.

### 1.3 Play — every entry point

| # | Entry point | Line | Calls |
|---|---|---|---|
| 1 | Main transport PLAY button | 4425 | `togglePlay()` |
| 2 | Live View PLAY | 5080 | `togglePlay()` |
| 3 | Canvas PLAY | 5228 | `togglePlay()` |
| 4 | Keyboard `Space` | 10613 | `togglePlay()` |
| 5 | MIDI `play_pause` | 10687 | `togglePlay()` |
| 6 | MIDI `play` | 10685 | `wwr_req(1007)` **raw** |
| 7 | Song row (list) | 8302 | `playRegion(start,id)` |
| 8 | Song card (grid) | 8217 | `playRegion(start,id)` |
| 9 | Section row | 8364 | `playRegion(sub.start,sub.id)` |
| 10 | "Play Song" in expanded panel | 8376 | `playRegion(r.start,r.id)` |
| 11 | Search result pick | 8187 | `playRegion(...)` |
| 12 | Keyboard `R` (restart) | 10626 | `playRegion(active…)` |
| 13 | `delayAfter` timer | 9043 | `wwr_req(1007)` after `SET/POS` |

`togglePlay()` today (9360):

```js
function togglePlay() {
    if (isPlaying) { wwr_req(1008); }          // pause
    else {
        var activeIdx = /* scan displayList against currentPos */;
        if (activeIdx === -1 && displayList.length > 0)
            playRegion(displayList[0].start, displayList[0].id);   // ← #3 race
        else wwr_req(1007);
    }
}
```

Two defects, both named in #3:

* **`displayList[0]` fallback.** If `currentPos` does not land inside any
  region — which is exactly what happens in the window between a user's
  `SET/POS` and the next TRANSPORT reply, and also whenever the cursor sits in
  a gap between regions — Play starts *song 1*.
* **No intent input.** Even with a fresh `currentPos`, Play only ever consults
  the cursor. A tap that has not yet been acknowledged by REAPER is invisible.

### 1.4 `playRegion` — the cue/play/queue conflation

```js
function playRegion(start, id) {
    var queueMode = document.getElementById('queueModeToggle').checked;
    if (!isPlaying || !queueMode) {
        window._playRegionLocked = Date.now() + 500;
        window._pendingCuePos    = null;
        window._playIntent       = { id: id, start: start };
        seekManualTransport(midiInitPreroll(start), true);   // ← SET/POS + 1007
        queuedRegion = null;
        /* clear .queued classes */
    } else {
        /* resolve id in displayList or g_subRegionMap → queuedRegion, paint .queued */
    }
}
```

and `seekManualTransport(start, /*startWhenStopped*/ true)` (9281):

```js
if (!wasPlaying && startWhenStopped) { wwr_req("SET/POS/"+start+";1007"); return true; }
wwr_req("SET/POS/"+start);
if (wasPlaying && !smoothSeekEnabled) wwr_req(1007);
```

Consequences, matching the epic's symptom list one for one:

* **STOPPED + tap = PLAY.** `!isPlaying` takes the first branch, which appends
  action `1007`. Tapping a song *always* starts it (#3 A/B).
* **PLAYING + Queue Mode OFF = immediate seek.** `!queueMode` also takes the
  first branch, so the tap seeks the running transport (#9).
* **Queue only exists behind a toggle.** `queuedRegion` is reachable only when
  `queueModeToggle` is checked (#9, Option 1).

### 1.5 Pause

Pause is `wwr_req(1008)` — REAPER action 1008 is *toggle* pause — issued from
`togglePlay` (9361) and from the `+PAUSE` section marker (8952). There is:

* no manual-intent marker, so the automatic block in `updatePlaybackUI` keeps
  running against the *pre-pause* `currentPos` for up to a poll interval;
* no interlock with `queuedRegion` (8966, 9019) — a queued transition whose
  `subTimeRem`/`timeRem` window is already open will still fire a `SET/POS`
  after the user pressed Pause;
* no interlock with `_pendingCuePos` (7184), which fires *on the first
  `playState == 0` reply* — i.e. it will fire on the reply that reports the
  user's own pause, moving the cursor off the paused position.

That last one is the concrete mechanism behind "Pause does not feel
authoritative" in #4.

### 1.6 Stop

`smartStop()` (9352):

```js
wwr_req(1016);
if (target !== null) setTimeout(function () { wwr_req("SET/POS/" + target); }, 150);
```

with `target` = start of the region containing `currentPos`, **or
`displayList[0].start` if none** — the same first-song fallback as `togglePlay`.

Defects for #4:

* the 150 ms `setTimeout` is un-cancellable and un-guarded — it lands after the
  user may have already tapped something else;
* it does **not** clear `queuedRegion`, so 8966/9019 can still fire;
* it does **not** clear `window._pendingCuePos`, so 7184 fires on the very
  TRANSPORT reply that confirms the stop;
* it does not clear `_lastRegionEndTrigger` / `_endOfRegionLocked`, so the
  end-of-region block can re-arm;
* `_playRegionLocked` is not set, so the auto-stop branch (9080) is not
  suppressed either.

Stop entry points: main Stop (4426, hold/tap), Live Stop (5076), Canvas Stop
(5224), section-row `■` (8358), keyboard `Enter` (10614), MIDI `stop`
(**raw `wwr_req(1016)`**, 10686).

### 1.7 Automatic transport writers (the complete list)

Everything below can move REAPER without the user touching anything. #4's guard
must cover all of them.

| Line | Writer | Guarded by `_suppressAutoTransport()` today? |
|---|---|---|
| 7187 | `_pendingCuePos` consumption | **no** |
| 8634 | skipped-region auto-seek | yes |
| 8696 | skipped sub-section auto-seek | **no** |
| 8764/8765 | `SONG_END` special marker | yes |
| 8769/8771 | `STOP` special marker (+ 100 ms `setTimeout`) | yes / **timeout no** |
| 8920/8938/8943 | `+LOOP:N` / `+LOOPFULL` / `+LOOP` JS fallback | yes |
| 8952 | `+PAUSE` section marker | yes |
| 8961 | `>>>` transition | yes |
| 8966 | queued region at section end | yes |
| 9017 | song-level loop | yes |
| 9019 | queued region at region end | yes |
| 9029/9032 | per-song `stopAfter` | yes |
| 9039–9044 | per-song `delayAfter` (nested `setTimeout`s) | yes / **timeouts no** |
| 9056 | chain / auto-advance | yes |
| 9089 | auto-stop fallback STOP | yes |
| 7894 | `syncRegions` first-init cursor → `displayList[0].start` | **no** |
| 9350 | `cueRegion` (`1016;SET/POS`) — used by Next/Prev/MIDI | n/a (user) |

`_suppressAutoTransport()` (5665) is a *reconnect* guard only:
`Date.now() < _resyncGuardUntil`, armed on a >700 ms reply gap (7119) and on
page-hide (5800/5806). It has no concept of manual intent. #4 adds a second,
orthogonal guard rather than overloading this one.

### 1.8 Auto-Stop / NativeLoop / MIDI Init — must be preserved

* **Auto-Stop** is *armed, not detected*: `updatePlaybackUI` (8639–8651)
  publishes `autoStopStart` / `autoStopEnd` / `autoStop=on` to ExtState only
  when the key changes; `Reaset.lua:autostop_arm` (166) then stops REAPER at
  the exact sample in its own defer tick and republishes `autoStopArmed`.
  JS falls back to `wwr_req(1016)` only when `window._autoStopArmed` is false
  (9085). **Not to be touched.**
* **NativeLoop** — `_reaperNativeLoopOn/Off` + `Reaset.lua:loop_arm/loop_tick`
  (105/207), driving REAPER's own Repeat. **Not to be touched.**
* **MIDI Init** — `midiInitPreroll()` (9275) subtracts 5 ms so plugins receive
  MIDI before the region starts; `_playIntent` (9313, consumed at 7167) exists
  purely to stop that 5 ms from resolving the *previous* region in the display.
  #3 requires **cue must not pre-roll**: pre-roll belongs to Play, not to
  selection.

---

## 2. Sync — current map (issue #5)

### 2.1 Producer → transport → receiver → consumer

```text
PRODUCER (Director browser)
  saveCurrentState()                        7919
    ├─ setlists[currentSetlistName] = fmt
    ├─ localStorage[STORAGE_KEY], [CURRENT_KEY]
    ├─ _syncPushSoon()                      5963   (1000 ms debounce)
    └─ _libraryEnqueue(currentSetlistName)  5995
  _syncPushNow()                            5939
    ├─ _syncBuildPayload()                  5890   {v,fp,rev,ts,instanceId,currentSetlistName,setlist[]}
    ├─ SET/EXTSTATE ReaSet/setlistChunk0..N        (base64url, 700 chars each)
    ├─ SET/EXTSTATE ReaSet/setlistChunkCount
    └─ SET/EXTSTATE ReaSet/setlistRev              ← Lua's trigger

TRANSPORT (REAPER ExtState → disk)
  Reaset.lua sync_tick()                    541
    gate: setlistRev != s_syncLastCount
    → <webroot>/reaset_setlist_sync.json  = {"v":1,"b64":"…"}

RECEIVER (Player browser)
  applyModeUI() → _syncStartPlayerPolling() 6160   ← PLAYER MODE ONLY
    _syncPullNow(false) every 4000 ms       6094
      fetch(SYNC_FILE + '?t=' + Date.now(), {cache:'no-store'})

CONSUMER
  _syncApplyPayload(payload,false)          6108
    ├─ reject if payload.fp !== g_projectKey (only when g_projectKey is truthy)
    ├─ reject if payload.rev <= _syncLastAppliedRev
    ├─ reorder displayList by payload.setlist, copy chain/skipped/loop
    ├─ currentSetlistName = payload.currentSetlistName
    ├─ saveCurrentState()
    └─ lastRenderChecksum=''; renderSetlist(); updatePlaybackUI()
```

### 2.2 Confirmed defects

Each failure mode listed in #5 was checked against the source. Verdicts:

| # | #5's hypothesis | Verdict |
|---|---|---|
| 1 | Set switch does not hit the same choke point as edits | **CONFIRMED — primary root cause.** `changeSetlist()` (10511) writes `currentSetlistName`, writes `localStorage[CURRENT_KEY]`, resets `displayList`/`initialized`, calls `syncRegions()` — and **never calls `saveCurrentState()`**. `syncRegions()` *does* call `saveCurrentState()` at 7912, but only after `displayList` has been rebuilt, and the push it schedules carries the **new** name — so the switch does eventually push *if and only if* a REGION reply arrives and the render checksum path runs. Any failure to rebuild (no regions yet, project not loaded) drops the switch silently. The push is also debounced 1000 ms behind it. |
| 2 | Debounced push never scheduled for a pure switch | **PARTIALLY CONFIRMED** — see above; it is scheduled indirectly and late, never directly. |
| 3 | Player receives payload but does not rebuild the set | **PARTIALLY CONFIRMED.** `_syncApplyPayload` reorders `displayList` in place from `payload.setlist` (which is order-carrying, so the visible order is right) but never calls `updateSetlistDropdown()`, so the Player's own dropdown keeps showing the old name while the rows change underneath it. |
| 4 | `saveCurrentState()` after apply re-pushes | **NOT A BUG on a Player** (`_syncPushSoon` returns early outside Director) but **IS a bug for a Director doing a manual Pull**: apply → `saveCurrentState()` → `_syncPushSoon()` → the Director re-broadcasts what it just received under a *new* `rev`. |
| 5 | localStorage wins over shared state on refresh | **CONFIRMED.** Boot order is: `applyModeUI()` (7102) starts Player polling immediately → a pull can land while `g_projectKey` is still `null`, so the fingerprint check at 6110 is skipped and the payload applies → then the first `REGION_LIST_END` calls `_initProjectStorage()` (6312), which **overwrites** `currentSetlistName` from `localStorage[CURRENT_KEY]` (6324). Stale local name wins. |
| 6 | library sync and shared sync race during boot | **CONFIRMED** — same window as #5. |
| 7 | Session-local revision counters ignore a valid payload | **NOT CONFIRMED.** `_syncLastAppliedRev` starts at 0 on every load, so a refreshed Player accepts any `rev >= 1`. The *Director's* `_syncLocalRev` also restarts at 0 after a refresh, which means a refreshed Director's first push carries `rev=1` and a Player that already applied `rev=18` will **ignore it** until the Director pushes 18 more times. Real bug, different from the one hypothesised. |
| 8 | 4 s polling is an unsafe delay | **CONFIRMED.** 6162: `setInterval(…, 4000)`. Target is ≤1 s. |

### 2.3 `currentSetlistName` — every writer

| Line | Writer | Pushes? |
|---|---|---|
| 7033 | boot from `localStorage[CURRENT_KEY]` | n/a |
| 6324 | `_initProjectStorage()` re-read on project change | **no** |
| 6070 | library reconcile | writes localStorage directly |
| 10452 | `createSetlist()` | yes (`saveCurrentState`) |
| 10500 | `deleteSetlist()` | yes |
| **10512** | **`changeSetlist()` (the dropdown)** | **no — root cause** |
| 10536 | `importSetlists()` | **no** |
| 6137 | `_syncApplyPayload()` | yes (unwanted on a Director) |

---

## 3. Session / Director — current map (issue #6)

| Symbol | Line | Behaviour |
|---|---|---|
| `REASET_MODE` | 5277 | `'player'` by default (fails closed) |
| `REASET_MODE_STORED` | 5278 | true when `localStorage['reaset_mode']` held a real choice |
| `wwr_req` wrapper | 5303 | Player mode drops any command that is not all-`GET/` segments |
| `_isWriteCommand` | 5294 | fail-closed classifier |
| `chooseMode(mode)` | 7060 | PIN prompt, then **`window.confirm` that ALLOWS a second Director** |
| `applyModeUI()` | 7086 | badge, `body.reaset-player`, starts polling *or* heartbeat |
| `_dcStartHeartbeat()` | 6268 | writes `directorHeartbeatId/Ts/Name` every **4000 ms** |
| `_dcForeignActive()` | 6263 | foreign id **and** `Date.now() - _dcLastChangeAt < 9000` |
| `_dcWatchConflict()` | 6309 | 2000 ms banner poll |
| probe | 5323 | `GET/EXTSTATE/ReaSet/directorHeartbeat*` every **2000 ms** |

Timing today: beat 4 s · probe 2 s · TTL 9 s (≈2 missed beats) · banner 2 s.

Defects: `chooseMode` **permits** the second Director (7076–7079); the boot path
`if (REASET_MODE_STORED) applyModeUI()` (7102) starts a heartbeat with **no
conflict check at all**, so a refreshed stale Director silently re-arms; there is
no lease, only an advisory last-writer-wins ExtState triple; nothing revokes a
displaced Director's write authority.

---

## 4. Roles — current map (issue #7)

Only two roles exist. The read-only guarantee is real and lives at one
chokepoint (`wwr_req`, 5303) plus a visual layer (`body.reaset-player`, CSS
3802–3960). A third role needs a **third classification**, not a third CSS
class: transport writes (`1007`/`1008`/`1016`/`SET/POS`) must be separable from
publish writes (`SET/EXTSTATE/ReaSet/setlist*`, `directorPinHash`,
`library*`) — today both are simply "not GET".

---

## 5. Visual blocks — current map (issue #8)

* `getSongEnd(song)` (8433) → `'stop' | 'wait' | 'continue' | 'auto'`, derived
  from `getOverride(id).stopAfter` / `.delayAfter` / `song.chain`.
* `songEndVisual(song)` (8473) already resolves `'auto'` against
  `#autoStopToggle.checked` — **for the icon only**. The block logic needs the
  same resolution as a *value*, so this is where `effectiveSongEnd()` belongs.
* `renderSetlist()` (8200) builds two layouts. In **list** mode the top-level
  node is `li.song-container` (8266) with `div.song-row` inside; in **grid**
  mode the top-level node is `li.grid-card` (8215). Section rows live in
  `div.section-list > div.section-row` (8362) inside the same `li`, so a margin
  on `li.song-container` can never leak between sections. That is the safe
  hook.
* Skips: the loop `continue`s on `hideSkippedMode && r.skipped` (8218/8241)
  *after* the totals are accumulated. "Previous relevant song" must therefore be
  computed over the same predicate the renderer uses to emit rows, not over
  `displayList[i-1]`.
* Re-render triggers already exist and all funnel through
  `lastRenderChecksum = ''; syncRegions()` (or `renderSetlist()`), so live
  updates need no new plumbing — the checksum at 7913 already includes
  `g_songOverrides`, but **not** the Auto-Stop toggle state, so a global
  Auto-Stop flip will not by itself repaint. That is a one-line fix in the
  Auto-Stop handler.

---

## 6. Dependency graph

```text
        ┌──────────────────────────────┐
        │ #10 diagnostics (?diag=…)    │  ← no dependencies; unblocks everyone
        └──────────────┬───────────────┘
                       │ (observability used by all)
      ┌────────────────┼────────────────────────────┐
      ▼                ▼                            ▼
┌───────────┐   ┌──────────────┐            ┌───────────────┐
│ #3 select │──►│ #9 queue     │            │ #5 setlist    │
│  + Play   │   │ while playing│            │    sync       │
└─────┬─────┘   └──────┬───────┘            └───────┬───────┘
      │                │                            │
      └────────┬───────┘                            │
               ▼                                    ▼
        ┌─────────────┐                      ┌─────────────┐
        │ #4 Pause /  │                      │ #6 single   │
        │    Stop     │                      │   Director  │
        └──────┬──────┘                      └──────┬──────┘
               │                                    │
               └───────────────┬────────────────────┘
                               ▼
                       ┌───────────────┐
                       │ #7 Controller │
                       └───────────────┘

        ┌───────────────────────────────┐
        │ #8 visual blocks (independent)│  ← touches renderSetlist + CSS only
        └───────────────────────────────┘
```

Hard edges:

* **#3 → #9 → #4** share one state machine (`selectedRegion` / `queuedRegion` /
  manual guard). They must land in that order, in one branch.
* **#7 → #3,#4,#9** — Controller must reuse the transport semantics, not
  duplicate them.
* **#7 → #5** — a Controller that does not follow the Director's set is useless.
* **#7 → #6** — the role model and the lease share `REASET_MODE` and the mode
  picker.
* **#8** is independent: it touches `renderSetlist()` row construction and CSS,
  which no other track edits.
* **#10** is independent and lands **first** so the other tracks can be
  instrumented as they are written.

---

## 7. Tracks, branches, and file ownership

`ReaSet.html` is one 11 355-line file, so tracks are separated by **region of
the file**, and integration is serialized.

| Track | Issues | Branch | Regions of `ReaSet.html` it owns | Other files |
|---|---|---|---|---|
| **F — QA** | #10 | `test/stage-diagnostics` | new `RSDiag` block inserted just after the `wwr_req` gate (~5310); one-line instrumentation calls elsewhere | `docs/STAGE_TEST_MATRIX.md` (new) |
| **A — Transport** | #3 → #9 → #4 | `fix/stage-transport` | 9281–9370 (`seekManualTransport`/`playRegion`/`cueRegion`/`smartStop`/`togglePlay`), 7160–7195 (TRANSPORT case), 8960–9095 (queue + end-of-region), 10613–10640 (keyboard), 10685–10690 (MIDI), 7894 (init cursor) | — |
| **B — Sync** | #5 | `fix/active-setlist-sync` | 5890–5975 (payload/push), 6094–6165 (pull/apply/poll), 6312–6330 (`_initProjectStorage`), 10511 (`changeSetlist`), 10530 (`importSetlists`) | `Reaset.lua` `sync_tick` (541) |
| **C — Session** | #6 | `fix/single-director` | 6255–6320 (heartbeat), 7060–7105 (`chooseMode`/`applyModeUI`/boot), 5277–5310 (mode + gate) | — |
| **D — Controller** | #7 | `feat/controller-mode` | 5277–5310 (gate → capability classifier), 7060–7105 (picker), CSS 3800–3960, mode badge/i18n | — |
| **E — Blocks** | #8 | `feat/setlist-block-spacing` | 8200–8390 (`renderSetlist` row construction), 8433–8490 (`getSongEnd`/`songEndVisual`), CSS near `.song-row` | — |

Overlaps that require serialized integration (not blind merge):

* **A ∩ F** at every transport call site — F lands first, A writes its new code
  already instrumented.
* **C ∩ D** at `chooseMode`/`applyModeUI`/`REASET_MODE` — C lands first, D
  extends the role enum it leaves behind.
* **B ∩ D** at `_syncPushNow`'s Director gate — D reads it, does not rewrite it.
* **A ∩ E** at `renderSetlist` — A only changes the row's `onclick` target, E
  only changes the row's classes/wrapper. Different attributes on the same line
  ⇒ merge by hand.

Integration branch: **`dev/stage-reliability`**, merged in this order:

```text
#10 → #3 → #9 → #4 → #5 → #6 → #7 → #8
```

---

## 8. Target state machine (what the tracks build)

```text
        ┌───────────────────────── observed ─────────────────────────┐
        │  currentPos      last position REAPER reported             │
        │  isPlaying       last playState REAPER reported            │
        │  activeRegion    region containing currentPos (derived)    │
        └────────────────────────────────────────────────────────────┘
        ┌───────────────────────── intent ───────────────────────────┐
        │  selectedRegion  {id,start,end,at}  explicit, while idle    │
        │  queuedRegion    {id,start,end,at}  explicit, while playing │
        │  manualGuard     {intent:'pause'|'stop'|null, until:ms}     │
        └────────────────────────────────────────────────────────────┘

  STOPPED / PAUSED ──tap song X──► selectedRegion = X ; SET/POS X ; stay stopped
  STOPPED / PAUSED ──Play──────► resolvePlayTarget():
                                   1. selectedRegion            (explicit)
                                   2. region containing cursor  (observed)
                                   3. nothing → plain 1007      (never displayList[0])
  PLAYING          ──tap song X──► queuedRegion = X ; NO SET/POS ; NO 1007
  PLAYING          ──Pause─────► manualGuard('pause') ; 1008 ; keep selection
  ANY              ──Stop──────► manualGuard('stop') ; 1016 ;
                                 queuedRegion = null ; _pendingCuePos = null ;
                                 cancel pending timers ; clear end-of-region dedup
  song end + effectiveEnd == 'continue' + queuedRegion  → SET/POS queued
  song end + effectiveEnd == 'stop'     + queuedRegion  → stop; queued → selected
```

`manualGuard` blocks **automatic transport writes only** — never rendering,
never a subsequent explicit user command.

---

## 9. Risk register / rollback

| Risk | Mitigation |
|---|---|
| Cue-only changes muscle memory for existing users | Behaviour is the epic's explicit product decision; documented in `docs/USER_GUIDE*.md` and the test matrix |
| Manual guard swallows a legitimate auto-advance | Guard is bounded (short TTL) and cleared by the first confirming TRANSPORT reply, never open-ended |
| Faster polling floods REAPER | Poll a tiny `setlistRev` ExtState value, fetch the full payload only when it changes |
| Lease arbitration races in the browser | Fail closed — refuse the second Director; move arbitration into `Reaset.lua` only if a real race is reproduced |
| Rollback mid-show | Every track is a separate branch and a separate small commit; `git revert` of a single track is always possible. The last known-good tag on `main` is `9a3c568`. |

## 10. What cannot be verified in CI

`ReaSet.html` only runs meaningfully inside REAPER's Web Interface (`wwr_req`
is injected by REAPER; outside it, it is stubbed at 5261). Every behavioural
claim in #3–#9 therefore ends in **READY FOR MANUAL REAPER TEST**, with the
procedure in `docs/STAGE_TEST_MATRIX.md`. Static checks that *do* run in this
repo: `python -m pytest tests/test_reaboot_package.py -q` (packaging contract)
plus JS syntax validation of the single-file build.
