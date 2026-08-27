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


# ── The Director lease, and the false positives that took one off the air ────

def test_an_incumbent_director_needs_evidence_to_be_displaced(script_body: str) -> None:
    """Absence of evidence is not evidence of a competitor.

    `_directorClaimId` is only filled by the 2s probe reply, so at the 2.6s
    deadline it can still hold '' (no reply yet) or a STALE id from another
    device's earlier session — ExtState survives the REAPER session, not the
    browser's. Both used to read as "somebody else claimed it", so a working
    Director stood down with nobody else in the room, and then stopped beating,
    which let the next device legitimately claim the role. The story became
    self-confirming.

    A NEW claim must still fail closed. Re-verifying an incumbent must not.
    """
    body = strip_comments(script_body)
    lease = strip_comments(extract_function(body, "requestDirectorLease"))
    assert "keepUnlessDisplaced" in lease, (
        "requestDirectorLease() no longer distinguishes a new claim from a "
        "re-verification, so one of the two rules is wrong for its caller"
    )
    m = re.search(r"won\s*=\s*keepUnlessDisplaced\s*\?\s*([^:]+):\s*(.+?);", lease, re.S)
    assert m, "the two decisions are no longer expressed as one conditional"
    incumbent, fresh = m.group(1), m.group(2)
    assert "_directorClaimId" not in incumbent, (
        "an incumbent's lease still depends on the claim read-back arriving in "
        "time — that is the false negative that took a Director off the air"
    )
    assert "displaced" in incumbent, "an incumbent stands down on nothing at all"
    assert "_directorClaimId" in fresh and "displaced" in fresh, (
        "a NEW claim no longer fails closed — that is how two devices end up "
        "driving one REAPER"
    )

    verify = strip_comments(extract_function(body, "_dcVerifyStoredDirector"))
    assert "keepUnlessDisplaced" in verify, (
        "the stored-Director boot check asks for the strict new-claim rule, so "
        "it can still stand down on a missing reply"
    )


def test_the_displaced_banner_does_not_invent_a_takeover(script_body: str) -> None:
    """It said "another device is now the Director" unconditionally.

    When the stand-down had nothing to do with another device, that sent people
    looking for a phone that was not there.
    """
    body = strip_comments(script_body)
    banner = strip_comments(extract_function(body, "_setDisplacedBanner"))
    assert "_dcForeignActive()" in banner, (
        "the displaced banner names a takeover without checking that one "
        "happened"
    )
    assert "stepped down" in banner, "there is no message for the no-takeover case"


def test_a_warning_banner_does_not_cover_what_it_warns_about() -> None:
    """The banner is position:fixed directly under the top bar.

    Without room made for it, it sits ON the setlist row — and that row carries
    the ACTIVE SETLIST'S NAME, which is the one thing a musician needs while a
    warning is telling them something changed. Reported from a real device: the
    banner covered the row and the list looked broken.
    """
    html = REASET_HTML.read_text(encoding="utf-8")

    stack = re.search(r"#reaset-banner-stack\s*\{([^}]*)\}", html)
    assert stack and "position: fixed" in stack.group(1), (
        "the banner is no longer fixed — if it now sits in the flow, this test "
        "and the offset below are both obsolete, so re-check the layout by hand"
    )

    topbar = re.search(r"\.app-topbar\s*\{([^}]*)\}", html)
    assert topbar, ".app-topbar rule is gone"
    assert "var(--reaset-banner-h)" in topbar.group(1), (
        "nothing makes room for the banner after the top bar, so it covers the "
        "setlist row again"
    )

    content_top = re.search(r"--reaset-content-top:\s*([^;]+);", html)
    assert content_top, "--reaset-content-top is gone"
    assert "--reaset-banner-h" in content_top.group(1), (
        "the full-screen views start below the top bar but ABOVE the banner, so "
        "a warning covers Live / Canvas / Lyrics content too"
    )

    scripts = inline_scripts(html)[0]
    measure = strip_comments(extract_function(scripts, "_bannerMeasure"))
    assert "--reaset-banner-h" in measure and "offsetHeight" in measure, (
        "the banner height is no longer measured. It must not be assumed: the "
        "text wraps to one or two lines depending on width and language, so a "
        "hardcoded value is wrong on exactly the devices this matters for."
    )


@requires_node
def test_only_one_view_can_be_open(script_body: str) -> None:
    """Lyrics, Chords, Live and Canvas are all `position: fixed; inset: 0`.

    Two of them open at once is not a layout that exists — the higher z-index
    covers the lower one completely. They were tracked as four independent
    booleans and opening one never closed the others, so
    Lyrics → Chords → Canvas left all three flagged open, two invisible
    underneath, and the tab row lit three tabs. That is what "it never
    deselects" was.

    Runs the real toggles and asserts the invariant after every transition.
    """
    fns = "\n".join(extract_function(script_body, f) for f in (
        "closeOtherViews", "toggleLyricsPanel", "toggleChordsPanel",
        "openCanvasMode", "closeCanvasMode", "openLiveView", "closeLiveView",
        "updateTopTabs",
    ))

    harness = textwrap.dedent(
        """
        var lyricsVisible = false, chordsVisible = false;
        var liveViewOpen = false, canvasOpen = false;
        var _lrmLastSongId = null;
        var currentSetlistName = 'Default';
        var classes = {};
        function stubEl(id) {
            classes[id] = classes[id] || {};
            return {
                classList: {
                    add:      function (c) { classes[id][c] = true; },
                    remove:   function (c) { classes[id][c] = false; },
                    contains: function (c) { return !!classes[id][c]; },
                    toggle:   function (c, on) { classes[id][c] = !!on; }
                },
                innerText: '', style: {}
            };
        }
        document = { getElementById: stubEl };
        function wwr_req() {}
        function updatePlaybackUI() {}
        function toggleCanvasEdit() {}
        function closeLiveConfig() {}
        function applyLiveSettings() {}
        function _setViewTabActive(name, on) { classes['tab-' + name] = { active: !!on }; }

        __FNS__

        function openCount() {
            return [lyricsVisible, chordsVisible, liveViewOpen, canvasOpen]
                   .filter(Boolean).length;
        }
        function litTabs() {
            return ['show','lyrics','chords','live','canvas']
                   .filter(function (n) { return classes['tab-' + n] && classes['tab-' + n].active; });
        }

        var out = [];
        function step(label, fn) {
            fn();
            updateTopTabs();
            out.push([label, openCount(), litTabs()]);
        }

        // The exact sequence from the bug report.
        step('lyrics',            function () { toggleLyricsPanel(); });
        step('then-chords',       function () { toggleChordsPanel(); });
        step('then-canvas',       function () { openCanvasMode(); });
        step('then-live',         function () { openLiveView(); });
        step('back-to-lyrics',    function () { toggleLyricsPanel(); });
        // A second press on the open view closes it and lands back on SHOW.
        step('toggle-off',        function () { toggleLyricsPanel(); });
        // Closing an overlay directly also lands on SHOW.
        step('canvas-then-close', function () { openCanvasMode(); closeCanvasMode(); });

        console.log(JSON.stringify(out));
        """
    ).replace("__FNS__", fns)

    rows = json.loads(run_node(harness))
    for label, open_count, lit in rows:
        assert open_count <= 1, (
            f"after {label!r}: {open_count} views open at once. They are all "
            f"full-screen overlays, so the ones underneath are invisible and "
            f"their tabs stay lit forever."
        )
        assert len(lit) == 1, (
            f"after {label!r} the tab row lights {lit} — exactly one tab must "
            f"be active, always"
        )

    got = {r[0]: r[2][0] for r in rows}
    assert got == {
        "lyrics": "lyrics",
        "then-chords": "chords",
        "then-canvas": "canvas",
        "then-live": "live",
        "back-to-lyrics": "lyrics",
        "toggle-off": "show",
        "canvas-then-close": "show",
    }, got


