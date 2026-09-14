import { InkCanvas } from './ink.js';
import { captureRequestIdentity, isCurrentRequestIdentity } from './session.js';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const escapeHTML = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
const E = escapeHTML;
const clone = (value) => JSON.parse(JSON.stringify(value));
const uid = () => `q_${Array.from(crypto.getRandomValues(new Uint8Array(12)), (byte) => byte.toString(16).padStart(2, '0')).join('')}`;
const clamp = (value, low = 0, high = 1) => Math.min(high, Math.max(low, value));
const number = (value) => Number.isFinite(Number(value)) ? Number(value) : 0;
const fmt = (value) => Number.isFinite(Number(value)) ? Number(value).toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—';
const PAGE = $('#app');
const dialog = $('#dialog');

const paths = {
  book: '<path d="M4 4h6c1 0 2 1 2 2v14c0-2-2-3-4-3H3V4h1Zm16 0h-6c-1 0-2 1-2 2v14c0-2 2-3 4-3h5V4h-1Z"/>',
  pen: '<path d="m15 4 5 5M4 20l5-1L20 8a2 2 0 0 0-5-5L4 14l-1 7 1-1Z"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  back: '<path d="M19 12H5m5-5-5 5 5 5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  upload: '<path d="M12 15V3m-4 4 4-4 4 4M4 15v5h16v-5"/>',
  download: '<path d="M12 3v12m-4-4 4 4 4-4M4 17v4h16v-4"/>',
  lock: '<rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 5v2"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10v1"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  copy: '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M15 8V3H3v13h5"/>',
  save: '<path d="M5 3h12l4 4v14H3V3h2Z"/><path d="M7 3v6h10V3M7 21v-8h10v8"/>',
  undo: '<path d="M4 10h10a6 6 0 0 1 0 12M9 5l-5 5 5 5"/>',
  eraser: '<path d="m15 3 7 7-12 12H5l-5-5L15 3Zm-8 8 7 7M9 22h13"/>',
  trash: '<path d="M3 6h18M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7"/>',
  review: '<path d="M9 3h11v18H4V8m0 0 5-5v5H4Zm4 5h8m-8 4h6"/>',
  logout: '<path d="M9 3H3v18h6m5-14 5 5-5 5m-6-5h11"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
};
const icon = (name) => `<span class="icon" aria-hidden="true"><svg viewBox="0 0 24 24">${paths[name] || paths.book}</svg></span>`;
const button = (action, label, kind = 'secondary', extra = '') => `<button class="btn ${kind}" data-action="${action}" ${extra}>${label}</button>`;
const tag = (label, color = '') => `<span class="tag ${color}">${E(label)}</span>`;
const questionLabel = (question, index) => /^\s*\d+[.)]\s/.test(question.label) ? question.label : `${index + 1}. ${question.label}`;

const state = {
  user: null, csrf: '', health: null, view: 'auth', authMode: 'login', worksheets: [], attempts: [],
  worksheet: null, attempt: null, page: 0, selected: null, editorDirty: false, keysConfirmed: false,
  drawMode: false, ink: new Map(), pad: null, finger: false, tool: 'pen', mode: 'ink',
  dirtyGeneration: 0, savedGeneration: 0, savePromise: null, saveTimer: null, localTimer: null,
  conflict: false, saveError: '', pollTimer: null, importTab: 'samples', navToken: 0,
  inkHistory: new Map(), submitting: false, retrying: false, activeInkSurface: null, authGeneration: 0,
};

class APIError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

async function api(path, { method = 'GET', body, signal } = {}) {
  const identity = captureRequestIdentity(state, path);
  const headers = { Accept: 'application/json' };
  if (body && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
  if (!['GET', 'HEAD'].includes(method)) headers['X-CSRF-Token'] = state.csrf;
  let response;
  try {
    response = await fetch(`/api${path}`, { method, headers, credentials: 'same-origin', body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body), signal });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new APIError('Connection lost. Your unsent handwriting is kept on this device. Try again when connected.', 0);
  }
  const result = await response.json().catch(() => ({}));
  if (!isCurrentRequestIdentity(identity, state)) throw new APIError('Your sign-in changed while this request was loading. The earlier response was ignored.', 419);
  if (!response.ok) {
    let detail = result.detail || `The request could not be completed (${response.status}).`;
    if (Array.isArray(detail)) detail = detail.map((item) => `${(item.loc || []).filter((part) => part !== 'body').join('.')}: ${item.msg}`).join('; ');
    if (typeof detail !== 'string') detail = 'The server could not accept this request.';
    if (response.status === 401 && state.user && !['/login', '/register', '/bootstrap'].includes(path)) expireSession('Your session has ended. Sign in again to recover your saved draft.');
    throw new APIError(detail, response.status);
  }
  return result;
}

const sessionChannel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('geniusbees-classroom-session') : null;
function announceSession() {
  const message = { user: state.user?.id || null, stamp: Date.now(), nonce: Math.random() };
  sessionChannel?.postMessage(message);
  try { localStorage.setItem('geniusbees:session-change', JSON.stringify(message)); } catch { /* BroadcastChannel still covers compatible browsers. */ }
}
function expireSession(message, preserveDraft = true) {
  state.authGeneration += 1;
  state.navToken += 1;
  if (preserveDraft) persistLocal();
  clearTimeout(state.saveTimer);
  clearTimeout(state.localTimer);
  clearTimeout(state.pollTimer);
  closeDialog();
  state.user = null;
  state.csrf = '';
  state.attempt = null;
  state.worksheet = null;
  state.saveError = '';
  state.conflict = false;
  state.dirtyGeneration = 0;
  state.savedGeneration = 0;
  state.submitting = false;
  state.retrying = false;
  state.editorDirty = false;
  authPage('login');
  toast(message, true);
}
function sessionChanged(message) {
  if (state.user && message.user !== state.user.id) {
    if (!message.user) clearAccountDrafts();
    expireSession(message.user ? 'The account changed in another tab. Sign in to continue. Your unsent work is kept under your original account.' : 'You signed out in another tab. This account’s local recovery drafts have been cleared.', !!message.user);
  } else if (state.user) checkSession();
}
if (sessionChannel) sessionChannel.onmessage = (event) => sessionChanged(event.data || {});
window.addEventListener('storage', (event) => {
  if (event.key !== 'geniusbees:session-change' || !event.newValue) return;
  try { sessionChanged(JSON.parse(event.newValue)); } catch { /* Ignore unrelated malformed browser storage. */ }
});
let checkingSession;
async function checkSession() {
  if (!state.user || checkingSession) return;
  const userID = state.user.id;
  checkingSession = true;
  try {
    const session = await api('/session');
    if (state.user?.id !== userID) return;
    if (session.user?.id !== userID) expireSession('Your sign-in changed or expired. Sign in again to continue your own worksheet.');
    else state.csrf = session.csrf_token;
  } catch { /* Network outages are handled by draft saving. */ }
  finally { checkingSession = false; }
}

let toastTimer;
function toast(message, error = false) {
  const element = $('#toast');
  element.textContent = message;
  element.className = `toast${error ? ' error' : ''}`;
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.hidden = true; }, error ? 8500 : 4000);
}

let dialogResolver;
function closeDialog(value = false) {
  if (dialog.open) dialog.close();
  dialogResolver?.(value);
  dialogResolver = null;
}

function showDialog(title, body, actions = '') {
  closeDialog(false);
  dialog.innerHTML = `<div class="dialog-head"><h2 id="dialog-title">${E(title)}</h2>${button('close-dialog', icon('close'), 'ghost square', 'aria-label="Close dialog"')}</div><div class="dialog-body">${body}</div>${actions ? `<div class="dialog-actions">${actions}</div>` : ''}`;
  dialog.showModal();
}

function confirmDialog(title, message, confirmLabel = 'Continue', dangerous = false) {
  showDialog(title, `<p class="mb0">${E(message)}</p>`, `${button('close-dialog', 'Cancel', 'secondary')}${button('confirm-dialog', E(confirmLabel), dangerous ? 'danger' : 'primary')}`);
  return new Promise((resolve) => { dialogResolver = resolve; });
}

dialog.addEventListener('cancel', (event) => { event.preventDefault(); closeDialog(false); });

function header() {
  const teacher = state.user?.role === 'teacher';
  return `<header class="topbar"><button class="brand" data-action="library" aria-label="GeniusBees classroom home"><img class="brand-logo" src="/static/brand/gb-logo.jpg" alt="GeniusBees" width="1000" height="312"><span class="brand-divider" aria-hidden="true"></span><span class="brand-text"><span class="brand-name">Classroom</span><span class="brand-sub">Worksheets &amp; marking</span></span></button>${state.user ? `<nav class="main-nav" aria-label="Main navigation"><button class="nav-btn ${['library', 'editor', 'attempt'].includes(state.view) ? 'active' : ''}" data-action="library">${teacher ? 'Worksheets' : 'My worksheets'}</button><button class="nav-btn ${state.view === 'results' ? 'active' : ''}" data-action="results">${teacher ? 'Student results' : 'My results'}</button></nav><div class="profile"><span class="avatar" aria-hidden="true">${E(state.user.name.slice(0, 2).toUpperCase())}</span><div class="profile-details"><div class="profile-name">${E(state.user.name)}</div><div class="profile-role">${E(state.user.role)}</div></div>${button('logout', icon('logout') + 'Sign out', 'ghost')}</div>` : '<span class="caption">A little practice. A lot of possibility.</span>'}</header>`;
}

function destroyInk() {
  state.ink.forEach((canvas) => canvas.destroy());
  state.ink.clear();
  state.pad?.destroy();
  state.pad = null;
  state.activeInkSurface = null;
}

function replacePage(content) {
  destroyInk();
  PAGE.innerHTML = header() + content;
}

