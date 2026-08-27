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

| Track | Issues | Branch (deleted after merge — see the rollback table in `STAGE_TEST_MATRIX.md` for the permanent SHAs) | Regions of `ReaSet.html` it owns | Other files |
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

---

## 11. Role permission matrix (as built, #7)

Enforced in three layers, outermost first. The CSS layer is never the only
thing standing between a role and a write.

1. **Command classifier** (`_commandClass` → `wwr_req` gate). Every command
   REAPER could receive from this page passes through one function.
2. **Capability check inside each mutator** (`canEditSetlist()` /
   `canPublishSetlist()` / `canControlTransport()`).
3. **CSS** (`body.reaset-controller`) — so a control that would do nothing does
   not *look* like it worked.

> **Superseded on the Player column.** The read-only *Player* role was retired
> after this audit; see §13. Both surviving roles drive transport, and the line
> between them is authoring. The Player column is kept below because it records
> what the audit measured, and because the migration path depends on it: a
> device that stored `'player'` comes back as a Controller, gaining exactly the
> ✅s in the Controller column and nothing else.

| Action | Director | Controller | ~~Player~~ (retired) |
|---|---|---|---|
| Play / Pause / Stop | ✅ | ✅ | ❌ |
| Cue song while stopped / paused | ✅ | ✅ | ❌ |
| Queue song while playing | ✅ | ✅ | ❌ |
| Next / Previous (song and section) | ✅ | ✅ | ❌ |
| MIDI-mapped transport | ✅ | ✅ | ❌ |
| Reorder setlist | ✅ | ❌ | ❌ |
| Skip / Loop / Chain / end-state authoring | ✅ | ❌ (state visible, inert) | ❌ (state visible, inert) |
| Per-song overrides (`⋮` menu) | ✅ | ❌ | ❌ |
| Create / delete / import / export setlists | ✅ | ❌ | ❌ |
| Switch active named setlist | ✅ | follow only | follow only |
| Publish shared setlist (`SET/EXTSTATE ReaSet/setlist*`) | ✅ | ❌ | ❌ |
| Arm Auto-Stop / NativeLoop in `Reaset.lua` | ✅ | ❌ | ❌ |
| Set the Director PIN | ✅ | ❌ | ❌ |
| Claim / take over the Director lease | ✅ | ✅ (explicit, or automatic when nobody is directing — §13) | ✅ (explicit) |
| Edit mode (drag handles) | ✅ | ❌ | ❌ |
| Lyrics / chords / Canvas / Live View | ✅ | ✅ | ✅ |
| Local display prefs (theme, fonts, Auto-Scroll, Hide Skips, Grid) | ✅ | ✅ | ✅ |
| Smooth Seek, Init Song MIDI, Stop Hold | ✅ | ✅ (local to this device's own seeks / Play / Stop button) | ❌ |
| Queue Mode switch | ✅ (governs the EDIT-mode audition jump only) | ❌ | ❌ |
| RECONNECT (restart polling) | ✅ | ✅ | ✅ |

### Command classes

| Class | Shape | Director | Controller |
|---|---|---|---|
| `read` | every `;`-segment starts `GET/` | ✅ | ✅ |
| `transport` | action ids `1007` / `1008` / `1016`, and `SET/POS/…` | ✅ | ✅ |
| `publish` | everything else — `SET/EXTSTATE`, `SET/EXTSTATEPERSIST`, `SET/REPEAT`, `SET/PROJEXTSTATE`, unrecognised shapes | ✅ | ❌ |

The transport set is a **whitelist**, not a pattern. "Any bare number is an
action id" would let a Controller send any REAPER action at all, which defeats
the point of the role. Anything unrecognised is `publish`, so a command added
later is Director-only until somebody classifies it deliberately.

The one deliberate exception is the Director lease (`_dcWriteLease`), which
writes `SET/EXTSTATE ReaSet/director*` outside the gate. It has to: the claim
happens *before* a device is a Director, so gating it would deadlock
arbitration permanently in favour of whoever was already there. It can write
those keys and nothing else.

> **Not a security boundary.** REAPER's Web Interface has no authentication
> unless configured separately, so anyone on the network can drive REAPER
> directly regardless of what ReaSet allows. This is an operational safety
> boundary that stops a musician from editing the show by accident, and it is
> not intended to resist an attacker.

---

## 12. Findings carried over from the first plan revision

An earlier revision of this document (commit `4cb382e`, kept in history) audited
the same code independently. Its conclusions agree with §1–§5 above almost
everywhere. Four points it raised are recorded here with what was done about
each, so nothing from that pass is lost when the two documents merged.

### Acted on

**Followers could not compute block boundaries.** The shared payload carried
only `chain`, `skipped` and `loop`. But `getSongEnd()` also reads
`g_songOverrides` — `stopAfter` / `delayAfter`, which live in **this browser's**
localStorage — and `effectiveSongEnd()` resolves `'auto'` against **this
device's** Auto-Stop toggle. A Player therefore had no way to know a song was
marked "always stop" on the Director, and would draw a completely different set
of blocks from the same setlist. Fixed by adding `end` (the resolved end-state)
per song and `autoStop` (the global) to the payload, and by having
`getSongEnd()` prefer a synchronised end-state on a follower.

**Chunked pushes could be assembled across generations.** The chunk bodies,
the count and the revision are separate HTTP requests. `Reaset.lua` retries
while any chunk is empty, which covers a *late* chunk — but not a *stale*
one: a shorter push leaves the previous generation's later chunks in place
with non-empty values, and a dropped request in the middle of a longer push
leaves one old chunk between two new ones. Base64 concatenated across two
generations decodes to garbage and fails at `JSON.parse` on every follower,
with no signal about why. Fixed by publishing the total payload length
alongside the count and having `Reaset.lua` refuse to write a file whose
reassembled length does not match.

### Considered and not done

**Lease arbitration in `Reaset.lua`.** That revision proposed moving
owner/epoch/TTL into Lua. #6 says explicitly not to add that complexity unless
a reproducible browser-only race requires it. The claim/settle/check protocol
in §3 resolves simultaneous acquisition through ExtState's own
last-writer-wins, and the id tiebreak bounds the residual window to a couple of
seconds rather than leaving it open. If real-device testing (S11) produces a
dual-Director state that persists, the Lua arbiter is the next step and this is
the note that says so.

**Two tabs in one browser share an `instanceId`,** so they are invisible to
each other's conflict detection. Real, and out of scope: `instanceId` is
persisted precisely so a Director that refreshes is still recognised as the
same Director, and the stage scenario is two devices, not two tabs. Noted here
because it makes two tabs a *bad way to test* #6 — see the test matrix, which
requires physical devices for exactly this reason.

---

## 13. Role model, revised: two roles and no question on the way in

Added after the epic's implementation, on the project owner's decision. It
supersedes the three-role model §11 audited.

### What changed

**The read-only *Player* role is retired.** Two roles remain:

| | Director | Controller |
|---|---|---|
| Setlist: order, chains, loops, skips, end-states, overrides | ✅ owns it | ❌ follows |
| Publishes to the other devices | ✅ | ❌ |
| Play / Pause / Stop / cue / queue | ✅ | ✅ |
| How many per session | exactly one | any number |

The line between them is **editing, not transport**. Every device in the room is
there to play the show; a phone on a mic stand that can display the setlist but
cannot start it is a worse instrument than the spacebar it replaced. Anyone who
opens ReaSet can move REAPER — only the Director can change what REAPER plays.

**The mode picker no longer opens on the way in.** A device with no stored
choice used to be held behind a forced three-option modal asking a musician a
question about a distributed lease protocol, thirty seconds before downbeat.
The answer is one the code can derive, so it does: the page opens as a
Controller — usable immediately, transport live, following whatever the
Director has published — and `_dcAutoResolveRole()` then reads the room. A live
foreign heartbeat means somebody is already directing; its absence means
somebody has to.

The picker still exists and is still reachable from the mode badge. It is now
what it should always have been: the way to *change* a role, not a tollgate.

### Why the automatic claim waits longer than a deliberate one

`_dcBeatIsProofOfLife` judges a foreign Director alive by **whether its
timestamp changed**, never by comparing a foreign clock to ours (see §6 — two
devices' clocks disagree, and the heartbeat must not care). The cost is that a
foreign heartbeat id read once is *ambiguous*: a Director beating normally whose
timestamp has simply not been seen to change yet, or a corpse left in ExtState
by a laptop that closed without releasing the lease. Distinguishing them takes
one full `DIRECTOR_BEAT_MS` observed across the 2s probe — **longer** than the
`DIRECTOR_CLAIM_MS` window a deliberate claim uses.

A deliberate claim can live with that gap: a human pressed the button, and
`_dcWatchConflict` resolves a double-claim by id tiebreak within a couple of
seconds. An automatic claim cannot, because it fires on **every boot of every
device** — the same odds that are acceptable once are, repeated, a phone that
walks in during the second song and takes the show off the Mac. So when a
foreign heartbeat id is present but unproven, the resolver waits a full
`DIRECTOR_TTL_MS` and looks again. Nothing is lost by waiting: the device is
already a working Controller with live transport; the only thing it cannot do
meanwhile is edit.

### Two things the automatic path deliberately refuses

**A configured Director PIN blocks it.** The PIN exists to make directing a
deliberate act, and an automatic claim would satisfy it without anyone typing
it. `_directorPinHash === null` (probe reply not yet landed) is treated as
*unknown*, not as "no PIN" — claiming on a value that has not been read is
exactly the blind claim the PIN prevents — so the resolver defers once and
decides on evidence.

**An automatic role is never persisted.** It is a reading of the room right
now, not a decision, so every boot takes the reading again. That is what makes
it self-healing: close the Director's laptop and the next device to reload
picks the lease up, instead of a room full of Controllers with nothing to
follow. Only an explicit pick — the selector, or the badge — is stored, and
`_roleChosenExplicitly` guards the resolver so a choice made during its claim
window always wins.

### Consequences elsewhere

- **`REASET_MODE` now defaults to `'controller'`**, not `'player'`. It still
  fails closed on the property that matters: a race before the mode resolves
  can move the playhead but can never mutate the shared setlist. A stray seek
  is undone with one tap; a setlist overwritten by a device that turned out not
  to be the Director is not.
- **`_dcStandDown()` drops to Controller.** A displaced Director loses the
  *setlist*, not the transport. The musician holding it is still in the band and
  still has to be able to start the next song.
- **`localStorage['reaset_mode'] === 'player'` is migrated to `'controller'`**
  on read, so devices carrying the retired role come back usable rather than
  booting into a role nothing renders.
- **The `body.reaset-player` stylesheet is gone** — ~140 lines of dimmed
  transport and inert rows that nothing could match any more.
- **The read-only keyboard gate is gone.** Space / Enter / KeyO / arrows are all
  transport, and both roles may drive transport.
- **`director-only` rows are no longer hidden from a Controller.** The three
  that carry it without `authoring-only` — Smooth Seek, MIDI Init, Stop Hold —
  all tune how *this device* issues *its own* transport (verified:
  `setSmoothSeek` and `setStopMode` write only localStorage, and
  `initSongMidiToggle` is read solely by `midiInitPreroll`). A Controller that
  may press Stop is entitled to say whether its own Stop button takes a tap or a
  hold. The rows that publish — Queue Mode, Auto-Stop — carry `authoring-only`
  as well, and that is what hides them.

### Locked by tests

`tests/test_reaset_html.py`: `test_player_role_is_gone`,
`test_default_mode_cannot_author`,
`test_fresh_device_resolves_its_role_instead_of_asking`,
`test_stand_down_drops_to_controller_not_read_only`. Each was verified to fail
against a mutation of the source that reintroduces the behaviour it forbids.

### Still requires a real-device test

Two devices, one REAPER. §13 changes *who may do what* and *how a role is
chosen*; neither can be proven in this repository, because `wwr_req` is injected
by REAPER's own web server. See `docs/STAGE_TEST_MATRIX.md` §C.

---

## 14. Session clock: the Director owns it

Reported from the stage: the phone read **6:02:21** while the Mac read **1:48**,
same show, same REAPER.

### What it had been measuring

Not "how long the project has been open". Wall-clock since **the first playback
on that device**, written to that browser's own `localStorage`, and it never
expired — it survived reloads, quitting the browser, and changing REAPER
projects. Three separate reasons the two numbers could not agree:

1. **Per-device by construction.** Each browser wrote its own
   `reaset_session_start`. There was no shared value, so two devices agreed only
   by coincidence.
2. **It started on that device's first Play**, not the show's. A phone used for
   soundcheck at 14:00 and a Mac first played at 19:30 were measuring two
   different things, both correctly.
3. **Nothing ever cleared it.** The only reset was a 600ms long-press. The 6h
   was a leftover start timestamp from an earlier session, still counting.

The same value drove `#live-show-time`, so Live View inherited the discrepancy.

### Why the wire carries ELAPSED and not a start timestamp

The obvious synced design — publish `sessionStart` as epoch milliseconds, let
each device compute `Date.now() - start` — **is wrong**, and wrong in exactly
the way this codebase already went out of its way to avoid once.

A phone and a Mac do not agree on `Date.now()`. Phones drift and resync against
the carrier; a laptop that slept holds a stale clock for a while after waking.
Publishing an absolute start renders that disagreement *directly on screen* as
an offset — so the two devices would still differ, only now the difference would
look like a bug in ReaSet rather than in the clocks.

So the Director publishes **elapsed seconds**, on every heartbeat:

```
SET/EXTSTATE/ReaSet/sessionElapsed/<integer seconds>      // -1 = no session
```

and a follower anchors it against its **own** clock the instant it arrives:

```
displayed = publishedElapsed + (now − whenIReceivedIt)
```

Only local differences are ever taken. Foreign clock skew cancels out completely
and cannot reach the screen. This is the same rule `_dcBeatIsProofOfLife`
follows for the heartbeat: **judge by what changed locally, never by comparing a
foreign clock to ours.**

The anchor is refreshed **only when the value changes**. The Director publishes
every `DIRECTOR_BEAT_MS` (4s) and the probe polls at 2s, so every value is seen
more than once; re-anchoring on a repeat would restart the extrapolation each
time and drag the displayed time visibly backwards.

`sessionElapsed` is published as a **separate request**, not as another segment
on the heartbeat write. `_dcWriteLease` bypasses the publish gate, and it may
keep doing so for exactly the `ReaSet/director*` keys and nothing else —
widening it to carry the clock would trade a real invariant for one saved HTTP
request.

### Why it expires on idle, not on age

A start timestamp that never expires is how six hours accumulated. But "reset
after N hours" is wrong too: a long rehearsal is a real session, and zeroing it
mid-way is the failure the persistence exists to prevent.

What separates two sessions is a **gap** — nobody played anything for hours — so
that is what is measured. The stored record is `{s: start, t: lastPlayback, p:
projectKey}`, and a gap of more than `SESSION_IDLE_RESET_MS` (4h) since the last
observed playback discards it on load. A six-hour rehearsal with playback
throughout keeps counting; a laptop that played at 14:00 and is reopened at
20:00 starts over. `t` is refreshed while playing, throttled to one
`localStorage` write a minute — the clock ticks every second and a write per
second for the length of a show is not a thing to do on a phone.

The legacy bare-integer format is read as `{s: v, t: v}` — last seen *at* the
start — so anything old enough to be the reported bug expires on the very first
load after this change.

A different REAPER project is a different show: `_initProjectStorage` clears the
clock when `g_projectKey` changes, alongside every other project-scoped store.

### Handover does not restart the show

A device that was following a Director which then went away — or that took over
from it — already holds the show's elapsed time in its anchor, so on promotion
it adopts that as a local start rather than counting from its own first
playback. Without this, the Mac closing its laptop would reset everyone's clock
to whenever the phone happened to press Play.

Whichever session began **earlier** wins: a device that has been in the room
since soundcheck knows more about when this started than a Director that joined
an hour in. The arithmetic is entirely local — the anchor is already expressed
as "this many seconds, at *this* instant on *my* clock".

### Reset is Director-only

A follower clearing its local value would watch the Director's next published
tick overwrite it half a second later: a button that silently does nothing. The
long-press refuses on a follower, `#tb-session-grp.is-readonly` drops the
pointer cursor so it does not look pressable, and the `title` says which clock
is on screen. On the Director the reset publishes the `-1` sentinel immediately
rather than waiting for the next beat, so it reaches every device within one
poll.

### Fallback

A follower shows its **own** clock whenever no Director is live —
`_dcForeignActive()`, the same proof-of-life the lease uses. So a device that
loses contact mid-show keeps counting instead of freezing, and a device running
solo has a clock at all. `_sessionDisplaySec()` is the single place that decides,
which is what stops `#tb-session` and Live View's `#live-show-time` from ever
disagreeing.

One visible consequence, accepted: a freshly-booted follower shows its own clock
for the few seconds proof-of-life takes, then switches to the Director's. It is
self-correcting and honest — the alternative is showing `0:00` while pretending
to know something it has not established yet.

### Locked by tests

`test_session_clock_never_puts_a_timestamp_on_the_wire`,
`test_session_clock_reanchors_only_on_change`,
`test_session_clock_reset_is_director_only`, and
`test_session_clock_behaviour` — the last **executes** the real restore, observe,
display and promotion code under Node against a stubbed clock and
`localStorage`, covering ten cases including the reported bug, a six-hour
rehearsal that must NOT expire, the legacy format, the skew immunity property,
and both handover directions. Each check was verified to fail against a mutation
reintroducing what it forbids — an absolute timestamp on the wire, re-anchoring
on duplicates, a follower that may reset, expiry on age instead of idle, a
remote value treated as absolute, a missing local fallback, a legacy record
given a free pass, a promotion that restarts the clock, one that clobbers an
older session, and one that does its arithmetic against the foreign clock.

### Still requires a real-device test

The skew case is the one that separates this implementation from the naive one,
and it cannot be run here. See `docs/STAGE_TEST_MATRIX.md` §S.

---

## 15. Controller surfaces, Slide to Stop, and the two-icons-one-symbol bug

Four fixes from the owner's second pass on real hardware.

### A Controller gets a banner, not a dead dropdown

The setlist picker was left in place for a Controller with `pointer-events: none`
and `opacity: 0.85`. That is a *disabled control*, and a disabled dropdown still
promises a choice: the chevron is drawn, the tap does nothing, and on a phone
that reads as an app that has hung — not as a permission boundary.

It is now replaced outright. `body.reaset-controller` hides `.setlist-picker`
and shows `.setlist-banner`, which states the same two facts the picker carried
and offers nothing: the active set's name, and — since a Controller has no
picker to open — whether the project is reachable at all, which would otherwise
be unlearnable on that device.

Same visual family as `.n-select-btn`: same height, radius, type and inset,
minus the border, hover, chevron and pointer. The dot pulses only while REAPER
is playing, borrowing the Director badge's living-dot language so one glance
says both "this is the set" and "the show is running".

Both surfaces are filled from `renderSetlistPicker()`, so they cannot show
different setlists — a bug the picker already had once against the hidden
`<select>` it shadows.

`_refreshSetlistBanner()` is called from `updatePlaybackUI()`, which runs at
**transport poll rate**. The `title` write is therefore guarded on change:
`classList.toggle` is a no-op when the state already matches, an attribute
assignment thirty times a second is not, and that is the exact shape of the two
performance faults already fixed on this branch.

### A Controller sees only the songs that will play

Hide Skips is a *view preference* for the Director, who needs to see the songs it
dropped in order to put them back. For a Controller it is not a preference at
all: a skipped song is not in tonight's set, the Controller cannot un-skip it,
and a greyed-out row it must learn to ignore is one more thing to misread on a
dark stage between songs.

`_hideSkippedEffective()` returns `hideSkippedMode || !canEditSetlist()`.
Deliberately **derived, never assigned** into `hideSkippedMode` — that value is
persisted, so forcing it would silently rewrite the Director's own preference on
any device that had ever been a Controller.

Both render loops and, critically, **both render checksums** use it. A checksum
left on the raw preference is worse than no filter at all, because the list then
keeps its old contents across a role change until something unrelated happens to
move the checksum — a bug that only appears sometimes. `applyModeUI()` clears
`lastRenderChecksum` and repaints, so the change lands on the role switch rather
than on the next poll. The sidebar toggle is `authoring-only`, since where it is
forced it could only ever be a switch that does nothing.

### Slide to Stop

Stop is the one transport control whose mistake is unrecoverable in front of an
audience, and on a phone it sits between PLAY and Loop where a thumb reaching for
either can land on it.

The old guard was a three-second **hold**, and holding is the wrong gesture for
it: it is invisible until it completes, indistinguishable from a tap that did not
register, and a musician who presses and lets go has no way to tell whether the
app is broken or whether they simply did not press long enough. *That is exactly
the "I pressed Stop and it did not stop" report this replaces* — the label bug
fixed in `8990f6f` was the same failure seen from the other side.

A slide cannot be performed by accident, shows its own progress, and is abandoned
by doing nothing. Same reasoning macOS uses for slide-to-power-off.

- Commit threshold is **82%** of travel, and the stop fires on **release**, not
  on crossing it. A finger that reaches the end and slides back has changed its
  mind, and being abandonable is the whole point.
- The label follows the state: `SLIDE TO STOP` → `RELEASE TO STOP` when armed.
- **Pointer events**, not the inline `onmousedown`/`ontouchstart` pairs the markup
  carried: those fire twice on a touchscreen that also reports mouse events, and
  the drag has to survive the finger leaving the button — which is the *normal*
  way this gesture ends, since the thumb is at the far edge by then. Pointer
  capture keeps the stream coming.
- `touch-action: none` in slide mode only. Without it the first vertical wobble
  hands the gesture to Safari's scroller and the thumb stops following.
- Tap mode is unchanged and still available from the sidebar.
- Stored `'hold'` **migrates to `'slide'`** — a device that came back wanting a
  gesture nothing implements is a Stop button that does nothing at all, again.

Every rule is written against a shared `.stop-ctl` class rather than the three
buttons' own classes, because the last time each carried its own markup, two of
the three never updated their label. The retired `stop-holding` machinery and its
`@keyframes stop-fill` are deleted rather than left inert.

Keyboard Enter still stops immediately, deliberately: the risk this guards
against is a fat finger on a phone, and pressing Enter is not one.

### RECONNECT no longer wears the loop icon

The reconnect button drew `&#8635;` — the identical codepoint `.t-btn-loop` draws,
two buttons away on the same transport bar. Mid-show that is a coin flip between
"repeat this song" and "restart the network connection", and those are not
neighbouring mistakes. It is now an inline plug SVG, which says *connection* and
cannot be read as *repeat*. The sidebar's copy of the action uses the same icon.

### Locked by tests

`test_every_stop_button_says_what_it_wants`,
`test_stop_slide_fires_on_release_not_on_threshold`,
`test_stop_mode_migrates_the_retired_hold`,
`test_controller_gets_a_banner_not_a_dead_dropdown`,
`test_controller_list_excludes_songs_outside_the_set`, and
`test_reconnect_does_not_share_the_loop_glyph`.

Twelve mutations were run against these. **Three of them initially passed** and
the tests were tightened until they failed: counting `_hideSkippedEffective()`
call sites was satisfied by the function's own declaration, so the raw preference
is now banned from the render path outright; nothing asserted the reconnect glyph
at all; and asserting `_libConnected` merely *appeared* in the banner function was
satisfied by the `title` line surviving after the offline class was removed.

### Still requires a real-device test

**T23–T30** and **C18–C22** in `docs/STAGE_TEST_MATRIX.md`. T25 (slide back and
release must NOT stop) and T26 (diagonal drag on a phone must not be stolen by
the scroller) are the two that cannot be reasoned about from here.

---

## 16. pt-BR, and closing the gap where strings bypassed the table

Issue #14. Two problems, and the second had to be fixed first or the first only
half-lands.

### The table now has three columns, and every column is still a key

```js
I18N_ROWS = [ ["English", "Español", "Português"], … ]   // 211 rows
I18N_LANGS = ['en', 'es', 'pt']
```

`t()` and `_i18nWalk()` took `REASET_LANG === 'es' ? 1 : 0` — a **boolean**, which
is what limited the table to two languages. Both now take `_langIndex(lang)`, and
an unknown language reads as English rather than as `undefined`.

The design property worth preserving is that **every column is a lookup key**, not
just English. That is what lets translation work with no markup annotations at all
and makes re-running the walk idempotent. A third column had to keep it: a Spanish
node must still be findable when the user picks Portuguese, and a Portuguese node
when they pick English. A per-language dictionary keyed on English would only
translate in one direction, and switching twice would strand half the screen in
whatever language it last landed in.

`I18N_MAP` registers all three cells per row, **first writer wins** — where two
rows would share a translation, the earlier row keeps the key rather than a later
one silently stealing it. A test asserts no such collision exists at all, because
a cell owned by two rows cannot be translated deterministically.

Empty cells fall back to English. A row added without its translation should
degrade to a readable string, not an invisible one.

Browser detection gained `/^pt/i` and the switcher a third segment.

### The strings that never reached the table

Eleven dialogs held their text inline, in Spanish, so they rendered Spanish on an
English or Portuguese device: the Director PIN prompt and its four outcomes, the
Pull confirmation, the MIDI-mappings clear, the device rename, the reorder prompt,
and the new-setlist prompt. All now go through `t()` with an English source string
and a row.

The mode-selector card — **the first screen a new device ever sees** — was
Spanish-only in the markup regardless of the setting. It was already rewritten in
English by `a03c61e`; §16 adds its rows.

### The part that keeps it from decaying

Nothing *fails* when a string bypasses the table. It renders, it is readable to
whoever wrote it, and only a user in the other language sees the seam — which is
how a phone set to English showed

> ⚠ El dispositivo "Mac · Chrome" **is now the Director — this device is read-only**

one sentence in two languages. A reviewer will not reliably catch that. Four tests
do:

- `test_i18n_table_is_complete_and_unambiguous` — three full columns, no empty
  cells, and no cell owned by two rows.
- `test_every_language_is_reachable` — both readers index by language rather than
  branching on Spanish, every language in the table has a switcher button, and a
  pt-BR browser is detected.
- `test_no_dialog_bypasses_the_translation_table` — **this is the one that stops
  the next feature from reintroducing the bug.** Any `prompt`/`confirm`/`alert`
  whose first argument is a multi-word string literal fails the build.
- `test_markup_prose_is_in_the_table` — pins the mode selector's prose
  specifically, since that is the surface that actually went wrong.

Eight mutations were run and all eight were caught: `t()` and the walk reverted to
a boolean, pt dropped from browser detection, the PT button removed, a row left
with an empty pt cell, two rows given the same translation, a dialog put back
inline, and mode-selector prose moved out of the table.

### Four rows deleted

The `Stop Hold (3s)` help body, `■ STOP (Hold)`, `Mode: Hold` and `STOP (Hold)`
went with the hold gesture in `402b84d`. Translating strings nothing renders is
how a table grows to a size nobody wants to maintain.

### The judgement call

The owner chose to keep the table **inline**. ReaSet ships as a single file
dropped into `reaper_www_root`, `Sortable.min.js` being separate is already a
documented install step that has to be got right, and this session alone
contained two "did you update the file?" incidents. A third file to keep in sync
is another chance to run something old on a stage — and it fails silently, which
is the worst property a translation can have.

### Still requires a real-device test

Set a phone to pt-BR and open ReaSet: every screen, every dialog, every banner,
and no sentence mixing two languages. Switch language at runtime and confirm
what is already on screen follows — the DOM walk does this, so anything that
does not follow is a string still outside the table.

---

## 17. Instance identity: the same song, twice in one set

Issue #13, first half. Membership and the `+` picker are still to come; this is
the foundation they need, and it is the part that touches transport.

### The problem is identity, not UI

Two instances of a song occupy the **identical time range in REAPER**. So the
test every scan in this file used —

```js
if (currentPos >= r.start && currentPos < r.end) { activeIdx = j; break; }
```

— matches **both** rows, and `break` takes the earlier one. Nine scans did this.

The wrong row highlighting is the cosmetic half. The dangerous half is
`findNextValidSong(activeIdx)`: playing instance #2 advanced from instance #1's
index, so the show jumped to whatever follows the *earlier* copy. A repeat near
the top of the set would send the band back to song 2 in the middle of the
encore — and nothing would look broken until it happened.

### Two ids, and a rule about which is which

```text
r.id    which REAPER region this is      — shared by repeats
r.uid   which ENTRY in tonight's list    — unique per row
```

| Keyed on the **row** (uid) | Keyed on the **song** (region id) |
|---|---|
| every DOM id: `row-`, `bg-`, `dur-`, `chev-`, `slist-`, `loop-counter-`, `_ctx_*` | `getOverride` / `setSongOverride` |
| `expandedSongs` | stop / wait / colour / description |
| `chain`, `loop`, `skipped` | `g_subRegionMap` (already keyed by song *name*) |
| `selectedRegion`, `queuedRegion`, `_playIntent`, `lastActiveID` | |
| `data-uid`, and the order Sortable rebuilds from it | |

The split is a judgement, stated once so it is not re-derived at each call site:
*"play this one twice, and loop it the second time"* is the whole reason repeats
exist, so `loop` is per-row — while stop/wait/colour describe the **song**, and a
repeat is the same song, so both rows must agree. Per-instance overrides may be a
reasonable feature one day; they should be a decision, not a side effect of an
identity refactor, and a test asserts they have not become one by accident.

DOM ids are not merely *ambiguous* if keyed on the region — two elements would
carry the same `id` attribute, and `getElementById` returns the first. The
progress fill, the countdown, the active highlight and the loop badge would all
paint the earlier row while the later one played, silently, with no error
anywhere.

Sections belong to a song by **name**, so two instances share one section list.
Their rows are scoped as `_subUid(parent, sub)` = `<parentUid>.<subId>`.

### Resolving which instance is playing

`currentPos` cannot answer it — not "does not currently", *cannot*, because the
two rows are indistinguishable to the transport. So it is not asked to. This is
the observed-vs-intent split #3/#4/#9 already built, and repeats make the
evidence strictly weaker while leaving the decision exactly as good.

`activeInstanceIdx()` consults `_activeUidHint`, set wherever playback is
**commanded** to a specific row: Play from a selection, a cue, a queued song
consumed at a boundary, an auto-chain, a wait-resume. It is cleared on a manual
Stop and dropped automatically when the transport leaves the hinted row.

It deliberately does **not** `break` at the first match — the hinted instance may
be the later one, and stopping early is precisely the bug. With no hint it
returns the first match, which is the best answer available when playback started
from REAPER or the cursor was dragged by hand; that is documented as a fallback
rather than left to look arbitrary.

`findNextValidSong` / `findPrevValidSong` needed no change at all: they were
already index-based, and every fragility was upstream in the nine scans.

### Three places that silently collapsed duplicates

- **`syncRegions()`** used `delete mainMap[id]` as the "already placed" mark.
  That idiom cannot represent a repeat *at all*: the second saved entry finds the
  key gone and is dropped without a trace. Consumption is tracked separately now.
  Rows are also built by `_makeInstance()` rather than pushing the shared map
  entry, because the same object at two indices means one row's Loop toggles the
  other's.
- **`Sortable.onEnd`** rebuilt the order from `data-id` with a first-match scan.
  Both rows carry the same `data-id`, so dragging either would have collapsed the
  pair into one entry on the next save. It reads `data-uid` now.
- **`_syncApplyPayload`** bound two payload entries to the same local object and
  pushed it in twice. A follower now *builds* a row per entry and adopts the
  Director's uid verbatim, so both devices key their DOM off the same value.

### The numeric reorder prompt is gone

It was a second reorder path bound to the song's index number, and the only one
that raised a native `prompt()` — a modal asking a musician to type a position,
on a phone, during a show. Dragging by the handle is the feature and has worked
all along.

### Persistence is unchanged

`setlists[name]` still stores `{id, chain, skipped, loop}`. Uids are handed out
at build time and are stable for the life of the page only; nothing durable is
keyed on one. An old setlist therefore loads unchanged, which is acceptance test
7 satisfied by construction rather than by a migration.

### A defect found in the test helper itself

`strip_comments()` — which most static assertions in `tests/test_reaset_html.py`
are built on — did not understand **regex literals**. ReaSet contains

```js
subOv.description.replace(/"/g, '&quot;')
```

and the `"` inside that regex opened a string literal that never closed. Every
one of the ~210,000 characters after it came back **unstripped**, so any
assertion of the form `"X" not in strip_comments(body)` could be satisfied — or
defeated — by prose in a comment, anywhere past that point.

It surfaced only because a new test looked for a function that had been deleted
and found the comment explaining the deletion. It had been quietly weakening
assertions before that. The scan now handles regex literals, and
`test_strip_comments_survives_a_regex_containing_a_quote` guards the helper the
other tests depend on.

### Locked by tests

`test_no_scan_resolves_the_active_row_positionally`,
`test_dom_ids_key_off_the_instance`, `test_overrides_stay_keyed_on_the_song`,
`test_the_numeric_reorder_prompt_is_gone`, `test_every_row_is_its_own_object`,
and `test_auto_advance_follows_the_playing_instance` — the last **executes** the
real `activeInstanceIdx()` and `findNextValidSong()` against a list holding the
same song at index 0 and index 2, and asserts that playing the second copy
advances to what follows the *second* copy. That is acceptance test 10, and it is
the case that would have caught the old behaviour.

Nine mutations were run and all nine caught, including two that initially passed
and forced better tests: pushing the shared map entry instead of a constructed
row, and a constructor that returns its source.

### Still to do on #13

Membership as its own concept (show mode listing only the set), the `+` picker,
`✕` removing rather than skipping, and the roles guard on those new paths.

### Still requires a real-device test

Everything here. Acceptance tests 8–15 of #13 need REAPER, and 12 (playback
started outside ReaSet must not flicker the highlight between two instances)
cannot be reasoned about from here at all.

---

## 18. Membership: the setlist becomes a repertoire

Issue #13, second half. §17 built the identity this needs.

### Exclusion had no way to be said

`displayList` held every region in the project, and exclusion was expressed as
`skipped: true` — which means *"in the list, greyed out"*. That is a different
statement from *"not in the list"*, and there was no way to make the second one.

Now:

| | means |
|---|---|
| **skip** | in the set, greyed out, not played tonight |
| **remove** | not in the set at all — still in the REAPER project, reachable from the `+` picker |

They live in different modes, for the same reason the drag handle does: skip is a
*performance* decision a Director makes during a show; remove is *structural
authoring*. Edit mode already hid `.song-actions` and revealed the drag handle,
so the remove button belongs on that side and the ✕ in show mode still means skip.

### Membership needs no new storage

An entry's **presence** in `setlists[name]` is its membership — which is exactly
the format already on disk. `displayList` is the set, in order; `g_offSetlist`
holds everything else in the project and is read *only* by the picker. Nothing
about playback may walk it, and a test enforces that: transport, auto-advance and
the block grouping all iterate `displayList`, so a song nobody added being in it
means the show can chain into it.

The refresh branch of `syncRegions()` is where that matters most — it runs about
once a second for the life of the page, so a leak there would quietly re-absorb
the whole project.

### One deliberate exception

**An empty setlist absorbs the whole project on its first build.** Without it,
opening ReaSet on a new project would show an empty list and a picker —
technically correct and a terrible first thirty seconds. Once a set has any entry
at all it is curated, and a region added in REAPER later appears in the picker
rather than silently joining the show.

This also makes migration a non-event: every existing setlist already contains
everything, so it loads exactly as before. Acceptance test 7 by construction.

### Known limitation, stated rather than hidden

Emptying a setlist completely and then reloading brings the whole project back,
because an empty set is indistinguishable from a new one **in this storage
format** — and the epic's constraint is not to change that format without a fix
requiring it. Distinguishing them needs either a per-setlist "curated" flag (a
format change) or a device-local marker (which a second device would not see, so
two devices would disagree about the same set).

Removing every song from a set is a rare deliberate act, and the recovery — it
comes back — is benign next to the alternative of a blank first run. If it turns
out to matter, the fix is a format change and should be taken as one.

### The picker allows repeats

It lists what the project has and the set does not, then every song already in
the set, tagged **AGAIN**. That second group is the point: a song can legitimately
be played twice in one show, which AbleSet does not allow and #13 requires.

Adding appends. Position is then a drag, which is the gesture the list already
teaches — a second "insert at index N" affordance would be the numeric reorder
prompt growing back under a different name.

Removing one instance of a repeat leaves the song in the set, one row lighter; it
returns to the picker only when its **last** instance goes. Removal also clears
any selection, queue entry or active-instance hint pointing at that row, since
intent aimed at a row that no longer exists is a cue nobody can see.

### Roles

`removeFromSetlist()`, `addSongToSetlist()` and `openAddSongPicker()` each check
`canEditSetlist()` at the function, not only in CSS — #13 acceptance test 16. The
add row is additionally rendered only for a Director and CSS-hidden outside edit
mode, but neither of those is what stops a write.

### Locked by tests

`test_off_setlist_songs_never_reach_playback`, `test_remove_is_not_skip`, and
`test_membership_actions` — the last **executes** the real `addSongToSetlist()`
and `removeFromSetlist()` and covers the repeat in both directions: adding a song
already in the set, and removing one instance of a repeat without the song
leaving.

Eight mutations run, eight caught. One initially passed and forced a much better
test: re-appending off-setlist regions in the refresh branch was invisible to an
assertion that only checked `g_offSetlist` was mentioned *somewhere* in
`syncRegions()`. The test now asserts the refresh branch contains no
`displayList.push` at all.

### Still requires a real-device test

#13's acceptance tests 1–6 and 8–15. In particular 6 (add/remove/reorder reach
followers) and 14 (a follower renders both instances in the right order) are
multi-device and cannot be reasoned about here.

