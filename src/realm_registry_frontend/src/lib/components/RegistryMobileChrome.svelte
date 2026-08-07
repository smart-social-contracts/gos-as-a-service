<script>
  import { createEventDispatcher } from 'svelte';
  import { _ } from 'svelte-i18n';
  import { assistantChrome } from '$lib/assistant-chrome.js';
  import { requestAssistantToggle } from '$lib/assistant-open.js';
  import BrowseEarIcon from '$lib/components/BrowseEarIcon.svelte';
  import { computeKpis } from '$lib/globe/hex-data.js';

  export let panelOpen = false;
  export let realms = [];
  export let realmZoneData = {};
  export let version = '';
  export let commitHash = '';

  const dispatch = createEventDispatcher();

  $: assistantOpen = $assistantChrome.open;
  $: kpis = computeKpis(realms, realmZoneData);
  $: stageLine = (() => {
    const labels = {
      production: 'live',
      beta: 'beta',
      alpha: 'alpha',
      deprecation: 'winding down',
      terminated: 'archived',
    };
    const parts = Object.entries(kpis.stageCounts)
      .filter(([, count]) => count > 0)
      .map(([stage, count]) => `${count} ${labels[stage] || stage}`);
    return parts.length ? parts.join(' · ') : '';
  })();

  $: isLocal =
    typeof window !== 'undefined' &&
    (window.location.hostname === 'localhost' || window.location.hostname.endsWith('.localhost'));

  $: versionLabel = (() => {
    const v = version || 'dev';
    const hash =
      commitHash && commitHash !== 'local' && commitHash !== 'dev' ? ` (${commitHash})` : '';
    const local = isLocal ? ` · ${$_('footer.local_deployment')}` : '';
    return `${v}${hash}${local}`;
  })();

  function togglePanel() {
    dispatch('togglePanel');
  }

  function toggleAssistant() {
    requestAssistantToggle();
  }
</script>

<div class="mobile-chrome registry-mobile-only" aria-label="Mobile navigation">
  <div class="chrome-bottom">
    {#if !panelOpen}
      <button
        type="button"
        class="ear ear-left"
        data-tour="browse-ear-mobile"
        on:click={togglePanel}
        title={$_('globe.browse_realms')}
        aria-label={$_('globe.browse_realms')}
        aria-expanded={false}
      >
        <BrowseEarIcon variant="compass" />
      </button>
    {:else}
      <div class="ear-spacer ear-slot-left" aria-hidden="true"></div>
    {/if}

    <div class="chrome-center" data-tour="mobile-stats" aria-live="polite">
      <div class="center-kpi">
        <span class="kpi-primary">
          {$_('globe.kpi_realms', { values: { count: kpis.totalRealms } })}
          ·
          {$_('globe.kpi_users', { values: { count: kpis.totalUsers } })}
          {#if kpis.locationClusters > 0}
            ·
            {$_('globe.kpi_locations', { values: { count: kpis.locationClusters } })}
          {/if}
        </span>
        {#if stageLine}
          <span class="kpi-stages">{stageLine}</span>
        {/if}
      </div>

      <div class="center-meta">
        <div class="meta-icons">
          <a
            href="https://github.com/smart-social-contracts/realms"
            target="_blank"
            rel="noopener noreferrer"
            class="meta-link"
            aria-label="GitHub"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
            </svg>
          </a>
          <a
            href="https://internetcomputer.org"
            target="_blank"
            rel="noopener noreferrer"
            class="meta-link"
            aria-label={$_('footer.built_on_ic')}
            title={$_('footer.built_on_ic')}
          >
            <img
              src="/images/internet-computer-icp-logo.svg"
              alt=""
              width="16"
              height="16"
              class="ic-logo"
            />
          </a>
        </div>
        <span class="meta-version">{versionLabel}</span>
      </div>
    </div>

    {#if !assistantOpen}
      <button
        type="button"
        class="ear ear-right"
        data-tour="assistant-ear-mobile"
        on:click={toggleAssistant}
        title={$_('assistant.toggle', { default: 'AI Assistant' })}
        aria-label={$_('assistant.toggle', { default: 'AI Assistant' })}
        aria-expanded={false}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"></path>
          <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"></path>
          <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"></path>
          <path d="M12 21v-3"></path>
        </svg>
      </button>
    {:else}
      <div class="ear-spacer ear-slot-right" aria-hidden="true"></div>
    {/if}
  </div>
</div>

<style>
  .mobile-chrome {
    position: fixed;
    left: 0;
    right: 0;
    bottom: 0;
    z-index: 175;
    font-family: var(--font-family);
    pointer-events: none;
    padding-bottom: env(safe-area-inset-bottom, 0);
  }

  .chrome-bottom {
    display: grid;
    grid-template-columns: var(--registry-ear-width-mobile) minmax(0, 1fr) var(--registry-ear-width-mobile);
    align-items: end;
    pointer-events: none;
  }

  .chrome-center {
    grid-column: 2;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.15rem;
    min-width: 0;
    padding: 0.15rem 0.35rem 0.3rem;
    background: transparent;
    pointer-events: auto;
    text-align: center;
  }

  .center-kpi {
    display: flex;
    flex-direction: column;
    gap: 0.05rem;
  }

  .kpi-primary,
  .kpi-stages,
  .meta-version {
    text-shadow:
      0 0 6px rgba(250, 250, 250, 0.95),
      0 1px 2px rgba(255, 255, 255, 0.85);
  }

  .kpi-primary {
    font-size: 0.6875rem;
    color: var(--text-tertiary);
    line-height: 1.35;
  }

  .kpi-stages {
    font-size: 0.625rem;
    color: var(--text-faint);
    line-height: 1.3;
  }

  .center-meta {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.45rem;
    flex-wrap: wrap;
  }

  .meta-icons {
    display: flex;
    align-items: center;
    gap: 0.4rem;
  }

  .meta-link {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    color: var(--text-faint);
    text-decoration: none;
  }

  .meta-link:hover {
    color: var(--text-tertiary);
  }

  .ic-logo {
    display: block;
  }

  .meta-version {
    font-size: 0.625rem;
    color: var(--text-faint);
    white-space: nowrap;
  }

  .ear,
  .ear-spacer {
    grid-row: 1;
    height: var(--registry-ear-height-mobile);
    width: var(--registry-ear-width-mobile);
  }

  .ear-left,
  .ear-slot-left {
    grid-column: 1;
  }

  .ear-right,
  .ear-slot-right {
    grid-column: 3;
  }

  .ear {
    pointer-events: auto;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 0;
    border: 1px solid rgba(229, 229, 229, 0.9);
    border-bottom: none;
    cursor: pointer;
    box-shadow: 0 -2px 10px rgba(0, 0, 0, 0.06);
  }

  .ear :global(svg) {
    width: 18px;
    height: 18px;
  }

  .ear-left {
    background: rgba(17, 17, 17, 0.9);
    color: #ffffff;
    border-left: none;
    border-color: rgba(38, 38, 38, 0.9);
    border-radius: 0 12px 0 0;
  }

  .ear-right {
    background: rgba(17, 17, 17, 0.9);
    color: #ffffff;
    border-right: none;
    border-color: rgba(38, 38, 38, 0.9);
    border-radius: 12px 0 0 0;
  }
</style>
