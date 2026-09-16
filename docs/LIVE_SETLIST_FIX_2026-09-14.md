# Live setlist editing investigation — 2026-09-14

Reported behavior: adding and repositioning a song after a show starts does
not reliably play that song; selecting it can return playback to the beginning.

## Confirmed findings

The local REAPER web root still contained the August 29 HTML without the
transport and cue fixes merged in PR #18 (repository HEAD `57dc438`). The
installed Lua script also lacked that PR's paused-loop correction. Updating
the repository had not updated the files loaded by REAPER.

A separate defect remained in the current Sortable `onEnd` callback: it called
`saveCurrentState()` before assigning the reordered `displayList`. The save
signature therefore matched the old list and skipped persistence/publication.
Adding D and dragging it into A,D,B,C left browser storage and the library
write at A,B,C,D until a later region poll saved again. Followers could also
observe the old order in that interval.

## Correction and regression

Assign the reordered list before saving. Let `saveCurrentState()` derive the
saved representation, as it does for other edits.

`test_added_song_drag_persists_and_plays_mid_show` runs the actual add function,
Sortable callback, save function, row selection and Play. All three variants
(stopped, playing and paused during the edit) failed on the original code with
`AssertionError: drag persisted the old order`; all pass with the correction.
The test checks local storage, library/publication inputs, the live order,
automatic recuing while stopped, absence of edit-triggered seeks while playing
or paused, and the explicit new-song seek/play command once stopped.

## Limits and stage check

REAPER was not running during this investigation. These tests execute the
shipping JavaScript with browser and REAPER I/O simulated; they do not prove
audio output or reproduce the reported return to the start on a live project.
The stale installed version explains why the earlier fixes were unavailable
locally; the drag defect is independently reproduced, not proof that it alone
caused every reported symptom.

Validation completed after the follow-up: **191 tests passed**, including Lua,
with no skips.
The installed HTML matched the pre-PR #18 Git blob exactly
(`bf5b0aed5aab2aba5df7576b0d58eee4e1f6a8cf`). HTML and Lua were then copied
to their existing REAPER installation paths and verified byte-for-byte against
the repository. Previous files are preserved in
`~/Library/Application Support/REAPER/reaset-backup-20260914-nz9odm/`.

After updating the local HTML and Lua and reloading REAPER/ReaSet, verify in a
rehearsal project: finish a song, add an off-set song, drag it immediately after
the finished song, and press Play. Repeat with explicit row selection and with
edits made during playback and pause. Check the same order after reload and on
a follower. Keep audio-device and live transport verification separate from
the automated regression results.

## Follow-up: region rename and edit search

Renaming a REAPER region refreshed `g_offSetlist`, but the render checksum only
covered `displayList`. A song outside the current set therefore retained its
old name and coordinates in the search UI until a manual refresh or unrelated
render change. Off-set rows also had no navigation action: only their `+`
button did anything, so clicking a search result could not locate the region.

The render checksum now includes normalized current-set and off-set rows. Any
name, display name, boundary or color change repaints automatically. An off-set
row click resolves its stable region id through the latest `g_mainRegions`
parse and seeks REAPER to the current start. It does not add, cue, queue or
expose that song to auto-advance. The regression changes both the name and
coordinates, proves the checksum changes, and proves the click uses the new
coordinate rather than stale DOM data.
