import test from 'node:test';
import assert from 'node:assert/strict';
import { captureRequestIdentity, isCurrentRequestIdentity } from '../static/session.js';

test('authenticated responses are accepted only for the original account and session generation', () => {
  const session = { user: { id: 'student-a' }, authGeneration: 4 };
  const request = captureRequestIdentity(session, '/attempts/attempt-a');
  assert.equal(isCurrentRequestIdentity(request, session), true);
  session.user = { id: 'student-b' };
  assert.equal(isCurrentRequestIdentity(request, session), false);
});

test('a response cannot restore an expired account even after the same pupil signs in again', () => {
  const session = { user: { id: 'student-a' }, authGeneration: 4 };
  const request = captureRequestIdentity(session, '/attempts/attempt-a');
  session.user = null;
  session.authGeneration += 1;
  assert.equal(isCurrentRequestIdentity(request, session), false);
  session.user = { id: 'student-a' };
  session.authGeneration += 1;
  assert.equal(isCurrentRequestIdentity(request, session), false);
});

test('late saves, logout replies and authenticated session checks share the guard', () => {
  for (const path of ['/attempts/attempt-a/answers', '/worksheets/worksheet-a', '/logout', '/session']) {
    const session = { user: { id: 'student-a' }, authGeneration: 1 };
    const request = captureRequestIdentity(session, path);
    session.authGeneration += 1;
    assert.equal(isCurrentRequestIdentity(request, session), false, path);
  }
});

test('login, registration, bootstrap and anonymous discovery can establish a new session', () => {
  const session = { user: { id: 'student-a' }, authGeneration: 1 };
  for (const path of ['/login', '/register', '/bootstrap']) {
    const request = captureRequestIdentity(session, path);
    session.authGeneration += 1;
    assert.equal(isCurrentRequestIdentity(request, session), true, path);
  }
  for (const path of ['/session', '/health']) {
    assert.equal(captureRequestIdentity({ user: null, authGeneration: 0 }, path), null);
  }
});
