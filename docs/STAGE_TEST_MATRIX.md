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
| **T23** | Slide-to-Stop ON (default). Tap STOP once, quickly. | **Nothing happens.** This is the point of the control. | | |
| **T24** | Drag the STOP thumb all the way across and release. | Playback stops. Label reads SLIDE TO STOP, then RELEASE TO STOP once armed. | | |
| **T25** | Drag past the arm point, then drag **back** and release. | Playback does **not** stop — a slide is abandoned by changing your mind. | | |
| **T26** | On a phone, drag STOP with a slightly diagonal finger movement. | The thumb follows the finger; the page does not scroll and the gesture is not lost. | | |
| **T27** | Repeat T23–T25 in Live View and in Canvas. | Identical behaviour in all three. The three copies drifted apart once before. | | |
| **T28** | Turn Slide to Stop OFF in the sidebar. | STOP becomes a plain button acting on one press, everywhere, immediately. | | |
| **T29** | Device that stored the retired hold mode (`localStorage.reaset_stop_mode='hold'`, reload). | Comes back in slide mode — never a Stop button that responds to nothing. | | |
| **T30** | Look at RECONNECT next to Loop on the transport bar. | Two clearly different icons. RECONNECT is a plug; only Loop is ↻. | | |

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
| **C18** | Controller, phone. Look at the setlist row. | A read-only banner with the active set's name — no dropdown, no chevron. Dot pulses while REAPER plays. | | |
| **C19** | Controller: tap the setlist banner. | Nothing happens, and it never looked pressable. | | |
| **C20** | Director marks two songs as skipped, then look at the Controller. | The skipped songs are **absent** from the Controller's list, not greyed out. The Director still sees them. | | |
| **C21** | Switch a device from Controller to Director via the badge (and back). | The list repaints immediately — skipped songs appear/disappear on the spot, not on the next unrelated poll. | | |
| **C22** | Unplug REAPER's project (or stop `Reaset.lua`) while a Controller is open. | The banner turns amber and says the project is unreachable. | | |
| **E01** | Director, edit mode. Tap ✕ on a song. | It leaves the list. Show mode no longer lists it. It is still in REAPER. | | |
| **E02** | Tap **+ Add song**. | Picker lists the removed song, plus every song already in the set tagged AGAIN. | | |
| **E03** | Add a song from the picker. | Appended to the end of the list, playable, and gone from the picker. | | |
| **E04** | Add a song that is **already in the set**. | Two rows for it, each with its own Loop / Skip / end-state controls. | | |
| **E05** | Play the **first** copy of a repeated song and let it end. | Advances to what follows the FIRST copy. | | |
| **E06** | Play the **second** copy and let it end. | Advances to what follows the SECOND copy. **This is the case the old code got wrong.** | | |
| **E07** | While a repeat plays, watch the row highlight, the progress fill and the countdown. | All three land on the row that is actually playing, and none flicker to the other copy. | | |
| **E08** | Start playback from REAPER itself (not from ReaSet) inside a repeated song. | The FIRST copy highlights, and stays highlighted — no flicker between the two. This is the documented fallback. | | |
| **E09** | Set one copy of a repeat to Loop and the other not. | Only the looping copy loops. | | |
| **E10** | Set a per-song colour / note / end-state on one copy. | **Both** copies show it — those describe the song, not the row. | | |
| **E11** | Drag to reorder a list containing a repeat. | Both copies survive the drag in the positions you left them. Reload and check again — this is where a first-match scan used to collapse them. | | |
| **E12** | Remove ONE copy of a repeat. | The other stays. The song does **not** reappear in the picker. | | |
| **E13** | Remove the last copy. | It leaves the set and returns to the picker. | | |
| **E14** | Repeat E01–E04 while a phone is watching as Controller. | Every change reaches the phone, in order, with both copies of a repeat rendered. | | |
| **E15** | Controller, edit mode unavailable: try to reach add/remove. | No add row, no ✕, and nothing reaches REAPER even if a control is forced. | | |
| **E16** | Setlist saved **before** this change: open it. | Loads unchanged, same songs, same order. | | |
| **E17** | Add a new region in REAPER while a **curated** set is open. | It appears in the **picker**, not in the show. | | |
| **E18** | Open ReaSet on a brand-new project with no setlist. | The whole project is listed — the empty-set bootstrap. | | |
| **E19** | Remove **every** song, then reload. | Known limitation: the project comes back. See plan §18. | | |

### Loop, sections and the panels that read them

