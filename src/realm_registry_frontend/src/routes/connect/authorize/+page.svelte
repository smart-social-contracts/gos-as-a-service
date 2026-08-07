<!--
  OAuth consent screen for the Geister MCP server (Tier 2, install-free).

  Claude (or any MCP client) sends the browser here from the MCP server's
  /authorize endpoint with ?request_id=<id>. We authenticate the human with
  Internet Identity — pinned to the same derivationOrigin as the whole platform
  so the principal matches their realms/credits — and POST the approved
  principal back to the MCP server, which mints a one-time authorization code
  and hands the browser back to Claude's callback.

  Svelte 4 (the registry frontend is Svelte 4).
-->
<script>
  import { onMount } from 'svelte';
  import { _ } from 'svelte-i18n';
  import { login, getPrincipal, isAuthenticated } from '$lib/auth.js';

  const MCP_HOST = 'https://geister-mcp.realmsgos.dev';

  let phase = 'loading'; // loading | error | consent | redirecting
  let errorMsg = '';
  let requestId = '';
  let info = null; // { client_name, requested_scopes, valid_scopes }
  let principal = '';
  let selectedScope = 'read';
  let submitting = false;

  onMount(async () => {
    try {
      const params = new URLSearchParams(window.location.search);
      requestId = (params.get('request_id') || '').trim();
      if (!requestId) {
        return fail($_('mcpConsent.no_request', {
          default: 'Missing authorization request. Start the connection from your MCP client.',
        }));
      }

      const res = await fetch(`${MCP_HOST}/oauth/request?request_id=${encodeURIComponent(requestId)}`);
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        return fail(data?.error || $_('mcpConsent.expired', {
          default: 'This authorization request is invalid or has expired. Please try connecting again.',
        }));
      }
      info = data;
      // Default the picker to the broadest scope the client asked for, but never
      // above read unless they explicitly requested full.
      selectedScope = (info.requested_scopes || []).includes('full') ? 'full' : 'read';

      if (await isAuthenticated()) {
        const p = await getPrincipal();
        principal = p ? p.toText() : '';
      }
      phase = 'consent';
    } catch (err) {
      console.error('consent init failed:', err);
      fail($_('mcpConsent.load_error', { default: 'Could not load the authorization request.' }));
    }
  });

  function fail(msg) {
    errorMsg = msg;
    phase = 'error';
  }

  async function signIn() {
    const { principal: p } = await login();
    if (p) principal = p.toText();
  }

  async function decide(approve) {
    if (submitting) return;
    if (approve && !principal) {
      await signIn();
      if (!principal) return;
    }
    submitting = true;
    try {
      const res = await fetch(`${MCP_HOST}/oauth/consent`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: requestId,
          user_principal: principal,
          scope: selectedScope,
          approve,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok || !data?.redirect_to) {
        throw new Error(data?.error || `HTTP ${res.status}`);
      }
      phase = 'redirecting';
      window.location.href = data.redirect_to;
    } catch (err) {
      console.error('consent decision failed:', err);
      fail($_('mcpConsent.submit_error', {
        default: 'Could not complete authorization. Please try again.',
      }));
    } finally {
      submitting = false;
    }
  }
</script>

<svelte:head>
  <title>{$_('mcpConsent.page_title', { default: 'Connect to your Realms account' })}</title>
</svelte:head>

