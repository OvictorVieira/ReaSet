"""Shipping transport handler and boundary executor, with delayed REAPER I/O."""
import json

import pytest

from test_reaset_html import _brace_block, extract_function, run_node, script_body, requires_node


def transport_harness(source: str, scenario: str) -> dict:
    functions = [
        'updatePlaybackUI', 'togglePlay', 'resolvePlayTarget', 'activeInstanceIdx',
        '_uidOf', '_ownerUidOf', 'noteActiveInstance', '_selectionOf',
        'clearSelectedRegion', '_clearCueAnchor', 'clearQueuedRegion',
        'promoteQueuedToSelected', 'resolveBoundaryAction', 'findNextValidSong',
        'findPrevValidSong', 'isManualTransportGuardActive', 'clearManualTransportGuard',
        '_suppressAutoTransport', 'getExtrapolatedPos', '_fmtPos',
        'cancelPendingAutomaticTransport',
        '_playSelectedViaLua', '_findInstanceByUid',
        '_consumeNativeStop', 'selectRegionForCue',
    ]
    # Execute the real TRANSPORT switch branch, not a second state machine.
    handler = source[source.index('case "TRANSPORT":'):source.index('case "REGION_LIST":')]
    script = """
        var clock = 10000;
        Date.now = function() { return clock; };
        var sent = [], logs = [];
        var window = { subStates: {}, _autoStopArmed: true };
        var displayList = [
            {id:'A',uid:'uA',name:'A',start:0,end:10,duration:10},
            {id:'B',uid:'uB',name:'B',start:10,end:20,duration:10},
            {id:'C',uid:'uC',name:'C',start:20,end:30,duration:10}
        ];
        var isPlaying = false, isPaused = false, currentPos = 0, wasPlayingLast = false;
        var selectedRegion = null, queuedRegion = null, _activeUidHint = null;
        var _manualGuardUntil = 0, _manualIntent = null, _resyncGuardUntil = 0;
        var _lastTransportTs = 0, _autoTransportTimers = [];
        var isDragging = false, lastActiveID = null, expandedSongs = {};
        var g_subRegionMap = {}, currentSetlistName = 'Test', liveViewOpen = false;
        var autoStop = true;
        var MIDI_INIT_PREROLL = 0.005;
        var node = {checked:false, style:{}, classList:{add:function(){},remove:function(){},toggle:function(){}},
                    getAttribute:function(){return '0';}};
        var document = {
            getElementById: function(id) {
                if (id === 'autoStopToggle') return {checked:autoStop};
                if (id.indexOf('row-') === 0) return null;
                return node;
            },
            querySelector:function(){return null;},querySelectorAll:function(){return [];}
        };
        var RSDiag = {log:function(k,v){logs.push([k,v]);},logChange:function(){},blocked:function(){}};
        function wwr_req(cmd, why) { sent.push([String(cmd), why]); }
        function canControlTransport(){return true;}
        function canPublishSetlist(){return true;}
        function _refreshSetlistBanner(){}
        function _applyLoopPermission(){}
        function _paintIntent(){}
        function _sessionBegin(){}
        function _showProgressSec(){return 0;}
        function _fmtClock(){return '';}
        function _ico(){return '';}
        function formatTime(v){return String(v);}
        function getOverride(){return {};}
        function effectiveSongEnd(){return autoStop ? 'stop' : 'continue';}
        function flashRow(){}
        function _reaperNativeLoopOff(){}
        function midiInitPreroll(v){return Math.max(0,v-0.005);}
        function pauseTransport(){wwr_req(1008,'user-pause');}
    """
    script += '\n'.join(extract_function(source, f) for f in functions)
    script += '\nfunction reply(state, pos) { var tok = ["TRANSPORT", String(state), String(pos)]; var _now = clock; switch(tok[0]) {' + handler + '} }\n'
    return json.loads(run_node(script + scenario))


@requires_node
def test_stale_boundary_after_play_cannot_override_selected_song(script_body):
    got = transport_harness(script_body, """
        autoStop = false;
        currentPos = 9.9;
        selectedRegion = _selectionOf(displayList[2]);
        togglePlay();
        clock += 50;
        // In-flight reply describes A ending, before the seek to C lands.
        reply(1, 9.9);
        console.log(JSON.stringify({sent:sent, selected:selectedRegion}));
    """)
    assert not any(why == 'auto-chain' for _, why in got['sent']), got


