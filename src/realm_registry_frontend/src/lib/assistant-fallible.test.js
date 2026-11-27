import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const locale = (name) => JSON.parse(readFileSync(join(here, `i18n/locales/${name}.json`), 'utf8')).assistant;
const panel = readFileSync(join(here, 'components/RegistryAssistant.svelte'), 'utf8');

// The CLFO's ruling for the demo: the panel's "AI Assistant" label says it is an AI; this line says it can be wrong.
test('the fallibility line is the approved wording in English and Spanish', () => {
	assert.equal(locale('en').answers_can_be_wrong, 'Answers can be wrong.');
	assert.equal(locale('es').answers_can_be_wrong, 'Las respuestas pueden ser erróneas.');
});

test('the panel is labelled as an AI in English and Spanish', () => {
	assert.equal(locale('en').title, 'AI Assistant');
	assert.equal(locale('es').title, 'Asistente de IA');
	assert.equal(locale('es').toggle, 'Asistente de IA');
});

test('the line shows signed in or not, whatever assistant_experimental_notice says', () => {
	const start = panel.indexOf('{#if experimentalNoticeOn}');
	const gated = panel.slice(start, panel.indexOf('{/if}', start));
	assert.doesNotMatch(gated, /answers_can_be_wrong/);
	assert.match(
		panel,
		/<p class="sign-in-note">[^\n]*<\/p>\s*\{\/if\}\s*<!--[^>]*-->\s*<p class="assistant-fallible">\{\$_\('assistant\.answers_can_be_wrong'/,
	);
});
