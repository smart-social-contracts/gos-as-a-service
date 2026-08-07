<script>
  import { _ } from 'svelte-i18n';
  import { computeKpis } from '$lib/globe/hex-data.js';

  export let realms = [];
  export let realmZoneData = {};

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
</script>

<div class="kpi-line registry-desktop-only" data-tour="desktop-stats" aria-live="polite">
  <span>
    {$_('globe.kpi_realms', { values: { count: kpis.totalRealms } })}
    ·
    {$_('globe.kpi_users', { values: { count: kpis.totalUsers } })}
    {#if kpis.locationClusters > 0}
      ·
      {$_('globe.kpi_locations', { values: { count: kpis.locationClusters } })}
    {/if}
  </span>
  {#if stageLine}
    <span class="stage-line">{stageLine}</span>
  {/if}
</div>

<style>
  .kpi-line {
    position: absolute;
    left: 1rem;
    bottom: 1rem;
    z-index: 10;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    font-size: 0.8125rem;
    color: var(--text-tertiary);
    font-family: var(--font-family);
    pointer-events: none;
  }

  .stage-line {
    font-size: 0.75rem;
    color: var(--text-faint);
  }
</style>
