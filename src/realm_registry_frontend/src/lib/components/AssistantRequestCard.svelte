<!--
  Who prepared a realm for the signed-in user, shown at the top of the deploy wizard's Review step
  (deploy-gos?assistant_request=<id>), in the style of the /connect/authorize card.

  Everything the assistant chose (its name, its note) is shown as plain text and marked as its own
  words. The cost is the registry's fixed price, passed in by the page, never a number from the request.
-->
<script>
  import { _, locale } from 'svelte-i18n';

  export let clientName = '';
  export let delegatePrincipal = '';
  export let note = '';
  export let principal = '';
  /** Unix seconds. */
  export let expiresAt = 0;
  export let expired = false;
  export let cost = 0;
  export let balance = 0;

  $: expiresLabel = new Date(expiresAt * 1000).toLocaleString($locale || undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  });
</script>

<section class="assistant-card" data-testid="assistant-request-card">
  <p class="lead">
    <strong data-testid="assistant-client-name">{clientName || $_('assistantDeploy.unnamed_assistant')}</strong>
    {$_('assistantDeploy.lead')}
  </p>
  <p class="unverified">{$_('assistantDeploy.unverified')}</p>

  {#if note}
    <blockquote class="note">
      <span class="label">{$_('assistantDeploy.note_label')}</span>
      <span data-testid="assistant-note">{note}</span>
    </blockquote>
  {/if}

  <dl class="facts">
    {#if delegatePrincipal}
      <dt>{$_('assistantDeploy.requested_by')}</dt>
      <dd><code title={delegatePrincipal}>{delegatePrincipal}</code></dd>
    {/if}
    <dt>{$_('assistantDeploy.signed_in_as')}</dt>
    <dd><code title={principal}>{principal}</code></dd>
    <dt>{$_('assistantDeploy.expires')}</dt>
    <dd class:expired data-testid="assistant-expires">
      {expired ? $_('assistantDeploy.expired') : expiresLabel}
    </dd>
    <dt>{$_('assistantDeploy.cost_label')}</dt>
    <dd data-testid="assistant-cost">{$_('assistantDeploy.cost', { values: { cost, balance } })}</dd>
  </dl>

  <p class="hint">{$_('assistantDeploy.only_you')}</p>
</section>

<style>
  .assistant-card {
    border: 1px solid #6366f1;
    background: #f5f4ff;
    border-radius: 0.75rem;
    padding: 1rem 1.1rem;
    margin: 0 0 1.5rem;
  }
  .lead {
    margin: 0 0 0.25rem;
    color: #171717;
    font-size: 0.95rem;
    line-height: 1.5;
  }
  .unverified {
    margin: 0 0 0.9rem;
    color: #b45309;
    font-size: 0.8rem;
  }
  .note {
    margin: 0 0 0.9rem;
    padding: 0.6rem 0.8rem;
    background: #fff;
    border-left: 3px solid #6366f1;
    border-radius: 0.3rem;
    font-size: 0.88rem;
    color: #404040;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .label {
    display: block;
    margin-bottom: 0.2rem;
    font-size: 0.72rem;
    color: #737373;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .facts {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: 0.4rem 0.9rem;
    margin: 0 0 0.75rem;
    font-size: 0.85rem;
  }
  dt {
    color: #737373;
  }
  dd {
    margin: 0;
    color: #171717;
    min-width: 0;
  }
  code {
    font-family: ui-monospace, monospace;
    font-size: 0.78rem;
    overflow-wrap: anywhere;
  }
  .expired {
    color: #b91c1c;
    font-weight: 600;
  }
  .hint {
    margin: 0;
    font-size: 0.78rem;
    color: #737373;
  }
  @media (max-width: 480px) {
    .facts {
      grid-template-columns: 1fr;
      gap: 0.1rem;
    }
    dd {
      margin-bottom: 0.4rem;
    }
  }
</style>
