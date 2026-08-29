#!/usr/bin/env node
/**
 * build: write dist/version — the GET /version asset (gos-as-a-service#39).
 *
 * dist/ is checked in and shipped as-is, so this generated file is the single
 * build step. Values are stamped from the repo checkout at build time; when a
 * value is unknown (no git, no version.txt) the field is omitted honestly.
 * Self-contained on purpose: this package must stay dependency-free so
 * `dfx deploy file_registry_frontend` stays trivial.
 */
import { execSync } from 'child_process';
import { existsSync, readFileSync, writeFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const frontendDir = join(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = join(frontendDir, '..', '..');
const distDir = join(frontendDir, 'dist');

/** @type {{canister: string, sha?: string, built_at?: string, version?: string}} */
const payload = { canister: 'file_registry_frontend' };

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

if (!existsSync(distDir)) {
	console.error('write-version-file: dist/ not found');
	process.exit(1);
}

writeFileSync(join(distDir, 'version'), JSON.stringify(payload, null, 2) + '\n', 'utf-8');
console.log(`dist/version: ${JSON.stringify(payload)}`);
