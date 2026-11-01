<script>
  import { _ } from 'svelte-i18n';
  import { ALPHA_INVITE_REQUEST_URL } from '$lib/invite-request-url.js';
</script>

<a class="request-invitation" href={ALPHA_INVITE_REQUEST_URL} target="_blank" rel="noopener noreferrer">
  {$_('alpha_access.request')}
</a>

<style>
  .request-invitation {
    display: inline-block;
    padding: 0.5rem 1rem;
    border: 1px solid var(--border);
    border-radius: 0.5rem;
    background: var(--surface);
    color: var(--text-primary);
    font-size: 0.9rem;
    font-weight: 500;
    text-decoration: none;
    white-space: nowrap;
  }

  .request-invitation:hover {
    background: var(--surface-2);
  }
</style>