@requires_node
def test_stopped_reply_cannot_rearm_previous_song_during_pending_cue(script_body):
    got = transport_harness(script_body, """
        reply(1, 9.85);  // boundary arms next-song cue; native stop is pending
        clock += 80;
        reply(0, 0);     // REAPER rewinds edit cursor on stop
        sent = [];
        togglePlay();   // play B before confirmation of SET/POS/10
        clock += 50;
        reply(0, 0);    // stale reply must not publish A's auto-stop again
        console.log(JSON.stringify({sent:sent, selected:selectedRegion}));
    """)
    assert not any('autoStopEnd/10;' in cmd for cmd, _ in got['sent']), got


@requires_node
def test_play_does_not_start_against_previous_songs_stop_range(script_body):
    got = transport_harness(script_body, """
        window._nativeTransportReady = true;
        reply(1, 9.85);
        clock += 80;
        reply(0, 0);
        sent = [];
        togglePlay();
        console.log(JSON.stringify({sent:sent}));
    """)
    cmd, why = got['sent'][0]
    assert why == 'user-play-selected-native', got
    assert cmd.endswith('|9.995|10|20|1'), got
    assert len(got['sent']) == 1, got


@requires_node
def test_play_cancels_old_delay_timer(script_body):
    got = transport_harness(script_body, """
        _autoTransportTimers = [123];
        var cancelled = [];
        function clearTimeout(id){cancelled.push(id);}
        selectedRegion = _selectionOf(displayList[2]);
        togglePlay();
        console.log(JSON.stringify({cancelled:cancelled}));
    """)
    assert got['cancelled'] == [123], got


@requires_node
def test_native_completion_recovers_missed_browser_boundary(script_body):
    got = transport_harness(script_body, """
        reply(1, 8);
        clock += 2200;
        reply(0, 0);
        _consumeNativeStop('42|0|10');
        var target = resolvePlayTarget();
        _consumeNativeStop('42|0|10');
        console.log(JSON.stringify({target:target.region.id,
            seeks:sent.filter(function(c){return c[1]==='user-cue';})}));
    """)
    assert got['target'] == 'B'
    assert got['seeks'] == [['SET/POS/10', 'user-cue']]


@requires_node
@pytest.mark.parametrize('intent', ['pause', 'manual-stop', 'new-selection', 'playing'])
def test_old_completion_does_not_override_manual_intent(script_body, intent):
    setup = {
        'pause': 'isPaused=true;',
        'manual-stop': '_manualGuardUntil=clock+900;',
        'new-selection': 'selectedRegion=_selectionOf(displayList[2]);',
        'playing': 'isPlaying=true;',
    }[intent]
    got = transport_harness(script_body, setup + """
        _consumeNativeStop('42|0|10');
        console.log(JSON.stringify(sent));
    """)
    assert got == []


@requires_node
def test_repeated_play_retries_same_native_request_until_transport_confirms(script_body):
    got = transport_harness(script_body, """
        window._nativeTransportReady = true;
        selectedRegion = _selectionOf(displayList[1]);
        togglePlay();
        var first = sent[0][0];
        clock += 60; togglePlay();
        var earlyCount = sent.length;
        clock += 1600; togglePlay();
        var retry = sent[sent.length-1][0];
        reply(1, 10.2);
        togglePlay();
        console.log(JSON.stringify({same:first===retry,earlyCount:earlyCount,
            last:sent[sent.length-1],pending:window._nativePlayRequest}));
    """)
    assert got == {'same': True, 'earlyCount': 1, 'last': ['1008', 'user-pause'], 'pending': None}


@requires_node
@pytest.mark.parametrize('command', ['1016', '1008', '1007', 'SET/POS/20', '1016;SET/POS/20'])
def test_transport_gate_cancels_unconsumed_native_start(script_body, command):
    at = script_body.index('window.wwr_req = function (cmd, reason)')
    body, _ = _brace_block(script_body, script_body.index('{', at))
    out = run_node('''
        var window={_nativeTransportReady:true,_nativePlayRequest:'old'};
        var sent=[];
        var RSDiag={cmd:function(){},blocked:function(){}};
        function _commandClass(){return 'transport';}
        function canControlTransport(){return true;}
        function canPublishSetlist(){return false;}
        function _wwrReqReal(cmd){sent.push(cmd);}
        function send(cmd,reason){
    ''' + body + '\n}\nsend(' + json.dumps(command) + ''');
        console.log(JSON.stringify({sent:sent,pending:window._nativePlayRequest}));
    ''')
    got = json.loads(out)
    assert got['pending'] is None
    assert got['sent'] == ['SET/EXTSTATE/ReaSet/playRequest/;SET/EXTSTATE/ReaSet/autoStopDone/;SET/EXTSTATE/ReaSet/autoStopCancel/1;' + command]
