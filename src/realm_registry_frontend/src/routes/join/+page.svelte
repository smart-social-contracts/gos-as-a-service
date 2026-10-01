<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { login, isAuthenticated, getPrincipal } from '$lib/auth.js';

  let loading = true;
  let signingIn = false;
  let error = '';
  let principalText = '';
  let rememberMe = false;

  $: returnTo = $page.url.searchParams.get('returnTo') || '/';
  $: realmLabel = realmLabelFromReturn(returnTo);

  function realmLabelFromReturn(value) {
    const path = (value || '').split('?')[0];
    const match = path.match(/^\/r\/([^/]+)/);
    if (!match) return '';
    try {
      return decodeURIComponent(match[1]);
    } catch {
      return match[1];
    }
  }

  onMount(async () => {
    try {
      try {
        rememberMe = localStorage.getItem('portal:remember_me') === '1';
      } catch {
        // storage unavailable
      }
      if (await isAuthenticated()) {
        const p = await getPrincipal();
        principalText = p ? p.toText() : '';
        await goto(returnTo.startsWith('/') ? returnTo : `/${returnTo}`);
        return;
      }
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  });

  async function handleLogin() {
    signingIn = true;
    error = '';
    try {
      const { principal } = await login({ rememberMe });
      if (!principal) {
        error = 'Sign-in was cancelled or failed.';
        return;
      }
      principalText = principal.toText();
      await goto(returnTo.startsWith('/') ? returnTo : `/${returnTo}`);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      signingIn = false;
    }
  }
</script>

<svelte:head>
  <title>Sign in — Realms</title>
</svelte:head>

<main class="signin">
  <section class="panel" aria-busy={loading || signingIn}>
    <h1>Sign in</h1>
    {#if realmLabel}
      <p class="return">You will return to <span>{realmLabel}</span>.</p>
    {/if}

    {#if loading}
      <p class="status" role="status">
        <span class="spinner" aria-hidden="true"></span>
        Checking your session
      </p>
    {:else}
      {#if error}
        <p class="error" role="alert">{error}</p>
      {/if}
      <button type="button" class="submit" on:click={handleLogin} disabled={signingIn}>
        {#if signingIn}
          <span class="spinner spinner--on-dark" aria-hidden="true"></span>
          Opening Internet Identity
        {:else}
          Sign in with Internet Identity
        {/if}
      </button>
      <label class="remember">
        <input type="checkbox" bind:checked={rememberMe} disabled={signingIn} />
        <span>Remember me for 7 days</span>
      </label>
    {/if}

    {#if principalText}
      <p class="principal">Signed in as <code>{principalText}</code></p>
    {/if}
  </section>
</main>

<style>
  .signin {
    min-height: 100vh;
    min-height: 100dvh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem 1.25rem;
    background: var(--bg, #fafafa);
    color: var(--text-primary, #171717);
    font-family: var(--font-family, Inter, ui-sans-serif, system-ui, sans-serif);
    font-size: 1rem;
    line-height: 1.5;
  }

  .panel {
    width: 100%;
    max-width: 24rem;
    padding: 2.25rem 1.75rem 1.75rem;
    background: var(--surface, #fff);
    border: 1px solid var(--border, #e5e5e5);
    border-radius: 1rem;
    box-shadow: 0 1px 2px rgba(23, 23, 23, 0.04), 0 16px 40px rgba(23, 23, 23, 0.06);
    text-align: center;
  }

  h1 {
    margin: 0;
    font-size: 1.375rem;
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.2;
  }

  .return {
    margin: 0.75rem 0 0;
    color: var(--text-tertiary, #737373);
    font-size: 0.8125rem;
  }

  .return span {
    color: var(--text-primary, #171717);
    font-weight: 500;
  }

  .status {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.625rem;
    margin: 1.75rem 0 0.25rem;
    color: var(--text-secondary, #525252);
    font-size: 0.875rem;
  }

  .error {
    margin: 1.25rem 0 0;
    padding: 0.625rem 0.75rem;
    border-radius: 0.5rem;
    background: #fef2f2;
    color: #b91c1c;
    font-size: 0.8125rem;
    line-height: 1.4;
  }

  .submit {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    width: 100%;
    margin-top: 1.5rem;
    padding: 0.75rem 1rem;
    border: none;
    border-radius: 0.5rem;
    background: #171717;
    color: #fff;
    font: inherit;
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
  }

  .submit:hover:not(:disabled) {
    background: #404040;
  }

  .submit:disabled {
    background: #a3a3a3;
    cursor: wait;
  }

  .remember {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    margin-top: 1rem;
    color: var(--text-secondary, #525252);
    font-size: 0.875rem;
    cursor: pointer;
  }

  .remember input {
    width: 1rem;
    height: 1rem;
    margin: 0;
    accent-color: #171717;
    cursor: pointer;
  }

  .principal {
    margin: 1rem 0 0;
    color: var(--text-tertiary, #737373);
    font-size: 0.75rem;
    word-break: break-all;
  }

  .principal code {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  }

  .spinner {
    width: 0.875rem;
    height: 0.875rem;
    border: 2px solid #e5e5e5;
    border-top-color: #525252;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    flex-shrink: 0;
  }

  .spinner--on-dark {
    border-color: rgba(255, 255, 255, 0.35);
    border-top-color: #fff;
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
