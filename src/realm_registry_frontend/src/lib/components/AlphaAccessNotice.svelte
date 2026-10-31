<script>
  import { _ } from 'svelte-i18n';
  import { ALPHA_INVITE_REQUEST_URL } from '$lib/invite-request-url.js';
</script>

<aside class="alpha-notice" aria-label={$_('alpha_access.title')}>
  <h2>{$_('alpha_access.title')}</h2>
  <p>{$_('alpha_access.body')}</p>
  <a class="request" href={ALPHA_INVITE_REQUEST_URL} target="_blank" rel="noopener noreferrer">
    {$_('alpha_access.request')}
  </a>
  <p class="privacy">
    {$_('alpha_access.privacy')}
    <a href="/privacy" target="_blank" rel="noopener noreferrer">{$_('alpha_access.privacy_link')}</a>.
  </p>
</aside>

<style>
  .alpha-notice {
    max-width: 28rem;
    padding: 1rem 1.25rem;
    border: 1px solid var(--border);
    border-radius: 0.75rem;
    background: var(--surface);
    color: var(--text-primary);
    text-align: center;
  }

  h2 {
    margin: 0 0 0.35rem;
    font-size: 1.05rem;
  }

  p {
    margin: 0 0 0.75rem;
    font-size: 0.9rem;
    color: var(--text-secondary);
  }

  .request {
    display: inline-block;
    padding: 0.5rem 1rem;
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    color: var(--text-primary);
    font-size: 0.9rem;
    font-weight: 500;
    text-decoration: none;
  }

  .request:hover {
    background: var(--surface-2);
  }

  .privacy {
    margin: 0.75rem 0 0;
    font-size: 0.8rem;
  }

  .privacy a {
    color: inherit;
    text-decoration: underline;
  }
</style>
