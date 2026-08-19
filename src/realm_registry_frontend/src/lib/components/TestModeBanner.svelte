<script>
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { testMode } from '$lib/stores/registryRuntimeFlags.js';
  import { _ } from 'svelte-i18n';

  const STORAGE_KEY = 'gos_test_mode_banner_dismissed';
  let dismissed = false;

  function dismissBanner() {
    dismissed = true;
    if (browser) localStorage.setItem(STORAGE_KEY, 'true');
  }

  if (browser) {
    dismissed = localStorage.getItem(STORAGE_KEY) === 'true';
  }

  $: viewingRealm = $page.url.pathname.startsWith('/r/');
  $: showBanner = browser && $testMode && !dismissed && !viewingRealm;

  $: if (browser) {
    const height = showBanner ? '2.75rem' : '0px';
    document.documentElement.style.setProperty('--test-mode-banner-height', height);
    document.documentElement.classList.toggle('test-mode-banner-on', showBanner);
  }
</script>

{#if showBanner}
  <div class="test-mode-banner" role="status">
    <p class="banner-text">
      <span class="title">{$_('demo_banner.title')}</span> {$_('demo_banner.description')}
    </p>
    <button type="button" class="dismiss" on:click={dismissBanner} aria-label={$_('demo_banner.dismiss_label')}>
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" d="M6 18L18 6M6 6l12 12"/>
      </svg>
    </button>
  </div>
{/if}

<style>
  .test-mode-banner {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 400;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: #000;
    color: #fff;
    padding: 0.625rem 1rem;
    font-size: 0.875rem;
    line-height: 1.3;
    font-family: var(--font-family);
  }
  .banner-text { margin: 0; flex: 1; min-width: 0; }
  .title { font-weight: 600; }
  .dismiss {
    flex-shrink: 0;
    border: none;
    background: transparent;
    color: #fff;
    border-radius: 0.25rem;
    padding: 0.375rem;
    cursor: pointer;
    display: flex;
    align-items: center;
  }
  .dismiss:hover { background: rgba(255,255,255,0.15); }
</style>
