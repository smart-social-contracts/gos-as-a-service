<script>
  import { onMount } from 'svelte';
  import { afterNavigate } from '$app/navigation';
  import { page } from '$app/stores';
  import { browser } from '$app/environment';
  import { initI18n } from '$lib/i18n';
  import { ensureRegistryRuntimeFlags } from '$lib/stores/registryRuntimeFlags.js';
  import { syncAuthSession } from '$lib/stores/authSession.js';
  import TestModeBanner from '$lib/components/TestModeBanner.svelte';
  import RegistryAssistant from '$lib/components/RegistryAssistant.svelte';
  import DeployProgressModal from '$lib/components/DeployProgressModal.svelte';
  import { assistantChrome } from '$lib/assistant-chrome.js';
  import { deployProgress, closeDeployProgress } from '$lib/stores/deployProgress.js';
  import '../index.scss';
  import '$lib/theme/tokens.css';

  // Flag to track if i18n is ready
  let i18nReady = false;

  /** Registry map page insets the globe itself; avoid double-shrinking via shell padding. */
  $: registryMapRoute = $page.url.pathname === '/';
  $: assistantDockPadding =
    $assistantChrome.open && $assistantChrome.docked && !registryMapRoute;

  /** Full-viewport routes that must not scroll the document. */
  function pathLocksScroll(pathname) {
    return pathname === '/' || pathname.startsWith('/r/');
  }

  function syncBodyScroll(pathname) {
    if (!browser) return;
    // Inline style beats leftover route CSS (SPA navigations used to leave
    // body { overflow: hidden } from the map/portal pages).
    document.body.style.overflow = pathLocksScroll(pathname) ? 'hidden' : '';
  }

  onMount(async () => {
    await ensureRegistryRuntimeFlags();
    await syncAuthSession();
    // Initialize i18n and wait for translations to load
    await initI18n();
    i18nReady = true;
    if (browser) syncBodyScroll(window.location.pathname);
  });

  afterNavigate(({ to }) => {
    syncBodyScroll(to?.url?.pathname || '/');
  });
</script>

{#if browser && i18nReady}
  <TestModeBanner />
  <div
    class="app-shell"
    class:full-viewport={pathLocksScroll($page.url.pathname)}
    class:assistant-docked={assistantDockPadding}
    class:assistant-resizing={$assistantChrome.resizing}
    style="--assistant-width: {$assistantChrome.width}px"
  >
    <slot />
  </div>
  <!-- Mundus-level AI assistant (float/dock); see issue #233. -->
  <RegistryAssistant />
  <DeployProgressModal
    open={$deployProgress.open}
    phase={$deployProgress.phase}
    activeStep={$deployProgress.activeStep}
    errorMessage={$deployProgress.errorMessage}
    on:dismiss={closeDeployProgress}
  />
{:else}
  <div class="loading-screen">
    <div class="spinner"></div>
  </div>
{/if}

<style>
  :global(html),
  :global(body) {
    overflow-x: hidden;
    overflow-y: auto;
  }

  .app-shell {
    min-height: 100vh;
    padding-top: var(--test-mode-banner-height, 0px);
    transition: padding-right 0.25s ease;
  }
  .app-shell.full-viewport {
    /* Globe/portal pages use position:fixed chrome. Do not drop the banner
       offset here — those panels read --test-mode-banner-height themselves.
       Zeroing padding avoids a double-gap under the globe canvas. */
    padding-top: 0;
  }
  .app-shell.assistant-docked {
    padding-right: var(--assistant-width);
  }
  .app-shell.assistant-docked.assistant-resizing {
    transition: none;
  }
  /* Narrow: docked panel is a full-width overlay — don't pad the shell. */
  @media (max-width: 767px) {
    .app-shell.assistant-docked {
      padding-right: 0;
    }
  }

  .loading-screen {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    background: #FAFAFA;
  }

  .spinner {
    width: 40px;
    height: 40px;
    border: 4px solid #F5F5F5;
    border-top: 4px solid #525252;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
</style>
