// ReaSet — legacy engine harness
//
// ReaSet has to run on an iPad that no longer receives updates. Chrome on iOS
// is the system WebKit with a different icon, so the engine there is whatever
// the last iOS for that device shipped — installing another browser changes
// nothing.
//
// Nothing that breaks on that engine throws. It drops the declaration or the
// event it cannot handle and renders something plausible-but-wrong: a Stop
// control that is inert, controls with no space between them, a modal backdrop
// covering a corner. None of it shows up in a test suite that reads the source,
// and none of it shows up in a browser that is not broken.
//
// So this drives the two failure modes that a modern engine cannot reproduce on
// its own:
//
//   1. NO POINTER EVENTS. `window.PointerEvent` is deleted before the page's
//      script runs, which is what makes _HAS_POINTER false and binds the touch
//      and mouse fallback. The gesture is then driven with real touch events —
//      including the synthetic mouse echo a touchscreen sends after touchend,
//      which is the thing that would otherwise stop the show twice.
//
//   3. NO CSS GRID. `display: grid` is Safari 10.1, and the iPad this targets
//      stopped at iOS 9.3.5 — Safari 9. There the declaration is dropped and
//      the element is a block. Forced here by overriding every grid container
//      to `display: block`, which is exactly what that engine does, and then
//      measuring what the page makes of it.
//
//   2. NO FLEX GAP. Every gap is forced to zero, which is what WebKit before
//      14.1 does in a flex container, and the class the real probe would set is
//      applied. Spacing is then compared against the same page unforced.
//
// It is not run by CI: it needs a browser binary, and the point of it is the
// engine, not the source. Run it by hand after touching the transport bar, the
// Stop gesture, or anything that spaces controls with gap.
//
//   npm i playwright
//   node Tools/legacy_engine_test.js [path/to/ReaSet.html]
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
    results.push({ name, pass, detail });
    console.log(`  ${pass ? 'ok  ' : 'FAIL'}  ${name}${detail ? '   ' + detail : ''}`);
}

// Deleting the constructor is what the app actually branches on, so this
// reproduces the engine's behaviour rather than imitating it.
// Overrides every grid container the stylesheet declares, the way an engine
// that has never heard of grid would. Applied as a stylesheet rather than by
// deleting the declarations so the fallback rules still get their chance —
// the point is to check the FALLBACK, not to check that grid is gone.
const KILL_GRID = () => {
    document.documentElement.className += ' no-grid';
    const st = document.createElement('style');
    st.textContent =
        '.song-ctx-palette, .ap-swatches, .ls-swatches, .grid-mode,' +
        '.sview-grid, .two-col, .three-col { display: block !important; }';
    document.head.appendChild(st);
};

const KILL_POINTER = () => {
    try { delete window.PointerEvent; } catch (e) {}
    Object.defineProperty(window, 'PointerEvent', { value: undefined, configurable: true });
};

async function openPage(browser, { mode = 'slide', lang = 'en', noPointer = false, noGap = false, noGrid = false } = {}) {
    const ctx = await browser.newContext({
        viewport: { width: 768, height: 1024 }, hasTouch: true, isMobile: true,
    });
    const page = await ctx.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(String(e).slice(0, 200)));
    await page.addInitScript(([m, l]) => {
        localStorage.setItem('reaset_stop_mode', m);
        localStorage.setItem('reaset_lang', l);
    }, [mode, lang]);
    if (noPointer) await page.addInitScript(KILL_POINTER);
    await page.goto(FILE);
    if (noGap) {
        await page.addStyleTag({ content: '*{gap:0 !important;row-gap:0 !important;column-gap:0 !important}' });
        await page.evaluate(() => { document.documentElement.className += ' no-flexgap'; });
    }
    if (noGrid) await page.evaluate(KILL_GRID);
    await page.waitForTimeout(700);
    return { ctx, page, errors };
}

