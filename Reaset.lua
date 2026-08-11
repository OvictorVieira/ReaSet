--[[
 * Script Name: Reaset.lua  — UNIFIED BACKGROUND BRIDGE  (v1.0)
 * About: Single-script companion for the ReaSet web interface (ReaSet.html).
 *        Merges the three former helper scripts into ONE persistent background
 *        script so the whole setup is a single "run once" action:
 *
 *          1) Native A/B loop engine   (was ReaSet_NativeLoop.lua)
 *          2) Lyrics notes → web bridge (was X-Raym Convert Lyrics ...)
 *          3) Chords notes → web bridge (was X-Raym Convert Chords ...)
 *
 *        It also owns two things the browser cannot do on its own:
 *
 *          4) The shared setlist file, for Player devices.
 *          5) The setlist library in <project folder>/reaset/setlists, so
 *             setlists live with the project instead of in one browser's
 *             localStorage.
 *
 * Credits:
 *   - Lyrics/Chords note bridge: inspired by X-Raym's scripts of the same
 *     purpose (https://github.com/X-Raym/REAPER-ReaScripts). Independent
 *     implementation — see docs/RELICENSING.md for the line-by-line
 *     comparison behind that claim. The originals are kept, unmodified and
 *     under their own GPL v3, in Legacy/.
 *   - Native loop engine + unification: ReaSet project.
 * Licence: see LICENSE. Proprietary, free to use. Versions up to v2.x were
 *          released under GPL v3 and remain so.
 *
 * INSTALL (one time only):
 *   Actions → "ReaScript: Load..." → select Reaset.lua
 *   Actions → Show action list → find "Reaset" → Run
 *   (Recommended) add it to REAPER startup: Options → Preferences → General
 *                 → Startup actions, OR SWS "Global startup action".
 *
 *   Nothing else to run. No Action ID needs to be pasted into ReaSet.html.
 *   The web interface auto-detects this script via the "nativeLoopReady" flag.
 *
 * DESIGN NOTES:
 *   - Runs forever via a single reaper.defer() tick.
 *   - Lyrics/Chords tracks are OPTIONAL: if a "lyrics" or "chords" track is
 *     missing the bridge for it simply stays idle. The loop engine keeps
 *     working regardless — so a project without lyrics/chords still gets full
 *     transport + loop control (the old scripts aborted with an error box).
 *   - ULT_GetMediaItemNote (SWS/S&M extension) is called defensively: if the
 *     extension is not installed, lyrics/chords are skipped but the loop
 *     engine and the rest of ReaSet keep functioning.
--]]

----------------------------------------------------------------------------
-- SHARED
----------------------------------------------------------------------------

local SEC          = "ReaSet"
local STR_NO_TEXT  = "--XR-NO-TEXT--"
local HAS_ULT      = (reaper.ULT_GetMediaItemNote ~= nil)  -- SWS present?

----------------------------------------------------------------------------
-- 1) NATIVE LOOP ENGINE  (formerly ReaSet_NativeLoop.lua v3)
----------------------------------------------------------------------------

local REGION_NAME  = "ReaSet Loop"
local REGION_COLOR = reaper.ColorToNative(80, 160, 255) | 0x1000000
local IDX_KEY      = "reasetLoopRegionIdx"
local NEAR_END     = 0.08   -- sec before loop_end that arms the crossing detector
local NEAR_START   = 0.30   -- sec after loop_start that confirms the jump landed

local s_active   = false
local s_start    = 0
local s_end      = 0
local s_max      = 0        -- 0 = infinite
local s_crosses  = 0
local s_near_end = false
local s_key      = ""

local function delete_region()
    local idx = tonumber(reaper.GetExtState(SEC, IDX_KEY))
    if idx then
        reaper.DeleteProjectMarker(nil, idx, true)
        reaper.SetExtState(SEC, IDX_KEY, "", false)
    end
    -- safety scan: remove any orphaned "ReaSet Loop" regions
    local i = 0
    while true do
        local ok, isrgn, _, _, name, midx = reaper.EnumProjectMarkers(i)
        if ok == 0 then break end
        if isrgn and name == REGION_NAME then
            reaper.DeleteProjectMarker(nil, midx, true)
            i = 0
        else
            i = i + 1
        end
    end
end

local function loop_cleanup()
    reaper.GetSetRepeat(0)
    reaper.GetSet_LoopTimeRange(true, true, 0, 0, false)
    delete_region()
    reaper.SetExtState(SEC, "nativeLoop", "done", false)
    reaper.UpdateArrange()
    s_active   = false
    s_crosses  = 0
    s_near_end = false
    s_key      = ""
end

