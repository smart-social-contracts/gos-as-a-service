import { browser } from '$app/environment';

/** Realm iframe handles its own II login — no separate portal session required. */
export async function load() {
	if (!browser) return {};
	return {};
}
