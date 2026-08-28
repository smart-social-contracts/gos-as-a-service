import { execFileSync } from 'child_process';
import { existsSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

function defaultRepoRoot() {
	return join(dirname(fileURLToPath(import.meta.url)), '../../..');
}

function livenessScript(repoRoot) {
	return join(repoRoot, 'cli/gaas/canister_liveness.py');
}

/**
 * Fail closed before a persistent-network bake injects CANISTER_ID_REALM_INSTALLER.
 * Local / unset DFX_NETWORK skips the IC lookup.
 *
 * @param {string} canisterId
 * @param {string | undefined} network
 * @param {{ repoRoot?: string, run?: (cmd: string, args: string[]) => void }} [options]
 */
export function assertInstallerLiveForBake(canisterId, network, options = {}) {
	const net = (network || '').trim();
	// Staging SPA bake is the recurrence that injected fksuf. Other networks
	// keep their existing IDs; do not block test/demo/ic builds here.
	if (net !== 'staging') {
		return;
	}

	const id = (canisterId || '').trim();
	if (!id) {
		throw new Error(
			`refusing to bake CANISTER_ID_REALM_INSTALLER: missing ${net} installer id`
		);
	}

	const repoRoot = options.repoRoot || defaultRepoRoot();
	const script = livenessScript(repoRoot);
	if (!existsSync(script)) {
		throw new Error(
			`refusing to bake CANISTER_ID_REALM_INSTALLER=${id}: missing ${script}`
		);
	}

	const run =
		options.run ||
		((cmd, args) => {
			execFileSync(cmd, args, { stdio: 'pipe', encoding: 'utf-8' });
		});

	try {
		run('python3', [script, id, 'realm_installer']);
	} catch (err) {
		const detail = [err.stderr, err.stdout, err.message].filter(Boolean).join('\n');
		throw new Error(
			`refusing to bake CANISTER_ID_REALM_INSTALLER=${id}: canister not found (IC0301). ${detail}`.trim()
		);
	}
}

const KNOWN_DEAD_PREFIXES = new Set(['fdr7z', 'jj2e5', 'rbuam', 'fksuf', 'hznxf', 'h6mrr']);

/**
 * Fail closed before a persistent-network bake injects CANISTER_ID_CASALS_FRONTEND.
 * Unset is allowed (the portal hides the Architecture link). A dead ID is not.
 *
 * @param {string} canisterId
 * @param {string | undefined} network
 * @param {{ repoRoot?: string, run?: (cmd: string, args: string[]) => void }} [options]
 */
export function assertCasalsFrontendLiveForBake(canisterId, network, options = {}) {
	const net = (network || '').trim();
	if (!net || net === 'local' || net === 'localhost') {
		return;
	}

	const id = (canisterId || '').trim();
	if (!id) {
		return;
	}

	const prefix = id.split('-')[0];
	if (KNOWN_DEAD_PREFIXES.has(prefix)) {
		throw new Error(
			`refusing to bake CANISTER_ID_CASALS_FRONTEND=${id}: known-dead canister`
		);
	}

	const repoRoot = options.repoRoot || defaultRepoRoot();
	const script = livenessScript(repoRoot);
	if (!existsSync(script)) {
		throw new Error(
			`refusing to bake CANISTER_ID_CASALS_FRONTEND=${id}: missing ${script}`
		);
	}

	const run =
		options.run ||
		((cmd, args) => {
			execFileSync(cmd, args, { stdio: 'pipe', encoding: 'utf-8' });
		});

	try {
		run('python3', [script, id, 'casals_frontend']);
	} catch (err) {
		const detail = [err.stderr, err.stdout, err.message].filter(Boolean).join('\n');
		throw new Error(
			`refusing to bake CANISTER_ID_CASALS_FRONTEND=${id}: canister not found (IC0301). ${detail}`.trim()
		);
	}
}
