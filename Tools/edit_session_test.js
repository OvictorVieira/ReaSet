// ReaSet — edit session harness
//
// Edit mode became a TRANSACTION: entering takes a snapshot, Apply keeps the
// changes and Discard puts everything back. None of that is provable by
// reading the source. "Discard restores displayList" is a claim about what a
// sequence of real calls leaves behind, and the interesting failure — the save
// signature swallowing the revert, so the Director's screen goes back while
// every follower stays on the edited set — looks identical to success from
// inside the function that was changed.
//
// So this drives the real page: seed a set, enter edit mode, mutate it, and
// read the state back out afterwards.
//
//   npm i playwright
//   node Tools/edit_session_test.js [path/to/ReaSet.html]
//
// Exit code is 0 only if every check passes.

const path = require('path');

let chromium;
try {
    ({ chromium } = require('playwright'));
} catch (e) {
    console.error('playwright is not installed.  npm i playwright');
    process.exit(2);
}

const FILE = 'file://' + path.resolve(process.argv[2] || path.join(__dirname, '..', 'ReaSet.html'));
const EXE = process.env.CHROMIUM_PATH || undefined;

const results = [];
function check(name, pass, detail) {
    results.push({ name, pass });
    console.log(`  ${pass ? 'ok  ' : 'FAIL'}  ${name}${detail ? '   ' + detail : ''}`);
}

// Three real REGION rows, fed in the shape REAPER's Web Remote sends, so the
// page bootstraps its own setlist from them. Handing displayList a literal
// would skip the reconciliation that discardEdits() ends on — and that
// reconciliation is the step that decides whether a restored row survives.
const SEED = `
    window.__sent = [];
    window.wwr_req = function (cmd, reason) { window.__sent.push(cmd); };
    // name, id, start, end, colour — colour as the 0xRRGGBB int REAPER sends.
    g_regions = [
        ['REGION', 'ONE',   '1', '0',   '100', String(0x112233)],
        ['REGION', 'TWO',   '2', '100', '200', '0'],
        ['REGION', 'THREE', '3', '200', '300', String(0x445566)]
    ];
    setlists = { Default: [] };
    currentSetlistName = 'Default';
    displayList = []; initialized = false; lastRenderChecksum = '';
    REASET_MODE = 'director';
    document.body.classList.remove('reaset-controller');
    syncRegions();
`;

const snap = () => ({
    order:   displayList.map(r => r.uid).join(','),
    loops:   displayList.map(r => (r.loop ? 1 : 0)).join(''),
    skips:   displayList.map(r => (r.skipped ? 1 : 0)).join(''),
    ov:      JSON.stringify(g_songOverrides),
});

