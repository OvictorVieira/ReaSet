"""A region created in REAPER is a new region, not a new project.

The project key (which namespaces localStorage and the shared sync) used to be a hash of the region IDs, so adding, deleting
or renaming one region produced a different key: ReaSet reloaded its storage as if REAPER had opened another project, the
setlist was rebuilt from an empty one and the whole project was absorbed into "Default". Since the library write queue
started to keep (instead of dropping) writes made before the first index read, that bootstrapped list was then also written
to the project, replacing the real one.
"""
import json
import textwrap

from test_reaset_html import extract_function, requires_node, run_node, script_body  # noqa: F401


def _project_harness(source: str, scenario: str) -> dict:
    fns = "\n".join(extract_function(source, f) for f in
                    ("_computeProjectFingerprint", "_regionPairs", "_sameProject", "_resolveProjectKey"))
    script = textwrap.dedent("""
        __FNS__
        var R = function (id, name) { return ['REGION', name, String(id), '0', '10', '0']; };
        var out = {};
        __SCENARIO__
        console.log(JSON.stringify(out));
    """).replace("__FNS__", fns).replace("__SCENARIO__", scenario)
    return json.loads(run_node(script))


BASE = "[R(1,'LOGO'),R(2,'FALLING'),R(3,'GORILLAZ'),R(4,'UNSHATTER'),R(5,'INCEPTION'),R(6,'EMPTINESS')]"


@requires_node
def test_the_first_region_list_names_the_project(script_body: str) -> None:
    got = _project_harness(script_body, f"""
        var a = _resolveProjectKey(null, null, {BASE});
        out.key = a.key; out.switched = a.switched; out.fp = _computeProjectFingerprint({BASE});
    """)
    assert got["switched"] is True and got["key"] == got["fp"]


@requires_node
def test_adding_deleting_or_renaming_a_region_keeps_the_project(script_body: str) -> None:
    got = _project_harness(script_body, f"""
        var base = {BASE};
        var first = _resolveProjectKey(null, null, base);
        var keep = function (regions) {{
            var r = _resolveProjectKey(first.key, first.pairs, regions);
            return [r.key === first.key, r.switched];
        }};
        out.added   = keep(base.concat([R(7, 'NEW SONG')]));
        out.deleted = keep(base.slice(0, 5));
        out.renamed = keep([R(1,'LOGO 2'), R(2,'FALLING'), R(3,'GORILLAZ'), R(4,'UNSHATTER'), R(5,'INCEPTION'), R(6,'EMPTINESS')]);
        out.loop    = keep(base.concat([R(8, 'ReaSet Loop')]));          // the temp region NativeLoop.lua makes
        out.empty   = keep([]);                                           // REAPER answered nothing: not a project switch
    """)
    for what, (same_key, switched) in got.items():
        assert same_key and not switched, f"{what}: a region edit was taken for another project"


@requires_node
def test_another_project_is_still_told_apart(script_body: str) -> None:
    """Region ids are small sequential numbers in every project (1..N): a project with a different number of regions has a
    different id set, and none of its names is shared. The pairs id|name decide it, so a new region is not mistaken for it."""
    got = _project_harness(script_body, f"""
        var first = _resolveProjectKey(null, null, {BASE});
        var other = [];
        for (var i = 1; i <= 9; i++) other.push(R(i, 'OTHER ' + i));      // overlapping ids, no name in common
        var r = _resolveProjectKey(first.key, first.pairs, other);
        out.switched = r.switched; out.differs = r.key !== first.key;
        out.sameCountElsewhere = _sameProject(first.pairs, [R(1,'LOGO'), R(2,'X'), R(3,'Y'), R(4,'Z'), R(5,'W'), R(6,'V')].map(function (r) {{ return r[2] + '|' + r[1]; }}));
    """)
    assert got["switched"] is True and got["differs"] is True
    assert got["sameCountElsewhere"] is False          # one pair in common out of six is not the same project


def test_region_list_end_resets_storage_only_on_a_real_switch(script_body: str) -> None:
    start = script_body.index('case "REGION_LIST_END":')
    handler = script_body[start:script_body.index("case ", start + 10)]
    assert "_resolveProjectKey(" in handler, "REGION_LIST_END no longer asks whether it is the same project"
    init_at = handler.index("_initProjectStorage(")
    guard = handler[:init_at]
    assert "switched" in guard[guard.rindex("if"):], (
        "_initProjectStorage() is called on every region change again: a new region would reset the setlists"
    )


@requires_node
def test_a_list_built_before_the_library_was_read_is_not_written_to_the_project(script_body: str) -> None:
    """The bootstrap of an EMPTY setlist (storage just reset, index not read yet) is not a user's setlist: it must not
    reach the project library nor the Players. A real edit before the index is read must still be kept (and sent later)."""
    fn = extract_function(script_body, "saveCurrentState")
    script = textwrap.dedent("""
        var displayList = [{id: 'A', chain: true, skipped: false, loop: false}];
        var currentSetlistName = 'Default', setlists = {}, STORAGE_KEY = 'k', CURRENT_KEY = 'c', _lastSavedSig = null;
        var _store = {}; var localStorage = { setItem: function (k, v) { _store[k] = v; } };
        var document = { getElementById: function () { return null; } };
        function _partitionActiveFirst(l) { return l; }
        function getSongEnd() { return 0; }
        function getOverride() { return {}; }
        var calls = [];
        function _syncPushSoon() { calls.push('push'); }
        function _libraryEnqueue(n) { calls.push('lib:' + n); }
        __FN__
        var out = {};
        saveCurrentState(true);                       // the bootstrap, before the index was read
        out.bootstrap = calls.slice(); out.savedLocally = !!_store.k; calls.length = 0;
        displayList.push({id: 'B', chain: true, skipped: false, loop: false});
        saveCurrentState();                           // an edit
        out.edit = calls.slice();
        console.log(JSON.stringify(out));
    """).replace("__FN__", fn)
    got = json.loads(run_node(script))
    assert got["bootstrap"] == [] and got["savedLocally"] is True
    assert got["edit"] == ["push", "lib:Default"]


def test_syncregions_marks_the_bootstrap_before_the_index_as_unconfirmed(script_body: str) -> None:
    sync = extract_function(script_body, "syncRegions")
    assert "saveCurrentState(" in sync
    call = sync[sync.rindex("saveCurrentState("):][:60]
    assert "saveCurrentState()" not in call, "syncRegions() saves its bootstrap like a user edit again"
    assert "_libReconciled" in sync, "syncRegions() does not look at whether the library index was read"


@requires_node
def test_an_edit_made_before_the_library_is_read_is_still_kept_for_later(script_body: str) -> None:
    """The fix for setlists lost to a stale disk read (#19) must keep working: a write enqueued before the first index read is
    deferred, not dropped, and its local copy beats the disk until it lands."""
    fn = extract_function(script_body, "_libraryEnqueue")
    script = textwrap.dedent("""
        var REASET_MODE = 'director', _libReconciled = false, _libPending = {}, _libDeferred = [], _libQueue = [];
        var LIB_PENDING_MAX = 60000, _libDraining = false;
        function _libraryDrain() {}
        __FN__
        _libraryEnqueue('My Set');
        console.log(JSON.stringify({deferred: _libDeferred, pending: !!_libPending['My Set'], queued: _libQueue}));
    """).replace("__FN__", fn)
    got = json.loads(run_node(script))
    assert got["deferred"] == ["My Set"] and got["pending"] is True and got["queued"] == []
