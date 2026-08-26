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
