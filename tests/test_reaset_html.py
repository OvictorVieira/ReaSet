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
