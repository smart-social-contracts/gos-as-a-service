<script>
  import { createEventDispatcher } from 'svelte';
  import { _ } from 'svelte-i18n';
  import { assistantChrome } from '$lib/assistant-chrome.js';
  import { requestAssistantToggle } from '$lib/assistant-open.js';
  import BrowseEarIcon from '$lib/components/BrowseEarIcon.svelte';

  export let panelOpen = false;

  const dispatch = createEventDispatcher();

  $: assistantOpen = $assistantChrome.open;

  function togglePanel() {
    dispatch('togglePanel');
  }

  function toggleAssistant() {
    requestAssistantToggle();
  }
</script>

{#if !panelOpen}
  <button
    type="button"
    class="edge-tab edge-tab-left registry-desktop-only"
    data-tour="browse-ear-desktop"
    on:click={togglePanel}
    title={$_('globe.browse_realms')}
    aria-label={$_('globe.browse_realms')}
    aria-expanded={false}
  >
    <BrowseEarIcon variant="compass" />
  </button>
{/if}

{#if !assistantOpen}
  <button
    type="button"
    class="edge-tab edge-tab-right registry-desktop-only"
    data-tour="assistant-ear-desktop"
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
{/if}

<style>
  .edge-tab {
    position: fixed;
    top: 50%;
    z-index: 175;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 88px;
    padding: 0;
    border: 1px solid rgba(38, 38, 38, 0.9);
    background: rgba(17, 17, 17, 0.88);
    color: #ffffff;
    cursor: pointer;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
    transition: background 0.15s ease, color 0.15s ease, transform 0.15s ease;
  }

  .edge-tab :global(svg) {
    width: 18px;
    height: 18px;
  }

  .edge-tab:hover {
    transform: translateY(-50%) scale(1.03);
  }

  .edge-tab-left {
    left: 0;
    transform: translateY(-50%);
    border-left: none;
    border-radius: 0 12px 12px 0;
    background: rgba(17, 17, 17, 0.88);
    color: #ffffff;
    border-color: rgba(38, 38, 38, 0.9);
  }

  .edge-tab-left:hover {
    background: rgba(38, 38, 38, 0.95);
  }

  .edge-tab-right {
    right: 0;
    transform: translateY(-50%);
    border-right: none;
    border-radius: 12px 0 0 12px;
    background: rgba(17, 17, 17, 0.88);
    color: #ffffff;
    border-color: rgba(38, 38, 38, 0.9);
  }

  .edge-tab-right:hover {
    background: rgba(38, 38, 38, 0.95);
  }

  @media (max-width: 767px) {
    .edge-tab {
      top: auto;
      bottom: 0;
      width: 48px;
      height: var(--registry-ear-height-mobile, 44px);
      border-bottom: none;
      box-shadow: 0 -2px 12px rgba(0, 0, 0, 0.08);
    }

    .edge-tab :global(svg) {
      width: 18px;
      height: 18px;
    }

    .edge-tab:hover {
      transform: scale(1.03);
    }

    .edge-tab-left {
      left: 0;
      transform: none;
      border-left: none;
      border-radius: 0 12px 0 0;
    }

    .edge-tab-left:hover {
      transform: scale(1.03);
    }

    .edge-tab-right {
      right: 0;
      transform: none;
      border-right: none;
      border-radius: 12px 0 0 0;
    }

    .edge-tab-right:hover {
      transform: scale(1.03);
    }
  }
</style>