local function loop_arm(ls, le, lm)
    if s_active then delete_region() end

    s_start    = ls
    s_end      = le
    s_max      = lm
    s_crosses  = 0
    s_near_end = false
    s_active   = true
    s_key      = string.format("%.5f:%.5f:%d", ls, le, lm)

    local new_idx = reaper.AddProjectMarker2(
        nil, true, ls, le, REGION_NAME, -1, REGION_COLOR)
    reaper.SetExtState(SEC, IDX_KEY, tostring(new_idx), false)

    reaper.GetSet_LoopTimeRange(true, true, ls, le, false)
    reaper.GetSetRepeat(1)
    reaper.UpdateArrange()
end

-- Returns false when the caller should skip the rest of this tick (a cleanup
-- + defer already happened is NOT done here; caller just continues normally).
----------------------------------------------------------------------------
-- ARMED AUTO-STOP — "stop at this position", resolved by the engine
----------------------------------------------------------------------------
-- ARM, DON'T DETECT.
--
-- The browser used to DETECT the end of a song and SEND a stop, and that path
-- can never be punctual: ~60ms poll, 72-107ms round-trip, and on top of that
-- Main_OnCommand does not stop the transport on the spot — it stops it on the
-- next audio block. A SET/POS landing in that gap runs while the transport is
-- STILL ROLLING, so it seeks PLAYBACK into the next song, which is audible.
--
-- Here REAPER is told where to stop BEFORE it matters. It stops in its own
-- audio engine, at the exact sample, and at the critical moment no command
-- travels at all. Verified on a real region transition: stops 10.7ms before the
-- boundary without ever crossing it.
--
-- IT LIVES HERE, NEXT TO THE LOOP ENGINE, ON PURPOSE: the loop time range is
-- ONE range and both features want it — the loop with GetSetRepeat(1), the
-- auto-stop with 0. They are mutually exclusive per song, so there has to be a
-- single arbiter rather than two that fight. The loop wins: a song marked to
-- loop does not auto-stop.

local s_stopArmed   = false
local s_stopKey     = ""
local s_stopPrefWas = nil   -- the user's global preference, to put back

local function autostop_cleanup()
    if s_stopPrefWas ~= nil and reaper.SNM_SetIntConfigVar then
        reaper.SNM_SetIntConfigVar("stopendofloop", s_stopPrefWas)
        s_stopPrefWas = nil
    end
    if s_stopArmed then
        reaper.GetSet_LoopTimeRange(true, true, 0, 0, false)
    end
    s_stopArmed = false
    s_stopKey   = ""
    reaper.SetExtState(SEC, "autoStopArmed", "", false)
end

local function autostop_arm(ls, le)
    if not reaper.SNM_GetIntConfigVar then return false end
    -- stopendofloop is a GLOBAL REAPER preference, not a project one: save the
    -- user's value the first time and restore it on disarm and on exit.
    if s_stopPrefWas == nil then
        s_stopPrefWas = reaper.SNM_GetIntConfigVar("stopendofloop", 0)
    end
    reaper.SNM_SetIntConfigVar("stopendofloop", 1)
    reaper.GetSet_LoopTimeRange(true, true, ls, le, false)
    reaper.GetSetRepeat(0)
    s_stopArmed = true
    s_stopKey   = string.format("%.5f:%.5f", ls, le)
    -- The browser reads this flag so it does NOT also send its own stop. If
    -- arming cannot happen (no SWS, for instance) the flag stays empty and the
    -- browser's detection remains the fallback: losing precision is acceptable,
    -- losing auto-stop is not.
    reaper.SetExtState(SEC, "autoStopArmed", "1", false)
    return true
end

-- `loop_active` comes from loop_tick: the loop owns the range when it is on.
local function autostop_tick(loop_active)
    if loop_active then
        if s_stopArmed then autostop_cleanup() end
        return
    end
    local ctrl = reaper.GetExtState(SEC, "autoStop")
    if ctrl ~= "on" then
        if s_stopArmed then autostop_cleanup() end
        return
    end
    local ls = tonumber(reaper.GetExtState(SEC, "autoStopStart"))
    local le = tonumber(reaper.GetExtState(SEC, "autoStopEnd"))
    if not (ls and le and le > ls) then
        if s_stopArmed then autostop_cleanup() end
        return
    end
    local key = string.format("%.5f:%.5f", ls, le)
    if key ~= s_stopKey then autostop_arm(ls, le) end
end

