/* Isolated browser checks for printed-worksheet uploads and GeniusBees branding.
 * Starts its own server on port 8025 with a private test database and no
 * handwriting model, so written answers deterministically wait for review.
 * Never point this script at a real classroom.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');
const puppeteer = require('../../backend/node_modules/puppeteer');

const root = path.resolve(__dirname, '..');
const base = 'http://127.0.0.1:8025';
const artifact = path.join(root, 'artifacts', 'paper-upload-runs', String(Date.now()));
const python = path.join(root, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
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
const imageLoaded = (page, selector) => page.$eval(selector, image => image.complete && image.naturalWidth > 0);
const waitForMarking = (page, id) => page.waitForFunction(async attemptId => {
  const attempt = await (await fetch('/api/attempts/' + attemptId)).json();
  return ['review', 'graded'].includes(attempt.status);
}, { timeout: 120000 }, id);

function makePhotos() {
  // Realistic synthetic phone photos of the original sample page with handwriting.
  const script = [
    'import sys',
    "sys.path.insert(0, '.'); sys.path.insert(0, 'tests')",
    'from pathlib import Path',
    'from tempfile import TemporaryDirectory',
    'from test_paper import render_sample, write_answer, photograph',
    'out = Path(sys.argv[1])',
    "with TemporaryDirectory(prefix='.paper-tests-', dir='.') as folder:",
    "    page, questions = render_sample('35879581.pdf', folder)",
    "student = page.copy()",
    "for question in questions[:3]: write_answer(student, question['rect'], question['expected'][0])",
    "(out / 'student-paper.jpg').write_bytes(photograph(student, seed=11))",
    "teacher = page.copy()",
    "for question in questions[:5]: write_answer(teacher, question['rect'], question['expected'][0])",
    "(out / 'teacher-scan.jpg').write_bytes(photograph(teacher, seed=12))",
  ].join('\n');
  const result = spawnSync(python, ['-c', script, artifact], { cwd: root, encoding: 'utf8', windowsHide: true });
  if (result.status !== 0) throw Error('Could not create test photos: ' + result.stderr);
}

async function main() {
  try { await fetch(base + '/api/health'); throw Error('Port 8025 is already occupied; no existing server will be stopped.'); }
  catch (error) { if (error.message.includes('occupied')) throw error; }
  fs.mkdirSync(artifact, { recursive: true });
  makePhotos();
  const server = spawn(python, ['run.py', '--port', '8025'], { cwd: root, windowsHide: true,
    env: { ...process.env, PYTHONUNBUFFERED: '1', AG_DATA_DIR: path.join(artifact, 'data'),
      AG_BOOTSTRAP_TOKEN: 'isolated-paper-test-only', AG_SECURE_COOKIES: '0', OCR_MODEL_PATH: path.join(artifact, 'no-model') } });
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
    teacher.on('pageerror', error => errors.push('teacher: ' + error.message));
    await teacher.setViewport({ width: 1440, height: 1000 });
    await teacher.goto(base, { waitUntil: 'networkidle0' });
    assert(await imageLoaded(teacher, '.brand-logo'), 'The GeniusBees logo must load in the header.');
    assert.equal(await teacher.$eval('link[rel=icon]', link => link.getAttribute('href')), '/static/brand/gb-favicon.jpg');
    const favicon = await teacher.evaluate(async () => (await fetch('/static/brand/gb-favicon.jpg')).status);
    assert.equal(favicon, 200);
    await teacher.screenshot({ path: path.join(artifact, '00-branded-sign-in.png') });
    const session = await api(teacher, '/bootstrap', 'POST', { token: 'isolated-paper-test-only', name: 'Paper Teacher', username: 'paper.teacher', password: 'Isolated-password-123' });
    const imported = await api(teacher, '/samples/import', 'POST', { filename: '35879581.pdf' });
    await api(teacher, '/worksheets/' + imported.id, 'PUT', { title: imported.title, questions: imported.questions, revision: imported.revision, published: true, keys_confirmed: true });

    const pupil = await (await browser.createBrowserContext()).newPage();
    pupil.on('pageerror', error => errors.push('student: ' + error.message));
    await pupil.setViewport({ width: 1180, height: 900, hasTouch: true });
    await pupil.goto(base, { waitUntil: 'networkidle0' });
    await api(pupil, '/register', 'POST', { name: 'Paper Student', username: 'paper.student', password: 'Isolated-password-123', class_code: session.user.class_code });
    await pupil.reload({ waitUntil: 'networkidle0' });
    await click(pupil, '[data-action=start-worksheet]');
    await pupil.waitForSelector('[data-action=paper-upload]');
    const firstID = await pupil.evaluate(() => location.hash.split('/')[1]);
    await click(pupil, '[data-action=paper-upload]');
    await pupil.waitForSelector('#paper-form #paper-files');
    await pupil.screenshot({ path: path.join(artifact, '01-student-upload-dialog.png') });
    await (await pupil.$('#paper-files')).uploadFile(path.join(artifact, 'student-paper.jpg'));
    await click(pupil, '#paper-form [type=submit]');
    await waitForMarking(pupil, firstID);
    await pupil.waitForSelector('.score-hero', { timeout: 30000 });
    const marked = await api(pupil, '/attempts/' + firstID);
    assert.equal(marked.submission_mode, 'paper');
    assert.equal(marked.summary.pending, 3, 'Written answers wait for review when no handwriting model is installed.');
    assert.equal(marked.summary.earned, 0);
    assert.equal(marked.results.filter(result => result.source === 'blank').length, 17, 'Unanswered printed boxes receive zero.');
    assert((await pupil.$eval('#sheet-page img', image => image.getAttribute('src'))).includes('/paper/pages/0.png'));
    assert(await imageLoaded(pupil, '#sheet-page img'), 'The aligned paper page must display.');
    await click(pupil, '[data-action=select-question][data-id="subtract-1"]');
    await pupil.waitForSelector('.paper-pad img');
    await pupil.waitForFunction(() => [...document.querySelectorAll('.paper-pad img, .isolated-ink img')].every(image => image.complete && image.naturalWidth > 0), { timeout: 15000 });
    assert.equal(await pupil.$('[data-action=paper-upload]'), null, 'A handed-in attempt cannot upload again.');
    await pupil.screenshot({ path: path.join(artifact, '02-student-marked-paper.png'), fullPage: true });

    await teacher.reload({ waitUntil: 'networkidle0' });
    await click(teacher, '[data-action=results]');
    await click(teacher, '[data-action=teacher-paper-upload]');
    await teacher.waitForSelector('#teacher-paper-form #teacher-paper-files');
    const studentOption = await teacher.$eval('#paper-student option', option => option.textContent);
    assert(studentOption.includes('paper.student'));
    await (await teacher.$('#teacher-paper-files')).uploadFile(path.join(artifact, 'teacher-scan.jpg'));
    await teacher.screenshot({ path: path.join(artifact, '03-teacher-upload-dialog.png') });
    await click(teacher, '#teacher-paper-form [type=submit]');
    await teacher.waitForFunction(id => location.hash.startsWith('#attempt/') && !location.hash.endsWith(id), { timeout: 60000 }, firstID);
    const secondID = await teacher.evaluate(() => location.hash.split('/')[1]);
    await waitForMarking(teacher, secondID);
    const second = await api(teacher, '/attempts/' + secondID);
    assert.equal(second.attempt_number, 2);
    assert.equal(second.previous_attempt_id, firstID);
    assert.equal(second.paper.uploaded_by_role, 'teacher');
    assert.equal(second.summary.pending, 5);
    await teacher.waitForSelector('#review-form', { timeout: 30000 }).catch(async () => {
      await click(teacher, '[data-action=select-question][data-id="subtract-1"]');
      await teacher.waitForSelector('#review-form');
    });
    await teacher.screenshot({ path: path.join(artifact, '04-teacher-paper-review.png'), fullPage: true });
    const csv = await teacher.evaluate(async () => (await fetch('/api/results.csv')).text());
    assert.equal((csv.match(/Paper upload/g) || []).length, 2);
    assert.deepEqual(errors, [], 'Browser JavaScript errors');
    const report = { passed: true, checks: ['GeniusBees logo and favicon', 'student paper upload dialog', 'photo aligned and marked in background', 'unanswered printed boxes zero', 'written answers pending without a model', 'aligned paper page displayed', 'answer crop and isolated writing displayed', 'handed-in attempt cannot re-upload', 'teacher upload for a student', 'numbered teacher attempt linked to history', 'CSV identifies paper uploads'], artifact };
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
