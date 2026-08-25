import { browser } from '$app/environment';
import { resolveSlug } from '$lib/slug-resolver.js';
import { readSplashBrandHint, writeSplashBrandHint } from '$lib/realm-utils.js';

/** Realm iframe handles its own II login — no separate portal session required. */
export async function load({ params }) {
	if (!browser) return {};
	const slug = params.slug;
	const splashHint = readSplashBrandHint(slug);
	if (splashHint?.frontendCanisterId) {
		return { splashHint };
	}
	try {
		const resolved = await resolveSlug(slug);
		const hint = {
			frontendCanisterId: String(resolved.frontend_canister_id || '').trim(),
			configuredLogoUrl: '',
		};
		writeSplashBrandHint(slug, hint);
		return { resolved, splashHint: hint };
	} catch (err) {
		return {
			resolveError: err instanceof Error ? err.message : String(err),
		};
	}
}