local function loop_tick()
    local ctrl = reaper.GetExtState(SEC, "nativeLoop")

    if ctrl == "on" then
        local ls = tonumber(reaper.GetExtState(SEC, "loopStart"))
        local le = tonumber(reaper.GetExtState(SEC, "loopEnd"))
        local lm = tonumber(reaper.GetExtState(SEC, "loopMax")) or 0
        if ls and le and le > ls then
            local new_key = string.format("%.5f:%.5f:%d", ls, le, lm)
            if new_key ~= s_key then
                -- The loop wins the range: release the auto-stop before taking
                -- it, or the GetSetRepeat(1) below would fight its 0.
                if s_stopArmed then autostop_cleanup() end
                loop_arm(ls, le, lm)
            end
        end
    end

    if s_active then
        if ctrl == "off" then loop_cleanup(); return end

        local ps = reaper.GetPlayState()  -- 0=stop 1=play 2=pause 4=rec 5=rec+play
        if ps == 0 then loop_cleanup(); return end

        if ps ~= 2 then
            local pos = reaper.GetPlayPosition()
            if not s_near_end then
                if pos >= (s_end - NEAR_END) then s_near_end = true end
            else
                if pos >= (s_start - 0.10) and pos <= (s_start + NEAR_START) then
                    s_crosses  = s_crosses + 1
                    s_near_end = false
                    if s_max > 0 and s_crosses >= s_max then loop_cleanup(); return end
                elseif pos > s_start + NEAR_START then
                    s_near_end = false
                end
            end
        end
    end
end

----------------------------------------------------------------------------
-- 2) + 3)  LYRICS / CHORDS NOTE BRIDGE  (formerly X-Raym scripts)
----------------------------------------------------------------------------
-- One reusable bridge object per named track. Sends the item-note text under
-- the play/edit cursor to a Project ExtState the web interface polls.

local function bridge_new(track_name, ext_name, status_key, context)
    return {
        track_name = track_name,
        ext_name   = ext_name,
        status_key = status_key,  -- ExtState key ReaSet.html polls for diagnostics
        context    = context,     -- also publish the previous/next item's notes
        track      = nil,
        text       = nil,
        prev_text  = nil,
        next_text  = nil,
        prev_pos   = nil,
        next_pos   = nil,
        status     = nil,
    }
end

-- Publishes what this bridge is actually doing, so the web UI can tell apart
-- the failure modes that otherwise all look like "no lyrics showing":
--   ""          → key absent/cleared: this script is not running at all
--   "!NOTRACK"  → script alive, but no track matched the keyword
--   "!NOSWS"    → track found, but SWS/ULT_GetMediaItemNote is unavailable
--   "<name>"    → track found and readable (shows the real REAPER track name)
-- Written as non-persistent global ExtState so it dies with REAPER and is
-- never baked into the project file (which would strand a stale status).
local function bridge_publish_status(b, value)
    if b.status ~= value then
        b.status = value
        reaper.SetExtState(SEC, b.status_key, value, false)
    end
end

-- Normalises a track name for matching. The track must still BE the keyword —
-- we only strip decoration around it, so detection stays predictable:
--   • case is ignored            → "LYRICS", "Lyrics", "lyrics"
--   • leading symbols are ignored → "*Lyrics", "##Chords", "-- lyrics", "[Chords]"
--   • leading numbering ignored   → "01 Lyrics", "3 - Chords"
--   • trailing symbols ignored    → "Lyrics*", "Chords --", "[Lyrics]"
-- Anything that leaves extra WORDS behind does NOT match, on purpose:
-- "Backing Lyrics" or "Lyrics Bus" stay ordinary audio tracks.
--
-- This is the canonical implementation. Tools/Lyrics_Tapper.lua has its own
-- copy (normalize_track_name there too, ported to match this one exactly) —
-- ReaScripts don't share a module loader across files without a fragile
-- relative dofile(), so the two are kept as intentionally duplicated,
-- byte-identical algorithms rather than one unverified cross-file include.
-- If you change the rules here, port the same change there.
local function normalize_track_name(name)
    local s = name:lower()
    -- Strip leading decoration repeatedly so mixed prefixes like "* 01 - " unwind
    -- in any order. Each pass can only shorten s, so this always terminates.
    local prev
    repeat
        prev = s
        s = s:gsub("^[^%w]+", "")   -- symbols / spaces: * # - _ > / [ .
        s = s:gsub("^%d+", "")      -- numbering: 01, 3, 12
    until s == prev
    s = s:gsub("[^%w]+$", "")       -- trailing symbols / spaces
    return s
end

-- Finds the track for this bridge. Returns (track, match_count).
--
-- A track that actually HAS items wins over one that does not, even if the
-- empty one comes first. Without this, a divider/folder track called
-- "*LYRICS*" or "=== LYRICS ===" sitting above the real lyrics track silently
-- shadows it: it matches the keyword, has no items, and the panel stays empty
-- forever. Falls back to the first match when none of them have items.
local function bridge_find_track(b)
    local n = reaper.CountTracks(0)
    local first, with_items, count = nil, nil, 0
    for i = 0, n - 1 do
        local tr = reaper.GetTrack(0, i)
        local _, name = reaper.GetTrackName(tr)
        if normalize_track_name(name) == b.track_name then
            count = count + 1
            if not first then first = tr end
            if not with_items and reaper.GetTrackNumMediaItems(tr) > 0 then
                with_items = tr
            end
        end
    end
    return (with_items or first), count
