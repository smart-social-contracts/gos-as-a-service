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
	if (data && typeof data === 'object') {
		const creatable = data.creatable_subnets ?? data.creatableSubnets;
		if (Array.isArray(creatable) && creatable.length > 0) return creatable;
		const subnets = data.subnets;
		if (Array.isArray(subnets)) return subnets;
	}
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