@requires_node
def test_closing_reaper_ends_the_session(script_body: str) -> None:
    """The idle rule alone could not express this, and that is why it shipped
    showing six hours.

    Quit REAPER at 20:00 after playing at 17:00, come back at 23:00: the gap
    since the last playback is three hours, under the four-hour idle threshold,
    so the clock restored and displayed six. Correct by its own rule, and wrong.

    Reaset.lua's `tick` starts at 0 on every run, so a tick LOWER than the
    highest one seen means it restarted — which means REAPER did.
    """
    fns = "\n".join(extract_function(script_body, f)
                    for f in ("_sessionObserveLuaTick", "_sessionClear"))

    harness = textwrap.dedent(
        """
        var NOW = 1000000000000;
        Date.now = function () { return NOW; };
        var RSDiag = { log: function () {} };
        var SESSION_TICK_KEY = 'reaset_lua_tick', SESSION_KEY = 'reaset_session_start';
        var SESSION_TICK_WRITE_MS = 30 * 1000;
        var store = {};
        var localStorage = {
            getItem: function (k) { return store.hasOwnProperty(k) ? store[k] : null; },
            setItem: function (k, v) { store[k] = String(v); },
            removeItem: function (k) { delete store[k]; }
        };
        var _sessionStart = null, _sessionSeen = 0, _sessionSeenWritten = 0;
        var _sessionRemoteSec = null, _sessionRemoteAt = 0;
        var _luaTickSeen = null, _luaTickWritten = 0;
        var published = [];
        function _sessionPublish() { published.push(_sessionStart); }
        function _tickSessionClock() {}

        __FNS__

        function armed(startAgoMs) {
            _sessionStart = NOW - startAgoMs; _sessionSeen = NOW; _sessionSeenWritten = NOW;
            store[SESSION_KEY] = 'x';
            _sessionRemoteSec = 300; _sessionRemoteAt = NOW;
        }
        var out = [];

        // A run of REAPER, ticking upward. Nothing resets.
        armed(6 * 3600 * 1000);
        _sessionObserveLuaTick('0');
        NOW += 40000; _sessionObserveLuaTick('75');
        NOW += 40000; _sessionObserveLuaTick('150');
        out.push(['ticking-up-keeps-clock', _sessionStart !== null, _luaTickSeen]);

        // REAPER restarts: the counter goes back to 0.
        NOW += 3 * 3600 * 1000;
        _sessionObserveLuaTick('0');
        out.push(['restart-clears', _sessionStart, store[SESSION_KEY] || null,
                  _sessionRemoteSec, _sessionRemoteAt]);

        // A fresh browser, REAPER still running past the persisted mark.
        store[SESSION_TICK_KEY] = '5000';
        _luaTickSeen = 5000; _luaTickWritten = 0;
        armed(600000);
        _sessionObserveLuaTick('6000');
        out.push(['still-running-keeps-clock', _sessionStart !== null]);

        // A fresh browser, REAPER restarted while it was closed. THE REPORTED CASE.
        store[SESSION_TICK_KEY] = '5000';
        _luaTickSeen = 5000; _luaTickWritten = 0;
        armed(6 * 3600 * 1000);
        _sessionObserveLuaTick('15');
        out.push(['reopened-after-restart-clears', _sessionStart]);

        // The script is not running: '' must not be read as a restart.
        _luaTickSeen = 5000;
        armed(600000);
        _sessionObserveLuaTick('');
        out.push(['no-script-keeps-clock', _sessionStart !== null, _luaTickSeen]);

        // The high-water mark is persisted, but not on every tick.
        store = {}; _luaTickSeen = null; _luaTickWritten = 0;
        _sessionObserveLuaTick('10');
        var afterFirst = store[SESSION_TICK_KEY];
        NOW += 1000; _sessionObserveLuaTick('20');
        var afterSecond = store[SESSION_TICK_KEY];
        NOW += 60000; _sessionObserveLuaTick('30');
        out.push(['write-throttled', afterFirst, afterSecond, store[SESSION_TICK_KEY]]);

        console.log(JSON.stringify(out));
        """
    ).replace("__FNS__", fns)

    got = {r[0]: r[1:] for r in json.loads(run_node(harness))}
    assert got["ticking-up-keeps-clock"] == [True, 150], got["ticking-up-keeps-clock"]
    # Cleared: local start gone, storage gone, AND the Director's published
    # anchor dropped — otherwise a follower keeps extrapolating from the old one
    # across exactly the event that was meant to zero them both.
    assert got["restart-clears"] == [None, None, None, 0], got["restart-clears"]
    assert got["still-running-keeps-clock"] == [True], got["still-running-keeps-clock"]
    assert got["reopened-after-restart-clears"] == [None], got["reopened-after-restart-clears"]
    # '' means the script is not running. It is not evidence of a restart, and
    # treating it as one would zero the clock every time Reaset.lua is stopped.
    assert got["no-script-keeps-clock"] == [True, 5000], got["no-script-keeps-clock"]
    # First write lands; the one a second later does not; the one a minute later does.
    assert got["write-throttled"] == ["10", "10", "30"], got["write-throttled"]


