--[[
 * Script Name: ReaSet_LibraryDoctor.lua — SETLIST LIBRARY STATUS
 * About: Shows the project's /reaset folder, which setlists are on disk, and
 *        whether the index the browser reads is up to date. Use it to see
 *        which link broke in the chain browser → Reaset.lua → disk.
 *
 *        Reads only. Changes nothing.
 *
 * USAGE:
 *   Actions → "ReaScript: Load..." → select ReaSet_LibraryDoctor.lua
 *   Actions → Show action list → find "ReaSet_LibraryDoctor" → Run
 *   Read the report in the ReaScript console window that opens.
 *
 * Licence: see ../LICENSE
--]]

local SEC = "ReaSet"
local function out(s) reaper.ShowConsoleMsg(tostring(s) .. "\n") end
local function rule() out(string.rep("-", 70)) end

local function read_all(path)
    local f = io.open(path, "rb"); if not f then return nil end
    local s = f:read("*a"); f:close(); return s
end

reaper.ClearConsole()
out("ReaSet — setlist library")
out(os.date("%Y-%m-%d %H:%M"))
out("")

local _, projfn = reaper.EnumProjects(-1, "")
out("PROJECT")
rule()
out("  " .. ((projfn ~= "" and projfn) or "(unsaved)"))
out("")

local dir = nil
if projfn and projfn ~= "" then
    local d = projfn:match("^(.*)[/\\][^/\\]*$")
    if d then dir = d .. "/reaset/setlists" end
end

out("DISK FOLDER (the source of truth)")
rule()
if not dir then
    out("  x The project was never saved, so there is no folder to write to.")
    out("    Save the project and run this again.")
else
    out("  " .. dir)
    -- EnumerateFiles is the piece the whole index depends on: if this REAPER
    -- build does not expose it, the report says so instead of lying.
    if not reaper.EnumerateFiles then
        out("  x reaper.EnumerateFiles does not exist in this REAPER version.")
        out("    The index cannot be built. Please report this.")
    else
        local i, n = 0, 0
        while true do
            local fn = reaper.EnumerateFiles(dir, i)
            if not fn then break end
            if fn:match("%.json$") then
                n = n + 1
                local body = read_all(dir .. "/" .. fn) or ""
                local name = body:match('"name"%s*:%s*"(.-)"') or "?"
                local _, songs = body:gsub('"id"', "")
                out(string.format("    - %-34s  %-22s %d songs", fn, "«" .. name .. "»", songs))
            end
            i = i + 1
        end
        if n == 0 then
            out("    (empty — the browser has not pushed any setlist yet)")
        else
            out(string.format("  %d file(s)", n))
        end
    end
end
out("")

out("WWW ROOT — where the web interface serves files from")
rule()
-- Both candidates are probed and the one holding ReaSet.html is named: that is
-- the one the browser asks with a relative URL, and therefore the only one
-- where writing the index accomplishes anything.
local base = reaper.GetResourcePath()
local cands = { base .. "/reaper_www_root", base .. "/Plugins/reaper_www_root" }
local chosen = nil
for _, d in ipairs(cands) do
    local has_html = read_all(d .. "/ReaSet.html") ~= nil
    local writable = false
    local f = io.open(d .. "/.reaset_probe", "wb")
    if f then f:close(); os.remove(d .. "/.reaset_probe"); writable = true end
    out(string.format("  %s", d))
    out(string.format("     ReaSet.html: %s     writable: %s",
        has_html and "YES" or "no", writable and "yes" or "NO"))
    if has_html and not chosen then chosen = d end
end
if not chosen then
    for _, d in ipairs(cands) do
        local f = io.open(d .. "/.reaset_probe", "wb")
        if f then f:close(); os.remove(d .. "/.reaset_probe"); chosen = d; break end
    end
end
out("")
out("  Chosen by the Doctor:       " .. (chosen or "(none usable)"))
out("  Chosen by Reaset.lua:       " .. (reaper.GetExtState(SEC, "wwwRoot") ~= "" and reaper.GetExtState(SEC, "wwwRoot") or "(not published)"))
out("")

out("INDEX THE BROWSER READS (derived, disposable)")
rule()
local idx = (chosen or cands[1]) .. "/reaset_setlists.json"
out("  " .. idx)
local body = read_all(idx)
if not body then
    out("  x Does not exist.")
    out("    If Reaset.lua is running and the folder above is writable,")
    out("    reload the script: the path is resolved once, at startup.")
else
    local _, sets = body:gsub('"songs"', "")
    out(string.format("  ok %d bytes, %d setlist(s)", #body, sets))
end
out("")

out("STATE PUBLISHED BY Reaset.lua")
rule()
local pth = reaper.GetExtState(SEC, "libraryPath")
if pth == "" then
    out("  x Reaset.lua published nothing. Is it running?")
elseif pth == "!UNSAVED" then
    out("  ! Running, but the project is not saved.")
else
    out("  ok " .. pth)
    out("  Setlists in the last index: " .. reaper.GetExtState(SEC, "libraryCount"))
end
local rev = reaper.GetExtState(SEC, "libRev")
out("  Last revision received from the browser: " .. (rev ~= "" and rev or "(none)"))
