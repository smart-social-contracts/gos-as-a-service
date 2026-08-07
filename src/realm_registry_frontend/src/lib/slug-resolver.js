import { backend } from '$lib/canisters.js';

/** Parse GenericResult { Ok: text } | { Err: text } from registry. */
function parseGenericResult(raw) {
	if (raw && typeof raw === 'object') {
		if ('Ok' in raw && raw.Ok != null) {
			try {
				return { ok: true, data: JSON.parse(raw.Ok) };
			} catch {
				return { ok: true, data: raw.Ok };
			}
		}
		if ('Err' in raw && raw.Err != null) {
			return { ok: false, error: String(raw.Err) };
		}
	}
	return { ok: false, error: 'Invalid registry response' };
}

/**
 * Consensus-backed slug resolution (@update). Cached per session in memory.
 */
const _cache = new Map();

export async function resolveSlug(slug, { force = false } = {}) {
	const key = (slug || '').trim().toLowerCase();
	if (!key) {
		throw new Error('Slug is required');
	}
	if (!force && _cache.has(key)) {
		return _cache.get(key);
	}
	const raw = await backend.resolve_slug(key);
	const parsed = parseGenericResult(raw);
	if (!parsed.ok) {
		throw new Error(parsed.error || 'resolve_slug failed');
	}
	if (!parsed.data?.success) {
		throw new Error(parsed.data?.error || `Unknown slug '${key}'`);
	}
	_cache.set(key, parsed.data);
	return parsed.data;
}

export function clearSlugCache() {
	_cache.clear();
}
