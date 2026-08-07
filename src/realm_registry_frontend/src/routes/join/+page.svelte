<script>
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { login, isAuthenticated, getPrincipal } from '$lib/auth.js';

  let loading = true;
  let error = '';
  let principalText = '';

  $: returnTo = $page.url.searchParams.get('returnTo') || '/';

  onMount(async () => {
    try {
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
    loading = true;
    error = '';
    try {
      const { principal } = await login();
      if (!principal) {
        error = 'Sign-in was cancelled or failed.';
        return;
      }
      principalText = principal.toText();
      await goto(returnTo.startsWith('/') ? returnTo : `/${returnTo}`);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      loading = false;
    }
  }
</script>

<svelte:head>
  <title>Sign in — Realms Federation</title>
</svelte:head>

<main class="join-page">
  <div class="card">
    <h1>Sign in</h1>
    <p class="subtitle">Internet Identity — one account for every realm on this portal.</p>

    {#if loading && !error}
      <p>Checking session…</p>
    {:else}
      {#if error}
        <p class="error">{error}</p>
      {/if}
      <button type="button" class="btn-primary" on:click={handleLogin} disabled={loading}>
        Sign in with Internet Identity
      </button>
    {/if}

    {#if principalText}
      <p class="hint">Signed in as <code>{principalText}</code></p>
    {/if}
  </div>
</main>

<style>
  .join-page {
    min-height: 70vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
  }
  .card {
    max-width: 420px;
    width: 100%;
    padding: 2rem;
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.12);
    background: rgba(0, 0, 0, 0.25);
  }
  h1 {
    margin: 0 0 0.5rem;
    font-size: 1.5rem;
  }
  .subtitle {
    margin: 0 0 1.5rem;
    opacity: 0.85;
    font-size: 0.95rem;
  }
  .btn-primary {
    width: 100%;
    padding: 0.75rem 1rem;
    font-size: 1rem;
    cursor: pointer;
    border-radius: 8px;
    border: none;
    background: #4f46e5;
    color: white;
  }
  .btn-primary:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }
  .error {
    color: #f87171;
    margin-bottom: 1rem;
  }
  .hint {
    margin-top: 1rem;
    font-size: 0.85rem;
    opacity: 0.8;
    word-break: break-all;
  }
</style>
