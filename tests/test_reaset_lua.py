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
import sys
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
          GetTrack = function(_, i) return { index = i } end,
          GetTrackName = function(track)
            if track == nil then error('MediaTrack expected') end
            return true, 'guitar'
          end,
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
        ext = { regionColor = '1:FF8800,2:x' }   -- comma: ';' is REAPER's command separator
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


def test_the_track_name_is_exact_and_a_near_miss_is_named() -> None:
    """The name IS the command, so it is one spelling: "Lyrics".

    This used to fold case and strip decoration, accepting "lyrics", "LYRICS",
    "*Lyrics" and "01 - Lyrics" alike. A convention that accepts eight
    spellings is not a convention — nobody converges on one and the rule
    becomes something you have to read the source to know.

    Being strict is only usable if being wrong is LOUD, so the loose form still
    runs, for exactly one purpose: recognising a near miss and NAMING it, so
    the panel can say what to rename rather than reporting "no track".

    Runs the real chunk against a stubbed reaper API — a transcription of this
    logic into Python would keep passing after the original drifted.
    """
    src = REASET_LUA.read_text(encoding="utf-8")
    chunk = extract_lua_chunk(
        src, "local function normalize_track_name", "local function item_at_pos"
    )

    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    tracks: list[tuple[str, int]] = []

    class Reaper:
        def CountTracks(self, _proj):
            return len(tracks)

        def GetTrack(self, _proj, i):
            return i

        def GetTrackName(self, i):
            return (True, tracks[i][0])

        def GetTrackNumMediaItems(self, i):
            return tracks[i][1]

    lua.globals()["reaper"] = Reaper()
    find = lua.execute(chunk + "\nreturn bridge_find_track")

    def probe(names: list[tuple[str, int]]):
        nonlocal tracks
        tracks = names
        return find(lua.table(track_name="Lyrics"))

    found, count, near = probe([("Lyrics", 3)])
    assert found is not None and count == 1 and near is None, (
        "the exact name stopped matching"
    )

    for wrong in ("lyrics", "LYRICS", "*Lyrics", "01 - Lyrics", "Lyrics --"):
        found, count, near = probe([(wrong, 3)])
        assert found is None, f'"{wrong}" still matches — the name is not exact'
        assert near == wrong, (
            f'"{wrong}" is not reported as a near miss, so the panel can only '
            "say 'no track' and the user has nothing to act on"
        )

    for unrelated in ("Backing Lyrics", "Lyrics Bus", "Guitar"):
        found, count, near = probe([(unrelated, 3)])
        assert found is None and near is None, (
            f'"{unrelated}" is being offered as a near miss — it is an '
            "ordinary audio track"
        )

    # A divider track must not shadow the real one, and must not be reported
    # as a near miss in preference to the match that exists.
    found, count, near = probe([("=== LYRICS ===", 0), ("Lyrics", 5)])
    assert found is not None and count == 1, "a divider track shadows the real one"


TAPPER_LUA = ROOT / "Tools" / "Lyrics_Tapper.lua"


