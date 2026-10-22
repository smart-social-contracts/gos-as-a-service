<script>
  import { createEventDispatcher } from 'svelte';
  import { slide } from 'svelte/transition';
  import { _, locale } from 'svelte-i18n';
  import {
    acceptBrandingAssetUrl,
    ensureProtocol,
    formatCount,
    formatFullDate,
    formatLastActivity,
    realmFrontendAssetBase,
    resolvedRealmLogoUrl,
    resolveRealmAssetUrl,
  } from '$lib/realm-utils.js';
  import { stageLabel } from '$lib/realm-stages.js';

  export let realm;
  export let selected = false;
  export let expanded = false;

  const dispatch = createEventDispatcher();

  let logoFailed = false;
  let logoSrc = null;
  let logoKey = '';
  let bannerSrc = '';
  let bannerKey = '';

  $: assetKey = `${realm?.id || ''}|${realm?.frontend_canister_id || ''}|${realmFrontendAssetBase(realm || {})}`;
  $: probeLogo(assetKey);
  // The background is the heaviest asset on the card: only fetch it once the card is opened.
  $: if (expanded) probeBanner(assetKey);

  $: name = realm.name || realm.realm_name || '';
  $: stageId = realm.realm_stage;
  $: stageText = stageId ? $_(`stages.${stageId}.label`, { default: stageLabel(stageId) }) : '';
  $: stageHelp = stageId ? $_(`stages.${stageId}.help`, { default: '' }) : '';
  $: activity = formatLastActivity(realm.last_activity_at, $_, $locale);
  $: activityTitle = realm.last_activity_at ? formatFullDate(realm.last_activity_at, $locale) : '';
  $: members = formatCount(realm.users_count, $locale);
  $: visitUrl = realm.url ? ensureProtocol(realm.url).replace(/\/+$/, '') + '/' : '';
  $: detailsId = `realm-details-${realm.id}`;

  async function accepted(url) {
    try {
      return Boolean(url) && (await acceptBrandingAssetUrl(url));
    } catch {
      return false;
    }
  }

  async function probeLogo(key) {
    if (key === logoKey) return;
    logoKey = key;
    logoFailed = false;
    logoSrc = null;
    const url = resolvedRealmLogoUrl(realm || {});
    if ((await accepted(url)) && key === logoKey) logoSrc = url;
  }

  async function probeBanner(key) {
    if (key === bannerKey) return;
    bannerKey = key;
    bannerSrc = '';
    const url = resolveRealmAssetUrl(realm || {}, '/custom/background.png');
    if ((await accepted(url)) && key === bannerKey) bannerSrc = url;
  }
</script>

