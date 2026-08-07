<script>
  import { onMount } from 'svelte';
  import { _ } from 'svelte-i18n';
  import { loadPrefs, savePrefs } from '$lib/geister/assistant-prefs.js';
  import {
    fetchConversations,
    deleteConversation,
    clearAllHistory,
    formatConversationDate,
  } from '$lib/geister/conversations.js';
  import { fetchAssistants, checkApiStatus } from '$lib/geister/personas.js';

  /** @type {{ id: string, name: string, emoji?: string, description?: string }[]} */
  let availableAssistants = [];
  let isLoadingAssistants = false;
  let prefDefaultAssistant = '';
  let prefShowSuggestions = true;
  let prefSharePageContext = true;

  let userPrincipal = '';
  /** @type {import('$lib/geister/conversations.js').Conversation[]} */
  let conversations = [];
  let isLoadingHistory = false;
  let clearingHistory = false;
  let historyCleared = false;

  /** @type {'unknown' | 'online' | 'offline'} */
  let apiStatus = 'unknown';

  function persistPrefs() {
    savePrefs({
      defaultAssistant: prefDefaultAssistant,
      showSuggestions: prefShowSuggestions,
      sharePageContext: prefSharePageContext,
    });
  }

  function selectDefaultAssistant(id) {
    prefDefaultAssistant = id;
    persistPrefs();
  }

  function toggleShowSuggestions() {
    prefShowSuggestions = !prefShowSuggestions;
    persistPrefs();
  }

  function toggleSharePageContext() {
    prefSharePageContext = !prefSharePageContext;
    persistPrefs();
  }

  async function refreshApiStatus() {
    apiStatus = 'unknown';
    apiStatus = await checkApiStatus();
  }

  async function loadHistory() {
    if (!userPrincipal) return;
    isLoadingHistory = true;
    try {
      const { conversations: list } = await fetchConversations(userPrincipal);
      conversations = list;
    } catch (e) {
      console.warn('[assistant settings] fetchConversations failed:', e);
    } finally {
      isLoadingHistory = false;
    }
  }

  async function removeConversation(id, e) {
    e.stopPropagation();
    try {
      await deleteConversation(id);
      conversations = conversations.filter((c) => c.conversation_id !== id);
    } catch (err) {
      console.warn('[assistant settings] deleteConversation failed:', err);
    }
  }

  async function clearHistory() {
    if (!userPrincipal || clearingHistory) return;
    clearingHistory = true;
    try {
      await clearAllHistory(userPrincipal);
      conversations = [];
      historyCleared = true;
      setTimeout(() => {
        historyCleared = false;
      }, 2000);
    } catch (e) {
      console.warn('[assistant settings] clearAllHistory failed:', e);
    } finally {
      clearingHistory = false;
    }
  }

  onMount(async () => {
    const prefs = loadPrefs();
    prefDefaultAssistant = prefs.defaultAssistant || '';
    prefShowSuggestions = prefs.showSuggestions;
    prefSharePageContext = prefs.sharePageContext;

    isLoadingAssistants = true;
    try {
      availableAssistants = await fetchAssistants();
      if (!prefDefaultAssistant && availableAssistants.length > 0) {
        prefDefaultAssistant = availableAssistants[0].id;
      }
    } catch (e) {
      console.warn('[assistant settings] fetchAssistants failed:', e);
    } finally {
      isLoadingAssistants = false;
    }

    try {
      const { isAuthenticated, getPrincipal } = await import('$lib/auth.js');
      if (await isAuthenticated()) {
        const p = await getPrincipal();
        userPrincipal = p ? p.toText() : '';
        if (userPrincipal) await loadHistory();
      }
    } catch (e) {
      /* anonymous */
    }

    await refreshApiStatus();
  });
</script>

<svelte:head>
  <title>{$_('assistant.settings_title', { default: 'Realms Assistant — Settings' })}</title>
</svelte:head>