def test_generate_spreads_the_lines_across_a_real_span() -> None:
    """Tapping gets timing that matches the vocal; generating gets the words in.

    The point of Generate is to turn a lyric sheet into items in one gesture,
    so the span it chooses has to be the one the user meant — and when there is
    no such span it must refuse rather than scatter forty items from the cursor
    into a project with no way to know where they went.

    Runs the real chunk against a stubbed reaper API.
    """
    src = TAPPER_LUA.read_text(encoding="utf-8")
    chunk = src[
        src.index("local SECTION_PATTERNS") : src.index("local function do_reset()")
    ]

    items: list[dict] = []
    regions: list[tuple[str, float, float]] = []
    state = {"timesel": (0.0, 0.0), "cursor": 0.0}

    class Reaper:
        def GetSet_LoopTimeRange(self, *_a):
            return state["timesel"]

        def GetCursorPosition(self):
            return state["cursor"]

        def EnumProjectMarkers(self, i):
            if i >= len(regions):
                return (0, False, 0, 0, "", 0)
            name, start, end = regions[i]
            return (i + 1, True, start, end, name, i)

        def AddMediaItemToTrack(self, _tr):
            items.append({"pos": None, "len": None, "note": None})
            return len(items) - 1

        def SetMediaItemInfo_Value(self, it, key, value):
            items[it]["pos" if key == "D_POSITION" else "len"] = value

        def GetSetMediaItemInfo_String(self, it, _k, value, _set):
            items[it]["note"] = value

        def Undo_BeginBlock(self):
            pass

        def Undo_EndBlock(self, *_a):
            pass

        def UpdateArrange(self):
            pass

        def GetPlayState(self):
            return 0

    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.globals()["reaper"] = Reaper()
    # The upvalues the extracted chunk closes over, stubbed so the chunk itself
    # stays the real one.
    preamble = """
        lines = {}
        target_track = 0
        track_type_idx = 0
        TRACK_TYPES = { [0] = "Lyrics", [1] = "Chords", [2] = "Notes" }
        ui_msg = ""
        full_text = ""
        function ensure_target_track() return target_track end
        function get_current_pos() return 0 end
    """
    api = lua.execute(
        preamble + chunk + "\nreturn { gen = do_generate, parse = parse_lines }"
    )

    sheet = "Chorus\numa linha\n\noutra linha\n  terceira  \n"
    parsed, skipped = api.parse(sheet)
    assert skipped == 1, "the section header is no longer filtered out"
    lua.globals()["lines"] = parsed

    # A song is a region, and the cursor is inside it.
    regions.append(("Numb", 10.0, 190.0))
    state["cursor"] = 60.0
    api.gen()
    assert len(items) == 3, "one item per line"
    assert items[0]["pos"] == 10.0, "the first line does not start at the region"
    last_end = items[-1]["pos"] + items[-1]["len"]
    assert abs(last_end - 190.0) < 1e-9, "the last line does not reach the end"
    assert items[0]["note"] == "uma linha", "the text is not in the item note"
    for a, b in zip(items, items[1:]):
        assert abs((a["pos"] + a["len"]) - b["pos"]) < 1e-9, (
            "items do not touch, so the panel goes blank between lines"
        )

    # An explicit time selection is a clearer statement of intent than the
    # region the cursor happens to be in.
    items.clear()
    state["timesel"] = (100.0, 120.0)
    api.gen()
    assert items[0]["pos"] == 100.0 and abs(
        (items[-1]["pos"] + items[-1]["len"]) - 120.0
    ) < 1e-9, "the time selection no longer wins over the region"

    # Neither: it must refuse.
    items.clear()
    regions.clear()
    state["timesel"] = (0.0, 0.0)
    state["cursor"] = 5.0
    api.gen()
    assert items == [], (
        "with no span it invented one — forty items land somewhere nobody chose"
    )
    assert "region" in lua.globals()["ui_msg"], "it refused without saying why"


def test_the_track_template_round_trips_its_notes() -> None:
    """A generated file nobody can read back is how a format bug ships.

    ReaSet reads Item Notes, not the take name, so the whole point of emitting a
    track template instead of MIDI is the `<NOTES>` block. This proves the chunk
    is balanced and every lyric survives it — including the ones carrying `<`,
    `>` and `|`, which are chunk syntax and would otherwise be read as
    structure.
    """
    sys.path.insert(0, str(ROOT / "Tools"))
    import lyrics_to_reaper as gen

    lyrics = [
        "I'm tired of being what you want me to be",
        "a line with <angle> brackets",
        "a pipe | inside",
        "> leading angle",
        "acentuação e ç",
    ]
    chunk = gen.build_template("Numb", lyrics, 4.0, "Lyrics")
    assert gen.notes_from_template(chunk) == lyrics, (
        "a lyric did not survive the chunk"
    )
    assert chunk.count("<ITEM") == len(lyrics), "one item per line"
    assert "NAME Lyrics" in chunk, "the track does not arrive with the exact name"

    # Re-running on an unchanged sheet must produce an identical file, or the
    # output churns on every run and cannot be reviewed in a diff.
    assert gen.build_template("Numb", lyrics, 4.0, "Lyrics") == chunk

    parsed, skipped = gen.parse_lines("Chorus\num verso\n\n  mais um  \n")
    assert parsed == ["um verso", "mais um"] and skipped == 1

    # A collision worth knowing about rather than discovering on stage: "outro"
    # is an English section name and the Portuguese word for "another". A line
    # that is exactly "outro" is dropped. --keep-sections is the way out, and
    # the Lyrics Tapper's list has the same overlap.
    parsed, skipped = gen.parse_lines("outro\n")
    assert parsed == [] and skipped == 1
    parsed, _ = gen.parse_lines("outro\n", keep_sections=True)
    assert parsed == ["outro"], "--keep-sections must be the escape hatch"