end

local function item_at_pos(track, pos)
    local n = reaper.GetTrackNumMediaItems(track)
    for i = 0, n - 1 do
        local item = reaper.GetTrackMediaItem(track, i)
        local p = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
        if p <= pos then
            local len = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
            if p + len > pos then return item end
        end
    end
    return nil
end

-- Resolves the item under the cursor plus its neighbours, in ONE pass.
-- Items on a track are stored in timeline order, so:
--   * everything that ends at/before pos keeps overwriting `prev`
--   * the first item covering pos is `cur` (its successor is `nxt`)
--   * if we reach an item starting after pos, we are in a gap: `cur` stays nil
--     and that item is `nxt`, while `prev` already holds the preceding one.
-- Returning all three from one scan keeps the per-frame cost the same as the
-- old single lookup.
local function items_around(track, pos)
    local n = reaper.GetTrackNumMediaItems(track)
    local prev, cur, nxt = nil, nil, nil
    for i = 0, n - 1 do
        local item = reaper.GetTrackMediaItem(track, i)
        local p    = reaper.GetMediaItemInfo_Value(item, "D_POSITION")
        if p > pos then
            nxt = item
            break
        end
        local l = reaper.GetMediaItemInfo_Value(item, "D_LENGTH")
        if p + l > pos then
            cur = item
            if i + 1 < n then nxt = reaper.GetTrackMediaItem(track, i + 1) end
            break
        end
        prev = item
    end
    return prev, cur, nxt
end

-- Resolves the text for the item under the cursor and publishes it.
-- Writes only on change (SetProjExtState dirties the project), but when
-- `verify` is set it also confirms the stored value still matches ours.
--
-- That read-back matters: another instance of this script running atexit, or a
-- project reload, can wipe the key behind our back. Because we only write on
-- change, the cache would then agree with itself forever and the panel would
-- stay blank permanently with no way to recover short of restarting REAPER.
local function process_notes(ext_name, ext_key, item, cached, verify)
    local out
    if not item then
        out = STR_NO_TEXT
    else
        if not HAS_ULT then return cached end
        local ok, note = pcall(reaper.ULT_GetMediaItemNote, item)
        if not ok or note == nil then return cached end
        note = note:gsub("\r?\n", "<br>")
        -- Compare in PUBLISHED form. Comparing the raw note against a cached
        -- "--XR-NO-TEXT--" made an item with empty notes rewrite the same value
        -- on every single frame, keeping the project permanently dirty.
        out = (note == "") and STR_NO_TEXT or note
    end

    if out ~= cached then
        reaper.SetProjExtState(0, ext_name, ext_key, out)
    elseif verify then
        local _, actual = reaper.GetProjExtState(0, ext_name, ext_key)
        if actual ~= out then
            reaper.SetProjExtState(0, ext_name, ext_key, out)
        end
    end
    return out
end

-- Publishes a neighbouring item's start position (or "" when there is none),
-- so ReaSet.html can tell a verse that belongs to a DIFFERENT song from one
-- that's still part of the current one, and clamp/relabel it accordingly.
-- Only meaningful for context-mode bridges (see bridge_tick).
local function process_pos(ext_name, ext_key, item, cached)
    local out = item and tostring(reaper.GetMediaItemInfo_Value(item, "D_POSITION")) or ""
    if out ~= cached then
        reaper.SetProjExtState(0, ext_name, ext_key, out)
    end
    return out
end

-- Publishes how many tracks matched the keyword, so the UI can warn about an
-- ambiguous project instead of silently using one of them.
local function bridge_publish_matches(b, n)
    if b.matches ~= n then
        b.matches = n
        reaper.SetExtState(SEC, b.status_key .. "Matches", tostring(n), false)
    end
end

local RESCAN_TICKS = 120  -- ~2 s at 60 fps