def test_an_automatic_session_reset_is_not_director_gated(script_body: str) -> None:
    """A REAPER restart happens to every device at once.

    resetSessionClock() is the LONG-PRESS, and stays Director-only because the
    Director owns the clock. The automatic path must not borrow that gate, or
    a Controller would keep counting from a session that ended.
    """
    body = strip_comments(script_body)
    clear = strip_comments(extract_function(body, "_sessionClear"))
    assert "REASET_MODE" not in clear, (
        "_sessionClear() is role-gated, so an automatic reset skips every "
        "Controller and the devices disagree about what time it is"
    )
    press = strip_comments(extract_function(body, "resetSessionClock"))
    assert re.search(r"""REASET_MODE\s*!==\s*['"]director['"]\s*\)\s*return""", press), (
        "the long-press reset lost its Director gate — a follower's would be "
        "overwritten by the next published tick half a second later"
    )
    assert "_sessionClear(" in press, "the two reset paths have drifted apart"


# ── The phone transport bar ─────────────────────────────────────────────────
#
# Four controls share about 340px on a phone. Split by flex weight, STOP landed
# at ~75px: "SLIDE TO STOP" wrapped to three lines, the button grew to ~70px
# tall, the thumb — which stretches top to bottom — became a 46x62 blob that
# read as an oversized circle spilling out of its track, and the gesture had
# 23px of travel. Every one of those is a separate rule below, because each one
# on its own is enough to make the control unusable in front of an audience.


def _css_decls(html: str, selector: str) -> str:
    """The declaration block of the LAST rule whose selector list includes one.

    Last, not first: CSS cascade means a later rule of equal specificity wins,
    so asserting against the first one would pass while the screen disagrees.

    Anchored to a rule at the stylesheet's own indentation — eight spaces —
    for two reasons that bit in the same afternoon. An unanchored
    ".stop-ctl.is-slide" also matches inside ".app-transport .stop-ctl.is-slide",
    so a mutation that gutted the base rule survived by leaving the phone
    override intact. And a merely line-anchored one matches rules nested in a
    @media block, which are indented further: the last match became a tablet
    override carrying one font-size, and the base rule went unread.

    Matches a GROUPED selector too — `.a, .b { }` is one rule that styles both,
    and an exact-string match silently reported it missing, which reads as "you
    deleted this" when the truth is "two selectors now share a block".
    """
    # Comments first. A rule's explanation sits directly above it at the same
    # indentation, so without this the match starts at the comment and the
    # "selector list" is a paragraph of prose with the selector glued on the
    # end — which reports every documented rule as missing.
    css = re.sub(r"/\*.*?\*/", "", html, flags=re.S)
    pat = re.compile(r"(?m)^ {8}(?! )([^{}]*?)\{([^{}]*)\}")
    found = [
        body for sels, body in pat.findall(css)
        if selector in [s.strip() for s in sels.split(",")]
    ]
    assert found, f"no CSS rule for {selector!r} — it was renamed or deleted"
    return found[-1]


def test_play_is_the_only_control_that_grows() -> None:
    """Area is hierarchy, and the bar had it backwards.

    PLAY was 17% of the transport bar while a full-red Stop slide took 48%: the
    loudest colour and the largest target belonged to the one action nobody
    wants to trigger by accident, and the control the whole bar exists for was
    the smallest thing on it. From the far end of a stage, in peripheral
    vision, size is the only hierarchy that survives.

    So exactly one control in the main row grows, and it is PLAY. Loop and
    RECONNECT are fixed: whatever width is left over is PLAY's.
    """
    html = REASET_HTML.read_text(encoding="utf-8")

    play = _css_decls(html, ".t-btn-play")
    assert re.search(r"flex:\s*1\b", play), (
        "PLAY no longer absorbs the leftover width, so the bar is back to "
        "splitting by weight — which is how Stop came to be three times its size"
    )

    for sel, why in [
        (".t-btn-loop", "Loop"),
        (".t-btn-nav", "Previous and Next"),
    ]:
        decls = _css_decls(html, sel)
        assert re.search(r"flex:\s*0 0 auto", decls) and "width:" in decls, (
            f"{why} can grow again — anything that grows beside PLAY takes "
            f"width from the one control that should have it all"
        )


def test_play_button_keeps_its_word_in_a_span(script_body: str) -> None:
    """Every writer of the PLAY button must emit the same two spans.

    The label used to be written as a flat string on every play/pause. The phone
    hides .t-lbl and keeps .t-ico, so the first transport change after load put
    the word back and re-crammed the bar the slider needs — a layout that is
    correct only until someone presses play.
    """
    html = REASET_HTML.read_text(encoding="utf-8")

    markup = re.search(r'<button[^>]*id="main-play-btn"[^>]*>(.*?)</button>', html, re.S)
    assert markup, "the main PLAY button is gone"
    assert 't-ico' in markup.group(1) and 't-lbl' in markup.group(1), (
        "PLAY's glyph and word are not separate spans, so the phone cannot drop "
        "the word without dropping the symbol too"
    )

    # Not "up to the next semicolon": the spans contain HTML entities, and
    # &#9646; ends in one. A fixed window past the assignment is enough to see
    # the whole expression and immune to what the value happens to contain.
    stripped = strip_comments(script_body)
    writes = [
        stripped[m.end():m.end() + 320]
        for m in re.finditer(r"playBtn\.innerHTML\s*=", stripped)
    ]
    assert writes, "nothing writes the PLAY button any more"
    for write in writes:
        assert "t-ico" in write and "t-lbl" in write, (
            "a writer of the PLAY button emits a flat label instead of the two "
            f"spans, so the phone bar re-crams on the next transport change: {write.strip()[:90]}"
        )


