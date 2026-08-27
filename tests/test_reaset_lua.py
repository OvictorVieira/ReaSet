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


def test_colour_tick_paints_the_region_and_consumes_its_key() -> None:
    """Executed, not grepped: the real chunk against a stubbed reaper API.

    Two things have to hold and neither is visible by reading the source.

    Colouring a region DIRTIES the project, so an instruction left in the
    ExtState would re-apply on every defer tick — roughly thirty times a
    second, forever, on a project that then never stops asking to be saved.
    The key is consumed BEFORE the write for exactly that reason, and the cost
    of that order is that a failed write loses the instruction. That is the
    right trade: the user can pick the colour again.

    And the block form has to work, because a whole block arrives as one
    semicolon-separated write rather than one write per song.
    """
    src = REASET_LUA.read_text(encoding="utf-8")
    chunk = extract_lua_chunk(src, "local function color_tick", "local function tick_body")
    chunk += "\n_color_tick = color_tick\n"

    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        """
        SEC = 'ReaSet'
        ext = { regionColor = '1:FF8800;2:x' }
        writes = {}
        arranged = 0
        regions = {
          [0] = { 1, true,  0.0,  10.0, 'ONE', 1 },
          [1] = { 1, true,  10.0, 20.0, 'TWO', 2 },
          [2] = { 1, false, 25.0, 25.0, 'a marker', 3 },
        }
        reaper = {
          GetExtState = function(_, k) return ext[k] or '' end,
          SetExtState = function(_, k, v) ext[k] = v end,
          EnumProjectMarkers = function(i)
            local r = regions[i]
            if not r then return 0, false, 0, 0, '', 0 end
            return r[1], r[2], r[3], r[4], r[5], r[6]
          end,
          SetProjectMarker3 = function(_, idx, isrgn, pos, e, name, col)
            writes[#writes + 1] = { idx = idx, col = col, name = name }
          end,
          ColorToNative = function(r, g, b) return (b << 16) | (g << 8) | r end,
          UpdateArrange = function() arranged = arranged + 1 end,
        }
        """
    )
    lua.execute(chunk)
    lua.eval("_color_tick")()

    assert lua.eval("ext.regionColor") == "", (
        "the instruction is still in the ExtState, so this repaints and "
        "re-dirties the project on every tick from here on"
    )

    writes = lua.eval("writes")
    assert len(writes) == 2, f"expected both regions written, got {len(writes)}"

    first = writes[1]
    assert first["idx"] == 1, f"wrong region written: {first['idx']}"
    assert first["col"] == (0x0088FF | 0x1000000), (
        f"FF8800 did not reach REAPER as its native colour with the set-flag: "
        f"{first['col']:#x} — without 0x1000000 the value reads as unset and "
        f"the region stays default"
    )
    assert first["name"] == "ONE", "the region's own name was not preserved"

    second = writes[2]
    assert second["idx"] == 2 and second["col"] == 0, (
        "'x' must clear to REAPER's own default, not paint black"
    )

    assert lua.eval("arranged") == 1, (
        "the arrange view was refreshed the wrong number of times"
    )