local function bridge_tick(b, cur_pos, tick)
    -- Re-acquire when the pointer died, and ALSO re-validate periodically.
    -- A latched pointer stays valid after the user renames the track, so
    -- without this a rename never takes effect and the script keeps reading
    -- the wrong (or a now-misnamed) track until REAPER restarts.
    local needs_scan = not reaper.ValidatePtr(b.track, 'MediaTrack*')
    if not needs_scan and (tick % RESCAN_TICKS == 0) then
        local _, cur_name = reaper.GetTrackName(b.track)
        if normalize_track_name(cur_name) ~= b.track_name then
            needs_scan = true               -- renamed away from the keyword
        elseif reaper.GetTrackNumMediaItems(b.track) == 0 then
            needs_scan = true               -- empty: a better candidate may exist now
        end
    end

    if needs_scan then
        local tr, count = bridge_find_track(b)
        b.track = tr
        bridge_publish_matches(b, count)
        if not tr then
            bridge_publish_status(b, "!NOTRACK")
            return
        end
    end
    if not HAS_ULT then
        -- Track exists but item notes cannot be read without SWS.
        bridge_publish_status(b, "!NOSWS")
        return
    end
    local _, tname = reaper.GetTrackName(b.track)
    bridge_publish_status(b, tname)
    local verify = (tick % 60 == 0)   -- ~1 s: cheap self-heal, no project dirtying

    if b.context then
        -- Publish the surrounding verses too, so the panel can show what just
        -- passed and what is coming next.
        local prev_it, cur_it, next_it = items_around(b.track, cur_pos)
        b.text      = process_notes(b.ext_name, "text", cur_it,  b.text,      verify)
        b.prev_text = process_notes(b.ext_name, "prev", prev_it, b.prev_text, verify)
        b.next_text = process_notes(b.ext_name, "next", next_it, b.next_text, verify)
        -- Positions ride alongside the text so ReaSet.html can tell a verse
        -- from another song apart from one still inside the current one.
        b.prev_pos  = process_pos(b.ext_name, "prevPos", prev_it, b.prev_pos)
        b.next_pos  = process_pos(b.ext_name, "nextPos", next_it, b.next_pos)
    else
        b.text = process_notes(b.ext_name, "text", item_at_pos(b.track, cur_pos), b.text, verify)
    end
end

-- Both panels show their neighbours: lyrics stacks them vertically, chords
-- places them left/right of the current one.
local lyrics = bridge_new("lyrics", "XR_Lyrics", "lyricsTrack", true)
local chords = bridge_new("chords", "XR_Chords", "chordsTrack", true)

----------------------------------------------------------------------------
-- 4) SETLIST SYNC  — Director's browser → Reaset.lua → shared file → Players
----------------------------------------------------------------------------
-- ReaSet has no server of its own, so a Director's browser cannot write a
-- file directly — the only channel it has into REAPER is SET/EXTSTATE. It
-- base64url-encodes its setlist snapshot, splits it into pieces small enough
-- to stay well under any URL-length ceiling, and writes each piece plus a
-- final "chunk count" key. This script never decodes or parses any of it —
-- it is opaque text the whole way through — it only watches the count key
-- for a new value, concatenates that many numbered chunks, and writes the
-- result to a file living next to ReaSet.html, where Players fetch() it.
-- See ReaSet.html's "Shared setlist sync" section for the JS-side encode.

-- Where REAPER's web interface serves files from.
--
-- This used to be hardcoded to "<resource>/Plugins/reaper_www_root". When that
-- path is not the right one for an install, io.open fails silently: the file is
-- never written, the browser gets a 404, and NOBODY RETURNS AN ERROR — the whole
-- path looks like it works. Measured on a real install where the correct
-- directory was "<resource>/reaper_www_root" instead.
--
-- Resolved by looking instead: the right directory is the one ReaSet.html itself
-- lives in, which is exactly the one the browser asks with a relative URL. If it
-- is not found, the first writable candidate wins.
local s_wwwRoot = nil
local function www_root()
    if s_wwwRoot then return s_wwwRoot end
    local base = reaper.GetResourcePath()
    local cands = { base .. "/reaper_www_root", base .. "/Plugins/reaper_www_root" }
    for _, d in ipairs(cands) do
        local f = io.open(d .. "/ReaSet.html", "rb")
        if f then f:close(); s_wwwRoot = d; return d end
    end
    for _, d in ipairs(cands) do
        local probe = d .. "/.reaset_probe"
        local f = io.open(probe, "wb")
        if f then f:close(); os.remove(probe); s_wwwRoot = d; return d end
    end
    s_wwwRoot = cands[1]
    return s_wwwRoot
end

local SYNC_FILE_NAME = "reaset_setlist_sync.json"

local function sync_file_path()
    return www_root() .. "/" .. SYNC_FILE_NAME
end

local s_syncLastCount = nil   -- last chunk-count value already written to disk