// ── 1. The transport, on an engine with no Pointer Events ─────────────────
//
// This section used to drive Slide to Stop, which was the one control here
// bound to pointer events and therefore inert on WebKit before 13. Stop is
// gone — pause is what a show needs — and with it the gesture. What is left is
// four plain buttons, and the thing worth proving about them on that engine is
// the unglamorous one: a touch actually reaches them.
//
// It is thinner than what it replaces and says so. The interesting failure
// moved out of the transport when the gesture did.
async function transportResponds(browser) {
    console.log('\n1. Transport buttons with no Pointer Events');
    const { ctx, page, errors } = await openPage(browser, { noPointer: true });

    await page.evaluate(() => {
        window.__calls = [];
        for (const fn of ['togglePlay', 'navSong', 'toggleCurrentLoop']) {
            const real = window[fn];
            window[fn] = function () { window.__calls.push(fn + (arguments[0] ? ':' + arguments[0] : '')); };
            window['__real_' + fn] = real;
        }
    });

    for (const [id, want] of [
        ['footer-prev-btn', 'navSong:prev'],
        ['main-play-btn',   'togglePlay'],
        ['footer-loop-btn', 'toggleCurrentLoop'],
        ['footer-next-btn', 'navSong:next'],
    ]) {
        const el = await page.$('#' + id);
        check(`${id} exists`, !!el);
        if (!el) continue;
        await el.tap().catch(async () => { await el.click(); });
        const calls = await page.evaluate(() => window.__calls);
        check(`${id} responds to a touch`, calls.includes(want),
              `calls=${JSON.stringify(calls)} want=${want}`);
        await page.evaluate(() => { window.__calls = []; });
    }
    check('no page errors', errors.length === 0, errors[0] || '');
    await ctx.close();
}

// ── 2. Spacing, on an engine with no flex gap ─────────────────────────────
//
// Two assertions per container, and the first one is the one that matters.
//
// "The gap-less layout matches the modern one" is necessary but not
// sufficient: if the modern layout has no spacing either, the two agree on
// zero and the check passes on a bar whose controls are touching. This harness
// shipped with exactly that hole — deleting every margin from the transport
// row left it green, because that row is spaced by margins in both modes and
// so can never disagree with itself.
//
// So: the controls must be separated AT ALL, and then the two engines must
// agree about by how much.
async function gapEmulation(browser) {
    console.log('\n2. Control spacing with no flex gap');
    const measure = async (noGap) => {
        const { ctx, page } = await openPage(browser, { noGap });
        const out = await page.evaluate(() => {
            const want = ['.tr-row-main', '.app-topbar-info', '.live-transport', '.modal-actions'];
            const res = {};
            for (const sel of want) {
                const host = document.querySelector(sel);
                if (!host) { res[sel] = null; continue; }
                const undo = [];
                let n = host;
                while (n && n !== document.body) {
                    if (getComputedStyle(n).display === 'none') { undo.push([n, n.style.display]); n.style.display = 'block'; }
                    n = n.parentElement;
                }
                const kids = [...host.children].filter(e => e.offsetWidth || e.offsetHeight);
                res[sel] = kids.length < 2 ? null
                    : Math.round(kids[1].getBoundingClientRect().left - kids[0].getBoundingClientRect().right);
                undo.forEach(([n, d]) => { n.style.display = d; });
            }
            return res;
        });
        await ctx.close();
        return out;
    };
    const modern = await measure(false);
    const legacy = await measure(true);
    for (const sel of Object.keys(modern)) {
        if (modern[sel] === null || legacy[sel] === null) continue;
        // Adjacent touch targets with nothing between them is the failure this
        // whole section exists for; agreeing on zero is not passing.
        check(`${sel} separates its controls`, modern[sel] > 0, `${modern[sel]}px`);
        check(`${sel} keeps that spacing without gap`, Math.abs(modern[sel] - legacy[sel]) <= 2,
              `modern ${modern[sel]}px vs gap-less ${legacy[sel]}px`);
    }
}

