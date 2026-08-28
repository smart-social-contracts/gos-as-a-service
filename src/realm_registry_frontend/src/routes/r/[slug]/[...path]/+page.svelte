<script>
  import { onMount, onDestroy } from 'svelte';
  import { fade } from 'svelte/transition';
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { resolveSlug } from '$lib/slug-resolver.js';
  import { realmIframeUrl } from '$lib/federation.js';
  import { attachPortalBridge } from '$lib/portal-bridge-host.js';
  import { portalDocumentFocus } from '$lib/portal-focus.js';
  import { requestAssistantOpen } from '$lib/assistant-open.js';
  import { login } from '$lib/auth.js';
  import { authSession } from '$lib/stores/authSession.js';
  import { CONFIG } from '$lib/config.js';
  import { fetchRealmRuntimeFlags } from '$lib/realm-runtime-flags.js';
  import { fetchDeploymentJobsFromInstaller } from '$lib/installer-queue.js';
  import { isUnknownSlugError, findJobForSlug, unknownSlugView } from '$lib/unknown-slug.js';
  import {
    clearSplashBrandHint,
    HOST_SPLASH_MARK_PATH,
    writeSplashBrandHint,
  } from '$lib/realm-utils.js';
  import RealmsSphereLoader from '$lib/components/RealmsSphereLoader.svelte';

  export let data = {};

  let iframeEl;
  let loading = true;
  let error = '';
  let slugView = null;
  let realm = null;
  let bridge = null;
  /** When true the embedded realm handles auth locally (test-mode II bypass). */
  let realmIIBypass = false;
  // The embedded realm asked for a delegation but the portal has no II
  // session — surface a sign-in UI on this (canonical) origin.
  let needsLogin = false;
  let loggingIn = false;
  let loginError = '';
  // Bare /r/<slug> always loads the realm root. The realm decides
  // member-dashboard vs public-dashboard vs /join. Deep paths are preserved.
  let rootIframePath = '/';
  let creatingPollTimer = null;
  let iframeLoaded = false;
  let iframeReady = false;
  let iframeReadyFallbackTimer = null;

  $: slug = $page.params.slug;
  $: subPath = $page.url.pathname.replace(new RegExp(`^/r/${slug}`), '') || '/';

  let unsubAuth = () => {};

  onMount(async () => {
    if (!browser) return;
    // If the portal session is (or becomes) available after the iframe's
    // first silent probe was answered with auth:pending, push the delegation
    // without requiring the user to click anything.
    unsubAuth = authSession.subscribe((s) => {
      if (s?.isLoggedIn) void bridge?.refreshDelegation?.();
    });
    await loadRealm();
  });

  onDestroy(() => {
    unsubAuth();
    stopCreatingPoll();
    clearIframeReadyFallback();
    bridge?.dispose?.();
    portalDocumentFocus.set(null);
  });

  function clearIframeReadyFallback() {
    if (iframeReadyFallbackTimer) {
      clearTimeout(iframeReadyFallbackTimer);
      iframeReadyFallbackTimer = null;
    }
  }

  function markIframeReady() {
    if (iframeReady) return;
    iframeReady = true;
    clearIframeReadyFallback();
  }

  function startIframeReadyFallback() {
    clearIframeReadyFallback();
    iframeReadyFallbackTimer = setTimeout(() => {
      iframeReadyFallbackTimer = null;
      markIframeReady();
    }, 10000);
  }

  $: if (browser && slugView?.kind === 'creating') {
    startCreatingPoll();
  } else {
    stopCreatingPoll();
  }

  function stopCreatingPoll() {
    if (creatingPollTimer) {
      clearInterval(creatingPollTimer);
      creatingPollTimer = null;
    }
  }

  function startCreatingPoll() {
    if (creatingPollTimer) return;
    creatingPollTimer = setInterval(() => {
      void pollCreatingSlug();
    }, 5000);
  }

  async function pollCreatingSlug() {
    try {
      const data = await resolveSlug(slug, { force: true });
      slugView = null;
      error = '';
      stopCreatingPoll();
      await applyResolved(data);
    } catch (e) {
      if (isUnknownSlugError(e, slug)) {
        let jobs = [];
        try {
          jobs = await fetchDeploymentJobsFromInstaller();
        } catch (_) {
          jobs = [];
        }
        slugView = unknownSlugView(slug, findJobForSlug(jobs, slug));
        error = slugView.title;
        if (slugView.kind !== 'creating') {
          clearSplashBrandHint(slug);
          stopCreatingPoll();
        }
      } else {
        slugView = null;
        error = e instanceof Error ? e.message : String(e);
        stopCreatingPoll();
      }
    }
  }

  async function handlePortalLogin() {
    loggingIn = true;
    loginError = '';
    try {
      const { identity } = await login();
      if (!identity) {
        loginError = 'Sign-in was cancelled or failed. Please try again.';
        return;
      }
      // Deliver the freshly minted session to the waiting iframe.
      await bridge?.refreshDelegation?.();
      needsLogin = false;
    } catch (e) {
      loginError = e instanceof Error ? e.message : String(e);
    } finally {
      loggingIn = false;
    }
  }

  async function applyResolved(data) {
    realm = {
      slug: data.slug,
      backendCanisterId: data.backend_canister_id,
      frontendCanisterId: data.frontend_canister_id,
      portalUrl: data.portal_url,
      loaderProfile: data.loader_profile || 'realms-iframe-v1',
      logoUrl: '',
      env: CONFIG.deploy_queue_network
    };
    const flags = await fetchRealmRuntimeFlags(data.backend_canister_id);
    realmIIBypass = !!flags?.test_mode_ii_bypass;
    const logoUrl = String(flags?.logo_url || flags?.realm_logo || '').trim();
    realm = { ...realm, logoUrl };
    writeSplashBrandHint(data.slug || slug, {
      frontendCanisterId: data.frontend_canister_id,
      configuredLogoUrl: logoUrl,
    });
    if (realmIIBypass) {
      needsLogin = false;
    }
  }

  async function loadRealm() {
    loading = true;
    error = '';
    slugView = null;
    iframeLoaded = false;
    iframeReady = false;
    clearIframeReadyFallback();
    stopCreatingPoll();
    bridge?.dispose?.();
    bridge = null;
    try {
      const data = await resolveSlug(slug);
      await applyResolved(data);
    } catch (e) {
      if (isUnknownSlugError(e, slug)) {
        let jobs = [];
        try {
          jobs = await fetchDeploymentJobsFromInstaller();
        } catch (_) {
          jobs = [];
        }
        slugView = unknownSlugView(slug, findJobForSlug(jobs, slug));
        error = slugView.title;
        clearSplashBrandHint(slug);
      } else {
        slugView = null;
        error = e instanceof Error ? e.message : String(e);
      }
    } finally {
      loading = false;
    }
  }

  function onIframeLoad() {
    if (!iframeEl || !realm) return;
    // Fires on every iframe navigation, including in-frame reloads — re-arm
    // the overlay so a reloaded realm gets the same no-blank-gap treatment.
    iframeLoaded = true;
    iframeReady = false;
    startIframeReadyFallback();
    bridge?.dispose?.();
    bridge = attachPortalBridge(iframeEl, realm, {
      onAuthState: (pending) => {
        if (realmIIBypass) {
          needsLogin = false;
          return;
        }
        needsLogin = pending;
        if (!pending) loginError = '';
      },
      onFocus: (focus) => {
        portalDocumentFocus.set(focus ?? null);
      },
      onAssistantOpen: () => {
        requestAssistantOpen();
      },
      onUiReady: () => {
        markIframeReady();
      }
    });
    // Do not syncPath here. The iframe already loaded `iframeSrc` (including
    // portal=1/slug). A host `/join` sync used to `goto('/join')` inside the
    // frame, strip those params, and reload in a loop.
  }

  $: iframePath = subPath === '/' ? rootIframePath : subPath;

  $: iframeSrc =
    realm && browser
      ? realmIframeUrl(realm.frontendCanisterId, realm.slug, iframePath)
      : '';
