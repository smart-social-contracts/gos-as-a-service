import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
	ASSISTANT_EXPERIMENTAL_NOTICE,
	ASSISTANT_EXPERIMENTAL_PROMPT_RULES,
	isAssistantExperimentalNoticeEnabled,
} from './assistant-experimental-flag.js';

const here = dirname(fileURLToPath(import.meta.url));
const en = JSON.parse(readFileSync(join(here, 'i18n/locales/en.json'), 'utf8'));
const panel = readFileSync(join(here, 'components/RegistryAssistant.svelte'), 'utf8');

test('experimental notice copy is the go-live string', () => {
	assert.equal(
		ASSISTANT_EXPERIMENTAL_NOTICE,
		'Experimental. Not official. Not legal advice. Do not enter personal data. Chats may be stored.',
	);
	assert.equal(en.assistant.experimental_notice, ASSISTANT_EXPERIMENTAL_NOTICE);
	assert.match(ASSISTANT_EXPERIMENTAL_PROMPT_RULES, /unofficial/);
	assert.match(ASSISTANT_EXPERIMENTAL_PROMPT_RULES, /lawyer/);
	assert.match(ASSISTANT_EXPERIMENTAL_PROMPT_RULES, /written notice \/ codex/);
	assert.doesNotMatch(ASSISTANT_EXPERIMENTAL_NOTICE, /I agree to terms/i);
	assert.doesNotMatch(ASSISTANT_EXPERIMENTAL_PROMPT_RULES, /I agree to terms/i);
});

test('assistant_experimental_notice defaults ON for staging and demo', () => {
	assert.equal(isAssistantExperimentalNoticeEnabled({ network: 'staging' }), true);
	assert.equal(isAssistantExperimentalNoticeEnabled({ network: 'demo' }), true);
	assert.equal(isAssistantExperimentalNoticeEnabled({ network: 'Staging' }), true);
});

test('assistant_experimental_notice defaults OFF for test and production', () => {
	assert.equal(isAssistantExperimentalNoticeEnabled({ network: 'test' }), false);
	assert.equal(isAssistantExperimentalNoticeEnabled({ network: 'ic' }), false);
	assert.equal(isAssistantExperimentalNoticeEnabled({ network: '' }), false);
});

test('explicit flag overrides the network default', () => {
	assert.equal(
		isAssistantExperimentalNoticeEnabled({
			assistantExperimentalNotice: false,
			network: 'staging',
		}),
		false,
	);
	assert.equal(
		isAssistantExperimentalNoticeEnabled({
			assistantExperimentalNotice: true,
			network: 'test',
		}),
		true,
	);
});

test('registry assistant chrome shows the notice without History or Settings', () => {
	assert.match(panel, /isAssistantExperimentalNoticeEnabled/);
	assert.match(panel, /assistant-experimental-notice/);
	assert.match(panel, /ASSISTANT_EXPERIMENTAL_PROMPT_RULES/);
	assert.doesNotMatch(panel, /I agree to terms/i);
	assert.doesNotMatch(panel, /assistant-empty/);
});
