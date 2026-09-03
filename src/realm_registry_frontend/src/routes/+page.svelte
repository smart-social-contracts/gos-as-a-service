<script>
  import { onMount, tick } from 'svelte';
  import { get } from 'svelte/store';
  import { browser } from '$app/environment';
  import { _ } from 'svelte-i18n';
  import MapView from '$lib/components/MapView.svelte';
  import { casalsFrontendUrl } from '$lib/architecture-link.js';
  import { registryRuntimeFlags } from '$lib/stores/registryRuntimeFlags.js';
  import RegistryHeader from '$lib/components/RegistryHeader.svelte';
  import RegistryEdgeTabs from '$lib/components/RegistryEdgeTabs.svelte';
  import RegistryKpiLine from '$lib/components/RegistryKpiLine.svelte';
  import RealmPanel from '$lib/components/RealmPanel.svelte';
  import RegistryFooter from '$lib/components/RegistryFooter.svelte';
  import RegistryMobileChrome from '$lib/components/RegistryMobileChrome.svelte';
  import RegistryTour from '$lib/components/RegistryTour.svelte';
  import GlobeWireframeLoader from '$lib/components/GlobeWireframeLoader.svelte';
  import { fetchRealmDetails, fetchZoneData } from '$lib/globe/zone-fetcher.js';
  import { DUMMY_REALMS, DUMMY_ZONE_DATA } from '$lib/globe/dummy-realms.js';
  import { filterAndSortRealms } from '$lib/realm-utils.js';
  import { realmPanelChrome } from '$lib/realm-panel-chrome.js';
  import { assistantChrome } from '$lib/assistant-chrome.js';
  import { mapShellInsets } from '$lib/map-shell-insets.js';
  import { syncAuthSession, authSession } from '$lib/stores/authSession.js';
  
  let backend;
  let realms = [];
  let filteredRealms = [];
  let realmZoneData = {};
  let loading = true;
  let globeLoading = true;
  let error = null;
  let searchQuery = '';
  let debouncedSearchQuery = '';
  let filterStage = '';
  let sortBy = 'users_desc';
  let panelOpen = false;
  let selectedRealmId = null;
  let activeManifestoRealm = null;

  let isLoggedIn = false;
  let userPrincipal = null;
  let authLoading = true;

  let commitHash = '';
  let commitDatetime = '';
  let version = '';
  
  /** @type {import('$lib/components/MapView.svelte').default | null} */
  let mapView = null;
  let searchInput = null;
  let desktopLayout = true;
  let pageOverlayShown = true;
  let pageOverlayFade = false;
  /** @type {ReturnType<typeof setTimeout> | null} */
  let pageOverlayFadeTimer = null;

  $: mapInsets = mapShellInsets($realmPanelChrome, $assistantChrome, desktopLayout);
  $: mapShellTransition =
    !$realmPanelChrome.resizing && !$assistantChrome.resizing;

  $: if (loading) {
    pageOverlayShown = true;
    pageOverlayFade = false;
    if (pageOverlayFadeTimer) {
      clearTimeout(pageOverlayFadeTimer);
      pageOverlayFadeTimer = null;
    }
  } else if (pageOverlayShown && !pageOverlayFade) {
    pageOverlayFade = true;
    pageOverlayFadeTimer = setTimeout(() => {
      pageOverlayShown = false;
      pageOverlayFade = false;
      pageOverlayFadeTimer = null;
    }, 420);
  }

  $: casalsUrl = casalsFrontendUrl($registryRuntimeFlags.casalsFrontendCanisterId);

  function isLocalDevelopment() {
    return (
      typeof window !== 'undefined' &&
      (window.location.hostname.includes('localhost') ||
        window.location.hostname.includes('127.0.0.1'))
    );
  }

  function applyFilters() {
    filteredRealms = filterAndSortRealms(realms, debouncedSearchQuery, filterStage, sortBy);
  }

  $: debouncedSearchQuery, filterStage, sortBy, realms, applyFilters();

  let searchDebounceTimer;
  $: {
    clearTimeout(searchDebounceTimer);
    searchDebounceTimer = setTimeout(() => {
      debouncedSearchQuery = searchQuery;
    }, 150);
  }

  async function loadRealms() {
    try {
      loading = true;
      error = null;
      const response = await backend.list_realms();
      realms = response || [];

      // Local empty registry: inject demo realms so the globe can be previewed
      const useDummy = isLocalDevelopment() && realms.length === 0;
      if (useDummy) {
        realms = DUMMY_REALMS.map((r) => ({ ...r }));
        filteredRealms = realms;
        loading = false;
        realmZoneData = { ...DUMMY_ZONE_DATA };
        globeLoading = false;
        return;
      }

      filteredRealms = realms;
      // Paint the globe as soon as the registry directory is back. Details and
      // zone hexes fill in afterwards — do not hold the wireframe overlay.
      loading = false;
      globeLoading = false;

      void hydrateRealmDetailsAndZones(realms);
    } catch (err) {
      error = err.message || 'Failed to load realms';
      loading = false;
      globeLoading = false;

      // Still show demo data locally if backend fails
      if (isLocalDevelopment() && realms.length === 0) {
        realms = DUMMY_REALMS.map((r) => ({ ...r }));
        filteredRealms = realms;
        realmZoneData = { ...DUMMY_ZONE_DATA };
        error = null;
      }
    }
  }

  async function hydrateRealmDetailsAndZones(currentRealms) {
    try {
      const [details, zones] = await Promise.all([
        fetchRealmDetails(currentRealms),
        fetchZoneData(currentRealms),
      ]);
      details.forEach(({ id, users_count, manifesto, realm_name, realm_stage }) => {
        realms = realms.map((r) =>
          r.id === id ? { ...r, users_count, manifesto, realm_name, realm_stage } : r
        );
      });
      realmZoneData = zones;
    } catch (err) {
      console.warn('Background realm hydrate failed:', err?.message || err);
    }
  }

  async function selectRealm(realmId) {
    selectedRealmId = realmId;
    const panelWasOpen = panelOpen;
    panelOpen = true;
    await tick();
    const realm = filteredRealms.find((r) => r.id === realmId);
    if (realm && mapView) {
      mapView.flyToRealm(realm, { waitForInset: !panelWasOpen });
    }
  }

  function acceptSearch() {
    // Use live query (not debounced) so Enter matches what the user typed
    const matches = filterAndSortRealms(realms, searchQuery, filterStage, sortBy);
    filteredRealms = matches;
    debouncedSearchQuery = searchQuery;
    if (matches[0]) {
      selectRealm(matches[0].id);
    } else {
      panelOpen = true;
    }
  }

  function handleMapSelect(event) {
    selectRealm(event.detail.realmId);
  }

  function handlePanelSelect(event) {
    selectRealm(event.detail.realm.id);
  }

  function handleKeydown(e) {
    if (e.key === '/' && document.activeElement !== searchInput) {
      e.preventDefault();
      panelOpen = true;
      tick().then(() => searchInput?.focus());
    }
  }

  async function handleLogin() {
    const { login } = await import('$lib/auth.js');
    const result = await login();
    if (result?.principal) {
      isLoggedIn = true;
      userPrincipal = result.principal;
    }
  }

  async function handleLogout() {
    const { logout } = await import('$lib/auth.js');
    await logout();
    isLoggedIn = false;
    userPrincipal = null;
  }

  async function syncAuthState() {
    await syncAuthSession();
    const session = get(authSession);
    isLoggedIn = session.isLoggedIn;
    userPrincipal = session.principal;
    authLoading = session.loading;
  }

  onMount(async () => {
    if (!browser) return;

    const layoutMq = window.matchMedia('(min-width: 768px)');
    const syncLayout = () => {
      desktopLayout = layoutMq.matches;
    };
    syncLayout();
    layoutMq.addEventListener('change', syncLayout);

    window.addEventListener('keydown', handleKeydown);

    const { backend: b } = await import('$lib/canisters');
    backend = b;
    await loadRealms();

    const commitHashMeta = document.querySelector('meta[name="commit-hash"]');
    if (commitHashMeta) {
      commitHash = commitHashMeta.getAttribute('content') || '';
      if (commitHash && commitHash !== 'COMMIT_HASH_PLACEHOLDER' && commitHash.length > 7) {
        commitHash = commitHash.substring(0, 7);
      }
    }

    const commitDatetimeMeta = document.querySelector('meta[name="commit-datetime"]');
    if (commitDatetimeMeta) {
      commitDatetime = commitDatetimeMeta.getAttribute('content') || '';
    }

    const versionMeta = document.querySelector('meta[name="version"]');
    if (versionMeta) {
      version = versionMeta.getAttribute('content') || '';
    }

    if (!version || version === 'VERSION_PLACEHOLDER') {
      version = typeof __BUILD_VERSION__ !== 'undefined' ? __BUILD_VERSION__ : 'dev';
    }
    if (!commitHash || commitHash === 'COMMIT_HASH_PLACEHOLDER') {
      commitHash = typeof __BUILD_COMMIT__ !== 'undefined' ? __BUILD_COMMIT__ : 'local';
    }
    if (!commitDatetime || commitDatetime === 'COMMIT_DATETIME_PLACEHOLDER') {
      commitDatetime =
        typeof __BUILD_TIME__ !== 'undefined'
          ? __BUILD_TIME__
          : new Date().toISOString().replace('T', ' ').substring(0, 19);
    }

    await syncAuthState();

    return () => {
      if (pageOverlayFadeTimer) clearTimeout(pageOverlayFadeTimer);
      layoutMq.removeEventListener('change', syncLayout);
      window.removeEventListener('keydown', handleKeydown);
      clearTimeout(searchDebounceTimer);
    };
  });
