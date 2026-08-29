import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import {
	buildVersionPayload,
	getBuildTimeValues,
	writeVersionFile
} from '../../scripts/build-info.js';

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), '..', '..', '..', '..');

const ISO_Z = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/;

test('buildVersionPayload always includes canister and ISO-8601 UTC built_at', () => {
	const payload = buildVersionPayload('realm_registry_frontend', repoRoot);
	assert.equal(payload.canister, 'realm_registry_frontend');
	assert.match(payload.built_at, ISO_Z);
	// In a git checkout the sha is stamped; outside git it is omitted honestly.
	if (payload.sha !== undefined) {
		assert.match(payload.sha, /^[0-9a-f]{7,}$/);
	}
});

test('buildVersionPayload omits sha and version honestly when unknown', () => {
	const fakeRoot = mkdtempSync(join(tmpdir(), 'build-info-'));
	try {
		const payload = buildVersionPayload('file_registry_frontend', fakeRoot);
		assert.equal(payload.canister, 'file_registry_frontend');
		assert.match(payload.built_at, ISO_Z);
		assert.equal(payload.sha, undefined);
		assert.equal(payload.version, undefined);
	} finally {
		rmSync(fakeRoot, { recursive: true, force: true });
	}
});

test('writeVersionFile writes the extension-less version asset', () => {
	const dist = mkdtempSync(join(tmpdir(), 'build-info-dist-'));
	try {
		const payload = writeVersionFile(dist, 'realm_registry_frontend', dist);
		const raw = readFileSync(join(dist, 'version'), 'utf-8');
		assert.deepEqual(JSON.parse(raw), payload);
	} finally {
		rmSync(dist, { recursive: true, force: true });
	}
});

test('getBuildTimeValues keeps the existing vite define behaviour', () => {
	const values = getBuildTimeValues(repoRoot);
	// No version.txt in a dev checkout: honest 'dev' default.
	assert.equal(values.version, 'dev');
	assert.match(values.buildTime, /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/);
	assert.ok(values.commitHash.length > 0);
});