def test_transport_bar_reserves_space_without_flex_gap() -> None:
    """`gap` in a flex container is a no-op on the engine this must run on.

    WebKit did not support it until 14.1. Where it is the only thing separating
    the controls, they fuse into one bar-shaped slab — and every target on it
    becomes adjacent to every other, on the screen where a mis-tap stops the
    show.
    """
    html = REASET_HTML.read_text(encoding="utf-8")

    bar_css = html[html.index("        .app-transport {"):html.index("        .t-btn-loop {")]
    assert not re.search(r"^\s*(gap|column-gap|row-gap)\s*:", bar_css, re.M), (
        "the transport bar is spacing itself with flex `gap` again — it "
        "resolves to zero on the tablet this has to run on"
    )
    assert re.search(r"\.app-transport\s*>\s*\.t-btn\s*\{[^{}]*margin-right", bar_css), (
        "nothing reserves the space between the transport controls"
    )


# ── Legacy WebKit ────────────────────────────────────────────────────────────
# ReaSet has to run on an iPad that no longer receives updates. Chrome on iOS
# is the system WebKit with a different icon, so "install another browser" is
# not a fix — the engine is whatever the last iOS for that device shipped.
#
# None of what follows is a parse error, which is why none of it would show up
# in review: the engine drops the declaration it cannot read and renders
# something plausible-but-wrong. A modal backdrop that darkens a 40x20 corner.
# A song title sized for a stage rendering at body-text size. Controls with no
# space between them on a touch screen.


def test_flex_gap_has_a_fallback_for_every_container() -> None:
    """`gap` in a flex container is a no-op before WebKit 14.1.

    Not a degraded layout — zero. Every control the gap separates ends up
    touching the next one, and on a touch UI two adjacent targets with no space
    between them is a mis-tap waiting to happen.

    The burden is inverted on purpose. The first version of this test asked
    "is this rule a flex container?" by looking for `display: flex` in the same
    rule, and five containers walked straight through it: each was
    `display: none` in its own rule and became flex from a state rule or a
    shared class somewhere else. A test that has to recognise flex cannot be
    trusted to, because the stylesheet is free to say it anywhere.

    So instead: a gap declaration must ANNOUNCE itself as grid in its own rule,
    or carry a fallback. Anything else fails. A new flex gap with no fallback
    fails, and so does a grid gap that does not say it is one — which is a
    convention, not a burden.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    css = html[html.index("<style>"):html.index("</style>")]

    unguarded = []
    for m in re.finditer(r"([^{}]*)\{([^{}]*)\}", css):
        sel = m.group(1).strip().split("\n")[-1].strip()
        body = m.group(2)
        if not re.search(r"^\s*gap\s*:", body, re.M):
            continue
        if sel.startswith("html.no-flexgap"):
            continue
        if "display: grid" in body or "display: inline-grid" in body:
            # Grid gap works on the target engine. grid-gap takes it back
            # further still, and costs one line.
            assert "grid-gap" in body, (
                f"{sel} uses grid gap with no grid-gap twin, so it collapses "
                f"on anything before Safari 12"
            )
            continue
        if ("html.no-flexgap " + sel + " >") not in css:
            unguarded.append(sel)

    assert not unguarded, (
        f"{len(unguarded)} gap rule(s) neither declare themselves grid nor "
        f"carry a margin fallback, so their children touch on the tablet this "
        f"has to run on: {unguarded}"
    )

    # The gate. Without it the fallback and a working gap both apply.
    assert ".no-flexgap" in css, "the fallback rules are no longer gated"
    body = strip_comments(inline_scripts(html)[0])
    detect = strip_comments(extract_function(body, "detectFlexGap"))
    assert "scrollWidth" in detect, (
        "flex-gap support is no longer MEASURED — a UA string cannot answer "
        "this, since Chrome on iOS reports Chrome and runs the failing engine"
    )
    assert "no-flexgap" in detect, "the detect no longer sets the class it exists to set"
    assert "removeChild" in detect, "the probe element is left in the document"


def test_ios12_vendor_prefixes_are_present() -> None:
    """Three properties that need -webkit- on the engine this has to run on.

    `position: sticky` is the one that matters: unprefixed alone it is not
    degraded, it is ignored, so the element is plain `static` and the topbar
    scrolls away with the setlist. The other two are cosmetic by comparison —
    an unblurred panel, a label that selects when a finger drags across it.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    css = html[html.index("<style>"):html.index("</style>")]

    for prop in ("position: sticky", "backdrop-filter", "user-select"):
        pat = r"^\s*" + re.escape(prop.split(":")[0]) + r"\s*:"
        if prop == "position: sticky":
            pat = r"^\s*position:\s*sticky"
        for m in re.finditer(pat, css, re.M):
            block_start = css.rfind("{", 0, m.start())
            block_end = css.find("}", m.start())
            block = css[block_start:block_end]
            twin = "-webkit-sticky" if prop == "position: sticky" else "-webkit-" + prop
            assert twin in block, (
                f"a rule uses {prop} with no {twin} — on iOS 12 that "
                f"declaration is dropped: {block.strip()[:90]!r}"
            )