local function sync_tick()
    -- Gate on a MONOTONIC revision, not on the chunk count.
    --
    -- This used to compare setlistChunkCount against the last one handled, and
    -- that silently dropped most pushes: toggling a skip flag changes the
    -- payload by three characters, so the chunk count stays identical, the
    -- comparison sees no change, and the shared file is never rewritten —
    -- Players keep displaying the old setlist with no sign anything failed.
    -- Only edits that happened to push the payload across a chunk boundary got
    -- through, which is why it looked like it worked.
    local rev_str = reaper.GetExtState(SEC, "setlistRev")
    if rev_str == "" then
        -- Older ReaSet.html that doesn't send a rev yet: fall back to the old
        -- count-based trigger so a mixed pair still syncs at all.
        rev_str = reaper.GetExtState(SEC, "setlistChunkCount")
    end
    if rev_str == "" or rev_str == s_syncLastCount then return end

    local count_str = reaper.GetExtState(SEC, "setlistChunkCount")
    local count = tonumber(count_str)
    if not count or count < 1 then return end

    local parts = {}
    for i = 0, count - 1 do
        local chunk = reaper.GetExtState(SEC, "setlistChunk" .. i)
        if chunk == "" then
            -- A chunk hasn't landed yet (the browser sends bodies before the
            -- count, but each is a separate HTTP round-trip, so a brief gap
            -- is possible). Don't write a half-assembled file — leave
            -- s_syncLastCount untouched so the NEXT tick retries immediately;
            -- self-heals within a fraction of a second once the rest arrive.
            return
        end
        parts[#parts + 1] = chunk
    end

    -- Base64url's alphabet ([A-Za-z0-9_-]) can never contain a quote or
    -- backslash, so it drops straight into this JSON string with zero
    -- escaping needed.
    local f = io.open(sync_file_path(), "wb")
    if f then
        f:write('{"v":1,"b64":"' .. table.concat(parts) .. '"}')
        f:close()
    end
    s_syncLastCount = rev_str     -- mark handled either way — a permissions
                                   -- error won't be retried every tick
end

----------------------------------------------------------------------------
-- BASE64URL DECODE  — the return path of the browser's _b64uEncode
----------------------------------------------------------------------------
-- sync_tick above never needed this: it copies the browser's base64 straight
-- into the shared file and lets the browser decode it again. The library does
-- need it, because it writes real JSON to disk that a human may open.

local B64U_ALPHABET   = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
local B64U_DECODE_MAP = {}
for i = 1, #B64U_ALPHABET do
    B64U_DECODE_MAP[B64U_ALPHABET:sub(i, i)] = i - 1
end

-- Reverses ReaSet.html's _b64uEncode. Verified standalone against real output
-- of that function (including accented UTF-8 text) before landing here —
-- REAPER's ReaScript Lua has no base64 of its own.
local function b64u_decode(input)
    local bits, value, out = 0, 0, {}
    for i = 1, #input do
        local d = B64U_DECODE_MAP[input:sub(i, i)]
        if d then
            value = (value << 6) | d
            bits = bits + 6
            if bits >= 8 then
                bits = bits - 8
                out[#out + 1] = string.char((value >> bits) & 0xFF)
            end
        end
    end
    return table.concat(out)
end

----------------------------------------------------------------------------
-- SETLIST LIBRARY  — a /reaset folder living next to the project
----------------------------------------------------------------------------
-- THE DISK IS THE ONLY SOURCE OF TRUTH. The browser is a client, not a store:
-- there are never two versions to reconcile, there is one and it gets read.
--
--   <project folder>/
--     reaset/
--       setlists/
--         Default.json
--         Rehearsal set.json
--
-- ONE FILE PER SETLIST, deliberately: if one gets corrupted or hand-edited
-- badly it takes down that setlist, not the whole library. And they can be
-- backed up, versioned or sent around individually.
--
-- WHY NOT ProjExtState: it only reaches the disk if the user saves, and those
-- changes don't appear in the undo history, so there is no signal that
-- anything is pending. Closing without saving takes them away silently.
--
-- WHY ALSO AN INDEX IN reaper_www_root: the browser cannot list a directory
-- or read arbitrary paths — only fetch inside the web interface's www root.
-- The index is derived and disposable; the disk is what counts.

local LIB_INDEX_NAME = "reaset_setlists.json"

local function lib_index_path()
    return www_root() .. "/" .. LIB_INDEX_NAME
end

-- <project folder>/reaset/setlists, or nil if the project was never saved.
local function lib_dir()
    local _, projfn = reaper.EnumProjects(-1, "")
    if not projfn or projfn == "" then return nil end
    local dir = projfn:match("^(.*)[/\\][^/\\]*$")
    if not dir then return nil end
    return dir .. "/reaset/setlists"
end

-- Short, stable checksum, only to tell apart names that sanitise the same.
local function lib_hash4(s)
    local h = 5381
    for i = 1, #s do h = (h * 33 + s:byte(i)) % 65536 end
    return string.format("%04x", h)
end

-- Characters forbidden on Windows and on macOS, plus control ones. Windows is
-- a target platform, so the rule is the union of both, not the rule of
-- whichever machine happened to create the file.
local WIN_RESERVED = {
    CON=true, PRN=true, AUX=true, NUL=true,
    COM1=true, COM2=true, COM3=true, COM4=true, COM5=true,
    COM6=true, COM7=true, COM8=true, COM9=true,
    LPT1=true, LPT2=true, LPT3=true, LPT4=true, LPT5=true,
    LPT6=true, LPT7=true, LPT8=true, LPT9=true,
}

local function lib_name_is_safe(name)
    if name == "" or #name > 80 then return false end
    if name:find('[/\\:%*%?"<>|%c]') then return false end
    if name:find("^[%s%.]") or name:find("[%s%.]$") then return false end
    if WIN_RESERVED[name:upper()] then return false end
    return true
end

-- DETERMINISTIC: the same name always yields the same file, with no separate
-- map that could drift out of sync. Ordinary names stay as they are and stay
-- readable in Finder/Explorer; only the ones that need sanitising carry the
-- suffix, and that suffix is what makes them collision-free.
local function lib_filename(name)
    if lib_name_is_safe(name) then return name .. ".json" end
    local safe = name:gsub('[/\\:%*%?"<>|%c]', "_"):gsub("^[%s%.]+", ""):gsub("[%s%.]+$", "")
    if safe == "" then safe = "setlist" end
    if #safe > 60 then safe = safe:sub(1, 60) end
    return safe .. "-" .. lib_hash4(name) .. ".json"
end

local function json_escape(s)
    return (s:gsub('[\\"]', "\\%0"):gsub("\n", "\\n"):gsub("\r", "\\r"):gsub("\t", "\\t"))
end

local function read_all(path)
    local f = io.open(path, "rb"); if not f then return nil end
    local s = f:read("*a"); f:close(); return s
end

-- Rebuilds the index by reading the DIRECTORY, not an in-memory copy: what the
-- browser sees is literally what is on disk, including a file the user added,
-- edited or deleted by hand.
local function lib_rebuild_index()
    local dir = lib_dir()
    local bodies = {}
    if dir then
        local i = 0
        while true do
            local fn = reaper.EnumerateFiles(dir, i)
            if not fn then break end
            if fn:match("%.json$") then
                local body = read_all(dir .. "/" .. fn)
                -- Copied VERBATIM: no JSON parser is needed in Lua, and what
                -- the browser receives is byte for byte what is on disk.
                if body and body:find('"songs"') then bodies[#bodies + 1] = body end
            end
            i = i + 1
        end
    end
    local stamp = dir and json_escape(dir) or ""
    local out = '{"v":2,"proj":"' .. stamp .. '","sets":[' .. table.concat(bodies, ",") .. ']}'
    local f = io.open(lib_index_path(), "wb")
    if f then f:write(out); f:close() end
    reaper.SetExtState(SEC, "libraryPath", dir or "!UNSAVED", false)
    reaper.SetExtState(SEC, "libraryCount", tostring(#bodies), false)
    reaper.SetExtState(SEC, "wwwRoot", www_root(), false)
end

-- Writes or deletes ONE setlist. An empty `songs_json` means delete.
local function lib_apply(name, songs_json)
    local dir = lib_dir()
    if not dir then return false end
    reaper.RecursiveCreateDirectory(dir, 0)
    local path = dir .. "/" .. lib_filename(name)
    if songs_json == "" then
        os.remove(path)
    else
        local f = io.open(path, "wb")
        if not f then return false end
        f:write('{"v":1,"name":"' .. json_escape(name) .. '","songs":' .. songs_json .. '}')
        f:close()
    end
    return true
end

local s_libRev    = nil
local s_libLoaded = false
local s_libProj   = nil

local function library_tick()
    -- The project changed (or this is the first tick): the folder is a
    -- different one, so the index is regenerated from the new disk before
    -- anything gets served.
    local cur = reaper.EnumProjects(-1)
    if cur ~= s_libProj then
        s_libProj = cur; s_libLoaded = false; s_libRev = nil
    end
    if not s_libLoaded then
        lib_rebuild_index()
        s_libLoaded = true
        return
    end

    local rev = reaper.GetExtState(SEC, "libRev")
    if rev == "" or rev == s_libRev then return end

    local name_b64 = reaper.GetExtState(SEC, "libName")
    if name_b64 == "" then return end
    local n = tonumber(reaper.GetExtState(SEC, "libChunks"))
    if not n then return end

    local parts = {}
    for i = 0, n - 1 do
        local c = reaper.GetExtState(SEC, "libChunk" .. i)
        -- A chunk that hasn't landed yet: don't write half a setlist. Leaving
        -- s_libRev untouched makes the next tick retry.
        if c == "" then return end
        parts[#parts + 1] = c
    end

    local name = b64u_decode(name_b64)
    if name == "" then return end
    lib_apply(name, n == 0 and "" or b64u_decode(table.concat(parts)))
    lib_rebuild_index()
    s_libRev = rev
end

----------------------------------------------------------------------------
-- MAIN DEFER LOOP  — drives all three subsystems from one tick
----------------------------------------------------------------------------

local _hb_tick = 0

local function tick_body()
    -- Presence flag (never expires — only proves the script ran at least once).
    if _hb_tick % 150 == 0 then
        reaper.SetExtState(SEC, "nativeLoopReady", "1", false)
    end

    -- REAL heartbeat: a value that CHANGES while we are alive. The flag above
    -- cannot do this job — it survives in memory until REAPER quits, so a
    -- crashed script still looks "ready". Watchers compare successive samples;
    -- if this stops advancing, the defer chain is dead.
    if _hb_tick % 15 == 0 then
        reaper.SetExtState(SEC, "tick", tostring(_hb_tick), false)
    end

    -- 1) Loop engine
    loop_tick()
    autostop_tick(s_active)

    -- 2/3) Lyrics + Chords note bridges (share the same cursor position)
    local cur_pos = reaper.GetPlayState() > 0
        and reaper.GetPlayPosition() or reaper.GetCursorPosition()
    bridge_tick(lyrics, cur_pos, _hb_tick)
    bridge_tick(chords, cur_pos, _hb_tick)

    -- 4) Shared setlist file, written whenever a Director pushes
    sync_tick()

    -- 5) Setlist library: serves the project's /reaset/setlists folder and
    --    writes back whatever the browser saves.
    library_tick()
end

local function main()
    _hb_tick = _hb_tick + 1

    -- A raw error inside a deferred script silently ends the defer chain: the
    -- bridge stops updating while the last published values stay frozen, which
    -- looks exactly like "chords work, lyrics don't". Catch it, publish it, and
    -- keep ticking so a transient failure self-heals instead of killing ReaSet.
    local ok, err = pcall(tick_body)
    if not ok then
        reaper.SetExtState(SEC, "error", tostring(err), false)
    elseif _hb_tick % 150 == 0 then
        reaper.SetExtState(SEC, "error", "", false)
    end

    reaper.defer(main)
end

----------------------------------------------------------------------------
-- CLEAN EXIT  — clear published note state so the web UI shows "not running"
----------------------------------------------------------------------------

local function on_exit()
    reaper.SetProjExtState(0, "XR_Lyrics", "text", "")
    reaper.SetProjExtState(0, "XR_Lyrics", "prev", "")
    reaper.SetProjExtState(0, "XR_Lyrics", "next", "")
    reaper.SetProjExtState(0, "XR_Lyrics", "prevPos", "")
    reaper.SetProjExtState(0, "XR_Lyrics", "nextPos", "")
    reaper.SetProjExtState(0, "XR_Chords", "text", "")
    reaper.SetProjExtState(0, "XR_Chords", "prev", "")
    reaper.SetProjExtState(0, "XR_Chords", "next", "")
    reaper.SetProjExtState(0, "XR_Chords", "prevPos", "")
    reaper.SetProjExtState(0, "XR_Chords", "nextPos", "")
    -- Clear bridge diagnostics so the UI reports "script not running".
    reaper.SetExtState(SEC, "lyricsTrack", "", false)
    reaper.SetExtState(SEC, "chordsTrack", "", false)
    reaper.SetExtState(SEC, "lyricsTrackMatches", "", false)
    reaper.SetExtState(SEC, "chordsTrackMatches", "", false)
    reaper.SetExtState(SEC, "tick", "", false)
    reaper.SetExtState(SEC, "error", "", false)
    if s_active then loop_cleanup() end
    -- stopendofloop is a GLOBAL REAPER preference: hand it back as it was.
    autostop_cleanup()
    -- Drop the presence flag so ReaSet falls back to JS loop next session.
    reaper.SetExtState(SEC, "nativeLoopReady", "0", false)
end

----------------------------------------------------------------------------
-- BOOT
----------------------------------------------------------------------------

-- Clear any stale "on" loop state left over from a previous REAPER session.
if reaper.GetExtState(SEC, "nativeLoop") == "on" then
    reaper.SetExtState(SEC, "nativeLoop", "done", false)
end

-- Announce presence immediately (non-persistent: vanishes when REAPER closes).
reaper.SetExtState(SEC, "nativeLoopReady", "1", false)

reaper.atexit(on_exit)
reaper.defer(main)
