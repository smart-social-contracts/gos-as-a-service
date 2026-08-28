function parseSubnetId(entry) {
	if (typeof entry === 'string') return entry.trim();
	if (entry && typeof entry === 'object') {
		const id =
			entry.id ?? entry.subnet_id ?? entry.subnetId ?? entry.principal ?? entry.subnet;
		if (typeof id === 'string') return id.trim();
	}
	return '';
}

function subnetEntriesFromPayload(data) {
	if (Array.isArray(data)) return data;
	if (!data || typeof data !== 'object') return [];
	if (data.ok === false) return [];
	if (Array.isArray(data.subnets)) return data.subnets;
	return [];
}

export function parseSubnetList(raw) {
	let data = raw;
	if (typeof raw === 'string') {
		try {
			data = JSON.parse(raw);
		} catch {
			return [];
		}
	}
	return [...new Set(subnetEntriesFromPayload(data).map(parseSubnetId).filter(Boolean))];
}

export function requireCasalsBackendCanisterId(canisterId) {
	const id = typeof canisterId === 'string' ? canisterId.trim() : '';
	if (!id) {
		throw new Error('Could not load available subnets');
	}
	return id;
}
