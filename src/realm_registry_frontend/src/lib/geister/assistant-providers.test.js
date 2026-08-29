import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  PERSONAL_PROVIDER_IDS,
  PERSONAL_PROVIDERS,
  getPersonalProvider,
  isPersonalProviderId,
  normalizeConnectedProviders,
  providerLabelMentionsCloud,
  shouldOfferPersonalConnect,
} from './assistant-providers.js';

const en = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), '../i18n/locales/en.json'), 'utf8'),
);

test('personal providers are exactly ChatGPT, Claude, and Grok', () => {
  assert.deepEqual([...PERSONAL_PROVIDER_IDS], ['chatgpt', 'claude', 'grok']);
  assert.deepEqual(
    PERSONAL_PROVIDERS.map((p) => p.id),
    ['chatgpt', 'claude', 'grok'],
  );
  assert.deepEqual(
    PERSONAL_PROVIDERS.map((p) => p.label),
    ['ChatGPT', 'Claude', 'Grok'],
  );
});

test('copy never calls Claude Cloud', () => {
  for (const provider of PERSONAL_PROVIDERS) {
    assert.equal(providerLabelMentionsCloud(provider.label), false);
    assert.match(provider.label, /Claude|ChatGPT|Grok/);
    assert.doesNotMatch(provider.label, /cloud/i);
    for (const step of provider.stepDefaults) {
      assert.doesNotMatch(step, /\bcloud\b/i);
      assert.doesNotMatch(step, /cursor cloud/i);
    }
  }
  assert.equal(getPersonalProvider('claude')?.label, 'Claude');
});

test('unknown ids are rejected', () => {
  assert.equal(isPersonalProviderId('claude'), true);
  assert.equal(isPersonalProviderId('cloud'), false);
  assert.equal(isPersonalProviderId('gemini'), false);
  assert.equal(getPersonalProvider('cloud'), null);
  assert.deepEqual(normalizeConnectedProviders(['claude', 'cloud', 'grok', 'claude']), [
    'claude',
    'grok',
  ]);
});

test('first-open offers connect until a provider is connected or dismissed', () => {
  assert.equal(shouldOfferPersonalConnect({}), true);
  assert.equal(shouldOfferPersonalConnect({ connectedProviders: [], dismissConnectSuggestion: false }), true);
  assert.equal(shouldOfferPersonalConnect({ connectedProviders: ['claude'] }), false);
  assert.equal(shouldOfferPersonalConnect({ dismissConnectSuggestion: true }), false);
  assert.equal(shouldOfferPersonalConnect({ connectedProviders: ['cloud'] }), true);
});

test('registry assistant keeps built-in empty copy, FAB, and personal connect offer', () => {
  const here = dirname(fileURLToPath(import.meta.url));
  const panel = readFileSync(join(here, '../components/RegistryAssistant.svelte'), 'utf8');
  const settings = readFileSync(join(here, '../../routes/assistant/settings/+page.svelte'), 'utf8');
  assert.match(panel, /ConnectPersonalProviders/);
  assert.match(panel, /assistant-fab/);
  assert.match(panel, /Ask me anything about the realms in the registry/);
  assert.match(panel, /class="assistant-input"/);
  assert.doesNotMatch(panel, /\bCloud\b/);
  assert.match(settings, /ConnectPersonalProviders/);
  assert.match(settings, /personal-assistants/);
});

test('English copy names ChatGPT, Claude, and Grok and never says Cloud', () => {
  const assistant = en.assistant;
  const dashboard = en.dashboard;
  const blob = [
    assistant.connect_title,
    assistant.connect_lead,
    assistant.connect_section,
    assistant.connect_section_desc,
    assistant.connect_chatgpt_step1,
    assistant.connect_claude_step1,
    assistant.connect_grok_step1,
    dashboard.connect_tab,
  ].join('\n');
  assert.match(blob, /ChatGPT/);
  assert.match(blob, /Claude/);
  assert.match(blob, /Grok/);
  assert.doesNotMatch(blob, /\bCloud\b/);
  assert.match(assistant.connect_lead, /built-in assistant/);
});
