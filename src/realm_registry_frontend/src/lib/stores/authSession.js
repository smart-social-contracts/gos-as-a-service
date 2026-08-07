import { writable } from 'svelte/store';

/** @type {import('svelte/store').Writable<{ loading: boolean, isLoggedIn: boolean, principal: import('@dfinity/agent').Principal | null, identityIndex: number }>} */
export const authSession = writable({
  loading: true,
  isLoggedIn: false,
  principal: null,
  identityIndex: 0,
});

export function setAuthSession(partial) {
  authSession.update((state) => ({ ...state, ...partial }));
}

export function clearAuthSession() {
  authSession.set({
    loading: false,
    isLoggedIn: false,
    principal: null,
    identityIndex: 0,
  });
}

export async function syncAuthSession() {
  setAuthSession({ loading: true });
  try {
    const { ensureTestAuth, isAuthenticated, getPrincipal, getTestIdentityIndex } = await import(
      '$lib/auth.js',
    );
    const { getTestModeIIBypass } = await import('$lib/config.js');

    if (getTestModeIIBypass()) {
      const result = await ensureTestAuth();
      setAuthSession({
        loading: false,
        isLoggedIn: !!result?.principal,
        principal: result?.principal ?? null,
        identityIndex: getTestIdentityIndex(),
      });
      return result;
    }

    const loggedIn = await isAuthenticated();
    const principal = loggedIn ? await getPrincipal() : null;
    setAuthSession({
      loading: false,
      isLoggedIn: loggedIn,
      principal,
      identityIndex: 0,
    });
    return loggedIn ? { principal } : null;
  } catch (error) {
    setAuthSession({ loading: false, isLoggedIn: false, principal: null, identityIndex: 0 });
    throw error;
  }
}