// ── 3. Every target stays a target ────────────────────────────────────────
//
// 44pt in both axes is the floor for a finger. It was lost once already: a
// phone on its side is 844px wide and 390px tall, and a width-only media query
// read that as a tablet — the bar took 46% of the screen and left about one
// song visible.
//
// The bar is also checked for what it is NOT: four controls, no more. Every
// button here costs a target a thumb can land on by mistake, and the two that
// were removed — Stop and RECONNECT — were the two nobody presses during a
// song.
async function touchTargets(browser) {
    console.log('\n3. Touch targets');
    const sizes = [
        [844, 390, 'phone landscape'], [390, 844, 'phone portrait'],
        [1024, 768, 'iPad landscape'], [768, 1024, 'iPad portrait'],
        [320, 568, 'small phone'],     [1400, 900, 'desktop'],
    ];
    const IDS = ['footer-prev-btn', 'main-play-btn', 'footer-loop-btn', 'footer-next-btn'];
    for (const [w, h, label] of sizes) {
        const ctx = await browser.newContext({ viewport: { width: w, height: h } });
        const page = await ctx.newPage();
        // Portuguese: the longest labels this app has to fit.
        await page.addInitScript(() => localStorage.setItem('reaset_lang', 'pt'));
        await page.goto(FILE);
        await page.waitForTimeout(600);
        const r = await page.evaluate((ids) => {
            const bar = document.querySelector('.app-transport');
            const boxes = ids.map(id => {
                const el = document.getElementById(id);
                if (!el) return null;
                const b = el.getBoundingClientRect();
                return [Math.round(b.width), Math.round(b.height)];
            });
            return {
                boxes,
                count: bar.querySelectorAll(':scope > button').length,
                barShare: Math.round(bar.getBoundingClientRect().height / window.innerHeight * 100),
                barH: Math.round(bar.getBoundingClientRect().height),
                playWidest: (() => {
                    const w = boxes.map(b => b ? b[0] : 0);
                    return w[1] === Math.max.apply(null, w);
                })(),
            };
        }, IDS);

        check(`${label}: all four controls present`, r.boxes.every(Boolean) && r.count === 4,
              `count=${r.count}`);
        if (!r.boxes.every(Boolean)) { await ctx.close(); continue; }
        const shortest = Math.min.apply(null, r.boxes.map(b => b[1]));
        check(`${label}: every control is at least 44px tall`, shortest >= 44, `shortest ${shortest}px`);
        check(`${label}: PLAY is the widest control`, r.playWidest,
              r.boxes.map((b, i) => IDS[i].replace('footer-', '').replace('-btn', '') + '=' + b[0]).join(' '));
        check(`${label}: the bar does not eat the setlist`, r.barShare <= 32, `${r.barShare}% of the screen`);
        // A hard ceiling in pixels, not just a share of the screen. The bar has
        // grown twice — once to 147px for a two-row layout, once to 120px on a
        // tablet — and both times it was reported as the app looking wrong
        // before any check noticed. 77px is what it was before either.
        check(`${label}: the bar is no taller than it ever was`, r.barH <= 82, `${r.barH}px`);
        await ctx.close();
    }
}

