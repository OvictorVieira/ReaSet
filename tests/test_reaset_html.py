#!/usr/bin/env python3
"""Static contract tests for ReaSet.html.

ReaSet.html is one ~11k-line file whose entire behaviour lives in a single
inline <script>. A syntax error in it is not a failing feature, it is a blank
page on a stage, and nothing in this repository caught that before this file
existed.

These tests deliberately run the REAL source rather than a transcription of
it: the block-grouping cases below extract the actual functions out of
ReaSet.html and execute them under Node, stubbing only the browser environment
they touch. A copy of the logic in Python would pass forever after the original
drifted, which is worse than no test.

They cannot test transport ordering, multi-device sync, or anything audible —
wwr_req is injected by REAPER's own web server and is a no-op stub anywhere
else. See docs/STAGE_TEST_MATRIX.md for what has to be verified by hand.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REASET_HTML = ROOT / "ReaSet.html"

# Node is present on GitHub-hosted runners and is installed explicitly by the
# workflow, so a skip here means a contributor's laptop, never CI.
requires_node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is required to parse/execute ReaSet.html's inline script",
)


def inline_scripts(html: str) -> list[str]:
    """Bodies of every inline <script> (those without a src attribute)."""
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)


def extract_function(source: str, name: str) -> str:
    """Pull one `function NAME(...) {...}` out by matching its braces.

    Sliced by brace depth rather than by a line range so that reordering the
    file, or adding a function between two of these, cannot silently make the
    test extract the wrong text and still pass.
    """
    match = re.search(r"\bfunction\s+" + re.escape(name) + r"\s*\(", source)
    assert match, f"{name}() not found in ReaSet.html"
    start = match.start()
    brace = source.index("{", match.end() - 1)
    depth = 0
    for i in range(brace, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
    raise AssertionError(f"unbalanced braces while extracting {name}()")


def _brace_block(source: str, open_at: int) -> tuple[str, int]:
    """Slice a `{...}` starting at open_at; returns (body, index after `}`)."""
    depth = 0
    for i in range(open_at, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[open_at + 1 : i], i + 1
    raise AssertionError("unbalanced braces")


def _else_branch(source: str, header: str) -> str:
    """Body of the `else` attached to `header`'s if-statement.

    Brace-matched rather than regex-matched: the if-branch this one is paired
    with contains its own if/else, and a non-greedy pattern happily returns
    that inner one instead — which is how the first version of this test
    passed while reading the wrong branch.
    """
    at = source.index(header)
    _, after = _brace_block(source, source.index("{", at + len(header) - 1))
    tail = source[after:]
    assert tail.lstrip().startswith("else"), f"{header} has no else branch"
    body, _ = _brace_block(tail, tail.index("{", tail.index("else")))
    return body


def strip_comments(js: str) -> str:
    """Remove JS comments, leaving string literals intact.

    Needed because the fix being locked below is also *explained* in a comment
    right where it used to live — the first run of this test failed on its own
    prose. A naive regex would also have to be trusted not to cut inside a
    string containing "//", so this scans instead of guessing.
    """
    out = []
    i, n = 0, len(js)
    quote = None
    while i < n:
        ch = js[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(js[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'`":
            quote = ch
            out.append(ch)
            i += 1
            continue
        if js.startswith("//", i):
            i = js.find("\n", i)
            if i == -1:
                break
            continue
        if js.startswith("/*", i):
            end = js.find("*/", i + 2)
            i = n if end == -1 else end + 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def run_node(script: str) -> str:
    result = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, f"node failed:\n{result.stderr}"
    return result.stdout


@pytest.fixture(scope="module")
def script_body() -> str:
    scripts = inline_scripts(REASET_HTML.read_text(encoding="utf-8"))
    assert len(scripts) == 1, f"expected one inline script, found {len(scripts)}"
    return scripts[0]


@requires_node
def test_inline_script_parses(script_body: str, tmp_path: Path) -> None:
    """The whole app is one script. If it does not parse, nothing renders."""
    js = tmp_path / "reaset-inline.js"
    js.write_text(script_body, encoding="utf-8")
    result = subprocess.run(
        ["node", "--check", str(js)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, f"ReaSet.html's inline script is invalid JS:\n{result.stderr}"


# Acceptance cases from issue #8, as (name, autoStop, overrides, songs, expected).
# `expected` uses a blank line for a block gap, so a failure prints the two
# layouts side by side rather than a boolean.
BLOCK_CASES = [
    (
        "TC-01 basic blocks",
        True,
        {"C": {"stopAfter": True}, "E": {"stopAfter": True}, "F": {"stopAfter": True}},
        [{"id": "A", "chain": True}, {"id": "B", "chain": True}, {"id": "C"},
         {"id": "D", "chain": True}, {"id": "E"}, {"id": "F"}],
        "A\nB\nC\n\nD\nE\n\nF",
    ),
    (
        "TC-02 stop to continue closes the gap",
        True,
        {"E": {"stopAfter": True}, "F": {"stopAfter": True}},
        [{"id": "A", "chain": True}, {"id": "B", "chain": True}, {"id": "C", "chain": True},
         {"id": "D", "chain": True}, {"id": "E"}, {"id": "F"}],
        "A\nB\nC\nD\nE\n\nF",
    ),
    (
        "TC-04a auto with Auto-Stop ON: every song its own block",
        True,
        {},
        [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "A\n\nB\n\nC",
    ),
    (
        "TC-04b auto with Auto-Stop OFF: one block",
        False,
        {},
        [{"id": "A"}, {"id": "B"}, {"id": "C"}],
        "A\nB\nC",
    ),
    (
        "TC-05 wait ends a block",
        False,
        {"C": {"delayAfter": 5}},
        [{"id": "A", "chain": True}, {"id": "B", "chain": True}, {"id": "C"},
         {"id": "D", "chain": True}],
        "A\nB\nC\n\nD",
    ),
    (
        "TC-06/07 a skipped song cannot punch a phantom gap",
        True,
        {"B": {"stopAfter": True}, "C": {"stopAfter": True}},
        [{"id": "A", "chain": True}, {"id": "B", "skipped": True}, {"id": "C"},
         {"id": "D", "chain": True}],
        "A\nB\nC\n\nD",
    ),
    (
        "leading skip: the first PLAYABLE song opens the first block",
        True,
        {},
        [{"id": "A", "skipped": True}, {"id": "B", "chain": True}, {"id": "C"}],
        "A\nB\nC",
    ),
    (
        "a synced end-state wins on a follower",
        False,
        {},
        [{"id": "A", "chain": True}, {"id": "B", "syncedEnd": "stop"}, {"id": "C", "chain": True}],
        "A\nB\n\nC",
    ),
]


@requires_node
@pytest.mark.parametrize(
    "name,auto_stop,overrides,songs,expected",
    BLOCK_CASES,
    ids=[c[0] for c in BLOCK_CASES],
)
def test_block_grouping(script_body, name, auto_stop, overrides, songs, expected):
    """Playback-block boundaries (#8), run against the real helpers.

    The last case exercises the follower path: getSongEnd() prefers a
    synchronised end-state where the device does not author the setlist, which
    is what stops a Player from drawing different blocks than the Director.
    """
    authors = "syncedEnd" not in json.dumps(songs)
    functions = "\n".join(
        extract_function(script_body, fn)
        for fn in (
            "getSongEnd",
            "effectiveSongEnd",
            "_blockPrevPlayable",
            "_playableStartsBlock",
            "isBlockStart",
        )
    )
    harness = textwrap.dedent(
        """
        // Only the browser environment is stubbed; every function below is the
        // real text out of ReaSet.html.
        var displayList = %(songs)s;
        var g_songOverrides = %(overrides)s;
        function getOverride(id) { return g_songOverrides[id] || {}; }
        function canEditSetlist() { return %(authors)s; }
        var document = { getElementById: function (id) {
            return (id === 'autoStopToggle') ? { checked: %(auto_stop)s } : null;
        } };

        %(functions)s

        console.log(displayList.map(function (s, i) {
            return (isBlockStart(i) && i > 0 ? '\\n' : '') + s.id;
        }).join('\\n'));
        """
    ) % {
        "songs": json.dumps(songs),
        "overrides": json.dumps(overrides),
        "authors": "true" if authors else "false",
        "auto_stop": "true" if auto_stop else "false",
        "functions": functions,
    }
    assert run_node(harness).strip("\n") == expected


# (prevTs, nextTs, is_proof_of_life, why)
BEAT_CASES = [
    ("", "1700000000000", False, "first sighting of a value could be a corpse in ExtState"),
    ("1700000000000", "1700000000000", False, "unchanged: a dead Director's value never moves"),
    ("1700000000000", "1700000004000", True, "watched it move: another Director is beating"),
    ("", "", False, "key unset: nothing to see"),
]


@requires_node
@pytest.mark.parametrize("prev,nxt,expected,why", BEAT_CASES, ids=[c[3] for c in BEAT_CASES])
def test_heartbeat_proof_of_life(script_body, prev, nxt, expected, why):
    """Locks the fix for the boot demotion found on a real REAPER.

    Nothing clears directorHeartbeat* when a browser closes, so ExtState keeps
    the last Director's value forever. The observation site used to treat the
    FIRST value it ever saw as a change, which put every boot inside a 12s
    window where a session dead for hours read as live — and the only device in
    the room demoted itself to Player before it could claim the lease.

    As a banner that was cosmetic. As the input to a lease decision it made the
    tool unusable, which is why the rule is a pure function now.
    """
    harness = (
        extract_function(script_body, "_dcBeatIsProofOfLife")
        + "\nconsole.log(_dcBeatIsProofOfLife(%s, %s));" % (json.dumps(prev), json.dumps(nxt))
    )
    assert run_node(harness).strip() == ("true" if expected else "false"), why


HARNESS = ROOT / "Tools" / "stage_race_test.js"

# What Tools/stage_race_test.js reaches into on the page. Not an exhaustive
# list of the file's globals — just the ones that would break it silently.
#
# Matched on a word boundary, not as a substring: "function smartStop" is
# happily contained in "function smartStopX", so a plain `in` check would sail
# straight past exactly the rename this is meant to catch. Found by mutating
# smartStop's name and watching this test pass anyway.
HARNESS_DEPENDENCIES = [
    ("var", "displayList"),
    ("var", "currentPos"),
    ("var", "isPlaying"),
    ("function", "smartStop"),
    ("function", "playRegion"),
    ("function", "togglePlay"),
]


@requires_node
def test_race_harness_parses() -> None:
    """The harness is pasted into a console by someone mid-test.

    Same exposure as ReaSet.html and the same reason to guard it: a syntax
    error here costs the person running a 20-rep race test their time, at the
    moment they are least equipped to debug a paste.
    """
    result = subprocess.run(
        ["node", "--check", str(HARNESS)], capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, f"{HARNESS.name} is invalid JS:\n{result.stderr}"


@pytest.mark.parametrize(
    "kind,name", HARNESS_DEPENDENCIES, ids=[d[1] for d in HARNESS_DEPENDENCIES]
)
def test_race_harness_dependencies_still_exist(script_body: str, kind: str, name: str) -> None:
    """The harness drives ReaSet.html's own entry points, by name.

    That is deliberate — it is what makes the harness exercise the shipping
    path instead of a parallel one — but it also means a rename in ReaSet.html
    breaks it silently, and the breakage surfaces as a confusing console error
    during a race test rather than as a failing build.
    """
    pattern = r"\b" + kind + r"\s+" + re.escape(name) + r"\b"
    assert re.search(pattern, script_body), (
        f"Tools/stage_race_test.js drives `{name}` but ReaSet.html no longer "
        f"declares it as a {kind} — the harness needs updating alongside the rename"
    )


@requires_node
def test_save_current_state_skips_unchanged_state(script_body: str) -> None:
    """saveCurrentState() must not re-publish a state that has not changed.

    It is the choke point for edits, but syncRegions() calls it on every
    REGION reply — polled once a second — so without this guard the whole
    setlist is re-uploaded and a sync push re-armed every second of every
    session, whether or not a flag moved. Measured on a real project, that
    flood made REAPER drop most of the SET/POS commands a user's taps
    produced: 102 commands in 8 seconds, 12 of them the user's.

    Runs the real function with the publishing side effects stubbed and
    counts how many of three identical calls get through.
    """
    harness = (
        """
        var calls = 0, pushes = 0;
        // Declared beside saveCurrentState() in ReaSet.html, so it is not part
        // of the extracted function and has to be provided here.
        var _lastSavedSig = null;
        var currentSetlistName = 'Set A';
        var displayList = [
            { id: '1', chain: true,  skipped: false, loop: false },
            { id: '2', chain: false, skipped: false, loop: false }
        ];
        var setlists = {}, STORAGE_KEY = 'k', CURRENT_KEY = 'c';
        var g_songOverrides = {};
        function getOverride(id) { return g_songOverrides[id] || {}; }
        function getSongEnd(song) {
            var ov = getOverride(song.id);
            if (ov.stopAfter) return 'stop';
            if (ov.delayAfter > 0) return 'wait';
            return song.chain ? 'continue' : 'auto';
        }
        var localStorage = { setItem: function () {} };
        var document = { getElementById: function () { return { checked: true }; } };
        function _syncPushSoon() { pushes++; }
        function _libraryEnqueue() { calls++; }
        """
        + extract_function(script_body, "saveCurrentState")
        + """
        saveCurrentState(); saveCurrentState(); saveCurrentState();
        var afterIdentical = pushes;
        // A song switching from auto to stop leaves chain false and the
        // id/chain/skipped/loop tuple identical — the signature has to notice
        // anyway, or every follower keeps drawing the old blocks.
        g_songOverrides['2'] = { stopAfter: true };
        saveCurrentState();
        console.log(afterIdentical + ',' + pushes);
        """
    )
    assert re.search(r"\bvar\s+_lastSavedSig\b", script_body), (
        "_lastSavedSig is gone from ReaSet.html — saveCurrentState() would throw "
        "on the real page, where an undeclared read is not silently tolerated"
    )
    identical, after_edit = run_node(harness).strip().split(",")
    assert identical == "1", (
        f"three identical saves produced {identical} pushes — the unchanged-state "
        f"guard is gone, and the request queue floods again"
    )
    assert after_edit == "2", (
        "changing a song's end-state produced no push, so followers would keep "
        "rendering the previous blocks"
    )


BRIDGE_TRACK_CASES = [
    (None, False, "no reply yet"),
    ("", False, "Reaset.lua is not running"),
    ("!NOTRACK", False, "no track matches the keyword"),
    ("!NOSWS", False, "track exists but its notes cannot be read"),
    ("lyrics", True, "a real track name"),
]


@requires_node
@pytest.mark.parametrize(
    "status,expected,why", BRIDGE_TRACK_CASES, ids=[c[2] for c in BRIDGE_TRACK_CASES]
)
def test_bridge_poll_rate_gate(script_body, status, expected, why):
    """Only a real track earns the fast lyrics/chords poll.

    The lyrics keys were polled every 10ms unconditionally for the life of the
    page — ~100 requests a second on the same connection every transport
    command crosses, spent whether or not the project has a lyrics track. A
    project with neither track is the normal case, so the default
    configuration paid the most.
    """
    harness = (
        extract_function(script_body, "_bridgeHasTrack")
        + "\nconsole.log(_bridgeHasTrack(%s));" % json.dumps(status)
    )
    assert run_node(harness).strip() == ("true" if expected else "false"), why


def test_lyrics_polling_is_cancellable(script_body: str) -> None:
    """The lyrics/chords polls must not go back to wwr_req_recur.

    wwr_req_recur has no unregister, so anything started with it runs at that
    rate until the page is closed — which is exactly why the rate could never
    be tuned before. Plain intervals are what make the gate above possible.
    """
    recurs = re.findall(r"wwr_req_recur\(([^,]{0,120})", script_body)
    for arg in recurs:
        assert "XR_Lyrics" not in arg and "XR_Chords" not in arg, (
            "the lyrics/chords poll is registered with wwr_req_recur again — it "
            "can never be slowed down or stopped after that"
        )


VIEW_TABS = ["show", "lyrics", "chords", "live", "canvas"]


@pytest.mark.parametrize("tab", VIEW_TABS)
def test_view_tab_highlight_contract(tab: str) -> None:
    """Every view tab must be able to light up, and only when it is current.

    The topbar's colour rule was `.vtab.t-show { ... }` with no `.active`, and
    only SHOW's markup carried its t-* class. So SHOW was lit permanently and
    the other four could never light at all, whatever _setViewTabActive()
    toggled — the class it sets was one the topbar CSS did not read. The
    sidebar copies of the same tabs already used `.sview-btn.t-show.active`;
    the topbar was left behind when they were added.

    Nothing fails when a selector simply does not match, which is why this went
    unnoticed: the bar just quietly disagreed with the screen.
    """
    html = REASET_HTML.read_text(encoding="utf-8")

    assert re.search(r'class="vtab t-' + tab + r'[ "]', html), (
        f"the {tab} tab has no t-{tab} class, so no colour rule can ever match it"
    )
    assert re.search(r"\.vtab\.t-" + tab + r"\.active\s*\{", html), (
        f".vtab.t-{tab} is styled without requiring .active — the colour belongs "
        f"to the tab instead of to the current view"
    )


def test_view_tabs_have_one_owner(script_body: str) -> None:
    """updateTopTabs() must decide all five tabs.

    It used to set three and leave live/canvas to whoever opened them: two
    mechanisms, neither complete, so any interleaving left the bar disagreeing
    with the screen. Opening a view could switch its own tab on but never
    switched SHOW off.
    """
    body = extract_function(script_body, "updateTopTabs")
    for tab in VIEW_TABS:
        assert "'" + tab + "'" in body, (
            f"updateTopTabs() no longer sets the {tab} tab, so it can go stale "
            f"whenever another view changes"
        )
    for fn in ("openCanvasMode", "closeCanvasMode", "openLiveView", "closeLiveView"):
        src = extract_function(script_body, fn)
        assert "updateTopTabs()" in src, f"{fn}() does not refresh the tab bar"
        assert "_setViewTabActive" not in src, (
            f"{fn}() sets a tab directly again — that is the split ownership "
            f"that let the bar disagree with the screen"
        )


@requires_node
def test_every_stop_button_says_whether_it_needs_a_hold() -> None:
    """A Stop button that needs a three-second hold must say so.

    Hold is the default and the right default — a stray tap must not stop a
    show. But the label was a literal "STOP" in the main transport's markup and
    in Live View's, and nothing ever updated either: the button said STOP,
    wanted three seconds, and did nothing at all for a tap. Silently. That is
    the worst failure a transport control can have, and it cost a real testing
    session.

    Asserts every Stop button carries a label element, and that the one
    function that writes them covers all of them at once.
    """
    html = REASET_HTML.read_text(encoding="utf-8")

    # Each handler is a Stop control; each must have a label to update.
    stop_buttons = re.findall(r"<button[^>]*(?:handleMainStopPress|handleStopPress)[^>]*>(.*?)</button>",
                              html, re.S)
    assert len(stop_buttons) >= 3, f"expected the three Stop buttons, found {len(stop_buttons)}"
    for markup in stop_buttons:
        assert 'class="stop-label"' in markup, (
            "a Stop button has no .stop-label, so its text can never be kept in "
            f"step with the hold mode: {markup.strip()[:80]}"
        )

    scripts = inline_scripts(html)[0]
    body = extract_function(scripts, "_refreshStopLabels")
    assert "querySelectorAll('.stop-label')" in body, (
        "_refreshStopLabels no longer writes every label at once — one button "
        "will drift out of step with the others"
    )
    assert "STOP (Hold)" in body and "_stopMode" in body, (
        "the label no longer reflects _stopMode"
    )


def test_modal_buttons_use_classes_that_exist(script_body: str) -> None:
    """showAppConfirm() REPLACES the OK button's className.

    It wrote 'app-modal-btn btn-danger' — three class names the stylesheet
    never defined — which also discarded the markup's own .m-btn, so every
    confirm dialog rendered its OK button as an unstyled white box. Nothing
    fails when a class is simply absent, so this is only ever caught by
    somebody looking at the dialog.

    Asserts the classes it assigns are ones the stylesheet actually declares.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    assigned = re.search(r"okBtn\.className\s*=\s*'([^']*)'\s*\+\s*\([^)]*\?\s*'([^']*)'\s*:\s*'([^']*)'",
                         script_body)
    assert assigned, "could not find showAppConfirm's className assignment"
    for cls in [c for group in assigned.groups() for c in group.split() if c]:
        assert re.search(r"\." + re.escape(cls) + r"\s*[,{]", html), (
            f"showAppConfirm assigns .{cls} but no such rule exists in the "
            f"stylesheet — the button will render unstyled"
        )


def test_play_target_has_no_first_song_fallback(script_body: str) -> None:
    """Locks the #3 fix.

    togglePlay() used to call playRegion(displayList[0]...) whenever currentPos
    did not resolve to a region — which is exactly the window between a user's
    seek and its TRANSPORT acknowledgement, so it started song 1 at the moment
    the user's intent was clearest. smartStop() had the same fallback.

    A reader would have to reintroduce it deliberately to get past this.
    """
    for fn in ("togglePlay", "smartStop"):
        body = strip_comments(extract_function(script_body, fn))
        assert "displayList[0]" not in body, (
            f"{fn}() references displayList[0] again — see issue #3: falling back "
            f"to the first song when the cursor has not resolved is a race, not a "
            f"default"
        )
    assert re.search(r"\bfunction\s+resolvePlayTarget\s*\(", script_body), (
        "resolvePlayTarget() is gone — Play's target must come from one place: "
        "explicit selection, then cursor-region, then the cursor"
    )


# ── Two roles, and no dialog on the way in ───────────────────────────────────
# The read-only "Player" role was retired: both surviving roles drive REAPER,
# and the line between them is EDITING. These lock the two properties that are
# easy to reintroduce by accident and expensive to notice on a stage — a device
# that can author before it knows it is the Director, and a modal in front of a
# musician who just opened a phone thirty seconds before downbeat.

def test_player_role_is_gone(script_body: str) -> None:
    """No live code path may resolve to the retired role.

    The one permitted mention is the localStorage MIGRATION, which exists
    precisely so a device that stored 'player' before the change comes back as
    a Controller instead of booting into a role nothing renders any more.
    """
    body = strip_comments(script_body)
    mentions = re.findall(r"""['"]player['"]""", body)
    assert len(mentions) == 1, (
        f"expected exactly one 'player' literal (the localStorage migration), "
        f"found {len(mentions)} — the retired read-only role must not be "
        f"reachable from any live branch"
    )
    assert re.search(
        r"""_storedMode\s*===\s*['"]player['"]\s*\)\s*\{\s*_storedMode\s*=\s*['"]controller['"]""",
        body,
    ), "the surviving 'player' literal is not the migration — check what it does"

    html = REASET_HTML.read_text(encoding="utf-8")
    assert "reaset-player" not in html, (
        "body.reaset-player rules survive but nothing adds that class — dead "
        "CSS that reads as a third role still existing"
    )
    assert "REASET_PLAYER_BLOCKED_KEYS" not in body, (
        "the read-only keyboard gate is still here; Space/Enter/arrows are "
        "transport, and both roles may drive transport"
    )


def test_default_mode_cannot_author(script_body: str) -> None:
    """The pre-resolution default must fail closed on EDITING, not transport.

    A device opens before it knows whether anyone is directing. Moving the
    playhead in that window is undone with one tap; publishing a setlist from a
    device that turns out not to be the Director is not — it overwrites the
    real one on every other device. So the default is the role that cannot
    author, and canEditSetlist()/canPublishSetlist() must both be Director-only.
    """
    body = strip_comments(script_body)
    default = re.search(r"""var\s+REASET_MODE\s*=\s*['"]([a-z]+)['"]""", body)
    assert default, "REASET_MODE's declaration is gone"
    assert default.group(1) == "controller", (
        f"REASET_MODE defaults to {default.group(1)!r} — it must default to the "
        f"role that cannot publish, so a race before the mode resolves can "
        f"never mutate the shared setlist"
    )
    for fn in ("canEditSetlist", "canPublishSetlist"):
        gate = strip_comments(extract_function(body, fn))
        assert re.search(r"""REASET_MODE\s*===\s*['"]director['"]""", gate), (
            f"{fn}() no longer requires Director"
        )
        assert "controller" not in gate, (
            f"{fn}() admits a Controller — a Controller drives the show, it "
            f"does not change it"
        )


def test_fresh_device_resolves_its_role_instead_of_asking(script_body: str) -> None:
    """No stored choice must NOT open the modal.

    The boot path used to call openModeSelector(true) — a forced three-option
    dialog about a distributed lease protocol, shown to whoever opened the app
    last. It now applies the Controller UI immediately and schedules
    _dcAutoResolveRole(), which reads the room: a live foreign heartbeat means
    somebody is already directing, its absence means somebody has to.
    """
    body = strip_comments(script_body)
    fresh = _else_branch(body, "if (REASET_MODE_STORED)")
    assert "openModeSelector" not in fresh, (
        "a fresh device is forced into the mode picker again — it must enter "
        "without being asked"
    )
    assert "_dcAutoResolveRole" in fresh, (
        "the fresh-device branch no longer schedules the role resolver"
    )

    resolver = strip_comments(extract_function(body, "_dcAutoResolveRole"))
    assert "_dcForeignActive()" in resolver, (
        "the resolver claims Director without checking for a live one"
    )
    assert "requestDirectorLease" in resolver, (
        "the resolver must go through the lease — nothing becomes Director on "
        "optimism, automatic or not"
    )
    assert "_directorPinHash" in resolver, (
        "a configured Director PIN must block an AUTOMATIC claim: the PIN "
        "exists to make directing deliberate, and auto-claiming satisfies it "
        "without anyone typing it"
    )
    assert "localStorage" not in resolver, (
        "an auto-resolved role must not persist — every boot re-reads the "
        "room, which is what lets the next device pick up a lease its Director "
        "dropped instead of a room full of Controllers with nothing to follow"
    )
    assert "_roleChosenExplicitly" in resolver, (
        "the resolver can overwrite a choice the user made during its claim "
        "window"
    )
    assert "DIRECTOR_TTL_MS" in resolver, (
        "the resolver claims on the short window. A foreign heartbeat id whose "
        "timestamp has not been seen to CHANGE yet is a live Director OR a "
        "corpse, and telling them apart takes a full beat interval observed "
        "across the probe — longer than a deliberate claim needs, because this "
        "one fires on every boot of every device"
    )


def test_stand_down_drops_to_controller_not_read_only(script_body: str) -> None:
    """Losing the lease costs the SETLIST, not the transport.

    _dcStandDown() used to set REASET_MODE = 'player', so a Director whose
    Wi-Fi blinked mid-show came back unable to start the next song. It is still
    in the band; what it lost is the right to decide what that song is.
    """
    body = strip_comments(extract_function(strip_comments(script_body), "_dcStandDown"))
    assert re.search(r"""REASET_MODE\s*=\s*['"]controller['"]""", body), (
        "a displaced Director no longer drops to Controller — check it has not "
        "been sent back to a read-only role"
    )
