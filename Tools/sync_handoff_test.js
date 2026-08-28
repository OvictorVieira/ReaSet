// ReaSet — Director → Controller handoff harness
//
// The app's whole reason to exist: the Director owns the setlist and every
// other device follows it. Nothing about that is provable by reading one file.
// The Director serialises to ExtState, Reaset.lua reassembles the chunks into a
// file, and the follower fetches, decodes and REBUILDS its list from it. The
// interesting failures live in the seam, and they are silent — the follower
// takes the new setlist NAME, renders the old rows underneath it, and looks
// like it is following.
//
// So this runs TWO real pages against one shared fake REAPER: every ExtState
// write the Director makes is captured, reassembled the way Reaset.lua does
// (length guard included), and handed to the follower through its own apply
// path.
//
// What it caught, and what it exists to keep caught: the follower resolved
// each payload entry against `displayList` — its CURRENT setlist — so it could
// only ever adopt songs it already had. Selecting a different set on the
// Director published the right payload, the follower took the name and dropped
// every song the old set did not contain, and a leftover pass re-appended the
// old list underneath. The follower ended up with exactly what it started
// with, under the new name, and a reload put it back on the local default.
//
//   npm i playwright
//   node Tools/sync_handoff_test.js [path/to/ReaSet.html]
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

// Four regions and two setlists that share no songs. That is the case the
// report came from and the one the old code could not represent: if the two
// sets overlap, resolving against the current list accidentally works.
const SEED = `
    g_regions = [
        ['REGION','ONE','1','0','100','0'],    ['REGION','TWO','2','100','200','0'],
        ['REGION','THREE','3','200','300','0'],['REGION','FOUR','4','300','400','0']
    ];
    setlists = { Default: [{id:'1'},{id:'2'}], Gig: [{id:'3'},{id:'4'}] };
    currentSetlistName = 'Default';
    displayList = []; initialized = false; lastRenderChecksum = '';
    syncRegions();
    // The hidden <select> is the source changeSetlist() reads. Without this it
    // has no option to select and the switch is refused — which would look
    // like the bug while testing nothing.
    updateSetlistDropdown();
`;