---

## 19. What the identity refactor broke, and how it was found

§17 moved every song DOM id onto a uid and scoped every section id by its
parent row. An audit of the four subsystems that read those — Live View,
Canvas, the lyrics/chords panels, and the per-section loop — found **five**
defects. Three of them affected **every setlist**, not only repeats, and all
three failed silently.

Worth recording as a process point: the automated suite was green throughout.
These are not the kind of defect a static assertion finds unless somebody first
asks "what else reads this?" — the tests were locking the *new* contract, and
these were places the old contract survived untouched.

### The three that hit everyone

**Auto-expand was dead.** The guard read `expandedSongs[activeRegion.uid]`
while the call wrote `toggleExpand(activeRegion.id, ...)`. The key was
therefore never set, so it re-fired on every song change, and `toggleExpand`
looked up `slist-` / `chev-` / `row-` ids built from a region id — none of
which are rendered. Unlike the other row actions, `toggleExpand` has no
region-id fallback, so nothing rescued it.

**Tapping a section painted no highlight.** A section's uid is scoped as
`<parentUid>__<subId>`, which no `displayList` row carries, so
`_resolveTapTarget` missed and fell through to the raw `g_subRegionMap` object
— which has no uid at all. Two things then broke at once: `_rowElFor` looked
for `subrow-<bareSubId>` and found nothing, and `noteActiveInstance` was handed
a bare sub id that `activeInstanceIdx()` can never match, so the hint was
dropped as stale on the next tick.

