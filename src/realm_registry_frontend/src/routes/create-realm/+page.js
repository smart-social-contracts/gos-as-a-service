import { redirect } from '@sveltejs/kit';

// Do not prerender a static meta-refresh — that would drop ?draft= and other params.
export const prerender = false;

/** Preserve drafts and other query params when the old wizard URL is opened. */
export function load({ url }) {
	throw redirect(308, `/deploy-gos${url.search}`);
}
