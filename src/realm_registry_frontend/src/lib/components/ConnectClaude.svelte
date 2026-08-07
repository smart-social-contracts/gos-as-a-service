<!--
  Connect Claude — self-service MCP pairing tokens (issue #233 follow-up).

  Lets the Internet-Identity-authenticated user mint a personal pairing token
  for the Geister MCP server, so they can drive their realms from their own
  Claude (or any MCP client). The token is bound to their stable principal
  (the same one the platform sees thanks to the II derivationOrigin setup).

  Svelte 4 (the registry frontend is Svelte 4).
-->
<script>
  import { onMount } from 'svelte';
  import { _ } from 'svelte-i18n';

  // Geister API host — same origin the registry assistant talks to.
  const GEISTER_API = 'https://geister-api.realmsgos.dev';
  const MCP_URL = 'https://geister-mcp.realmsgos.dev/mcp';

  /** The user's IC principal as text (passed from the dashboard page). */
  export let principal = '';

  let tokens = [];
  let loadingList = true;
  let listError = '';

  // New-token form
  let label = '';
  let scope = 'read';
  let ttlDays = '';
  let creating = false;
  let createError = '';

  // The freshly minted token — shown exactly once.
  let newToken = '';
  let newTokenScope = '';
  let copiedToken = false;
  let copiedConfig = false;
  let copiedUrl = false;

  // Tier 1 snippet OS variant: Windows needs `cmd /c npx` because npx is a
  // .cmd shim that Claude can't spawn directly.
  let osChoice = detectOs();

  $: claudeConfig = newToken ? buildClaudeConfig(newToken, osChoice) : '';

  function detectOs() {
    if (typeof navigator === 'undefined') return 'unix';
    return /win/i.test(navigator.platform || navigator.userAgent || '') ? 'windows' : 'unix';
  }

  function buildClaudeConfig(token, os) {
    const remoteArgs = ['-y', 'mcp-remote', MCP_URL, '--header', `Authorization: Bearer ${token}`];
    const server =
      os === 'windows'
        ? { command: 'cmd', args: ['/c', 'npx', ...remoteArgs] }
        : { command: 'npx', args: remoteArgs };
    return JSON.stringify({ mcpServers: { realms: server } }, null, 2);
  }

  onMount(() => {
    if (principal) loadTokens();
    else loadingList = false;
  });

  async function loadTokens() {
    loadingList = true;
    listError = '';
    try {
      const res = await fetch(
        `${GEISTER_API}/api/mcp/tokens?user_principal=${encodeURIComponent(principal)}`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      tokens = Array.isArray(data?.tokens) ? data.tokens : [];
    } catch (err) {
      console.error('Failed to load MCP tokens:', err);
      listError = $_('connectClaude.list_error', {
        default: 'Could not load your tokens. Please try again shortly.',
      });
      tokens = [];
    } finally {
      loadingList = false;
    }
  }

  async function createToken() {
    if (!principal || creating) return;
    creating = true;
    createError = '';
    newToken = '';
    try {
      const body = { user_principal: principal, label: label.trim(), scope };
      const ttl = parseInt(ttlDays, 10);
      if (Number.isFinite(ttl) && ttl > 0) body.ttl_days = ttl;

      const res = await fetch(`${GEISTER_API}/api/mcp/tokens`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok || !data?.success) {
        throw new Error(data?.error || `HTTP ${res.status}`);
      }
      newToken = data.token;
      newTokenScope = data?.metadata?.scope || scope;
      label = '';
      ttlDays = '';
      await loadTokens();
    } catch (err) {
      console.error('Failed to mint MCP token:', err);
      createError = $_('connectClaude.create_error', {
        default: 'Could not generate a token. Please try again.',
      });
    } finally {
      creating = false;
    }
  }

  async function revokeToken(id) {
    try {
      const res = await fetch(`${GEISTER_API}/api/mcp/tokens/${id}`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_principal: principal }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await loadTokens();
    } catch (err) {
      console.error('Failed to revoke MCP token:', err);
    }
  }

  async function copy(text, which) {
    try {
      await navigator.clipboard.writeText(text);
      if (which === 'token') {
        copiedToken = true;
        setTimeout(() => (copiedToken = false), 1800);
      } else if (which === 'url') {
        copiedUrl = true;
        setTimeout(() => (copiedUrl = false), 1800);
      } else {
        copiedConfig = true;
        setTimeout(() => (copiedConfig = false), 1800);
      }
    } catch (err) {
      console.error('Clipboard write failed:', err);
    }
  }

  function dismissNewToken() {
    newToken = '';
    newTokenScope = '';
  }

  function formatDate(value) {
    if (!value) return '';
    const parsed = Date.parse(value);
    return Number.isNaN(parsed) ? value : new Date(parsed).toLocaleString();
  }
</script>

<div class="connect-section">
  <div class="intro">
    <h3>{$_('connectClaude.title', { default: 'Connect your Claude' })}</h3>
    <p>
      {$_('connectClaude.intro', {
        default:
          'Use your realms from your own Claude (or any MCP client). Access acts on behalf of your principal — only approve clients you trust.',
      })}
    </p>
  </div>

  <!-- Recommended: install-free OAuth (Tier 2) -->
  <div class="oauth-card">
    <div class="oauth-head">
      <span class="badge">{$_('connectClaude.recommended', { default: 'Recommended' })}</span>
      <h4>{$_('connectClaude.oauth_title', { default: 'Connect with one click (no install)' })}</h4>
    </div>
    <p class="oauth-desc">
      {$_('connectClaude.oauth_desc', {
        default:
          'Add the server URL below as a custom connector in Claude. Claude opens a browser, you sign in with Internet Identity and approve access — no Node.js, no token to copy.',
      })}
    </p>
    <div class="url-row">
      <code class="url-value">{MCP_URL}</code>
      <button class="copy-btn" on:click={() => copy(MCP_URL, 'url')}>
        {copiedUrl ? $_('connectClaude.copied', { default: 'Copied' }) : $_('connectClaude.copy', { default: 'Copy' })}
      </button>
    </div>
    <ol class="steps">
      <li>{$_('connectClaude.oauth_step1', { default: 'In Claude: Settings → Connectors → Add custom connector.' })}</li>
      <li>{$_('connectClaude.oauth_step2', { default: 'Paste the URL above and continue.' })}</li>
      <li>{$_('connectClaude.oauth_step3', { default: 'Sign in with Internet Identity and choose read-only or full access.' })}</li>
    </ol>
  </div>

  <div class="alt-divider">
    <span>{$_('connectClaude.alt_label', { default: 'Or use a pairing token (advanced)' })}</span>
  </div>

  {#if !principal}
    <div class="notice">{$_('connectClaude.signin', { default: 'Sign in to manage access tokens.' })}</div>
  {:else}
    <!-- Generate -->
    <div class="generate-card">
      <h4>{$_('connectClaude.generate', { default: 'Generate a token' })}</h4>
      <div class="form-row">
        <label>
          <span class="field-label">{$_('connectClaude.label', { default: 'Label' })}</span>
          <input
            type="text"
            bind:value={label}
            placeholder={$_('connectClaude.label_ph', { default: 'e.g. My Claude Desktop' })}
            disabled={creating}
          />
        </label>
        <label>
          <span class="field-label">{$_('connectClaude.scope', { default: 'Access' })}</span>
          <select bind:value={scope} disabled={creating}>
            <option value="read">{$_('connectClaude.scope_read', { default: 'Read-only (safer)' })}</option>
            <option value="full">{$_('connectClaude.scope_full', { default: 'Full (can act for you)' })}</option>
          </select>
        </label>
        <label class="ttl">
          <span class="field-label">{$_('connectClaude.expiry', { default: 'Expires (days)' })}</span>
          <input type="number" min="1" bind:value={ttlDays} placeholder="∞" disabled={creating} />
        </label>
      </div>

      {#if scope === 'full'}
        <p class="scope-warn">
          {$_('connectClaude.full_warn', {
            default:
              'Full access exposes actions (voting, deploying, transfers) that run on your behalf. Prefer read-only unless you need them.',
          })}
        </p>
      {/if}

      {#if createError}<div class="error-message">{createError}</div>{/if}

      <button class="primary-btn" on:click={createToken} disabled={creating}>
        {#if creating}
          <span class="btn-spinner"></span>
        {:else}
          {$_('connectClaude.generate_btn', { default: 'Generate token' })}
        {/if}
      </button>
    </div>

    <!-- Freshly minted token (shown once) -->
    {#if newToken}
      <div class="token-reveal">
        <div class="reveal-head">
          <strong>{$_('connectClaude.copy_now', { default: 'Copy this token now — it won\'t be shown again.' })}</strong>
          <button class="dismiss" on:click={dismissNewToken} aria-label="Dismiss">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6L6 18M6 6l12 12" /></svg>
          </button>
        </div>
        <div class="token-row">
          <code class="token-value">{newToken}</code>
          <button class="copy-btn" on:click={() => copy(newToken, 'token')}>
            {copiedToken ? $_('connectClaude.copied', { default: 'Copied' }) : $_('connectClaude.copy', { default: 'Copy' })}
          </button>
        </div>
        <span class="scope-pill {newTokenScope}">{newTokenScope}</span>

        <div class="snippet-block">
          <div class="snippet-head">
            <span>{$_('connectClaude.claude_config', { default: 'Claude Desktop config (claude_desktop_config.json)' })}</span>
            <div class="os-toggle" role="group" aria-label="Operating system">
              <button class:active={osChoice === 'unix'} on:click={() => (osChoice = 'unix')}>macOS / Linux</button>
              <button class:active={osChoice === 'windows'} on:click={() => (osChoice = 'windows')}>Windows</button>
            </div>
            <button class="copy-btn" on:click={() => copy(claudeConfig, 'config')}>
              {copiedConfig ? $_('connectClaude.copied', { default: 'Copied' }) : $_('connectClaude.copy', { default: 'Copy' })}
            </button>
          </div>
          <pre class="snippet">{claudeConfig}</pre>
          <p class="snippet-hint">
            {$_('connectClaude.snippet_hint', {
              default:
                'Requires Node.js (the npx/mcp-remote bridge). Add this to Claude Desktop → Settings → Developer → Edit Config, then restart Claude and ask: “List my realms”.',
            })}
            {#if osChoice === 'windows'}
              {$_('connectClaude.snippet_hint_win', {
                default:
                  ' On Windows, npx is a .cmd shim, so it is launched via cmd /c.',
              })}
            {/if}
          </p>
        </div>
      </div>
    {/if}

    <!-- Existing tokens -->
    <div class="tokens-list">
      <h4>{$_('connectClaude.your_tokens', { default: 'Your tokens' })}</h4>
      {#if loadingList}
        <div class="loading-placeholder"></div>
      {:else if listError}
        <div class="error-message">{listError}</div>
      {:else if tokens.length === 0}
        <div class="empty">{$_('connectClaude.no_tokens', { default: 'No tokens yet.' })}</div>
      {:else}
        <ul>
          {#each tokens as t (t.id)}
            <li class="token-item" class:revoked={t.revoked}>
              <div class="token-meta">
                <span class="token-label">
                  {t.label || $_('connectClaude.untitled', { default: 'Untitled' })}
                  <span class="scope-pill {t.scope}">{t.scope}</span>
                  {#if t.revoked}<span class="scope-pill revoked-pill">{$_('connectClaude.revoked', { default: 'revoked' })}</span>{/if}
                </span>
                <span class="token-sub">
                  {$_('connectClaude.created', { default: 'Created' })} {formatDate(t.created_at)}
                  {#if t.last_used_at}· {$_('connectClaude.last_used', { default: 'last used' })} {formatDate(t.last_used_at)}{/if}
                  {#if t.expires_at}· {$_('connectClaude.expires', { default: 'expires' })} {formatDate(t.expires_at)}{/if}
                </span>
              </div>
              {#if !t.revoked}
                <button class="revoke-btn" on:click={() => revokeToken(t.id)}>
                  {$_('connectClaude.revoke_btn', { default: 'Revoke' })}
                </button>
              {/if}
            </li>
          {/each}
        </ul>
      {/if}
    </div>
  {/if}
</div>

<style>
  .connect-section {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .intro h3 {
    font-size: 1.125rem;
    font-weight: 600;
    color: #171717;
    margin: 0 0 0.5rem 0;
  }
  .intro p {
    color: #525252;
    font-size: 0.875rem;
    margin: 0;
    line-height: 1.5;
  }

  .notice {
    background: #f5f5f5;
    color: #525252;
    padding: 1rem;
    border-radius: 0.5rem;
    font-size: 0.875rem;
  }

  .oauth-card {
    border: 1px solid #ddd6fe;
    background: #f5f4ff;
    border-radius: 1rem;
    padding: 1.5rem;
  }
  .oauth-head {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin-bottom: 0.5rem;
  }
  .oauth-head h4 {
    font-size: 1rem;
    font-weight: 600;
    color: #171717;
    margin: 0;
  }
  .badge {
    background: #6366f1;
    color: #fff;
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    padding: 0.15rem 0.5rem;
    border-radius: 1rem;
  }
  .oauth-desc {
    color: #525252;
    font-size: 0.875rem;
    line-height: 1.5;
    margin: 0 0 1rem;
  }
  .url-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    margin-bottom: 0.75rem;
  }
  .url-value {
    flex: 1;
    background: #fff;
    border: 1px solid #ddd6fe;
    border-radius: 0.5rem;
    padding: 0.6rem 0.75rem;
    font-family: ui-monospace, monospace;
    font-size: 0.82rem;
    color: #4338ca;
    word-break: break-all;
  }
  .steps {
    margin: 0;
    padding-left: 1.1rem;
    color: #525252;
    font-size: 0.82rem;
    line-height: 1.6;
  }

  .alt-divider {
    display: flex;
    align-items: center;
    text-align: center;
    color: #a3a3a3;
    font-size: 0.78rem;
  }
  .alt-divider::before,
  .alt-divider::after {
    content: '';
    flex: 1;
    border-bottom: 1px solid #ececec;
  }
  .alt-divider span {
    padding: 0 0.75rem;
  }

  .os-toggle {
    display: inline-flex;
    border: 1px solid #d1fae5;
    border-radius: 0.4rem;
    overflow: hidden;
    margin-left: auto;
  }
  .os-toggle button {
    background: #fff;
    border: none;
    color: #047857;
    font-size: 0.72rem;
    font-weight: 600;
    padding: 0.25rem 0.55rem;
    cursor: pointer;
  }
  .os-toggle button.active {
    background: #059669;
    color: #fff;
  }

  .generate-card {
    background: #f5f5f5;
    border-radius: 1rem;
    padding: 1.5rem;
  }
  .generate-card h4 {
    font-size: 1rem;
    font-weight: 600;
    color: #171717;
    margin: 0 0 1rem 0;
  }

  .form-row {
    display: flex;
    gap: 1rem;
    flex-wrap: wrap;
  }
  .form-row label {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    flex: 1;
    min-width: 160px;
  }
  .form-row label.ttl {
    flex: 0 0 120px;
    min-width: 120px;
  }
  .field-label {
    font-size: 0.8rem;
    font-weight: 500;
    color: #171717;
  }
  .form-row input,
  .form-row select {
    height: 40px;
    border: 1px solid #e5e5e5;
    border-radius: 0.5rem;
    padding: 0 0.75rem;
    font-size: 0.9rem;
    background: #fff;
    color: #171717;
  }
  .form-row input:focus,
  .form-row select:focus {
    outline: none;
    border-color: #171717;
  }

  .scope-warn {
    margin: 0.75rem 0 0;
    font-size: 0.8rem;
    color: #92400e;
    background: #fef3c7;
    border: 1px solid #fde68a;
    border-radius: 0.5rem;
    padding: 0.5rem 0.75rem;
  }

  .primary-btn {
    margin-top: 1rem;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 42px;
    padding: 0 1.5rem;
    background: #171717;
    color: #fff;
    border: none;
    border-radius: 0.5rem;
    font-size: 0.9rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s ease;
  }
  .primary-btn:hover:not(:disabled) {
    background: #404040;
  }
  .primary-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .token-reveal {
    background: #ecfdf5;
    border: 1px solid #a7f3d0;
    border-radius: 1rem;
    padding: 1.25rem;
  }
  .reveal-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    color: #065f46;
    font-size: 0.875rem;
    margin-bottom: 0.75rem;
  }
  .dismiss {
    background: none;
    border: none;
    color: #065f46;
    cursor: pointer;
    padding: 2px;
  }
  .token-row {
    display: flex;
    gap: 0.5rem;
    align-items: center;
  }
  .token-value {
    flex: 1;
    background: #fff;
    border: 1px solid #d1fae5;
    border-radius: 0.5rem;
    padding: 0.6rem 0.75rem;
    font-family: ui-monospace, monospace;
    font-size: 0.8rem;
    color: #111;
    word-break: break-all;
  }
  .copy-btn {
    background: #059669;
    color: #fff;
    border: none;
    border-radius: 0.5rem;
    padding: 0 0.9rem;
    height: 38px;
    font-size: 0.8rem;
    font-weight: 600;
    cursor: pointer;
    white-space: nowrap;
  }
  .copy-btn:hover {
    background: #047857;
  }

  .scope-pill {
    display: inline-block;
    margin-left: 0.4rem;
    padding: 0.1rem 0.5rem;
    border-radius: 1rem;
    font-size: 0.7rem;
    font-weight: 600;
    background: #e5e5e5;
    color: #525252;
    vertical-align: middle;
  }
  .scope-pill.read {
    background: #dbeafe;
    color: #1d4ed8;
  }
  .scope-pill.full {
    background: #fee2e2;
    color: #b91c1c;
  }
  .scope-pill.revoked-pill {
    background: #f5f5f5;
    color: #737373;
  }

  .snippet-block {
    margin-top: 1rem;
  }
  .snippet-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 0.8rem;
    color: #065f46;
    margin-bottom: 0.4rem;
    gap: 0.5rem;
  }
  .snippet {
    background: #0b1f17;
    color: #d1fae5;
    border-radius: 0.5rem;
    padding: 0.9rem;
    font-family: ui-monospace, monospace;
    font-size: 0.75rem;
    line-height: 1.5;
    overflow-x: auto;
    margin: 0;
    white-space: pre;
  }
  .snippet-hint {
    font-size: 0.78rem;
    color: #525252;
    margin: 0.5rem 0 0;
    line-height: 1.45;
  }

  .tokens-list h4 {
    font-size: 1rem;
    font-weight: 600;
    color: #171717;
    margin: 0 0 1rem 0;
  }
  .tokens-list ul {
    list-style: none;
    padding: 0;
    margin: 0;
  }
  .token-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    padding: 0.85rem 0;
    border-bottom: 1px solid #f0f0f0;
  }
  .token-item:last-child {
    border-bottom: none;
  }
  .token-item.revoked {
    opacity: 0.55;
  }
  .token-meta {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    min-width: 0;
  }
  .token-label {
    font-weight: 600;
    color: #171717;
    font-size: 0.9rem;
  }
  .token-sub {
    font-size: 0.75rem;
    color: #737373;
  }
  .revoke-btn {
    background: none;
    border: 1px solid #e5e5e5;
    color: #b91c1c;
    border-radius: 0.5rem;
    padding: 0.4rem 0.8rem;
    font-size: 0.8rem;
    font-weight: 500;
    cursor: pointer;
    flex-shrink: 0;
  }
  .revoke-btn:hover {
    background: #fef2f2;
    border-color: #fecaca;
  }

  .empty {
    color: #737373;
    font-size: 0.875rem;
    padding: 0.5rem 0;
  }
  .error-message {
    background: #fee2e2;
    color: #dc2626;
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
    font-size: 0.85rem;
  }
  .loading-placeholder {
    height: 60px;
    background: #f5f5f5;
    border-radius: 0.5rem;
    animation: pulse 1.5s ease-in-out infinite;
  }
  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }
  .btn-spinner {
    width: 18px;
    height: 18px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: #fff;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 640px) {
    .form-row label,
    .form-row label.ttl {
      flex: 1 1 100%;
      min-width: 0;
    }
  }
</style>
