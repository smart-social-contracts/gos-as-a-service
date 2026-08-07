<script>
  import { createEventDispatcher, onMount, tick } from 'svelte';
  import { _ } from 'svelte-i18n';
  import RealmCard from './RealmCard.svelte';
  import { realmPanelChrome } from '$lib/realm-panel-chrome.js';
  import { loadRealmPanelWidth, saveRealmPanelWidth } from '$lib/realm-panel-prefs.js';
  import { clampPanelWidth, defaultPanelWidth } from '$lib/panel-width.js';
  import { REALM_STAGES, stageMeta } from '$lib/realm-stages.js';

  export let open = false;
  export let realms = [];
  export let selectedRealmId = null;
  export let filterStage = '';
  export let sortBy = 'users_desc';
  export let searchQuery = '';
  /** @type {HTMLInputElement | null} */
  export let searchInput = null;

  const dispatch = createEventDispatcher();

  let panelEl;
  let listEl;
  let panelWidth = defaultPanelWidth();
  let isResizing = false;
  let showStageMenu = false;

  $: selectedStage = stageMeta(filterStage);

  $: if (open && selectedRealmId) {
    scrollToSelected();
  }

  $: syncPanelChrome(), open, panelWidth, isResizing;

  function syncPanelChrome() {
    realmPanelChrome.set({ open, width: panelWidth, resizing: isResizing });
  }

  async function scrollToSelected() {
    await tick();
    if (!listEl || !selectedRealmId) return;
    const card = listEl.querySelector(`[data-realm-id="${selectedRealmId}"]`);
    card?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function handleKeydown(e) {
    if (e.key === 'Escape' && open) {
      dispatch('close');
    }
  }

  function handleSearchKeydown(e) {
    if (e.key === 'Escape' && showStageMenu) {
      showStageMenu = false;
      return;
    }
    if (e.key === 'Enter') {
      e.preventDefault();
      dispatch('acceptSearch');
    }
  }

  function selectStage(stageId) {
    filterStage = stageId;
    showStageMenu = false;
    dispatch('filter');
  }

  function onStageMenuDocClick(e) {
    if (!showStageMenu) return;
    if (e.target?.closest?.('.stage-filter')) return;
    showStageMenu = false;
  }

  function onResizeStart(event) {
    if (typeof window !== 'undefined' && window.innerWidth < 768) return;
    event.preventDefault();
    event.stopPropagation();
    isResizing = true;
    syncPanelChrome();
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    const startX = event.clientX;
    const startWidth = panelWidth;

    const onMove = (e) => {
      const delta = e.clientX - startX;
      panelWidth = clampPanelWidth(startWidth + delta);
      syncPanelChrome();
    };

    const onUp = (e) => {
      isResizing = false;
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      panelWidth = clampPanelWidth(panelWidth);
      saveRealmPanelWidth(panelWidth);
      syncPanelChrome();
      handle.releasePointerCapture(e.pointerId);
      handle.removeEventListener('pointermove', onMove);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
    };

    handle.addEventListener('pointermove', onMove);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  }

  onMount(() => {
    panelWidth = clampPanelWidth(loadRealmPanelWidth(defaultPanelWidth()));
    syncPanelChrome();
    window.addEventListener('keydown', handleKeydown);
    document.addEventListener('click', onStageMenuDocClick);
    return () => {
      window.removeEventListener('keydown', handleKeydown);
      document.removeEventListener('click', onStageMenuDocClick);
    };
  });
</script>

{#if open}
  <button class="panel-backdrop" aria-label="Close panel" on:click={() => dispatch('close')}></button>
{/if}

<aside
  class="realm-panel"
  data-tour="realm-panel"
  class:open
  class:resizing={isResizing}
  style="width: {panelWidth}px"
  bind:this={panelEl}
  aria-hidden={!open}
  role="complementary"
  aria-label={$_('globe.browse_realms')}
>
  {#if open}
    <button
      type="button"
      class="resize-handle"
      aria-label="Resize panel"
      on:pointerdown|stopPropagation={onResizeStart}
    ></button>
  {/if}

  <div class="panel-header">
    <h2 class="panel-title">{$_('globe.browse_realms')}</h2>
    <button class="close-btn" on:click={() => dispatch('close')} aria-label="Close">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M18 6L6 18M6 6l12 12"></path>
      </svg>
    </button>
  </div>

  <div class="panel-search">
    <svg class="search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
      <circle cx="11" cy="11" r="8"></circle>
      <path d="m21 21-4.35-4.35"></path>
    </svg>
    <input
      bind:this={searchInput}
      type="text"
      class="search-input"
      placeholder={$_('search.placeholder')}
      aria-label={$_('search.placeholder')}
      bind:value={searchQuery}
      on:input={() => dispatch('search')}
      on:keydown={handleSearchKeydown}
      autocomplete="off"
      spellcheck="false"
    />
    {#if searchQuery}
      <button
        type="button"
        class="clear-btn"
        on:click={() => {
          searchQuery = '';
          dispatch('search');
          searchInput?.focus();
        }}
        aria-label={$_('search.clear')}
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 6L6 18M6 6l12 12"></path>
        </svg>
      </button>
    {/if}
  </div>

  <div class="panel-filters">
    <div class="stage-filter">
      <button
        type="button"
        class="filter-select stage-filter-btn"
        aria-haspopup="listbox"
        aria-expanded={showStageMenu}
        on:click|stopPropagation={() => (showStageMenu = !showStageMenu)}
      >
        {#if selectedStage}
          <span class="stage-swatch" style="background-color: {selectedStage.color}" aria-hidden="true"></span>
          <span class="stage-filter-label" style="color: {selectedStage.color}">{selectedStage.label}</span>
        {:else}
          <span class="stage-filter-label muted">{$_('globe.filter_all_stages')}</span>
        {/if}
        <svg class="filter-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
          <polyline points="6 9 12 15 18 9"></polyline>
        </svg>
      </button>

      {#if showStageMenu}
        <div class="stage-menu" role="listbox" aria-label={$_('globe.filter_all_stages')} on:mousedown|stopPropagation>
          <button
            type="button"
            class="stage-option"
            class:selected={!filterStage}
            role="option"
            aria-selected={!filterStage}
            on:click={() => selectStage('')}
          >
            <span class="stage-filter-label muted">{$_('globe.filter_all_stages')}</span>
          </button>
          {#each REALM_STAGES as stage (stage.id)}
            <button
              type="button"
              class="stage-option"
              class:selected={filterStage === stage.id}
              role="option"
              aria-selected={filterStage === stage.id}
              on:click={() => selectStage(stage.id)}
            >
              <span class="stage-swatch" style="background-color: {stage.color}" aria-hidden="true"></span>
              <span class="stage-filter-label" style="color: {stage.color}">{stage.label}</span>
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <select class="filter-select" bind:value={sortBy} on:change={() => dispatch('filter')}>
      <option value="users_desc">{$_('globe.sort_users_desc')}</option>
      <option value="name">{$_('globe.sort_name')}</option>
      <option value="users_asc">{$_('globe.sort_users_asc')}</option>
      <option value="newest">{$_('globe.sort_newest')}</option>
    </select>
  </div>

  <div class="panel-list" bind:this={listEl}>
    {#if realms.length === 0}
      <div class="empty-panel">
        {#if searchQuery}
          <p>{$_('search.no_results_message', { values: { query: searchQuery } })}</p>
        {:else}
          <p>{$_('empty.message')}</p>
        {/if}
      </div>
    {:else}
      {#each realms as realm (realm.id)}
        <div data-realm-id={realm.id} class="card-wrapper">
          <RealmCard
            {realm}
            selected={selectedRealmId === realm.id}
            on:select={(e) => dispatch('select', e.detail)}
            on:manifesto={(e) => dispatch('manifesto', e.detail)}
          />
        </div>
      {/each}
    {/if}
  </div>
</aside>

<style>
  .panel-backdrop {
    display: none;
    position: fixed;
    inset: 0;
    z-index: 250;
    background: transparent;
    border: none;
    cursor: default;
  }

  .realm-panel {
    position: fixed;
    top: 0;
    left: 0;
    bottom: 0;
    z-index: 260;
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border-right: 1px solid var(--border);
    box-shadow: 4px 0 16px rgba(0, 0, 0, 0.06);
    transform: translateX(-100%);
    transition: transform 0.25s ease;
    font-family: var(--font-family);
  }

  .realm-panel.resizing {
    transition: none;
    user-select: none;
  }

  .realm-panel.open {
    transform: translateX(0);
  }

  .resize-handle {
    position: absolute;
    top: 0;
    right: 0;
    width: 6px;
    height: 100%;
    padding: 0;
    border: none;
    background: transparent;
    cursor: col-resize;
    z-index: 2;
  }

  .resize-handle:hover,
  .realm-panel.resizing .resize-handle {
    background: rgba(0, 0, 0, 0.06);
  }

  .panel-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.875rem 1rem;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .panel-title {
    margin: 0;
    font-size: 0.9375rem;
    font-weight: 600;
    color: var(--text-primary);
  }

  .close-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 32px;
    height: 32px;
    border: none;
    border-radius: 8px;
    background: transparent;
    color: var(--text-secondary);
    cursor: pointer;
  }

  .close-btn:hover {
    background: var(--surface-2);
  }

  .panel-search {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.65rem 1rem;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .search-icon {
    flex-shrink: 0;
    color: var(--text-tertiary);
  }

  .search-input {
    flex: 1;
    min-width: 0;
    height: 32px;
    border: none;
    outline: none;
    background: transparent;
    font-size: 0.875rem;
    font-family: inherit;
    color: var(--text-primary);
  }

  .search-input::placeholder {
    color: var(--text-tertiary);
  }

  .clear-btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border: none;
    border-radius: 50%;
    background: transparent;
    color: var(--text-tertiary);
    cursor: pointer;
    flex-shrink: 0;
  }

  .clear-btn:hover {
    background: var(--surface-2);
    color: var(--text-secondary);
  }

  .panel-filters {
    display: flex;
    gap: 0.5rem;
    padding: 0.75rem 1rem;
    border-bottom: 1px solid var(--border);
    flex-shrink: 0;
  }

  .filter-select {
    flex: 1;
    height: 32px;
    padding: 0 0.5rem;
    border: 1px solid var(--border);
    border-radius: 6px;
    background: var(--surface);
    color: var(--text-secondary);
    font-size: 0.75rem;
    font-family: inherit;
    outline: none;
  }

  .stage-filter {
    position: relative;
    flex: 1;
    min-width: 0;
  }

  .stage-filter-btn {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    width: 100%;
    cursor: pointer;
    text-align: left;
  }

  .stage-filter-label {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-weight: 500;
  }

  .stage-filter-label.muted {
    color: var(--text-secondary);
    font-weight: 400;
  }

  .stage-swatch {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }

  .filter-chevron {
    flex-shrink: 0;
    color: var(--text-tertiary);
  }

  .stage-menu {
    position: absolute;
    top: calc(100% + 4px);
    left: 0;
    right: 0;
    z-index: 5;
    display: flex;
    flex-direction: column;
    padding: 0.25rem;
    border: 1px solid var(--border);
    border-radius: 8px;
    background: var(--surface);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.08);
  }

  .stage-option {
    display: flex;
    align-items: center;
    gap: 0.45rem;
    width: 100%;
    padding: 0.45rem 0.5rem;
    border: none;
    border-radius: 6px;
    background: transparent;
    cursor: pointer;
    text-align: left;
    font-family: inherit;
    font-size: 0.75rem;
  }

  .stage-option:hover,
  .stage-option.selected {
    background: var(--surface-2);
  }

  .panel-list {
    flex: 1;
    overflow-y: auto;
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .card-wrapper {
    flex-shrink: 0;
  }

  .empty-panel {
    padding: 2rem 1rem;
    text-align: center;
    color: var(--text-tertiary);
    font-size: 0.875rem;
  }

  @media (max-width: 767px) {
    .panel-backdrop {
      display: block;
    }

    .realm-panel {
      top: auto;
      left: 0;
      right: 0;
      bottom: 0;
      width: 100% !important;
      max-height: 70vh;
      border-left: none;
      border-top: 1px solid var(--border);
      border-radius: 16px 16px 0 0;
      transform: translateY(100%);
      box-shadow: 0 -4px 16px rgba(0, 0, 0, 0.08);
    }

    .resize-handle {
      display: none;
    }

    .realm-panel.open {
      transform: translateY(0);
    }
  }
</style>
