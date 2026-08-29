import assert from 'node:assert/strict';
import test from 'node:test';
import {
  defaultPrefs,
  dismissConnectSuggestion,
  loadPrefs,
  markProviderConnected,
  markProviderDisconnected,
  savePrefs,
} from './assistant-prefs.js';

function memoryStorage() {
  /** @type {Record<string, string>} */
  const data = {};
  return {
    getItem(key) {
      return Object.prototype.hasOwnProperty.call(data, key) ? data[key] : null;
    },
    setItem(key, value) {
      data[key] = String(value);
    },
    removeItem(key) {
      delete data[key];
    },
  };
}

test('prefs persist connected ChatGPT / Claude / Grok and ignore Cloud', () => {
  globalThis.localStorage = memoryStorage();
  assert.deepEqual(loadPrefs(), defaultPrefs());
  savePrefs({
    connectedProviders: ['claude', 'cloud', 'chatgpt'],
    dismissConnectSuggestion: true,
  });
  const prefs = loadPrefs();
  assert.deepEqual(prefs.connectedProviders, ['claude', 'chatgpt']);
  assert.equal(prefs.dismissConnectSuggestion, true);
  assert.equal(prefs.showSuggestions, true);
});

test('mark connected / disconnected updates only personal providers', () => {
  globalThis.localStorage = memoryStorage();
  assert.deepEqual(markProviderConnected('claude'), ['claude']);
  assert.deepEqual(markProviderConnected('grok'), ['claude', 'grok']);
  assert.deepEqual(markProviderConnected('claude'), ['claude', 'grok']);
  assert.deepEqual(markProviderDisconnected('claude'), ['grok']);
  dismissConnectSuggestion();
  assert.equal(loadPrefs().dismissConnectSuggestion, true);
});