Three of these caught regressions from the identity refactor that affected
**every** setlist, not only repeats. They are cheap and worth running first.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **L01** | Play a song that has sections. | Its section list **auto-expands**. (This was dead: the guard read one key and the call wrote another.) | | |
| **L02** | Tap a section row while stopped. | The section row highlights as cued. (This painted nothing before the fix.) | | |
| **L03** | Press Next / Previous, or use MIDI next/prev song. | No `SyntaxError` in the console. (`flashRow` built an invalid CSS selector out of the uid and threw on every call.) | | |
| **L04** | Expand a song, press **▶ Play Song** inside it. | Cues that song. With a repeat, cues **the copy you pressed it in**. | | |
| **L05** | Name a marker `> Chorus +LOOP`. Play into it. | Loops the section forever. The label reads **Chorus** — the flag is stripped. Loop icon lit. | | |
| **L06** | With `+LOOP` running, queue another song. | The loop **releases** and the queued song plays. | | |
| **L07** | Name a marker `> Chorus +LOOPFULL`. Queue another song while it loops. | The loop **keeps priority**; the queued song waits. | | |
| **L08** | Name a marker `> Chorus +LOOP:4`. | Plays four times, shows a `2/4` counter on both the song and section rows, then moves on by itself. | | |
| **L09** | After an `+LOOP:4` finishes, play that song again. | It loops four times **again** — the count re-arms per pass. | | |
| **L10** | Same marker tests with `Reaset.lua` **stopped**. | Still loops, via a fallback seek. The seam may be audibly less tight — that is expected, note it. | | |
| **L11** | Put the same song in the set **twice**, with `+LOOP:2` on a section. Play the first copy through, then the second. | The second copy loops twice too. It must not inherit a spent count from the first. | | |
| **L12** | Set `A, A` back to back, with a `SONG END` or `STOP` marker in A. | The marker fires for **both** copies. (It fired only for the first — the dedup is keyed on absolute position, which both copies share.) | | |
| **L13** | Toggle a section's loop with the `↻` button, then reload the page. | The toggle is **lost**. Known: section state is memory-only. Use a marker if it must survive. | | |
| **L14** | Toggle a section's loop on the Director; watch a Controller. | The Controller does **not** see it. Known: section state is not in the sync payload. Marker-driven loop *does* reach it, because each device parses the marker itself. | | |
| **L15** | Live View, on a song with sections. | The section map draws, the active segment highlights, and a looping segment pulses. | | |
| **L16** | Canvas mode, during playback. | Song title, current section and "next" all track the transport. With a repeat, "next" names what follows **the copy that is playing**. | | |
| **L17** | Lyrics and Chords panels during playback. | Both follow. The "next song" label under the lyrics names what follows the **playing** instance. | | |
| **L18** | Expand a song, open a section's `⋮` menu, set a note and a colour. | Applies. With a repeat, **both** copies show it — sections belong to the song. | | |

### What happens when a song ends

The three the show depends on. Run them with audio, not just eyes on the screen.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **B01** | Song marked **Emendar** (chain). Let it end. | Rolls straight into the next song, **no audible gap**. | | |
| **B02** | Auto-Stop **off** globally, song on Auto. Let it end. | Same — plays on into the next. | | |
| **B03** | Auto-Stop **on** globally, song on Auto. Let it end. | **Stops.** Cursor lands on the next song, so one Play starts it. | | |
| **B04** | Song marked **Parar**, Auto-Stop off. Let it end. | Stops anyway — the per-song setting beats the global one. | | |
| **B05** | While a song is playing, tap another. Let the current one end. Current song set to **continue**. | The tapped song plays **instead of** the natural next. | | |
| **B06** | Same, but the current song is set to **Parar** (or Auto-Stop is on). | It **stops**. The tapped song becomes what the next Play starts — the queue does not override a stop. This is deliberate: see plan §20. | | |
| **B07** | Song set to **Esperar 5s**. Let it end. | Stops, waits about five seconds, then resumes into the next song by itself. | | |
| **B08** | Song set to **Esperar 5s**, and you tap another song mid-play. | After the wait it resumes into **the tapped song**, not the natural next. | | |
| **B09** | Let the **last** song of the setlist end. | Stops cleanly. No seek to song 1, no error. | | |
| **B10** | Tap a song and press Play, then immediately let the previous region's end tick arrive. | The song you started keeps playing — a stale end-of-region reply must not stop it. | | |
| **B11** | Repeat B01–B06 with `?diag=transport` open. | Each boundary logs one `BOUNDARY` line naming the action taken. If something surprises you, that line says which of the seven branches ran. | | |

### The Director lease, and the connection button

