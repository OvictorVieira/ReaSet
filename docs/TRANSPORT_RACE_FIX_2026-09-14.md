# Play / end-of-song transport investigation — 2026-09-14

Reported symptoms: Play often requires repeated taps; finishing a song can
prepare/restart that same song instead of preparing the next one. This follows
the installation, live-reorder and edit-search investigation documented in
`LIVE_SETLIST_FIX_2026-09-14.md`.

## Reproduced causes

1. **An automatic command could overwrite a manual start.** With A ending at
   10 and C starting at 20, selecting C and pressing Play sent
   `SET/POS/19.995;1007`. A delayed playing reply at 9.9 then made the shipping
   boundary executor send `SET/POS/10` (auto-chain). The existing play lock did
   not protect that executor. Pending automatic timers also survived Play.
2. **The previous native stop range could stop the new song immediately.**
   With REAPER's stop range still at 0–2, starting the next song at 1.995 crossed
   the old end before a subsequent Lua/browser update could arm 2–4. In an
   isolated real REAPER instance, the old sequence was already stopped at the
   first observation, about 28 ms later. Preparing 2–4 before seek/play kept it
   playing through the same boundary and subsequent observations.
3. **Next-song preparation depended on receiving a browser poll in the final
   200 ms.** Missing that window left no next selection. After native stop,
   REAPER's HTTP TRANSPORT reported the edit cursor back at 0; the next Play
   consequently started A. This was reproduced with the shipping JS functions
   driving real REAPER over HTTP, while deliberately withholding end-window
   polls.

## Correction

- Manual Play cancels delayed automatic work and temporarily suppresses all
  automatic transport decisions, including stale auto-stop publication.
- A selected-song start uses a Lua mailbox when the updated engine announces
  support. Lua configures loop/stop ownership and the new range **before**
  seeking and starting playback. The legacy path remains for older engines.
- Repeated taps awaiting confirmation do not become accidental Pause commands.
  A late retry uses the same request token; Lua consumes duplicate tokens only
  once. Stop, Pause and other seeks cancel any unconsumed native start.
- Lua publishes native stop completion independently of browser polling.
  The app can prepare the next song after a missed boundary window, without
  overriding a newer explicit cue, pause or manual-stop guard.
- Native completion uses the measured render/audible-position lead. In the
  real probe this was about 37 ms, while output latency alone was about 6 ms;
  relying on output latency did not identify the completed boundary correctly.

## Validation

`tests/test_transport_races.py` executes the shipping transport handler,
boundary executor, Play and cue functions with controlled delayed replies.
It covers stale boundary commands, old timers, missed completion, repeated
Play and cancellation. Lua tests execute the actual engine chunk to verify
range-before-play ordering, request idempotency and completion classification.
The CI workflow now includes the new transport test module.

Full regression suite: **212 passed**, no skips (37.90 s). `git diff --check`
also passed.

Real-engine probe: an isolated, empty REAPER project, separate resource/config
directory and localhost HTTP port 18089. Twenty cycles cover app/REAPER starts
crossed with normal polling/missed end-window polling (five per combination).
All twenty prepared B and started B on the next single Play. Browser DOM and
I/O collection were stubbed; transport commands and Lua engine ran in REAPER.
Temporary probe scripts and logs are in `/tmp/reaset-engine-probe.cJ9rH8`.

These checks do **not** validate a full show, multitrack audio/MIDI, the user's
audio interface, mobile browsers, Wi-Fi or multi-device contention. Before
stage use, restart the installed Lua engine, reload ReaSet, and rehearse:
app/REAPER starts; song completion with auto-stop enabled; chain mode; repeated
Play; Stop/Pause during a pending start; and add/reorder during playback.
Auto-stop still prepares the next song for Play; it does not enable automatic
continuous playback when that mode is disabled.

## Local installation

Updated both the existing REAPER web-root `ReaSet.html` and
`Scripts/ReaSet/ReaSet/Reaset.lua`, with byte-for-byte verification against the
repository. Previous files are preserved together in:

`/Users/victorhugo/Library/Application Support/REAPER/reaset-backup-transport-20260914-mxhiDF`

The isolated test instance was closed after validation. No show project was
opened or modified. Restart the Lua engine and reload the browser before
testing the installed pair; updating source files does not replace scripts
already running in memory.
