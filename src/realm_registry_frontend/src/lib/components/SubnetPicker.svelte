<script>
  import {
    getSubnetGeo,
    regionFlagGroups,
    subnetGeoTitle,
    subnetShortLabel,
    subnetTypeLabel,
    warmSubnetGeoCache,
  } from '$lib/subnet-geo.js';

  export let subnetIds = [];
  export let value = '';
  export let disabled = false;

  let geoById = {};
  let loadingGeo = false;
  let loadedKey = '';
  let filter = '';
  let copiedId = '';

  $: loadKey = subnetIds.join('|');
  $: if (loadKey && loadKey !== loadedKey) {
    void loadGeo(subnetIds, loadKey);
  }

  $: query = filter.trim().toLowerCase();
  $: visibleIds = query
    ? subnetIds.filter((id) => matchesFilter(id, geoById[id], query))
    : subnetIds;

  async function loadGeo(ids, key) {
    loadingGeo = true;
    try {
      await warmSubnetGeoCache(ids);
      const next = {};
      await Promise.all(
        ids.map(async (id) => {
          next[id] = await getSubnetGeo(id);
        }),
      );
      if (key === loadKey) geoById = next;
    } finally {
      if (key === loadKey) {
        loadedKey = key;
        loadingGeo = false;
      }
    }
  }

  function matchesFilter(id, geo, q) {
    if (id.toLowerCase().includes(q)) return true;
    if (subnetShortLabel(id).toLowerCase().includes(q)) return true;
    if (geo?.subnetType && subnetTypeLabel(geo.subnetType).toLowerCase().includes(q)) return true;
    return (geo?.orderedCountries || []).some(
      (c) => c.name.toLowerCase().includes(q) || c.code.toLowerCase() === q,
    );
  }

  function select(id) {
    if (disabled) return;
    value = id;
  }

  async function copyId(event, id) {
    event.stopPropagation();
    try {
      await navigator.clipboard.writeText(id);
      copiedId = id;
      setTimeout(() => {
        if (copiedId === id) copiedId = '';
      }, 1400);
    } catch {
      /* ignore */
    }
  }
</script>

<div class="picker">
  <div class="toolbar">
    <input
      type="search"
      class="filter"
      placeholder="Filter by country or subnet…"
      bind:value={filter}
      disabled={disabled || loadingGeo}
    />
    <span class="count">
      {#if loadingGeo}
        Loading locations…
      {:else}
        {visibleIds.length}{query ? ` of ${subnetIds.length}` : ''} subnet{visibleIds.length === 1 ? '' : 's'}
      {/if}
    </span>
  </div>

  {#if visibleIds.length === 0}
    <p class="empty">No subnets match that filter.</p>
  {:else}
    <div class="list" role="listbox" aria-label="Available subnets">
      {#each visibleIds as subnetId (subnetId)}
        {@const geo = geoById[subnetId]}
        {@const selected = value === subnetId}
        {@const groups = regionFlagGroups(geo?.orderedCountries || [])}
        <button
          type="button"
          class="row"
          class:selected
          role="option"
          aria-selected={selected}
          title={subnetGeoTitle(geo) || subnetId}
          {disabled}
          on:click={() => select(subnetId)}
        >
          <span class="radio" aria-hidden="true">
            {#if selected}
              <span class="radio-dot"></span>
            {/if}
          </span>
          <span class="id-block">
            <code class="prefix">{subnetShortLabel(subnetId)}</code>
            <button
              type="button"
              class="copy"
              title={copiedId === subnetId ? 'Copied' : 'Copy full subnet ID'}
              aria-label="Copy subnet ID"
              on:click={(e) => copyId(e, subnetId)}
            >
              {copiedId === subnetId ? 'Copied' : 'Copy ID'}
            </button>
          </span>
          <span class="flags">
            {#if groups.length}
              {#each groups as group, i (group.region)}
                {#if i > 0}<span class="region-gap" aria-hidden="true"></span>{/if}
                <span class="region" title={group.label}>
                  {#each group.countries as country (country.code)}
                    <span class="flag" title="{group.label}: {country.name}">{country.flag}</span>
                  {/each}
                </span>
              {/each}
            {:else if loadingGeo}
              <span class="muted">…</span>
            {/if}
          </span>
          <span class="meta">
            {#if geo?.subnetType}{subnetTypeLabel(geo.subnetType)}{/if}
            {#if geo?.subnetType && geo?.nodeCount}<span class="dot">·</span>{/if}
            {#if geo?.nodeCount}{geo.nodeCount} nodes{/if}
          </span>
        </button>
      {/each}
    </div>
  {/if}
</div>

<style>
  .picker {
    display: flex;
    flex-direction: column;
    gap: 0.65rem;
  }

  .toolbar {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .filter {
    flex: 1;
    min-width: 0;
    padding: 0.55rem 0.75rem;
    border: 1px solid #e5e5e5;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    background: #fff;
  }

  .filter:focus {
    outline: none;
    border-color: #171717;
  }

  .count,
  .muted,
  .empty {
    margin: 0;
    font-size: 0.75rem;
    color: #737373;
    white-space: nowrap;
  }

  .list {
    display: flex;
    flex-direction: column;
    border: 1px solid #e5e5e5;
    border-radius: 0.75rem;
    overflow: auto;
    max-height: 26rem;
    background: #fff;
  }

  .row {
    display: grid;
    grid-template-columns: 1.25rem 4.75rem minmax(0, 1fr) auto;
    align-items: center;
    gap: 0.65rem;
    width: 100%;
    padding: 0.65rem 0.85rem;
    border: 0;
    border-bottom: 1px solid #f0f0f0;
    background: #fff;
    cursor: pointer;
    text-align: left;
  }

  .row:last-child {
    border-bottom: 0;
  }

  .row:hover:not(:disabled) {
    background: #fafafa;
  }

  .row.selected {
    background: #f0fdf4;
  }

  .row:disabled {
    cursor: not-allowed;
    opacity: 0.6;
  }

  .radio {
    width: 16px;
    height: 16px;
    border: 2px solid #d4d4d4;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .row.selected .radio {
    border-color: #22c55e;
  }

  .radio-dot {
    width: 8px;
    height: 8px;
    background: #22c55e;
    border-radius: 50%;
  }

  .id-block {
    display: flex;
    flex-direction: column;
    gap: 0.1rem;
    min-width: 0;
  }

  .prefix {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.875rem;
    font-weight: 600;
    color: #171717;
  }

  .copy {
    border: 0;
    padding: 0;
    background: none;
    font-size: 0.6875rem;
    color: #737373;
    cursor: pointer;
    text-align: left;
    width: fit-content;
  }

  .copy:hover {
    color: #171717;
  }

  .flags {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.15rem;
    min-width: 0;
    font-size: 1rem;
    line-height: 1;
  }

  .region {
    display: inline-flex;
    gap: 0.12rem;
  }

  .region-gap {
    width: 0.45rem;
  }

  .flag {
    display: inline-block;
  }

  .meta {
    font-size: 0.75rem;
    color: #737373;
    white-space: nowrap;
  }

  .dot {
    margin: 0 0.2rem;
  }

  @media (max-width: 640px) {
    .row {
      grid-template-columns: 1.25rem minmax(0, 1fr);
      grid-template-rows: auto auto;
    }

    .id-block {
      grid-column: 2;
    }

    .flags,
    .meta {
      grid-column: 2;
    }
  }
</style>