**D01–D03 are the bug reported from the desktop**: it was marked Controller with
nobody else in the room, and the banner named a takeover that never happened.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **D01** | Desktop as Director, **no other device open at all**. Reload it several times. | Stays **DIRECTOR** every time. No banner. It must not stand down with nobody to stand down to. | | |
| **D02** | Same, but with REAPER visibly busy (big project, heavy plugins). Reload a few more times. | Still DIRECTOR. This is where the old code failed — the claim read-back missed a 2.6s deadline and the device concluded it had lost its own claim. | | |
| **D03** | Force the banner (open a second device and take Director from it). Read the banner text. | Names the device that actually took over. It must never say "another device" when there is none. | | |
| **D04** | While the banner is up, look at the setlist row. | The active setlist's **name is still visible** — the banner makes room instead of covering it. | | |
| **D05** | Same, in Live View / Canvas / Lyrics. | Content starts below the banner, not under it. | | |
| **D06** | Banner up on a **phone**, in Portuguese and in English. | Wraps to two lines if needed and still pushes content down by its real height. | | |
| **D07** | Normal operation, REAPER answering. | RECONNECT is **green, disabled, quiet** — a status light. Pressing it does nothing. | | |
| **D07b** | **Hover over it, and press it, while connected.** | It does not light up, does not change colour, does not shrink, and the cursor stays an arrow. `disabled` blocks the click; the styling has to agree, or it still reads as pressable. | | |
| **D08** | Quit REAPER, or pull the network. | Within ~2s it turns **red, swaps to a broken-plug icon, and pulses**. | | |
| **D09** | With it red, press it. | Reconnects. Once replies flow again it goes back to green and disabled by itself. | | |
| **D10** | Repeat D08 with the OS set to "reduce motion". | Still red, still the broken plug — just not pulsing. The state must not depend on the animation. | | |

### View tabs

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **W01** | Open LYRICS, then CHORDS, then CANVAS, then LIVE, in that order. | After **each** tap exactly **one** tab is lit — the view you are actually looking at. This sequence lit three at once. | | |
| **W02** | With a view open, tap the **same** tab again. | It closes and SHOW lights up. | | |
| **W03** | Close a view with its own ✕ / Exit button instead of the tab. | SHOW lights up. | | |
| **W04** | Use the keyboard shortcuts (L, C, V, N) in a run. | Same invariant — one lit tab, one open view. | | |
| **W05** | Open CANVAS, then press Escape. | Back to SHOW, one tab lit, and no invisible view left open behind it. | | |

### Session clock

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **K01** | Play something. Quit REAPER. Reopen it and ReaSet. | Clock at **0:00**. This is the reported bug — it read six hours. | | |
| **K02** | Same, but close the **browser** too before reopening. | Still 0:00. This is the case the in-memory signal alone could not catch. | | |
| **K03** | Same again with a phone also open as Controller. | **Both** devices at 0:00. | | |
| **K04** | Play, then leave everything running and untouched for a while. | Keeps counting. A quiet stretch mid-rehearsal is not a new session. | | |
| **K05** | Stop `Reaset.lua` from the Actions list, leave REAPER open. | Clock does **not** reset — the script being absent is not a restart. | | |
| **K06** | Open a different REAPER project. | Clock at 0:00. | | |
| **K07** | Long-press the clock on the Director. | Zeroes on every device. On a Controller the long-press still does nothing. | | |

### The transport bar

**Previous · Play/Pause · Loop · Next.** Stop is gone: pause is what a musician
reaches for when a show has to hold, and it holds the position, the queue and
the cue where Stop discarded all three and rewound. Two controls that both halt
playback, differing in what they silently throw away, is one more thing to get
wrong in the dark. RECONNECT is gone from the bar too — it is a status, not a
transport control, so it now appears only when the link drops.

`smartStop()` stays. Auto-Stop, a stop-after marker and the Enter key all still
stop the transport; what went is the button.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **P01** | Open ReaSet and look at the bar. | Four controls: ⏮, a large green PLAY, LOOP, ⏭. Nothing else. | | |
| **P02** | Stand back and glance without reading. | The green PLAY is what your eye lands on. | | |
| **P03** | Look at the LOOP button. | A circular arrow plus the word LOOP. | | |
| **P04** | Press PLAY, then look again. | PLAY became ▮▮ and did **not** change width. | | |
| **P05** | Playing a song, past its opening. Press ⏮. | **Restarts the song you are on** — it does not step back. That is the press a musician means most of the time. | | |
| **P06** | Within the first two seconds of a song, press ⏮. | Goes to the **previous** song. | | |
| **P07** | Press ⏭ mid-song. | Jumps to the next song. Skipped songs are passed over. | | |
| **P08** | Repeat P05–P07 from Live View and from Canvas. | Identical. All three go through one function now. | | |
| **P09** | Rotate the phone to landscape. | Bar shrinks, all four still at least 44px tall, setlist still readable. | | |
| **P10** | Language in Português, repeat P01. | Nothing clipped. | | |