<article class="realm-card" class:selected class:expanded>
  <button
    type="button"
    class="realm-row"
    aria-expanded={expanded}
    aria-controls={expanded ? detailsId : undefined}
    on:click={() => dispatch('toggle', { realm })}
  >
    <span class="realm-logo-container">
      {#if logoSrc && !logoFailed}
        <img src={logoSrc} alt="" class="realm-logo" on:error={() => (logoFailed = true)} />
      {:else}
        <span class="realm-logo-fallback">{(name || '?').charAt(0).toUpperCase()}</span>
      {/if}
    </span>

    <span class="realm-main">
      <span class="realm-name">{name}</span>
      {#if stageText || activity}
        <span class="realm-meta">
          {#if stageText}
            <span class="stage-badge stage-{stageId}" title={stageHelp}>{stageText}</span>
          {/if}
          {#if activity}
            <span class="activity" title={activityTitle}>{activity}</span>
          {/if}
        </span>
      {/if}
    </span>

    <span
      class="user-badge"
      class:has-users={realm.users_count > 0}
      title={$_('card.members', { values: { count: members } })}
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
      </svg>
      <span>{members}</span>
    </span>

    <svg class="chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <polyline points="6 9 12 15 18 9"></polyline>
    </svg>
    <span class="sr-only">{expanded ? $_('card.collapse') : $_('card.expand')}</span>
  </button>

  {#if expanded}
    <div
      id={detailsId}
      class="realm-details"
      class:has-image={bannerSrc}
      style:background-image={bannerSrc ? `url('${bannerSrc}')` : null}
      transition:slide={{ duration: 160 }}
    >
      {#if realm.manifesto}
        <button
          type="button"
          class="realm-manifesto"
          title={$_('card.read_manifesto')}
          on:click={() => dispatch('manifesto', { realm })}
        >
          {realm.manifesto}
        </button>
      {/if}
      {#if visitUrl}
        <a class="visit-btn" href={visitUrl} target="_blank" rel="noopener noreferrer">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path>
            <polyline points="15 3 21 3 21 9"></polyline>
            <line x1="10" y1="14" x2="21" y2="3"></line>
          </svg>
          {$_('card.visit')}
        </a>
      {/if}
    </div>
  {/if}
</article>

<style>
  .realm-card {
    width: 100%;
    border: 1px solid var(--border);
    border-radius: 12px;
    background: var(--surface);
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

  .realm-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
    padding: 0.75rem 0.875rem;
    border: 0;
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }

  .realm-row:focus-visible {
    outline: 2px solid var(--text-secondary);
    outline-offset: -2px;
    border-radius: 12px;
  }

  .realm-logo-container {
    flex-shrink: 0;
    display: flex;
  }

  .realm-logo,
  .realm-logo-fallback {
    width: 36px;
    height: 36px;
    border-radius: 8px;
    border: 1px solid var(--border);
  }

  .realm-logo {
    object-fit: contain;
    background: var(--surface);
  }

  .realm-logo-fallback {
    background: var(--surface-2);
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    color: var(--text-secondary);
    font-size: 1rem;
  }

  .realm-main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .realm-name {
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--text-primary);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .realm-meta {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    min-width: 0;
    font-size: 0.75rem;
    color: var(--text-tertiary);
  }

  .activity {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .stage-badge {
    flex-shrink: 0;
    font-size: 0.6875rem;
    font-weight: 500;
    padding: 0.125rem 0.5rem;
    border-radius: 4px;
    cursor: help;
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
    flex-shrink: 0;
    display: flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: var(--text-faint);
  }

  .user-badge.has-users {
    color: var(--text-secondary);
  }

  .chevron {
    flex-shrink: 0;
    color: var(--text-faint);
    transition: transform 0.15s;
  }

  .expanded .chevron {
    transform: rotate(180deg);
  }

  .sr-only {
    position: absolute;
    width: 1px;
    height: 1px;
    margin: -1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }

  .realm-details {
    position: relative;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    padding: 0.875rem;
    border-top: 1px solid var(--border);
    background-size: cover;
    background-position: center;
  }

  .realm-details.has-image {
    min-height: 160px;
    justify-content: flex-end;
  }

  /* Darken toward the text so it stays readable on any photo. */
  .realm-details.has-image::before {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(
      to top,
      rgba(15, 23, 42, 0.9) 0%,
      rgba(15, 23, 42, 0.6) 55%,
      rgba(15, 23, 42, 0.15) 100%
    );
  }

  .realm-details > * {
    position: relative;
  }

  .realm-manifesto {
    display: -webkit-box;
    -webkit-line-clamp: 5;
    -webkit-box-orient: vertical;
    overflow: hidden;
    padding: 0;
    border: 0;
    background: none;
    font: inherit;
    font-size: 0.8125rem;
    line-height: 1.45;
    text-align: left;
    color: var(--text-secondary);
    cursor: pointer;
  }

  .realm-manifesto:hover {
    color: var(--text-primary);
  }

  .has-image .realm-manifesto {
    color: rgba(255, 255, 255, 0.92);
    text-shadow: 0 1px 2px rgba(0, 0, 0, 0.45);
  }

  .has-image .realm-manifesto:hover {
    color: #fff;
  }

  .visit-btn {
    align-self: flex-start;
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.8125rem;
    font-weight: 500;
    color: var(--text-primary);
    background: var(--surface-2);
    padding: 0.375rem 0.75rem;
    border-radius: 6px;
    text-decoration: none;
  }

  .visit-btn:hover {
    background: var(--border);
  }

  .has-image .visit-btn {
    color: #0f172a;
    background: rgba(255, 255, 255, 0.92);
  }

  .has-image .visit-btn:hover {
    background: #fff;
  }
</style>
