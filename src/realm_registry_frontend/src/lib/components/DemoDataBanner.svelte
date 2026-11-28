<script>
  import { browser } from '$app/environment';
  import { _ } from 'svelte-i18n';
  import { LEGAL_CONTACT_EMAIL } from '$lib/legal/legal-info.js';
  import { topBannerInset } from '$lib/top-banner-inset.js';

  // The demo portal's notice, on every page including an embedded realm's (/r/…): the realm then leaves it to us
  // rather than show a second one. It folds to one line, and that is remembered, but it has no dismiss: the notice
  // must never disappear.
  const COLLAPSED_KEY = 'demo_data_banner_collapsed';

  let collapsed = browser && localStorage.getItem(COLLAPSED_KEY) === 'true';

  function toggle() {
    collapsed = !collapsed;
    if (browser) localStorage.setItem(COLLAPSED_KEY, String(collapsed));
  }
</script>

<div class="demo-data-banner" use:topBannerInset role="region" aria-label={$_('demo_data_banner.title')}>
  <p class="banner-text">
    <span class="title">{$_('demo_data_banner.title')}</span>
    {#if !collapsed}{' '}{$_('demo_data_banner.body')}{/if}
    {' '}<a href="/privacy">{$_('demo_data_banner.privacy')}</a>
    · <a href="/terms">{$_('demo_data_banner.terms')}</a>
    · <a href="mailto:{LEGAL_CONTACT_EMAIL}">{$_('demo_data_banner.report')}</a>
  </p>
  <button type="button" class="fold" aria-expanded={!collapsed} on:click={toggle}>
    {collapsed ? $_('demo_data_banner.expand') : $_('demo_data_banner.collapse')}
  </button>
</div>

<style>
  .demo-data-banner {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    z-index: 400;
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    background: #fffbeb;
    color: #451a03;
    border-bottom: 1px solid #fcd34d;
    padding: 0.5rem 1rem;
    font-size: 0.875rem;
    line-height: 1.35;
    font-family: var(--font-family);
  }
  .banner-text { margin: 0; flex: 1; min-width: 0; }
  .title { font-weight: 600; }
  a { color: inherit; text-decoration: underline; }
  .fold {
    flex-shrink: 0;
    border: 1px solid #fcd34d;
    background: #fff;
    color: inherit;
    border-radius: 0.375rem;
    padding: 0.125rem 0.5rem;
    font-size: 0.75rem;
    font-weight: 500;
    cursor: pointer;
  }
  .fold:hover { background: #fef3c7; }
</style>
