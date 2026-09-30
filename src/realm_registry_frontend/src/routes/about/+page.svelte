<script>
  import { _ } from 'svelte-i18n';
  import { MAINTAINER_CONTACT_URL } from '$lib/maintainer.js';
</script>

<svelte:head>
  <title>{$_('about.title')} | {$_('page_title')}</title>
</svelte:head>

<div class="about-page">
  <div class="about-container">
    <a href="/" class="back-link">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M19 12H5M12 19l-7-7 7-7"/>
      </svg>
      {$_('about.back')}
    </a>
    <h1>{$_('about.title')}</h1>
    <p class="lede">
      {$_('about.body_before')}<a href={MAINTAINER_CONTACT_URL} rel="noopener noreferrer">{$_('about.link')}</a>{$_('about.body_after')}
    </p>
  </div>
</div>

<style>
  .about-page {
    min-height: 100vh;
    background: #fafafa;
    padding: 2rem;
    font-family: var(--font-family);
  }

  .about-container {
    max-width: 40rem;
    margin: 0 auto;
  }

  .back-link {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    color: #525252;
    text-decoration: none;
    font-size: 0.875rem;
    margin-bottom: 1.25rem;
  }

  .back-link:hover {
    color: #171717;
  }

  h1 {
    margin: 0 0 0.85rem;
    font-size: 2rem;
    font-weight: 700;
    color: #171717;
  }

  .lede {
    margin: 0;
    color: #525252;
    font-size: 1.05rem;
    line-height: 1.6;
  }

  .lede a {
    color: #171717;
    font-weight: 600;
  }

  @media (max-width: 768px) {
    .about-page {
      padding: 1rem;
    }

    h1 {
      font-size: 1.5rem;
    }
  }
</style>