**`flashRow` threw on every call.** `_newUid` produced `12#3`, and while
`getElementById("row-12#3")` is fine, `querySelector("#row-12#3 .load-btn")` is
an **invalid selector** — `#` opens a new id token — so it raised
`SyntaxError` on every Next / Previous and every MIDI navigation.

That last one is the instructive one. The uid was fine everywhere it was used
with `getElementById`, and broken in the single place a selector was built from
it. **The separators are now `_` and `__`**, chosen so a uid is always a valid
CSS identifier, and a test asserts it — because fixing only `flashRow` would
have left the next selector to rediscover the same bug.

### The two that need a repeat

**"▶ Play Song" dropped the row.** The expanded-controls button called
`playRegion(start, id)` without the uid, so pressing it inside the second
instance cued the first — and then hinted the wrong row, which is the half that
makes the show jump.

**`SONG END` / `STOP` was suppressed on an adjacent repeat.**
`_lastSpecialTriggerPos` is keyed on an **absolute position**, and two
instances of one song occupy identical positions. In a set containing `A, A`
the marker fired for the first copy and was then suppressed forever for the
second, which ran straight past it. It is now reset on a section change,
alongside the two dedup flags that already were.

### One more, tightened while there

`_prevActiveSubId` held a bare sub id. A song whose sections cover it end to
end with a **single** section re-enters the same id when playback crosses from
one instance to the next, so `loopCount` and `_loopExhausted` never reset and
the second copy started with the first's spent loop. It is now scoped by the
parent row.

