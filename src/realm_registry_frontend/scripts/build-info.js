/**
 * Build provenance for GET /version (gos-as-a-service#39).
 *
 * Every platform canister serves the same /version contract so the
 * "estado de los entornos" command can poll fast HTTP GETs. The values are
 * stamped at build time from the repo checkout — never guessed at query
 * time. When a value is unknown at build time (no git, no version.txt),
 * the field is omitted honestly.
 */
import { execSync } from 'child_process';
import { readFileSync, writeFileSync } from 'fs';
import { join } from 'path';

/**
 * Build-time values injected into the bundle via Vite defines.
 * Reads version.txt (written by release.yml) and the git HEAD.
 *
 * @param {string} repoRoot absolute path to the repo root
 */
export function getBuildTimeValues(repoRoot) {
	let version = 'dev';
	let commitHash = 'local';
	const buildTime = new Date().toISOString().replace('T', ' ').substring(0, 19);

	try {
		version = readFileSync(join(repoRoot, 'version.txt'), 'utf-8').trim();
	} catch (e) {
		// version.txt not found, use default
	}

	try {
		commitHash = execSync('git rev-parse --short HEAD', {
			encoding: 'utf-8',
			cwd: repoRoot
		}).trim();
	} catch (e) {
		// git not available, use default
	}

	return { version, commitHash, buildTime };
}

/**
 * The /version JSON payload for an asset canister.
 *
 * @param {string} canisterName static canister name (always present)
 * @param {string} repoRoot absolute path to the repo root
 * @returns {{canister: string, sha?: string, built_at?: string, version?: string}}
 */
export function buildVersionPayload(canisterName, repoRoot) {
	/** @type {{canister: string, sha?: string, built_at?: string, version?: string}} */
	const payload = { canister: canisterName };

	try {
		const sha = execSync('git rev-parse --short HEAD', {
			encoding: 'utf-8',
			cwd: repoRoot
		}).trim();
		if (sha) payload.sha = sha;
	} catch (e) {
		// git unavailable at build time — omit sha honestly
	}

	// The build clock is the build stamp: always known at build time.
	payload.built_at = new Date().toISOString().replace(/\.\d{3}Z$/, 'Z');

	try {
		const version = readFileSync(join(repoRoot, 'version.txt'), 'utf-8').trim();
		if (version) payload.version = version;
	} catch (e) {
		// no release tag at build time — omit version honestly
	}

	return payload;
}

/**
 * Write the /version asset (extension-less JSON file) into a dist directory.
 *
 * @param {string} distDir absolute path to the built asset source dir
 * @param {string} canisterName static canister name
 * @param {string} repoRoot absolute path to the repo root
 */
export function writeVersionFile(distDir, canisterName, repoRoot) {
	const payload = buildVersionPayload(canisterName, repoRoot);
	writeFileSync(join(distDir, 'version'), JSON.stringify(payload, null, 2) + '\n', 'utf-8');
	return payload;
}