</script>

<svelte:head>
  <title>{slug} — Realms</title>
  <link rel="preload" as="image" href={HOST_SPLASH_MARK_PATH} />
</svelte:head>

<div class="portal-shell">
  {#if error}
    <div class="error-box">
      {#if slugView}
        <p class="error-title">{slugView.title}</p>
        {#if slugView.body}
          <p class="error-body">{slugView.body}</p>
        {/if}
        {#if slugView.href}
          <a href={slugView.href}>Open deployment</a>
        {/if}
        <a href="/">Back to registry</a>
        {#if slugView.kind === 'missing'}
          <a href="/create-realm">Create a realm</a>
        {/if}
        {#if slugView.kind === 'creating'}
          <p class="error-checking">Checking again…</p>
        {/if}
      {:else}
        <p class="error-generic">{error}</p>
        <a href="/">Back to registry</a>
      {/if}
    </div>
  {:else if realm || loading}
    {#if realm}
      <div class="frame-wrap">
        <iframe
          bind:this={iframeEl}
          title="Realm {slug}"
          src={iframeSrc}
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-downloads"
          referrerpolicy="no-referrer"
          on:load={onIframeLoad}
          class="realm-frame"
        ></iframe>
        {#if needsLogin && !realmIIBypass}
          <div class="login-overlay">
            <div class="login-card">
              <h2>Sign in to Realms</h2>
              <p>
                One Internet Identity login works across every realm on this portal.
                You'll return to <strong>{slug}</strong> automatically.
              </p>
              <button class="login-btn" on:click={handlePortalLogin} disabled={loggingIn}>
                {loggingIn ? 'Waiting for Internet Identity…' : 'Sign in with Internet Identity'}
              </button>
              {#if loginError}
                <p class="login-error">{loginError}</p>
              {/if}
            </div>
          </div>
        {/if}
      </div>
    {/if}
    {#if loading || (realm && !iframeReady)}
      <div
        class="loading-overlay"
        role="status"
        aria-live="polite"
        transition:fade={{ duration: 300 }}
      >
        <RealmsSphereLoader size={128} />
        <p class="loading-label">{iframeLoaded ? 'Preparing realm…' : 'Loading realm'}</p>
      </div>
    {/if}
  {/if}
</div>

<style>
  :global(html),
  :global(body) {
    margin: 0;
    padding: 0;
    background: #fff;
    /* Overflow stays on .portal-shell — body lock leaks to other routes. */
  }

  .portal-shell {
    position: relative;
    display: flex;
    flex-direction: column;
    width: 100%;
    height: 100vh;
    height: 100dvh;
    overflow: hidden;
    background: #fff;
  }
  .frame-wrap {
    position: relative;
    flex: 1;
    display: flex;
    flex-direction: column;
    width: 100%;
    min-height: 0;
  }
  .realm-frame {
    flex: 1;
    width: 100%;
    height: 100%;
    min-height: 100vh;
    min-height: 100dvh;
    border: none;
    display: block;
    background: #fff;
  }
  .loading-overlay {
    position: absolute;
    inset: 0;
    z-index: 20;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1.5rem;
    background: #fff;
  }
  .loading-label {
    margin: 0;
    font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    font-size: 1.0625rem;
    font-weight: 600;
    letter-spacing: 0.04em;
    color: #737373;
  }
  .login-overlay {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(10, 10, 14, 0.72);
    backdrop-filter: blur(3px);
    z-index: 10;
  }
  .login-card {
    max-width: 24rem;
    padding: 2rem;
    border-radius: 0.75rem;
    background: #18181b;
    border: 1px solid rgba(255, 255, 255, 0.12);
    text-align: center;
    color: #e4e4e7;
  }
  .login-card h2 {
    margin: 0 0 0.75rem;
    font-size: 1.25rem;
  }
  .login-card p {
    margin: 0 0 1.25rem;
    font-size: 0.9rem;
    line-height: 1.5;
    color: #a1a1aa;
  }
  .login-btn {
    width: 100%;
    padding: 0.7rem 1rem;
    border: none;
    border-radius: 0.5rem;
    background: #fafafa;
    color: #18181b;
    font-weight: 600;
    cursor: pointer;
  }
  .login-btn:disabled {
    opacity: 0.6;
    cursor: wait;
  }
  .login-error {
    margin-top: 1rem;
    color: #f87171;
    font-size: 0.85rem;
  }
  .error-box {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    padding: 2rem;
    text-align: center;
    background: #fff;
  }
  .error-title {
    margin: 0;
    font-size: 0.9375rem;
    font-weight: 500;
    color: #525252;
  }
  .error-body {
    margin: 0;
    font-size: 0.875rem;
    color: #737373;
  }
  .error-generic {
    margin: 0;
    color: #f87171;
  }
  .error-checking {
    margin: 0.5rem 0 0;
    font-size: 0.8125rem;
    color: #a3a3a3;
  }
  .error-box a {
    font-size: 0.875rem;
    color: #2563eb;
    text-decoration: none;
  }
  .error-box a:hover {
    text-decoration: underline;
  }
</style>
