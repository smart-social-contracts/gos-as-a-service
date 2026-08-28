import assert from 'node:assert/strict';
import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import test from 'node:test';
import {
	assertCasalsFrontendLiveForBake,
	assertInstallerLiveForBake
} from '../../scripts/assert-canister-live.js';

function fakeRepo(scriptBody = '') {
	const dir = mkdtempSync(join(tmpdir(), 'assert-live-'));
	mkdirSync(join(dir, 'cli/gaas'), { recursive: true });
	writeFileSync(join(dir, 'cli/gaas/canister_liveness.py'), scriptBody, 'utf-8');
	return dir;
}

test('assertInstallerLiveForBake skips non-staging networks', () => {
	assert.doesNotThrow(() =>
		assertInstallerLiveForBake('fksuf-niaaa-aaaae-ag22q-cai', 'test', {
			run: () => {
				throw new Error('should not run');
			}
		})
	);
	assert.doesNotThrow(() => assertInstallerLiveForBake('', 'local'));
	assert.doesNotThrow(() => assertInstallerLiveForBake('', undefined));
});

test('assertInstallerLiveForBake fails closed on missing staging id', () => {
	assert.throws(
		() => assertInstallerLiveForBake('', 'staging'),
		/missing staging installer id/
	);
});

test('assertInstallerLiveForBake fails closed when the liveness check exits nonzero', () => {
	const repoRoot = fakeRepo('raise SystemExit(1)\n');
	try {
		assert.throws(
			() =>
				assertInstallerLiveForBake('fksuf-niaaa-aaaae-ag22q-cai', 'staging', {
					repoRoot,
					run: () => {
						const err = new Error('command failed');
						err.stderr = 'canister not found (IC0301)';
						throw err;
					}
				}),
			/CANISTER_ID_REALM_INSTALLER=fksuf-niaaa-aaaae-ag22q-cai/
		);
	} finally {
		rmSync(repoRoot, { recursive: true, force: true });
	}
});

test('assertInstallerLiveForBake passes when the liveness script succeeds', () => {
	const repoRoot = fakeRepo('');
	try {
		assert.doesNotThrow(() =>
			assertInstallerLiveForBake('ta6df-miaaa-aaaan-q6n4a-cai', 'staging', {
				repoRoot,
				run: () => {}
			})
		);
	} finally {
		rmSync(repoRoot, { recursive: true, force: true });
	}
});

test('assertCasalsFrontendLiveForBake skips local and empty ids', () => {
	assert.doesNotThrow(() =>
		assertCasalsFrontendLiveForBake('to4on-xyaaa-aaaan-q6n5a-cai', 'local', {
			run: () => {
				throw new Error('should not run');
			}
		})
	);
	assert.doesNotThrow(() =>
		assertCasalsFrontendLiveForBake('', 'staging', {
			run: () => {
				throw new Error('should not run');
			}
		})
	);
});

test('assertCasalsFrontendLiveForBake rejects fdr7z without a network call', () => {
	assert.throws(
		() =>
			assertCasalsFrontendLiveForBake('fdr7z-3aaaa-aaaae-ag23a-cai', 'staging', {
				run: () => {
					throw new Error('should not run');
				}
			}),
		/CANISTER_ID_CASALS_FRONTEND=fdr7z-3aaaa-aaaae-ag23a-cai/
	);
});

test('assertCasalsFrontendLiveForBake fails closed when the liveness check exits nonzero', () => {
	const repoRoot = fakeRepo('raise SystemExit(1)\n');
	try {
		assert.throws(
			() =>
				assertCasalsFrontendLiveForBake('to4on-xyaaa-aaaan-q6n5a-cai', 'staging', {
					repoRoot,
					run: () => {
						const err = new Error('command failed');
						err.stderr = 'canister not found (IC0301)';
						throw err;
					}
				}),
			/CANISTER_ID_CASALS_FRONTEND=to4on-xyaaa-aaaan-q6n5a-cai/
		);
	} finally {
		rmSync(repoRoot, { recursive: true, force: true });
	}
});

test('assertCasalsFrontendLiveForBake passes when the liveness script succeeds', () => {
	const repoRoot = fakeRepo('');
	try {
		assert.doesNotThrow(() =>
			assertCasalsFrontendLiveForBake('to4on-xyaaa-aaaan-q6n5a-cai', 'staging', {
				repoRoot,
				run: () => {}
			})
		);
	} finally {
		rmSync(repoRoot, { recursive: true, force: true });
	}
});