(async () => {
    const browser = await chromium.launch(EXE ? { executablePath: EXE } : {});
    const shared = { ext: {}, file: null };
    const errors = [];

    async function openDevice(role) {
        const ctx = await browser.newContext({ viewport: { width: 1100, height: 900 } });
        const page = await ctx.newPage();
        page.on('pageerror', e => errors.push(role + ': ' + String(e).slice(0, 200)));
        await page.exposeFunction('__extSet', (k, v) => { shared.ext[k] = v; });
        await page.exposeFunction('__extAll', () => shared.ext);
        await page.exposeFunction('__fileGet', () => shared.file);
        await page.goto(FILE);
        await page.waitForTimeout(600);
        await page.evaluate((role) => {
            // REAPER's ExtState, shared between the two pages. Splitting on ';'
            // is what REAPER's web interface itself does with a compound
            // request, so a value must never contain one.
            window.wwr_req = function (cmd) {
                String(cmd).split(';').forEach(function (one) {
                    var m = one.match(/^SET\/EXTSTATE\/ReaSet\/([^/]+)\/([\s\S]*)$/);
                    if (m) window.__extSet(m[1], m[2]);
                });
            };
            REASET_MODE = role; applyModeUI();
            // The fingerprint gate in _syncApplyPayload: nothing applies until
            // the project is identified.
            g_projectKey = 'PROJ-1';
        }, role);
        await page.evaluate(SEED);
        return page;
    }

    // Reaset.lua's half of the seam, including the length guard that stops two
    // generations of chunks being stitched into one unparseable payload.
    const assemble = (page) => page.evaluate(async () => {
        const ext = await window.__extAll();
        const n = parseInt(ext.setlistChunkCount, 10);
        let b64 = '';
        for (let i = 0; i < n; i++) b64 += ext['setlistChunk' + i] || '';
        if (b64.length !== parseInt(ext.setlistChunkLen, 10)) return null;
        return { b64: b64 };
    });
    const pull = (page) => page.evaluate(async () => {
        const f = await window.__fileGet();
        if (!f) return null;
        _syncApplyPayload(JSON.parse(_b64uDecode(f.b64)), false);
        return { set: currentSetlistName, rows: displayList.map(r => r.name).join(',') };
    });
    const state = (page) => page.evaluate(() => ({
        set: currentSetlistName, rows: displayList.map(r => r.name).join(',')
    }));
    // What a Controller can actually READ. It has no picker — the Director
    // owns which set is live — so the banner is the only place the show's name
    // appears on that device, and a name that stays on the local default while
    // the rows change is the same bug from the other side.
    const banner = (page) => page.evaluate(() => {
        const nm = document.getElementById('setlistBannerName');
        const bn = document.getElementById('setlistBanner');
        const pk = document.getElementById('setlistPicker');
        return {
            text: nm ? nm.textContent : '(gone)',
            shown: !!bn && getComputedStyle(bn).display !== 'none',
            pickerShown: !!pk && getComputedStyle(pk).display !== 'none'
        };
    });

    try {
        const director = await openDevice('director');
        let controller = await openDevice('controller');

        console.log('\n1. The Director selects a different setlist');
        check('both devices start on the same set',
              JSON.stringify(await state(director)) === JSON.stringify(await state(controller)),
              JSON.stringify(await state(controller)));

        await director.evaluate(() => {
            var sel = document.getElementById('setlistSelect');
            sel.value = 'Gig';
            if (sel.value !== 'Gig') throw new Error('the picker has no Gig option');
            changeSetlist();
        });
        await director.waitForTimeout(200);
        shared.file = await assemble(director);
        check('the Director is on the new set', (await state(director)).rows === 'THREE,FOUR',
              JSON.stringify(await state(director)));
        check('the push assembled into a shared file', !!shared.file,
              shared.file ? '' : 'chunk length did not match');

        let got = await pull(controller);
        check('the Controller follows the set change',
              !!got && got.set === 'Gig' && got.rows === 'THREE,FOUR', JSON.stringify(got));

        const bn = await banner(controller);
        check('the Controller reads the show name, not its own default',
              bn.text === 'Gig', JSON.stringify(bn));
        check('and it is on screen', bn.shown === true, JSON.stringify(bn));
        check('with no picker beside it — the Director owns the choice',
              bn.pickerShown === false, JSON.stringify(bn));

        console.log('\n2. A reload must not fall back to the local default');
        await controller.context().close();
        controller = await openDevice('controller');
        check('a fresh Controller starts on its own stored set',
              (await state(controller)).rows === 'ONE,TWO', JSON.stringify(await state(controller)));
        got = await pull(controller);
        check('and its first pull puts it on the shared set',
              !!got && got.set === 'Gig' && got.rows === 'THREE,FOUR', JSON.stringify(got));

        console.log('\n3. Every edit reaches the follower');
        await director.evaluate(() => { removeFromSetlist(displayList[0].uid); _syncPushNow(); });
        await director.waitForTimeout(200);
        shared.file = await assemble(director);
        check('the Director removed a song', (await state(director)).rows === 'FOUR',
              JSON.stringify(await state(director)));
        got = await pull(controller);
        // The one the "keep anything the payload does not mention" rule made
        // impossible: a follower could never lose a song.
        check('the Controller loses it too', !!got && got.rows === 'FOUR', JSON.stringify(got));

        await director.evaluate(() => { addSongToSetlist('1'); _syncPushNow(); });
        await director.waitForTimeout(200);
        shared.file = await assemble(director);
        const added = (await state(director)).rows;
        check('the Director added a song the set did not have', added.indexOf('ONE') !== -1, added);
        got = await pull(controller);
        check('the Controller gains it too', !!got && got.rows === added,
              `${got && got.rows} vs ${added}`);

        await director.evaluate(() => { displayList.reverse(); saveCurrentState(); _syncPushNow(); });
        await director.waitForTimeout(200);
        shared.file = await assemble(director);
        const reordered = (await state(director)).rows;
        got = await pull(controller);
        check('the Controller follows a reorder', !!got && got.rows === reordered,
              `${got && got.rows} vs ${reordered}`);

        console.log('\n4. The follower does not talk back');
        const pushedBefore = shared.ext.setlistRev;
        await controller.evaluate(() => { saveCurrentState(); _syncPushNow(); });
        await controller.waitForTimeout(100);
        check('applying a payload does not re-broadcast it',
              shared.ext.setlistRev === pushedBefore,
              `rev ${pushedBefore} -> ${shared.ext.setlistRev}`);

        check('no page errors', errors.length === 0, errors[0] || '');
    } finally {
        await browser.close();
    }

    const failed = results.filter(r => !r.pass);
    console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
    if (failed.length) {
        console.log('\nfailed:');
        failed.forEach(f => console.log('  ' + f.name));
    }
    process.exit(failed.length ? 1 : 0);
})();
