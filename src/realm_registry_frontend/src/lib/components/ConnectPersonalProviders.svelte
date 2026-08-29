<!--
  Connect ChatGPT, Claude, or Grok via the existing Geister MCP URL.
  Built-in Geister chat is unchanged and stays available unconnected.
-->
<script>
  import { createEventDispatcher } from 'svelte';
  import { _ } from 'svelte-i18n';
  import { MCP_URL } from '$lib/geister/constants.js';
  import { PERSONAL_PROVIDERS, getPersonalProvider } from '$lib/geister/assistant-providers.js';
  import {
    loadPrefs,
    markProviderConnected,
    markProviderDisconnected,
  } from '$lib/geister/assistant-prefs.js';

  /** @type {'panel' | 'settings'} */
  export let variant = 'panel';
  /** @type {string} */
  export let initialProvider = '';
  export let showDismiss = false;

  const dispatch = createEventDispatcher();

  /** @type {string} */
  let selectedId = getPersonalProvider(initialProvider)?.id || '';
  /** @type {import('$lib/geister/assistant-providers.js').PersonalProviderId[]} */
  let connectedProviders = loadPrefs().connectedProviders;
  let copiedUrl = false;

  $: selected = getPersonalProvider(selectedId);

  function refreshConnected() {
    connectedProviders = loadPrefs().connectedProviders;
  }

  function selectProvider(id) {
    selectedId = selectedId === id ? '' : id;
  }

  function isConnected(id) {
    return connectedProviders.includes(id);
  }

  async function copyUrl() {
    try {
      await navigator.clipboard.writeText(MCP_URL);
      copiedUrl = true;
      setTimeout(() => {
        copiedUrl = false;
      }, 1800);
    } catch (err) {
      console.warn('[connect providers] clipboard failed:', err);
    }
  }

  function markConnected() {
    if (!selected) return;
    connectedProviders = markProviderConnected(selected.id);
    dispatch('connected', { id: selected.id });
  }

  function toggleConnected(id) {
    if (isConnected(id)) {
      connectedProviders = markProviderDisconnected(id);
    } else {
      selectedId = id;
      connectedProviders = markProviderConnected(id);
    }
    dispatch('connected', { id, connected: isConnected(id) });
    refreshConnected();
  }

  function dismiss() {
    dispatch('dismiss');
  }
</script>

