<script>
  import { browser } from '$app/environment';
  import { onMount, tick } from 'svelte';
  import { page } from '$app/stores';
  import { testMode } from '$lib/stores/registryRuntimeFlags.js';
  import { _ } from 'svelte-i18n';

  const STORAGE_KEY = 'gos_test_mode_banner_dismissed';
  const FALLBACK_HEIGHT = '2.75rem';
  let dismissed = false;
  /** @type {HTMLElement | undefined} */
  let bannerEl;
  /** @type {ResizeObserver | undefined} */
  let observer;

  function dismissBanner() {
    dismissed = true;
    if (browser) localStorage.setItem(STORAGE_KEY, 'true');
  }

  function publishHeight() {
    if (!browser) return;
    let height = '0px';
    if (showBanner && bannerEl) {
      height = `${Math.round(bannerEl.getBoundingClientRect().height)}px`;
    } else if (showBanner) {
      height = FALLBACK_HEIGHT;
    }
    document.documentElement.style.setProperty('--test-mode-banner-height', height);
    document.documentElement.classList.toggle('test-mode-banner-on', !!showBanner);
  }

  if (browser) {
    dismissed = localStorage.getItem(STORAGE_KEY) === 'true';
  }

  $: viewingRealm = $page.url.pathname.startsWith('/r/');
  $: showBanner = browser && $testMode && !dismissed && !viewingRealm;

  $: if (browser) {
    void tick().then(publishHeight);
    showBanner;
    bannerEl;
  }

  $: if (observer && bannerEl) observer.observe(bannerEl);

  onMount(() => {
    observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(publishHeight) : undefined;
    return () => {
      observer?.disconnect();
      document.documentElement.style.setProperty('--test-mode-banner-height', '0px');
      document.documentElement.classList.remove('test-mode-banner-on');
    };
  });
</script>

{#if showBanner}
  <div class="test-mode-banner" bind:this={bannerEl} role="status">
    <p class="banner-text">
      <span class="title">{$_('demo_banner.title')}</span> {$_('demo_banner.description')}
    </p>
    <button type="button" class="dismiss" on:click={dismissBanner} aria-label={$_('demo_banner.dismiss_label')}>
      <!-- SVG must not be the hit target: click on <path> is mouse-dead in
           some browsers while Tab+Enter still fires on the button. -->
      <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24" aria-hidden="true">
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
    pointer-events: auto;
    position: relative;
    z-index: 1;
  }
  .dismiss svg,
  .dismiss path {
    pointer-events: none;
  }
  .dismiss:hover { background: rgba(255,255,255,0.15); }
</style>