### Losing the connection

The bar no longer carries a reconnect button. The notice **is** the affordance.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **N01** | Everything connected. Look at the top of the screen. | **No** connection notice at all, and no reconnect button on the bar. | | |
| **N02** | Quit REAPER (or stop its web server) with ReaSet open. | Within ~2s an orange notice appears saying REAPER is not answering. | | |
| **N03** | Tap that notice. | It says "Reconnecting…" and polling restarts. | | |
| **N04** | Bring REAPER back. | The notice disappears on its own. | | |
| **N05** | Same as N02 but pull the **wifi** instead. | Same notice. Both failures look the same to a musician, and should. | | |
| **N06** | With the notice showing, check the sidebar. | The Reconnect action is still there — the notice is not the only way back. | | |

### The iPad that no longer updates

Chrome on iOS is the system WebKit with a different icon, so the engine is
whatever the last iOS for that device shipped — installing another browser
changes nothing. None of what these cases look for is a crash: the engine
drops the declaration it cannot read and renders something plausible-but-wrong,
which is exactly why it has to be looked at rather than reasoned about.

**Do this on the iPad mini, in whatever browser is on it.**

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **V01** | Open ReaSet and look at the transport bar. | Space between every control. If PLAY, LOOP and the plug are touching, the flex-gap fallback did not engage. | | |
| **V02** | Drag the STOP thumb. | It moves, and the page behind it does **not** scroll. This is the case with no Pointer Events at all — if Stop is dead here, nothing else in this section matters. | | |
| **V03** | Same drag, but wobble vertically on the way. | The thumb keeps following. The gesture must not be handed to the scroller. | | |
| **V04** | Open the sidebar, then a modal (rename a setlist, say). | The dark backdrop covers the **whole screen**, not a small rectangle in the top-left corner. | | |
| **V05** | Open Live View. | The song title is large — stage-readable, not body text. | | |
| **V06** | Open Canvas. | Same: the widget text is sized for a stage. | | |
| **V07** | Open a song's colour palette. | The swatches are round and evenly spaced, not collapsed to zero height. | | |
| **V08** | Scroll the setlist, tap a song, press PLAY. | Everything responds. Any dead control here is a JS error — check whether the console is reachable, and if not, report which control. | | |
| **V09** | Rotate the iPad. | Both rows re-lay-out, nothing overlaps the setlist. | | |
| **V10** | Run the whole of §3 (transport) on the iPad. | Identical outcomes to the Mac. This is the point of the exercise. | | |

---

### How a row says what it is

A 2px ring around the playing card was the loudest thing on the screen, and
`.cued` stacked on `.active` drew it twice on the row that least needed one.
Every state is a **surface** now — what the row is, not a box drawn round it —
and the fill growing across it is the marker.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **R01** | Play a song and watch its row. | The row is green and the fill **grows across it**. No ring, no border, no bar down the edge. | | |
| **R02** | Same row, look at the boundary between filled and unfilled. | It reads as a **position** in a green row, not as a green block sitting on a grey card. | | |
| **R03** | Stopped, tap a song. | Its row goes green and **quieter** — no fill. That is "Play starts here". | | |
| **R04** | Tap the song that is already playing. | It stays exactly as it was. Playing beats cued; nothing new appears. | | |
| **R05** | Playing, tap a different song. | That row goes **amber**, same treatment. That is "this is next". | | |
| **R06** | Look at every row that is not playing, at the very left edge. | **No green sliver.** The playhead used to be a border, so it sat at x=0 on every idle row. | | |
| **R07** | Take a song with a looping **section** and look at its row. | A purple bracket sits where that section is inside the song — a third of the way in for a section a third of the way in. | | |
| **R08** | Same, but a song with **the whole song** looping. | A purple wash across the row, **no bracket**. A border there just traces the card. | | |
| **R09** | Play into a looping section and watch. | The fill passes through the bracket. The bracket does not move. | | |

### The loop button, and who may press it

