/**
 * Read a realm backend the same way whatever GOS runs it: through GGG (`ggg.did`) when the
 * canister implements it, through the pre-GGG Realms GOS methods otherwise.
 *
 * Discovery is ICRC-10: a canister that lists "GGG" in `icrc10_supported_standards` answers the
 * `ggg_` methods. Realms deployed before GGG have no such method, so the call fails and the
 * legacy methods are used.
 *
 * The IDL declares only what the portal reads. Candid lets a caller declare fewer record fields
 * than the canister sends, so `ggg.did` can add fields without breaking this file.
 *
 * Imports are static: delegation.js uses this for the iframe auth bridge (see its note).
 */
import { Actor, HttpAgent } from '@dfinity/agent';
import { Principal } from '@dfinity/principal';

const STAGES = ['Setup', 'Alpha', 'Beta', 'Production', 'Deprecation', 'Terminated'];

/** The part of ggg.did the portal reads, plus the pre-GGG methods older realms answer. */
export const idlFactory = ({ IDL }) => {
	const RealmStatus = IDL.Variant(Object.fromEntries(STAGES.map((s) => [s, IDL.Null])));
	const Realm = IDL.Record({
		name: IDL.Text,
		status: RealmStatus,
		logo_url: IDL.Opt(IDL.Text)
	});
	const GggError = IDL.Variant({
		NotFound: IDL.Null,
		Unauthenticated: IDL.Null,
		Forbidden: IDL.Record({ permission: IDL.Opt(IDL.Text), message: IDL.Text }),
		InvalidArgument: IDL.Text,
		Conflict: IDL.Text,
		Unavailable: IDL.Text,
		GenericError: IDL.Record({ error_code: IDL.Nat, message: IDL.Text })
	});
	const JoinTargets = IDL.Record({
		default: IDL.Opt(IDL.Text),
		targets: IDL.Vec(IDL.Text),
		mode: IDL.Opt(IDL.Text)
	});
	return IDL.Service({
		icrc10_supported_standards: IDL.Func(
			[],
			[IDL.Vec(IDL.Record({ name: IDL.Text, url: IDL.Text }))],
			['query']
		),
		ggg_realm_info: IDL.Func([], [Realm], ['query']),
		ggg_join_targets: IDL.Func([], [IDL.Variant({ Ok: JoinTargets, Err: GggError })], ['query']),
		get_runtime_flags: IDL.Func([], [IDL.Text], ['query']),
		get_join_targets: IDL.Func([], [IDL.Text], ['query'])
	});
};

function isLocalDevelopment() {
	if (typeof window === 'undefined') return false;
	const host = window.location.hostname;
	return host.includes('localhost') || host.includes('127.0.0.1');
}

async function createRealmActor(canisterId) {
	const local = isLocalDevelopment();
	const agent = new HttpAgent({ host: local ? undefined : 'https://icp0.io' });
	if (local) {
		try {
			await agent.fetchRootKey();
		} catch {
			/* non-fatal */
		}
	}
	return Actor.createActor(idlFactory, { agent, canisterId: Principal.fromText(canisterId) });
}

const actors = new Map();
const gggSupport = new Map();

function actorFor(canisterId, createActor) {
	if (createActor) return createActor(canisterId);
	if (!actors.has(canisterId)) actors.set(canisterId, createRealmActor(canisterId));
	return actors.get(canisterId);
}

/** Whether the canister lists GGG among its ICRC-10 standards. Asked once per canister. */
export function supportsGgg(actor, canisterId) {
	if (!gggSupport.has(canisterId)) {
		gggSupport.set(
			canisterId,
			actor
				.icrc10_supported_standards()
				.then((standards) => standards.some((s) => s.name === 'GGG'))
				.catch(() => false)
		);
	}
	return gggSupport.get(canisterId);
}

/** Forget what was learned about canisters (tests, or after a realm upgrade). */
export function resetRealmGosClient() {
	actors.clear();
	gggSupport.clear();
}

/**
 * The realm's lifecycle stage (lower case, e.g. "alpha") and logo URL, or null when the canister
 * cannot be read.
 * @param {string} canisterId
 * @param {{ createActor?: (id: string) => any }} [options]
 * @returns {Promise<{ stage: string, logoUrl: string } | null>}
 */
export async function fetchRealmInfo(canisterId, { createActor } = {}) {
	const cid = (canisterId || '').trim();
	if (!cid) return null;
	try {
		const actor = await actorFor(cid, createActor);
		if (await supportsGgg(actor, cid)) {
			const realm = await actor.ggg_realm_info();
			return {
				stage: Object.keys(realm.status)[0].toLowerCase(),
				logoUrl: (realm.logo_url[0] || '').trim()
			};
		}
		const flags = JSON.parse(await actor.get_runtime_flags());
		if (!flags?.success) return null;
		return {
			stage: (flags.realm_stage || 'alpha').trim().toLowerCase(),
			logoUrl: String(flags.logo_url || flags.realm_logo || '').trim()
		};
	} catch (err) {
		const message = err?.message || String(err);
		if (!/not found|IC0301/i.test(message)) console.warn('[realm] could not read', cid, err);
		return null;
	}
}

/**
 * The quarter canisters a realm may route a join to, besides itself. Empty when it has none or
 * cannot say.
 * @param {string} canisterId the realm's capital backend
 * @param {{ createActor?: (id: string) => any }} [options]
 * @returns {Promise<string[]>}
 */
export async function fetchJoinTargets(canisterId, { createActor } = {}) {
	const cid = (canisterId || '').trim();
	if (!cid) return [];
	try {
		const actor = await actorFor(cid, createActor);
		if (await supportsGgg(actor, cid)) {
			const reply = await actor.ggg_join_targets();
			if ('Err' in reply) throw new Error(`ggg_join_targets: ${Object.keys(reply.Err)[0]}`);
			return reply.Ok.targets.map((id) => id.trim()).filter(Boolean);
		}
		const parsed = JSON.parse(await actor.get_join_targets());
		return (parsed?.quarters || []).map((q) => (q?.canister_id || '').trim()).filter(Boolean);
	} catch (err) {
		console.warn('[realm] could not read join targets of', cid, err);
		return [];
	}
}
