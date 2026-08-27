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


# A `/` begins a regex literal, rather than a division, when the last
# significant character before it cannot end an expression.
_REGEX_MAY_FOLLOW = set("(,=:[!&|?{};+-*%~^<>") | {""}


def strip_comments(js: str) -> str:
    """Remove JS comments, leaving string literals intact.

    Needed because the fixes locked below are also *explained* in comments right
    where the old code lived — the first run of one of these tests failed on its
    own prose. A naive regex would also have to be trusted not to cut inside a
    string containing "//", so this scans instead of guessing.

    REGEX LITERALS ARE PART OF THE SCAN, and skipping them is not a nicety.
    ReaSet contains `subOv.description.replace(/"/g, '&quot;')`. Without this
    branch the `"` inside that regex opened a string that never closed, and
    every one of the ~210k characters after it came back UNSTRIPPED — so an
    assertion of the form `"X" not in strip_comments(body)` could be satisfied
    by prose in a comment, or defeated by it, anywhere past that point. The bug
    surfaced when a test looking for a deleted function found the comment that
    replaced it; it had been silently weakening assertions before that.
    """
    out = []
    i, n = 0, len(js)
    quote = None
    last_significant = ""
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
            last_significant = ch
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
        if ch == "/" and last_significant in _REGEX_MAY_FOLLOW:
            # Copy the literal through verbatim, honouring escapes and classes,
            # so nothing inside it is mistaken for a quote or a comment.
            out.append(ch)
            i += 1
            in_class = False
            while i < n:
                c = js[i]
                out.append(c)
                if c == "\\" and i + 1 < n:
                    out.append(js[i + 1])
                    i += 2
                    continue
                if c == "[":
                    in_class = True
                elif c == "]":
                    in_class = False
                elif c == "/" and not in_class:
                    i += 1
                    break
                elif c == "\n":
                    break   # not a regex after all; bail rather than run away
                i += 1
            last_significant = "/"
            continue
        out.append(ch)
        if not ch.isspace():
            last_significant = ch
        i += 1
    return "".join(out)


def test_strip_comments_survives_a_regex_containing_a_quote() -> None:
    """Guards the helper the other tests are built on.

    Every `X not in strip_comments(body)` assertion in this file is only as
    trustworthy as this scan. When it broke, it broke SILENTLY and for the whole
    remainder of the file.
    """
    src = 'var a = s.replace(/"/g, "x");  // comment one\nvar b = 1; // comment two\n'
    out = strip_comments(src)
    assert "comment one" not in out and "comment two" not in out, (
        "a regex literal containing a quote swallowed the rest of the input"
    )
    assert 'replace(/"/g, "x")' in out, "the regex itself was mangled"
    assert strip_comments('var re = /a[/]b/; // gone\n').count("gone") == 0
    assert "kept" in strip_comments('var s = "// kept";'), (
        "a comment marker inside a string literal was stripped"
    )


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
def test_every_stop_button_says_what_it_wants() -> None:
    """A Stop button that will not respond to a tap must say so.

    The label was a literal "STOP" in the main transport's markup and in Live
    View's, and nothing ever updated either: the button said STOP, wanted a
    three-second hold, and did nothing at all for a tap. Silently. That is the
    worst failure a transport control can have, and it cost a real testing
    session. Hold is gone, but the property that broke is the same one — three
    copies of a control, one function that must reach all of them.

    Asserts every Stop control shares the class the handlers and the styles are
    written against, carries a label element and a thumb, and that one function
    writes all of them at once.
    """
    html = REASET_HTML.read_text(encoding="utf-8")

    stop_buttons = re.findall(r"<button[^>]*\bstop-ctl\b[^>]*>(.*?)</button>", html, re.S)
    assert len(stop_buttons) == 3, (
        f"expected the three Stop controls to carry .stop-ctl, found {len(stop_buttons)} — "
        f"a copy that misses the class gets neither the gesture nor the label"
    )
    for markup in stop_buttons:
        assert 'class="stop-label"' in markup, (
            "a Stop control has no .stop-label, so its text can never be kept in "
            f"step with the mode: {markup.strip()[:80]}"
        )
        assert 'class="ss-thumb"' in markup, (
            "a Stop control has no .ss-thumb, so in slide mode it renders as a "
            f"track with nothing to drag: {markup.strip()[:80]}"
        )

    # The retired gesture must not linger in markup or styles.
    assert "stop-holding" not in html and "handleMainStopPress" not in html, (
        "the three-second hold is still wired up somewhere"
    )

    scripts = inline_scripts(html)[0]
    body = extract_function(scripts, "_refreshStopLabels")
    assert "querySelectorAll('.stop-ctl')" in body, (
        "_refreshStopLabels no longer writes every control at once — one button "
        "will drift out of step with the others"
    )
    assert "is-slide" in body and "_stopMode" in body, (
        "the label and the slide class no longer follow _stopMode"
    )


def test_stop_slide_fires_on_release_not_on_threshold(script_body: str) -> None:
    """A slide taken to the end and then back is a change of mind.

    Firing the moment the thumb crosses the commit threshold would make the
    gesture uninterruptible — which removes the one property that makes it
    safer than a tap. Stop must happen on release, and only if still armed.
    """
    body = strip_comments(script_body)
    up = strip_comments(extract_function(body, "_stopCtlUp"))
    assert "smartStop()" in up, "_stopCtlUp() no longer stops on release"
    move = strip_comments(extract_function(body, "_stopCtlMove"))
    assert "smartStop" not in move, (
        "_stopCtlMove() stops as soon as the threshold is crossed — the slide "
        "can no longer be abandoned, which is the whole point of it"
    )
    down = strip_comments(extract_function(body, "_stopCtlDown"))
    assert re.search(r"""_stopMode\s*!==\s*['"]slide['"]\s*\)\s*\{\s*smartStop\(\)""", down), (
        "tap mode no longer acts on press"
    )


