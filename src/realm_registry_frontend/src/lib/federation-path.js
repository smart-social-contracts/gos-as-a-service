export function portalPath(slug, subPath = '') {
	const p = subPath.startsWith('/') ? subPath : subPath ? `/${subPath}` : '';
	return `/r/${encodeURIComponent(slug)}${p}`;
}

/** In-realm path (`/extensions/import_export`) from a portal `/r/{slug}/…` URL. */
export function embeddedPathFromPortalPathname(pathname, slug) {
	const prefix = `/r/${encodeURIComponent(slug || '')}`;
	const path = pathname || '/';
	if (path === prefix) return '/';
	if (path.startsWith(`${prefix}/`)) {
		return path.slice(prefix.length) || '/';
	}
	return path || '/';
}

const PORTAL_STICKY_QUERY = ['ti', 'skip_ii', 'test_mode'];

/**
 * Apply a realm `nav:push` onto the portal bar without dropping host-only
 * test-identity query params the iframe src often omits.
 */
export function portalHistoryHref(slug, subPath, currentHref) {
	const next = new URL(portalPath(slug, subPath || '/'), 'https://portal.invalid');
	try {
		const cur = new URL(currentHref, 'https://portal.invalid');
		for (const key of PORTAL_STICKY_QUERY) {
			if (!next.searchParams.has(key) && cur.searchParams.has(key)) {
				next.searchParams.set(key, cur.searchParams.get(key));
			}
		}
	} catch {
		// ignore malformed currentHref
	}
	return `${next.pathname}${next.search}${next.hash}`;
}