Loop is an **edit** — it changes what REAPER plays and it is published — so
`toggleCurrentLoop()` has always refused on a Controller. The button did not
know that: it lit from the *Director's* song, did nothing when tapped, and
could never be turned off. From a phone that is indistinguishable from "the
loop button is stuck on".

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **Y01** | On the **Director**, play a song and press LOOP. | It lights. The row shows the loop. Press again: it goes out. | | |
| **Y02** | On a **Controller**, look at LOOP while the Director has loop on. | Lit — the state is worth knowing everywhere — but visibly **not pressable**: no hover, no press, dimmed. | | |
| **Y03** | On a Controller, press LOOP. | Nothing happens, and nothing pretends to. It must not look stuck. | | |
| **Y04** | On a Controller, hover or long-press LOOP. | "Only the Director can change the loop". | | |
| **Y05** | Director turns loop off; watch the Controller. | Its LOOP goes out within a poll. | | |
| **Y06** | A song with **no sections**, loop on. Look at its row. | A **bracket** end to end — `[` and `]` facing each other across the row. Not a tint: a tint only reads to someone who already knows what purple means. | | |
| **Y07** | A song **with** a looping section, loop on for the song too. | Two brackets: one spanning the row, one at the section's own position. | | |
| **Y11** | Expand a song whose section loops. | That **section's own row** is bracketed edge to edge. The song row says where; the section row says this is it. | | |
| **Y12** | A song whose **first** section loops. And one whose **last** does. | The bracket arm keeps clear of the card's border — it does not draw on top of it. Intro and outro are the two that land on the edge. | | |
| **Y13** | A song with **one** section, and it loops. | Both ends clear at once. | | |
| **Y08** | Set the language to Português and repeat Y04. | "Só o Diretor pode mudar o loop". | | |

### Colouring songs and blocks

The Director picks a colour; it is written to the **region in REAPER**, and
every device gets it from its own REGION poll. Nothing is stored per device,
so nothing can disagree.

**This needs the new `Reaset.lua` on the REAPER machine, with the script
restarted.** Without that the colour silently does nothing — the browser
writes an ExtState key that nobody is listening for. If Z01 does nothing at
all, check that before anything else.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **Z01** | As Director, press **EDIT**, open a song's `⋮` menu, turn colour on, pick a swatch. | The row takes the colour **immediately**. REAPER's timeline does **not** change yet — colour is staged like every other edit in this panel. | | |
| **Z02** | Now press **APPLY**, watching REAPER. | *Now* the region takes the colour. | | |
| **Z03** | Look at a phone that is watching the same setlist. | Within about a second, the same colour. Nobody had to import anything. | | |
| **Z2b** | Pick a colour and press **DISCARD** instead. | The row goes back, and REAPER was never touched. | | |
| **Z2c** | Pick a colour, press APPLY, and wait about six seconds without REAPER's script running. | It tells you REAPER did not confirm, and names the likely cause. Silence was the old failure: the write is swallowed with no error. | | |
| **Z03** | Save the REAPER project, close it, reopen. | The colour is still there. It belongs to the project now, not to a browser. | | |
| **Z04** | Tick **Apply to the whole block**, then pick a colour. | Every song in that block takes it — including the ones above the one you opened. | | |
| **Z4b** | Read the line under that switch **before** touching it. | It says how many songs the block holds, or that this song is a block on its own. A block is a run that plays **without stopping**: with Auto-Stop on and every song left on Auto, each song is its own block, and the switch correctly colours one. | | |
| **Z4c** | Pick a colour **first**, then turn the switch on. | The rest of the block takes it straight away. It used to be read only at the moment you tapped a swatch, so this order did nothing. | | |
| **Z4d** | Turn the switch back off. | The other songs go back to what they had; the one you opened keeps the colour. | | |
| **Z4e** | With the switch on, press **Remove colour**. | The whole block clears, not just the row you opened. | | |
| **Z4f** | Colour a song and look at the row next to an uncoloured one. | The colour is clearly the strongest thing on the row. It was painted at 0.10 alpha — weaker than the plain playing highlight at 0.13 — so a song you had deliberately marked read as less marked than one you had not. | | |
| **Z05** | Do Z04 from the **middle** of a block. | Still the whole block, not just the tail. | | |
| **Z06** | Press **Remove colour**. | The region goes back to REAPER's own default. Not black. | | |
| **Z07** | On a **Controller**, open a song menu. | No colour picker, or it refuses. This is an edit, and edits are the Director's. | | |
| **Z08** | Colour a song, then watch REAPER for a minute without touching anything. | The project does **not** keep marking itself dirty. The instruction is consumed once. | | |
| **Z09** | A song that appears **twice** in the set, inside one block. Colour the block. | It is written once, and both rows show it. | | |
| **Z10** | Colour a song, then change the region's colour in REAPER itself. | ReaSet follows REAPER. REAPER is the source. | | |

### Editing is a session, with two ways out

`EDIT` names the action. It used to display the mode you were in — "SHOW" —
which reads as a caption rather than a door, and the owner could not find the
way into editing at all. The `⋮` menu that holds loop, skip, end-state, note
and colour lives behind that button, so an unfindable button made all of it
unfindable.

