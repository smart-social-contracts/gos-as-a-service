<script>
  import { _ } from 'svelte-i18n';
  import { onMount } from 'svelte';
  import { browser } from '$app/environment';
  
  export let userPrincipal;
  export let onClose;
  
  let loading = true;
  let credits = {
    balance: 0,
    purchases: []
  };
  let userRealms = {
    created: [],
    joined: []
  };
  
  let activeTab = 'credits';
  
  onMount(async () => {
    if (browser && userPrincipal) {
      await loadUserData();
    }
  });
  
  async function loadUserData() {
    loading = true;
    try {
      // TODO: Replace with actual backend calls
      // For now, using placeholder data structure
      
      // Simulating API call delay
      await new Promise(resolve => setTimeout(resolve, 500));
      
      // Placeholder data - will be replaced with actual backend integration
      credits = {
        balance: 0,
        purchases: []
      };
      
      userRealms = {
        created: [],
        joined: []
      };
      
    } catch (err) {
      console.error('Failed to load user data:', err);
    } finally {
      loading = false;
    }
  }
  
  function formatDate(timestamp) {
    return new Date(timestamp).toLocaleDateString(undefined, {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  }
  
  function formatCredits(amount) {
    return amount.toLocaleString();
  }
</script>

<div class="dashboard-overlay" on:click={onClose}>
  <div class="dashboard-modal" on:click|stopPropagation>
    <button class="dashboard-close" on:click={onClose}>
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M18 6L6 18M6 6l12 12"></path>
      </svg>
    </button>
    
    <div class="dashboard-header">
      <h2>{$_('dashboard.title')}</h2>
      <p class="principal-display" title={userPrincipal?.toText()}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
          <circle cx="12" cy="7" r="4"></circle>
        </svg>
        {userPrincipal?.toText()}
      </p>
    </div>
    
    <div class="dashboard-tabs">
      <button 
        class="tab-btn" 
        class:active={activeTab === 'credits'}
        on:click={() => activeTab = 'credits'}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="10"></circle>
          <path d="M12 6v12M6 12h12"></path>
        </svg>
        {$_('dashboard.credits_tab')}
      </button>
      <button 
        class="tab-btn"
        class:active={activeTab === 'realms'}
        on:click={() => activeTab = 'realms'}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
          <polyline points="9 22 9 12 15 12 15 22"></polyline>
        </svg>
        {$_('dashboard.realms_tab')}
      </button>
    </div>
    
    <div class="dashboard-content">
      {#if loading}
        <div class="loading-state">
          <div class="spinner"></div>
          <p>{$_('dashboard.loading')}</p>
        </div>
      {:else if activeTab === 'credits'}
        <div class="credits-section">
          <div class="balance-card">
            <div class="balance-label">{$_('dashboard.current_balance')}</div>
            <div class="balance-amount">{formatCredits(credits.balance)}</div>
            <div class="balance-unit">{$_('dashboard.credits_unit')}</div>
          </div>
          
          <div class="section-header">
            <h3>{$_('dashboard.purchase_history')}</h3>
          </div>
          
          {#if credits.purchases.length === 0}
            <div class="empty-state">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="2" y="5" width="20" height="14" rx="2"></rect>
                <line x1="2" y1="10" x2="22" y2="10"></line>
              </svg>
              <p>{$_('dashboard.no_purchases')}</p>
            </div>
          {:else}
            <div class="purchases-list">
              {#each credits.purchases as purchase}
                <div class="purchase-item">
                  <div class="purchase-info">
                    <span class="purchase-amount">+{formatCredits(purchase.amount)}</span>
                    <span class="purchase-date">{formatDate(purchase.date)}</span>
                  </div>
                  <div class="purchase-details">
                    <span class="purchase-type">{purchase.type}</span>
                    {#if purchase.txId}
                      <code class="purchase-tx">{purchase.txId.slice(0, 8)}...</code>
                    {/if}
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {:else if activeTab === 'realms'}
        <div class="realms-section">
          <div class="section-header">
            <h3>{$_('dashboard.created_realms')}</h3>
            <span class="count-badge">{userRealms.created.length}</span>
          </div>
          
          {#if userRealms.created.length === 0}
            <div class="empty-state small">
              <p>{$_('dashboard.no_created_realms')}</p>
            </div>
          {:else}
            <div class="realms-list">
              {#each userRealms.created as realm}
                <div class="realm-item">
                  <div class="realm-icon">
                    {#if realm.logo}
                      <img src={realm.logo} alt={realm.name} />
                    {:else}
                      <span>{realm.name.charAt(0).toUpperCase()}</span>
                    {/if}
                  </div>
                  <div class="realm-info">
                    <span class="realm-name">{realm.name}</span>
                    <code class="realm-id">{realm.id}</code>
                  </div>
                  <span class="realm-role owner">{$_('dashboard.role_owner')}</span>
                </div>
              {/each}
            </div>
          {/if}
          
          <div class="section-header">
            <h3>{$_('dashboard.joined_realms')}</h3>
            <span class="count-badge">{userRealms.joined.length}</span>
          </div>
          
          {#if userRealms.joined.length === 0}
            <div class="empty-state small">
              <p>{$_('dashboard.no_joined_realms')}</p>
            </div>
          {:else}
            <div class="realms-list">
              {#each userRealms.joined as realm}
                <div class="realm-item">
                  <div class="realm-icon">
                    {#if realm.logo}
                      <img src={realm.logo} alt={realm.name} />
                    {:else}
                      <span>{realm.name.charAt(0).toUpperCase()}</span>
                    {/if}
                  </div>
                  <div class="realm-info">
                    <span class="realm-name">{realm.name}</span>
                    <code class="realm-id">{realm.id}</code>
                  </div>
                  <span class="realm-role member">{$_('dashboard.role_member')}</span>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      {/if}
    </div>
  </div>
</div>

<style>
  .dashboard-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
    padding: 1rem;
  }
  
  .dashboard-modal {
    background: #FFFFFF;
    border-radius: 1rem;
    width: 100%;
    max-width: 600px;
    max-height: 80vh;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    position: relative;
    box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  }
  
  .dashboard-close {
    position: absolute;
    top: 1rem;
    right: 1rem;
    background: none;
    border: none;
    padding: 0.5rem;
    cursor: pointer;
    color: #737373;
    border-radius: 0.5rem;
    transition: all 0.15s ease;
    z-index: 10;
  }
  
  .dashboard-close:hover {
    background: #F5F5F5;
    color: #171717;
  }
  
  .dashboard-header {
    padding: 1.5rem 2rem 1rem;
    border-bottom: 1px solid #E5E5E5;
  }
  
  .dashboard-header h2 {
    margin: 0 0 0.5rem;
    font-size: 1.5rem;
    font-weight: 600;
    color: #171717;
  }
  
  .principal-display {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-family: monospace;
    font-size: 0.75rem;
    color: #737373;
    background: #F5F5F5;
    padding: 0.5rem 0.75rem;
    border-radius: 0.5rem;
    margin: 0;
    word-break: break-all;
  }
  
  .principal-display svg {
    flex-shrink: 0;
  }
  
  .dashboard-tabs {
    display: flex;
    padding: 0 1rem;
    border-bottom: 1px solid #E5E5E5;
    background: #FAFAFA;
  }
  
  .tab-btn {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 1rem 1.5rem;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: #737373;
    font-size: 0.9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  
  .tab-btn:hover {
    color: #171717;
  }
  
  .tab-btn.active {
    color: #171717;
    border-bottom-color: #171717;
  }
  
  .dashboard-content {
    flex: 1;
    overflow-y: auto;
    padding: 1.5rem 2rem;
  }
  
  .loading-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 3rem;
    color: #737373;
  }
  
  .spinner {
    width: 32px;
    height: 32px;
    border: 3px solid #E5E5E5;
    border-top: 3px solid #525252;
    border-radius: 50%;
    animation: spin 1s linear infinite;
    margin-bottom: 1rem;
  }
  
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  
  .balance-card {
    background: linear-gradient(135deg, #171717 0%, #404040 100%);
    color: #FFFFFF;
    border-radius: 1rem;
    padding: 1.5rem;
    text-align: center;
    margin-bottom: 1.5rem;
  }
  
  .balance-label {
    font-size: 0.85rem;
    color: rgba(255, 255, 255, 0.7);
    margin-bottom: 0.5rem;
  }
  
  .balance-amount {
    font-size: 2.5rem;
    font-weight: 700;
    line-height: 1;
  }
  
  .balance-unit {
    font-size: 0.85rem;
    color: rgba(255, 255, 255, 0.7);
    margin-top: 0.25rem;
  }
  
  .section-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1rem;
    margin-top: 1rem;
  }
  
  .section-header:first-child {
    margin-top: 0;
  }
  
  .section-header h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: #171717;
  }
  
  .count-badge {
    background: #F5F5F5;
    color: #525252;
    font-size: 0.75rem;
    font-weight: 500;
    padding: 0.25rem 0.5rem;
    border-radius: 1rem;
  }
  
  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 2rem;
    color: #A3A3A3;
    text-align: center;
  }
  
  .empty-state.small {
    padding: 1.5rem;
  }
  
  .empty-state svg {
    margin-bottom: 0.75rem;
    opacity: 0.5;
  }
  
  .empty-state p {
    margin: 0;
    font-size: 0.9rem;
  }
  
  .purchases-list {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  
  .purchase-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    background: #FAFAFA;
    border-radius: 0.75rem;
    border: 1px solid #E5E5E5;
  }
  
  .purchase-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }
  
  .purchase-amount {
    font-weight: 600;
    color: #16a34a;
    font-size: 1rem;
  }
  
  .purchase-date {
    font-size: 0.8rem;
    color: #737373;
  }
  
  .purchase-details {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.25rem;
  }
  
  .purchase-type {
    font-size: 0.8rem;
    color: #525252;
    background: #E5E5E5;
    padding: 0.2rem 0.5rem;
    border-radius: 0.25rem;
  }
  
  .purchase-tx {
    font-size: 0.7rem;
    color: #737373;
    background: none;
  }
  
  .realms-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .realm-item {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.75rem 1rem;
    background: #FAFAFA;
    border-radius: 0.75rem;
    border: 1px solid #E5E5E5;
  }
  
  .realm-icon {
    width: 40px;
    height: 40px;
    border-radius: 0.5rem;
    background: #E5E5E5;
    display: flex;
    align-items: center;
    justify-content: center;
    overflow: hidden;
    flex-shrink: 0;
  }
  
  .realm-icon img {
    width: 100%;
    height: 100%;
    object-fit: cover;
  }
  
  .realm-icon span {
    font-weight: 600;
    color: #525252;
    font-size: 1.1rem;
  }
  
  .realm-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: 0.2rem;
  }
  
  .realm-name {
    font-weight: 500;
    color: #171717;
    font-size: 0.95rem;
  }
  
  .realm-id {
    font-size: 0.7rem;
    color: #737373;
    background: none;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  
  .realm-role {
    font-size: 0.75rem;
    font-weight: 500;
    padding: 0.25rem 0.75rem;
    border-radius: 1rem;
    flex-shrink: 0;
  }
  
  .realm-role.owner {
    background: #FEF3C7;
    color: #92400E;
  }
  
  .realm-role.member {
    background: #DBEAFE;
    color: #1E40AF;
  }
  
  @media (max-width: 640px) {
    .dashboard-modal {
      max-height: 90vh;
      border-radius: 1rem 1rem 0 0;
      margin-top: auto;
    }
    
    .dashboard-content {
      padding: 1rem;
    }
    
    .dashboard-header {
      padding: 1rem;
    }
    
    .tab-btn {
      padding: 0.75rem 1rem;
      font-size: 0.85rem;
    }
  }
</style>