def test_shorthands_older_webkit_drops_carry_a_longhand() -> None:
    """`inset`, `clamp()` and `aspect-ratio` all postdate this engine.

    Each one fails silently and differently: `inset: 0` dropped leaves an
    overlay collapsed to its content in the top-left corner, so a modal
    backdrop darkens a small rectangle instead of the screen; a dropped
    `clamp()` font-size falls back to what the element inherited, which on the
    Live View's song title is body text where 78px of stage-readable type
    should be.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    css = html[html.index("<style>"):html.index("</style>")]

    # Comments explaining the rule are not the rule.
    live_css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert "inset: 0" not in live_css, (
        "the `inset` shorthand is back — WebKit before 14.1 drops it and the "
        "overlay collapses to its content in the top-left corner"
    )

    for m in re.finditer(r"font-size:\s*clamp\(", css):
        head = css[max(0, m.start() - 140):m.start()]
        assert re.search(r"font-size:\s*[\d.]+px;\s*$", head), (
            "a clamp() font-size has no plain fallback before it, so on an "
            f"engine that drops clamp the element inherits its size: "
            f"{css[m.start():m.start() + 60]!r}"
        )

    for m in re.finditer(r"^\s*aspect-ratio:", css, re.M):
        head = css[max(0, m.start() - 160):m.start()]
        assert re.search(r"height:\s*[^;]+;\s*$", head), (
            "aspect-ratio with no height fallback — the box has no height at "
            "all on an engine that drops it"
        )


# ── The transport bar, AbleSet-shaped ───────────────────────────────────────
# Previous · Play/Pause · Loop · Next, and nothing else. Every control removed
# from here was removed for the same reason: a bar in a musician's peripheral
# vision can hold about four things, and two of the six were not played.


def test_transport_bar_carries_only_what_is_played() -> None:
    """Four controls, and Stop is not one of them.

    Stop and pause both halt playback and differ only in what they silently
    throw away — Stop discards the queue and the cue, and rewinds. Two controls
    for one intent, distinguished by their side effects, is the shape of a
    mistake made in the dark. RECONNECT was worse: a permanent target for
    something useless during all but a few seconds of a show.
    """
    html = REASET_HTML.read_text(encoding="utf-8")

    bar = re.search(r'<div class="app-transport">(.*?)\n        </div>', html, re.S)
    assert bar, "the transport bar is gone"
    ids = re.findall(r'<button[^>]*\bid="([^"]+)"', bar.group(1))
    assert ids == ["footer-prev-btn", "main-play-btn", "footer-loop-btn", "footer-next-btn"], (
        f"the transport bar is no longer Previous / Play / Loop / Next: {ids}"
    )

    for gone, why in [
        ("stop-ctl", "the Stop control"),
        ("reconnect-btn", "the RECONNECT button"),
        ("ss-thumb", "the slide-to-stop thumb"),
    ]:
        assert gone not in html, f"{why} is back on the bar"


def test_removing_the_stop_button_did_not_remove_stopping(script_body: str) -> None:
    """Auto-Stop, a stop-after marker and the MIDI stop action still stop.

    The button went; the capability did not. Deleting smartStop() with it would
    silently break the end-of-song behaviour the whole epic is about — a song
    marked "stop here" would chain into the next one instead, which is a worse
    failure than any the Stop button ever caused.
    """
    body = strip_comments(script_body)
    assert re.search(r"\bfunction smartStop\s*\(", body), (
        "smartStop() is gone — Auto-Stop and stop-after markers have nothing "
        "left to call"
    )

    # The boundary executor stops through REAPER's action id directly; that path
    # must survive too, or a stop-after marker plays on.
    assert '1016, "song-stop-after"' in body, (
        "the stop-after boundary no longer stops the transport"
    )
    assert '1016, "auto-stop-fallback"' in body, "Auto-Stop no longer stops the transport"


def test_one_navigation_path_for_every_surface(script_body: str) -> None:
    """Four surfaces offer Previous / Next. One function serves them.

    liveNav and canvasNav were literal duplicates of each other, and the footer
    would have been a third caller. This file has already lost two afternoons
    to copies of a control drifting apart.

    The MIDI module has its own pair and they are routed here as well, but that
    module is inside a /* */ block — Safari has no Web MIDI on any Apple
    platform — so nothing there runs, and nothing here asserts on it. It is
    kept in step so re-enabling it cannot resurrect a third behaviour.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    body = strip_comments(script_body)

    for dead in ("function liveNav", "function canvasNav"):
        assert dead not in body, f"{dead}() is back — that is a second navigation path"

    nav = strip_comments(extract_function(body, "navSong"))
    assert "findNextValidSong" in nav and "findPrevValidSong" in nav, (
        "navSong() no longer walks the setlist"
    )
    assert "cueRegion" in nav, (
        "navSong() no longer goes through cueRegion, which is what makes the "
        "stop-and-reposition one compound request and records the target as an "
        "explicit selection"
    )
    # PREVIOUS restarts the current song rather than stepping back, when more
    # than a moment into it. Losing this makes a mis-timed press skip a song.
    assert re.search(r"currentPos\s*-\s*displayList\[activeIdx\]\.start\s*>\s*2", nav), (
        "Previous no longer restarts the current song when past its opening — "
        "a press meant as 'take that again' now loses the song you are on"
    )

    # The three LIVE surfaces. Counted in the markup rather than the script,
    # because that is where the wiring is and where a fourth copy would appear.
    assert html.count('onclick="navSong(\'prev\', event)"') == 3, (
        "the footer, Live View and Canvas do not all reach navSong() for Previous"
    )
    assert html.count('onclick="navSong(\'next\', event)"') == 3, (
        "the footer, Live View and Canvas do not all reach navSong() for Next"
    )


def test_reconnecting_is_offered_only_when_the_link_is_down(script_body: str) -> None:
    """A link that is up needs no affordance; one that is down needs a loud one.

    The banner is now the only place reconnecting is offered, so it has to be
    driven by the failure that actually happens on a stage — REAPER going quiet
    while the wifi is fine. It used to hang off the browser's `offline` event
    alone, which does not fire for that at all.
    """
    body = strip_comments(script_body)

    badge = strip_comments(extract_function(body, "_refreshConnBadge"))
    assert "_connIsLive" in badge, "the badge no longer reads the connection"
    assert "_setConnBanner" in badge, (
        "the connection notice is no longer driven by the poll, so it can only "
        "appear when the browser itself goes offline — not when REAPER stops "
        "answering, which is the failure that happens at a show"
    )

    banner = strip_comments(extract_function(body, "_setConnBanner"))
    assert "wwr_start" in banner, (
        "the notice does not reconnect — with the button gone from the bar, "
        "nothing on screen restarts polling"
    )
    assert "pointer-events:auto" in banner and "cursor:pointer" in banner, (
        "the notice is not tappable, so it names a fix it does not offer"
    )
    assert "t(" in banner, "the notice text bypasses the translation table"