Entering takes a snapshot. **Apply** keeps the work; **Discard** puts
everything back — including the region colours, which live in the REAPER
project and cannot be restored by putting local state back.

Edits still reach the other devices **as they are made**, not on Apply. That
is deliberate and unchanged: buffering them would make the Director's screen
disagree with what the room is following. So Discard is a restore, and the
followers see the set go back.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **X01** | Look at the top bar as Director, not editing. | One button, reading **EDIT**. No Apply, no Discard. | | |
| **X02** | Press it. | EDIT disappears; **DISCARD** and **APPLY** take its place. The `⋮` handles appear on the rows. | | |
| **X03** | Reorder two songs, then press **APPLY**. | The new order stays. The buttons go away and EDIT comes back. | | |
| **X04** | Reorder two songs, then press **DISCARD**. | The old order comes back. | | |
| **X05** | Turn a loop on, mark a song skipped, write a note — then **DISCARD**. | All three go back. They are stored three different ways, so this is three tests in one. | | |
| **X06** | Colour a song, then **DISCARD**, watching REAPER's timeline. | The region goes back to the colour it had. Not black, not the new colour. | | |
| **X07** | Colour a song **twice** (two different swatches), then **DISCARD**. | It returns to the colour it had before you started — not to the first of the two. | | |
| **X08** | Colour a song that had **no** colour in REAPER, then **DISCARD**. | It goes back to having none, rather than to black. | | |
| **X09** | With a phone watching: edit as Director, and watch the phone. | The phone follows the edits **as you make them** — it does not wait for Apply. | | |
| **X10** | Then press **DISCARD** and watch the phone again. | The phone goes back too. A revert that only the Director sees is the worst case. | | |
| **X11** | Enter EDIT, change something, then switch to a different named setlist. | The change is kept. Discard from here reverts only what you do **after** the switch — it must never pour the old set into this one. | | |
| **X12** | Enter EDIT, change something, then **reload the page**. | The change is kept, and you are out of edit mode. There is no pending undo across a reload, on purpose. | | |
| **X13** | As a **Controller**, look at the top bar. | No EDIT, no Apply, no Discard, no `⋮`. | | |
| **X14** | On the phone and the old iPad, in edit mode. | Two round buttons, ✕ and ✓, clearly apart — not touching. They are 34px, same as every other control up there. | | |

### Dialogs are the app's, not the operating system's

`alert`, `confirm` and `prompt` are OS chrome: a different typeface, the page's
URL above them, a system sheet on a phone. Every one of them is now a styled
modal. The app already had a confirm and an alert; it had no **ask**, which is
why every question fell through to `window.prompt()`.