# GetPlayState is a BITFIELD, not an enum: &1 playing, &2 paused, &4 recording.
# Paused is therefore any state with bit 2 set — 2 while stopped, 6 while
# record-armed, and 3 on builds that keep the playing bit through a pause.
#
# (id, playstate, paused?)
LUA_PLAYSTATES = [
    ("playing", 1, False),
    ("paused", 2, True),
    ("paused-keeping-the-play-bit", 3, True),
    ("recording", 5, False),
    ("record-paused", 6, True),
]


@pytest.mark.parametrize(
    "state,playstate,paused",
    LUA_PLAYSTATES,
    ids=[c[0] for c in LUA_PLAYSTATES],
)
def test_loop_engine_reads_the_pause_bit_not_the_number(
    state: str, playstate: int, paused: bool
) -> None:
    """The loop's crossing detector must not run while the transport is paused.

    A paused transport returns the same GetPlayPosition() on every tick. The
    detector compares that position against the loop boundaries, so running it
    while paused counts crossings that never happened — and a `+LOOP` section
    with a repeat count then ends early, on stage, with no way to tell why.

    loop_tick guards this with `if ps ~= 2`, an equality test against one value
    of a bitfield. Record-paused (6) walks straight past it, and so does 3.

    Executes the real loop_tick against a stubbed reaper API and counts how
    many times the paused position was read.
    """
    src = REASET_LUA.read_text(encoding="utf-8")
    chunk = extract_lua_chunk(src, "local s_active", "local function bridge_new")
    chunk += "\n_loop_tick = loop_tick\n_arm = loop_arm\n"

    lua = lupa.LuaRuntime(unpack_returned_tuples=True)
    lua.execute(
        """
        reads = 0
        -- Declared above the extracted chunk, so they are not part of it.
        SEC = 'ReaSet'
        REGION_NAME  = 'ReaSet Loop'
        REGION_COLOR = 0
        IDX_KEY      = 'reasetLoopRegionIdx'
        NEAR_END     = 0.08
        NEAR_START   = 0.30
        function delete_region() end
        ext = { nativeLoop = 'on', loopStart = '10', loopEnd = '20', loopMax = '2' }
        reaper = {
          GetExtState    = function(_, k) return ext[k] or '' end,
          SetExtState    = function(_, k, v) ext[k] = v end,
          DeleteExtState = function(_, k) ext[k] = nil end,
          GetPlayState   = function() return PS end,
          -- Frozen, exactly as a paused transport reports it.
          GetPlayPosition = function() reads = reads + 1; return 19.95 end,
          GetSetRepeat   = function() return 0 end,
          GetSet_LoopTimeRange = function() return 0, 0 end,
          SNM_SetIntConfigVar  = function() end,
          SNM_GetIntConfigVar  = function(_, d) return d end,
          AddProjectMarker2 = function() return 1 end,
          DeleteProjectMarker = function() return true end,
          EnumProjectMarkers3 = function() return 0 end,
          CountProjectMarkers = function() return 0, 0, 0 end,
          UpdateArrange  = function() end,
          UpdateTimeline = function() end,
        }
        """
    )
    lua.execute(chunk)

    # Arm the loop with the transport rolling, then hand it the state under
    # test — the same order a pause arrives in during a show.
    lua.globals().PS = 1
    lua.execute("_loop_tick()")
    lua.globals().PS = playstate
    lua.execute("reads = 0; for _ = 1, 20 do _loop_tick() end")

    reads = lua.globals().reads
    if paused:
        assert reads == 0, (
            f"playstate {playstate} ({state}) is paused, and the crossing "
            f"detector still read the frozen play position {reads} times. It is "
            "counting loop passes that are not happening"
        )
    else:
        assert reads > 0, (
            f"playstate {playstate} ({state}) is rolling and the crossing "
            "detector never ran — the loop would never repeat"
        )
