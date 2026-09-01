<script>
  import { onDestroy, onMount, tick } from 'svelte';
  import { get } from 'svelte/store';
  import { browser } from '$app/environment';
  import { _ } from 'svelte-i18n';
  import { requestAssistantOpen, requestAssistantClose } from '$lib/assistant-open.js';
  import { createRegistryTour, registerTourReplay } from '$lib/registry-tour.js';
  import { applyIntroLinks, INTRO_LINKS } from '$lib/intro-links.js';

  /** Bound from parent so the tour can open/close the browse panel. */
  export let panelOpen = false;

  let activeTour = null;
  let introOpen = false;

  function isMobile() {
    return window.matchMedia('(max-width: 767px)').matches;
  }

  function translate(key) {
    return get(_)(key);
  }

  function destroyActiveTour() {
    activeTour?.destroy();
    activeTour = null;
  }

  function openIntro() {
    if (!browser) return;
    destroyActiveTour();
    introOpen = true;
  }

  function closeIntro() {
    introOpen = false;
  }

  function handleIntroKeydown(event) {
    if (!introOpen) return;
    if (event.key === 'Escape') closeIntro();
  }

  async function continueFromIntro() {
    introOpen = false;
    await runTour();
  }

  async function runTour() {
    if (!browser) return;

    destroyActiveTour();

    panelOpen = false;
    requestAssistantClose();
    await tick();

    const tour = createRegistryTour({
      t: translate,
      isMobile,
      actions: {
        openPanel: async () => {
          panelOpen = true;
          await tick();
        },
        closePanel: async () => {
          panelOpen = false;
          await tick();
        },
        closeAssistant: async () => {
          requestAssistantClose();
          await tick();
        },
        openAssistant: async () => {
          requestAssistantOpen();
          await tick();
          await new Promise((resolve) => setTimeout(resolve, 450));
        },
      },
      onComplete: () => {
        activeTour = null;
      },
    });

    activeTour = tour;
    tour.start();
  }

  onMount(() => {
    registerTourReplay(openIntro);
  });

  onDestroy(() => {
    destroyActiveTour();
    registerTourReplay(null);
  });
</script>

<svelte:window on:keydown={handleIntroKeydown} />

{#if introOpen}
  <div class="intro-overlay-wrap">
    <button type="button" class="intro-backdrop" aria-label={$_('tour.intro_close')} on:click={closeIntro}></button>
    <div
      class="intro-dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="registry-tour-intro-title"
    >
      <button
        type="button"
        class="intro-close"
        on:click={closeIntro}
        aria-label={$_('tour.intro_close')}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 6L6 18M6 6l12 12"></path>
        </svg>
      </button>

      <h2 id="registry-tour-intro-title" class="intro-title">{$_('tour.intro_title')}</h2>
      <p class="intro-lead">
        {@html applyIntroLinks($_('tour.intro_lead'), {
          ggg: { href: INTRO_LINKS.ggg, label: $_('tour.intro_ggg') },
        })}
      </p>
      <p class="intro-body">
        {@html applyIntroLinks($_('tour.intro_body'), {
          realm: { href: INTRO_LINKS.realm, label: $_('tour.intro_realm') },
        })}
      </p>
      <p class="intro-learn">{$_('tour.intro_learn_more')}</p>
      <p class="intro-sites">
        <a
          class="intro-link"
          href={INTRO_LINKS.ssc}
          target="_blank"
          rel="noopener noreferrer"
        >{$_('tour.intro_link_ssc')}</a>
        <a
          class="intro-link"
          href={INTRO_LINKS.ic}
          target="_blank"
          rel="noopener noreferrer"
        >{$_('tour.intro_link_ic')}</a>
      </p>
      <p class="intro-join">{$_('tour.intro_join')}</p>

      <div class="intro-actions">
        <button type="button" class="intro-btn intro-btn-primary" on:click={continueFromIntro}>
          {$_('tour.intro_continue')}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .intro-overlay-wrap {
    position: fixed;
    inset: 0;
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    animation: introFadeIn 0.15s ease-out;
  }

  .intro-backdrop {
    position: absolute;
    inset: 0;
    border: none;
    padding: 0;
    margin: 0;
    background: rgba(0, 0, 0, 0.45);
    backdrop-filter: blur(2px);
    cursor: default;
  }

  .intro-dialog {
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 36rem;
    background: var(--surface, #fff);
    border: 1px solid var(--border, #e5e5e5);
    border-radius: 0.875rem;
    padding: 1.5rem 1.5rem 1.25rem;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    font-family: var(--font-family);
    animation: introSlideUp 0.2s ease-out;
  }

  .intro-close {
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

  .intro-close:hover {
    background: var(--surface-2);
  }

  .intro-title {
    margin: 0 2rem 0.75rem 0;
    font-size: 1.125rem;
    font-weight: 700;
    line-height: 1.3;
    color: var(--text-primary);
  }

  .intro-lead {
    margin: 0 0 0.875rem;
    font-size: 0.9375rem;
    font-weight: 600;
    line-height: 1.55;
    color: var(--text-primary);
  }

  .intro-body,
  .intro-learn,
  .intro-join {
    margin: 0 0 0.875rem;
    font-size: 0.9375rem;
    line-height: 1.6;
    color: var(--text-secondary);
  }

  .intro-learn {
    margin-bottom: 0.35rem;
  }

  .intro-sites {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.2rem;
    margin: 0 0 0.875rem;
    font-size: 0.9375rem;
    line-height: 1.6;
  }

  .intro-link,
  .intro-lead :global(.intro-inline-link),
  .intro-body :global(.intro-inline-link) {
    font-size: inherit;
    line-height: inherit;
    color: var(--text-primary);
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .intro-link:hover,
  .intro-lead :global(.intro-inline-link:hover),
  .intro-body :global(.intro-inline-link:hover) {
    color: var(--text-secondary);
  }

  .intro-actions {
    display: flex;
    justify-content: center;
    margin-top: 1.25rem;
  }

  .intro-btn {
    min-width: 8.5rem;
    padding: 0.5rem 1.5rem;
    border-radius: 0.5rem;
    font-family: var(--font-family);
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    border: 1px solid transparent;
  }

  .intro-btn-primary {
    background: var(--text-primary, #171717);
    color: var(--surface, #fff);
  }

  .intro-btn-primary:hover {
    filter: brightness(1.05);
  }

  @keyframes introFadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  @keyframes introSlideUp {
    from {
      opacity: 0;
      transform: translateY(12px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  :global(.registry-tour-popover) {
    font-family: var(--font-family);
    color: var(--text-primary);
  }

  :global(.registry-tour-popover .driver-popover-title) {
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  :global(.registry-tour-popover .driver-popover-description) {
    font-size: 0.8125rem;
    line-height: 1.5;
    color: var(--text-secondary);
  }

  :global(.registry-tour-popover .driver-popover-progress-text) {
    font-size: 0.6875rem;
    color: var(--text-faint);
  }

  :global(.registry-tour-popover button) {
    font-family: var(--font-family);
    font-size: 0.75rem;
    text-shadow: none;
  }

  :global(.driver-active-element) {
    pointer-events: none !important;
  }
</style>
