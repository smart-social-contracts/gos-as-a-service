import { writable, derived, get } from 'svelte/store';
import { backend } from '$lib/canisters.js';

const initial = {
	loading: true,
	network: '',
	testMode: false,
	testModeIIBypass: false,
	testModeUserSelfRegistration: false,
	testModeDemoData: false,
	testModeSkipTerms: false,
	testModeSkipPassportZkproof: false,
	error: null
};

function createRegistryRuntimeFlagsStore() {
	const { subscribe, set, update } = writable({ ...initial });

	return {
		subscribe,
		fetch: async () => {
			update((state) => ({ ...state, loading: true, error: null }));
			try {
				const raw = await backend.get_runtime_flags();
				const payload = typeof raw === 'string' ? JSON.parse(raw) : raw;
				if (!payload?.success) {
					throw new Error(payload?.error || 'Failed to fetch registry runtime flags');
				}
				set({
					loading: false,
					network: payload.network || '',
					testMode: !!payload.test_mode,
					testModeIIBypass: !!payload.test_mode_ii_bypass,
					testModeUserSelfRegistration: !!payload.test_mode_user_self_registration,
					testModeDemoData: !!payload.test_mode_demo_data,
					testModeSkipTerms: !!payload.test_mode_skip_terms,
					testModeSkipPassportZkproof: !!payload.test_mode_skip_passport_zkproof,
					error: null
				});
				if (typeof sessionStorage !== 'undefined' && !payload.test_mode_ii_bypass) {
					sessionStorage.removeItem('ii_bypass');
					sessionStorage.removeItem('test_identity_index');
				}
			} catch (error) {
				console.warn('[registry] runtime flags fetch failed:', error);
				update((state) => ({
					...state,
					loading: false,
					error: error instanceof Error ? error.message : String(error)
				}));
			}
		}
	};
}

export const registryRuntimeFlags = createRegistryRuntimeFlagsStore();

export const testMode = derived(registryRuntimeFlags, ($f) => $f.testMode);
export const testModeIIBypass = derived(registryRuntimeFlags, ($f) => $f.testModeIIBypass);
export const testModeUserSelfRegistration = derived(
	registryRuntimeFlags,
	($f) => $f.testModeUserSelfRegistration
);
export const testModeDemoData = derived(registryRuntimeFlags, ($f) => $f.testModeDemoData);
export const testModeSkipTerms = derived(registryRuntimeFlags, ($f) => $f.testModeSkipTerms);
export const testModeSkipPassportZkproof = derived(
	registryRuntimeFlags,
	($f) => $f.testModeSkipPassportZkproof
);

/** Ensure runtime flags are loaded (idempotent). */
let fetchPromise = null;
export async function ensureRegistryRuntimeFlags() {
	if (!fetchPromise) {
		fetchPromise = registryRuntimeFlags.fetch().finally(() => {
			fetchPromise = null;
		});
	}
	return fetchPromise;
}

export function getRegistryRuntimeFlagsSnapshot() {
	return get(registryRuntimeFlags);
}
