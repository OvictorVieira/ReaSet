// ReaSet — stage race harness
//
// Paste into the browser console with ReaSet open as Director, REAPER running,
// and a real project loaded. Drives the SAME entry points a finger drives
// (playRegion / togglePlay / smartStop), so what it exercises is the shipping
// code path, not a parallel one.
//
// It exists because the two tests that matter most in this epic — #3's
// tap-then-Play race and #4's stop-at-the-boundary race — are specified as
// "repeat at least 20 times". A race that reproduces 1 time in 20 is still a
// ruined show, and 20 manual reps judged by eye is both slow and unreliable.
//
//   RSTest.help()
//   RSTest.race({ target: 3, reps: 20, tapGapMs: 60 })
//   RSTest.stopAtEnd({ song: 1, reps: 20, beforeEndMs: 300 })
//
// It moves REAPER. Do not run it during a show.

window.RSTest = (function () {
    function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }

    function activeIdx() {
        for (var i = 0; i < displayList.length; i++) {
            var r = displayList[i];
            if (currentPos >= r.start && currentPos < r.end) return i;
        }
        return -1;
    }

    function nameOf(i) {
        var r = displayList[i];
        return r ? (r.displayName || r.name) : '(nenhuma)';
    }

    // Polls a predicate rather than sleeping a fixed amount: the whole subject
    // here is timing, so the harness must not add guesses of its own.
    async function waitFor(pred, timeoutMs, label) {
        var t0 = Date.now();
        while (Date.now() - t0 < timeoutMs) {
            if (pred()) return true;
            await sleep(25);
        }
        console.warn('[RSTest] timeout esperando: ' + label);
        return false;
    }

    async function settleStopped() {
        smartStop();
        await waitFor(function () { return !isPlaying; }, 3000, 'transporte parar');
        // Past the manual-intent guard and the stop rewind, so each rep starts
        // from a genuinely idle transport instead of the tail of the last one.
        await sleep(1200);
    }

    function pickable(n) {
        var out = [];
        for (var i = 0; i < displayList.length; i++) {
            if (!displayList[i].skipped) out.push(i);
        }
        if (out.indexOf(n) === -1) return out.length > 1 ? out[1] : out[0];
        return n;
    }

    return {
        help: function () {
            console.log([
                'RSTest.race({target, reps, tapGapMs})      #3 — tap na música e Play imediato',
                'RSTest.stopAtEnd({song, reps, beforeEndMs}) #4 — Stop no fim da região',
                '',
                'target/song = índice na lista (0 = primeira). Use RSTest.list().',
                'Ambos movem o REAPER. Nao rode durante um show.'
            ].join('\n'));
        },

        list: function () {
            for (var i = 0; i < displayList.length; i++) {
                console.log(i + ': ' + nameOf(i) + (displayList[i].skipped ? '  (skipped)' : ''));
            }
        },

        // #3 / T02 — the whole point is that the Play lands BEFORE the TRANSPORT
        // reply that would confirm the seek. tapGapMs below one poll interval is
        // what puts it inside that window.
        race: async function (opts) {
            opts = opts || {};
            var target = pickable(opts.target === undefined ? 3 : opts.target);
            var reps = opts.reps || 20;
            var gap = opts.tapGapMs === undefined ? 60 : opts.tapGapMs;
            var want = displayList[target];
            if (!want) { console.error('[RSTest] índice inválido'); return; }

            console.log('[RSTest] race: ' + reps + 'x → "' + nameOf(target) + '" (gap ' + gap + 'ms)');
            var fails = [];

            for (var n = 1; n <= reps; n++) {
                await settleStopped();

                playRegion(want.start, want.id);   // o toque
                await sleep(gap);
                togglePlay();                       // o Play, antes da resposta chegar

                await waitFor(function () { return isPlaying; }, 4000, 'playback iniciar');
                await sleep(700);                   // deixa a posição assentar

                var got = activeIdx();
                var ok = (got === target);
                if (!ok) fails.push({ rep: n, esperado: nameOf(target), obtido: nameOf(got) });
                console.log('  ' + n + '/' + reps + ' ' + (ok ? 'PASS' : 'FAIL → tocou "' + nameOf(got) + '"'));
            }

            smartStop();
            console.log('[RSTest] race: ' + (reps - fails.length) + '/' + reps + ' PASS');
            if (fails.length) console.table(fails);
            else console.log('[RSTest] nenhuma falha. Confira tambem se ouviu algum inicio de outra musica.');
            return { reps: reps, fails: fails };
        },

        // #4 / T11 — seeks to just before the region end instead of playing the
        // whole song, so a rep costs seconds rather than minutes. What is under
        // test is the Stop at the boundary, not how the playhead got there.
        stopAtEnd: async function (opts) {
            opts = opts || {};
            var song = pickable(opts.song === undefined ? 1 : opts.song);
            var reps = opts.reps || 20;
            var beforeEnd = (opts.beforeEndMs === undefined ? 300 : opts.beforeEndMs) / 1000;
            var r = displayList[song];
            if (!r) { console.error('[RSTest] índice inválido'); return; }
            if (r.duration < 8) { console.warn('[RSTest] região muito curta, escolha outra'); return; }

            console.log('[RSTest] stopAtEnd: ' + reps + 'x em "' + nameOf(song) + '"');
            var fails = [];

            for (var n = 1; n <= reps; n++) {
                await settleStopped();

                wwr_req('SET/POS/' + (r.end - 5) + ';1007', 'rstest-seek-near-end');
                await waitFor(function () { return isPlaying; }, 4000, 'playback iniciar');

                var reached = await waitFor(function () {
                    return currentPos >= r.end - beforeEnd && currentPos < r.end;
                }, 8000, 'chegar perto do fim');
                if (!reached) { console.log('  ' + n + '/' + reps + ' SKIP (nao chegou na janela)'); continue; }

                smartStop();
                await sleep(2500);   // tempo de sobra para um callback atrasado agir

                var got = activeIdx();
                var stopped = !isPlaying;
                var advanced = (got !== song && got !== -1);
                var ok = stopped && !advanced;
                if (!ok) {
                    fails.push({
                        rep: n,
                        parado: stopped,
                        avancou_para: advanced ? nameOf(got) : '—'
                    });
                }
                console.log('  ' + n + '/' + reps + ' ' + (ok ? 'PASS' :
                    'FAIL → ' + (stopped ? '' : 'continuou tocando ') + (advanced ? 'avancou para "' + nameOf(got) + '"' : '')));
            }

            smartStop();
            console.log('[RSTest] stopAtEnd: ' + (reps - fails.length) + '/' + reps + ' PASS');
            if (fails.length) console.table(fails);
            return { reps: reps, fails: fails };
        }
    };
})();
console.log('[RSTest] pronto. RSTest.help()');