function setRoute(hash) { history.replaceState(null, '', `${location.pathname}${location.search}${hash ? `#${hash}` : ''}`); }

function authPage(mode = state.authMode) {
  state.view = 'auth';
  state.authMode = mode;
  const setup = mode === 'setup';
  const register = mode === 'register';
  const title = setup ? 'Create your classroom' : register ? 'Join your class' : 'Welcome back';
  replacePage(`<main id="main" class="auth-shell"><section class="auth-copy"><div class="eyebrow">A space to learn & grow</div><h1>Little hands.<br>Big <em>possibilities.</em></h1><p>Write, practise and discover. Your favourite worksheets, ready for a pencil and a curious mind.</p><div class="auth-benefits"><div class="auth-benefit">${icon('pen')} Write naturally with a stylus or Apple Pencil</div><div class="auth-benefit">${icon('review')} Helpful feedback, with a teacher when needed</div><div class="auth-benefit">${icon('lock')} Handwriting stays on your classroom server</div></div></section><section class="auth-card" aria-label="Classroom access"><h2>${title}</h2><p>${setup ? 'Set up the first teacher account using your server setup token.' : register ? 'Your teacher will give you a class code.' : 'A new page of learning is waiting for you.'}</p>${!setup ? `<div class="tabs" role="group" aria-label="Account access"><button data-action="auth-login" class="${register ? '' : 'active'}">Sign in</button><button data-action="auth-register" class="${register ? 'active' : ''}">Join a class</button></div>` : ''}<form id="auth-form">${setup ? '<div class="field"><label for="setup-token">Server setup token</label><input id="setup-token" name="token" type="password" required autocomplete="off"><small>Shown in the server terminal during first setup.</small></div>' : ''}${setup || register ? '<div class="field"><label for="full-name">Your name</label><input id="full-name" name="name" required maxlength="80" autocomplete="name"></div>' : ''}<div class="field"><label for="username">Username</label><input id="username" name="username" required minlength="3" maxlength="50" autocomplete="username" autocapitalize="none" spellcheck="false"></div><div class="field"><label for="password">Password</label><input id="password" name="password" type="password" required ${setup || register ? 'minlength="10"' : ''} maxlength="128" autocomplete="${setup || register ? 'new-password' : 'current-password'}">${setup || register ? '<small>Use at least 10 characters.</small>' : ''}</div>${register ? '<div class="field"><label for="class-code">Class code</label><input id="class-code" name="class_code" required autocomplete="off" autocapitalize="characters" spellcheck="false"></div>' : ''}<p class="form-error" id="auth-error" role="alert" hidden></p><button class="btn primary full" type="submit">${setup ? 'Create teacher account' : register ? 'Join classroom' : 'Sign in'}${icon('arrow')}</button></form><p class="auth-footnote">${setup ? 'The teacher account manages worksheet answers and student marks.' : 'Teachers and students sign in here. Your teacher can help if you need your class details.'}</p>${state.health?.setup_required && !setup ? '<p class="auth-footnote"><button class="link-button" data-action="auth-setup">Set up the first teacher account</button></p>' : ''}${setup ? '<p class="auth-footnote"><button class="link-button" data-action="auth-login">Back to sign in</button></p>' : ''}</section></main>`);
}

async function leaveCurrent() {
  if (state.retrying) { toast('Your new try is being prepared. Please wait a moment.'); return false; }
  if (state.submitting) { toast('Your worksheet is being submitted and marked. Please wait for the result before leaving.'); return false; }
  if (state.view === 'editor' && state.editorDirty && !await confirmDialog('Leave unsaved changes?', 'The answer areas and marking key have not been saved. Stay here to save, or leave and discard these changes.', 'Leave without saving', true)) return false;
  if (state.view === 'attempt' && state.attempt?.status === 'draft' && state.user?.role === 'student') {
    try { await flushAnswers(); } catch (error) {
      if (!await confirmDialog('Your draft is saved on this device', `${error.message} Leaving now keeps a recovery copy in this browser.`, 'Leave worksheet')) return false;
    }
  }
  clearTimeout(state.pollTimer);
  clearTimeout(state.saveTimer);
  return true;
}

function ocrNotice() {
  const ocr = state.health?.ocr;
  const title = ocr?.available ? 'Local handwriting recognition is loaded.' : ocr?.configured ? 'Local handwriting recognition is installed; the first handwritten submission loads the model.' : 'Local handwriting recognition is not ready on this server.';
  return `<div class="notice neutral">${icon('info')}<div>${E(title)} ${E(ocr?.message || '')} Typed answers and choices can be checked immediately. Uncertain handwriting waits for teacher review; this is not an incorrect mark.</div></div>`;
}

async function showLibrary({ skipGuard = false } = {}) {
  if (!state.user) return authPage();
  if (!skipGuard && !await leaveCurrent()) return;
  const token = ++state.navToken;
  const [response, health] = await Promise.all([api('/worksheets'), api('/health')]);
  if (token !== state.navToken) return;
  state.health = health;
  state.worksheets = response.worksheets || [];
  if (response.class_code) state.user.class_code = response.class_code;
  state.view = 'library';
  state.editorDirty = false;
  setRoute('');
  renderLibrary();
}

function renderLibrary() {
  const teacher = state.user.role === 'teacher';
  const worksheets = state.worksheets;
  const published = worksheets.filter((worksheet) => worksheet.published).length;
  const started = worksheets.filter((worksheet) => worksheet.attempt).length;
  const completed = worksheets.filter((worksheet) => worksheet.attempt && worksheet.attempt.status !== 'draft').length;
  replacePage(`<main id="main" class="page-main"><div class="page-heading"><div><div class="eyebrow">${teacher ? 'Your teaching space' : 'Ready, set, discover'}</div><h1>${teacher ? 'Make room for learning.' : `Hello, ${E(state.user.name.split(' ')[0])}.`}</h1><p>${teacher ? 'Bring your worksheets to life. Set the answers, invite your class and see how everyone is doing.' : 'Pick a worksheet, grab your pencil and give it a go. Your progress is saved as you work.'}</p></div>${teacher ? `<div class="class-code"><div><small>YOUR CLASS JOIN CODE</small><strong>${E(state.user.class_code || '—')}</strong></div>${button('copy-code', icon('copy'), 'ghost square', 'aria-label="Copy class code"')}</div>` : ''}</div>${teacher ? ocrNotice() : ''}<div class="stats"><div class="stat"><div class="value">${worksheets.length}</div><div class="label">${teacher ? 'Worksheets in your library' : 'Worksheets to explore'}</div></div><div class="stat"><div class="value">${teacher ? published : started - completed}</div><div class="label">${teacher ? 'Published for students' : 'In progress'}</div></div><div class="stat"><div class="value">${teacher ? worksheets.length - published : completed}</div><div class="label">${teacher ? 'Drafts to prepare' : 'Submitted worksheets'}</div></div></div><div class="section-title"><h2>${teacher ? 'Worksheet library' : 'Your worksheets'}</h2>${teacher ? button('import', icon('plus') + 'Add worksheet', 'primary') : tag('One page at a time', 'green')}</div>${worksheets.length ? `<div class="worksheet-grid">${worksheets.map((worksheet) => {
    const attempt = worksheet.attempt;
    const status = teacher ? tag(worksheet.published ? 'Published' : 'Draft', worksheet.published ? 'green' : 'orange') : attempt ? attemptStatus(attempt.status) : tag('Ready to start', 'blue');
    const pageCount = Array.isArray(worksheet.pages) ? worksheet.pages.length : worksheet.pages || 1;
    return `<article class="worksheet-card"><div class="card-preview">${status}<img src="/api/worksheets/${encodeURIComponent(worksheet.id)}/pages/0.png" alt="" loading="lazy"></div><div class="card-body"><h3>${E(worksheet.title)}</h3><p>${worksheet.question_count || 0} answer ${(worksheet.question_count || 0) === 1 ? 'area' : 'areas'} · ${pageCount} ${pageCount === 1 ? 'page' : 'pages'}</p><div class="card-bottom"><span class="card-meta">${fmt(worksheet.total_points)} marks${teacher ? ` · v${worksheet.revision}` : attempt ? ` · Try ${attempt.attempt_number || 1}` : ''}</span>${button(teacher ? 'open-editor' : 'start-worksheet', `${teacher ? 'Prepare worksheet' : attempt ? attempt.status === 'draft' ? 'Keep going' : 'View feedback' : 'Let’s begin'}${icon('arrow')}`, teacher ? 'secondary' : 'primary', `data-id="${E(worksheet.id)}"`)}</div></div></article>`;
  }).join('')}</div>` : `<section class="empty"><div class="empty-symbol">${icon('book')}</div><h2>${teacher ? 'Your first worksheet starts here' : 'A fresh page is coming soon'}</h2><p>${teacher ? 'Import one of the sample worksheets or upload a PDF from the worksheet generator. Then set up the answer areas and marking key.' : 'Your teacher is preparing worksheets for your class. Come back after they publish one.'}</p>${teacher ? button('import', icon('plus') + 'Add a worksheet', 'primary') : button('library', 'Refresh worksheets', 'secondary')}</section>`}<div class="footer-note">${icon('lock')} ${teacher ? 'Private classroom · Free local recognition · Teacher control over every mark' : 'Write with a stylus or Apple Pencil, type an answer, or print the worksheet and upload a photo of your paper.'}</div></main>`);
}

function attemptStatus(status) {
  const values = { draft: ['In progress', 'blue'], grading: ['Marking', 'orange'], review: ['Teacher review', 'orange'], graded: ['Marked', 'green'] };
  const [label, color] = values[status] || [status || 'Ready', ''];
  return tag(label, color);
}

async function showImport(tab = 'samples') {
  state.importTab = tab;
  const tabs = `<div class="tabs" role="group" aria-label="Import source"><button data-action="import-samples" class="${tab === 'samples' ? 'active' : ''}">Sample worksheets</button><button data-action="import-upload" class="${tab === 'upload' ? 'active' : ''}">Upload a PDF</button></div>`;
  if (tab === 'upload') {
    showDialog('Add a worksheet', `${tabs}<p>Use a PDF exported from your worksheet generator. The original design, header and footer are preserved.</p><form id="upload-form"><div class="field"><label for="upload-title">Worksheet title</label><input id="upload-title" name="title" required maxlength="160" placeholder="e.g. Counting from 1 to 10"></div><div class="field"><label for="upload-file">PDF file</label><input id="upload-file" name="file" type="file" accept="application/pdf,.pdf" required><small>After upload, draw an answer area around each response and add its marking key.</small></div><p class="form-error" id="upload-error" hidden role="alert"></p><button class="btn primary full" type="submit">${icon('upload')}Upload worksheet</button></form>`);
    return;
  }
  showDialog('Add a worksheet', `${tabs}<p class="muted">Loading your sample worksheets…</p>`);
  const { samples = [] } = await api('/samples');
  if (!dialog.open || state.importTab !== 'samples') return;
  $('.dialog-body', dialog).innerHTML = `${tabs}<p>These worksheets include suggested answer areas and keys. Review and confirm each key before publishing.</p><div class="sample-list">${samples.length ? samples.map((sample) => `<div class="sample-row"><span class="sample-symbol">${icon('book')}</span><div class="grow"><h3>${E(sample.title)}</h3><p>${sample.question_count} answer areas${sample.notes ? ` · ${E(Array.isArray(sample.notes) ? sample.notes.join(' ') : sample.notes)}` : ''}</p></div>${button('import-sample', 'Import', 'secondary compact', `data-file="${E(sample.filename)}"`)}</div>`).join('') : '<p>No bundled samples were found. You can upload a PDF instead.</p>'}</div>`;
}

function pageControls() {
  const document = state.view === 'editor' ? state.worksheet : state.attempt;
  const pages = document.pages || [];
  return `<div class="sheet-controls"><div class="row">${button('page-prev', '‹', 'ghost compact', `aria-label="Previous page" ${state.page === 0 ? 'disabled' : ''}`)}<span>Page ${state.page + 1} of ${pages.length}</span>${button('page-next', '›', 'ghost compact', `aria-label="Next page" ${state.page >= pages.length - 1 ? 'disabled' : ''}`)}</div><span class="muted">${state.view === 'editor' ? 'Select an area to edit its marking key' : isPaperAttempt(document) ? 'Uploaded paper copy' : 'Scroll with a finger · Write with your pencil'}</span><a class="btn ghost compact" href="/api/worksheets/${encodeURIComponent(state.view === 'editor' ? document.id : document.worksheet_id)}/pdf" target="_blank" rel="noopener">Print / PDF ${icon('download')}</a></div>`;
}

function positionStyle(rect) { return `left:${rect.x * 100}%;top:${rect.y * 100}%;width:${rect.w * 100}%;height:${rect.h * 100}%`; }

function sheetHTML() {
  const teacher = state.view === 'editor';
  const document = teacher ? state.worksheet : state.attempt;
  const worksheetID = teacher ? document.id : document.worksheet_id;
  const page = document.pages[state.page];
  const paperPage = !teacher && isPaperAttempt(document);
  const background = paperPage ? `/api/attempts/${encodeURIComponent(document.id)}/paper/pages/${state.page}.png` : `/api/worksheets/${encodeURIComponent(worksheetID)}/pages/${state.page}.png`;
  return `${pageControls()}<div class="sheet-surround" id="sheet-scroll"><div class="sheet-page" id="sheet-page" style="aspect-ratio:${page.width}/${page.height}"><img src="${background}" alt="${E(document.title)}, ${paperPage ? 'uploaded paper ' : ''}page ${state.page + 1}" draggable="false"><div class="sheet-overlay ${teacher && state.drawMode ? 'drawing' : ''}" id="sheet-overlay">${regionsHTML()}</div></div></div>`;
}

function regionsHTML() {
  const teacher = state.view === 'editor';
  const doc = teacher ? state.worksheet : state.attempt;
  const editable = !teacher && state.user.role === 'student' && doc.status === 'draft' && !state.conflict && !state.submitting;
  const paperMode = !teacher && isPaperAttempt(doc);
  return (doc.questions || []).filter((question) => question.page === state.page).map((question) => {
    const index = doc.questions.findIndex((item) => item.id === question.id);
    const selected = state.selected === question.id;
    const answer = doc.answers?.[question.id] || {};
    const result = doc.results?.find((item) => item.question_id === question.id);
    let inner = teacher ? `<span class="region-label">${E(questionLabel(question, index))}</span>${selected ? '<span class="resize-handle" data-handle="resize" aria-hidden="true"></span>' : ''}` : `<button class="region-open" data-action="select-question" data-id="${E(question.id)}" aria-label="Open answer ${index + 1}: ${E(question.label)}">${index + 1} ↗</button>${question.kind !== 'choice' && !paperMode ? `<canvas data-ink-id="${E(question.id)}" aria-label="Handwriting for ${E(question.label)}"></canvas><div class="typed-overlay" ${answer.text ? '' : 'hidden'}>${E(answer.text || '')}</div>` : ''}`;
    return `<div class="answer-region ${teacher ? 'teacher' : ''} ${selected ? 'selected' : ''} ${result?.status || ''}" data-region="${E(question.id)}" style="${positionStyle(question.rect)}" ${teacher ? `tabindex="0" role="button" aria-label="Edit ${E(question.label)}"` : ''}>${inner}</div>${!teacher && !paperMode && question.kind === 'choice' ? (question.options || []).filter((option) => option.rect).map((option) => `<button class="choice-hotspot ${answer.text === option.value ? 'chosen' : ''}" style="${positionStyle(option.rect)}" data-action="choose" data-id="${E(question.id)}" data-value="${E(option.value)}" aria-label="${E(question.label)}: ${E(option.label)}" aria-pressed="${answer.text === option.value}" ${editable ? '' : 'disabled'}>${E(option.label)}</button>`).join('') : ''}`;
  }).join('');
}

async function openEditor(id, { skipGuard = false } = {}) {
  if (!skipGuard && !await leaveCurrent()) return;
  const worksheet = await api(`/worksheets/${encodeURIComponent(id)}`);
  state.view = 'editor';
  state.worksheet = worksheet;
  state.page = 0;
  state.selected = worksheet.questions[0]?.id || null;
  state.editorDirty = false;
  state.keysConfirmed = false;
  state.drawMode = false;
  setRoute(`worksheet/${id}`);
  renderEditor();
}

function renderEditor() {
  replacePage(`<main id="main" class="workbench"><div class="workspace-toolbar"><div class="row">${button('library', icon('back'), 'ghost square', 'aria-label="Back to worksheets"')}<div class="workspace-title"><h1>${E(state.worksheet.title)}</h1><small id="editor-status">${state.worksheet.published ? 'Published worksheet' : 'Draft worksheet'} · Revision ${state.worksheet.revision}</small></div></div><div class="row wrap">${button('toggle-draw', icon('plus') + (state.drawMode ? 'Drawing answer area…' : 'Add answer area'), state.drawMode ? 'primary' : 'secondary', `aria-pressed="${state.drawMode}"`)}${button('save-worksheet', icon('save') + 'Save draft', 'secondary')}${button('publish-worksheet', state.worksheet.published ? 'Update & publish' : 'Publish worksheet', 'primary')}</div></div><div class="notice neutral">${icon('info')}<div>Draw a box around each place students should answer. Add accepted answers and marks, then confirm your marking key before publishing. Drawing and tracing are marked by a teacher.</div></div><div class="workspace-layout"><section class="sheet-column" aria-label="Worksheet answer area editor">${sheetHTML()}</section><aside class="side-panel" id="editor-panel" aria-label="Answer area properties">${editorPanelHTML()}</aside></div></main>`);
  bindTeacherGeometry();
}

function currentQuestion() {
  return (state.view === 'editor' ? state.worksheet : state.attempt)?.questions.find((question) => question.id === state.selected);
}

function editorPanelHTML() {
  const worksheet = state.worksheet;
  const question = currentQuestion();
  const total = worksheet.questions.reduce((sum, item) => sum + number(item.points), 0);
  return `<div class="panel-head"><h2>Marking key</h2><p>${worksheet.questions.length} answer areas · ${fmt(total)} marks in total</p></div><div class="panel-body"><div class="field"><label for="worksheet-title">Worksheet title</label><input id="worksheet-title" data-editor="title" value="${E(worksheet.title)}" maxlength="160"></div>${worksheet.notes ? `<div class="key-hint">${E(Array.isArray(worksheet.notes) ? worksheet.notes.join(' ') : worksheet.notes)}</div><div class="panel-separator"></div>` : ''}<div class="question-list" aria-label="Answer areas">${worksheet.questions.map((item, index) => `<button data-action="select-question" data-id="${E(item.id)}" class="${item.id === state.selected ? 'active' : ''}"><span>${E(questionLabel(item, index))}</span><span>${fmt(item.points)} pt</span></button>`).join('')}</div><div class="mb0">${button('add-default-question', 'Add area by coordinates', 'ghost compact')}</div>${question ? `<div class="form-section-label">Answer area ${worksheet.questions.indexOf(question) + 1}</div><div class="field"><label for="question-label">Question / instruction</label><input id="question-label" data-question="label" value="${E(question.label)}" maxlength="240"></div><div class="two-cols"><div class="field"><label for="question-kind">Answer type</label><select id="question-kind" data-question="kind">${[['number', 'Number'], ['text', 'Short text'], ['choice', 'Multiple choice'], ['manual', 'Drawing / teacher review']].map(([value, label]) => `<option value="${value}" ${question.kind === value ? 'selected' : ''}>${label}</option>`).join('')}</select></div><div class="field"><label for="question-points">Marks</label><input id="question-points" data-question="points" type="number" min="0.1" max="100" step="0.1" value="${question.points}"></div></div>${question.kind !== 'manual' ? `<div class="field"><label for="expected">Accepted ${question.kind === 'choice' ? 'option values' : 'answers'}</label><textarea id="expected" data-question="expected" rows="2" placeholder="One accepted answer per line">${E((question.expected || []).join('\n'))}</textarea><small>${question.kind === 'number' ? 'Numerical equality is used. Set a tolerance only when intended.' : 'One accepted answer per line. Answers are matched exactly after normalizing whitespace.'}</small></div>` : '<div class="manual-note">Students can draw, trace or write. This area always waits for a teacher to award marks.</div>'}${question.kind === 'number' ? `<div class="field"><label for="tolerance">Numeric tolerance</label><input id="tolerance" type="number" min="0" max="100" step="any" data-question="tolerance" value="${question.tolerance || 0}"></div>` : ''}${question.kind === 'text' ? `<label class="checkbox field"><input data-question="case_sensitive" type="checkbox" ${question.case_sensitive ? 'checked' : ''}>Match uppercase and lowercase exactly</label>` : ''}${question.kind === 'choice' ? `<div class="field"><label for="options">Choices</label><textarea id="options" data-question="options" rows="4" placeholder="value | label">${E((question.options || []).map((option) => `${option.value} | ${option.label}`).join('\n'))}</textarea><small>One “value | label” per line. Existing on-page choice positions are kept when the value stays the same. New choices appear as buttons in the answer pad.</small></div>` : ''}<details class="mt16"><summary class="small">Answer area position (%)</summary><div class="coord-grid mt16">${[['x', 'Left'], ['y', 'Top'], ['w', 'Width'], ['h', 'Height']].map(([key, label]) => `<div class="field"><label for="rect-${key}">${label}</label><input id="rect-${key}" data-rect="${key}" type="number" min="${['w', 'h'].includes(key) ? '0.5' : '0'}" max="100" step="0.1" value="${(question.rect[key] * 100).toFixed(1)}"></div>`).join('')}</div></details><div class="row mt16">${button('delete-question', icon('trash') + 'Delete area', 'danger compact')}</div>` : `<div class="empty" style="padding:25px 15px"><h3>Add your first answer area</h3><p class="mb0">Choose “Add answer area” and drag a box on the worksheet.</p></div>`}<div class="panel-separator"></div><label class="checkbox"><input id="keys-confirmed" type="checkbox" ${state.keysConfirmed ? 'checked' : ''}><span>I have checked every accepted answer, answer area and mark allocation.</span></label><p class="caption mt16 mb0">Publishing makes this worksheet available to your class. Attempts already started keep the marking key they began with.</p>${worksheet.published ? `<div class="mt16">${button('unpublish', 'Unpublish worksheet', 'ghost compact')}</div>` : ''}</div>`;
}

function refreshEditorPanel() { $('#editor-panel').innerHTML = editorPanelHTML(); }

function markEditorDirty() {
  state.editorDirty = true;
  state.keysConfirmed = false;
  if ($('#keys-confirmed')) $('#keys-confirmed').checked = false;
  $('#editor-status').textContent = `Unsaved changes · Based on revision ${state.worksheet.revision}`;
}

function updateRegionElement(question) {
  const region = $$('[data-region]').find((element) => element.dataset.region === question.id);
  if (region) {
    region.style.cssText = positionStyle(question.rect);
    const label = $('.region-label', region);
    if (label) label.textContent = questionLabel(question, state.worksheet.questions.indexOf(question));
  }
}

function bindTeacherGeometry() {
  const overlay = $('#sheet-overlay');
  let drag = null;
  const point = (event) => {
    const rect = overlay.getBoundingClientRect();
    return { x: clamp((event.clientX - rect.left) / rect.width), y: clamp((event.clientY - rect.top) / rect.height) };
  };
  overlay.addEventListener('pointerdown', (event) => {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    const region = event.target.closest('[data-region]');
    if (!state.drawMode && !region) return;
    event.preventDefault();
    const start = point(event);
    if (state.drawMode) {
      drag = { mode: 'draw', start, pointer: event.pointerId };
      const preview = document.createElement('div');
      preview.className = 'drawing-preview';
      preview.id = 'drawing-preview';
      overlay.append(preview);
    } else {
      const question = state.worksheet.questions.find((item) => item.id === region.dataset.region);
      state.selected = question.id;
      $$('[data-region]').forEach((element) => element.classList.toggle('selected', element.dataset.region === question.id));
      drag = { mode: event.target.dataset.handle === 'resize' ? 'resize' : 'move', start, rect: clone(question.rect), question, pointer: event.pointerId, moved: false };
    }
    overlay.setPointerCapture(event.pointerId);
  });
  overlay.addEventListener('pointermove', (event) => {
    if (!drag || drag.pointer !== event.pointerId) return;
    event.preventDefault();
    const end = point(event);
    if (drag.mode === 'draw') {
      drag.rect = { x: Math.min(drag.start.x, end.x), y: Math.min(drag.start.y, end.y), w: Math.abs(end.x - drag.start.x), h: Math.abs(end.y - drag.start.y) };
      $('#drawing-preview').style.cssText = positionStyle(drag.rect);
    } else {
      const dx = end.x - drag.start.x;
      const dy = end.y - drag.start.y;
      if (Math.abs(dx) + Math.abs(dy) > 0.001) drag.moved = true;
      if (drag.mode === 'move') drag.question.rect = { ...drag.rect, x: clamp(drag.rect.x + dx, 0, 1 - drag.rect.w), y: clamp(drag.rect.y + dy, 0, 1 - drag.rect.h) };
      else drag.question.rect = { ...drag.rect, w: clamp(drag.rect.w + dx, 0.008, 1 - drag.rect.x), h: clamp(drag.rect.h + dy, 0.008, 1 - drag.rect.y) };
      updateRegionElement(drag.question);
    }
  });
  const finish = (event) => {
    if (!drag || drag.pointer !== event.pointerId) return;
    const ended = drag;
    drag = null;
    if (overlay.hasPointerCapture(event.pointerId)) overlay.releasePointerCapture(event.pointerId);
    $('#drawing-preview')?.remove();
    if (ended.mode === 'draw' && ended.rect?.w >= 0.008 && ended.rect?.h >= 0.008) {
      const question = { id: uid(), label: `Question ${state.worksheet.questions.length + 1}`, page: state.page, rect: ended.rect, kind: 'number', expected: [], points: 1, tolerance: 0, case_sensitive: false, options: [] };
      state.worksheet.questions.push(question);
      state.selected = question.id;
      state.drawMode = false;
      markEditorDirty();
      renderEditor();
    } else if (ended.question) {
      if (ended.moved) markEditorDirty();
      overlay.innerHTML = regionsHTML();
      refreshEditorPanel();
    }
  };
  overlay.addEventListener('pointerup', finish);
  overlay.addEventListener('pointercancel', finish);
  overlay.addEventListener('lostpointercapture', finish);
  overlay.addEventListener('keydown', (event) => {
    const region = event.target.closest('[data-region]');
    if (region && ['Enter', ' '].includes(event.key)) { event.preventDefault(); selectQuestion(region.dataset.region); }
    if (region && ['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(event.key)) {
      event.preventDefault();
      const question = state.worksheet.questions.find((item) => item.id === region.dataset.region);
      state.selected = question.id;
      const step = event.shiftKey ? 0.02 : 0.005;
      const dx = event.key === 'ArrowLeft' ? -step : event.key === 'ArrowRight' ? step : 0;
      const dy = event.key === 'ArrowUp' ? -step : event.key === 'ArrowDown' ? step : 0;
      question.rect.x = clamp(question.rect.x + dx, 0, 1 - question.rect.w);
      question.rect.y = clamp(question.rect.y + dy, 0, 1 - question.rect.h);
      updateRegionElement(question);
      markEditorDirty();
      refreshEditorPanel();
    }
  });
}

async function saveWorksheet(publish) {
  const worksheet = state.worksheet;
  if (!worksheet.title.trim()) throw new Error('Add a worksheet title first.');
  if (publish && !state.keysConfirmed) throw new Error('Check the confirmation box after reviewing every marking key and answer area.');
  if (publish && !worksheet.questions.length) throw new Error('Add at least one answer area before publishing.');
  if (publish && !await confirmDialog(worksheet.published ? 'Update this published worksheet?' : 'Ready for your class?', `Publish ${worksheet.questions.length} answer areas worth ${fmt(worksheet.questions.reduce((sum, question) => sum + number(question.points), 0))} marks. Students can begin after you publish. Existing attempts keep their original key.`, 'Publish worksheet')) return;
  try {
    const saved = await api(`/worksheets/${encodeURIComponent(worksheet.id)}`, { method: 'PUT', body: { title: worksheet.title.trim(), questions: worksheet.questions, published: publish, keys_confirmed: publish ? state.keysConfirmed : false, revision: worksheet.revision } });
    state.worksheet = saved;
    state.editorDirty = false;
    state.keysConfirmed = false;
    renderEditor();
    toast(publish ? 'Worksheet published. Your class can now open it.' : 'Worksheet saved as a draft.');
  } catch (error) {
    if (error.status === 409) showDialog('A newer version was saved', '<p>Someone saved this worksheet in another tab. Your changes are still visible here. Download your marking key for reference, then reload the latest version before editing again.</p>', `${button('download-key', 'Download my marking key', 'secondary')}${button('reload-editor', 'Reload latest version', 'primary')}`);
    else throw error;
  }
}

function updateQuestionInput(element) {
  const question = currentQuestion();
  if (!question) return;
  const key = element.dataset.question;
  if (key === 'expected') question.expected = element.value.split('\n').map((value) => value.trim()).filter(Boolean);
  else if (key === 'options') question.options = element.value.split('\n').filter((value) => value.trim()).map((line) => {
    const [rawValue, ...label] = line.split('|');
    const value = rawValue.trim();
    const existing = question.options.find((option) => option.value === value);
    return { value, label: label.join('|').trim() || value, ...(existing?.rect ? { rect: existing.rect } : {}) };
  });
  else if (key === 'case_sensitive') question[key] = element.checked;
  else if (['points', 'tolerance'].includes(key)) question[key] = number(element.value);
  else question[key] = element.value;
  markEditorDirty();
  updateRegionElement(question);
  if (key === 'kind') refreshEditorPanel();
}

const localKey = (attemptID = state.attempt?.id) => `geniusbees:ink:${state.user?.id}:${attemptID}`;
function persistLocal() {
  if (state.user?.role !== 'student' || state.attempt?.status !== 'draft' || state.attempt.student_id && state.attempt.student_id !== state.user.id) return;
  try {
    localStorage.setItem(localKey(), JSON.stringify({ version: state.attempt.version, answers: state.attempt.answers, updated: new Date().toISOString(), unsaved: state.dirtyGeneration > state.savedGeneration }));
  } catch {
    toast('This browser cannot keep a recovery copy. Stay connected and check that your answers are saved before leaving.', true);
  }
}

function forgetLocal(attemptID = state.attempt?.id) { try { localStorage.removeItem(localKey(attemptID)); } catch { /* Storage may be disabled. */ } }

function clearAccountDrafts() {
  try {
    const prefix = `geniusbees:ink:${state.user.id}:`;
    Object.keys(localStorage).filter((key) => key.startsWith(prefix)).forEach((key) => localStorage.removeItem(key));
  } catch { /* A disabled store has no recoverable drafts. */ }
}

async function startWorksheet(id) {
  if (!await leaveCurrent()) return;
  const attempt = await api(`/worksheets/${encodeURIComponent(id)}/attempts`, { method: 'POST', body: {} });
  await openAttempt(attempt.id, { skipGuard: true, attempt });
}

async function retryAttempt() {
  const previous = state.attempt;
  const userID = state.user?.id;
  if (state.user?.role !== 'student' || !['review', 'graded'].includes(previous?.status) || state.retrying) return;
  if (!await confirmDialog('Try this worksheet again?', 'Your previous answers, marks and teacher feedback will stay in My results. This creates a new blank try using the worksheet and marking key currently published by your teacher.', 'Start a new try')) return;
  if (state.user?.id !== userID || state.view !== 'attempt' || state.attempt?.id !== previous.id) return;
  state.retrying = true;
  clearTimeout(state.pollTimer);
  try {
    const attempt = await api(`/attempts/${encodeURIComponent(previous.id)}/retry`, { method: 'POST', body: { version: previous.version } });
    if (state.user?.id !== userID || state.view !== 'attempt' || state.attempt?.id !== previous.id) return;
    await openAttempt(attempt.id, { skipGuard: true, attempt });
    toast(`Attempt ${attempt.attempt_number || 2} is ready. Your previous work is saved in My results.`);
  } catch (error) {
    if (error.status === 409 && state.user?.id === userID && state.attempt?.id === previous.id) {
      const latest = await api(`/attempts/${encodeURIComponent(previous.id)}`);
      if (state.attempt?.id === previous.id) { state.attempt = latest; renderAttempt(); }
    }
    throw error;
  } finally {
    state.retrying = false;
    if (state.user && state.view === 'attempt') schedulePoll();
  }
}

async function openAttempt(id, { skipGuard = false, attempt: loaded } = {}) {
  if (!skipGuard && !await leaveCurrent()) return;
  const attempt = loaded || await api(`/attempts/${encodeURIComponent(id)}`);
  state.view = 'attempt';
  state.attempt = attempt;
  state.attempt.answers ||= {};
  state.page = 0;
  state.selected = attempt.questions[0]?.id || null;
  state.dirtyGeneration = 0;
  state.savedGeneration = 0;
  state.conflict = false;
  state.saveError = '';
  state.tool = 'pen';
  state.inkHistory.clear();
  state.submitting = false;
  state.mode = attempt.answers[state.selected]?.text ? 'type' : 'ink';
  setRoute(`attempt/${id}`);
  renderAttempt();
  if (state.user.role === 'student' && attempt.status === 'draft') {
    let recovered;
    try { recovered = JSON.parse(localStorage.getItem(localKey()) || 'null'); } catch { recovered = null; }
    if (recovered?.unsaved && recovered.answers && JSON.stringify(recovered.answers) !== JSON.stringify(attempt.answers)) {
      if (recovered.version === attempt.version) {
        if (await confirmDialog('Continue your saved handwriting?', 'This browser has a newer unsent draft for your account. Restore it to continue where you left off, or cancel to use the server copy.', 'Restore my draft')) {
          state.attempt.answers = recovered.answers;
          state.dirtyGeneration += 1;
          state.mode = state.attempt.answers[state.selected]?.text ? 'type' : 'ink';
          renderAttempt();
          scheduleSave();
        } else forgetLocal();
      } else {
        showDialog('Two versions of your work', '<p>This device has unsent handwriting, but the server version has changed. Download the local draft for your teacher before choosing which copy to keep. Nothing will overwrite the newer server answers automatically.</p>', `${button('download-local', 'Download local draft', 'secondary')}${button('use-server-copy', 'Use server answers', 'primary')}`);
        state.conflict = true;
        updateSaveStatus();
      }
    }
  }
  schedulePoll();
}

function isStudentDraft() { return state.user?.role === 'student' && state.attempt?.status === 'draft'; }
function canEditAnswers() { return isStudentDraft() && !state.conflict && !state.submitting; }

function answeredCount() {
  return state.attempt.questions.filter((question) => {
    const answer = state.attempt.answers[question.id];
    return answer && (answer.text?.trim() || answer.strokes?.length);
  }).length;
}

function attemptActionsHTML(attempt, draft, teacher) {
  if (draft) return button('paper-upload', icon('upload') + 'Upload paper copy', 'secondary') + button('submit-attempt', 'Submit worksheet' + icon('arrow'), 'primary');
  const report = `<a class="btn secondary" href="/api/attempts/${encodeURIComponent(attempt.id)}/report.pdf" target="_blank" rel="noopener">${icon('download')}Marked PDF</a>`;
  if (!['review', 'graded'].includes(attempt.status)) return report;
  const newer = attempt.latest_attempt_id && attempt.latest_attempt_id !== attempt.id;
  if (newer) return report + button('open-latest-attempt', 'Open latest try', 'primary');
  if (teacher) return report + button('reopen-attempt', 'Return for another try', 'ghost');
  return report + button('retry-attempt', icon('undo') + 'Try again', 'primary', attempt.worksheet_published === false ? 'disabled title="Your teacher needs to publish this worksheet again before you can start a new try."' : '');
}

function renderAttempt() {
  const attempt = state.attempt;
  const draft = isStudentDraft();
  const teacher = state.user.role === 'teacher';
  replacePage(`<main id="main" class="workbench"><div class="workspace-toolbar"><div class="row">${button(teacher ? 'results' : 'library', icon('back'), 'ghost square', 'aria-label="Back"')}<div class="workspace-title"><h1>${E(attempt.title)}</h1><small>${teacher ? `${E(attempt.student_name)} · ` : ''}Attempt ${attempt.attempt_number || 1} · ${draft ? 'Take your time. Every answer is a step forward.' : 'Your worksheet and feedback'}</small></div></div><div class="row wrap">${draft ? '<span id="save-status" class="save-status" role="status" aria-live="polite"></span>' : attemptStatus(attempt.status)}${attemptActionsHTML(attempt, draft, teacher)}</div></div><div id="save-alert" hidden></div>${attempt.status === 'grading' ? `<div class="notice neutral">${icon('info')}<div>Your worksheet is being marked. Handwriting is read privately on the classroom computer, so this can take a few minutes. You can leave this page and come back. Anything that cannot be read with certainty is checked by your teacher.</div></div>` : ''}${teacher && attempt.status === 'draft' ? '<div class="notice neutral">This student is still working. Review becomes available after submission.</div>' : ''}<div class="workspace-layout"><section class="sheet-column" aria-label="Interactive worksheet">${sheetHTML()}</section><aside class="side-panel" id="answer-panel" aria-label="Answer pad and feedback">${answerPanelHTML()}</aside></div></main>`);
  bindStudentInk();
  bindPaperImages();
  updateSaveStatus();
}

function summaryHTML() {
  const summary = state.attempt.summary;
  if (!summary || state.attempt.status === 'draft' || state.attempt.status === 'grading') return '';
  return `<div class="score-hero"><div class="eyebrow">${summary.final ? 'Worksheet result' : 'Marks so far'}</div><div class="score">${fmt(summary.earned)} <span style="font-size:1.2rem;font-weight:450;color:#c3ccda">/ ${fmt(summary.total)}</span></div>${summary.final ? tag(`${fmt(summary.percentage)}% · All answers marked`, 'green') : tag(`${summary.pending} ${summary.pending === 1 ? 'answer needs' : 'answers need'} teacher review`, 'orange')}<p>${summary.final ? 'Each answer below has its own feedback.' : 'This is a provisional total. Answers waiting for review have no mark yet; they are not counted as wrong.'}</p></div>`;
}

function answerPanelHTML() {
  const attempt = state.attempt;
  const question = currentQuestion();
  const draft = isStudentDraft();
  const teacher = state.user.role === 'teacher';
  const count = answeredCount();
  const index = attempt.questions.findIndex((item) => item.id === state.selected);
  const answer = attempt.answers[question?.id] || { text: '', strokes: [] };
  const result = attempt.results?.find((item) => item.question_id === question?.id);
  const page = attempt.pages[question?.page || 0];
  const aspect = question ? question.rect.w * page.width / (question.rect.h * page.height) : 3;
  const typed = !!answer.text || state.mode === 'type';
  const tracing = question?.kind === 'manual';
  const background = tracing ? `<img class="pad-source" src="/api/worksheets/${encodeURIComponent(attempt.worksheet_id)}/pages/${question.page}.png" alt="Printed tracing guide" style="width:${100 / question.rect.w}%;height:${100 / question.rect.h}%;left:${-100 * question.rect.x / question.rect.w}%;top:${-100 * question.rect.y / question.rect.h}%">` : '';
  const pad = `<div class="pad-area ${tracing ? 'tracing-pad' : ''}" style="aspect-ratio:${aspect};width:min(100%,${350 * aspect}px);min-height:0;max-height:none;margin-inline:auto">${background}<canvas id="answer-pad" aria-label="${draft ? 'Write your answer here using a stylus, or use Type instead' : 'Student handwriting evidence'}"></canvas><div class="pad-placeholder" id="pad-placeholder" ${answer.strokes?.length || tracing ? 'hidden' : ''}>${draft ? 'Your pencil goes here' : 'No handwriting submitted'}</div></div>`;
  return `<div class="panel-head"><h2>${draft ? 'Your answer space' : teacher ? 'Review & feedback' : 'How did you do?'}</h2><p>${draft ? 'Tap a number to choose an answer area.' : 'Select an answer to see its marks and feedback.'}</p></div><div class="panel-body">${summaryHTML()}${draft ? `<div class="row between small"><span class="muted">Your progress</span><strong id="answer-count">${count} / ${attempt.questions.length} answered</strong></div><div class="progress-track"><span id="answer-progress" style="width:${attempt.questions.length ? count / attempt.questions.length * 100 : 0}%"></span></div>` : ''}<div class="question-chips" aria-label="Select an answer">${attempt.questions.map((item, number) => {
    const itemAnswer = attempt.answers[item.id];
    const itemResult = attempt.results?.find((entry) => entry.question_id === item.id);
    return `<button class="question-chip ${item.id === state.selected ? 'active' : ''} ${itemResult?.status || (itemAnswer?.text || itemAnswer?.strokes?.length ? 'answered' : '')}" data-action="select-question" data-id="${E(item.id)}" aria-label="Answer ${number + 1}: ${E(item.label)}" aria-pressed="${item.id === state.selected}">${number + 1}</button>`;
  }).join('')}</div>${question ? `<div class="row between"><h3 class="mb0">${E(questionLabel(question, index))}</h3><span class="tag">${fmt(question.points)} ${question.points === 1 ? 'mark' : 'marks'}</span></div>${!draft && isPaperAttempt(attempt) ? paperAnswerHTML(attempt, question) : question.kind === 'choice' ? `<p class="caption mt16">${draft ? 'Tap one choice here or on the worksheet.' : 'Selected answer'}</p><div class="choice-options">${(question.options || []).map((option) => `<button class="choice-option ${answer.text === option.value ? 'chosen' : ''}" data-action="choose" data-id="${E(question.id)}" data-value="${E(option.value)}" aria-pressed="${answer.text === option.value}" ${draft ? '' : 'disabled'}>${E(option.label)}</button>`).join('')}</div>${draft && answer.text ? `<div class="mt16">${button('clear-choice', 'Clear selection', 'ghost compact')}</div>` : ''}` : draft ? `<div class="tabs mode-tabs" role="group" aria-label="Answer input method"><button data-action="mode-ink" class="${typed ? '' : 'active'}">Write with pencil</button><button data-action="mode-type" class="${typed ? 'active' : ''}">Type instead</button></div>${typed ? `<div class="field"><label for="typed-answer">Your answer</label><textarea id="typed-answer" data-answer="text" rows="3" maxlength="2000" autocapitalize="off" spellcheck="false" ${question.kind === 'number' ? 'inputmode="decimal"' : ''}>${E(answer.text || '')}</textarea><small>Typing replaces any handwriting in this answer area.</small></div>` : `${pad}<p id="ink-evidence" class="caption ink-evidence" role="status">${answer.strokes?.length ? `${answer.strokes.length} pen ${answer.strokes.length === 1 ? 'stroke' : 'strokes'} in this answer` : 'Blank answer — no pen strokes'}</p><div class="pen-tools">${button('tool-pen', icon('pen') + 'Pen', 'secondary', `aria-pressed="${state.tool === 'pen'}"`)}${button('tool-eraser', icon('eraser') + 'Eraser', 'secondary', `aria-pressed="${state.tool === 'eraser'}"`)}${button('undo-ink', icon('undo'), 'secondary', 'aria-label="Undo last stroke"')}${button('clear-ink', icon('trash'), 'secondary', 'aria-label="Clear this answer"')}</div><label class="checkbox caption"><input id="finger-mode" type="checkbox" ${state.finger ? 'checked' : ''}>Draw with a finger too</label><p class="caption ink-hint">Tap once to focus, or drag to write immediately. Only your pen strokes are read—not the paper lines or pointer. Use Undo or Eraser for accidental dots. If the trackpad is difficult, use Type instead.</p><p class="caption">Write one clear answer, using most of the box height. A mouse or trackpad works too; a stylus usually gives more control. Use the page around the box to scroll.</p>`}${question.kind === 'manual' ? '<div class="manual-note">Your teacher will look at this answer and award the marks.</div>' : ''}` : `<div class="mt16">${answer.text ? `<div class="review-card"><span class="caption">${question.kind === 'choice' ? 'Selected answer' : 'Typed answer'}</span><p>${E(answer.text)}</p></div>` : pad}</div>`}${!draft && result ? resultHTML(result) : ''}${teacher && result && attempt.status !== 'grading' && attempt.status !== 'draft' ? `<div class="panel-separator"></div><div class="key-hint"><strong>Teacher marking key</strong><br>${question.kind === 'manual' ? 'Teacher judgment required for this response.' : E((question.expected || []).join(' or '))}</div><form id="review-form" class="mt16"><div class="two-cols"><div class="field"><label for="review-mark">Awarded marks</label><input id="review-mark" name="awarded" type="number" required min="0" max="${question.points}" step="0.01" value="${result.awarded ?? ''}" placeholder="0–${question.points}"></div><div class="field"><label for="review-text">Read as (optional)</label><input id="review-text" name="recognized_text" maxlength="2000" value="${E(result.recognized_text || '')}"></div></div><div class="field"><label for="review-feedback">Feedback for student</label><textarea id="review-feedback" name="feedback" rows="2" maxlength="2000">${E(result.source === 'teacher' ? result.feedback || '' : '')}</textarea></div><button type="submit" class="btn primary full">${icon('check')}Save teacher mark</button></form>` : ''}<div class="row between mt16">${button('question-prev', '← Previous', 'ghost compact', index <= 0 ? 'disabled' : '')}${button('question-next', 'Next →', 'secondary compact', index >= attempt.questions.length - 1 ? 'disabled' : '')}</div>` : '<p>No answer areas are available on this worksheet.</p>'}</div>`;
}

function resultHTML(result) {
  const status = { correct: ['Correct', 'green'], incorrect: ['Not correct yet', 'red'], partial: ['Partly correct', 'blue'], pending_review: ['Waiting for teacher', 'orange'] }[result.status] || ['Marking', 'orange'];
  return `<div class="review-card mt16"><div class="row between">${tag(status[0], status[1])}<strong>${result.awarded === null || result.awarded === undefined ? 'Pending' : `${fmt(result.awarded)} / ${fmt(result.max_points)}`}</strong></div>${result.recognized_text && !state.attempt.answers[result.question_id]?.text ? `<p><span class="muted">Read as:</span> ${E(result.recognized_text)}</p>` : ''}<p>${E(result.feedback || (result.status === 'pending_review' ? 'Your teacher will check this response before the mark is final.' : ''))}</p><div class="caption mt16">${result.source === 'teacher' ? 'Reviewed by your teacher' : result.source === 'paper' ? 'Read from the uploaded paper' : result.source === 'paper-choice' ? 'Marked option found on the uploaded paper' : result.source === 'handwriting' || result.source?.includes('ocr') ? 'Local handwriting recognition' : 'Answer checked against the marking key'}</div></div>`;
}

function bindStudentInk() {
  const attempt = state.attempt;
  for (const canvas of $$('[data-ink-id]')) {
    const question = attempt.questions.find((item) => item.id === canvas.dataset.inkId);
    const answer = attempt.answers[question.id] || { text: '', strokes: [] };
    const instance = new InkCanvas(canvas, {
      strokes: answer.strokes, readOnly: !canEditAnswers() || !!answer.text,
      finger: state.finger, tool: state.tool, width: 0.009, historyLimit: 0, onLimit: (message) => toast(message, true),
      selectOnTap: () => state.activeInkSurface !== canvas || state.selected !== question.id,
      onStart: () => {
        state.activeInkSurface = canvas;
        if (state.selected !== question.id) {
          state.selected = question.id;
          state.mode = 'ink';
          refreshAnswerPanel();
          highlightRegion();
        }
      },
      onChange: (strokes, source) => changeInk(question.id, strokes, source),
    });
    state.ink.set(question.id, instance);
  }
  bindPad();
}

function bindPad() {
  const canvas = $('#answer-pad');
  if (!canvas) return;
  const question = currentQuestion();
  const answer = state.attempt.answers[question.id] || {};
  state.pad = new InkCanvas(canvas, { strokes: answer.strokes, readOnly: !canEditAnswers(), finger: state.finger, tool: state.tool, width: 0.009, historyLimit: 0, selectOnTap: () => state.activeInkSurface !== canvas, onStart: () => { state.activeInkSurface = canvas; }, onLimit: (message) => toast(message, true), onChange: (strokes, source) => changeInk(question.id, strokes, source) });
}

function refreshAnswerPanel() {
  state.pad?.destroy();
  state.pad = null;
  $('#answer-panel').innerHTML = answerPanelHTML();
  bindPad();
  bindPaperImages();
}

function isPaperAttempt(attempt) { return attempt?.submission_mode === 'paper' && !!attempt.paper; }

function paperAnswerHTML(attempt, question) {
  const page = attempt.pages[question.page];
  const aspect = question.rect.w * page.width / (question.rect.h * page.height);
  const pageURL = `/api/attempts/${encodeURIComponent(attempt.id)}/paper/pages/${question.page}.png`;
  const crop = `<div class="pad-area paper-pad" style="aspect-ratio:${aspect};width:min(100%,${350 * aspect}px);min-height:0;max-height:none;margin-inline:auto"><img class="pad-source" src="${pageURL}" alt="Uploaded paper answer" style="width:${100 / question.rect.w}%;height:${100 / question.rect.h}%;left:${-100 * question.rect.x / question.rect.w}%;top:${-100 * question.rect.y / question.rect.h}%"></div>`;
  const isolated = ['number', 'text'].includes(question.kind) ? `<p class="caption mt16 mb0">Writing found by the marker (printing removed)</p><div class="isolated-ink"><img src="/api/attempts/${encodeURIComponent(attempt.id)}/paper/answers/${encodeURIComponent(question.id)}.png" alt="Handwriting isolated from the paper answer" loading="lazy"></div>` : '';
  return `<p class="caption mt16">From the uploaded paper copy</p>${crop}${isolated}`;
}

function bindPaperImages() {
  $$('.isolated-ink img').forEach((image) => image.addEventListener('error', () => { image.closest('.isolated-ink').hidden = true; }, { once: true }));
}

function highlightRegion() { $$('[data-region]').forEach((region) => region.classList.toggle('selected', region.dataset.region === state.selected)); }

function changeInk(id, strokes, source, recordHistory = true) {
  if (!canEditAnswers()) return;
  const otherPoints = Object.entries(state.attempt.answers).reduce((sum, [questionID, answer]) => sum + (questionID === id ? 0 : (answer.strokes || []).reduce((count, stroke) => count + stroke.points.length, 0)), 0);
  const limit = Math.min(20000, 150000 - otherPoints);
  const total = strokes.reduce((sum, stroke) => sum + stroke.points.length, 0);
  if (total > limit) {
    const minimum = strokes.reduce((sum, stroke) => sum + Math.min(stroke.points.length, 2), 0);
    if (limit < minimum) {
      source?.setStrokes(state.attempt.answers[id]?.strokes || []);
      toast('This worksheet has reached its handwriting limit. Erase unnecessary strokes before adding more.', true);
      return;
    }
    let remaining = limit - minimum;
    const excess = total - minimum;
    strokes = strokes.map((stroke) => {
      const baseline = Math.min(stroke.points.length, 2);
      const extra = Math.min(remaining, Math.floor((stroke.points.length - baseline) * (limit - minimum) / Math.max(1, excess)));
      remaining -= extra;
      const target = baseline + extra;
      return { ...stroke, points: target >= stroke.points.length ? stroke.points : Array.from({ length: target }, (_value, index) => stroke.points[Math.round(index * (stroke.points.length - 1) / Math.max(1, target - 1))]) };
    });
    source?.setStrokes(strokes);
  }
  if (recordHistory) {
    const history = state.inkHistory.get(id) || [];
    history.push(clone(state.attempt.answers[id]?.strokes || []));
    if (history.length > 40) history.shift();
    state.inkHistory.set(id, history);
    const pointCount = (snapshots) => snapshots.reduce((sum, snapshot) => sum + snapshot.reduce((count, stroke) => count + stroke.points.length, 0), 0);
    let historyPoints = [...state.inkHistory.values()].reduce((sum, snapshots) => sum + pointCount(snapshots), 0);
    for (const snapshots of state.inkHistory.values()) {
      while (historyPoints > 120000 && snapshots.length > 1) historyPoints -= pointCount([snapshots.shift()]);
    }
  }
  state.attempt.answers[id] = { text: '', strokes };
  if (state.ink.get(id) !== source) state.ink.get(id)?.setStrokes(strokes);
  if (state.selected === id && state.pad !== source) state.pad?.setStrokes(strokes);
  if (state.selected === id && $('#pad-placeholder')) $('#pad-placeholder').hidden = strokes.length > 0 || currentQuestion()?.kind === 'manual';
  if (state.selected === id && $('#ink-evidence')) $('#ink-evidence').textContent = strokes.length ? `${strokes.length} pen ${strokes.length === 1 ? 'stroke' : 'strokes'} in this answer` : 'Blank answer — no pen strokes';
  markAnswerDirty();
}

function markAnswerDirty() {
  state.dirtyGeneration += 1;
  state.saveError = '';
  updateAnswerProgress();
  updateSaveStatus();
  clearTimeout(state.localTimer);
  state.localTimer = setTimeout(persistLocal, 200);
  scheduleSave();
}

function updateAnswerProgress() {
  const count = answeredCount();
  if ($('#answer-count')) $('#answer-count').textContent = `${count} / ${state.attempt.questions.length} answered`;
  if ($('#answer-progress')) $('#answer-progress').style.width = `${count / Math.max(1, state.attempt.questions.length) * 100}%`;
  $$('.question-chip').forEach((chip) => {
    const answer = state.attempt.answers[chip.dataset.id];
    chip.classList.toggle('answered', !!(answer?.text?.trim() || answer?.strokes?.length));
  });
}

function scheduleSave(delay = 1200) {
  clearTimeout(state.saveTimer);
  if (!canEditAnswers()) return;
  state.saveTimer = setTimeout(() => flushAnswers().catch((error) => { state.saveError = error.message; updateSaveStatus(); }), delay);
}

async function flushAnswers() {
  clearTimeout(state.saveTimer);
  clearTimeout(state.localTimer);
  if (!isStudentDraft()) return;
  if (state.conflict) throw new Error('This worksheet has a newer server draft. Resolve the version conflict before saving.');
  persistLocal();
  if (state.savePromise) {
    await state.savePromise;
    if (state.dirtyGeneration > state.savedGeneration) return flushAnswers();
    return;
  }
  if (state.dirtyGeneration <= state.savedGeneration) return;
  const attempt = state.attempt;
  const generation = state.dirtyGeneration;
  const answers = clone(attempt.answers);
  state.savePromise = api(`/attempts/${encodeURIComponent(attempt.id)}/answers`, { method: 'PUT', body: { version: attempt.version, answers } });
  updateSaveStatus();
  try {
    const saved = await state.savePromise;
    if (state.attempt?.id !== attempt.id) return;
    state.attempt.version = saved.version;
    state.savedGeneration = generation;
    state.saveError = '';
    persistLocal();
  } catch (error) {
    if (state.attempt?.id !== attempt.id) throw error;
    state.saveError = error.message;
    if (error.status === 409) {
      state.conflict = true;
      state.ink.forEach((canvas) => canvas.configure({ readOnly: true }));
      state.pad?.configure({ readOnly: true });
    }
    persistLocal();
    throw error;
  } finally {
    state.savePromise = null;
    updateSaveStatus();
  }
  if (state.dirtyGeneration > state.savedGeneration) return flushAnswers();
}

function updateSaveStatus() {
  const label = $('#save-status');
  if (!label) return;
  const pending = state.dirtyGeneration > state.savedGeneration;
  const failed = state.conflict || !!state.saveError;
  label.className = `save-status${failed ? ' error' : pending ? ' warning' : ''}`;
  label.innerHTML = `${icon(failed ? 'info' : pending || state.savePromise ? 'save' : 'check')}${state.conflict ? 'Version conflict' : state.saveError ? 'Saved on this device only' : state.savePromise ? 'Saving…' : pending ? 'Waiting to save…' : 'All answers saved'}`;
  const alert = $('#save-alert');
  if (!alert) return;
  alert.hidden = !failed;
  if (failed) alert.innerHTML = `<div class="notice error"><div class="grow">${state.conflict ? 'Your draft changed in another tab or device. Your local handwriting has been kept. Review the server copy before continuing.' : E(state.saveError)}</div><div class="row wrap">${state.conflict ? button('download-local', 'Download local draft', 'secondary compact') + button('reload-attempt', 'Load server copy', 'secondary compact') : button('retry-save', 'Retry save', 'secondary compact')}</div></div>`;
}

async function selectQuestion(id) {
  if (isStudentDraft()) finishActiveInk();
  state.activeInkSurface = null;
  const doc = state.view === 'editor' ? state.worksheet : state.attempt;
  const question = doc.questions.find((item) => item.id === id);
  if (!question) return;
  state.selected = id;
  if (state.view === 'editor') {
    if (state.page !== question.page) { state.page = question.page; renderEditor(); }
    else { $('#sheet-overlay').innerHTML = regionsHTML(); refreshEditorPanel(); }
  } else {
    state.mode = state.attempt.answers[id]?.text ? 'type' : 'ink';
    if (state.page !== question.page) { state.page = question.page; renderAttempt(); }
    else { highlightRegion(); refreshAnswerPanel(); }
  }
}

async function setAnswerMode(mode) {
  if (!canEditAnswers() || state.mode === mode) return;
  finishActiveInk();
  const answer = state.attempt.answers[state.selected] || {};
  if ((mode === 'type' && answer.strokes?.length) || (mode === 'ink' && answer.text?.trim())) {
    if (!await confirmDialog('Change how you answer?', mode === 'type' ? 'Typing will clear the handwriting for this answer area.' : 'Writing with a pencil will clear the typed answer for this area.', 'Switch answer method')) return;
    state.attempt.answers[state.selected] = { text: '', strokes: [] };
    state.ink.get(state.selected)?.setStrokes([], { resetHistory: true });
    markAnswerDirty();
  }
  state.mode = mode;
  const region = $$('[data-region]').find((element) => element.dataset.region === state.selected);
  if (region && $('.typed-overlay', region)) { $('.typed-overlay', region).textContent = ''; $('.typed-overlay', region).hidden = true; }
  state.ink.get(state.selected)?.configure({ readOnly: mode === 'type' });
  refreshAnswerPanel();
  if (mode === 'type') $('#typed-answer')?.focus();
}

function chooseAnswer(id, value) {
  if (!canEditAnswers()) return;
  state.selected = id;
  state.attempt.answers[id] = { text: value, strokes: [] };
  markAnswerDirty();
  $$('.choice-hotspot').forEach((element) => {
    if (element.dataset.id !== id) return;
    const selected = element.dataset.value === value;
    element.classList.toggle('chosen', selected);
    element.setAttribute('aria-pressed', String(selected));
  });
  highlightRegion();
  refreshAnswerPanel();
}

async function submitAttempt() {
  if (!canEditAnswers()) return;
  const missing = state.attempt.questions.length - answeredCount();
  if (!await confirmDialog('Ready to hand it in?', `${missing ? `${missing} ${missing === 1 ? 'answer area is' : 'answer areas are'} still blank and will receive zero marks. ` : ''}Your answers will be saved before marking. Marking can take a few minutes. This submission stays saved; afterwards, you can use Try again to start a separate blank attempt.`, 'Submit worksheet')) return;
  await flushAnswers();
  const attempt = state.attempt;
  state.submitting = true;
  state.ink.forEach((canvas) => canvas.configure({ readOnly: true }));
  state.pad?.configure({ readOnly: true });
  $$('#answer-panel input, #answer-panel textarea, #answer-panel button, .choice-hotspot, [data-action="submit-attempt"]').forEach((element) => { element.disabled = true; });
  const alert = $('#save-alert');
  alert.hidden = false;
  alert.innerHTML = `<div class="notice neutral">${icon('info')}<div>Your answers are saved. Handing in your worksheet…</div></div>`;
  try {
    const response = await api(`/attempts/${encodeURIComponent(attempt.id)}/submit`, { method: 'POST', body: { version: attempt.version } });
    if (!state.user || state.attempt?.id !== attempt.id) return;
    state.attempt = response;
    forgetLocal();
    toast(response.status === 'graded' ? 'Your worksheet has been marked.' : response.status === 'grading' ? 'Worksheet handed in. Marking has started.' : 'Worksheet submitted. Your handwriting is safe.');
  } catch (error) {
    if (state.user) {
      try {
        const saved = await api(`/attempts/${encodeURIComponent(attempt.id)}`);
        if (saved.status !== 'draft') { state.attempt = saved; forgetLocal(); }
      } catch { /* Keep the saved local draft if the outcome cannot yet be confirmed. */ }
    }
    throw error;
  } finally {
    state.submitting = false;
    if (state.user && state.view === 'attempt') { renderAttempt(); schedulePoll(); }
  }
}

function schedulePoll() {
  clearTimeout(state.pollTimer);
  if (state.view !== 'attempt' || !['grading', 'review'].includes(state.attempt.status)) return;
  const id = state.attempt.id;
  state.pollTimer = setTimeout(async () => {
    try {
      const updated = await api(`/attempts/${encodeURIComponent(id)}`);
      if (state.view !== 'attempt' || state.attempt.id !== id) return;
      if (updated.version !== state.attempt.version || updated.status !== state.attempt.status) {
        const reviewing = state.user.role === 'teacher' && $('#review-form')?.contains(document.activeElement);
        if (!reviewing) { state.attempt = updated; renderAttempt(); }
      }
    } catch { /* The next bounded poll retries; existing feedback remains available. */ }
    schedulePoll();
  }, state.attempt.status === 'grading' ? 2500 : 12000);
}

async function showResults() {
  if (!await leaveCurrent()) return;
  const { attempts = [] } = await api('/attempts');
  state.attempts = attempts;
  state.view = 'results';
  setRoute('results');
  const teacher = state.user.role === 'teacher';
  const pending = attempts.filter((attempt) => attempt.status === 'review').length;
  const marked = attempts.filter((attempt) => attempt.status === 'graded').length;
  replacePage(`<main id="main" class="page-main"><div class="page-heading"><div><div class="eyebrow">${teacher ? 'Every effort tells a story' : 'Look how far you’ve come'}</div><h1>${teacher ? 'A window into their learning.' : 'Your learning journey.'}</h1><p>${teacher ? 'See submitted work, check handwriting and give every student the marks they have earned.' : 'Find your finished worksheets and see your teacher’s feedback.'}</p></div>${teacher ? `<div class="row wrap">${button('teacher-paper-upload', icon('upload') + 'Upload a paper worksheet', 'primary')}<a class="btn secondary" href="/api/results.csv">${icon('download')}Export marks CSV</a></div>` : ''}</div><div class="stats"><div class="stat"><div class="value">${attempts.length}</div><div class="label">${teacher ? 'Student attempts' : 'Your attempts'}</div></div><div class="stat"><div class="value">${pending}</div><div class="label">Waiting for teacher review</div></div><div class="stat"><div class="value">${marked}</div><div class="label">Fully marked</div></div></div><div class="section-title"><h2>${teacher ? 'Student work' : 'Worksheet results'}</h2>${button('results', 'Refresh', 'ghost compact')}</div>${attempts.length ? `<div class="table-wrap"><table><thead><tr>${teacher ? '<th scope="col">Student</th>' : ''}<th scope="col">Worksheet</th><th scope="col">Status</th><th scope="col">Marks</th><th scope="col"><span class="hidden">Open</span></th></tr></thead><tbody>${attempts.map((attempt) => {
    const summary = attempt.summary;
    return `<tr>${teacher ? `<td><div class="result-name">${E(attempt.student_name || 'Student')}</div></td>` : ''}<td><div class="result-name">${E(attempt.title || attempt.worksheet_title || 'Worksheet')}</div><div class="muted">Attempt ${attempt.attempt_number || 1}${attempt.submission_mode === 'paper' ? ' · Paper copy' : ''}${attempt.submitted_at ? ` · ${E(new Date(attempt.submitted_at).toLocaleString())}` : ''}</div></td><td>${attemptStatus(attempt.status)}</td><td>${summary && attempt.status !== 'draft' && attempt.status !== 'grading' ? `<strong>${fmt(summary.earned)} / ${fmt(summary.total)}</strong><div class="muted">${summary.final ? `${fmt(summary.percentage)}%` : `${summary.pending} pending · provisional`}</div>` : '<span class="muted">Not marked yet</span>'}</td><td>${button('open-attempt', teacher && attempt.status === 'review' ? 'Review' : 'Open', attempt.status === 'review' && teacher ? 'primary compact' : 'secondary compact', `data-id="${E(attempt.id)}"`)}</td></tr>`;
  }).join('')}</tbody></table></div>` : `<section class="empty"><div class="empty-symbol">${icon('review')}</div><h2>No results just yet</h2><p>${teacher ? 'Student work will appear here when someone starts a published worksheet.' : 'Start a worksheet from your library. Your work and feedback will appear here.'}</p>${button('library', 'Go to worksheets', 'primary')}</section>`}<div class="footer-note">${icon('info')} Pending answers have no mark yet. Final percentages appear only after every answer has been checked.</div></main>`);
}

const PAPER_ACCEPT = 'application/pdf,image/jpeg,image/png,.pdf,.jpg,.jpeg,.png';
const PAPER_TIPS = '<ul class="tips"><li>Lay each page flat in good light and include the whole page.</li><li>Upload every page once: PDF, JPG or PNG, up to 20 MB per file.</li><li>Answers that cannot be read with certainty are checked by the teacher.</li></ul>';

function showPaperDialog() {
  if (!canEditAnswers()) return;
  showDialog('Hand in a paper copy', `<p>Did this worksheet on paper? Photograph or scan the completed pages and upload them. The paper copy is marked instead of any answers on this screen.</p>${PAPER_TIPS}<form id="paper-form"><div class="field"><label for="paper-files">Photos or scan of your worksheet</label><input id="paper-files" name="files" type="file" accept="${PAPER_ACCEPT}" multiple required></div><p class="form-error" hidden role="alert"></p><button class="btn primary full" type="submit">${icon('upload')}Upload and mark</button></form>`);
}

async function showTeacherPaperDialog() {
  showDialog('Upload a paper worksheet', '<p class="muted">Loading your worksheets and class…</p>');
  const [{ worksheets = [] }, { students = [] }] = await Promise.all([api('/worksheets'), api('/students')]);
  if (!dialog.open) return;
  const published = worksheets.filter((worksheet) => worksheet.published);
  const body = $('.dialog-body', dialog);
  if (!published.length || !students.length) {
    body.innerHTML = `<p>${!published.length ? 'Publish a worksheet with a confirmed marking key first.' : 'No students have joined your class yet. Share your class code first.'}</p>`;
    return;
  }
  body.innerHTML = `<p>Upload a student's completed printed worksheet. It is marked with the published answer key.</p>${PAPER_TIPS}<form id="teacher-paper-form"><div class="field"><label for="paper-worksheet">Worksheet</label><select id="paper-worksheet" name="worksheet_id" required>${published.map((worksheet) => `<option value="${E(worksheet.id)}">${E(worksheet.title)}</option>`).join('')}</select></div><div class="field"><label for="paper-student">Student</label><select id="paper-student" name="student_id" required>${students.map((student) => `<option value="${E(student.id)}">${E(student.name)} (${E(student.username)})</option>`).join('')}</select></div><div class="field"><label for="teacher-paper-files">Photos or scan</label><input id="teacher-paper-files" name="files" type="file" accept="${PAPER_ACCEPT}" multiple required></div><label class="checkbox field"><input type="checkbox" name="replace_draft" value="true"><span>If this student has an unfinished online attempt, mark this paper copy instead.</span></label><p class="form-error" hidden role="alert"></p><button class="btn primary full" type="submit">${icon('upload')}Upload and mark</button></form>`;
}

async function uploadPaper(form) {
  const submit = $('button[type="submit"]', form);
  const label = submit.innerHTML;
  submit.textContent = 'Checking the pages…';
  try {
    const data = new FormData(form);
    if (form.id === 'paper-form') {
      await flushAnswers();
      data.set('version', String(state.attempt.version));
      const attempt = await api(`/attempts/${encodeURIComponent(state.attempt.id)}/paper`, { method: 'POST', body: data });
      closeDialog();
      forgetLocal();
      await openAttempt(attempt.id, { skipGuard: true, attempt });
    } else {
      const worksheetID = data.get('worksheet_id');
      data.delete('worksheet_id');
      const attempt = await api(`/worksheets/${encodeURIComponent(worksheetID)}/paper`, { method: 'POST', body: data });
      closeDialog();
      await openAttempt(attempt.id, { skipGuard: true, attempt });
    }
    toast('Paper copy received. Marking has started.');
  } finally {
    if (submit.isConnected) submit.innerHTML = label;
  }
}

async function reviewAttempt(form) {
  const question = currentQuestion();
  const values = new FormData(form);
  const awarded = Number(values.get('awarded'));
  if (!Number.isFinite(awarded) || awarded < 0 || awarded > question.points) throw new Error(`Enter a mark between 0 and ${question.points}.`);
  state.attempt = await api(`/attempts/${encodeURIComponent(state.attempt.id)}/review`, { method: 'POST', body: { version: state.attempt.version, reviews: [{ question_id: question.id, awarded, feedback: values.get('feedback') || '', recognized_text: values.get('recognized_text') || '' }] } });
  renderAttempt();
  toast('Teacher mark saved. The student result is updated.');
  schedulePoll();
}

function downloadJSON(value, filename) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function reloadAttempt() {
  if (!await confirmDialog('Load the server copy?', 'This replaces the answers currently shown with the latest server copy. Download your local draft first if you need to preserve it.', 'Load server copy')) return;
  forgetLocal();
  closeDialog();
  await openAttempt(state.attempt.id, { skipGuard: true });
}

async function signOut() {
  if (!await leaveCurrent()) return;
  if (state.saveError || state.conflict) {
    if (!await confirmDialog('Sign out and remove the local recovery copy?', 'Your latest answers are not saved to the server. Signing out clears this account’s local recovery drafts on this shared device. Go back and download your draft if you need it.', 'Sign out', true)) return;
  }
  state.authGeneration += 1;
  state.navToken += 1;
  await api('/logout', { method: 'POST', body: {} });
  clearAccountDrafts();
  clearTimeout(state.localTimer);
  state.user = null;
  state.authGeneration += 1;
  state.csrf = '';
  state.attempt = null;
  state.worksheet = null;
  state.editorDirty = false;
  state.saveError = '';
  state.conflict = false;
  setRoute('');
  announceSession();
  authPage('login');
}

const actions = {
  'close-dialog': () => closeDialog(false),
  'confirm-dialog': () => closeDialog(true),
  'auth-login': () => authPage('login'),
  'auth-register': () => authPage('register'),
  'auth-setup': () => authPage('setup'),
  library: () => showLibrary(),
  results: () => showResults(),
  logout: signOut,
  'copy-code': async () => {
    try { await navigator.clipboard.writeText(state.user.class_code || ''); toast('Class code copied. Share it with your students.'); }
    catch { showDialog('Your class code', `<p>Share this code with your students:</p><input readonly value="${E(state.user.class_code)}" aria-label="Class code">`); }
  },
  import: () => showImport(),
  'import-samples': () => showImport('samples'),
  'import-upload': () => showImport('upload'),
  'import-sample': async (element) => {
    const worksheet = await api('/samples/import', { method: 'POST', body: { filename: element.dataset.file } });
    closeDialog();
    await openEditor(worksheet.id, { skipGuard: true });
    toast('Sample imported as a draft. Check its marking key before publishing.');
  },
  'open-editor': (element) => openEditor(element.dataset.id),
  'toggle-draw': () => { state.drawMode = !state.drawMode; renderEditor(); },
  'add-default-question': () => {
    if (state.worksheet.questions.length >= 100) throw new Error('A worksheet can contain up to 100 answer areas.');
    const question = { id: uid(), label: `Question ${state.worksheet.questions.length + 1}`, page: state.page, rect: { x: 0.2, y: 0.35, w: 0.3, h: 0.1 }, kind: 'number', expected: [], points: 1, tolerance: 0, case_sensitive: false, options: [] };
    state.worksheet.questions.push(question);
    state.selected = question.id;
    state.drawMode = false;
    markEditorDirty();
    renderEditor();
    $('#question-label').focus();
    toast('Answer area added. Adjust its position using the percentage fields or arrow keys.');
  },
  'select-question': (element) => selectQuestion(element.dataset.id),
  'save-worksheet': async () => {
    if (state.worksheet.published && !await confirmDialog('Save as an unpublished draft?', 'Saving a draft removes this worksheet from the student library until you publish it again. Existing student attempts remain available.', 'Save as draft')) return;
    await saveWorksheet(false);
  },
  'publish-worksheet': () => saveWorksheet(true),
  unpublish: async () => { if (await confirmDialog('Unpublish this worksheet?', 'Students will not be able to start new attempts until you publish again. Existing attempts are kept.', 'Unpublish')) await saveWorksheet(false); },
  'delete-question': async () => {
    const question = currentQuestion();
    if (!await confirmDialog('Delete this answer area?', `Remove “${question.label}” and its marking key from this worksheet draft?`, 'Delete area', true)) return;
    state.worksheet.questions = state.worksheet.questions.filter((item) => item.id !== question.id);
    state.selected = state.worksheet.questions.find((item) => item.page === state.page)?.id || state.worksheet.questions[0]?.id;
    markEditorDirty(); renderEditor();
  },
  'download-key': () => downloadJSON(state.worksheet, 'worksheet-marking-key.json'),
  'reload-editor': async () => { closeDialog(); await openEditor(state.worksheet.id); },
  'page-prev': () => changePage(-1),
  'page-next': () => changePage(1),
  'start-worksheet': (element) => startWorksheet(element.dataset.id),
  'open-attempt': (element) => openAttempt(element.dataset.id),
  'question-prev': () => moveQuestion(-1),
  'question-next': () => moveQuestion(1),
  'mode-ink': () => setAnswerMode('ink'),
  'mode-type': () => setAnswerMode('type'),
  'tool-pen': () => setTool('pen'),
  'tool-eraser': () => setTool('eraser'),
  'undo-ink': () => {
    const history = state.inkHistory.get(state.selected);
    if (history?.length) changeInk(state.selected, history.pop(), null, false);
  },
  'clear-ink': async () => {
    if (!await confirmDialog('Clear this answer?', 'This removes all handwriting in the selected answer area.', 'Clear handwriting', true)) return;
    state.pad?.clear();
  },
  choose: (element) => chooseAnswer(element.dataset.id, element.dataset.value),
  'clear-choice': () => chooseAnswer(state.selected, ''),
  'retry-save': () => flushAnswers(),
  'submit-attempt': submitAttempt,
  'paper-upload': showPaperDialog,
  'teacher-paper-upload': showTeacherPaperDialog,
  'retry-attempt': retryAttempt,
  'open-latest-attempt': () => openAttempt(state.attempt.latest_attempt_id),
  'reload-attempt': reloadAttempt,
  'use-server-copy': reloadAttempt,
  'download-local': () => {
    let saved;
    try { saved = JSON.parse(localStorage.getItem(localKey()) || 'null'); } catch { saved = null; }
    downloadJSON({ attempt_id: state.attempt.id, student: state.user.name, ...(saved || { version: state.attempt.version, answers: state.attempt.answers }) }, 'worksheet-local-draft.json');
  },
  'reopen-attempt': async () => {
    if (!await confirmDialog('Return this worksheet to the student?', 'The student will be able to edit and resubmit. Existing marks will be cleared; handwriting will be kept.', 'Return for another try')) return;
    state.attempt = await api(`/attempts/${encodeURIComponent(state.attempt.id)}/reopen`, { method: 'POST', body: { version: state.attempt.version } });
    renderAttempt(); toast('Worksheet returned to the student.');
  },
};

function changePage(delta) {
  if (isStudentDraft()) finishActiveInk();
  const document = state.view === 'editor' ? state.worksheet : state.attempt;
  state.page = clamp(state.page + delta, 0, document.pages.length - 1);
  state.selected = document.questions.find((question) => question.page === state.page)?.id || null;
  if (state.view === 'editor') renderEditor();
  else { state.mode = document.answers[state.selected]?.text ? 'type' : 'ink'; renderAttempt(); }
}

function moveQuestion(delta) {
  const questions = state.attempt.questions;
  const index = questions.findIndex((question) => question.id === state.selected);
  const question = questions[index + delta];
  if (question) selectQuestion(question.id);
}

function setTool(tool) {
  state.tool = tool;
  state.ink.forEach((canvas) => canvas.configure({ tool }));
  state.pad?.configure({ tool });
  $$('[data-action="tool-pen"], [data-action="tool-eraser"]').forEach((element) => element.setAttribute('aria-pressed', String(element.dataset.action === `tool-${tool}`)));
}

document.addEventListener('click', async (event) => {
  const element = event.target.closest('[data-action]');
  if (!element || element.disabled) return;
  const action = actions[element.dataset.action];
  if (!action) return;
  event.preventDefault();
  element.disabled = true;
  try { await action(element); }
  catch (error) { toast(error.message || 'Something went wrong. Please try again.', true); }
  finally { if (element.isConnected) element.disabled = false; }
});

document.addEventListener('input', (event) => {
  const element = event.target;
  if (element.dataset.editor === 'title') { state.worksheet.title = element.value; markEditorDirty(); }
  if (element.dataset.question && element.tagName !== 'SELECT' && element.type !== 'checkbox') updateQuestionInput(element);
  if (element.dataset.rect) {
    const question = currentQuestion();
    const key = element.dataset.rect;
    const maximum = key === 'x' ? 1 - question.rect.w : key === 'y' ? 1 - question.rect.h : key === 'w' ? 1 - question.rect.x : 1 - question.rect.y;
    question.rect[key] = clamp(number(element.value) / 100, ['w', 'h'].includes(key) ? 0.005 : 0, maximum);
    markEditorDirty(); updateRegionElement(question);
  }
  if (element.dataset.answer === 'text' && canEditAnswers()) {
    state.attempt.answers[state.selected] = { text: element.value, strokes: [] };
    const region = $$('[data-region]').find((item) => item.dataset.region === state.selected);
    if (region && $('.typed-overlay', region)) { $('.typed-overlay', region).textContent = element.value; $('.typed-overlay', region).hidden = !element.value; }
    state.ink.get(state.selected)?.configure({ readOnly: true });
    markAnswerDirty();
  }
});

document.addEventListener('change', (event) => {
  const element = event.target;
  if (element.dataset.question && (element.tagName === 'SELECT' || element.type === 'checkbox')) updateQuestionInput(element);
  if (element.id === 'keys-confirmed') state.keysConfirmed = element.checked;
  if (element.id === 'finger-mode') {
    state.finger = element.checked;
    state.ink.forEach((canvas) => canvas.configure({ finger: state.finger }));
    state.pad?.configure({ finger: state.finger });
  }
  if (element.id === 'upload-file' && !$('#upload-title').value) $('#upload-title').value = element.files[0]?.name.replace(/\.pdf$/i, '').replaceAll('_', ' ') || '';
});

document.addEventListener('submit', async (event) => {
  const form = event.target;
  if (!['auth-form', 'upload-form', 'review-form', 'paper-form', 'teacher-paper-form'].includes(form.id)) return;
  event.preventDefault();
  const submit = $('button[type="submit"]', form);
  submit.disabled = true;
  const errorElement = $('.form-error', form);
  if (errorElement) errorElement.hidden = true;
  try {
    if (form.id === 'auth-form') {
      const values = Object.fromEntries(new FormData(form));
      if (values.class_code) values.class_code = values.class_code.trim();
      values.username = values.username.trim();
      state.authGeneration += 1;
      state.navToken += 1;
      const session = await api(state.authMode === 'setup' ? '/bootstrap' : state.authMode === 'register' ? '/register' : '/login', { method: 'POST', body: values });
      state.user = session.user;
      state.authGeneration += 1;
      state.csrf = session.csrf_token;
      if (!state.user) { const refreshed = await api('/session'); state.user = refreshed.user; state.csrf = refreshed.csrf_token; }
      announceSession();
      await showLibrary({ skipGuard: true });
    } else if (form.id === 'upload-form') {
      const data = new FormData(form);
      const worksheet = await api('/worksheets/upload', { method: 'POST', body: data });
      closeDialog();
      await openEditor(worksheet.id, { skipGuard: true });
      toast('PDF imported. Add answer areas and a marking key.');
    } else if (form.id === 'paper-form' || form.id === 'teacher-paper-form') await uploadPaper(form);
    else await reviewAttempt(form);
  } catch (error) {
    if (errorElement) { errorElement.textContent = error.message; errorElement.hidden = false; }
    else if (error.status === 409 && form.id === 'review-form') {
      toast('This attempt was updated elsewhere. Reload it before saving your review.', true);
      showDialog('The attempt has changed', '<p>Your review has not been saved because a newer version is available. Note your mark and feedback, then reload the attempt before applying it.</p>', button('reload-attempt', 'Load latest attempt', 'primary'));
    } else toast(error.message, true);
  } finally { if (submit.isConnected) submit.disabled = false; }
});

window.addEventListener('beforeunload', (event) => {
  finishActiveInk();
  if (state.editorDirty && state.view === 'editor' || isStudentDraftSafe() && state.dirtyGeneration > state.savedGeneration) {
    persistLocal();
    event.preventDefault();
    event.returnValue = '';
  }
});
function isStudentDraftSafe() { return state.user?.role === 'student' && state.attempt?.status === 'draft'; }
function finishActiveInk() {
  for (const canvas of [...state.ink.values(), state.pad].filter(Boolean)) {
    if (canvas.activePointer !== null) canvas.finish({ pointerId: canvas.activePointer, type: 'pointercancel' });
  }
}

document.addEventListener('visibilitychange', () => {
  if (document.hidden && isStudentDraftSafe()) { finishActiveInk(); persistLocal(); flushAnswers().catch(() => {}); }
  else if (!document.hidden) checkSession();
});
window.addEventListener('focus', checkSession);
window.addEventListener('pagehide', () => { if (isStudentDraftSafe()) { finishActiveInk(); persistLocal(); } });
window.addEventListener('online', () => { if (isStudentDraftSafe() && !state.conflict) { state.saveError = ''; scheduleSave(100); } });
window.addEventListener('offline', () => { if (isStudentDraftSafe()) { state.saveError = 'You are offline. Keep this tab open; your draft is stored on this device until the connection returns.'; persistLocal(); updateSaveStatus(); } });

async function initialize() {
  try {
    const [health, session] = await Promise.all([api('/health'), api('/session')]);
    state.health = health;
    state.user = session.user;
    state.authGeneration += 1;
    state.csrf = session.csrf_token;
    if (!state.user) return authPage(health.setup_required ? 'setup' : 'login');
    const [route, id] = location.hash.slice(1).split('/');
    if (route === 'worksheet' && id && state.user.role === 'teacher') await openEditor(id, { skipGuard: true });
    else if (route === 'attempt' && id) await openAttempt(id, { skipGuard: true });
    else if (route === 'results') await showResults();
    else await showLibrary({ skipGuard: true });
  } catch (error) {
    replacePage(`<main id="main" class="error-page"><div class="eyebrow">Classroom connection</div><h1>We couldn’t open this page.</h1><p class="muted">${E(error.message)}</p><a class="btn primary" href="/">Try the classroom again</a><p class="retry-note muted">If the server is starting up, give it a moment and try again.</p></main>`);
  }
}

initialize();