<div class="connect-card" class:panel={variant === 'panel'} class:settings={variant === 'settings'}>
  <div class="connect-head">
    {#if variant === 'panel'}
      <h3 class="connect-title">
        {$_('assistant.connect_title', { default: 'Connect a more powerful assistant' })}
      </h3>
    {/if}
    <p class="connect-lead">
      {$_('assistant.connect_lead', {
        default:
          'ChatGPT, Claude, and Grok are stronger than this built-in helper. Connect one with the same Realms MCP link — or keep using the built-in assistant with nothing connected.',
      })}
    </p>
  </div>

  <div class="provider-row" role="group" aria-label={$_('assistant.connect_title', { default: 'Connect a more powerful assistant' })}>
    {#each PERSONAL_PROVIDERS as provider (provider.id)}
      <button
        type="button"
        class="provider-btn"
        class:active={selectedId === provider.id}
        class:connected={isConnected(provider.id)}
        on:click={() => selectProvider(provider.id)}
      >
        <span class="provider-name">{provider.label}</span>
        {#if isConnected(provider.id)}
          <span class="provider-state">{$_('assistant.connect_connected', { default: 'Connected' })}</span>
        {/if}
      </button>
    {/each}
  </div>

  {#if selected}
    <div class="connect-detail">
      <p class="connect-detail-lead">
        {$_('assistant.connect_detail', {
          values: { name: selected.label },
          default: `Add this Realms MCP URL as a custom connector in ${selected.label}. ${selected.label} opens a browser, you sign in with Internet Identity, and approve access.`,
        })}
      </p>
      <div class="url-row">
        <code class="url-value">{MCP_URL}</code>
        <button type="button" class="copy-btn" on:click={copyUrl}>
          {copiedUrl
            ? $_('assistant.copied', { default: 'Copied' })
            : $_('assistant.copy', { default: 'Copy' })}
        </button>
      </div>
      <ol class="steps">
        {#each selected.stepDefaults as step, i (i)}
          <li>
            {$_(`assistant.connect_${selected.id}_step${i + 1}`, { default: step })}
          </li>
        {/each}
      </ol>
      <div class="detail-actions">
        {#if isConnected(selected.id)}
          <button type="button" class="text-btn" on:click={() => toggleConnected(selected.id)}>
            {$_('assistant.connect_unmark', {
              values: { name: selected.label },
              default: `Unmark ${selected.label}`,
            })}
          </button>
        {:else}
          <button type="button" class="primary-btn" on:click={markConnected}>
            {$_('assistant.connect_mark', {
              values: { name: selected.label },
              default: `I've connected ${selected.label}`,
            })}
          </button>
        {/if}
        <a class="text-link" href="/my-dashboard?tab=connect">
          {$_('assistant.connect_tokens', { default: 'Pairing tokens (advanced)' })}
        </a>
      </div>
    </div>
  {/if}

  <p class="connect-footnote">
    {$_('assistant.connect_footnote', {
      default: 'The built-in assistant stays available here without connecting anything.',
    })}
  </p>

  {#if showDismiss}
    <button type="button" class="dismiss-btn" on:click={dismiss}>
      {$_('assistant.connect_not_now', { default: 'Not now — use the built-in assistant' })}
    </button>
  {/if}
</div>

<style>
  .connect-card {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 12px;
    border: 1px solid #d6d3f0;
    background: #f7f6ff;
    border-radius: 12px;
  }
  .connect-card.settings {
    padding: 0;
    border: none;
    background: transparent;
    border-radius: 0;
  }
  .connect-title {
    margin: 0 0 4px;
    font-size: 0.95rem;
    font-weight: 650;
    color: #111;
  }
  .connect-lead,
  .connect-detail-lead,
  .connect-footnote {
    margin: 0;
    font-size: 0.82rem;
    line-height: 1.45;
    color: #555;
  }
  .connect-footnote {
    color: #777;
  }
  .provider-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }
  .provider-btn {
    flex: 1 1 96px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
    padding: 10px 8px;
    border-radius: 10px;
    border: 1.5px solid #c7c3e8;
    background: #fff;
    color: #111;
    cursor: pointer;
    font: inherit;
  }
  .provider-btn:hover {
    background: #eef2ff;
  }
  .provider-btn.active {
    border-color: #111;
    background: #111;
    color: #fff;
  }
  .provider-btn.connected:not(.active) {
    border-color: #16a34a;
  }
  .provider-name {
    font-size: 0.88rem;
    font-weight: 600;
  }
  .provider-state {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    text-transform: uppercase;
    opacity: 0.8;
  }
  .connect-detail {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding-top: 2px;
  }
  .url-row {
    display: flex;
    gap: 6px;
    align-items: stretch;
  }
  .url-value {
    flex: 1;
    min-width: 0;
    background: #fff;
    border: 1px solid #ddd6fe;
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 0.72rem;
    word-break: break-all;
    color: #222;
  }
  .copy-btn,
  .primary-btn,
  .dismiss-btn {
    font: inherit;
    cursor: pointer;
    border-radius: 8px;
  }
  .copy-btn {
    flex-shrink: 0;
    border: 1px solid #c7c3e8;
    background: #fff;
    color: #333;
    padding: 0 10px;
    font-size: 0.8rem;
  }
  .steps {
    margin: 0;
    padding-left: 1.15rem;
    color: #444;
    font-size: 0.8rem;
    line-height: 1.45;
  }
  .detail-actions {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 10px;
  }
  .primary-btn {
    border: none;
    background: #111;
    color: #fff;
    padding: 7px 12px;
    font-size: 0.82rem;
    font-weight: 600;
  }
  .text-btn,
  .dismiss-btn,
  .text-link {
    background: none;
    border: none;
    padding: 0;
    color: #4338ca;
    font-size: 0.8rem;
    text-decoration: underline;
    cursor: pointer;
  }
  .dismiss-btn {
    align-self: flex-start;
    color: #666;
  }
</style>
