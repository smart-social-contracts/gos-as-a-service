<script>
  import { _ } from 'svelte-i18n';

  export let authLoading = false;
  export let isLoggedIn = false;
  export let userPrincipal = null;
  export let onLogin = () => {};
  export let onLogout = () => {};
</script>

<div class="auth-section">
  {#if authLoading}
    <div class="auth-loading" aria-hidden="true"></div>
  {:else if isLoggedIn && userPrincipal}
    <div class="user-menu">
      <a href="/my-dashboard" class="user-principal-btn" title={userPrincipal.toText()}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
          <circle cx="12" cy="7" r="4"></circle>
        </svg>
        {userPrincipal.toText().slice(0, 5)}...{userPrincipal.toText().slice(-3)}
      </a>
      <button
        class="icon-btn logout-btn"
        on:click={onLogout}
        title={$_('auth.logout')}
        aria-label={$_('auth.logout')}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path>
          <polyline points="16 17 21 12 16 7"></polyline>
          <line x1="21" y1="12" x2="9" y2="12"></line>
        </svg>
      </button>
    </div>
  {:else}
    <button
      class="icon-btn login-btn"
      on:click={onLogin}
      title={$_('auth.login')}
      aria-label={$_('auth.login')}
    >
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
        <circle cx="12" cy="7" r="4"></circle>
      </svg>
    </button>
  {/if}
</div>

<style>
  .auth-section {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .user-menu {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .user-principal-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-family: monospace;
    font-size: 0.75rem;
    color: #525252;
    background: #F5F5F5;
    padding: 0.5rem 0.75rem;
    border-radius: 0.5rem;
    border: 1px solid #E5E5E5;
    text-decoration: none;
    transition: all 0.15s ease;
  }

  .user-principal-btn:hover {
    background: #FFFFFF;
    border-color: #525252;
    color: #171717;
  }

  .auth-loading {
    width: 20px;
    height: 20px;
    border: 2px solid #E5E5E5;
    border-top: 2px solid #525252;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  .icon-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 36px;
    height: 36px;
    padding: 0;
    background: #FFFFFF;
    border: 1px solid #E5E5E5;
    border-radius: 0.5rem;
    color: #525252;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .icon-btn:hover {
    border-color: #525252;
    color: #171717;
    background: #FAFAFA;
  }

  .icon-btn.login-btn {
    background: #171717;
    border-color: #171717;
    color: #FFFFFF;
  }

  .icon-btn.login-btn:hover {
    background: #404040;
    border-color: #404040;
    color: #FFFFFF;
  }

  .icon-btn.logout-btn:hover {
    border-color: #DC2626;
    color: #DC2626;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }
</style>
