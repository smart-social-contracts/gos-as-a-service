<script>
  import { createEventDispatcher } from 'svelte';
  import { _, locale } from 'svelte-i18n';
  import {
    ensureProtocol,
    formatFullDate,
    formatTimeAgo,
    resolvedRealmLogoUrl,
    resolveRealmAssetUrl,
  } from '$lib/realm-utils.js';
  import { stageLabel } from '$lib/realm-stages.js';

  export let realm;
  export let selected = false;

  const dispatch = createEventDispatcher();

  let logoFailed = false;

  $: welcomeBg = resolveRealmAssetUrl(realm, '/custom/background.png');
  $: logoSrc = resolvedRealmLogoUrl(realm);
  $: realm?.id, (logoFailed = false);
</script>

<button
  class="realm-card"
  class:selected
  on:click={() => dispatch('select', { realm })}
  type="button"
>
  {#if welcomeBg}
    <div class="realm-card-bg" style="background-image: url('{welcomeBg}')"></div>
  {/if}
  <div class="card-accent"></div>

  <div class="realm-header">
    <div class="realm-logo-container">
      {#if logoSrc && !logoFailed}
        <img
          src={logoSrc}
          alt=""
          class="realm-logo"
          on:error={() => (logoFailed = true)}
        />
      {:else}
        <div class="realm-logo-fallback">
          <span>{(realm.name || realm.realm_name || '?').charAt(0).toUpperCase()}</span>
        </div>
      {/if}
    </div>
    <div class="realm-badges">
      {#if realm.realm_stage}
        <span class="stage-badge stage-{realm.realm_stage}">
          {stageLabel(realm.realm_stage)}
        </span>
      {/if}
      <div class="user-badge" class:has-users={realm.users_count > 0}>
        <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
          <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
        </svg>
        <span>{realm.users_count || 0}</span>
      </div>
    </div>
  </div>

  <div class="realm-content">
    <h3 class="realm-name">{realm.name || realm.realm_name}</h3>

    {#if realm.manifesto}
      <p
        class="realm-manifesto"
        title={realm.manifesto}
        on:click|stopPropagation={() => dispatch('manifesto', { realm })}
        on:keydown|stopPropagation={(e) => e.key === 'Enter' && dispatch('manifesto', { realm })}
        role="button"
        tabindex="0"
      >
        {realm.manifesto}
      </p>
    {/if}

    <p class="realm-info" title={formatFullDate(realm.created_at)}>
      <code>{realm.id}</code>
      <span class="info-separator">·</span>
      <span>{formatTimeAgo(realm.created_at, $_, $locale)}</span>
    </p>
  </div>

  {#if realm.url}
    <div class="realm-actions">
      <span
        class="visit-btn"
        role="link"
        tabindex="0"
        on:click|stopPropagation={() =>
          window.open(ensureProtocol(realm.url).replace(/\/+$/, '') + '/', '_blank')}
        on:keydown|stopPropagation={(e) =>
          e.key === 'Enter' &&
          window.open(ensureProtocol(realm.url).replace(/\/+$/, '') + '/', '_blank')}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
          <polyline points="15 3 21 3 21 9"></polyline>
          <line x1="10" y1="14" x2="21" y2="3"></line>
        </svg>
        {$_('card.visit')}
      </span>
    </div>
  {/if}
</button>

<style>
  .realm-card {
    position: relative;
    display: flex;
    flex-direction: column;
    width: 100%;
    padding: 1rem;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface);
    text-align: left;
    cursor: pointer;
    font-family: var(--font-family);
    transition: border-color 0.15s, box-shadow 0.15s;
    overflow: hidden;
  }

  .realm-card:hover {
    border-color: var(--gray-300);
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  }

  .realm-card.selected {
    border-color: var(--text-secondary);
    box-shadow: 0 0 0 1px var(--text-secondary);
  }

  .realm-card-bg {
    position: absolute;
    inset: 0;
    background-size: cover;
    background-position: center;
    opacity: 0.28;
    pointer-events: none;
  }

  .card-accent {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: var(--border);
    z-index: 1;
  }

  .realm-header {
    position: relative;
    z-index: 1;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 0.75rem;
    margin-bottom: 0.75rem;
  }

  .realm-logo-container {
    flex-shrink: 0;
  }

  .realm-logo {
    width: 40px;
    height: 40px;
    border-radius: 8px;
    object-fit: cover;
    border: 1px solid var(--border);
  }

  .realm-logo-fallback {
    width: 40px;
    height: 40px;
    border-radius: 8px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    color: var(--text-secondary);
    font-size: 1rem;
  }

  .realm-badges {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.375rem;
  }

  .stage-badge {
    font-size: 0.6875rem;
    font-weight: 500;
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    text-transform: capitalize;
  }

  .stage-alpha {
    color: var(--stage-alpha-color);
    background: var(--stage-alpha-bg);
  }

  .stage-beta {
    color: var(--stage-beta-color);
    background: var(--stage-beta-bg);
  }

  .stage-production {
    color: var(--stage-live-color);
    background: var(--stage-live-bg);
  }

  .stage-deprecation {
    color: var(--stage-winding-color);
    background: var(--stage-winding-bg);
  }

  .stage-terminated {
    color: var(--stage-archived-color);
    background: var(--stage-archived-bg);
  }

  .user-badge {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: var(--text-faint);
  }

  .user-badge.has-users {
    color: var(--text-secondary);
  }

  .realm-content,
  .realm-actions {
    position: relative;
    z-index: 1;
  }

  .realm-name {
    margin: 0 0 0.375rem;
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .realm-manifesto {
    margin: 0 0 0.5rem;
    font-size: 0.8125rem;
    color: var(--text-tertiary);
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
    cursor: pointer;
  }

  .realm-manifesto:hover {
    color: var(--text-secondary);
  }

  .realm-info {
    margin: 0;
    font-size: 0.6875rem;
    color: var(--text-faint);
  }

  .realm-info code {
    font-family: ui-monospace, monospace;
    font-size: 0.625rem;
    word-break: break-all;
  }

  .info-separator {
    margin: 0 0.25rem;
  }

  .realm-actions {
    margin-top: 0.75rem;
    padding-top: 0.75rem;
    border-top: 1px solid var(--border);
  }

  .visit-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-primary);
    background: var(--surface-2);
    padding: 0.375rem 0.75rem;
    border-radius: 6px;
    cursor: pointer;
  }

  .visit-btn:hover {
    background: var(--border);
  }
</style>