(async () => {
    const browser = await chromium.launch({ executablePath: EXE });
    const page = await browser.newPage({ viewport: { width: 1200, height: 900 } });
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    await page.goto(FILE);
    await page.waitForTimeout(600);
    await page.addScriptTag({ content: 'window.__snap = ' + snap.toString() + ';' });

    // ── 1. The way in says what it does ─────────────────────────────────────
    console.log('\n1. The button names the action');
    const entry = await page.evaluate('(function(){' + SEED + `
        _refreshEditModeBtn();
        var b = document.getElementById('editModeBtn');
        var acts = document.getElementById('editActions');
        return {
            label: document.getElementById('editModeLabel').textContent.trim(),
            btnShown:  getComputedStyle(b).display !== 'none',
            actsShown: getComputedStyle(acts).display !== 'none'
        };
    ` + '})()');
    check('the button reads EDIT, not the mode you are already in',
          entry.label === 'EDIT', `label="${entry.label}"`);
    check('EDIT is on screen before you are editing', entry.btnShown === true);
    check('Apply/Discard are not', entry.actsShown === false);

    const opened = await page.evaluate('(function(){' + `
        enterEditMode();
        var b = document.getElementById('editModeBtn');
        var acts = document.getElementById('editActions');
        return {
            editing: !!REASET_EDITING,
            btnShown:  getComputedStyle(b).display !== 'none',
            actsShown: getComputedStyle(acts).display !== 'none',
            labels: [...acts.querySelectorAll('.ea-label')].map(e => e.textContent.trim())
        };
    ` + '})()');
    check('tapping EDIT enters edit mode', opened.editing === true);
    check('EDIT steps aside once you are in', opened.btnShown === false);
    check('Apply and Discard take its place', opened.actsShown === true,
          opened.labels.join(' / '));
    check('both ways out are offered',
          opened.labels.length === 2 && opened.labels.indexOf('DISCARD') !== -1
                                     && opened.labels.indexOf('APPLY') !== -1);

    // ── 2. Discard puts the setlist back ────────────────────────────────────
    console.log('\n2. Discard restores what was there');
    const discard = await page.evaluate('(function(){' + `
        var before = window.__snap();
        // Three different kinds of edit, because they are stored three
        // different ways: a per-ROW flag, the order, and a per-SONG override.
        displayList[1].loop = true;
        displayList[2].skipped = true;
        displayList.reverse();
        setSongOverride('2', 'description', 'scratch');
        var dirty = window.__snap();
        discardEdits();
        var after = window.__snap();
        return { before: before, dirty: dirty, after: after, editing: !!REASET_EDITING };
    ` + '})()');
    check('the edits actually landed first (or the test proves nothing)',
          discard.dirty.order !== discard.before.order &&
          discard.dirty.loops !== discard.before.loops &&
          discard.dirty.ov    !== discard.before.ov,
          `${discard.before.order} -> ${discard.dirty.order}`);
    check('order comes back',     discard.after.order === discard.before.order,
          `${discard.dirty.order} -> ${discard.after.order}`);
    check('loop flags come back', discard.after.loops === discard.before.loops);
    check('skip flags come back', discard.after.skips === discard.before.skips);
    check('overrides come back',  discard.after.ov    === discard.before.ov);
    check('and the session is over', discard.editing === false);

    // ── 3. Discard reaches into the REAPER project too ──────────────────────
    console.log('\n3. Discard un-paints the regions');
    const colour = await page.evaluate('(function(){' + `
        enterEditMode();
        window.__sent = [];
        _pushRegionColor(['1','2'], '#ff0000');
        var painted = window.__sent.slice();
        window.__sent = [];
        discardEdits();
        var reverted = window.__sent.filter(function (c) { return c.indexOf('regionColor') !== -1; });
        return { painted: painted, reverted: reverted };
    ` + '})()');
    const revert = (colour.reverted[0] || '');
    check('painting reaches Reaper', /regionColor\/1:ff0000;2:ff0000/.test(colour.painted[0] || ''),
          colour.painted[0]);
    check('Discard pushes each region back to the colour it had',
          /1:112233/.test(revert) && /2:x/.test(revert), revert);
    check('a region that had no colour goes back to having none, not to black',
          /2:x/.test(revert));

    // Two colours in one session. What Discard owes is the colour the project
    // had on the way IN, not the one it had a moment ago — otherwise changing
    // your mind twice leaves the second choice behind.
    const twice = await page.evaluate('(function(){' + `
        enterEditMode();
        _pushRegionColor(['1'], '#ff0000');
        // A REGION poll lands about once a second, and it is what refreshes
        // g_regionReaperColor. Without this line the two paints are
        // indistinguishable and the test cannot see the bug it exists for.
        g_regionReaperColor['1'] = '#ff0000';
        _pushRegionColor(['1'], '#00ff00');
        window.__sent = [];
        discardEdits();
        return window.__sent.filter(function (c) { return c.indexOf('regionColor') !== -1; })[0] || '';
    ` + '})()');
    check('two changes in one session still undo to the colour it started with',
          /1:112233/.test(twice), twice);

    // ── 4. The revert has to reach the other devices ────────────────────
    // The Director's own screen going back is half the job. saveCurrentState()
    // is what persists the restored order and schedules the push, so if
    // Discard ever stops calling it the room keeps playing the edited set
    // while the Director looks at the original — the worst of both.
    console.log('\n4. The revert is published, not just repainted');
    const published = await page.evaluate('(function(){' + `
        enterEditMode();
        var sigBefore = _lastSavedSig;
        displayList[0].loop = true;
        saveCurrentState();                 // signature now describes the EDIT
        var sigEdited = _lastSavedSig;
        discardEdits();
        return { sigBefore: sigBefore, sigEdited: sigEdited,
                 sigAfter: _lastSavedSig, loop0: !!displayList[0].loop };
    ` + '})()');
    check('the edit was published first (or there is nothing to take back)',
          published.sigEdited !== published.sigBefore);
    check('Discard saves and publishes the restored state',
          published.sigAfter === published.sigBefore,
          'the last thing sent describes the ORIGINAL set');
    check('and the flag really is off again', published.loop0 === false);

    // ── 5. Apply keeps everything ───────────────────────────────────────────
    console.log('\n5. Apply keeps the work');
    const applied = await page.evaluate('(function(){' + `
        enterEditMode();
        displayList[0].skipped = true;
        applyEdits();
        return { editing: !!REASET_EDITING, skipped: !!displayList[0].skipped };
    ` + '})()');
    check('Apply ends the session', applied.editing === false);
    check('Apply keeps the change', applied.skipped === true);

    // ── 6. A Controller has no way in ───────────────────────────────────────
    console.log('\n6. Editing is the Director\'s');
    const ctrl = await page.evaluate('(function(){' + `
        REASET_MODE = 'controller';
        document.body.classList.add('reaset-controller');
        enterEditMode();
        var acts = document.getElementById('editActions');
        return { editing: !!REASET_EDITING, actsShown: getComputedStyle(acts).display !== 'none' };
    ` + '})()');
    check('a Controller cannot enter edit mode', ctrl.editing === false);
    check('and is not shown the buttons', ctrl.actsShown === false);

    check('the page threw nothing', errors.length === 0, errors.join(' | '));

    await browser.close();
    const failed = results.filter(r => !r.pass);
    console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
    process.exit(failed.length ? 1 : 0);
})();