// ── 4. The probe itself ───────────────────────────────────────────────────
async function probeBehaviour(browser) {
    // ── 5. The colour palette on an engine with no CSS Grid ──────────────
    // A swatch is `width: 100%` with `padding-bottom` for its height, and a
    // percentage padding resolves against the CONTAINING BLOCK — the grid area
    // when there is a grid, the whole panel when there is not. Measured with
    // grid forced off and the fallback removed, each swatch came out 239x239
    // across 18 rows. This is the check that would have caught it.
    {
        console.log('\n5. The colour palette with no CSS Grid');
        const { ctx, page, errors } = await openPage(browser, { noGrid: true });
        const m = await page.evaluate(() => {
            displayList = [{ id: '1', uid: 'u1', name: 'X', displayName: 'X', start: 0,
                             end: 200, duration: 200, chain: false, skipped: false,
                             loop: false, color: null }];
            REASET_MODE = 'director';
            document.body.classList.remove('reaset-controller');
            REASET_EDITING = true;
            document.body.classList.add('reaset-editing');
            renderSetlist();
            openSongMenu({ stopPropagation: function () {},
                           currentTarget: document.querySelector('.song-dotmenu-btn') }, 'u1');
            var cb = document.getElementById('_ctx_coloron_u1');
            if (cb) { cb.checked = true; _ctxToggleColor('u1', true); }
            var sw = document.querySelectorAll('.ctx-color-swatch');
            if (!sw.length) return { n: 0 };
            var r = sw[0].getBoundingClientRect();
            var panel = document.querySelector('.song-ctx-panel').getBoundingClientRect();
            var rows = {};
            for (var i = 0; i < sw.length; i++) rows[Math.round(sw[i].getBoundingClientRect().top)] = 1;
            return { n: sw.length, w: Math.round(r.width), h: Math.round(r.height),
                     rows: Object.keys(rows).length,
                     panelBottom: Math.round(panel.bottom), vh: window.innerHeight };
        });
        check('the palette still has its swatches', m.n > 0, `${m.n} swatches`);
        check('a swatch is a swatch, not a slab', m.w > 0 && m.w <= 60 && m.h <= 60,
              `${m.w}x${m.h}`);
        check('it is round, not an oval', Math.abs(m.w - m.h) <= 1, `${m.w}x${m.h}`);
        check('they lay out in rows, not one per line', m.rows > 0 && m.rows <= 6,
              `${m.rows} rows for ${m.n} swatches`);
        check('the panel still fits the screen', m.panelBottom <= m.vh + 1,
              `bottom ${m.panelBottom} of ${m.vh}`);
        check('no page errors', errors.length === 0, errors[0] || '');
        await ctx.close();
    }

    // ── 6. One palette, everywhere ───────────────────────────────────────
    // There were three lists of colours for one decision: eighteen on a song
    // row, five in Appearance → Lyrics, seven in Appearance → Chords. Asserted
    // by COMPARING THE RENDERED SWATCHES rather than by reading the source —
    // the source check would have passed while the Lyrics tab rendered nothing
    // but a custom-colour blob, which is exactly what shipped.
    {
        console.log('\n6. One palette, everywhere');
        const { ctx, page, errors } = await openPage(browser, {});
        const sets = await page.evaluate(() => {
            REASET_MODE = 'director';
            document.body.classList.remove('reaset-controller');
            openAppearanceModal();
            displayList = [{ id: '1', uid: 'u1', name: 'X', displayName: 'X', start: 0,
                             end: 9, duration: 9, chain: false, skipped: false,
                             loop: false, color: null }];
            REASET_EDITING = true;
            document.body.classList.add('reaset-editing');
            renderSetlist();
            openSongMenu({ stopPropagation: function () {},
                           currentTarget: document.querySelector('.song-dotmenu-btn') }, 'u1');
            function colours(sel) {
                var host = document.querySelector(sel);
                if (!host) return null;
                var out = [];
                var sw = host.querySelectorAll('.ls-swatch, .ctx-color-swatch');
                for (var i = 0; i < sw.length; i++) {
                    var c = sw[i].getAttribute('data-color');
                    if (c) out.push(c.toUpperCase());   // the custom swatch has none
                }
                return out;
            }
            return {
                song:   colours('.song-ctx-palette'),
                lyrics: colours('.js-lyr-swatches'),
                chords: colours('#chords-color-selector'),
                popover: colours('#ls-swatches'),
            };
        });
        const song = sets.song || [];
        check('the song row has its palette', song.length >= 12, `${song.length} colours`);
        for (const name of ['lyrics', 'chords', 'popover']) {
            const got = sets[name];
            check(`${name} offers the same colours as a song row`,
                  !!got && got.join(',') === song.join(','),
                  got ? `${got.length} vs ${song.length}` : 'container missing');
        }
        check('no page errors', errors.length === 0, errors[0] || '');
        await ctx.close();
    }

    console.log('\n4. The flex-gap probe');
    const { ctx, page, errors } = await openPage(browser, {});
    const cls = await page.evaluate(() => document.documentElement.className);
    check('does not fire on an engine that supports gap', !/no-flexgap/.test(cls), `class="${cls}"`);
    check('leaves no probe element behind', 0 === await page.evaluate(
        () => document.querySelectorAll('div[style*="visibility:hidden"]').length));
    check('no page errors', errors.length === 0, errors[0] || '');
    await ctx.close();
}

(async () => {
    const browser = await chromium.launch(EXE ? { executablePath: EXE } : {});
    try {
        console.log('ReaSet legacy engine harness —', FILE);
        await transportResponds(browser);
        await gapEmulation(browser);
        await touchTargets(browser);
        await probeBehaviour(browser);
    } finally {
        await browser.close();
    }
    const failed = results.filter(r => !r.pass);
    console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
    if (failed.length) {
        console.log('\nfailed:');
        failed.forEach(f => console.log('  ' + f.name + '   ' + (f.detail || '')));
    }
    process.exit(failed.length ? 1 : 0);
})();
