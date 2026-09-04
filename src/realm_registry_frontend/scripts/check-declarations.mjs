#!/usr/bin/env node
/**
 * Verify the committed candid declarations this SPA imports are present.
 *
 * vite.config.js aliases `declarations` at src/declarations, which is committed,
 * so the build needs no dfx. This used to run `dfx generate`, which broke
 * unattended deploys on hosts that wrap dfx (and needlessly rebuilt files that
 * are already in git). Regenerate with `dfx generate <canister>` and commit the
 * result when a backend's .did changes.
 */
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const declarations = resolve(here, '../../declarations');
const required = ['realm_registry_backend', 'realm_installer', 'casals_backend'];

const missing = required.filter(
	(canister) => !existsSync(join(declarations, canister, 'index.js'))
);

if (missing.length > 0) {
	console.error(
		`[check-declarations] missing declarations for: ${missing.join(', ')}\n` +
			`Expected them under ${declarations}.\n` +
			`Run \`dfx generate <canister>\` for each and commit src/declarations.`
	);
	process.exit(1);
}

console.log(`[check-declarations] ${required.length} canister declarations present`);
