/* Isolated browser regressions for student retries and genuine digital ink.
 * Never uses the live classroom database, model, accounts, or port 8001.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const puppeteer = require('../../backend/node_modules/puppeteer');
const root = path.resolve(__dirname, '..');
const base = 'http://127.0.0.1:8021';
const artifact = path.join(root, 'artifacts', 'student-retry-runs', String(Date.now()));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const click = async (page, selector) => {
  await page.waitForSelector(selector, { visible: true });
  await page.$eval(selector, element => element.scrollIntoView({ block: 'center', inline: 'center' }));
  await page.click(selector);
};
const api = (page, endpoint, method = 'GET', body) => page.evaluate(async ({ endpoint, method, body }) => {
  const session = await (await fetch('/api/session')).json();
  const response = await fetch('/api' + endpoint, { method,
    headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': session.csrf_token || '' },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const value = await response.json();
  if (!response.ok) throw Error(`${endpoint}: ${response.status}: ${JSON.stringify(value)}`);
  return value;
}, { endpoint, method, body });
const attemptID = page => page.evaluate(() => location.hash.split('/')[1]);
const blankCanvas = page => page.$eval('#answer-pad', canvas => {
  const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
  return !data.some((value, index) => index % 4 === 3 && value > 0);
});
async function boxFor(page, selector) {
  await page.$eval(selector, element => element.scrollIntoView({ block: 'center' }));
  return (await page.$(selector)).boundingBox();
}
async function mouseStroke(page, selector) {
  const box = await boxFor(page, selector);
  await page.mouse.move(box.x + box.width * .25, box.y + box.height * .2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * .6, box.y + box.height * .5, { steps: 8 });
  await page.mouse.move(box.x + box.width * .3, box.y + box.height * .8, { steps: 8 });
  await page.mouse.up();
}
async function main() {
  try { await fetch(base + '/api/health'); throw Error('Port 8021 is already occupied; no existing server will be stopped.'); }
  catch (error) { if (error.message.includes('occupied')) throw error; }
  fs.mkdirSync(artifact, { recursive: true });
  const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
  const server = spawn(python, ['run.py', '--port', '8021'], { cwd: root, windowsHide: true,
    env: { ...process.env, PYTHONUNBUFFERED: '1', AG_DATA_DIR: path.join(artifact, 'data'),
      AG_BOOTSTRAP_TOKEN: 'isolated-retry-test-only', AG_SECURE_COOKIES: '0', OCR_MODEL_PATH: path.join(artifact, 'no-model') } });
  const log = fs.createWriteStream(path.join(artifact, 'server.log'));
  server.stdout.pipe(log); server.stderr.pipe(log);
  let browser;
  try {
    for (let count = 0; count < 100; count += 1) {
      try { if ((await fetch(base + '/api/health')).ok) break; } catch { /* Starting. */ }
      await pause(150);
    }
    browser = await puppeteer.launch({ headless: true, args: ['--no-sandbox'] });
    const errors = [];
    const teacher = await (await browser.createBrowserContext()).newPage();
    teacher.on('pageerror', error => errors.push(error.message));
    await teacher.goto(base, { waitUntil: 'networkidle0' });
    const session = await api(teacher, '/bootstrap', 'POST', { token: 'isolated-retry-test-only', name: 'Retry Teacher', username: 'retry.teacher', password: 'Isolated-password-123' });
    const worksheet = await api(teacher, '/samples/import', 'POST', { filename: '48544102.pdf' });
    const published = await api(teacher, '/worksheets/' + worksheet.id, 'PUT', { title: worksheet.title, questions: worksheet.questions, revision: worksheet.revision, published: true, keys_confirmed: true });
    const pupil = await (await browser.createBrowserContext()).newPage();
    pupil.on('pageerror', error => errors.push(error.message));
    await pupil.setViewport({ width: 1440, height: 1000, hasTouch: true });
    await pupil.goto(base, { waitUntil: 'networkidle0' });
    await api(pupil, '/register', 'POST', { name: 'Retry Student', username: 'retry.student', password: 'Isolated-password-123', class_code: session.user.class_code });
    await pupil.reload({ waitUntil: 'networkidle0' });
    await click(pupil, '[data-action=start-worksheet]');
    await pupil.waitForSelector('#answer-pad');
    const firstID = await attemptID(pupil);
    assert(await blankCanvas(pupil), 'Fresh pad must have no drawn pixels. CSS paper lines are not ink.');
    assert((await pupil.$eval('#ink-evidence', e => e.textContent)).includes('no pen strokes'));
    const firstPad = await boxFor(pupil, '#answer-pad');
    await pupil.mouse.click(firstPad.x + firstPad.width / 2, firstPad.y + firstPad.height / 2);
    assert(await blankCanvas(pupil), 'The initial pad-focus tap must not create a default dot.');
    await pupil.evaluate(() => window.scrollTo(0, 0));
    await pupil.screenshot({ path: path.join(artifact, '00-clean-answer-pad.png'), fullPage: true });
    for (const id of ['add-2', 'add-3', 'add-2']) {
      const box = await boxFor(pupil, `[data-ink-id="${id}"]`);
      await pupil.mouse.click(box.x + box.width / 2, box.y + box.height / 2);
      assert(await blankCanvas(pupil), 'Selecting an on-page answer must not make a phantom dot in its pad.');
    }
    await click(pupil, '[data-action=select-question][data-id="add-3"]');
    await mouseStroke(pupil, '[data-ink-id="add-2"]');
    await pupil.waitForFunction(async id => (await (await fetch('/api/attempts/' + id)).json()).answers['add-2']?.strokes.length === 1, {}, firstID);
    let first = await api(pupil, '/attempts/' + firstID);
    assert.deepEqual(Object.keys(first.answers), ['add-2'], 'Selection taps must not count as answers or dirty saves.');
    assert(first.answers['add-2'].strokes[0].points.length > 10, 'The initial real drag must not lose its first stroke.');
    assert(!await blankCanvas(pupil), 'The saved worksheet stroke must appear in its ruled pad.');
    await click(pupil, '[data-action=select-question][data-id="add-1"]');
    await mouseStroke(pupil, '#answer-pad');
    const pad = await boxFor(pupil, '#answer-pad');
    await pupil.mouse.click(pad.x + pad.width * .75, pad.y + pad.height * .85);
    await pupil.waitForFunction(async id => (await (await fetch('/api/attempts/' + id)).json()).answers['add-1']?.strokes.length === 2, {}, firstID);
    first = await api(pupil, '/attempts/' + firstID);
    assert.equal(first.answers['add-1'].strokes[1].points.length, 1, 'Intentional decimal point must be retained.');
    await click(pupil, '[data-action=select-question][data-id="add-4"]');
    const penBox = await boxFor(pupil, '#answer-pad');
    const cdp = await pupil.createCDPSession();
    for (const [type, x, y, buttons] of [['mouseMoved', .2, .2, 0], ['mousePressed', .2, .2, 1], ['mouseMoved', .7, .8, 1], ['mouseReleased', .7, .8, 0]]) {
      await cdp.send('Input.dispatchMouseEvent', { type, x: penBox.x + penBox.width * x, y: penBox.y + penBox.height * y,
        button: buttons || type === 'mouseReleased' ? 'left' : 'none', buttons, clickCount: type === 'mousePressed' ? 1 : 0, pointerType: 'pen', force: .75 });
    }
    await pupil.waitForFunction(async id => (await (await fetch('/api/attempts/' + id)).json()).answers['add-4']?.strokes.length === 1, {}, firstID);
    first = await api(pupil, '/attempts/' + firstID);
    assert(first.answers['add-4'].strokes[0].points.some(point => point.p === .75));
    await pupil.screenshot({ path: path.join(artifact, '01-captured-ink.png'), fullPage: true });
    await click(pupil, '[data-action=submit-attempt]');
    await click(pupil, 'dialog[open] [data-action=confirm-dialog]');
    await pupil.waitForSelector('[data-action=retry-attempt]');
    first = await api(pupil, '/attempts/' + firstID);
    assert.equal(first.status, 'review');
    assert.equal(first.summary.pending, 3);
    const originalEvidence = JSON.stringify({ answers: first.answers, results: first.results, summary: first.summary });
    await click(pupil, '[data-action=retry-attempt]');
    await click(pupil, 'dialog[open] [data-action=close-dialog]');
    assert.equal((await api(pupil, '/attempts')).attempts.length, 1, 'Cancelling a retry must not create an attempt.');
    await click(pupil, '[data-action=retry-attempt]');
    await click(pupil, 'dialog[open] [data-action=confirm-dialog]');
    await pupil.waitForFunction(id => location.hash !== '#attempt/' + id, {}, firstID);
    const secondID = await attemptID(pupil);
    await pupil.waitForSelector('#answer-pad');
    const second = await api(pupil, '/attempts/' + secondID);
    assert.equal(second.attempt_number, 2);
    assert.deepEqual(second.answers, {});
    assert(await blankCanvas(pupil), 'A retry starts blank, without copying old dots or old answers.');
    first = await api(pupil, '/attempts/' + firstID);
    assert.equal(JSON.stringify({ answers: first.answers, results: first.results, summary: first.summary }), originalEvidence);
    await click(pupil, '[data-action=library]');
    await pupil.waitForSelector('.worksheet-card');
    assert.equal(await pupil.$$eval('.worksheet-card', elements => elements.length), 1);
    assert((await pupil.$eval('[data-action=start-worksheet]', e => e.textContent)).includes('Keep going'));
    await click(pupil, '[data-action=start-worksheet]');
    await pupil.waitForFunction(id => location.hash === '#attempt/' + id, {}, secondID);
    assert.equal(await attemptID(pupil), secondID, 'Library must resume the latest try, not old review work.');
    const answers = ['3', '7', '11', '5', '13', '8', '4', '10', '6', '14', '9', '12', '7', '14', '5', '11'];
    for (let index = 0; index < answers.length; index += 1) {
      await click(pupil, `[data-action=select-question][data-id="add-${index + 1}"]`);
      await pupil.waitForFunction(id => document.querySelector('.question-chip.active')?.dataset.id === id, {}, `add-${index + 1}`);
      await click(pupil, '[data-action=mode-type]');
      await pupil.type('#typed-answer', answers[index]);
    }
    await click(pupil, '[data-action=submit-attempt]');
    await click(pupil, 'dialog[open] [data-action=confirm-dialog]');
    await pupil.waitForSelector('[data-action=retry-attempt]');
    const graded = await api(pupil, '/attempts/' + secondID);
    assert.equal(graded.status, 'graded');
    assert.equal(graded.summary.earned, 16);
    await click(pupil, '[data-action=results]');
    await pupil.waitForSelector('tbody tr');
    assert.equal(await pupil.$$eval('tbody tr', elements => elements.length), 2);
    assert((await pupil.$eval('tbody', e => e.textContent)).includes('Attempt 1'));
    assert((await pupil.$eval('tbody', e => e.textContent)).includes('Attempt 2'));
    await pupil.screenshot({ path: path.join(artifact, '02-preserved-history.png'), fullPage: true });
    await click(pupil, `[data-action=open-attempt][data-id="${firstID}"]`);
    await pupil.waitForSelector('[data-action=open-latest-attempt]');
    assert.equal(await pupil.$('[data-action=retry-attempt]'), null, 'Older history should link to the latest try.');
    await click(pupil, '[data-action=open-latest-attempt]');
    await pupil.waitForSelector('[data-action=retry-attempt]');
    assert.equal(await attemptID(pupil), secondID);
    await teacher.goto(base + '/#attempt/' + firstID, { waitUntil: 'networkidle0' });
    assert.equal(await teacher.$('[data-action=reopen-attempt]'), null, 'Teacher must not reopen older history over a newer try.');
    await api(teacher, '/worksheets/' + worksheet.id, 'PUT', { title: published.title, questions: published.questions, revision: published.revision, published: false, keys_confirmed: true });
    await pupil.reload({ waitUntil: 'networkidle0' });
    assert(await pupil.$eval('[data-action=retry-attempt]', button => button.disabled), 'Withdrawn worksheet must not permit a fresh retry.');
    assert.deepEqual(errors, []);
    const report = { passed: true, checks: ['empty canvas and first focus tap have no ink pixels', 'repeated field selection creates no phantom dots', 'first mouse drag retained', 'deliberate decimal dots retained', 'stylus pressure retained', 'missing-model review is provisional', 'cancel retry is no-op', 'retry starts blank', 'previous review evidence preserved', 'library resumes latest attempt', 'typed retry scores 16/16', 'numbered history preserved', 'older attempts link to latest', 'teacher cannot reopen older try', 'withdrawn worksheet disables retry'], artifact };
    fs.writeFileSync(path.join(artifact, 'result.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } finally {
    if (browser) await browser.close();
    if (process.platform === 'win32') spawnSync('taskkill', ['/PID', String(server.pid), '/T', '/F'], { windowsHide: true, stdio: 'ignore' });
    else server.kill('SIGTERM');
    log.end();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
