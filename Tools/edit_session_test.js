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

    // ── 3. Colour paints now, and reaches REAPER only on Apply ──────────
    // The original design wrote the region the moment a swatch was tapped and
    // cleared the local override, so the row kept its old colour until REAPER
    // echoed the new one back on the next REGION poll. On a machine whose
    // Reaset.lua was not restarted that echo never arrives, and picking a
    // colour looks like it does nothing whatsoever.
    console.log('\n3. Colour is staged, painted at once, written on Apply');
    const staged = await page.evaluate('(function(){' + `
        enterEditMode();
        window.__sent = [];
        _ctxPickColor('1_1', '#ff0000', false);
        var el = document.getElementById('row-1_1');
        var style = el ? (el.getAttribute('style') || '') : '(no row)';
        return {
            painted:   style.toLowerCase().indexOf('ff0000') !== -1,
            rowStyle:  style.slice(0, 70),
            staged:    JSON.stringify(g_stagedColors),
            sentSoFar: window.__sent.filter(function (c) { return c.indexOf('regionColor') !== -1; }).length
        };
    ` + '})()');
    check('the row paints the moment the swatch is tapped',
          staged.painted === true, staged.rowStyle);
    check('the colour is staged, not yet in the project',
          staged.staged.indexOf('ff0000') !== -1, staged.staged);
    check('nothing has been written to REAPER yet',
          staged.sentSoFar === 0, `${staged.sentSoFar} writes`);

    const discardedColour = await page.evaluate('(function(){' + `
        window.__sent = [];
        discardEdits();
        var el = document.getElementById('row-1_1');
        return {
            staged: JSON.stringify(g_stagedColors),
            sent:   window.__sent.filter(function (c) { return c.indexOf('regionColor') !== -1; }).length,
            style:  el ? (el.getAttribute('style') || '') : ''
        };
    ` + '})()');
    check('Discard drops the staged colour', discardedColour.staged === '{}', discardedColour.staged);
    check('and writes nothing to REAPER, because nothing was ever written',
          discardedColour.sent === 0, `${discardedColour.sent} writes`);
    check('the row stops showing it',
          discardedColour.style.toLowerCase().indexOf('ff0000') === -1,
          discardedColour.style.slice(0, 70));

    const appliedColour = await page.evaluate('(function(){' + `
        enterEditMode();
        // Upper case, the way SONG_COLOR_PALETTE is written — the mismatch
        // against REAPER's lower-case reply is the bug this models.
        _ctxPickColor('1_1', '#00FF00', false);
        _ctxPickColor('2_2', '#0000FF', false);
        window.__sent = [];
        applyEdits();
        var wrote = window.__sent.filter(function (c) { return c.indexOf('regionColor') !== -1; });
        var stillStaged = JSON.stringify(g_stagedColors);
        // REAPER answers: the next REGION poll reports the new colours — in
        // LOWER CASE, because they come back through Number.toString(16),
        // while the palette is written in upper case. Comparing them with ===
        // meant a colour the project HAD taken was never recognised, the
        // staging never cleared, and the watchdog cried "REAPER did not
        // confirm" every single time. Seeded lower-case on purpose.
        g_regionReaperColor['1'] = '#00FF00'.toLowerCase();
        g_regionReaperColor['2'] = '#0000FF'.toLowerCase();
        _confirmStagedColors();
        return { wrote: wrote, stillStaged: stillStaged, afterConfirm: JSON.stringify(g_stagedColors) };
    ` + '})()');
    check('Apply writes every staged colour in ONE request',
          appliedColour.wrote.length === 1, appliedColour.wrote[0] || '(nothing)');
    check('each region gets its own colour',
          /1:00FF00/i.test(appliedColour.wrote[0] || '') && /2:0000FF/i.test(appliedColour.wrote[0] || ''),
          appliedColour.wrote[0]);
    check('the colour stays on screen while REAPER catches up',
          appliedColour.stillStaged.indexOf('00FF00') !== -1, appliedColour.stillStaged);
    check('and the staging clears once the project agrees',
          appliedColour.afterConfirm === '{}', appliedColour.afterConfirm);

    const blockColour = await page.evaluate('(function(){' + `
        enterEditMode();
        displayList[0].chain = true;          // row 1 continues into row 2
        _ctxPickColor('2_2', '#abcdef', true);   // opened from the SECOND row of the block
        var st = JSON.stringify(g_stagedColors);
        window.__sent = [];
        applyEdits();
        return { staged: st,
                 wrote: window.__sent.filter(function (c) { return c.indexOf('regionColor') !== -1; })[0] || '' };
    ` + '})()');
    check('colouring a block stages every song in it, including the one above',
          /"1":"#abcdef"/.test(blockColour.staged) && /"2":"#abcdef"/.test(blockColour.staged),
          blockColour.staged);
    // Comma, not semicolon: `;` separates COMMANDS in REAPER's web interface,
    // so a `;`-joined value was read as several commands and all but the first
    // were dropped. That is what made colouring a block colour one song.
    check('and the block is still one write',
          /1:abcdef,2:abcdef/.test(blockColour.wrote), blockColour.wrote);
    check('the payload is one command, not several',
          (blockColour.wrote.match(/;/g) || []).length === 0, blockColour.wrote);

    // ── 3b. The block-scope switch ──────────────────────────────────────
    // It used to be read only at the instant a swatch was tapped, so picking a
    // colour and THEN asking for the whole block did nothing — which is
    // indistinguishable from a broken switch. And "Remove colour" ignored it
    // entirely, so a block coloured as a unit could not be cleared as one.
    console.log('\n3b. Apply to the whole block');
    const scope = await page.evaluate('(function(){' + `
        // Section 3 left a colour staged and unconfirmed (no REGION poll ran
        // to answer it), and these assertions read the whole staging map.
        g_stagedColors = {};
        enterEditMode();
        setSongEnd(displayList[0].id, 'continue');   // rows 1 and 2 play as one block
        renderSetlist();
        var uid = displayList[1].uid;                 // opened from the SECOND row
        openSongMenu({ stopPropagation: function () {}, currentTarget:
            document.querySelector('#row-' + uid + ' .song-dotmenu-btn') }, uid);
        var hint = _ctxPanel.querySelector('.ctx-scope-hint').textContent;
        var cb = document.getElementById('_ctx_blockscope_' + uid);

        _ctxPickColor(uid, '#FF453A', false);
        var afterPick = JSON.stringify(g_stagedColors);
        cb.checked = true;  _ctxScopeChanged(uid, true);
        var afterOn  = JSON.stringify(g_stagedColors);
        cb.checked = false; _ctxScopeChanged(uid, false);
        var afterOff = JSON.stringify(g_stagedColors);
        cb.checked = true;  _ctxScopeChanged(uid, true);
        _ctxClearColor(uid);
        var afterClear = JSON.stringify(g_stagedColors);
        return { hint: hint, afterPick: afterPick, afterOn: afterOn,
                 afterOff: afterOff, afterClear: afterClear };
    ` + '})()');
    check('the switch says how many songs the block holds',
          /^2 /.test(scope.hint), `"${scope.hint}"`);
    check('picking with the switch off colours one song',
          scope.afterPick === '{"2":"#FF453A"}', scope.afterPick);
    check('turning the switch ON applies the colour already picked',
          /"1":"#FF453A"/.test(scope.afterOn) && /"2":"#FF453A"/.test(scope.afterOn),
          scope.afterOn);
    check('turning it back OFF puts the other songs back',
          scope.afterOff === '{"2":"#FF453A"}', scope.afterOff);
    check('Remove colour clears the whole block when the switch is on',
          /"1":null/.test(scope.afterClear) && /"2":null/.test(scope.afterClear),
          scope.afterClear);
    await page.evaluate('(function(){ discardEdits(); })()');

    // ── 4. The revert has to reach the other devices ────────────────────
    // The Director's own screen going back is half the job. saveCurrentState()
    // is what persists the restored order and schedules the push, so if
    // Discard ever stops calling it the room keeps playing the edited set
    // while the Director looks at the original — the worst of both.
    console.log('\n4. The revert is published, not just repainted');
    const published = await page.evaluate('(function(){' + `
        saveCurrentState();          // baseline: the signature must describe the state we are actually in
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
