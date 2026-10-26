// Optional browser checks. No frontend build or production Node dependency.
const {test, before, after} = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const {spawn} = require('node:child_process');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
let server, browser, base;

function fixture() {
  const track = (id, filename, extra = {}) => ({track_id: id, filename, size_bytes: 8400000,
    available: true, desired: null, observed: false, pending_download: false,
    pending_removal: false, last_error: null, ...extra});
  return {csrf_token: 'fixture-csrf', reported_at: '2026-10-26T09:42:00+00:00',
    latest_sync: {outcome: 'success'}, association: {server_id: 'fixture-server',
      device_epoch: 'fixture-watch', confirmed: true},
    tracks: [track('a', 'Morning Miles.mp3', {desired: true, observed: true}),
      track('b', 'Find Your Pace.mp3', {desired: true, pending_download: true}),
      track('c', 'The Long Way Home.mp3', {desired: true, pending_download: true}),
      track('d', 'Late Night Loop.mp3', {desired: false, observed: true, pending_removal: true}),
      track('e', 'Open Road.mp3'),
      track('f', 'Sunday Sunrise.mp3', {available: false, observed: true})],
    inventory: ['a', 'd', 'f'].map(id => ({track_id: id, cache_id: 'cache-' + id}))};
}
before(async () => {
  server = http.createServer(async (req, res) => {
    const files = {'/': 'index.html', '/static/app.js': 'app.js', '/static/style.css': 'style.css'};
    if (!files[req.url]) {res.writeHead(404).end(); return;}
    res.setHeader('Content-Type', req.url.endsWith('.js') ? 'text/javascript' :
      req.url.endsWith('.css') ? 'text/css' : 'text/html');
    res.setHeader('Content-Security-Policy', "default-src 'self'; frame-ancestors 'none'; object-src 'none'");
    res.end(await fs.readFile(path.join(__dirname, '../src/garmin_sync/static', files[req.url])));
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  base = 'http://127.0.0.1:' + server.address().port;
  browser = await chromium.launch({headless: true, ...(process.env.CHROMIUM_PATH ?
    {executablePath: process.env.CHROMIUM_PATH} : {})});
});
after(async () => {await browser?.close(); await new Promise(resolve => server?.close(resolve));});

async function client(t, data = fixture(), options = {}) {
  const page = await browser.newPage({viewport: {width: 1440, height: 1000}});
  page.setDefaultTimeout(2000);
  await page.clock.install();
  const state = {data, offline: false, failMutation: false, requests: [], reads: 0, ...options};
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  t.after(async () => {await page.close(); assert.deepEqual(errors, []);});
  await page.route('**/api/local/**', async route => {
    const request = route.request();
    if (state.offline) {await route.abort(); return;}
    if (request.method() === 'GET') {
      state.reads++;
      const snapshot = JSON.stringify(state.data);
      if (state.holdRead) await state.holdRead;
      await route.fulfill({json: JSON.parse(snapshot)}); return;
    }
    state.requests.push({url: request.url(), method: request.method(),
      body: request.postDataJSON(), csrf: request.headers()['x-csrf-token']});
    if (state.holdMutation) await state.holdMutation;
    if (state.failMutation) {await route.fulfill({status: 409, json: {detail: 'Fixture save failed'}}); return;}
    if (request.url().includes('/desired/')) {
      const track = state.data.tracks.find(t => request.url().endsWith('/' + t.track_id));
      track.desired = request.postDataJSON().present;
      track.pending_download = track.desired && track.observed !== true;
      track.pending_removal = !track.desired && track.observed !== false;
    }
    if (request.url().endsWith('/association/confirm')) state.data.association.confirmed = true;
    await route.fulfill({json: {ok: true}});
  });
  await page.goto(base);
  if (!state.offline) await page.waitForFunction(() => document.querySelector('#connection')?.textContent.includes('connected'));
  return {page, state};
}
const row = (page, name) => page.locator('#library-body tr').filter({hasText: name});
const view = (page, filter) => page.locator(`[data-filter="${filter}"]`).click();

test('search combines with views and preserves query during polling', async t => {
  const {page, state} = await client(t);
  await page.getByRole('searchbox', {name: 'Search library'}).fill('Long Way');
  await view(page, 'pending');
  assert.equal(await page.locator('#library-body tr:visible').count(), 1);
  await page.clock.runFor(5100);
  await page.waitForFunction(() => document.querySelector('#connection').textContent.includes('connected'));
  assert.ok(state.reads >= 2);
  assert.equal(await page.getByRole('searchbox').inputValue(), 'Long Way');
  await view(page, 'watch');
  assert.match(await page.locator('#empty').innerText(), /No music matches/);
});

test('requests, cancellations and removals use existing API and preserve reported presence', async t => {
  const {page, state} = await client(t);
  await row(page, 'Open Road').getByRole('button', {name: 'Download to watch', exact: true}).click();
  await page.getByText('Download requested. Start Sync on your watch.', {exact: true}).waitFor();
  assert.deepEqual(state.requests[0], {url: base + '/api/local/desired/e', method: 'PUT',
    body: {present: true}, csrf: 'fixture-csrf'});
  assert.equal(state.data.tracks[4].observed, false);
  await row(page, 'Open Road').getByRole('button', {name: 'Cancel download request'}).click();
  await page.waitForFunction(() => document.querySelector('#feedback').textContent.includes('Download request cancelled'));
  await row(page, 'Morning Miles').getByRole('button', {name: 'Remove watch copy', exact: true}).click();
  await page.waitForFunction(() => document.querySelector('#feedback').textContent.includes('Removal requested'));
  assert.equal(state.data.tracks[0].observed, true);
  assert.match(await row(page, 'Morning Miles').innerText(), /Removal requested/);
  await row(page, 'Late Night').getByRole('button', {name: 'Keep on watch'}).click();
  await page.waitForFunction(() => document.querySelector('#feedback').textContent.includes('Removal request cancelled'));
  assert.equal(state.data.tracks[3].desired, true);
});

test('unknown inventory, empty report and retained unknown cache entries stay distinct', async t => {
  const data = fixture(); data.inventory = null; data.reported_at = null;
  data.tracks.forEach(t => {t.observed = null;});
  const {page, state} = await client(t, data);
  await view(page, 'watch');
  assert.match(await page.locator('#empty').innerText(), /unknown/i);
  state.data.inventory = []; state.data.reported_at = '2026-10-26T10:00:00Z';
  await page.clock.runFor(5100);
  await page.getByText('No tracks in the last complete watch report.', {exact: true}).waitFor();
  state.data.inventory = [{track_id: null, cache_id: 'unmapped', filename: 'Unknown cached song'}];
  await page.clock.runFor(5100);
  await row(page, 'Unknown cached song').waitFor();
  assert.equal(await row(page, 'Unknown cached song').getByRole('button').count(), 0);
  assert.match(await row(page, 'Unknown cached song').innerText(), /retained/i);
});

test('unavailable originals remain removable and errors are rendered as text', async t => {
  const data = fixture();
  data.tracks[5].filename = '<img src=x onerror=alert(1)>.mp3';
  data.tracks[5].last_error = '<b>Download failed</b>';
  data.tracks[5].desired = false; data.tracks[5].pending_removal = true;
  const {page} = await client(t, data);
  await view(page, 'attention');
  assert.equal(await page.locator('#library-body tr').count(), 1);
  assert.equal(await page.locator('#library-body img,#library-body b').count(), 0);
  assert.match(await page.locator('#library-body').innerText(), /<b>Download failed<\/b>/);
  assert.equal(await page.getByRole('button', {name: 'Keep on watch'}).count(), 0);
  assert.equal(await page.getByRole('button', {name: 'Remove watch copy', exact: true}).count(), 0);
  // A removal already requested remains pending; other unavailable watch copies can be removed.
  const {page: other} = await client(t, fixture());
  await view(other, 'attention');
  await other.getByRole('button', {name: 'Remove watch copy', exact: true}).click();
  await other.getByText('Removal requested. PC original stays unchanged. Start Sync on your watch.', {exact: true}).waitFor();
});

test('failed requests retain choices; offline polling retains report and retry recovers', async t => {
  const {page, state} = await client(t);
  state.failMutation = true;
  await row(page, 'Open Road').getByRole('button', {name: 'Download to watch', exact: true}).click();
  await page.getByText('Fixture save failed', {exact: true}).waitFor();
  assert.equal(state.data.tracks[4].desired, null);
  const timestamp = await page.locator('#reported-time').innerText();
  state.offline = true;
  await page.clock.runFor(5100);
  await page.waitForFunction(() => document.querySelector('#connection').textContent.includes('unavailable'));
  assert.equal(await page.locator('#reported-time').innerText(), timestamp);
  assert.equal(await page.locator('#library-body tr').count(), 6);
  state.offline = false;
  await page.getByRole('button', {name: 'Retry connection'}).click();
  await page.waitForFunction(() => document.querySelector('#connection').textContent.includes('connected'));
});

test('initial offline and empty library states provide recovery guidance', async t => {
  const {page, state} = await client(t, fixture(), {offline: true});
  await page.waitForFunction(() => document.querySelector('#connection').textContent.includes('unavailable'));
  assert.match(await page.locator('#empty').innerText(), /connect/i);
  state.offline = false; state.data.tracks = []; state.data.inventory = [];
  await page.getByRole('button', {name: 'Retry connection'}).click();
  await page.waitForFunction(() => document.querySelector('#connection').textContent.includes('connected'));
  assert.match(await page.locator('#empty').innerText(), /No MP3 files indexed/);
});

test('polling preserves actual focused nodes and disappearing actions return focus to the view', async t => {
  const {page, state} = await client(t);
  const action = row(page, 'Open Road').getByRole('button', {name: 'Download to watch', exact: true});
  await action.focus();
  await page.evaluate(() => {window.focusedBefore = document.activeElement;});
  await page.clock.runFor(5100);
  await page.waitForFunction(() => document.activeElement === window.focusedBefore);
  assert.equal(await page.evaluate(() => document.activeElement === window.focusedBefore && window.focusedBefore.isConnected), true);
  await view(page, 'pending');
  await row(page, 'Find Your Pace').getByRole('button', {name: 'Cancel download request'}).click();
  await page.waitForFunction(() => document.querySelector('#feedback').textContent.includes('Download request cancelled'));
  assert.equal(await page.evaluate(() => document.activeElement.dataset.filter), 'pending');
  assert.equal(state.data.tracks[1].desired, false);
});

test('association confirmation and rescan remain available', async t => {
  const data = fixture(); data.association.confirmed = false;
  const {page, state} = await client(t, data);
  await page.getByRole('button', {name: 'Confirm watch connection'}).click();
  await page.getByText('Watch connection confirmed. Start another sync to apply removal requests.', {exact: true}).waitFor();
  assert.deepEqual(state.requests[0].body, {server_id: 'fixture-server', device_epoch: 'fixture-watch'});
  await page.getByRole('button', {name: 'Rescan PC music'}).click();
  await page.getByText('PC music rescanned.', {exact: true}).waitFor();
  assert.equal(state.requests[1].url, base + '/api/local/rescan');
});

test('a changed preceding row does not steal focus from another pending action', async t => {
  const {page, state} = await client(t);
  await view(page, 'pending');
  await row(page, 'The Long Way').getByRole('button', {name: 'Cancel download request'}).focus();
  await page.evaluate(() => {window.focusedBefore = document.activeElement;});
  state.data.tracks[1].desired = false; state.data.tracks[1].pending_download = false;
  await page.clock.runFor(5100);
  await page.waitForFunction(() => document.querySelectorAll('#library-body tr').length === 2);
  assert.equal(await page.evaluate(() => document.activeElement === window.focusedBefore), true);
});

test('stale overlapping poll cannot restore old desired state after saving', async t => {
  const {page, state} = await client(t);
  let release;
  state.holdRead = new Promise(resolve => {release = resolve;});
  await page.clock.runFor(5100);
  await page.waitForTimeout(50);
  const reads = state.reads;
  await row(page, 'Open Road').getByRole('button', {name: 'Download to watch', exact: true}).click();
  // The browser must finish the existing read before sending this mutation.
  assert.equal(state.requests.length, 0);
  state.holdRead = null; release();
  await page.getByText('Download requested. Start Sync on your watch.', {exact: true}).waitFor();
  await row(page, 'Open Road').getByRole('button', {name: 'Cancel download request'}).waitFor();
  assert.ok(state.reads > reads);
});

test('retry during a save cannot replace the saved choice with a stale snapshot', async t => {
  const {page, state} = await client(t);
  state.offline = true;
  await page.clock.runFor(5100);
  await page.waitForFunction(() => !document.querySelector('#retry').hidden);
  state.offline = false;
  let releaseMutation, releaseRead;
  state.holdMutation = new Promise(resolve => {releaseMutation = resolve;});
  state.holdRead = new Promise(resolve => {releaseRead = resolve;});
  await row(page, 'Open Road').getByRole('button', {name: 'Download to watch', exact: true}).click();
  await page.getByRole('button', {name: 'Retry connection'}).click();
  await page.waitForTimeout(50);
  releaseMutation();
  await page.getByText('Download requested. Start Sync on your watch.', {exact: true}).waitFor();
  state.holdRead = null; releaseRead();
  await row(page, 'Open Road').getByRole('button', {name: 'Cancel download request'}).waitFor();
  assert.equal(state.data.tracks[4].desired, true);
});

test('mobile and zoom-sized layouts avoid overflow with long filenames', async t => {
  const data = fixture(); data.tracks[0].filename = 'VeryLongFilename'.repeat(30) + '.mp3';
  const {page} = await client(t, data);
  for (const width of [390, 320, 768]) {
    await page.setViewportSize({width, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
  }
});

test('real FastAPI serves assets and accepts browser choices with CSRF protection', async t => {
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'garmin-ui-'));
  const music = path.join(temp, 'music');
  await fs.mkdir(music);
  await fs.copyFile(path.join(__dirname, 'fixtures/tone-440hz.mp3'), path.join(music, 'Browser fixture.mp3'));
  const python = process.env.UI_PYTHON || path.join(__dirname, '../.venv/bin/python');
  const child = spawn(python, ['-c',
    'from pathlib import Path; import sys, uvicorn; from garmin_sync.admin import create_admin_app; from garmin_sync.config import Settings; uvicorn.run(create_admin_app(Settings(music_root=Path(sys.argv[1]), data_dir=Path(sys.argv[2]))), host="127.0.0.1", port=0, access_log=False)',
    music, path.join(temp, 'data')], {cwd: path.join(__dirname, '..')});
  const page = await browser.newPage();
  t.after(async () => {
    await page.close();
    if (child.exitCode === null) {
      const exited = new Promise(resolve => child.once('exit', resolve));
      child.kill(); await exited;
    }
    await fs.rm(temp, {recursive: true, force: true});
  });
  const url = await new Promise((resolve, reject) => {
    let log = '';
    const timeout = setTimeout(() => reject(new Error('FastAPI startup timed out')), 10000);
    child.once('error', error => {clearTimeout(timeout); reject(error);});
    child.once('exit', code => {clearTimeout(timeout); reject(new Error('FastAPI exited: ' + code));});
    child.stderr.on('data', chunk => {
      log += chunk;
      const match = log.match(/http:\/\/127\.0\.0\.1:\d+/);
      if (match) {clearTimeout(timeout); resolve(match[0]);}
    });
  });
  await page.goto(url);
  await page.getByRole('button', {name: 'Download to watch', exact: true}).click();
  await page.getByText('Download requested. Start Sync on your watch.', {exact: true}).waitFor();
  await page.getByRole('button', {name: 'Cancel download request'}).waitFor();
  const status = await page.evaluate(() => fetch('/api/local/status').then(r => r.json()));
  assert.equal(status.tracks[0].desired, true);
  assert.equal(status.tracks[0].observed, null);
  assert.equal(status.inventory, null);
  const denied = await page.evaluate(async id => (await fetch('/api/local/desired/' + id,
    {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({present: false})})).status,
    status.tracks[0].track_id);
  assert.equal(denied, 403);
  await page.getByRole('button', {name: 'Rescan PC music'}).click();
  await page.getByText('PC music rescanned.', {exact: true}).waitFor();
});

test('capture fixture-only desktop and mobile screenshots', {skip: !process.env.UI_SCREENSHOTS}, async t => {
  const {page} = await client(t);
  await fs.mkdir(process.env.UI_SCREENSHOTS, {recursive: true});
  await page.screenshot({path: path.join(process.env.UI_SCREENSHOTS, 'library-desktop.png'), fullPage: true});
  await page.setViewportSize({width: 390, height: 844});
  await page.screenshot({path: path.join(process.env.UI_SCREENSHOTS, 'library-mobile.png'), fullPage: true});
});