def test_every_element_the_script_reaches_for_still_exists() -> None:
    """An edit that deletes markup no test names is invisible until it throws.

    Removing the Slide-to-Stop switch took SEVEN other sidebar toggles with it —
    Auto-Stop, Hide Skips, auto-scroll, queue mode — because the cut searched
    back to `<div class="toggle-row"`, which does not match
    `class="toggle-row director-only"`, so it skipped its own row and started
    from an earlier one. The whole suite stayed green. The page threw a
    TypeError on load and stopped initialising.

    So: every id the script reads without a null guard must be in the markup.
    That is the invariant the deletion actually broke, and it is checkable.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    present = set(re.findall(r'id="([\w-]+)"', html))
    body = strip_comments(inline_scripts(html)[0])

    # getElementById(...) whose result is dereferenced on the same line — no
    # `var x = ...; if (x)` guard can save these.
    unguarded = re.findall(
        r"""document\.getElementById\(\s*["']([\w-]+)["']\s*\)\s*\.""", body
    )
    missing = sorted({el for el in unguarded if el not in present})
    assert not missing, (
        f"the script dereferences {len(missing)} element(s) that no longer "
        f"exist in the markup, which throws on load: {missing}"
    )


def test_the_sidebar_switches_survived_the_stop_removal() -> None:
    """The four that were collateral damage, named so they cannot vanish quietly.

    These are settings, not decorations: Auto-Stop decides whether a song ends
    the block, Hide Skips decides what the setlist even shows. Losing the
    switch loses the only way to reach them.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    for toggle, what in [
        ("hideSkippedToggle", "Hide Skips"),
        ("autoStopToggle", "Auto-Stop"),
        ("autoScrollToggle", "auto-scroll"),
        ("queueModeToggle", "queue mode"),
    ]:
        assert f'id="{toggle}"' in html, f"the {what} switch is gone from the sidebar"


# ── Row state ───────────────────────────────────────────────────────────────


def test_row_states_are_surfaces_not_outlines() -> None:
    """A 2px ring around the playing card was the loudest thing on the screen.

    It fought the PLAY button for the same green, on the one row whose progress
    fill already said everything, and stacking .cued on .active drew it twice.
    Each state is a tinted surface now — what the row IS, not a box drawn round
    it — and the fill growing across that surface is the marker.
    """
    html = REASET_HTML.read_text(encoding="utf-8")

    for sel in (".song-row.active", ".song-row.cued", ".grid-card.active",
                ".grid-card.cued"):
        decls = _css_decls(html, sel)
        assert "background:" in decls, f"{sel} has no surface, so only its border says anything"
        # A solid brand-coloured border IS the ring this replaced.
        assert not re.search(r"border-color:\s*var\(--color-brand\)", decls), (
            f"{sel} is outlined in solid brand green again"
        )
        assert not re.search(r"box-shadow:\s*inset", decls), (
            f"{sel} draws an inset bar — the state is meant to be the surface"
        )

    # Playing beats cued: both at once must not paint two states on one row.
    both = _css_decls(html, ".song-row.active.cued")
    active = _css_decls(html, ".song-row.active")
    assert both.split() == active.split(), (
        "a row that is playing AND cued no longer renders as merely playing"
    )


def test_a_looping_section_is_marked_where_it_happens(script_body: str) -> None:
    """A pip in the corner says a loop exists; the row has to say WHERE.

    Standing at a mic, the question is not "does this song loop" — it is "is the
    loop coming up, or am I already past it". That is a position, so it is drawn
    as one: the bracket spans the looping section's real place inside the song.

    Percentages of the song's own duration, so it survives every row width
    without measuring anything.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    body = strip_comments(script_body)

    assert "loop-marks" in html and "loop-mark" in html, "the loop bracket is gone"
    marks = body[body.index("var loopMarks"):body.index("rowDiv.innerHTML")]
    assert "sb.loop" in marks, "the bracket no longer follows the section's loop flag"
    assert "r.duration" in marks and "%" in marks, (
        "the bracket is no longer positioned as a fraction of the song, so it "
        "cannot be right at more than one row width"
    )
    assert re.search(r"if\s*\(\s*!\(\s*lEnd\s*>\s*lStart\s*\)\s*\)\s*continue", marks), (
        "a zero-or-negative-width section would still emit a bracket"
    )

    # A bracket, not a wash: the eye reads two facing corners as a SPAN the
    # way it reads nothing else, and a tinted stretch only says "this row is
    # coloured" to someone who already knows what it means.
    assert re.search(r"\.loop-mark::before[^{]*\{[^}]*border-right:\s*none", html), (
        "the opening bracket is a closed box, not a bracket"
    )
    assert re.search(r"\.loop-mark::after[^{]*\{[^}]*border-left:\s*none", html), (
        "the closing bracket is a closed box, not a bracket"
    )


def test_loop_cannot_look_pressable_to_a_role_that_cannot_press_it(script_body: str) -> None:
    """A control that lights itself and then refuses is worse than a missing one.

    Loop is an EDIT — it changes what REAPER plays, and it is published — so
    toggleCurrentLoop() refuses on a Controller. The footer button did not know
    that: it lit from the Director's song, did nothing when tapped, and could
    never be turned off. From a phone that is indistinguishable from "the loop
    button is stuck on", which is exactly how it was reported.

    Same rule the RECONNECT button had to learn. `disabled` stops the click;
    only CSS stops it LOOKING pressable, and the two have to agree.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    body = strip_comments(script_body)

    toggle = strip_comments(extract_function(body, "toggleCurrentLoop"))
    assert "canEditSetlist()" in toggle, (
        "toggleCurrentLoop no longer refuses on a Controller — if that is "
        "deliberate, this whole test is the wrong shape"
    )

    ui = strip_comments(extract_function(body, "updatePlaybackUI"))
    assert re.search(r"loopBtn\.disabled\s*=\s*!", ui), (
        "the LOOP button is offered to a role that cannot use it: it lights "
        "from the Director's song and then refuses every press"
    )
    assert "canEditSetlist()" in ui, "the button's enabled state is not the role's"

    # Disabled must also LOOK it, and .active must still read through — "does
    # this song loop" is worth knowing on every device in the room.
    off = _css_decls(html, ".t-btn-loop:disabled")
    assert "cursor: default" in off, "the disabled LOOP still shows a pointer"
    hover = _css_decls(html, ".t-btn-loop:not(:disabled):hover")
    assert hover, "the hover rule is no longer guarded, so a dead button repaints"


def test_the_role_modal_uses_the_app_s_icons() -> None:
    """Emoji were the last clip art in a file that draws everything else.

    They render differently on every OS, cannot take the theme's colour, and
    beside the plug, the repeat mark and the skip arrows they read as pasted in.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    card = re.search(r'<div class="mode-select-card">(.*?)\n    </div>', html, re.S)
    assert card, "the role modal is gone"
    icons = re.findall(r'<span class="mode-opt-icon[^"]*">(.*?)</span>', card.group(1), re.S)
    assert len(icons) == 2, f"expected two role icons, found {len(icons)}"
    for ic in icons:
        assert "<svg" in ic, f"a role icon is not an svg: {ic.strip()[:40]!r}"
        assert "&#1" not in ic, f"a role icon is still an emoji codepoint: {ic.strip()[:40]!r}"

    # The Controller's description outlived the Stop button once already.
    assert "stop" not in card.group(1).lower() or "stopped" in card.group(1).lower(), (
        "the Controller still advertises a Stop button that no longer exists"
    )


def test_a_whole_song_loop_is_bracketed_like_any_other() -> None:
    """The case with nothing else to read is the one that needs the bracket most.

    A song with no sections loops as a WHOLE, and nothing marks a start or an
    end anywhere — so this shipped as a bare tint, which is legible only to
    someone who already knows what a purple row means. It is bracketed now,
    end to end, and inset from the card's own edge so the two do not touch.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    body = strip_comments(inline_scripts(html)[0])

    # It spans the track from the markup, not from a rule of its own — the
    # track already carries the inset that keeps a bracket off the card border,
    # and a second one here would put the mark somewhere its own percentages
    # do not describe.
    assert "loop-mark is-whole" in body, "the whole-song mark is gone"
    assert re.search(r"is-whole[^\n]*left:0[^\n]*width:100%", body), (
        "the whole-song mark no longer spans its track end to end"
    )
    if re.search(r"(?m)^ {8}\.loop-mark\.is-whole\s*\{", html):
        whole = _css_decls(html, ".loop-mark.is-whole")
        assert "border: none" not in whole, (
            "the whole-song loop dropped its bracket again — that leaves a "
            "tint as the only marker on the one case that has no other"
        )

    # The looping SECTION's own row is bracketed too — the song row says WHERE
    # the loop is, the section row says THIS IS IT.
    body = strip_comments(inline_scripts(html)[0])
    assert "sub.loop ?" in body and "loop-mark is-whole" in body, (
        "a looping section's own row is no longer bracketed, so expanding a "
        "song hides the thing expanding it was meant to show"
    )
    assert _css_decls(html, ".section-row .loop-mark"), (
        "the section bracket has no size of its own and will swallow the row"
    )


def test_a_loop_at_the_songs_edge_does_not_draw_on_the_card_border() -> None:
    """The first and the last section are the two that land on the card's edge.

    A section starting at 0% or ending at 100% of its song put its bracket arm
    a pixel from the row's own border, where the two drew on top of each other
    — and those are not exotic cases, they are the intro and the outro.

    The fix is on the TRACK, not on each mark. Insetting per-mark would need a
    clamp, and a clamped bracket lies about the position by however much it
    clamped, on a mark whose entire job is to say where something is.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    track = _css_decls(html, ".loop-marks")

    left = re.search(r"left:\s*(\d+)px", track)
    right = re.search(r"right:\s*(\d+)px", track)
    assert left and right, (
        "the loop track runs edge to edge, so a bracket for the first or last "
        "section is drawn on top of the card's own border"
    )
    assert int(left.group(1)) >= 4 and int(right.group(1)) >= 4, (
        f"the track's inset ({left.group(1)}px / {right.group(1)}px) is too "
        f"small to keep a bracket arm clear of the border"
    )

    # And no mark may re-inset itself on top of that — two insets would put the
    # whole-song bracket somewhere its own percentages do not describe.
    whole = _css_decls(html, ".loop-mark.is-whole") if re.search(
        r"(?m)^ {8}\.loop-mark\.is-whole\s*\{", html) else ""
    assert "!important" not in whole, (
        "the whole-song mark is overriding the track's inset again"
    )


# ── Region colour ───────────────────────────────────────────────────────────


def test_region_colour_is_written_to_reaper_not_to_this_browser(script_body: str) -> None:
    """A colour only the Director can see is not a colour anyone can use.

    The local override is per-device localStorage, and the sync payload
    deliberately carries only what a follower needs to PLAY the show — not
    authoring data. So the colour goes onto the REGION: every device polls
    REGION once a second and gets it for free, it survives a reload, and it
    comes back with the project tomorrow.
    """
    body = strip_comments(script_body)

    # There must be exactly ONE place that writes the key. Asserting the role
    # gate on a function by name proves nothing if a second, ungated path can
    # reach the wire — and Discard needed a per-region variant, which is
    # exactly the moment such a path gets added.
    wire = "SET/EXTSTATE/ReaSet/regionColor/"
    assert body.count(wire) == 1, (
        f"{body.count(wire)} places write the colour key — a role gate on one "
        "of them is decoration"
    )
    assert wire in strip_comments(extract_function(body, "_pushRegionColorPairs")), (
        "the one write site is no longer the gated one"
    )

    push = strip_comments(extract_function(body, "_pushRegionColorPairs"))
    assert "canEditSetlist()" in push, (
        "anyone can recolour the project — this is an edit, and edits are the "
        "Director's"
    )
    assert "join(';')" in push, (
        "a whole block is no longer one write, so Reaset.lua re-enumerates the "
        "project once per song on its defer thread"
    )

    # The by-song entry point must go THROUGH the gated writer.
    by_song = strip_comments(extract_function(body, "_pushRegionColor"))
    assert "_pushRegionColorPairs(" in by_song, (
        "_pushRegionColor stopped delegating, so it is a second wire path"
    )

    pick = strip_comments(extract_function(body, "_ctxPickColor"))
    assert "_pushRegionColor" in pick, "picking a colour no longer writes the region"
    assert re.search(r"setSongOverride\([^)]*'colorHex',\s*null\)", pick), (
        "picking a colour still sets a LOCAL override as well — the Director's "
        "screen would then disagree with every other one in the room"
    )


def test_a_block_colours_as_one_unit(script_body: str) -> None:
    """A block is what a performer thinks in, so it is what they colour.

    Same operation as one song over a different set, so it is one function —
    two would drift, and this file has lost afternoons to exactly that.
    """
    body = strip_comments(script_body)
    fn = strip_comments(extract_function(body, "_blockRegionIdsFor"))
    assert "isBlockStart" in fn, (
        "the block is no longer derived from the same boundary rule the list "
        "draws its gaps from, so the colour and the gap can disagree"
    )
    assert "while (from > 0 && !isBlockStart(from)) from--" in fn, (
        "it no longer walks BACK to the block's first row, so colouring from "
        "the middle of a block only paints its tail"
    )
    # A repeated song is two rows and one region; colouring it twice is a
    # wasted write, not a bug, but the dedupe is cheap and states the intent.
    assert "seen" in fn, "a song that repeats inside a block is written twice"


# ── The edit session ────────────────────────────────────────────────────────


def test_the_edit_button_names_the_action_not_the_mode(script_body: str) -> None:
    """"SHOW" on the way in is a caption, and nobody read it as a door.

    The control that enters edit mode used to display the mode it was leaving,
    so a Director looking for a way to edit the set saw a button that appeared
    to announce they could not. It has to say what tapping it DOES.
    """
    refresh = strip_comments(extract_function(script_body, "_refreshEditModeBtn"))
    assert "t('EDIT')" in refresh, "the label stopped being the action"
    assert "t('SHOW')" not in refresh, (
        "the label reports the current mode again — that is the bug that made "
        "editing unfindable"
    )
    assert "REASET_EDITING ?" not in refresh, (
        "the label branches on the mode, so it is describing state rather than "
        "offering an action"
    )


def test_edit_mode_has_two_ways_out() -> None:
    html = REASET_HTML.read_text(encoding="utf-8")
    """Entering has to offer both Apply and Discard, and only while editing."""
    assert 'id="editActions"' in html, "the Apply/Discard pair is gone"
    assert 'onclick="discardEdits()"' in html, "no way to throw the edits away"
    assert 'onclick="applyEdits()"' in html, "no way to keep them deliberately"
    assert 'onclick="enterEditMode()"' in html, (
        "the button no longer enters edit mode"
    )

    assert "none" in _css_decls(html, ".edit-actions"), (
        "Apply/Discard are on screen when there is nothing to apply or discard"
    )
    assert "flex" in _css_decls(html, "body.reaset-editing .edit-actions"), (
        "the two buttons never appear"
    )
    assert "none" in _css_decls(html, "body.reaset-editing #editModeBtn"), (
        "EDIT stays on screen next to Apply/Discard, offering a third answer "
        "to a question with two"
    )

    # Spacing: WebKit before 14.1 drops flex gap, and the target device is an
    # iPad that stopped updating. Two buttons flush against each other are one
    # mis-tap between discarding a set and keeping it.
    assert "margin-left" in _css_decls(html, ".edit-actions > .ea-btn + .ea-btn"), (
        "the pair spaces with gap alone, so on the old iPad they touch"
    )


def test_a_controller_is_not_offered_the_edit_session(script_body: str) -> None:
    """Editing is the Director's, at both layers — not CSS alone."""
    html = REASET_HTML.read_text(encoding="utf-8")
    enter = strip_comments(extract_function(script_body, "enterEditMode"))
    assert "canEditSetlist()" in enter, (
        "a Controller can enter edit mode, and the CSS hiding the controls is "
        "the only thing stopping them"
    )
    controller_hides = re.search(
        r"body\.reaset-controller[^{]*\.edit-actions", html
    )
    assert controller_hides, "a Controller is shown Apply/Discard"


def test_discard_restores_the_list_itself_not_the_saved_copy(
    script_body: str,
) -> None:
    """setlists[name] is written FROM displayList, so restoring it is a no-op.

    saveCurrentState() serialises displayList into the named setlist. Putting
    the old array back into setlists[name] would be overwritten by the very
    next save — the screen would keep the edits while the code looked correct.
    """
    discard = strip_comments(extract_function(script_body, "discardEdits"))
    assert "displayList" in discard and "s.rows" in discard, (
        "Discard no longer restores displayList, which is the live list"
    )
    assert "g_songOverrides" in discard, (
        "end-states, notes and colours are per-song overrides, and Discard "
        "leaves them edited"
    )
    assert "_pushRegionColorPairs(" in discard, (
        "region colours live in the REAPER project: no amount of restoring "
        "local state reaches them, so Discard has to push them back"
    )
    assert "s.setlistName === currentSetlistName" in discard, (
        "a snapshot taken against another setlist can be poured into the one "
        "now open"
    )


def test_changing_the_setlist_ends_the_edit_session(script_body: str) -> None:
    """A different set is a different context; the old snapshot is a hazard."""
    change = strip_comments(extract_function(script_body, "changeSetlist"))
    assert "_editTakeSnapshot()" in change, (
        "switching setlists keeps a snapshot describing rows that are no "
        "longer on screen"
    )


def test_the_context_panel_width_is_one_number_not_two() -> None:
    """The panel is positioned in JS against a width declared in CSS.

    They are the same measurement written twice, so they drift silently: the
    panel renders one width and is placed as though it were another, which
    reads as a popup that hangs off the screen edge only near the edge.
    """
    html = REASET_HTML.read_text(encoding="utf-8")
    css_width = _css_decls(html, ".song-ctx-panel")
    match = re.search(r"width:\s*(\d+)px", css_width)
    assert match, "the panel lost its width"
    declared = int(match.group(1))

    placements = [int(w) for w in re.findall(r"var pw = (\d+),", html)]
    assert placements, "no panel placement constant found"
    assert all(p == declared for p in placements), (
        f"CSS says {declared}px, the placement code says {placements} — the "
        "panel is positioned as a size it does not have"
    )
