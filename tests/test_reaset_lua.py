#!/usr/bin/env python3
"""Contract tests for Reaset.lua.

Nothing in this repository checked Reaset.lua before this file existed. It is
the half of ReaSet that runs inside REAPER's defer loop, so a fault here is not
a broken feature — it is REAPER itself getting slower while the show runs.

The bridge test below EXECUTES the real function against a stubbed reaper API
rather than reading the source for a keyword, because what matters is how many
times it walks the project, and only running it can count that.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REASET_LUA = ROOT / "Reaset.lua"

lupa = pytest.importorskip("lupa", reason="lupa provides the Lua runtime")
luaparser_ast = pytest.importorskip(
    "luaparser.ast", reason="luaparser provides the syntax check"
)


def test_reaset_lua_parses() -> None:
    """A syntax error here kills the defer chain, and with it auto-stop,
    native loop, lyrics, chords and the shared setlist file — silently, since
    a dead deferred script leaves its last published values frozen in place."""
    luaparser_ast.parse(REASET_LUA.read_text(encoding="utf-8"))


def extract_lua_chunk(source: str, first: str, last_before: str) -> str:
    start = source.index(first)
    end = source.index(last_before)
    assert start < end
    return source[start:end]


def test_bridge_backs_off_when_no_track_exists() -> None:
    """bridge_tick must not walk the project on every tick when nothing matches.

    bridge_find_track iterates every track looking for a name. With no lyrics
    or chords track the re-acquire branch ran on EVERY defer tick, for both
    bridges — roughly 120 full project walks a second, forever, searching for
    something that is not there. A project with neither track is the normal
    case, not a fault: both panels are optional, so the default configuration
    paid the most. It is a large part of why REAPER felt heavy with ReaSet
    open.

    Executes the real chunk with a stubbed reaper API and counts the walks.
    """
    src = REASET_LUA.read_text(encoding="utf-8")
    # From bridge_new so the helpers bridge_tick calls come with it. The
    # functions are `local`, so they are exported explicitly — a local does not
    # outlive the chunk that declared it.
    chunk = extract_lua_chunk(src, "local function bridge_new", "local function www_root")
    chunk += "\n_bridge_new = bridge_new\n_bridge_tick = bridge_tick\n"

    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        """
        scans = 0
        HAS_ULT = false
        SEC = 'ReaSet'
        reaper = {
          -- Every call to this is one walk of the project.
          CountTracks = function() scans = scans + 1; return 8 end,
          GetTrack = function() return nil end,
          GetTrackName = function() return true, 'guitar' end,
          GetTrackNumMediaItems = function() return 0 end,
          ValidatePtr = function(p) return p ~= nil end,
          SetExtState = function() end,
          GetExtState = function() return '' end,
        }
        function normalize_track_name(n) return n end
        """
    )
    lua.execute(chunk)
    lua.execute(
        """
        local b = _bridge_new('lyrics', 'XR_Lyrics', 'lyricsTrack', true)
        for t = 1, 600 do _bridge_tick(b, 0.0, t) end
        """
    )

    scans = lua.globals().scans
    rescan_ticks = int(re.search(r"local RESCAN_TICKS\s*=\s*(\d+)", src).group(1))
    # 600 ticks at one walk per RESCAN_TICKS, plus the first.
    ceiling = (600 // rescan_ticks) + 2
    assert scans <= ceiling, (
        f"bridge_tick walked the project {scans} times in 600 ticks (expected "
        f"<= {ceiling}). The no-track backoff is gone: with two bridges at ~60fps "
        f"that is ~120 full project scans a second looking for nothing."
    )
    assert scans >= 1, "it never searched at all — a track created later is never found"


def test_shared_file_write_is_length_checked() -> None:
    """Reaset.lua must refuse a payload assembled across two pushes.

    The chunk bodies, the count and the revision are separate HTTP requests, so
    a stale chunk from a previous, longer push can sit between two new ones.
    Base64 spanning two generations decodes to garbage and dies at JSON.parse
    on every follower at once, with nothing in the failure to say why.
    """
    src = REASET_LUA.read_text(encoding="utf-8")
    assert "setlistChunkLen" in src, "the payload length check is gone from sync_tick"
    assert re.search(r"if\s+want_len\s+and\s+#payload\s*~=\s*want_len\s+then\s+return",
                     src), "the length is read but no longer gates the write"
