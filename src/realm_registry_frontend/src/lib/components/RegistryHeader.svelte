<script>
  import { createEventDispatcher, onMount } from 'svelte';
  import { _, locale } from 'svelte-i18n';
  import { supportedLocales, setLocale } from '$lib/i18n';
  import { requestRegistryTour } from '$lib/registry-tour.js';
  import { authSession } from '$lib/stores/authSession.js';

  export let isLoggedIn = false;
  export let userPrincipal = null;
  export let authLoading = false;
  export let marketplaceUrl = '';
  export let casalsUrl = '';

  const dispatch = createEventDispatcher();
  const CASALS_FALLBACK_URL = 'https://mcqbx-hyaaa-aaaaj-qsarq-cai.icp0.io';

  $: architectureUrl = casalsUrl || CASALS_FALLBACK_URL;

  let showHub = false;
  let showLanguagePicker = false;
  let showAuthMenu = false;
  let avatarFailed = false;

  $: effectiveLoggedIn = $authSession.isLoggedIn || isLoggedIn;
  $: effectivePrincipal = $authSession.principal ?? userPrincipal;
  $: effectiveAuthLoading = $authSession.loading || authLoading;
  $: principalText = effectivePrincipal?.toText?.() || '';
  $: principalShort = principalText
    ? `${principalText.slice(0, 5)}…${principalText.slice(-3)}`
    : '';
  $: avatarUrl = principalText
    ? `https://api.dicebear.com/9.x/glass/svg?seed=${encodeURIComponent(principalText)}`
    : '';

  $: if (principalText) {
    avatarFailed = false;
  }

  function closePopovers() {
    showHub = false;
    showLanguagePicker = false;
    showAuthMenu = false;
  }

  function toggleHub() {
    showHub = !showHub;
    if (showHub) {
      showAuthMenu = false;
    } else {
      showLanguagePicker = false;
    }
  }

  function openTour() {
    closePopovers();
    requestRegistryTour();
  }

  function onDocClick(e) {
    const keepOpen = e.target?.closest?.('.registry-header');
    if (!keepOpen) closePopovers();
  }

  function onDocKeydown(e) {
    if (e.key !== 'Escape') return;
    if (!showHub && !showAuthMenu) return;
    e.preventDefault();
    closePopovers();
  }

  onMount(() => {
    document.addEventListener('click', onDocClick);
    document.addEventListener('keydown', onDocKeydown);
    return () => {
      document.removeEventListener('click', onDocClick);
      document.removeEventListener('keydown', onDocKeydown);
    };
  });
</script>