</script>

<svelte:head>
  <title>{$_('page_title')}</title>
</svelte:head>

<div class="registry-page">
  <RegistryHeader
    {isLoggedIn}
    {userPrincipal}
    {authLoading}
    {casalsUrl}
    on:login={handleLogin}
    on:logout={handleLogout}
  />

  <RegistryEdgeTabs
    {panelOpen}
    on:togglePanel={() => (panelOpen = !panelOpen)}
  />

  {#if error}
    <div class="error-banner">
      <span>{error}</span>
      <button on:click={() => (error = null)} aria-label="Dismiss">✕</button>
    </div>
  {/if}

  <main
    class="map-shell"
    class:map-shell-transition={mapShellTransition}
    style="--map-inset-left: {mapInsets.left}px; --map-inset-right: {mapInsets.right}px"
  >
    <MapView
      bind:this={mapView}
      realms={filteredRealms}
      {realmZoneData}
      searchQuery={debouncedSearchQuery}
      loading={globeLoading}
      on:select={handleMapSelect}
    />
    {#if pageOverlayShown}
      <div class="page-loading" class:fade-out={pageOverlayFade} aria-busy={!pageOverlayFade}>
        <GlobeWireframeLoader size={56} />
      </div>
    {/if}
    {#if !loading}
      <RegistryKpiLine realms={filteredRealms} {realmZoneData} />
    {/if}
  </main>

  <RealmPanel
    open={panelOpen}
    realms={filteredRealms}
    {selectedRealmId}
    bind:filterStage
    bind:sortBy
    bind:searchQuery
    bind:searchInput
    on:close={() => (panelOpen = false)}
    on:filter={applyFilters}
    on:search={applyFilters}
    on:acceptSearch={acceptSearch}
    on:select={handlePanelSelect}
    on:manifesto={(e) => (activeManifestoRealm = e.detail.realm)}
  />

  <RegistryMobileChrome
    {panelOpen}
    realms={filteredRealms}
    {realmZoneData}
    {version}
    {commitHash}
    on:togglePanel={() => (panelOpen = !panelOpen)}
  />

  <RegistryFooter {version} {commitHash} {commitDatetime} />

  <RegistryTour bind:panelOpen />
              </div>
              
{#if activeManifestoRealm}
  <div
    class="manifesto-overlay"
    role="dialog"
    aria-modal="true"
    on:click={() => (activeManifestoRealm = null)}
    on:keydown={(e) => e.key === 'Escape' && (activeManifestoRealm = null)}
  >
    <div class="manifesto-modal" on:click|stopPropagation role="document">
      <button class="manifesto-close" on:click={() => (activeManifestoRealm = null)} aria-label="Close">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 6L6 18M6 6l12 12"></path>
                    </svg>
                  </button>
      <h3>{activeManifestoRealm.name || activeManifestoRealm.realm_name}</h3>
      <p>{activeManifestoRealm.manifesto}</p>
          </div>
        </div>
      {/if}

<style>
  :global(body) {
    margin: 0;
    padding: 0;
    font-family: var(--font-family);
    background: var(--bg);
    color: var(--text-primary);
    /* Do not set overflow:hidden on body — it leaks across SPA navigations
       and blocks scrolling on /deploy-gos and /my-dashboard. */
  }

  .registry-page {
    position: relative;
    width: 100vw;
    height: 100vh;
    overflow: hidden;
    overscroll-behavior: none;
    background: var(--bg);
  }

  .map-shell {
    position: absolute;
    top: 0;
    bottom: 0;
    left: var(--map-inset-left, 0px);
    right: var(--map-inset-right, 0px);
  }

  .map-shell.map-shell-transition {
    transition: left 0.25s ease, right 0.25s ease;
  }

  .page-loading {
    position: absolute;
    inset: 0;
    z-index: 5;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(250, 250, 250, 0.85);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    opacity: 1;
    transition: opacity 0.42s ease-out;
    pointer-events: none;
  }

  .page-loading.fade-out {
    opacity: 0;
  }

  @media (prefers-reduced-motion: reduce) {
    .page-loading {
      transition: none;
    }

    .page-loading.fade-out {
      display: none;
    }
  }

  .error-banner {
    position: fixed;
    top: 1rem;
    left: 50%;
    transform: translateX(-50%);
    z-index: 200;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.625rem 1rem;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
    font-size: 0.875rem;
    color: var(--text-primary);
  }

  .error-banner button {
    border: none;
    background: transparent;
    cursor: pointer;
    color: var(--text-tertiary);
    padding: 0;
  }

  .manifesto-overlay {
    position: fixed;
    inset: 0;
    z-index: 300;
    display: flex;
    align-items: center;
    justify-content: center;
    background: rgba(0, 0, 0, 0.3);
    padding: 1rem;
  }
  
  .manifesto-modal {
    position: relative;
    max-width: 480px;
    width: 100%;
    max-height: 80vh;
    overflow-y: auto;
    padding: 1.5rem;
    background: var(--surface);
    border-radius: 12px;
    border: 1px solid var(--border);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
    font-family: var(--font-family);
  }

  .manifesto-modal h3 {
    margin: 0 0 0.75rem;
    font-size: 1.125rem;
    color: var(--text-primary);
  }

  .manifesto-modal p {
    margin: 0;
    font-size: 0.9375rem;
    line-height: 1.6;
    color: var(--text-secondary);
    white-space: pre-wrap;
  }

  .manifesto-close {
    position: absolute;
    top: 0.75rem;
    right: 0.75rem;
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .manifesto-close:hover {
    background: var(--surface-2);
  }
</style>
