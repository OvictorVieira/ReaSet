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
const KILL_POINTER = () => {
    try { delete window.PointerEvent; } catch (e) {}
    Object.defineProperty(window, 'PointerEvent', { value: undefined, configurable: true });
};

async function openPage(browser, { mode = 'slide', lang = 'en', noPointer = false, noGap = false } = {}) {
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
        await ctx.close();
    }
}

// ── 4. The probe itself ───────────────────────────────────────────────────
async function probeBehaviour(browser) {
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
