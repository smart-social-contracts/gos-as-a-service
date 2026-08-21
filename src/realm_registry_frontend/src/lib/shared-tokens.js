/**
 * Shared treasury tokens a realm can adopt during creation.
 * Registry keys (e.g. REALMS) are stable manifest identifiers; name/symbol
 * are resolved live from each ledger's ICRC-1 metadata when possible.
 */

import { Actor, HttpAgent } from '@dfinity/agent';
import { Principal } from '@dfinity/principal';
import { CONFIG } from '$lib/config.js';

/** @typedef {{ registryKey: string, name: string, symbol: string, description: string, ledger: string, decimals?: number, source?: string }} SharedTokenOption */

/** Static catalog — registry keys and ledger IDs per network. */
export const SHARED_TOKEN_CATALOG = [
	{
		registryKey: 'REALMS',
		name: 'REALMS Token',
		symbol: 'REALMS',
		description: 'The shared mundus-wide token, common to all realms',
		ledgers: {
			staging: 'cj65k-laaaa-aaaac-bfxqq-cai',
			demo: 'xbkkh-syaaa-aaaah-qq3ya-cai',
			test: 'nusyl-jiaaa-aaaae-qj6mq-cai'
		},
		decimals: 8
	},
	{
		registryKey: 'ckBTC',
		name: 'ckBTC',
		symbol: 'ckBTC',
		description: 'Chain-Key Bitcoin — IC-native Bitcoin twin',
		ledgers: {
			staging: 'mxzaz-hqaaa-aaaar-qaada-cai',
			demo: 'mxzaz-hqaaa-aaaar-qaada-cai',
			test: 'mxzaz-hqaaa-aaaar-qaada-cai'
		},
		decimals: 8
	},
	{
		registryKey: 'ckUSDC',
		name: 'ckUSDC',
		symbol: 'ckUSDC',
		description: 'Chain-Key USDC — IC-native USD stablecoin',
		ledgers: {
			staging: 'xevnm-gaaaa-aaaar-qafnq-cai',
			demo: 'xevnm-gaaaa-aaaar-qafnq-cai',
			test: 'xevnm-gaaaa-aaaar-qafnq-cai'
		},
		decimals: 6
	}
];

const icrc1MetadataIdl = ({ IDL }) =>
	IDL.Service({
		icrc1_name: IDL.Func([], [IDL.Text], ['query']),
		icrc1_symbol: IDL.Func([], [IDL.Text], ['query']),
		icrc1_decimals: IDL.Func([], [IDL.Nat8], ['query'])
	});

function ledgerForNetwork(entry, network) {
	const net = (network || CONFIG.deploy_queue_network || 'staging').trim().toLowerCase();
	return (entry.ledgers?.[net] || entry.ledgers?.staging || '').trim();
}

/** @param {string} value */
export function normalizeSharedRegistryKey(value) {
	const raw = (value || '').trim();
	if (!raw) return '';
	const upper = raw.toUpperCase();
	for (const entry of SHARED_TOKEN_CATALOG) {
		if (entry.registryKey === raw || entry.registryKey.toUpperCase() === upper) {
			return entry.registryKey;
		}
	}
	return raw;
}

/** @param {string} value */
export function matchesSharedRegistryKey(value) {
	return !!normalizeSharedRegistryKey(value);
}

/**
 * @param {string} network
 * @returns {Promise<SharedTokenOption[]>}
 */
export async function loadSharedTokenMetadata(network = CONFIG.deploy_queue_network) {
	const agent = new HttpAgent({ host: 'https://icp0.io' });
	await agent.fetchRootKey();

	const results = await Promise.all(
		SHARED_TOKEN_CATALOG.map(async (entry) => {
			const ledger = ledgerForNetwork(entry, network);
			const fallback = {
				registryKey: entry.registryKey,
				name: entry.name,
				symbol: entry.symbol,
				description: entry.description,
				ledger,
				decimals: entry.decimals,
				source: 'catalog'
			};
			if (!ledger) return fallback;

			try {
				const actor = Actor.createActor(icrc1MetadataIdl, {
					agent,
					canisterId: Principal.fromText(ledger),
				});
				const [name, symbol, decimals] = await Promise.all([
					actor.icrc1_name(),
					actor.icrc1_symbol(),
					actor.icrc1_decimals().catch(() => entry.decimals)
				]);
				const liveName = String(name || '').trim();
				const liveSymbol = String(symbol || '').trim();
				if (!liveSymbol) return fallback;
				return {
					...fallback,
					name: liveName || entry.name,
					symbol: liveSymbol,
					decimals: Number(decimals ?? entry.decimals),
					source: 'ledger'
				};
			} catch (err) {
				console.warn(`Could not load ICRC-1 metadata for ${entry.registryKey} (${ledger}):`, err);
				return fallback;
			}
		})
	);

	return results;
}

/** @param {string} registryKey @param {SharedTokenOption[]} tokens */
export function displaySharedToken(registryKey, tokens = []) {
	const key = normalizeSharedRegistryKey(registryKey);
	const match = tokens.find((t) => t.registryKey === key);
	if (match) {
		return { name: match.name, symbol: match.symbol, registryKey: match.registryKey };
	}
	return { name: key, symbol: key, registryKey: key };
}