<div class="consent-wrap">
  <div class="card">
    <div class="brand">
      <div class="logo-dot"></div>
      <span>Realms</span>
    </div>

    {#if phase === 'loading'}
      <div class="center muted">
        <span class="spinner"></span>
        {$_('mcpConsent.loading', { default: 'Preparing authorization…' })}
      </div>
    {:else if phase === 'error'}
      <h1>{$_('mcpConsent.error_title', { default: 'Authorization unavailable' })}</h1>
      <div class="error">{errorMsg}</div>
    {:else if phase === 'redirecting'}
      <div class="center muted">
        <span class="spinner"></span>
        {$_('mcpConsent.redirecting', { default: 'Returning you to your client…' })}
      </div>
    {:else}
      <h1>
        {$_('mcpConsent.title', { default: 'Authorize access' })}
      </h1>
      <p class="lead">
        <strong>{info?.client_name || 'An MCP client'}</strong>
        {$_('mcpConsent.lead', {
          default: 'wants to access your Realms account and act through the Geister assistant on your behalf.',
        })}
      </p>

      <div class="who">
        {#if principal}
          <div class="who-row">
            <span class="who-label">{$_('mcpConsent.signed_in_as', { default: 'Signed in as' })}</span>
            <code class="principal" title={principal}>{principal}</code>
          </div>
        {:else}
          <p class="muted small">
            {$_('mcpConsent.need_signin', {
              default: 'Sign in with Internet Identity to continue. This binds access to your stable principal.',
            })}
          </p>
          <button class="ii-btn" on:click={signIn} disabled={submitting}>
            {$_('mcpConsent.signin_btn', { default: 'Sign in with Internet Identity' })}
          </button>
        {/if}
      </div>

      {#if principal}
        <fieldset class="scope">
          <legend>{$_('mcpConsent.access_level', { default: 'Access level' })}</legend>
          <label class:active={selectedScope === 'read'}>
            <input type="radio" bind:group={selectedScope} value="read" />
            <span>
              <strong>{$_('mcpConsent.scope_read', { default: 'Read-only' })}</strong>
              <small>{$_('mcpConsent.scope_read_desc', { default: 'View realms, credits, proposals and balances. Recommended.' })}</small>
            </span>
          </label>
          <label class:active={selectedScope === 'full'}>
            <input type="radio" bind:group={selectedScope} value="full" />
            <span>
              <strong>{$_('mcpConsent.scope_full', { default: 'Full access' })}</strong>
              <small>{$_('mcpConsent.scope_full_desc', { default: 'Also vote, submit proposals, deploy and transfer on your behalf.' })}</small>
            </span>
          </label>
        </fieldset>

        {#if selectedScope === 'full'}
          <div class="warn">
            {$_('mcpConsent.full_warn', {
              default: 'Full access lets this client take actions that move funds and change governance. Only approve clients you trust.',
            })}
          </div>
        {/if}
      {/if}

      <div class="actions">
        <button class="deny" on:click={() => decide(false)} disabled={submitting}>
          {$_('mcpConsent.deny', { default: 'Deny' })}
        </button>
        <button class="approve" on:click={() => decide(true)} disabled={submitting || !principal}>
          {#if submitting}
            <span class="spinner small-spin"></span>
          {:else}
            {$_('mcpConsent.approve', { default: 'Approve' })}
          {/if}
        </button>
      </div>

      <p class="footnote">
        {$_('mcpConsent.footnote', {
          default: 'You can revoke this access any time from your dashboard → Connect Claude.',
        })}
      </p>
    {/if}
  </div>
</div>

<style>
  .consent-wrap {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
    background: #fafafa;
  }
  .card {
    width: 100%;
    max-width: 440px;
    background: #fff;
    border: 1px solid #ededed;
    border-radius: 1rem;
    padding: 1.75rem;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.06);
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 700;
    color: #171717;
    margin-bottom: 1.25rem;
  }
  .logo-dot {
    width: 18px;
    height: 18px;
    border-radius: 50%;
    background: linear-gradient(135deg, #6366f1, #a855f7);
  }
  h1 {
    font-size: 1.25rem;
    font-weight: 700;
    color: #171717;
    margin: 0 0 0.5rem;
  }
  .lead {
    color: #525252;
    font-size: 0.9rem;
    line-height: 1.5;
    margin: 0 0 1.25rem;
  }
  .who {
    background: #f7f7f8;
    border-radius: 0.75rem;
    padding: 1rem;
    margin-bottom: 1.25rem;
  }
  .who-row {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
  }
  .who-label {
    font-size: 0.75rem;
    color: #737373;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .principal {
    font-family: ui-monospace, monospace;
    font-size: 0.78rem;
    color: #111;
    word-break: break-all;
    background: #fff;
    border: 1px solid #eee;
    border-radius: 0.4rem;
    padding: 0.45rem 0.55rem;
  }
  .ii-btn {
    margin-top: 0.5rem;
    width: 100%;
    background: #171717;
    color: #fff;
    border: none;
    border-radius: 0.6rem;
    padding: 0.7rem 1rem;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
  }
  .ii-btn:hover:not(:disabled) { background: #404040; }

  .scope {
    border: none;
    padding: 0;
    margin: 0 0 1rem;
  }
  .scope legend {
    font-size: 0.8rem;
    font-weight: 600;
    color: #171717;
    padding: 0;
    margin-bottom: 0.5rem;
  }
  .scope label {
    display: flex;
    gap: 0.6rem;
    align-items: flex-start;
    border: 1px solid #e9e9e9;
    border-radius: 0.6rem;
    padding: 0.7rem 0.8rem;
    margin-bottom: 0.5rem;
    cursor: pointer;
  }
  .scope label.active {
    border-color: #6366f1;
    background: #f5f4ff;
  }
  .scope label span {
    display: flex;
    flex-direction: column;
    gap: 0.15rem;
  }
  .scope strong {
    font-size: 0.88rem;
    color: #171717;
  }
  .scope small {
    font-size: 0.78rem;
    color: #737373;
    line-height: 1.4;
  }
  .scope input {
    margin-top: 0.2rem;
  }

  .warn {
    font-size: 0.78rem;
    color: #92400e;
    background: #fef3c7;
    border: 1px solid #fde68a;
    border-radius: 0.5rem;
    padding: 0.6rem 0.75rem;
    margin-bottom: 1rem;
    line-height: 1.45;
  }

  .actions {
    display: flex;
    gap: 0.75rem;
  }
  .actions button {
    flex: 1;
    min-height: 44px;
    border-radius: 0.6rem;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    justify-content: center;
  }
  .deny {
    background: #fff;
    border: 1px solid #e5e5e5;
    color: #404040;
  }
  .deny:hover:not(:disabled) { background: #f5f5f5; }
  .approve {
    background: #6366f1;
    border: none;
    color: #fff;
  }
  .approve:hover:not(:disabled) { background: #4f46e5; }
  .approve:disabled,
  .deny:disabled { opacity: 0.6; cursor: not-allowed; }

  .footnote {
    font-size: 0.75rem;
    color: #a3a3a3;
    margin: 1rem 0 0;
    text-align: center;
  }

  .center {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.6rem;
    padding: 2rem 0;
  }
  .muted { color: #737373; font-size: 0.9rem; }
  .small { font-size: 0.82rem; }
  .error {
    background: #fee2e2;
    color: #b91c1c;
    border-radius: 0.6rem;
    padding: 0.85rem 1rem;
    font-size: 0.85rem;
    line-height: 1.45;
  }
  .spinner {
    width: 20px;
    height: 20px;
    border: 2px solid #e5e5e5;
    border-top-color: #6366f1;
    border-radius: 50%;
    animation: spin 0.9s linear infinite;
  }
  .small-spin {
    width: 18px;
    height: 18px;
    border-top-color: #fff;
    border-color: rgba(255, 255, 255, 0.35);
    border-top-color: #fff;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
