// A cookie can change while a request is in flight (another tab signs out or
// signs in). Reject the old response before it can repopulate account state.
const authTransitions = new Set(['/login', '/register', '/bootstrap']);

export function captureRequestIdentity(session, path) {
  if (!session.user || authTransitions.has(path)) return null;
  return { userID: session.user.id, generation: session.authGeneration };
}

export function isCurrentRequestIdentity(identity, session) {
  return identity === null || (
    identity.userID === session.user?.id &&
    identity.generation === session.authGeneration
  );
}