def test_stop_mode_migrates_the_retired_hold(script_body: str) -> None:
    """A device that stored 'hold' must not come back with a gesture nothing
    implements — that is a Stop button that does nothing at all, again."""
    body = strip_comments(script_body)
    decl = body[body.index("var _stopMode ="):body.index("function toggleStopMode")]
    assert re.search(r"""v\s*===\s*['"]hold['"]""", decl), (
        "the stored 'hold' mode is no longer migrated"
    )
    assert re.search(r"""return\s+['"]slide['"]""", decl), (
        "'hold' does not migrate to 'slide'"
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


# ── Session clock ────────────────────────────────────────────────────────────
# The bug: a phone read 6:02:21 next to a Mac reading 1:48 on the same show.
# The clock was per-device localStorage that never expired, so both were
# correct and neither was useful. It is now the Director's, published as
# ELAPSED SECONDS and anchored locally on arrival.

def test_session_clock_never_puts_a_timestamp_on_the_wire(script_body: str) -> None:
    """The naive synced design is the one that had to be avoided.

    Publishing sessionStart as epoch ms and letting each device compute
    Date.now() - start renders the two devices' CLOCK SKEW directly on screen:
    phones drift and resync against the carrier, a slept laptop wakes stale.
    The wire carries elapsed seconds instead, and a follower anchors it against
    its own clock — so only local differences are ever taken.

    Same rule _dcBeatIsProofOfLife follows: judge by what changed locally,
    never by comparing a foreign clock to ours.
    """
    body = strip_comments(script_body)

    publish = strip_comments(extract_function(body, "_sessionPublish"))
    assert "sessionElapsed" in publish, "the published key is no longer the elapsed one"
    assert re.search(r"Date\.now\(\)\s*-\s*_sessionStart", publish), (
        "_sessionPublish() no longer publishes a locally-computed DELTA"
    )
    assert not re.search(r"/\s*'\s*\+\s*_sessionStart\b", publish), (
        "_sessionPublish() puts a raw start timestamp on the wire — every "
        "reader would then subtract it from ITS OWN clock, and the skew "
        "between the two devices becomes the displayed error"
    )

    display = strip_comments(extract_function(body, "_sessionDisplaySec"))
    assert re.search(r"Date\.now\(\)\s*-\s*_sessionRemoteAt", display), (
        "the remote branch no longer anchors against the LOCAL arrival instant"
    )
    for foreign in ("_sessionRemoteSec -", "- _sessionRemoteSec"):
        assert foreign not in display, (
            "a foreign clock value is being subtracted from a local one"
        )


def test_session_clock_reanchors_only_on_change(script_body: str) -> None:
    """The Director beats every 4s; the probe polls at 2s.

    Every published value is therefore seen more than once. Re-anchoring on a
    repeat would restart the extrapolation each time and drag the displayed
    time visibly backwards.
    """
    observe = strip_comments(extract_function(strip_comments(script_body), "_sessionObserveRemote"))
    assert re.search(r"if\s*\(\s*v\s*===\s*_sessionRemoteSec\s*\)\s*return", observe), (
        "_sessionObserveRemote() re-anchors on an unchanged value — the clock "
        "will stutter backwards on every duplicate poll"
    )


def test_session_clock_reset_is_director_only(script_body: str) -> None:
    """A follower clearing its local value would watch the Director's next
    published tick overwrite it half a second later: a button that silently
    does nothing."""
    reset = strip_comments(extract_function(strip_comments(script_body), "resetSessionClock"))
    assert re.search(r"""REASET_MODE\s*!==\s*['"]director['"]\s*\)\s*return""", reset), (
        "resetSessionClock() no longer refuses on a follower"
    )


@requires_node
def test_session_clock_behaviour(script_body: str) -> None:
    """Runs the real restore / observe / display code under Node.

    Covers the reported bug directly (case 2) and the skew property that
    distinguishes a correct implementation from the naive one (case 5).
    """
    fns = "\n".join(
        extract_function(script_body, fn)
        for fn in ("_sessionObserveRemote", "_sessionDisplaySec",
                   "_sessionAdoptOnPromotion", "_sessionWrite")
    )
    restore = script_body[
        script_body.index("(function _sessionRestore() {") :
        script_body.index("function _sessionWrite()")
    ]

    harness = textwrap.dedent(
        """
        var NOW = 1000000000000;
        Date.now = function () { return NOW; };

        var SESSION_IDLE_RESET_MS = 4 * 60 * 60 * 1000;
        var SESSION_KEY = 'reaset_session_start';
        var _sessionStart = null, _sessionSeen = 0, _sessionPk = null;
        var _sessionRemoteSec = null, _sessionRemoteAt = 0;
        var REASET_MODE = 'controller';
        var _sessionSeenWritten = 0, g_projectKey = 'pa';
        var STORED = null, FOREIGN = false;
        var localStorage = {
            getItem: function (k) { return STORED; },
            removeItem: function (k) { STORED = null; },
            setItem: function (k, v) { STORED = v; }
        };
        function _dcForeignActive() { return FOREIGN; }

        __FNS__

        function restore() { __RESTORE__ }

        function reset(stored, mode, foreign) {
            STORED = stored; REASET_MODE = mode; FOREIGN = foreign;
            _sessionStart = null; _sessionSeen = 0; _sessionPk = null;
            _sessionRemoteSec = null; _sessionRemoteAt = 0;
            restore();
        }
        var out = [];

        // 1. a session from ten minutes ago survives a reload
        reset(JSON.stringify({s: NOW - 600000, t: NOW - 60000, p: 'pa'}), 'director', false);
        out.push(['fresh-session-survives', Math.round(_sessionDisplaySec())]);

        // 2. THE REPORTED BUG: a start six hours old whose last playback was
        //    six hours ago is a different session and must not be restored.
        reset(JSON.stringify({s: NOW - 21720000, t: NOW - 21720000, p: 'pa'}), 'director', false);
        out.push(['stale-session-expires', Math.round(_sessionDisplaySec()), STORED === null]);

        // 3. a SIX HOUR rehearsal that is still being played must keep counting
        reset(JSON.stringify({s: NOW - 21720000, t: NOW - 30000, p: 'pa'}), 'director', false);
        out.push(['long-active-rehearsal-survives', Math.round(_sessionDisplaySec())]);

        // 4. the legacy bare-integer format, six hours old, expires
        reset(String(NOW - 21720000), 'director', false);
        out.push(['legacy-format-expires', Math.round(_sessionDisplaySec())]);

        // 5. SKEW: the follower's own clock is 8 minutes ahead of the
        //    Director's, and the displayed time must not show that at all.
        reset(null, 'controller', true);
        _sessionObserveRemote('300');          // Director says 5:00
        NOW += 4000;                            // four seconds pass locally
        out.push(['skew-immune', Math.round(_sessionDisplaySec())]);

        // 6. a repeated value must not drag the clock backwards
        _sessionObserveRemote('300');
        out.push(['duplicate-does-not-rewind', Math.round(_sessionDisplaySec())]);

        // 7. the Director's reset sentinel reaches the follower as 0:00
        _sessionObserveRemote('-1');
        out.push(['reset-sentinel', Math.round(_sessionDisplaySec())]);

        // 8. no live Director: the follower falls back to its own clock
        //    instead of freezing
        reset(JSON.stringify({s: NOW - 120000, t: NOW - 5000, p: 'pa'}), 'controller', false);
        _sessionObserveRemote('9999');
        out.push(['no-director-falls-back-local', Math.round(_sessionDisplaySec())]);

        // 9. HANDOVER: a follower two minutes into its own clock, watching a
        //    Director at 50:00, gets promoted. It must adopt the show's time,
        //    not restart from its own first playback.
        reset(JSON.stringify({s: NOW - 120000, t: NOW - 5000, p: 'pa'}), 'controller', true);
        _sessionObserveRemote('3000');
        NOW += 2000;
        REASET_MODE = 'director';
        _sessionAdoptOnPromotion();
        out.push(['handover-adopts-show-time', Math.round(_sessionDisplaySec())]);

        // 10. ...but a device that has been in the room LONGER keeps its own.
        reset(JSON.stringify({s: NOW - 7200000, t: NOW - 5000, p: 'pa'}), 'controller', true);
        _sessionObserveRemote('60');
        REASET_MODE = 'director';
        _sessionAdoptOnPromotion();
        out.push(['handover-keeps-older-session', Math.round(_sessionDisplaySec())]);

        console.log(JSON.stringify(out));
        """
    ).replace("__FNS__", fns).replace("__RESTORE__", restore.strip().removeprefix("(function _sessionRestore() {").rsplit("})();", 1)[0])

    got = dict((row[0], row[1]) for row in json.loads(run_node(harness)))
    expected = {
        "fresh-session-survives": 600,
        "stale-session-expires": 0,
        "long-active-rehearsal-survives": 21720,
        "legacy-format-expires": 0,
        # 300 published + 4s of LOCAL time. The follower's own clock being
        # minutes off the Director's cannot enter this number.
        "skew-immune": 304,
        "duplicate-does-not-rewind": 304,
        "reset-sentinel": 0,
        "no-director-falls-back-local": 120,
        # 3000 published + 2s local. Its own 122s clock is discarded because
        # the show demonstrably started earlier than this device did.
        "handover-adopts-show-time": 3002,
        # Two hours in the room beats a Director that joined a minute ago.
        "handover-keeps-older-session": 7200,
    }
    assert got == expected, f"\ngot      {got}\nexpected {expected}"


# ── What a Controller sees ───────────────────────────────────────────────────

def test_controller_gets_a_banner_not_a_dead_dropdown() -> None:
    """A dropdown that cannot drop down is a broken control, not a read-only one.

    The picker was left in place for a Controller with `pointer-events: none`,
    so the chevron still promised a choice and the tap did nothing. On a phone
    that reads as an app that has hung, not as a permission boundary.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    assert re.search(r'body\.reaset-controller\s+\.setlist-picker\s*\{[^}]*display:\s*none', html), (
        "the picker is still rendered for a Controller"
    )
    assert re.search(r'body\.reaset-controller\s+\.setlist-banner\s*\{[^}]*display:\s*flex', html), (
        "no banner replaces it"
    )
    assert 'id="setlistBannerName"' in html, "the banner has nowhere to put the set's name"

    scripts = inline_scripts(html)[0]
    picker = strip_comments(extract_function(scripts, "renderSetlistPicker"))
    assert "_refreshSetlistBanner()" in picker, (
        "the banner is not refreshed from renderSetlistPicker(), so the two "
        "surfaces can show different setlists — which is the bug the picker "
        "already had once"
    )
    banner = strip_comments(extract_function(scripts, "_refreshSetlistBanner"))
    assert "currentSetlistName" in banner, "the banner does not read the active set"
    assert "is-offline" in banner and "_libConnected" in banner, (
        "the banner no longer flags an unreachable project. A Controller has no "
        "picker to open, so this is the only place it could ever find out that "
        "the setlist it is reading is not the live one"
    )
    assert "is-live" in banner and "isPlaying" in banner, (
        "the banner's dot no longer follows playback"
    )


def test_controller_list_excludes_songs_outside_the_set(script_body: str) -> None:
    """Skipped songs are not in tonight's set, and a Controller cannot un-skip
    one — so a greyed-out row is one more thing to misread on a dark stage.

    The forcing must be DERIVED, never written into hideSkippedMode: that value
    is persisted, so forcing it would silently rewrite the Director's own view
    preference on any device that had ever been a Controller.
    """
    body = strip_comments(script_body)
    gate = strip_comments(extract_function(body, "_hideSkippedEffective"))
    assert "canEditSetlist()" in gate, (
        "_hideSkippedEffective() no longer forces the filter for a role that "
        "cannot edit the set"
    )
    assert "hideSkippedMode" in gate and "=" not in gate.split("return")[1], (
        "the effective value is being assigned somewhere instead of derived"
    )

    # Every render site must ask the function, not the raw preference.
    assert "hideSkippedMode && r.skipped" not in body, (
        "a render loop still reads the raw preference, so a Controller sees "
        "songs that are not in the set"
    )
    # Counting call sites would be satisfied by the declaration itself, so the
    # raw preference is banned from the render path outright instead.
    assert "(hideSkippedMode ? 1 : 0)" not in body, (
        "a render CHECKSUM still hashes the raw preference. The list then keeps "
        "its old contents across a role change until something unrelated "
        "happens to move the checksum — which is worse than not filtering at "
        "all, because it is intermittent"
    )
    assert body.count("_hideSkippedEffective() && r.skipped") == 2, (
        "expected the filter at both render sites (list view and grid view), "
        f"found {body.count('_hideSkippedEffective() && r.skipped')}"
    )
    # One checksum site, in syncRegions(). There were two until reorderPrompt()
    # was deleted with the numeric reorder path — this count going back to 2
    # would mean a second, competing place that decides when to repaint.
    assert body.count("(_hideSkippedEffective() ? 1 : 0)") == 1, (
        "expected exactly one render checksum to hash the filter, found "
        f"{body.count('(_hideSkippedEffective() ? 1 : 0)')}"
    )


def test_reconnect_does_not_share_the_loop_glyph() -> None:
    """Two controls, one symbol, one transport bar.

    RECONNECT used the ↻ (&#8635;) codepoint — the same one .t-btn-loop draws,
    two buttons away on the same bar. Mid-show that is a coin flip between
    "repeat this song" and "restart the network connection", and those are not
    neighbouring mistakes.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    sync = re.search(r'<button[^>]*\bt-btn-sync\b[^>]*>(.*?)</button>', html, re.S)
    assert sync, "the reconnect button is gone"
    for glyph in ("&#8635;", "\u21bb", "&#8634;", "\u21ba"):
        assert glyph not in sync.group(1), (
            f"the reconnect button is drawing {glyph!r} again — that is the loop icon"
        )
    assert "<svg" in sync.group(1), (
        "the reconnect button has no icon at all"
    )
    loop = re.search(r'<button[^>]*\bt-btn-loop\b[^>]*>(.*?)</button>', html, re.S)
    assert loop, "the loop button is gone"
    assert "&#8635;" in loop.group(1) or "\u21bb" in loop.group(1), (
        "the loop button no longer uses ↻ — if it moved to something else, "
        "check this test still compares the two controls that sit side by side"
    )


# ── i18n ─────────────────────────────────────────────────────────────────────
# Nothing FAILS when a string bypasses the translation table. It renders, it is
# readable to whoever wrote it, and only a user in the other language sees the
# seam — which is how a phone set to English ended up showing
#
#     ⚠ El dispositivo "Mac · Chrome" is now the Director — this device is read-only
#
# one sentence in two languages. A reviewer will not reliably catch that. These
# will.

def _i18n_rows() -> list[list[str]]:
    html = REASET_HTML.read_text(encoding="utf-8")
    start = html.index("var I18N_ROWS = [")
    end = html.index("\n        ];", start) + len("\n        ];")
    out = run_node(html[start:end] + "\nconsole.log(JSON.stringify(I18N_ROWS));")
    return json.loads(out)


@requires_node
def test_i18n_table_is_complete_and_unambiguous() -> None:
    """Three full columns, and every cell usable as a lookup key.

    The table's whole design is that BOTH — now all three — sides are keys, so
    translation needs no markup annotations and re-running the DOM walk is
    idempotent. That only holds if a cell identifies exactly one row: if two
    rows share a translation, a node holding it would flip to whichever row won,
    and switching language twice would land it in the wrong string.
    """
    rows = _i18n_rows()
    assert len(rows) > 150, f"the table shrank to {len(rows)} rows — check what was deleted"

    for row in rows:
        assert len(row) == 3, f"row is not [en, es, pt]: {row}"
        for cell in row:
            assert isinstance(cell, str) and cell.strip(), (
                f"empty cell in {row[0]!r} — an untranslated cell renders blank, "
                f"and a blank label on stage is worse than an English one"
            )

    owner: dict[str, list[str]] = {}
    for row in rows:
        for cell in row:
            if cell in owner and owner[cell] is not row:
                raise AssertionError(
                    f"{cell!r} is a cell of two different rows "
                    f"({owner[cell][0]!r} and {row[0]!r}) — a node holding it "
                    f"cannot be translated deterministically"
                )
            owner.setdefault(cell, row)


@requires_node
def test_every_language_is_reachable(script_body: str) -> None:
    """The readers must index by language, not by a boolean.

    `REASET_LANG === 'es' ? 1 : 0` is what limited the table to two columns.
    Both readers — t() for strings built in JS, and the DOM walk for markup —
    have to take an index, or a third language silently renders as English.
    """
    body = strip_comments(script_body)
    langs = re.search(r"var\s+I18N_LANGS\s*=\s*\[([^\]]*)\]", body)
    assert langs, "I18N_LANGS is gone — the column order is the table's contract"
    assert [x.strip().strip("'\"") for x in langs.group(1).split(",")] == ["en", "es", "pt"]

    for fn in ("t", "_i18nWalk"):
        src = strip_comments(extract_function(body, fn))
        assert "_langIndex" in src, (
            f"{fn}() does not index by language — with a binary conditional the "
            f"third column can never be read"
        )
        assert "=== 'es'" not in src, f"{fn}() still branches on Spanish specifically"

    switcher = REASET_HTML.read_text(encoding="utf-8")
    for lang in ("en", "es", "pt"):
        assert f"""data-lang="{lang}\"""" in switcher, (
            f"{lang} is in the table but not in the language switcher, so no "
            f"user can select it"
        )

    detect = body[body.index("var REASET_LANG ="):body.index("function t(")]
    assert "/^pt/i" in detect, (
        "a browser set to Portuguese is not detected, so a pt-BR device still "
        "opens in English"
    )


def test_no_dialog_bypasses_the_translation_table(script_body: str) -> None:
    """A hardcoded string in a prompt/confirm/alert is invisible until someone
    in the wrong language is on stage.

    This is the check that keeps the fix from decaying: without it the next
    feature adds another inline string and nobody notices.
    """
    body = strip_comments(script_body)
    offenders = []
    for m in re.finditer(r"\b(?:window\.)?(prompt|confirm|alert)\s*\(\s*(['\"])(.*?)(?<!\\)\2",
                         body, re.S):
        text = m.group(3)
        # Punctuation-only and single-token arguments (a key, a number, a glyph)
        # are not prose and have nothing to translate.
        if len(text) < 4 or " " not in text.strip():
            continue
        offenders.append(f"{m.group(1)}({text[:70]!r}...)")
    assert not offenders, (
        "these dialogs hold their text inline instead of going through t():\n  "
        + "\n  ".join(offenders)
    )


@requires_node
def test_markup_prose_is_in_the_table() -> None:
    """The mode-selector card was Spanish-only in the markup regardless of the
    language setting — and it is the FIRST screen a new device ever sees.

    Rather than police every text node in a 12k-line file, this pins the
    surfaces that have actually gone wrong: any block that is prose a user
    reads before choosing anything.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    keys = {cell for row in _i18n_rows() for cell in row}

    card = re.search(r'<div id="mode-select-overlay".*?\n    </div>', html, re.S)
    assert card, "the mode selector is gone"
    prose = re.findall(r">\s*([^<>{}]{12,})\s*<", card.group(0))
    missing = []
    for text in prose:
        flat = " ".join(text.split())
        if flat and flat not in keys:
            missing.append(flat[:70])
    assert not missing, (
        "the mode selector — the first screen a new device sees — holds prose "
        "that is not in the translation table, so it renders in one language "
        "whatever the user picked:\n  " + "\n  ".join(missing)
    )


# ── Instance identity (#13) ──────────────────────────────────────────────────
# A song may appear twice in one set. Two instances occupy the IDENTICAL time
# range in REAPER, so `currentPos >= r.start && currentPos < r.end` matches both
# and every scan in this file used to take the first. The cosmetic half of that
# is the wrong row highlighting; the dangerous half is auto-advance following
# the earlier copy, which sends the band back to song 2 mid-encore.

def test_no_scan_resolves_the_active_row_positionally(script_body: str) -> None:
    """One resolver, and nothing may go around it.

    Nine separate list scans used to answer "which row is playing", each with
    `break` on the first match. They now all defer to activeInstanceIdx(), which
    consults intent before falling back to the first match.
    """
    body = strip_comments(script_body)
    scans = re.findall(r"for\s*\([^)]*displayList\.length[^)]*\)\s*\{?[^{}]*"
                       r"currentPos\s*>=\s*\w+\.start", body)
    assert len(scans) <= 1, (
        f"{len(scans)} positional scans still resolve the active row directly. "
        f"Each one takes the FIRST region whose time range contains the cursor, "
        f"which with a repeat is always the earlier row:\n  "
        + "\n  ".join(x[:90] for x in scans)
    )

    resolver = strip_comments(extract_function(body, "activeInstanceIdx"))
    assert "_activeUidHint" in resolver, "the resolver ignores intent entirely"
    assert "break" not in resolver, (
        "activeInstanceIdx() breaks out of its scan — the hinted instance may be "
        "the LATER one, and stopping at the first match is precisely the bug"
    )
    assert "return i" in resolver and "return first" in resolver, (
        "the resolver no longer has both the intent answer and the documented "
        "first-match fallback"
    )


def test_dom_ids_key_off_the_instance() -> None:
    """Two rows for one song must not carry the same DOM id.

    getElementById returns the FIRST match, so a region-keyed id would make the
    progress fill, the countdown, the active highlight and the loop badge all
    paint the earlier row while the later one plays — silently, with no error
    anywhere.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    scripts = inline_scripts(html)[0]

    for prefix in ("row-", "bg-", "dur-", "chev-", "slist-", "loop-counter-"):
        for m in re.finditer(r'"' + re.escape(prefix) + r'"\s*\+\s*([\w.]+)', scripts):
            ref = m.group(1)
            assert "uid" in ref.lower() or ref == "lastActiveID", (
                f'a DOM id is still built as "{prefix}" + {ref} — with a repeat '
                f"that names two elements"
            )

    # The row itself has to be addressable AS a row for the drag reorder.
    assert 'setAttribute("data-uid"' in scripts, (
        "rows no longer carry data-uid, so Sortable cannot tell two instances "
        "apart when it rebuilds the order"
    )
    sortable = strip_comments(scripts[scripts.index("onEnd:"):])[:1200]
    assert 'getAttribute("data-uid")' in sortable, (
        "Sortable.onEnd still rebuilds the order from data-id, which two rows "
        "share — dragging either would collapse the pair on the next save"
    )


def test_overrides_stay_keyed_on_the_song(script_body: str) -> None:
    """Stop / wait / colour / description describe the SONG.

    A repeat is the same song, so both rows must agree about them. This is the
    one axis that deliberately does NOT move to the uid, and it is easy to
    "fix" by mistake while converting everything else.
    """
    body = strip_comments(script_body)
    for fn in ("getOverride", "setSongOverride"):
        src = strip_comments(extract_function(body, fn))
        assert "uid" not in src, (
            f"{fn}() has become uid-keyed. Per-instance overrides may be a "
            f"reasonable feature one day, but they are a decision to take "
            f"deliberately — not a side effect of an identity refactor"
        )
    cycle = strip_comments(extract_function(body, "cycleSongEnd"))
    assert "setSongEnd(song.id" in cycle, (
        "cycleSongEnd() writes the end-state under something other than the "
        "region id, so the two instances of a repeat would disagree"
    )


def test_the_numeric_reorder_prompt_is_gone() -> None:
    """Acceptance test 4 of #13.

    It was a second reorder path bound to the index number, and the only one
    that raised a native prompt() — a modal asking a musician to type a
    position, on a phone, during a show.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    scripts = strip_comments(inline_scripts(html)[0])
    assert "reorderPrompt" not in scripts, "reorderPrompt is still reachable"
    # Only the MARKUP: the note explaining why the function was deleted lives in
    # a JS comment and naturally names it.
    markup = re.sub(r"<script.*?</script>", "", html, flags=re.S)
    assert "reorderPrompt" not in re.sub(r"<!--.*?-->", "", markup, flags=re.S), (
        "the index number is still wired to the numeric reorder prompt"
    )


@requires_node
def test_auto_advance_follows_the_playing_instance(script_body: str) -> None:
    """THE test this issue exists for — acceptance test 10.

    With one song listed twice, playing the SECOND copy must advance to what
    follows the second copy. The old code took the first index whose region
    contained the cursor, so it advanced from the FIRST copy and the show
    jumped backwards.

    Runs the real activeInstanceIdx() and findNextValidSong().
    """
    fns = "\n".join(extract_function(script_body, f)
                    for f in ("activeInstanceIdx", "findNextValidSong", "noteActiveInstance"))

    harness = textwrap.dedent(
        """
        var RSDiag = { log: function () {} };
        var _activeUidHint = null;
        var currentPos = 0;
        // A, B, A again, C — the same song at index 0 and index 2, so both
        // rows carry identical start/end.
        var displayList = [
            { id: 'A', uid: 'A#1', start:  0, end: 10, skipped: false },
            { id: 'B', uid: 'B#1', start: 10, end: 20, skipped: false },
            { id: 'A', uid: 'A#2', start:  0, end: 10, skipped: false },
            { id: 'C', uid: 'C#1', start: 20, end: 30, skipped: false }
        ];
        __FNS__

        var out = [];
        currentPos = 5;   // inside A — which is BOTH row 0 and row 2

        // No intent: the documented fallback is the first matching instance.
        _activeUidHint = null;
        out.push(['no-intent-idx', activeInstanceIdx()]);
        out.push(['no-intent-next', (findNextValidSong(activeInstanceIdx()) || {}).uid || null]);

        // Played the FIRST copy: advance to what follows the first copy.
        noteActiveInstance('A#1', 'test');
        out.push(['first-copy-idx', activeInstanceIdx()]);
        out.push(['first-copy-next', (findNextValidSong(activeInstanceIdx()) || {}).uid || null]);

        // Played the SECOND copy: advance to what follows the SECOND copy.
        noteActiveInstance('A#2', 'test');
        out.push(['second-copy-idx', activeInstanceIdx()]);
        out.push(['second-copy-next', (findNextValidSong(activeInstanceIdx()) || {}).uid || null]);

        // The transport leaves A entirely. A stale hint must not steer this.
        currentPos = 15;
        out.push(['moved-away-idx', activeInstanceIdx()]);
        out.push(['hint-dropped', _activeUidHint]);

        console.log(JSON.stringify(out));
        """
    ).replace("__FNS__", fns)

    got = dict(json.loads(run_node(harness)))
    expected = {
        "no-intent-idx": 0,
        "no-intent-next": "B#1",
        "first-copy-idx": 0,
        "first-copy-next": "B#1",
        # The whole point: index 2, and the song after it, not after index 0.
        "second-copy-idx": 2,
        "second-copy-next": "C#1",
        "moved-away-idx": 1,
        "hint-dropped": None,
    }
    assert got == expected, f"\ngot      {got}\nexpected {expected}"


@requires_node
def test_every_row_is_its_own_object(script_body: str) -> None:
    """Two instances must not be one object wearing two hats.

    syncRegions() used to push the shared `mainMap` entry straight into
    displayList. With a repeat that puts the SAME object at two indices, so
    chain/loop/skip — which are per-row, and the entire reason repeats are
    useful — would be shared between them, and setting one would set the other.

    Checks both that the build path constructs rows and that the constructor
    actually copies.
    """
    body = strip_comments(script_body)
    sync = strip_comments(extract_function(body, "syncRegions"))
    pushes = re.findall(r"displayList\.push\(([^;]*?)\);", sync, re.S)
    assert pushes, "syncRegions() no longer builds displayList"
    for p in pushes:
        assert "_makeInstance(" in p, (
            f"syncRegions() pushes a row that is not built by _makeInstance: "
            f"{' '.join(p.split())[:100]!r}. A shared object at two indices "
            f"means one row's Loop toggles the other's."
        )

    fn = extract_function(script_body, "_makeInstance")
    out = run_node(fn + textwrap.dedent(
        """
        var region = { id: 'A', name: 'Song A', start: 0, end: 10 };
        var a = _makeInstance(region, 'A#1', { loop: true });
        var b = _makeInstance(region, 'A#2', null);
        a.loop = false; b.chain = true; a.name = 'renamed';
        console.log(JSON.stringify({
            distinct:   a !== b,
            notSource:  a !== region && b !== region,
            uids:       [a.uid, b.uid],
            carried:    b.name === 'Song A' && b.start === 0,
            flagsFree:  [a.loop, b.loop, a.chain, b.chain],
            sourceSafe: region.name === 'Song A' && region.loop === undefined
        }));
        """
    ))
    got = json.loads(out)
    assert got == {
        "distinct": True,
        "notSource": True,
        "uids": ["A#1", "A#2"],
        "carried": True,
        # a.loop set true then false; b.loop false; a.chain false; b.chain true.
        # Nothing leaks between them.
        "flagsFree": [False, False, False, True],
        # and nothing leaks back into the region every row is copied from
        "sourceSafe": True,
    }, got


# ── Membership (#13, second half) ────────────────────────────────────────────
# A setlist is now a REPERTOIRE: tonight's songs, in order, and nothing else.
# It used to be a view of every region in the project, where exclusion was
# expressed as `skipped` — "in the list but greyed out", which is a different
# statement from "not in the list" and left no way to make the second one.

def test_off_setlist_songs_never_reach_playback(script_body: str) -> None:
    """Songs outside the set must not be in displayList.

    Transport, auto-advance and the block grouping all walk that list. A song
    nobody put in the show being in it means the show can chain into it.
    """
    body = strip_comments(script_body)
    assert re.search(r"var\s+g_offSetlist\s*=\s*\[\]", body), (
        "g_offSetlist is gone — off-setlist regions are back in displayList"
    )
    sync = strip_comments(extract_function(body, "syncRegions"))
    assert "g_offSetlist" in sync, "syncRegions() no longer separates off-setlist regions"

    # The load-bearing one: on a REFRESH, a region the set does not contain must
    # not be appended to displayList. That branch runs once a second for the
    # life of the page, so a leak there quietly re-absorbs the whole project and
    # the show can chain into a song nobody added.
    refresh = _else_branch(sync, "if (displayList.length === 0 && !initialized)")
    assert "displayList.push" not in refresh, (
        "the refresh branch of syncRegions() appends to displayList again — "
        "off-setlist regions rejoin the show, which is the behaviour #13 exists "
        "to end"
    )
    assert "g_offSetlist" in refresh, (
        "the refresh branch no longer records off-setlist regions, so the add "
        "picker goes empty a second after any edit"
    )

    # And in the bootstrap branch it may only happen for an EMPTY set.
    assert re.search(r"bootstrap\s*=\s*\(\s*saved\.length\s*===\s*0\s*\)", sync), (
        "the whole-project absorb is no longer conditional on the set being "
        "empty, so every new region silently joins the show again"
    )
    # Only the picker may read it.
    readers = [m for m in re.findall(r"function\s+(\w+)[^{]*\{", body)
               if "g_offSetlist" in _fn_body(body, m)]
    allowed = {"syncRegions", "openAddSongPicker", "addSongToSetlist", "removeFromSetlist"}
    assert set(readers) <= allowed, (
        f"g_offSetlist is read outside the picker and its two actions: "
        f"{sorted(set(readers) - allowed)}"
    )


def _fn_body(body: str, name: str) -> str:
    try:
        return extract_function(body, name)
    except AssertionError:
        return ""


def test_remove_is_not_skip(script_body: str) -> None:
    """The two mean different things and must stay separate.

    skip   = in the set, greyed out, not played tonight
    remove = not in the set at all, still in the REAPER project

    Conflating them is what the old ✕ did, and it is why there was no way to
    say "this song is not in tonight's show".
    """
    body = strip_comments(script_body)
    rm = strip_comments(extract_function(body, "removeFromSetlist"))
    assert "displayList.splice" in rm, "removeFromSetlist() does not remove the row"
    assert ".skipped" not in rm, (
        "removeFromSetlist() touches the skipped flag — removing is not skipping"
    )
    sk = strip_comments(extract_function(body, "toggleSkip"))
    assert "splice" not in sk and "g_offSetlist" not in sk, (
        "toggleSkip() has started removing rows — skipping is not removing"
    )
    for fn in ("removeFromSetlist", "addSongToSetlist", "openAddSongPicker"):
        assert "canEditSetlist()" in strip_comments(extract_function(body, fn)), (
            f"{fn}() is not gated by canEditSetlist() — #13 acceptance test 16 "
            f"requires the guard at the function, not only in CSS"
        )


@requires_node
def test_membership_actions(script_body: str) -> None:
    """Runs the real add/remove against a stubbed list.

    Covers the repeat case in both directions: adding a song already in the set
    (which AbleSet forbids and #13 requires), and removing ONE instance of a
    repeat without the song leaving the set.
    """
    fns = "\n".join(extract_function(script_body, f)
                    for f in ("removeFromSetlist", "addSongToSetlist", "_makeInstance",
                              "_findInstanceByUid", "_uidOf"))

    harness = textwrap.dedent(
        """
        var RSDiag = { log: function () {}, blocked: function () {} };
        var _uidSeq = 100;
        function _newUid(rid) { return String(rid) + '#' + (++_uidSeq); }
        function canEditSetlist() { return true; }
        function saveCurrentState() {}
        function renderSetlist() {}
        function clearSelectedRegion() { selectedRegion = null; }
        function clearQueuedRegion() { queuedRegion = null; }
        function noteActiveInstance(u) { _activeUidHint = u || null; }
        function closeAddSongPicker() {}
        var lastRenderChecksum = '', selectedRegion = null, queuedRegion = null, _activeUidHint = null;

        var A = { id: 'A', name: 'Song A', start: 0,  end: 10, duration: 10 };
        var B = { id: 'B', name: 'Song B', start: 10, end: 20, duration: 10 };
        var C = { id: 'C', name: 'Song C', start: 20, end: 30, duration: 10 };
        var displayList = [ _makeInstance(A, 'A#1', {}), _makeInstance(B, 'B#1', {}) ];
        var g_offSetlist = [ C ];

        __FNS__
        var out = [];
        var ids = function () { return displayList.map(function (r) { return r.uid; }); };
        var off = function () { return g_offSetlist.map(function (r) { return r.id; }); };

        // Add a song that is NOT in the set.
        addSongToSetlist('C');
        out.push(['added-off-setlist', ids(), off()]);

        // Add a song that IS in the set — the repeat.
        addSongToSetlist('A');
        out.push(['added-repeat', ids(), off()]);

        // Remove ONE instance of the repeat: the song stays in the set.
        removeFromSetlist('A#102');
        out.push(['removed-one-of-two', ids(), off()]);

        // Remove the last instance: now it leaves, and returns to the picker.
        removeFromSetlist('A#1');
        out.push(['removed-last', ids(), off()]);

        // Intent pointing at a removed row must not survive it.
        selectedRegion = { id: 'B', uid: 'B#1' };
        queuedRegion   = { id: 'B', uid: 'B#1' };
        _activeUidHint = 'B#1';
        removeFromSetlist('B#1');
        out.push(['intent-cleared', [selectedRegion, queuedRegion, _activeUidHint]]);

        console.log(JSON.stringify(out));
        """
    ).replace("__FNS__", fns)

    got = {row[0]: row[1:] for row in json.loads(run_node(harness))}
    assert got["added-off-setlist"] == [["A#1", "B#1", "C#101"], []], got["added-off-setlist"]
    # The repeat: two rows for A, and A is NOT put back in the picker.
    assert got["added-repeat"] == [["A#1", "B#1", "C#101", "A#102"], []], got["added-repeat"]
    # One instance gone, the song still in the set, picker untouched.
    assert got["removed-one-of-two"] == [["A#1", "B#1", "C#101"], []], got["removed-one-of-two"]
    # Last instance gone: now it goes back to the picker.
    assert got["removed-last"] == [["B#1", "C#101"], ["A"]], got["removed-last"]
    assert got["intent-cleared"] == [[None, None, None]], got["intent-cleared"]


# ── Sections, loop, and the panels that read them ────────────────────────────
# The identity refactor moved every song DOM id to a uid and scoped every
# section id by its parent row. Four subsystems read those: Live View, Canvas,
# the lyrics/chords panels, and the per-section loop. Three regressions got
# through and hit EVERY setlist, not only repeats — these lock all of it.

def test_uids_are_valid_css_identifiers(script_body: str) -> None:
    """A uid ends up inside a DOM id, and a DOM id ends up inside a selector.

    `#` opens a new id token and `.` opens a class token, so a uid built with
    either does not make querySelector *miss* — it makes it THROW. getElementById
    tolerates both, which is exactly why it hid: every lookup worked except the
    one that used a selector, and that one was `flashRow`, whose only job is a
    200ms colour flash nobody would report.
    """
    body = strip_comments(script_body)
    for name, pat in (("UID_SEP", r"var\s+UID_SEP\s*=\s*'([^']*)'"),
                      ("SUB_UID_SEP", r"var\s+SUB_UID_SEP\s*=\s*'([^']*)'")):
        m = re.search(pat, body)
        assert m, f"{name} is gone — the separator is back to a literal"
        sep = m.group(1)
        assert re.fullmatch(r"[_a-zA-Z0-9-]+", sep), (
            f"{name} is {sep!r}, which cannot appear in a CSS identifier. "
            f"Any selector built from a uid will throw SyntaxError."
        )
    # And a whole uid, prefix included, must still parse as one.
    for sample in ("row-12_3", "subrow-12_3__7", "loop-counter-sub-12_3__7"):
        assert re.fullmatch(r"-?[_a-zA-Z][_a-zA-Z0-9-]*", sample), sample


def test_no_selector_is_built_from_a_uid(script_body: str) -> None:
    """Belt and braces on top of the separator.

    Even with safe separators, interpolating an id into a selector is a trap
    waiting for the next separator change. Resolve by id, then search within.
    """
    body = strip_comments(script_body)
    for m in re.finditer(r"querySelector(?:All)?\(\s*[\"']#[^\"']*[\"']\s*\+", body):
        raise AssertionError(
            f"a selector is built by concatenating onto an id: "
            f"{body[m.start():m.start()+90]!r}"
        )
    flash = strip_comments(extract_function(body, "flashRow"))
    assert "getElementById" in flash, (
        "flashRow builds a selector from a uid again — that is the call that "
        "threw SyntaxError on every Next/Previous"
    )


def test_auto_expand_reads_and_writes_the_same_key(script_body: str) -> None:
    """The guard read expandedSongs[uid] while the call wrote expandedSongs[id].

    The key was therefore never set, so auto-expand re-fired on every song
    change and toggleExpand looked up slist-/chev-/row- ids built from a region
    id — none of which are rendered. Auto-expand was dead for every setlist,
    repeat or not, and silently.
    """
    body = strip_comments(script_body)
    m = re.search(r"expandedSongs\[activeRegion\.(\w+)\]\)\s*\{\s*toggleExpand\(activeRegion\.(\w+)",
                  body, re.S)
    assert m, "the auto-expand block is gone or reshaped — re-check it by hand"
    assert m.group(1) == m.group(2) == "uid", (
        f"auto-expand guards on .{m.group(1)} but calls with .{m.group(2)}. "
        f"toggleExpand has no region-id fallback, so a mismatch here is not a "
        f"degraded lookup, it is a dead feature."
    )


def test_section_tap_carries_both_identities(script_body: str) -> None:
    """A section belongs to a ROW, and the two identities do different jobs.

    The highlight paints on the section row (`subrow-<parentUid>__<subId>`); the
    active-instance hint must name the PARENT row, because activeInstanceIdx()
    only ever matches uids of displayList rows. Handing it a bare sub id means
    the hint is dropped as stale on the very next tick.
    """
    body = strip_comments(script_body)
    resolve = strip_comments(extract_function(body, "_resolveTapTarget"))
    assert "SUB_UID_SEP" in resolve, (
        "_resolveTapTarget no longer recognises a scoped section uid, so a "
        "section tap falls through to the raw g_subRegionMap object — which has "
        "no uid, so nothing highlights"
    )
    assert "ownerUid" in resolve, "the parent row is not recorded"
    assert re.search(r"for\s*\(var\s+key\s+in\s+found\)", resolve), (
        "_resolveTapTarget mutates the shared g_subRegionMap entry instead of "
        "copying it — both instances of a repeat read that object"
    )
    for fn in ("selectRegionForCue", "cueRegion", "togglePlay"):
        src = strip_comments(extract_function(body, fn))
        if "noteActiveInstance" not in src:
            continue
        assert "_ownerUidOf" in src, (
            f"{fn}() hints activeInstanceIdx() with _uidOf instead of "
            f"_ownerUidOf — for a section tap that is a uid no row carries"
        )


def test_position_keyed_dedups_reset_on_section_change(script_body: str) -> None:
    """Two instances of one song occupy the IDENTICAL positions.

    `_lastSpecialTriggerPos` is keyed on an absolute position, so in a set
    containing A, A the SONG END / STOP marker fired for the first copy and was
    then suppressed forever for the second — which ran straight past it.
    """
    body = strip_comments(script_body)
    m = re.search(r"window\._prevActiveSubId\s*!==\s*(\w+)\)\s*\{(.*?)\n\s{20}\}", body, re.S)
    assert m, "the section-change reset block is gone or reshaped"
    reset = m.group(2)
    for flag in ("_lastPauseTriggerPos", "_lastTransitionTriggerPos",
                 "_lastLoopFireKey", "_lastSpecialTriggerPos"):
        assert flag in reset, (
            f"{flag} is no longer reset on a section change. If it is keyed on "
            f"a position or a bare sub id, the second instance of a repeat "
            f"inherits the first's spent state."
        )
    # Scoped to the block, not the file: `_subUid(activeRegion, activeSub)`
    # appears elsewhere for the section DOM ids, so a file-wide search is
    # satisfied by those and never sees this key revert.
    key_var = m.group(1)
    assign = re.search(r"var\s+" + re.escape(key_var) + r"\s*=\s*([^;]+);", body)
    assert assign, (
        f"_prevActiveSubId is compared against {key_var!r}, which is not "
        f"assigned nearby — check the block by hand"
    )
    assert "_subUid(" in assign.group(1), (
        f"the section-change key is {assign.group(1).strip()!r}, a bare sub id. "
        f"A song whose sections cover it end to end with ONE section re-enters "
        f"the same id when playback crosses from one instance to the next, so "
        f"loopCount and _loopExhausted never reset and the second copy starts "
        f"with the first's spent loop."
    )


def test_every_row_control_passes_the_row(script_body: str) -> None:
    """Every playRegion call site rendered into a row must carry its uid.

    The one in the expanded 'Play Song' button did not, so pressing it inside
    the second instance cued the FIRST — and then hinted the wrong row, which
    is the half that makes the show jump.
    """
    body = strip_comments(script_body)
    calls = re.findall(r"playRegion\((?:'\s*\+\s*)?[^)]*?\)", body)
    rendered = [c for c in calls if "r.start" in c or "sub.start" in c]
    assert rendered, "no rendered playRegion call sites found — check the pattern"
    for c in rendered:
        assert c.count("+") >= 4 and ("r.uid" in c or "_subUid" in c), (
            f"a rendered playRegion call omits the row: {c[:110]!r}"
        )


@requires_node
def test_section_tap_resolution(script_body: str) -> None:
    """Runs the real _resolveTapTarget against a repeated song's section."""
    fns = "\n".join(extract_function(script_body, f)
                    for f in ("_resolveTapTarget", "_ownerUidOf", "_uidOf",
                              "_findInstanceByUid", "_findRegionById", "_subUid"))
    harness = textwrap.dedent(
        """
        var UID_SEP = '_', SUB_UID_SEP = '__';
        var CHORUS = { id: 'sub9', name: 'Chorus', start: 4, end: 8 };
        var displayList = [
            { id: 'A', uid: 'A_1', start: 0, end: 10 },
            { id: 'B', uid: 'B_2', start: 10, end: 20 },
            { id: 'A', uid: 'A_3', start: 0, end: 10 }
        ];
        var g_subRegionMap = { 'Song A': [CHORUS] };
        __FNS__

        // Tapping the Chorus inside the SECOND instance of Song A.
        var t = _resolveTapTarget('sub9', 'A_3__sub9', 4);
        console.log(JSON.stringify({
            // paints on the section row of the second instance...
            paintUid: _uidOf(t),
            // ...but the active-instance hint names that instance's ROW
            hintUid:  _ownerUidOf(t),
            keptCoords: [t.start, t.end],
            // and the shared section object was not mutated
            sourceClean: CHORUS.uid === undefined && CHORUS.ownerUid === undefined,
            // a plain song tap still resolves to the row itself
            songUid: _ownerUidOf(_resolveTapTarget('A', 'A_3', 0))
        }));
        """
    ).replace("__FNS__", fns)
    got = json.loads(run_node(harness))
    assert got == {
        "paintUid": "A_3__sub9",
        "hintUid": "A_3",
        "keptCoords": [4, 8],
        "sourceClean": True,
        "songUid": "A_3",
    }, got


# ── What happens when a song ends ────────────────────────────────────────────
# The most important decision in the app, and until this test the only one with
# no automated coverage at all: seven branches inlined in updatePlaybackUI,
# tangled with DOM reads and wwr_req calls, so it could not be asked a question
# without a running REAPER.

@requires_node
def test_what_happens_when_a_song_ends(script_body: str) -> None:
    """Runs the real resolveBoundaryAction() across all seven branches.

    The three cases the show actually depends on:
      * set to continue  → the next song plays, uninterrupted
      * set to stop      → it stops, and the next Play starts the right song
      * queued mid-song  → the queue replaces the natural next
    """
    fn = extract_function(script_body, "resolveBoundaryAction")

    harness = textwrap.dedent(
        """
        var A = { id: 'A', start: 0,  end: 10 };
        var B = { id: 'B', start: 10, end: 20 };   // the natural next
        var Q = { id: 'Q', start: 90, end: 99 };   // a queued song

        __FN__

        // The context fields are NOT independent: getSongEnd() derives the
        // end-state from stopAfter / delayAfter / chain, and effectiveSongEnd()
        // then resolves 'auto' against the global toggle. Deriving it here the
        // same way makes an impossible fixture impossible to write — the first
        // draft of this test asked what happens to a song that is set to WAIT
        // and to CONTINUE at once, which cannot occur.
        function endStateOf(region, stopAfter, delayAfter, autoStop) {
            if (stopAfter)      return 'stop';
            if (delayAfter > 0) return 'wait';
            if (region.chain)   return 'continue';
            return autoStop ? 'stop' : 'continue';   // 'auto', resolved
        }
        function ctx(over) {
            var base = {
                region: A, nativeLoopSubId: null, queued: null,
                stopAfter: false, delayAfter: 0, next: B, autoStop: false,
                playRegionLocked: false
            };
            for (var k in over) if (over.hasOwnProperty(k)) base[k] = over[k];
            base.endState = endStateOf(base.region, base.stopAfter, base.delayAfter, base.autoStop);
            return base;
        }
        function run(label, over) {
            var r = resolveBoundaryAction(ctx(over));
            return [label, r.action, (r.target || r.cue || {}).id || null, !!r.fromQueue];
        }

        console.log(JSON.stringify([
          // ── 1. PLAY STRAIGHT ON ───────────────────────────────────────────
          run('chain-flag',      { region: { id:'A', start:0, end:10, chain:true }, autoStop:true }),
          run('auto-stop-off',   { autoStop: false }),

          // ── 2. STOP AT THE END ────────────────────────────────────────────
          run('auto-stop-on',    { autoStop: true }),
          run('per-song-stop',   { stopAfter: true, autoStop: false }),
          // Per-song stop beats a global "keep playing".
          run('stop-beats-auto', { stopAfter: true, autoStop: false }),

          // ── 3. TAPPED ANOTHER SONG WHILE PLAYING ──────────────────────────
          // Continue + queued: the queue replaces the natural next.
          run('queued-continue', { queued: Q, autoStop: false }),
          // Stop + queued: the STOP STANDS. The queue only decides what the
          // next Play will start. This is #9's precedence rule, and it is the
          // one that looks surprising until you have run a block on stage.
          run('queued-vs-stop',  { queued: Q, autoStop: true }),
          run('queued-vs-stopafter', { queued: Q, stopAfter: true }),

          // ── the rest ──────────────────────────────────────────────────────
          run('song-loop',       { region: { id:'A', start:0, end:10, loop:true } }),
          run('native-loop',     { region: { id:'A', start:0, end:10, loop:true }, nativeLoopSubId: 'A' }),
          run('wait',            { delayAfter: 5 }),
          run('wait-queued',     { delayAfter: 5, queued: Q }),
          // A wait with nowhere to go falls THROUGH, exactly as the inlined
          // version did — it does not swallow the boundary.
          run('wait-no-target',  { delayAfter: 5, next: null, autoStop: true }),
          run('end-of-setlist',  { next: null, autoStop: false }),
          // A Play issued moments ago outranks a stop built from a stale reply.
          run('play-just-issued',{ autoStop: true, playRegionLocked: true })
        ]));
        """
    ).replace("__FN__", fn)

    got = {row[0]: row[1:] for row in json.loads(run_node(harness))}
    expected = {
        # plays straight on, into B
        "chain-flag":         ["chain", "B", False],
        "auto-stop-off":      ["chain", "B", False],
        # stops, and B is what the next Play starts
        "auto-stop-on":       ["auto-stop", "B", False],
        "per-song-stop":      ["stop-after", "B", False],
        "stop-beats-auto":    ["stop-after", "B", False],
        # the queue replaces the natural next
        "queued-continue":    ["queued", "Q", True],
        # ...but never overrides a stop; it becomes the cue instead
        "queued-vs-stop":     ["auto-stop", "Q", True],
        "queued-vs-stopafter":["stop-after", "Q", True],
        "song-loop":          ["song-loop", "A", False],
        "native-loop":        ["native-loop", None, False],
        "wait":               ["wait", "B", False],
        "wait-queued":        ["wait", "Q", True],
        "wait-no-target":     ["auto-stop", None, False],
        "end-of-setlist":     ["none", None, False],
        "play-just-issued":   ["none", None, False],
    }
    assert got == expected, (
        "\n" + "\n".join(
            f"  {k:22} got {got.get(k)!s:32} expected {v}"
            for k, v in expected.items() if got.get(k) != v
        )
    )


def test_the_boundary_decision_has_no_side_effects(script_body: str) -> None:
    """It must stay pure, or the test above stops meaning anything.

    Every side effect — the commands, the locks, the queue promotion — belongs
    to the caller. A wwr_req sneaking in here would make the decision
    untestable again and, worse, would look tested.
    """
    body = strip_comments(extract_function(strip_comments(script_body), "resolveBoundaryAction"))
    for forbidden in ("wwr_req", "document.", "window.", "clearQueuedRegion",
                      "promoteQueuedToSelected", "noteActiveInstance", "Date.now"):
        assert forbidden not in body, (
            f"resolveBoundaryAction() reaches for {forbidden} — it is no longer a "
            f"decision, and the seven-branch test above is now asserting against "
            f"something that also acts"
        )
