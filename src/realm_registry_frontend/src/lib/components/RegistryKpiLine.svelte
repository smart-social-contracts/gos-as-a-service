<script>
  import { _, locale } from 'svelte-i18n';
  import { REALM_STAGES } from '$lib/realm-stages.js';
  import { formatCount } from '$lib/realm-utils.js';
  import { computeKpis } from '$lib/globe/hex-data.js';

  export let realms = [];
  export let realmZoneData = {};

  $: kpis = computeKpis(realms, realmZoneData);

  $: stageParts = REALM_STAGES.filter((stage) => kpis.stageCounts[stage.id] > 0).map((stage) => ({
    ...stage,
    count: kpis.stageCounts[stage.id],
  }));
</script>

<div class="kpi-line registry-desktop-only" data-tour="desktop-stats" aria-live="polite">
  <span>
    {$_('globe.kpi_realms', { values: { count: formatCount(kpis.totalRealms, $locale) } })}
    ·
    {$_('globe.kpi_users', { values: { count: formatCount(kpis.totalUsers, $locale) } })}
    {#if kpis.locationClusters > 0}
      ·
      {$_('globe.kpi_locations', { values: { count: kpis.locationClusters } })}
    {/if}
  </span>
  {#if stageParts.length}
    <span class="stage-line">
      {#each stageParts as stage, i (stage.id)}{#if i > 0}<span aria-hidden="true"> · </span>{/if}<span class="stage-part"><span class="stage-dot" style="background-color: {stage.marker}" aria-hidden="true"></span>{stage.count} {$_(`stages.${stage.id}.label`, { default: stage.label })}</span>{/each}
    </span>
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

  .stage-part {
    white-space: nowrap;
  }

  .stage-dot {
    display: inline-block;
    width: 0.5rem;
    height: 0.5rem;
    margin-right: 0.3rem;
    border-radius: 50%;
  }
</style>