<header class="registry-header" aria-label="Main">
  <div class="header-zone header-left">
    <div class="logo-hub" data-tour="top-rail">
      <button
        type="button"
        class="corner-btn"
        class:active={showHub}
        on:click|stopPropagation={toggleHub}
        title={showHub ? $_('hub.close') : $_('hub.open')}
        aria-label={showHub ? $_('hub.close') : $_('hub.open')}
        aria-expanded={showHub}
      >
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <rect x="3" y="3" width="7" height="7" rx="1"></rect>
          <rect x="14" y="3" width="7" height="7" rx="1"></rect>
          <rect x="3" y="14" width="7" height="7" rx="1"></rect>
          <rect x="14" y="14" width="7" height="7" rx="1"></rect>
        </svg>
      </button>

      {#if showHub}
        <nav class="hub-panel" aria-label={$_('hub.open')} on:mousedown|stopPropagation>
          <button type="button" class="hub-item" on:click={openTour}>
            <span class="hub-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
                <circle cx="12" cy="12" r="10"></circle>
                <path d="M9.09 9a3 3 0 1 1 5.82 1c0 2-3 2-3 4"></path>
                <line x1="12" y1="17" x2="12.01" y2="17"></line>
              </svg>
            </span>
            <span class="hub-copy">
              <span class="hub-label">{$_('hub.tour_title')}</span>
            </span>
          </button>

          <a href="/create-realm" class="hub-item" on:click={() => closePopovers()}>
            <span class="hub-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="12" y1="5" x2="12" y2="19"></line>
                <line x1="5" y1="12" x2="19" y2="12"></line>
              </svg>
            </span>
            <span class="hub-copy">
              <span class="hub-label">{$_('controls.create_realm')}</span>
            </span>
          </a>

          {#if marketplaceUrl}
            <a
              href={marketplaceUrl}
              target="_blank"
              rel="noopener noreferrer"
              class="hub-item"
              on:click={() => closePopovers()}
            >
              <span class="hub-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"></path>
                  <line x1="3" y1="6" x2="21" y2="6"></line>
                  <path d="M16 10a4 4 0 0 1-8 0"></path>
                </svg>
              </span>
              <span class="hub-copy">
                <span class="hub-label">{$_('controls.marketplace')}</span>
              </span>
            </a>
          {/if}

          <a
            href={architectureUrl}
            target="_blank"
            rel="noopener noreferrer"
            class="hub-item"
            on:click={() => closePopovers()}
          >
            <span class="hub-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="6" y1="18" x2="6" y2="11"></line>
                <line x1="10" y1="18" x2="10" y2="11"></line>
                <line x1="14" y1="18" x2="14" y2="11"></line>
                <line x1="18" y1="18" x2="18" y2="11"></line>
                <line x1="2" y1="21" x2="22" y2="21"></line>
                <line x1="4" y1="18" x2="20" y2="18"></line>
                <path d="M12 3v5"></path>
                <path d="M8 8h8"></path>
              </svg>
            </span>
            <span class="hub-copy">
              <span class="hub-label">{$_('controls.architecture')}</span>
            </span>
          </a>

          <button
            type="button"
            class="hub-item"
            class:expanded={showLanguagePicker}
            on:click|stopPropagation={() => {
              showLanguagePicker = !showLanguagePicker;
            }}
          >
            <span class="hub-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <path d="m5 8 6 6"></path>
                <path d="m4 14 6-6 2-3"></path>
                <path d="M2 5h12"></path>
                <path d="M7 2v3"></path>
                <path d="m14 19 5-10 5 10"></path>
                <path d="m15 15h6"></path>
              </svg>
            </span>
            <span class="hub-copy">
              <span class="hub-label">{$_('language.select')}</span>
            </span>
          </button>

          {#if showLanguagePicker}
            <div class="hub-locales" role="group" aria-label={$_('language.select')}>
              {#each supportedLocales as loc (loc.id)}
                <button
                  type="button"
                  class="locale-chip"
                  class:active={$locale === loc.id}
                  on:click|stopPropagation={() => {
                    setLocale(loc.id);
                  }}
                >
                  {loc.name}
                </button>
              {/each}
            </div>
          {/if}
        </nav>
      {/if}
    </div>
  </div>

  <div class="header-zone header-right">
    <div class="auth-item">
      {#if effectiveAuthLoading}
        <div class="corner-btn corner-loading" aria-hidden="true"></div>
      {:else}
        <button
          type="button"
          class="corner-btn auth-btn"
          class:auth-btn-avatar={effectiveLoggedIn}
          class:active={showAuthMenu}
          on:click|stopPropagation={() => {
            showAuthMenu = !showAuthMenu;
            if (showAuthMenu) {
              showHub = false;
              showLanguagePicker = false;
            }
          }}
          title={effectiveLoggedIn ? principalText || $_('auth.account') : $_('auth.login')}
          aria-label={effectiveLoggedIn ? $_('auth.account') : $_('auth.login')}
          aria-expanded={showAuthMenu}
        >
          {#if effectiveLoggedIn}
            {#if avatarUrl && !avatarFailed}
              <img
                src={avatarUrl}
                alt=""
                class="auth-avatar"
                width="40"
                height="40"
                on:error={() => (avatarFailed = true)}
              />
            {:else}
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                <circle cx="12" cy="7" r="4"></circle>
              </svg>
            {/if}
          {:else}
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
              <circle cx="12" cy="7" r="4"></circle>
            </svg>
          {/if}
        </button>

        {#if showAuthMenu}
          <div class="auth-menu" role="menu" on:mousedown|stopPropagation>
            {#if effectiveLoggedIn}
              {#if principalShort}
                <div class="menu-meta" title={principalText}>{$_('auth.signed_in')}: {principalShort}</div>
              {/if}
              <a
                href="/my-dashboard"
                class="menu-option"
                role="menuitem"
                on:click={() => (showAuthMenu = false)}
              >
                {$_('dashboard.title')}
              </a>
              <button
                type="button"
                class="menu-option menu-option-danger"
                role="menuitem"
                on:click={() => {
                  showAuthMenu = false;
                  dispatch('logout');
                }}
              >
                {$_('auth.logout')}
              </button>
            {:else}
              <button
                type="button"
                class="menu-option menu-option-primary"
                role="menuitem"
                on:click={() => {
                  showAuthMenu = false;
                  dispatch('login');
                }}
              >
                {$_('auth.sign_in_ii')}
              </button>
            {/if}
          </div>
        {/if}
      {/if}
    </div>
  </div>
</header>

<style>
  .registry-header {
    position: fixed;
    top: var(--test-mode-banner-height, 0px);
    left: 0;
    right: 0;
    z-index: 200;
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    padding: 1rem;
    pointer-events: none;
  }

  .header-zone {
    pointer-events: auto;
    position: relative;
    flex-shrink: 0;
  }

  .logo-hub {
    display: flex;
    align-items: flex-start;
    gap: 0.65rem;
    max-width: min(92vw, 360px);
  }

  .corner-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 60px;
    height: 60px;
    padding: 0;
    border: none;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.38);
    color: #171717;
    cursor: pointer;
    text-decoration: none;
    border: 1px solid rgba(255, 255, 255, 0.55);
    backdrop-filter: blur(14px);
    -webkit-backdrop-filter: blur(14px);
    box-shadow:
      0 4px 20px rgba(0, 0, 0, 0.06),
      inset 0 1px 0 rgba(255, 255, 255, 0.65);
    transition:
      background 0.2s ease,
      transform 0.2s ease,
      color 0.2s ease,
      box-shadow 0.2s ease;
    flex-shrink: 0;
  }

  .corner-btn :global(svg) {
    width: 24px;
    height: 24px;
  }

  .corner-btn:hover {
    background: rgba(255, 255, 255, 0.52);
    transform: scale(1.03);
    box-shadow:
      0 6px 24px rgba(0, 0, 0, 0.08),
      inset 0 1px 0 rgba(255, 255, 255, 0.75);
  }

  .corner-btn.active {
    background: rgba(255, 255, 255, 0.58);
    color: #0a0a0a;
    box-shadow:
      0 8px 28px rgba(0, 0, 0, 0.1),
      inset 0 1px 0 rgba(255, 255, 255, 0.8);
  }

  .hub-panel {
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
    min-width: 280px;
    max-width: min(80vw, 340px);
    padding: 0.65rem;
    border-radius: 18px;
    border: 1px solid rgba(255, 255, 255, 0.22);
    background: transparent;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.06);
    backdrop-filter: blur(18px) saturate(1.2);
    -webkit-backdrop-filter: blur(18px) saturate(1.2);
    animation: hub-in 0.22s cubic-bezier(0.22, 1, 0.36, 1);
  }

  @keyframes hub-in {
    from {
      opacity: 0;
      transform: translateX(-6px) scale(0.98);
    }
    to {
      opacity: 1;
      transform: translateX(0) scale(1);
    }
  }

  .hub-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    width: 100%;
    padding: 0.6rem 0.65rem;
    border: none;
    border-radius: 12px;
    background: transparent;
    color: #171717;
    text-align: left;
    text-decoration: none;
    cursor: pointer;
    font-family: inherit;
    transition:
      background 0.18s ease,
      transform 0.18s ease;
  }

  .hub-item:hover,
  .hub-item.expanded {
    background: rgba(255, 255, 255, 0.14);
    transform: translateX(1px);
  }

  .hub-icon {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 40px;
    height: 40px;
    border-radius: 11px;
    background: rgba(255, 255, 255, 0.12);
    border: 1px solid rgba(255, 255, 255, 0.2);
    color: #262626;
    flex-shrink: 0;
  }

  .hub-icon :global(svg) {
    width: 20px;
    height: 20px;
  }

  .hub-copy {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    min-width: 0;
  }

  .hub-label {
    font-size: 0.9375rem;
    font-weight: 600;
    color: #141414;
    line-height: 1.25;
    letter-spacing: -0.01em;
  }

  .hub-locales {
    display: flex;
    flex-wrap: wrap;
    gap: 0.35rem;
    padding: 0.2rem 0.55rem 0.45rem;
    border-top: 1px solid rgba(255, 255, 255, 0.18);
    margin-top: 0.15rem;
  }

  .locale-chip {
    padding: 0.35rem 0.6rem;
    border: 1px solid rgba(255, 255, 255, 0.25);
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.1);
    font-size: 0.75rem;
    font-family: inherit;
    color: #262626;
    cursor: pointer;
    backdrop-filter: blur(8px);
  }

  .locale-chip:hover,
  .locale-chip.active {
    background: rgba(23, 23, 23, 0.82);
    border-color: rgba(23, 23, 23, 0.9);
    color: #fafafa;
  }

  .auth-btn {
    position: relative;
  }

  .auth-btn-avatar {
    background: transparent;
    border: none;
    box-shadow: none;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }

  .auth-btn-avatar:hover,
  .auth-btn-avatar.active {
    background: transparent;
    transform: scale(1.05);
    box-shadow: none;
  }

  .auth-avatar {
    display: block;
    width: 40px;
    height: 40px;
    border-radius: 50%;
    object-fit: cover;
    pointer-events: none;
  }

  .auth-menu {
    position: absolute;
    top: calc(100% + 0.5rem);
    right: 0;
    z-index: 230;
    min-width: 220px;
    padding: 0.4rem;
    background: rgba(255, 255, 255, 0.36);
    border: 1px solid rgba(255, 255, 255, 0.42);
    border-radius: 14px;
    box-shadow:
      0 14px 36px rgba(0, 0, 0, 0.1),
      inset 0 1px 0 rgba(255, 255, 255, 0.55);
    backdrop-filter: blur(20px) saturate(1.35);
    animation: hub-in 0.22s cubic-bezier(0.22, 1, 0.36, 1);
  }

  .menu-meta {
    padding: 0.4rem 0.65rem 0.3rem;
    font-size: 0.6875rem;
    color: rgba(38, 38, 38, 0.65);
    font-family: ui-monospace, monospace;
    word-break: break-all;
  }

  .menu-option {
    display: block;
    width: 100%;
    padding: 0.55rem 0.65rem;
    border: none;
    border-radius: 10px;
    background: transparent;
    text-align: left;
    font-size: 0.8125rem;
    font-family: inherit;
    color: #171717;
    text-decoration: none;
    cursor: pointer;
    transition: background 0.15s ease;
  }

  .menu-option:hover {
    background: rgba(255, 255, 255, 0.38);
  }

  .menu-option-primary {
    font-weight: 600;
  }

  .menu-option-danger {
    color: #b91c1c;
  }

  .corner-loading {
    opacity: 0.55;
    animation: pulse 1.2s ease-in-out infinite;
    pointer-events: none;
  }

  @keyframes pulse {
    0%,
    100% {
      opacity: 0.4;
    }
    50% {
      opacity: 0.85;
    }
  }

  @media (max-width: 767px) {
    .logo-hub {
      max-width: none;
    }

    .hub-panel {
      position: fixed;
      left: 50%;
      top: calc(var(--test-mode-banner-height, 0px) + 0.75rem + 56px + 0.55rem);
      transform: translateX(-50%);
      width: min(320px, calc(100vw - 1.5rem));
      min-width: min(280px, calc(100vw - 1.5rem));
      max-width: min(320px, calc(100vw - 1.5rem));
      z-index: 240;
      animation: hub-in-mobile 0.22s cubic-bezier(0.22, 1, 0.36, 1);
    }

    @keyframes hub-in-mobile {
      from {
        opacity: 0;
        transform: translateX(-50%) translateY(-5px) scale(0.98);
      }
      to {
        opacity: 1;
        transform: translateX(-50%) translateY(0) scale(1);
      }
    }
  }

  @media (max-width: 900px) {
    .corner-btn {
      width: 56px;
      height: 56px;
    }
  }

  @media (max-width: 480px) {
    .registry-header {
      padding: 0.75rem;
    }

    .corner-btn {
      width: 44px;
      height: 44px;
    }

    .corner-btn :global(svg) {
      width: 20px;
      height: 20px;
    }

    .hub-panel {
      top: calc(0.75rem + 44px + 0.55rem);
      width: min(300px, calc(100vw - 1.25rem));
      min-width: min(260px, calc(100vw - 1.25rem));
      max-width: min(300px, calc(100vw - 1.25rem));
    }
  }
</style>