### What was checked and is genuinely fine

- **Live View's section map** writes `seg.dataset.subid` and reads it back
  against the same bare id, inside a container it rebuilds itself. These are
  `data-*` attributes on freshly created nodes, not global DOM ids — there is
  no collision to have. Its `_lrmLastSongId` cache keys on the region id
  *deliberately*: segment geometry is identical for two instances, so keying on
  the uid would force a rebuild producing a byte-identical track.
- **Canvas** uses only static element ids from markup and inherits `activeIdx`
  and `activeSub` from `updatePlaybackUI`, so it names the correct instance's
  successor for free.
- **Lyrics and chords** build no DOM id from a region or sub id, and cache on
  text content rather than identity. The one identity-dependent thing they do —
  `findNextValidSong(_lyActiveIdx)` for the "next song" label — is a case the
  refactor *fixes*.
- **The loop counter badges** round-trip correctly: written scoped, stored
  scoped in `_loopCounterSongId` / `_loopCounterSubId`, read back verbatim.

### Two pre-existing gaps, not caused by this work

`window.subStates` — where a manually toggled section loop or skip lives — is
neither **persisted** nor **synced**. Toggling a section loop on the Director
does not reach a Controller, and does not survive a reload.

Marker-driven loop (`+LOOP`, `+LOOPFULL`, `+LOOP:N`) has neither problem,
because every device parses the marker names out of REAPER itself. That makes
the marker the robust path and the button a rehearsal tool, which is worth
saying out loud in the docs rather than leaving users to discover.

### Locked by tests

`test_uids_are_valid_css_identifiers`, `test_no_selector_is_built_from_a_uid`,
`test_auto_expand_reads_and_writes_the_same_key`,
`test_section_tap_carries_both_identities`,
`test_position_keyed_dedups_reset_on_section_change`,
`test_every_row_control_passes_the_row`, and `test_section_tap_resolution` —
the last **executes** the real `_resolveTapTarget` against a section of a
repeated song and asserts both identities come back: the section row for the
highlight, the parent row for the hint.

Ten mutations run, ten caught. One initially passed and forced a scoped
assertion: reverting the section-change key to a bare sub id was invisible to a
file-wide search for `_subUid(activeRegion, activeSub)`, since that call also
appears where the section DOM ids are built.

### Still requires a real-device test

**L01–L18** in `docs/STAGE_TEST_MATRIX.md`. L01, L02 and L03 are the three
regressions above and are cheap to check first.