<div class="settings-page">
  <div class="settings-container">
    <header class="settings-header">
      <a href="/" class="back-link">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
        {$_('assistant.back', { default: 'Back' })}
      </a>
      <h1 class="settings-title">{$_('assistant.settings_title', { default: 'Realms Assistant — Settings' })}</h1>
    </header>

    <section class="settings-section">
      <h2 class="settings-section-title">{$_('assistant.default_assistant', { default: 'Default assistant' })}</h2>
      <p class="settings-section-desc">
        {$_('assistant.default_assistant_desc', {
          default: 'Which persona opens when you start a new conversation.',
        })}
      </p>
      {#if isLoadingAssistants}
        <p class="settings-section-desc">{$_('assistant.loading_assistants', { default: 'Loading assistants…' })}</p>
      {:else if availableAssistants.length > 0}
        <div class="settings-assistant-grid">
          {#each availableAssistants as a (a.id)}
            <button
              class="settings-assistant-btn"
              class:selected={prefDefaultAssistant === a.id ||
                (!prefDefaultAssistant && availableAssistants[0]?.id === a.id)}
              on:click={() => selectDefaultAssistant(a.id)}
              type="button"
            >
              {#if a.emoji}<span class="settings-assistant-emoji">{a.emoji}</span>{/if}
              <span class="settings-assistant-name">{a.name}</span>
            </button>
          {/each}
        </div>
      {:else}
        <p class="settings-section-desc">{$_('assistant.no_assistants', { default: 'No assistants available.' })}</p>
      {/if}
    </section>

    <section class="settings-section">
      <h2 class="settings-section-title">{$_('assistant.preferences', { default: 'Preferences' })}</h2>
      <div class="settings-toggle">
        <div class="settings-toggle-info">
          <span class="settings-toggle-label"
            >{$_('assistant.show_suggestions', { default: 'Show suggestion chips' })}</span
          >
          <span class="settings-toggle-desc"
            >{$_('assistant.show_suggestions_desc', {
              default: 'Display quick-reply suggestions after each response.',
            })}</span
          >
        </div>
        <button
          class="settings-switch"
          class:on={prefShowSuggestions}
          role="switch"
          aria-checked={prefShowSuggestions}
          on:click={toggleShowSuggestions}
          aria-label={$_('assistant.show_suggestions', { default: 'Show suggestion chips' })}
          type="button"
        ></button>
      </div>
      <div class="settings-toggle">
        <div class="settings-toggle-info">
          <span class="settings-toggle-label"
            >{$_('assistant.share_page_context', { default: 'Share page context' })}</span
          >
          <span class="settings-toggle-desc"
            >{$_('assistant.share_page_context_desc', {
              default: "Send the current page you're viewing as context to the assistant.",
            })}</span
          >
        </div>
        <button
          class="settings-switch"
          class:on={prefSharePageContext}
          role="switch"
          aria-checked={prefSharePageContext}
          on:click={toggleSharePageContext}
          aria-label={$_('assistant.share_page_context', { default: 'Share page context' })}
          type="button"
        ></button>
      </div>
    </section>

    {#if userPrincipal}
      <section class="settings-section">
        <h2 class="settings-section-title"
          >{$_('assistant.conversation_history', { default: 'Conversation history' })}</h2
        >
        {#if conversations.length > 0}
          <div class="settings-history-list">
            {#each conversations as conv (conv.conversation_id)}
              <div class="settings-history-item">
                <div class="settings-history-body">
                  <div class="settings-history-title">
                    {conv.title || $_('assistant.untitled', { default: 'Untitled' })}
                  </div>
                  <div class="settings-history-meta">
                    {formatConversationDate(conv.updated_at)} · {conv.message_count || 0}
                    {$_('assistant.messages_abbr', { default: 'msgs' })}
                  </div>
                </div>
                <button
                  class="settings-history-delete"
                  on:click={(e) => removeConversation(conv.conversation_id, e)}
                  title={$_('assistant.delete', { default: 'Delete' })}
                  type="button"
                >
                  <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"
                    ><path
                      d="M3 4h10M6 4V3h4v1M5 4v8h6V4H5z"
                      stroke="currentColor"
                      stroke-width="1.2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    /></svg
                  >
                </button>
              </div>
            {/each}
          </div>
        {:else}
          <p class="settings-section-desc">
            {isLoadingHistory
              ? $_('assistant.history_loading', { default: 'Loading conversations…' })
              : $_('assistant.history_empty_settings', { default: 'No conversations yet.' })}
          </p>
        {/if}
        <button
          class="settings-danger-btn"
          on:click={clearHistory}
          disabled={clearingHistory || conversations.length === 0}
          type="button"
        >
          {#if historyCleared}
            {$_('assistant.history_cleared', { default: 'History cleared' })}
          {:else if clearingHistory}
            {$_('assistant.clearing_history', { default: 'Clearing…' })}
          {:else}
            {$_('assistant.clear_history', { default: 'Clear all history' })}
          {/if}
        </button>
      </section>
    {/if}

    <section class="settings-section">
      <h2 class="settings-section-title">{$_('assistant.about', { default: 'About' })}</h2>
      <div class="settings-about-row">
        <span class="settings-about-label">{$_('assistant.product_name', { default: 'Product' })}</span>
        <span class="settings-about-value">Mundus Realms Assistant</span>
      </div>
      <div class="settings-about-row">
        <span class="settings-about-label">{$_('assistant.api_status', { default: 'API status' })}</span>
        <span class="settings-api-status {apiStatus}">
          {#if apiStatus === 'online'}
            ● {$_('assistant.online', { default: 'Online' })}
          {:else if apiStatus === 'offline'}
            ● {$_('assistant.offline_status', { default: 'Offline' })}
          {:else}
            {$_('assistant.checking', { default: 'Checking…' })}
          {/if}
        </span>
      </div>
      <button class="settings-link-btn" on:click={refreshApiStatus} type="button">
        {$_('assistant.check_again', { default: 'Check again' })}
      </button>
    </section>
  </div>
</div>

<style>
  .settings-page {
    min-height: 100vh;
    background: #f7f7f7;
    padding: 24px 16px 48px;
  }
  .settings-container {
    max-width: 640px;
    margin: 0 auto;
  }
  .settings-header {
    margin-bottom: 24px;
  }
  .back-link {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    color: #555;
    text-decoration: none;
    font-size: 0.9rem;
    margin-bottom: 12px;
  }
  .back-link:hover {
    color: #111;
  }
  .settings-title {
    font-size: 1.5rem;
    font-weight: 700;
    color: #111;
    margin: 0;
  }

  .settings-section {
    background: #fff;
    border: 1px solid #e8e8e8;
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
  }
  .settings-section-title {
    font-size: 1rem;
    font-weight: 600;
    color: #111;
    margin: 0 0 6px;
  }
  .settings-section-desc {
    font-size: 0.88rem;
    color: #777;
    margin: 0 0 14px;
    line-height: 1.45;
  }

  .settings-assistant-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
    gap: 10px;
  }
  .settings-assistant-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6px;
    padding: 14px 10px;
    border-radius: 10px;
    border: 1.5px solid #e5e5e5;
    background: #fafafa;
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
  }
  .settings-assistant-btn:hover {
    background: #f0f0f0;
  }
  .settings-assistant-btn.selected {
    border-color: #111;
    background: #111;
    color: #fff;
  }
  .settings-assistant-emoji {
    font-size: 1.4rem;
  }
  .settings-assistant-name {
    font-size: 0.85rem;
    font-weight: 500;
  }

  .settings-toggle {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
    padding: 12px 0;
    border-top: 1px solid #f0f0f0;
  }
  .settings-toggle:first-of-type {
    border-top: none;
    padding-top: 4px;
  }
  .settings-toggle-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
    min-width: 0;
  }
  .settings-toggle-label {
    font-size: 0.92rem;
    font-weight: 500;
    color: #222;
  }
  .settings-toggle-desc {
    font-size: 0.8rem;
    color: #888;
    line-height: 1.4;
  }
  .settings-switch {
    flex-shrink: 0;
    width: 44px;
    height: 26px;
    border-radius: 13px;
    border: none;
    background: #ddd;
    position: relative;
    cursor: pointer;
    transition: background 0.2s;
    padding: 0;
  }
  .settings-switch::after {
    content: '';
    position: absolute;
    top: 3px;
    left: 3px;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    background: #fff;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
    transition: transform 0.2s;
  }
  .settings-switch.on {
    background: #111;
  }
  .settings-switch.on::after {
    transform: translateX(18px);
  }

  .settings-history-list {
    display: flex;
    flex-direction: column;
    gap: 6px;
    margin-bottom: 14px;
    max-height: 320px;
    overflow-y: auto;
  }
  .settings-history-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid #f0f0f0;
    background: #fafafa;
  }
  .settings-history-body {
    flex: 1;
    min-width: 0;
  }
  .settings-history-title {
    font-size: 0.88rem;
    font-weight: 500;
    color: #222;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .settings-history-meta {
    font-size: 0.75rem;
    color: #999;
    margin-top: 2px;
  }
  .settings-history-delete {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border: none;
    background: transparent;
    color: #ccc;
    cursor: pointer;
    border-radius: 6px;
    padding: 4px;
  }
  .settings-history-delete svg {
    width: 14px;
    height: 14px;
  }
  .settings-history-delete:hover {
    color: #b00020;
    background: #fef2f2;
  }

  .settings-danger-btn {
    display: inline-flex;
    align-items: center;
    padding: 8px 14px;
    border-radius: 8px;
    border: 1px solid #fecaca;
    background: #fef2f2;
    color: #b00020;
    font-size: 0.88rem;
    cursor: pointer;
  }
  .settings-danger-btn:hover:not(:disabled) {
    background: #fee2e2;
  }
  .settings-danger-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .settings-about-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 8px 0;
    font-size: 0.9rem;
  }
  .settings-about-label {
    color: #777;
  }
  .settings-about-value {
    color: #222;
    font-weight: 500;
  }
  .settings-api-status {
    font-weight: 500;
  }
  .settings-api-status.online {
    color: #16a34a;
  }
  .settings-api-status.offline {
    color: #dc2626;
  }
  .settings-api-status.unknown {
    color: #9ca3af;
  }
  .settings-link-btn {
    margin-top: 8px;
    background: none;
    border: none;
    color: #2563eb;
    font-size: 0.88rem;
    cursor: pointer;
    padding: 0;
    text-decoration: underline;
  }
  .settings-link-btn:hover {
    color: #1d4ed8;
  }
</style>