The three dialogs also moved above the mode selector (z-index 9600). At their
old 9000 the PIN prompt and the takeover warning — both raised *by* that
selector — would have opened behind it: invisible, while still holding the
answer everything downstream waits for.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **Q01** | Press **+** in the top bar. | An app modal, styled like the rest — never an OS box with the page URL in it. | | |
| **Q02** | Type a name, press **Enter** (don't click Create). | It creates the setlist. Enter still submits. | | |
| **Q03** | Open it again and press **Escape**. | It closes and nothing is created. | | |
| **Q04** | Open it and press **Cancel**. | Same: nothing created. | | |
| **Q05** | Create a setlist with a name that already exists. | It says so. It used to close and silently do nothing. | | |
| **Q06** | Create one with an empty name, or only spaces. | Nothing created, no error spam. | | |
| **Q07** | Sidebar → **Rename this device**. | Styled modal, pre-filled with the current name, text selected. | | |
| **Q08** | Rename to empty and save. | Back to the automatic guess (e.g. "iPhone · Safari"). | | |
| **Q09** | Sidebar → set a **Director PIN**. | Styled modal, and the field is **masked** — a PIN typed on a stand is not readable over a shoulder. | | |
| **Q10** | With a PIN set, choose Director from the mode selector. | The PIN modal appears **on top of** the selector, not behind it. Masked. | | |
| **Q11** | Enter the wrong PIN. | Styled "Wrong PIN.", and you stay a Controller. | | |
| **Q12** | Cancel the PIN modal. | You stay a Controller. Nothing is claimed. | | |
| **Q13** | With another device already Director, choose Director. | Styled takeover warning naming the other device, red **Take over** button. | | |
| **Q14** | Cancel that warning. | You stay a Controller and **no lease is requested**. | | |
| **Q15** | Confirm it. | You become Director and the other device goes read-only. | | |
| **Q16** | As Director, sidebar → **Pull** the shared setlist. | Styled confirm, red **Replace**. This one used a native confirm on purpose, on the belief that the styled one could never appear — measured in a browser, it appears. | | |
| **Q17** | On the phone, open any of these. | The app's own modal, not a system sheet sliding up from the bottom. | | |

### The row panel on a phone

Measured before the change: the `⋮` panel is 288×567, which does not fit a
320×568 screen nor any phone held sideways, and it did not scroll — **Remove
colour was unreachable**. 27 of its controls were under the 44px a thumb needs.

On a phone it is a **sheet** now: full width, off the bottom edge, scrolling
inside itself. On any touch device — the iPad included, which no width test
calls a phone — the controls are sized for a finger.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **M01** | On the phone, open a song's `⋮`. | It comes up from the bottom, full width — not a small popup pinned near the row. | | |
| **M02** | Turn **Color** on inside it. | The palette appears and the sheet grows *upwards*; nothing falls off the bottom. | | |
| **M03** | Scroll inside the sheet. | It scrolls, and **Remove colour** at the very bottom is reachable. | | |
| **M04** | Hold the phone **sideways** and do M01–M03. | Same. This is the case that was cut off. | | |
| **M05** | Tap the switches and the four end-state buttons with a thumb, not a fingernail. | Each one hits. | | |
| **M06** | Tap a colour swatch. | Five per row on a phone, not six — they are big enough to hit first time. | | |
| **M07** | Tap the note field. | The page does **not** zoom in. (16px text is what stops iOS doing that.) | | |
| **M08** | On the **iPad**, open the same panel. | Still a popup — there is room — but with the same finger-sized controls as the phone. | | |
| **M09** | On the iPad **sideways**, open it and turn colour on. | It repositions rather than running off the bottom. | | |
| **M10** | On a desktop, open it. | Unchanged: a popup near the row, mouse-sized. | | |

### The app's own controls, everywhere

Ten CSS custom properties were **read but never declared** — `--accent`,
`--text`, `--text2`, `--text3`, `--border`, `--bg-surface`, `--shadow`,
`--accent2`, `--accent3`, `--font-heading` — across forty-one rules. A
`var(--x)` with no definition and no fallback makes the whole declaration
invalid, so the browser drops it in silence: no error, no warning, the element
just renders without that colour, border or font.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **T01** | Open Lyrics → the gear → the settings popover. | Green slider thumbs on a thin track, the app's switch, the app's segmented buttons. Not the browser's blue. | | |
| **T02** | Change the weight (Thin / Medium / Bold / Black). | The chosen one is a green segment, exactly like the end-state buttons in the `⋮` panel. It used to render as plain bold text. | | |
| **T03** | Drag each of the three sliders. | They still change what they always changed. This was a styling change only. | | |
| **T04** | Toggle "show previous/next verses". | The app's switch, and it still works. | | |
| **T05** | Open Live View. | The session clock next to LIVE ● is **cyan**, not red. Its rule was written as a class while the element carries the id, so it matched nothing and inherited the indicator's red. | | |
| **T06** | Look at the section name and the remaining time in Live View. | Orange, the same orange the top bar reads its position out in. | | |
| **T07** | Look at any panel that draws a hairline border — Lyrics, Chords, Canvas. | The border is there. `var(--border)` was undefined, so every one of those `border` declarations was dropped. | | |
| **T08** | Open Canvas. | The song name is green; the tool buttons highlight green on hover. | | |
| **T09** | The active tab at the top. | Green text with a green underline. | | |
| **T10** | On the old iPad: the weight buttons and the colour swatches in the Lyrics popover. | Spaced apart, not touching. They spaced with flex `gap`, which that engine drops. | | |

### Lyrics, chords, and the name being the command

The lyrics track is the one called **exactly** `Lyrics`. Not `lyrics`, not
`LYRICS`, not `*Lyrics` or `01 - Lyrics`. This used to accept all of them, and
a convention that accepts eight spellings is not a convention.

Being strict is only usable if being wrong is loud, so a near miss is
recognised and **named**: the panel says which track to rename instead of
reporting "no track".

Chords can be written inline in the lyric in the ChordPro convention —
`[Am]Quando eu [F]te vi` — and render above the syllable they land on.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **L01** | A track named exactly `Lyrics`, with items carrying Item Notes. | The panel shows the note under the playhead. | | |
| **L02** | Rename it to `lyrics`. | It stops working **and says so**, naming `lyrics` and telling you to rename it. Silence would be the bug. | | |
| **L03** | Try `LYRICS`, `*Lyrics`, `01 - Lyrics`. | Same: refused, and named. | | |
| **L04** | A track called `Backing Lyrics`. | Nothing at all. It is an ordinary audio track and must not be offered as a near miss. | | |
| **L05** | A divider track `=== LYRICS ===` above the real `Lyrics`. | The real one is used. The divider does not shadow it. | | |
| **L06** | Open Lyrics Tapper with only a `lyrics` track in the project. | It refuses and tells you to rename — it must **not** create a second `Lyrics` track beside it. | | |
| **L07** | Item note: `[Am]Quando eu [F]te vi, o [C]mundo [G]parou`. | Four chords, each above the syllable it precedes. | | |
| **L08** | Item note: `[intro] 2 compassos` and `Repete [2x]`. | Left exactly as typed. Those are not chords. | | |
| **L09** | Chords with accidentals and slashes: `[F#m7]`, `[Bb]`, `[Csus4]`, `[G/B]`, `[Dadd9]`. | All recognised. | | |
| **L10** | Drag the size slider in the Lyrics popover with chords on screen. | The chord stays over its syllable at every size. | | |
| **L11** | A line long enough to wrap. | The chord wraps with its word, not left behind. | | |
| **L12** | Move to the next verse. | The neighbouring verses show their chords too, dimmer — they do not appear only in the middle slot. | | |
| **L13** | The `Chords` track, same rules. | Same. | | |

### The iPad that stopped at iOS 9.3.5

The floor was written as iOS 10.3. The actual device is an **iPad mini on iOS
9.3.5** — Safari 9 — which is a whole major version further back, and it takes
**CSS Grid** with it. Grid is Safari 10.1.

There `display: grid` is not a partial implementation. It is an unknown value:
the declaration is dropped and the element becomes a block. Five rules in the
file declared it, none with a fallback.

The colour palette was the one that did not degrade gracefully. A swatch is
`width: 100%` with `padding-bottom` for its height, and percentage padding
resolves against the **containing block** — the grid area when there is a grid,
the whole panel when there is not. Measured with grid forced off: each swatch
**239×239**, 18 rows. With the fallback: 36×36, 4 rows.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **W01** | On the iPad, open a song's `⋮` and turn Colour on. | A grid of small round swatches, several per row. Not one enormous circle per line. | | |
| **W02** | Count the rows. | Three or four. Eighteen means the fallback is not applying. | | |
| **W03** | Tap a swatch. | It takes the colour, same as anywhere else. | | |
| **W04** | Appearance → Lyrics → Colour, and the Lyrics popover's colour row. | Same palette, same swatches, same size. They are one CSS rule now. | | |
| **W05** | Turn on **Grid View** on the iPad. | Cards two per row, not one per row. | | |
| **W06** | Open the sidebar on a phone: the view switcher (SHOW / LYRICS / CHORDS…). | Three per row. | | |
| **W07** | Any modal using two or three columns. | Still in columns, not stacked. | | |
| **W08** | The whole app, generally, on that iPad. | Nothing else moved: the transport, the rows and the panels do not use grid. | | |

### The role modal

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **Y09** | Open the mode selector (tap the badge). | Two drawn icons, not emoji: a setlist-with-pen in green for Director, a play-in-a-frame in grey for Controller. | | |
| **Y10** | Read the Controller's description. | It lists play, pause, previous, next, cue and queue. **No Stop** — that button is gone. | | |

### Grid view

It showed a number, a name and a duration — so the one thing a setlist is read
for, where the show pauses, was spelled out in the list and invisible here.

| ID | Scenario | Expected | Result | Notes |
|---|---|---|---|---|
| **G01** | Switch to grid and look at any card. | A pip under the name: **→\|** chains, **■** stops, **⏱** waits. The same mark the list draws. | | |
| **G02** | Read a run of cards left to right. | Chains then a stop **is** the block. That is what the list says with a gap. | | |
| **G03** | Look at the first card of each block. | A vertical rule down its **leading edge**. A top margin would slide sideways into the middle of a row and mean nothing. | | |
| **G04** | A song with loop on; a song skipped. | A purple **↻** pip; a **✕** pip. | | |
| **G05** | Play something and find its card. | Green — same as the list. It used to be drawn in the **stop red**, with a red title. | | |
| **G06** | Tap a card while stopped, then while playing. | Green (cued), then amber (queued). Same language as the list. | | |

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
- [ ] The song `⋮` panel's four end-state buttons (Auto / Continue / Stop /
      Wait) each hold their label with air around it — in **Portuguese and
      Spanish too**, where "Continuar" is the longest. At the old 256px panel
      width that label overflowed its box, and English "Continue" filled its
      box edge to edge.
- [ ] In edit mode the two round ✕ / ✓ buttons are clearly apart, not touching

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
