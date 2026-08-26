# ReaSet — Stage Test Matrix

Companion to [#10](https://github.com/OvictorVieira/ReaSet/issues/10) and the
epic [#2](https://github.com/OvictorVieira/ReaSet/issues/2).

ReaSet controls stage playback. Passing static review is not enough: none of
the behaviour in this epic can be verified without a real REAPER, a real Mac
and a real phone, because `wwr_req` is injected by REAPER's own web server and
is stubbed to a no-op anywhere else. **Every test below is a manual test.**

Print this, or copy it per session, and fill the Result column.

---

## 1. Environment

Record before the run. A failure report without this section cannot be acted on.

| Field | Value |
|---|---|
| REAPER version | |
| SWS version | |
| ReaSet commit SHA | |
| `Reaset.lua` version / SHA | |
| macOS / OS version | |
| Mac model + architecture (Intel / Apple Silicon) | |
| Browser + version (Director) | |
| Phone model + OS | |
| Browser (phone) — Safari / Chrome / Home Screen app | |
| REAPER Web Remote port | |
| Network topology (router model, 2.4 / 5 GHz, mesh?) | |
| Project name + region count | |
| Date / tester | |

## 2. Prerequisites

1. REAPER open with a real show project — **not** a three-region test project.
   Race conditions at region boundaries only reproduce with contiguous regions.
2. `Reaset.lua` running (Actions → check it appears in the running-scripts
   list). Sidebar should show the bridge as connected.
3. Web Remote reachable from the phone on the same LAN.
4. Both devices on the **same** Wi-Fi band where possible; note it if not.
5. Open the Director with `?diag=transport` appended to the URL. Do the same on
   the phone for any test whose Result is FAIL, then re-run it.
6. Monitor audio — several tests are about what is *audible*, not what the UI
   shows.

### Reading the diagnostics

`?diag=transport` prints to the browser console and to an in-memory ring
buffer. Useful console commands:

```js
RSDiag.dump()    // print the whole buffer
RSDiag.save()    // download it as a .txt to attach to a bug report
RSDiag.clear()   // reset before starting a numbered test
```

A healthy explicit-selection sequence reads like this:

```text
14:31:02.102 USER_SELECT mode=director playing=0 pos=224.400 song=74 start=18798.2
14:31:02.105 SEND        mode=director playing=0 pos=224.400 cmd=SET/POS/18798.2 reason=user-cue
14:31:02.126 USER_PLAY   mode=director playing=0 pos=224.400 target=74 via=selected-region
14:31:02.127 SEND        mode=director playing=0 pos=224.400 cmd=1007 reason=user-play-selected
14:31:02.154 TRANSPORT   mode=director playing=1 pos=18798.2
```

Note `pos=224.400` on the USER_PLAY line: that is the **stale** position, and
the point of the test is that it did not decide anything.

---

## 3. Critical transport scenarios

Repeat counts are not optional. A race that reproduces one time in twenty is
still a ruined show.

| ID | Steps | Expected | Reps | Result | Notes |
|---|---|---|---|---|---|
| **T01** | Stop REAPER. Tap Song B. Wait 2 s. | Cursor at B start. **No playback.** B shown as selected/cued, visually distinct from playing. | 5 | | |
| **T02** | Stop. Tap Song D. Immediately tap Play (< 100 ms if possible). | D starts. No other song starts. **No brief audible start of song 1.** | **20** | | |
| **T03** | Stop. Tap Song C. Wait 5 s. Play. | C starts. | 3 | | |
| **T04** | Play A. Pause mid-song. Tap D. Wait 2 s. Play. | No playback after the tap; then D starts. A does not resume. | 5 | | |
| **T05** | Play A. Pause. Wait 5 s. | Stays paused. Cursor does not move. No automatic transition. | 5 | | |
| **T06** | Play A. Pause. Play. | Resumes from the paused position, not from A's start. | 5 | | |
| **T07** | Play A. Tap D mid-song. | A continues **uninterrupted**. D shown queued. Position stays inside A. No audible seek. | 10 | | |
| **T08** | Play A. Tap D. Tap E. | A uninterrupted. E is the **only** queued song; D's queued mark cleared. | 5 | | |
| **T09** | Play A. Rapidly tap D → E → C. | A uninterrupted. Final queue = C. No intermediate audible seek. | **20** | | |
| **T10** | Play A. Stop. Wait 5 s. | Stays stopped. No seek/restart from automatic logic. | 5 | | |
| **T11** | Play a song. Press Stop within the final ~500 ms of the region. | Stops. Does not advance. Does not briefly play the next song. No delayed cursor jump. | **20** | | |
| **T12** | Play A. Queue D. Stop before A ends. | Stops. D does not start later. Queue visibly cleared. | 10 | | |
| **T13** | Set a block end via Auto-Stop. Press Stop manually right at the boundary. | Final state is stopped and stable. | 10 | | |
| **T14** | Fast taps: Play → Pause → Play → Stop. | Final REAPER state matches the **last** explicit command, every time. | **20** | | |
| **T15** | A `continue` → B `continue` → C `stop`. Play A. | A→B→C run continuously. Stops after C. | 3 | | |
| **T16** | After T15 stops, select D, then Play. | D starts **only** on Play, never on the selection. | 3 | | |
| **T17** | A `continue`, queue D, let A end. | Transition to D at A's end (queued beats setlist order). | 5 | | |
| **T18** | A `stop`, queue D, let A end. | Playback **stops**. D does not audibly auto-start. D is ready as the manual next. | 5 | | |
| **T19** | Queue a song with skipped rows in between. | The explicit queued target wins. No skipped-row confusion. | 5 | | |
| **T20** | Tap the song that is currently playing. | Documented behaviour, applied consistently — no surprise restart. | 5 | | |
| **T21** | Stop with the cursor in a **gap** between regions. Play. | Follows the documented cursor rule. Does **not** jump to song 1. | 5 | | |
| **T22** | Stop. Refresh ReaSet. Press Play without selecting anything. | No unsafe arbitrary fallback. | 3 | | |

### Transport regression checklist

Tick each after the run. A regression here is as serious as a failed test.

- [ ] MIDI Init pre-roll still works, and **tapping a song does not audibly
      initialise plugins** (pre-roll belongs to Play, not to selection)
- [ ] Auto-Stop still stops sample-accurately where `Reaset.lua` arms it
- [ ] `+LOOP` / `+LOOPFULL` / `+LOOP:N` still loop, and loop counters count
- [ ] NativeLoop (REAPER Repeat) still engages and disengages
- [ ] `+PAUSE` markers still pause
- [ ] `>>>` section transitions still jump
- [ ] `SONG END` / `STOP` special markers still fire
- [ ] Per-song `stop after` / `wait N s` still behave
- [ ] Chain / Continue still advances
- [ ] Skip still skips, at both song and section level
- [ ] Stop Hold still requires the 3 s hold when enabled; tap mode is one-tap
- [ ] Live View transport matches the main transport
- [ ] Canvas transport matches the main transport
- [ ] Keyboard shortcuts (Space, Enter, arrows, R) match
- [ ] MIDI-mapped Play / Stop / Next / Prev match
- [ ] Lyrics and chords panels still follow playback
- [ ] Project switch / region refresh still re-namespaces state

---

## 4. Multi-device scenarios

**Two physical devices.** Two browser tabs on one machine share a clock, a
network path and a localStorage origin, and will pass tests that a phone fails.

| ID | Steps | Expected | Result | Notes |
|---|---|---|---|---|
| **S01** | Mac Director on Setlist A; phone shows A. Director switches to B. | Phone follows to B automatically, **≤ 1 s**, no manual pull. Record the measured latency. | | |
| **S02** | Switch A → B → C → A on the Director. | Phone follows each, in order, without sticking on an intermediate. | | |
| **S03** | Director on B. Refresh the phone browser. | Phone comes back **on B**, without a manual selection. | | |
| **S04** | Phone previously used A. Director is on C. Close and reopen the phone. | C wins. No silent stale A. | | |
| **S05** | Director on A. Turn phone Wi-Fi off. Director switches A → B. Turn Wi-Fi back on. | Phone adopts B. **No transport command is issued by the phone** on reconnect. | | |
| **S06** | Open a different REAPER project. | The old project's payload is not applied. | | |
| **S07** | Director switches to B, then reorders B. | Phone stays on B and receives the new order. | | |
| **S08** | Director switches A → B → C quickly. | Phone eventually shows C, not stuck on B. | | |
| **S09** | Mac is Director. Phone requests Director. | Second Director **denied by default**, with the current Director's device name shown. | | |
| **S10** | Close the Director browser. Wait the documented TTL. Phone requests Director. | Phone can acquire after the stale lease expires. | | |
| **S11** | With no Director active, request Director on both devices as close together as possible. Repeat ≥ 20×. | No stable dual-Director state, ever. | | |
| **S12** | Director active on Mac; perform an explicit takeover from the phone. | Phone gains authority; Mac detects the loss and can no longer control or edit as Director. | | |
| **S13** | Mac Director loses Wi-Fi; phone takes over after the timeout; Mac reconnects. | Mac does **not** automatically reclaim Director from its stored mode. | | |
| **S14** | Background the Director browser briefly, then foreground it. | No lease loss, no split brain. | | |
| **S15** | Background / foreground the phone browser. | UI recovers current state. **No phantom transport action.** | | |
| **S16** | Lock the phone briefly, unlock. | Reconnects safely. No stale seek. | | |
| **S17** | Disconnect only the phone's Wi-Fi during playback. | REAPER keeps playing. On reconnect the phone adopts REAPER's current state; **no backward jump**. | | |
| **S18** | Mac (Director) and phone (Controller), same show. Compare the session clocks. | Identical to within a second, with no manual reset on either. | | |
| **S19** | **Set the phone's system clock 8 minutes off the Mac's**, then repeat S18. | Still identical. **This is the case that distinguishes a correct implementation from the naive one** — if the clocks differ by ~8 minutes, an absolute timestamp is being put on the wire somewhere. | | |
| **S20** | Open a third device mid-show. | Adopts the running time within a few seconds; does not start from 0:00. | | |
| **S21** | Pull the phone's Wi-Fi mid-show. | Its clock keeps counting rather than freezing, and re-syncs to the Director's on reconnect. | | |
| **S22** | Long-press the clock on the **Director**. | Zeroes on every device within one poll (~2s). | | |
| **S23** | Long-press the clock on a **Controller**. | Nothing happens, and the cursor never suggested it would. | | |
| **S24** | Close the Director's laptop; another device takes the lease. | The show clock continues — it must NOT restart from the new Director's first Play. | | |
| **S25** | Play something, quit the browser, reopen **more than 4h later**. | Clock starts from 0:00, not from hours ago. This is the reported bug. | | |
| **S26** | Play something, quit the browser, reopen **within a few minutes**. | Clock resumes where it was — a refresh mid-rehearsal must not zero it. | | |
| **S27** | Open a different REAPER project. | Clock starts from 0:00 rather than inheriting the previous project's time. | | |

### Controller-role scenarios

| ID | Steps | Expected | Result | Notes |
|---|---|---|---|---|
| **C01** | Mac Director active. On the phone choose Controller. | Phone shows the same active setlist; transport controls present; edit controls absent. | | |
| **C02** | REAPER stopped. Controller taps Song C. | Cursor moves to C. No playback. Director shows a coherent selection. | | |
| **C03** | Controller presses Play. | The selected song starts — same determinism as T02. | | |
| **C04** | Song A playing. Controller taps D. | A continues; D queued. | | |
| **C05** | Controller Pause, then Stop. | Same authoritative semantics as T05 / T10. | | |
| **C06** | Attempt drag/reorder from the Controller. | Impossible via the UI **and** via the write path. | | |
| **C07** | Try every remaining control on the Controller. | No path reaches the shared-setlist publishing code. | | |
| **C08** | Director changes the active setlist. | Controller follows automatically (S01 path). | | |
| **C09** | Two Controllers open at once. | Both may control transport (documented policy). Neither becomes a Director. | | |
| **C10** | Refresh the Controller. | Stays Controller; reconnects; follows the current active setlist. | | |
| **C11** | *(retired with the Player role — see plan §13)* | — | | |
| **C12** | Fresh device (localStorage cleared), no Director anywhere: open ReaSet. | No modal. Opens as Controller with live transport, then becomes Director within ~6s. Badge reads DIRECTOR. | | |
| **C13** | Fresh device, a Director already beating on another device: open ReaSet. | No modal. Stays Controller. The incumbent keeps its lease and shows no conflict banner. | | |
| **C14** | Same as C13, but kill the incumbent (force-quit the browser, do not close cleanly), wait 15s, then reload the phone. | The phone becomes Director — the corpse in ExtState must not block it forever. | | |
| **C15** | Set a Director PIN, then open a fresh device with no Director running. | Stays Controller. It must NOT auto-claim past the PIN. Choosing Director from the badge prompts for it. | | |
| **C16** | Device that stored the retired `'player'` mode (set `localStorage.reaset_mode='player'`, reload). | Opens as Controller: transport works, setlist is read-only, badge reads CONTROLLER. | | |
| **C17** | Director device: pull its Wi-Fi so another device takes over, then restore. | Displaced device drops to Controller — transport still works, editing does not. Banner says it can no longer edit. | | |

---

## 5. Visual block scenarios

| ID | Setlist / action | Expected | Result | Notes |
|---|---|---|---|---|
| **V01** | A `continue`, B `continue`, C `stop`, D `continue`, E `stop`, F `stop` | A/B/C attached; gap; D/E attached; gap; F | | |
| **V02** | Change C from `stop` to `continue` | C→D gap disappears **immediately**, no refresh | | |
| **V03** | Change C back to `stop` | Gap reappears immediately | | |
| **V04** | Songs on `auto`; toggle global Auto-Stop ON then OFF | Grouping reflects the effective behaviour, live | | |
| **V05** | Set C to `wait` | D starts a new block | | |
| **V06** | A `continue`, B skipped, C `stop`, D `continue`; Hide Skips **ON** | No phantom or contradictory gap | | |
| **V07** | Same setlist, Hide Skips **OFF** | Skipped-row placement matches the documented rule | | |
| **V08** | Expand a song with several sections | **No** gaps between Verse / Chorus / Bridge; no gap inside the expanded card | | |
| **V09** | Drag a song into another block | Block classes recompute after the reorder | | |
| **V10** | iPhone, narrow viewport | Gaps aid scanning; no broken hitboxes; no excessive scrolling | | |
| **V11** | Grid view | Layout not broken by the block rule | | |
| **V12** | Each theme (dark / light / custom) | Gap and any divider read correctly in all | | |
| **V13** | Controller read views | Render correctly | | |

### Visual regression checklist

- [ ] Drag-and-drop reorder still works
- [ ] Touch scrolling stays smooth
- [ ] Row tap still works, and hits the right target
- [ ] `⋮` context menu still opens and its controls are clickable
- [ ] Active / selected / queued highlights unaffected
- [ ] Progress fills unaffected
- [ ] Expanded sections unaffected

---

## 6. Soak test

Run **after** the critical tests pass. Minimum rehearsal simulation:

1. Load the real show project.
2. Open the Director on the Mac and a Controller on the phone.
3. Run the full show setlist end to end.
4. Perform at least ten manual pauses, stops and manual block starts.
5. Background and foreground the phone at least five times; lock and unlock it.
6. Leave everything running **≥ 30 minutes** (60 preferred).

Pass criteria:

- [ ] No stuck transport
- [ ] No unexpected seek
- [ ] No setlist desync between devices
- [ ] No progressive UI slowdown that compromises use
- [ ] REAPER's own UI stays responsive with ReaSet open

Observations to record (subjective is fine, but be specific):

| Observation | Start | +15 min | +30 min | +60 min |
|---|---|---|---|---|
| Button → audible response latency | | | | |
| REAPER main UI responsiveness | | | | |
| CPU (REAPER / browser) if visible | | | | |
| Browser memory if visible | | | | |
| Anything that felt "off" | | | | |

---

## 7. Bug report template

Copy this per failure. A report without a diagnostic excerpt and a repro rate
usually cannot be fixed.

```md
### Failure

Commit:
Device:
Browser:
Song/region:
State before action:
Action:
Expected:
Actual:
Repro rate:            (e.g. 3/20)
Diagnostic log excerpt: (RSDiag.save(), or the console lines around the event)
Video/screen recording:
```

Attach the `RSDiag.save()` file whenever the failure is about **ordering** —
"it played the wrong song", "Stop didn't take", "the phone showed the old
setlist". The timeline is the evidence; a description of the symptom is not.

---

## 8. Rollback

Every behaviour landed as its own small commit, so one can be reverted without
taking the rest with it: `git revert <sha>`, newest first if you revert more
than one.

**Commits, not branch names.** The per-track branches were working refs and
were deleted once everything was merged. These SHAs are permanent, and a SHA is
what a revert actually takes.

| Behaviour | Issue | Commit(s) — revert newest first |
|---|---|---|
| Transport diagnostics (`?diag=transport`) | #10 | `aa1c070` |
| Deterministic selection and Play | #3 | `95aec18` |
| Queue a song tap while playing | #9 | `aeb40e9` |
| Authoritative Pause / Stop | #4 | `08df167` |
| Active named-setlist sync | #5 | `7ed53a3`, `0d7652d` |
| Single active Director | #6 | `fcfef7b`, `540be57`, `ebad0ea` |
| Controller / Performer role | #7 | `3620055`, `540be57`, `04c088a` |
| Visual playback blocks | #8 | `7ed53a3`, `5164488` |
| CI for `ReaSet.html` | #10 | `853741b`, `85a52b6` |

Two commits appear in two rows, so reverting one row can disturb the other:

- `7ed53a3` carries both the shared end-state (which #8 needs to draw the same
  blocks on a follower) and the chunk-integrity guard (#5). Reverting it for one
  takes the other with it.
- `540be57` sits between #6 and #7 — it forces edit mode off when a Director is
  downgraded, a case that only exists because both are present.

### The fast rollback is not a revert

Before a show, if anything in this matrix is unresolved, do not reason about
commits. Put the last known-good files back:

```bash
WEB=~/Library/Application\ Support/REAPER/reaper_www_root
SCR=~/Library/Application\ Support/REAPER/Scripts

git show 9a3c568:ReaSet.html > "$WEB/ReaSet.html"
git show 9a3c568:Reaset.lua  > "$SCR/Reaset.lua"
```

Then **restart the script in REAPER** — Actions → Show action list → Running
scripts → terminate `Reaset`, then run it again. Replacing the file does not
change the code already running in memory, and this is the step people skip.
Hard-reload the browser on every device afterwards (`Cmd+Shift+R`; on iOS,
clear Safari data or use a private tab).

Confirm the rollback took: the Director badge appears and the region list
populates. `9a3c568` is the last upstream state before this epic and is the
build documented in `docs/USER_GUIDE.md`.
