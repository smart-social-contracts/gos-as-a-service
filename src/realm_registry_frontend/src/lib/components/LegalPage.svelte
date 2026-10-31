<script>
  import { _, locale } from 'svelte-i18n';
  import { LEGAL_LAST_UPDATED } from '$lib/legal/legal-info.js';

  /** Texts by locale, e.g. TERMS from $lib/legal/terms.js. Locales without a text show English. */
  export let texts;

  $: text = texts[$locale?.split('-')[0]] ?? texts.en;
</script>

<svelte:head>
  <title>{text.title} | {$_('page_title')}</title>
</svelte:head>

<div class="legal-page">
  <div class="legal-container">
    <a href="/" class="back-link">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path d="M19 12H5M12 19l-7-7 7-7"/>
      </svg>
      {$_('about.back')}
    </a>
    <h1>{text.title}</h1>
    <p class="meta">{$_('legal.last_updated')}: {LEGAL_LAST_UPDATED}</p>
    <p class="alpha-notice">{text.alphaNotice}</p>
    {#each text.sections as section}
      <h2>{section.heading}</h2>
      {#each section.paragraphs as paragraph}
        <p>{paragraph}</p>
      {/each}
    {/each}
  </div>
</div>

<style>
  .legal-page {
    min-height: 100vh;
    background: #fafafa;
    padding: 2rem;
    font-family: var(--font-family);
  }

  .legal-container {
    max-width: 40rem;
    margin: 0 auto;
    color: #525252;
    line-height: 1.6;
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
    margin: 0 0 0.5rem;
    font-size: 2rem;
    font-weight: 700;
    color: #171717;
  }

  h2 {
    margin: 1.5rem 0 0.5rem;
    font-size: 1.1rem;
    font-weight: 600;
    color: #171717;
  }

  p {
    margin: 0 0 0.75rem;
    font-size: 0.95rem;
  }

  .meta {
    font-size: 0.85rem;
    color: #737373;
  }

  .alpha-notice {
    padding: 0.75rem 1rem;
    border-left: 3px solid #d97706;
    background: rgba(217, 119, 6, 0.08);
  }

  @media (max-width: 768px) {
    .legal-page {
      padding: 1rem;
    }

    h1 {
      font-size: 1.5rem;
    }
  }
</style>
