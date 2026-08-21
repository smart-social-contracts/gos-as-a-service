/** Subnet geography from the public IC Dashboard API (ic-api.internetcomputer.org). */

const IC_API = 'https://ic-api.internetcomputer.org';

export const GEO_REGION_ORDER = ['USA', 'EU', 'MidEast', 'APAC', 'Other'];

export const GEO_REGION_LABELS = {
	USA: 'Americas',
	EU: 'Europe',
	MidEast: 'Mid East',
	APAC: 'APAC',
	Other: 'Other',
};

const geoCache = new Map();

const regionNames =
	typeof Intl !== 'undefined' ? new Intl.DisplayNames(['en'], { type: 'region' }) : null;

const USA_CODES = new Set(['US', 'CA', 'MX', 'PR', 'GU', 'VI']);
const EU_CODES = new Set([
	'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR', 'DE', 'GR', 'HU', 'IE', 'IT',
	'LV', 'LT', 'LU', 'MT', 'NL', 'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE', 'GB', 'CH', 'NO',
	'IS', 'LI', 'IM', 'JE', 'GG', 'AD', 'MC', 'SM', 'VA',
]);
const MIDEAST_CODES = new Set([
	'AE', 'SA', 'IL', 'TR', 'EG', 'JO', 'LB', 'QA', 'BH', 'KW', 'OM', 'IQ', 'IR', 'PS', 'YE',
	'SY', 'CY',
]);
const APAC_CODES = new Set([
	'JP', 'KR', 'CN', 'IN', 'AU', 'NZ', 'SG', 'HK', 'TW', 'TH', 'MY', 'ID', 'PH', 'VN', 'KZ',
	'UZ', 'PK', 'BD', 'LK', 'NP', 'MM', 'KH', 'LA', 'MN', 'MO', 'BN', 'FJ', 'PG', 'NC',
]);

export function classifyCountry(code) {
	const c = (code || '').toUpperCase();
	if (!c) return 'Other';
	if (USA_CODES.has(c)) return 'USA';
	if (EU_CODES.has(c)) return 'EU';
	if (MIDEAST_CODES.has(c)) return 'MidEast';
	if (APAC_CODES.has(c)) return 'APAC';
	return 'Other';
}

/** Parse "Europe,RO,Bucharest" → "RO". */
export function countryCodeFromRegion(region) {
	const parts = (region || '').split(',').map((p) => p.trim());
	const code = parts.length >= 2 ? parts[1] : '';
	return /^[A-Za-z]{2}$/.test(code) ? code.toUpperCase() : '';
}

/** ISO 3166-1 alpha-2 → flag emoji (e.g. "RO" → 🇷🇴). */
export function countryCodeToFlag(code) {
	const c = (code || '').toUpperCase();
	if (c.length !== 2) return '';
	return String.fromCodePoint(...[...c].map((ch) => 0x1f1e6 - 65 + ch.charCodeAt(0)));
}

function countryName(code) {
	try {
		return regionNames?.of(code) ?? code;
	} catch {
		return code;
	}
}

function regionRank(region) {
	return GEO_REGION_ORDER.indexOf(region);
}

export function orderCountryCodes(codes) {
	const unique = [...new Set(codes.map((c) => c.toUpperCase()).filter(Boolean))];
	const entries = unique.map((code) => ({
		code,
		flag: countryCodeToFlag(code),
		name: countryName(code),
		region: classifyCountry(code),
	}));
	entries.sort((a, b) => {
		const dr = regionRank(a.region) - regionRank(b.region);
		if (dr !== 0) return dr;
		return a.name.localeCompare(b.name);
	});
	return entries;
}

function buildGeo(subnetId, payload) {
	const codes = new Set();
	const dcs = [];
	for (const dc of payload.data_centers ?? []) {
		const code = countryCodeFromRegion(dc.region ?? '');
		if (code) codes.add(code);
		const label = [dc.name, dc.region?.split(',').slice(2).join(', ')].filter(Boolean).join(', ');
		if (label) dcs.push(label);
	}
	const orderedCountries = orderCountryCodes([...codes]);
	return {
		subnetId,
		countryCodes: orderedCountries.map((c) => c.code),
		flags: orderedCountries.map((c) => c.flag),
		countryNames: orderedCountries.map((c) => c.name),
		orderedCountries,
		dataCenters: dcs,
		subnetType: payload.subnet_type,
		nodeCount: payload.total_nodes != null ? Number(payload.total_nodes) : undefined,
		subnetAuthorization: payload.subnet_authorization,
	};
}

export async function getSubnetGeo(subnetId) {
	const id = (subnetId || '').trim();
	if (!id) return null;
	const hit = geoCache.get(id);
	if (hit) return hit;

	const res = await fetch(`${IC_API}/api/v4/subnets/${encodeURIComponent(id)}`);
	if (!res.ok) return null;
	const payload = await res.json();
	const geo = buildGeo(id, payload);
	geoCache.set(id, geo);
	return geo;
}

export async function warmSubnetGeoCache(subnetIds) {
	const pending = [...new Set(subnetIds.map((s) => s.trim()).filter(Boolean))].filter(
		(id) => !geoCache.has(id),
	);
	await Promise.all(pending.map((id) => getSubnetGeo(id)));
}

export function subnetGeoTitle(geo) {
	if (!geo) return '';
	const parts = [];
	if (geo.orderedCountries.length) {
		const byRegion = new Map();
		for (const c of geo.orderedCountries) {
			if (!byRegion.has(c.region)) byRegion.set(c.region, []);
			byRegion.get(c.region).push(c.name);
		}
		parts.push(
			GEO_REGION_ORDER.filter((r) => byRegion.has(r))
				.map((r) => `${GEO_REGION_LABELS[r]}: ${byRegion.get(r).join(', ')}`)
				.join(' · '),
		);
	}
	if (geo.nodeCount != null) parts.push(`${geo.nodeCount} nodes`);
	if (geo.subnetType) parts.push(geo.subnetType);
	return parts.join(' · ');
}

export function regionFlagGroups(orderedCountries) {
	const groups = [];
	for (const region of GEO_REGION_ORDER) {
		const countries = (orderedCountries || []).filter((c) => c.region === region);
		if (countries.length) {
			groups.push({ region, label: GEO_REGION_LABELS[region], countries });
		}
	}
	return groups;
}

export function subnetTypeLabel(type) {
	if (!type) return '';
	return String(type)
		.replace(/_/g, ' ')
		.toLowerCase()
		.replace(/\b\w/g, (c) => c.toUpperCase());
}

export function subnetShortLabel(id) {
	return (id || '').trim().slice(0, 5);
}

export function shortSubnetId(id) {
	const s = (id || '').trim();
	if (s.length <= 13) return s;
	return `${s.slice(0, 5)}…${s.slice(-5)}`;
}
