<script>
  import { onMount } from 'svelte';
  import { browser } from '$app/environment';
  import { goto } from '$app/navigation';
  import { page } from '$app/stores';
  import { _, locale } from 'svelte-i18n';
  import { CONFIG } from '$lib/config.js';
  import DeploymentProgress from '$lib/components/DeploymentProgress.svelte';
  import { deploymentJobUrl } from '$lib/deployment-tracker.js';
  import {
    filterVisibleDrafts,
    findDraftForDeployment,
    draftResumeUrl,
    isFailedDeployment,
    canDestroyRealm,
  } from '$lib/wizard-drafts.js';
  import { stageLabel } from '$lib/realm-stages.js';
  import ConfirmModal from '$lib/components/ConfirmModal.svelte';
  import ConnectClaude from '$lib/components/ConnectClaude.svelte';
  import {
    indexCreatedRealmsByBackend,
    preferredVisitUrl,
    registryEntryForDeployment,
  } from '$lib/user-created-realms.js';
  import {
    buildDashboardDeploymentCards,
    deploymentToDestroyRecord,
  } from '$lib/realm-destroy-progress.js';
  import {
    dismissDestroyRecord,
    loadDestroyRecords,
    saveDestroyRecord,
  } from '$lib/realm-destroy-records.js';

  let userPrincipal = null;
  let loading = true;
  let activeTab = 'realms';

  // Invitation status
  let invitationActivated = false;
  let invitationModeOn = false;
  
  // Read tab from URL parameter (?tab=realms | billing | credits | connect)
  $: if (browser && $page.url.searchParams.get('tab')) {
    const tabParam = $page.url.searchParams.get('tab');
    if (tabParam === 'realms') {
      activeTab = 'realms';
    } else if (tabParam === 'connect') {
      activeTab = 'connect';
    } else if (tabParam === 'billing' || tabParam === 'credits') {
      activeTab = 'billing';
    }
  }
  
  // Billing — registry balance (same source as deploy); billing /credits proxies chain
  let balance = 0;
  let spentThisMonth = 0;
  let predictedThisMonth = 0;
  let purchases = [];
  let loadingCredits = true;
  
  // Registry rows keyed by backend canister (merged into deployment cards)
  let createdRealms = [];

  // Deployments data
  let deployments = [];
  /** Full installer job list (before dedupe) for created-realms resolution. */
  let rawDeploymentJobs = [];
  let totalDeploymentJobCount = 0;
  let loadingDeployments = true;
  let deploymentPollInterval = null;
  let deletingDeploymentId = null;
  let deploymentDeleteError = null;
  let deleteConfirmDeployment = null;
  let destroyConfirmDeployment = null;
  /** @type {Record<string, { deployment: object, stageIndex: number, startedAt: number, error?: string, complete?: boolean }>} */
  let activeDestroys = {};
  /** @type {object[]} persisted destroyed-realm cards */
  let destroyRecords = [];
  let dismissingDestroyedId = null;
  let deploymentDestroyError = null;
  /** @type {Record<string, string>} job_id -> lifecycle stage */
  let deploymentRealmStages = {};
  /** Expanded redeploy history panels (canonical job id). */
  let expandedJobHistory = {};

  $: dashboardCards = buildDashboardDeploymentCards(
    deployments,
    destroyRecords,
    activeDestroys,
  );
  $: hasVisibleRealms =
    dashboardCards.length > 0 || loadingDeployments || destroyRecords.length > 0;

  // Wizard drafts
  let wizardDrafts = [];
  let loadingDrafts = true;
  
  // Top-up state
  let topUpAmount = 10;
  let topUpLoading = false;
  let topUpError = null;

  // Voucher state
  let voucherCode = '';
  let voucherLoading = false;
  let voucherError = null;
  let voucherSuccess = null;
  let redeemedVouchers = [];

  // Billing service URL - should be configured per environment
  const BILLING_SERVICE_URL = CONFIG.billing_service_url || 'http://localhost:8001';

  onMount(async () => {
    if (browser) {
      // Check if user is authenticated
      const { isAuthenticated, getPrincipal, ensureTestAuth } = await import('$lib/auth.js');
      const { getTestModeIIBypass } = await import('$lib/config.js');

      let authenticated = false;
      if (getTestModeIIBypass()) {
        const result = await ensureTestAuth();
        authenticated = !!result.principal;
      } else {
        authenticated = await isAuthenticated();
      }
      
      if (!authenticated) {
        // Redirect to home if not logged in
        goto('/');
        return;
      }
      
      userPrincipal = await getPrincipal();
      destroyRecords = loadDestroyRecords(userPrincipal.toText());
      loading = false;

      // Check invitation activation status
      try {
        const { backend } = await import('$lib/canisters.js');
        const modeResult = await backend.get_invitation_mode();
        invitationModeOn = modeResult?.Ok === 'enabled';
        if (invitationModeOn && userPrincipal) {
          const actResult = await backend.is_principal_activated(userPrincipal.toText());
          invitationActivated = actResult?.Ok === 'activated';
        }
      } catch (e) {
        console.error('Invitation status check failed:', e);
      }
      
      await loadDeployments();
      loadWizardDrafts();
      
      loadVouchers();
      await loadCredits();
      
      // Start polling for deployment status updates
      startDeploymentPolling();
    }
  });
  
  import { onDestroy } from 'svelte';
  
  onDestroy(() => {
    // Clean up polling interval
    if (deploymentPollInterval) {
      clearInterval(deploymentPollInterval);
    }
  });

  async function loadCredits() {
    if (!userPrincipal) return;
    loadingCredits = true;
    try {
      const { fetchUserBillingSummary } = await import('$lib/user-credits.js');
      const summary = await fetchUserBillingSummary(
        userPrincipal.toText(),
        createdRealms.length
      );
      balance = summary.balance;
      spentThisMonth = summary.spentThisMonth;
      predictedThisMonth = summary.predictedThisMonth;
      purchases = [];
    } catch (err) {
      console.error('Failed to load credits:', err);
      balance = 0;
      spentThisMonth = 0;
      predictedThisMonth = 0;
      purchases = [];
    } finally {
      loadingCredits = false;
    }
  }

  async function refreshRegistryEntries({ refreshCredits = true } = {}) {
    if (!userPrincipal) return;
    try {
      const { fetchCreatedRealmsForUser } = await import('$lib/user-created-realms.js');
      const next = await fetchCreatedRealmsForUser(
        userPrincipal.toText(),
        rawDeploymentJobs.length ? rawDeploymentJobs : deployments,
      );
      createdRealms = next;
      if (refreshCredits) await loadCredits();
    } catch (err) {
      console.error('Failed to load registry entries:', err);
      // Keep previous createdRealms — avoids list flicker on transient errors.
    }
  }

  async function loadWizardDrafts() {
    if (!userPrincipal) return;
    loadingDrafts = true;
    try {
      const { listWizardDrafts } = await import('$lib/wizard-drafts.js');
      wizardDrafts = await listWizardDrafts();
    } catch (err) {
      console.error('Failed to load wizard drafts:', err);
      wizardDrafts = [];
    } finally {
      loadingDrafts = false;
    }
  }

  async function deleteDraft(draftId) {
    try {
      const { deleteWizardDraft } = await import('$lib/wizard-drafts.js');
      await deleteWizardDraft(draftId);
      wizardDrafts = wizardDrafts.filter((d) => d.id !== draftId);
    } catch (e) {
      console.error('Failed to delete draft:', e);
    }
  }

  function draftStepLabel(step) {
    const labels = ['Codex', 'Land & Tokens', 'Extensions', 'Data', 'Basics', 'Branding', 'Deploy'];
    return labels[step] || `Step ${(step || 0) + 1}`;
  }

  $: visibleDrafts = filterVisibleDrafts(wizardDrafts, deployments);
  $: registryByBackend = indexCreatedRealmsByBackend(createdRealms);

  function registryEntryFor(deployment) {
    return registryEntryForDeployment(deployment, registryByBackend);
  }

  function visitUrlFor(deployment) {
    return preferredVisitUrl(deployment, registryEntryFor(deployment));
  }

  function toggleJobHistory(deploymentId) {
    if (!deploymentId) return;
    expandedJobHistory = {
      ...expandedJobHistory,
      [deploymentId]: !expandedJobHistory[deploymentId],
    };
  }

  function jobHistoryStatusLabel(rawStatus) {
    const st = (rawStatus || '').toLowerCase();
    if (st === 'completed') return 'Complete';
    if (st === 'failed' || st === 'failed_verification') return 'Failed';
    if (st === 'cancelled') return 'Cancelled';
    if (
      st === 'pending' ||
      st === 'provisioning' ||
      st === 'deploying' ||
      st === 'verifying' ||
      st === 'extensions' ||
      st === 'registering'
    ) {
      return 'In progress';
    }
    return rawStatus || 'Unknown';
  }

  function editDraftUrlForDeployment(deployment) {
    const draft = findDraftForDeployment(wizardDrafts, deployment);
    if (!draft) return '/create-realm';
    return `${draftResumeUrl(draft, 6)}&edit=1`;
  }

  function retryDeployUrlForDeployment(deployment) {
    const draft = findDraftForDeployment(wizardDrafts, deployment);
    if (!draft) return '/create-realm';
    return draftResumeUrl(draft, 6);
  }

  function requestDeleteDeployment(deployment) {
    if (!deployment?.deployment_id || deletingDeploymentId) return;
    deleteConfirmDeployment = deployment;
  }

  function cancelDeleteDeployment() {
    deleteConfirmDeployment = null;
  }

  async function confirmDeleteDeployment() {
    const deployment = deleteConfirmDeployment;
    if (!deployment) return;
    const jobId = deployment.deployment_id;
    deletingDeploymentId = jobId;
    deploymentDeleteError = null;
    try {
      const { deleteDeploymentJob } = await import('$lib/installer-queue.js');
      await deleteDeploymentJob(jobId);
      deployments = deployments.filter((d) => d.deployment_id !== jobId);
      deleteConfirmDeployment = null;
      await loadWizardDrafts();
    } catch (err) {
      console.error('Failed to delete deployment:', err);
      deploymentDeleteError = err?.message || 'Failed to delete deployment.';
    } finally {
      deletingDeploymentId = null;
    }
  }

  function requestDestroyDeployment(deployment) {
    if (!deployment?.deployment_id || activeDestroys[deployment.deployment_id]) return;
    destroyConfirmDeployment = deployment;
  }

  function cancelDestroyDeployment() {
    destroyConfirmDeployment = null;
  }

  async function runDestroyForDeployment(deployment) {
    const jobId = deployment?.deployment_id;
    if (!jobId || !userPrincipal) return;

    activeDestroys = {
      ...activeDestroys,
      [jobId]: {
        deployment: { ...deployment },
        stageIndex: 0,
        startedAt: Date.now(),
        error: null,
        complete: false,
      },
    };

    try {
      const { destroyRealmJob } = await import('$lib/installer-queue.js');
      await destroyRealmJob(jobId, {
        backendCanisterId: deployment.backend_canister_id || '',
        onProgress: (update) => {
          const current = activeDestroys[jobId];
          if (!current) return;
          activeDestroys = {
            ...activeDestroys,
            [jobId]: {
              ...current,
              stageIndex: update.stageIndex ?? current.stageIndex,
              complete: update.complete ?? current.complete,
              error: null,
            },
          };
        },
      });

      const finished = activeDestroys[jobId];
      if (finished) {
        saveDestroyRecord(
          userPrincipal.toText(),
          deploymentToDestroyRecord(finished.deployment, Date.now()),
        );
        destroyRecords = loadDestroyRecords(userPrincipal.toText());
      }

      const { [jobId]: _removed, ...restDestroys } = activeDestroys;
      activeDestroys = restDestroys;
      const { [jobId]: _stage, ...restStages } = deploymentRealmStages;
      deploymentRealmStages = restStages;

      await loadWizardDrafts();
      await loadDeployments();
    } catch (err) {
      console.error('Failed to destroy realm:', err);
      const current = activeDestroys[jobId];
      if (current) {
        activeDestroys = {
          ...activeDestroys,
          [jobId]: {
            ...current,
            error: err?.message || 'Failed to destroy realm.',
          },
        };
      }
    }
  }

  function confirmDestroyDeployment() {
    const deployment = destroyConfirmDeployment;
    if (!deployment) return;
    destroyConfirmDeployment = null;
    deploymentDestroyError = null;
    runDestroyForDeployment(deployment);
  }

  function dismissDestroyedCard(deployment) {
    const jobId = deployment?.deployment_id;
    if (!jobId || !userPrincipal || dismissingDestroyedId) return;
    dismissingDestroyedId = jobId;
    dismissDestroyRecord(userPrincipal.toText(), jobId);
    destroyRecords = loadDestroyRecords(userPrincipal.toText());
    dismissingDestroyedId = null;
  }

  function retryDestroyDeployment(deployment) {
    if (!deployment?.deployment_id || activeDestroys[deployment.deployment_id]) return;
    deploymentDestroyError = null;
    runDestroyForDeployment(deployment);
  }

  function deploymentStage(deployment) {
    return deploymentRealmStages[deployment?.deployment_id] || null;
  }

  async function loadDeploymentRealmStages(rows = deployments) {
    try {
      const { fetchDeploymentRealmStages } = await import('$lib/realm-stage-client.js');
      deploymentRealmStages = await fetchDeploymentRealmStages(rows);
    } catch (err) {
      console.warn('Failed to load realm stages:', err);
      deploymentRealmStages = {};
    }
  }

  async function loadDeployments() {
    if (!userPrincipal) return;
    loadingDeployments = true;
    try {
      const { fetchDeploymentJobsFromInstaller, prepareDashboardDeploymentRows } = await import(
        '$lib/installer-queue.js'
      );
      const jobs = await fetchDeploymentJobsFromInstaller();
      const { rawJobs, deployments: rows, totalJobCount } = prepareDashboardDeploymentRows(
        jobs,
        userPrincipal.toText(),
      );
      rawDeploymentJobs = rawJobs;
      totalDeploymentJobCount = totalJobCount;
      deployments = rows;
      await loadDeploymentRealmStages(deployments);
      await refreshRegistryEntries({ refreshCredits: false });
    } catch (err) {
      console.error('Failed to load deployments:', err);
      if (!deployments.length) deployments = [];
    } finally {
      loadingDeployments = false;
    }
  }

  function startDeploymentPolling() {
    // Poll every 10 seconds for deployment status updates
    deploymentPollInterval = setInterval(async () => {
      const hasActiveDeployments = deployments.some((d) => d.progress?.isActive);
      if (hasActiveDeployments) {
        await loadDeployments();
        await loadWizardDrafts();
      }
    }, 10000);
  }

  function toTimestampMs(value) {
    if (value == null || value === '') return null;
    const n = typeof value === 'bigint' ? Number(value) : Number(value);
    if (!Number.isFinite(n) || n <= 0) return null;
    // nat64 seconds vs millisecond epoch
    return n > 1e12 ? n : n * 1000;
  }

  function formatDate(dateValue) {
    const ms = toTimestampMs(dateValue);
    if (ms == null) {
      if (typeof dateValue === 'string' && dateValue.trim()) {
        const parsed = Date.parse(dateValue);
        if (!Number.isNaN(parsed)) return new Date(parsed).toLocaleString();
        return dateValue;
      }
      return '';
    }
    return new Date(ms).toLocaleString();
  }

  async function loadVouchers() {
    if (!userPrincipal) return;
    try {
      const response = await fetch(`${BILLING_SERVICE_URL}/voucher/redemptions/${userPrincipal.toText()}`);
      if (response.ok) {
        redeemedVouchers = await response.json();
      }
    } catch (err) {
      console.error('Failed to load vouchers:', err);
    }
  }

  async function handleRedeemVoucher() {
    if (!userPrincipal || !voucherCode.trim()) return;
    
    voucherLoading = true;
    voucherError = null;
    voucherSuccess = null;
    
    try {
      const response = await fetch(`${BILLING_SERVICE_URL}/voucher/redeem`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          principal_id: userPrincipal.toText(),
          code: voucherCode.trim(),
        }),
      });
      
      const data = await response.json();
      
      if (!response.ok || !data.success) {
        voucherError = data.message || data.detail || 'Failed to redeem voucher';
        return;
      }
      
      voucherSuccess = data.message;
      voucherCode = '';
      if (data.data && data.data.balance != null) {
        balance = Number(data.data.balance);
      }
      await Promise.all([loadCredits(), loadVouchers()]);
      
    } catch (err) {
      console.error('Voucher redemption failed:', err);
      voucherError = 'Failed to redeem voucher. Please try again.';
    } finally {
      voucherLoading = false;
    }
  }

  async function handleTopUp() {
    if (!userPrincipal || topUpAmount < 1 || topUpAmount > 50) return;
    
    topUpLoading = true;
    topUpError = null;
    
    try {
      const response = await fetch(`${BILLING_SERVICE_URL}/checkout/create-session`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          principal_id: userPrincipal.toText(),
          amount: topUpAmount,
        }),
      });
      
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to create checkout session');
      }
      
      const data = await response.json();
      
      // Redirect to Stripe checkout
      window.location.href = data.checkout_url;
    } catch (err) {
      console.error('Top-up failed:', err);
      topUpError = err.message;
    } finally {
      topUpLoading = false;
    }
  }
</script>

<svelte:head>
  <title>{$_('dashboard.title')} | Realms</title>
</svelte:head>

<div class="dashboard-page">
  <div class="dashboard-container">
    <!-- Header -->
    <header class="dashboard-header">
      <a href="/" class="back-link">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        {$_('dashboard.back_to_realms')}
      </a>
      <h1>{$_('dashboard.title')}</h1>
      {#if userPrincipal}
        <div class="principal-display">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
          </svg>
          <span class="principal-text">{userPrincipal.toText()}</span>
        </div>
        {#if invitationModeOn}
          <div class="invitation-status" class:activated={invitationActivated}>
            {#if invitationActivated}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                <path d="M20 6L9 17l-5-5"/>
              </svg>
              Invitation redeemed
            {:else}
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <circle cx="12" cy="12" r="10"/>
                <line x1="12" y1="8" x2="12" y2="12"/>
                <line x1="12" y1="16" x2="12.01" y2="16"/>
              </svg>
              Invitation required — <a href="/create-realm">redeem a code</a>
            {/if}
          </div>
        {/if}
      {/if}
    </header>

    {#if loading}
      <div class="loading-container">
        <div class="spinner"></div>
        <p>{$_('dashboard.loading')}</p>
      </div>
    {:else}
      <!-- Tabs -->
      <div class="tabs">
        <button 
          class="tab" 
          class:active={activeTab === 'realms'}
          on:click={() => activeTab = 'realms'}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"></path>
            <polyline points="9 22 9 12 15 12 15 22"></polyline>
          </svg>
          {$_('dashboard.realms_tab')}
        </button>
        <button 
          class="tab" 
          class:active={activeTab === 'billing'}
          on:click={() => activeTab = 'billing'}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="2" y="5" width="20" height="14" rx="2" ry="2"></rect>
            <line x1="2" y1="10" x2="22" y2="10"></line>
          </svg>
          {$_('dashboard.billing_tab')}
        </button>
        <button
          class="tab"
          class:active={activeTab === 'connect'}
          on:click={() => activeTab = 'connect'}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M10.5 13.5a5 5 0 0 0 7.07 0l2-2a5 5 0 0 0-7.07-7.07l-1.15 1.14"></path>
            <path d="M13.5 10.5a5 5 0 0 0-7.07 0l-2 2a5 5 0 0 0 7.07 7.07l1.14-1.14"></path>
          </svg>
          {$_('dashboard.connect_tab', { default: 'Connect Claude' })}
        </button>
      </div>

      <!-- Tab Content -->
      <div class="tab-content">
        {#if activeTab === 'billing'}
          <div class="credits-section">
            <!-- Balance Card -->
            <div class="balance-card">
              <div class="balance-label">{$_('dashboard.current_balance')}</div>
              {#if loadingCredits}
                <div class="balance-loading"></div>
              {:else}
                <div class="balance-value">{balance}</div>
              {/if}
              <div class="balance-unit">{$_('dashboard.credits_unit')}</div>
            </div>

            <div class="usage-summary">
              <div class="usage-stat">
                <span class="usage-label">{$_('dashboard.spent_this_month')}</span>
                {#if loadingCredits}
                  <span class="usage-value loading">—</span>
                {:else}
                  <span class="usage-value">{spentThisMonth} {$_('dashboard.credits_unit')}</span>
                {/if}
              </div>
              <div class="usage-stat">
                <span class="usage-label">{$_('dashboard.predicted_this_month')}</span>
                {#if loadingCredits}
                  <span class="usage-value loading">—</span>
                {:else}
                  <span class="usage-value">{predictedThisMonth} {$_('dashboard.credits_unit')}</span>
                {/if}
              </div>
            </div>

            <!-- Voucher Redemption Section -->
            <div class="voucher-section">
              <h3>Redeem Voucher</h3>
              <p class="voucher-description">Have a voucher code? Enter it below to redeem credits.</p>
              
              <div class="voucher-form">
                <div class="voucher-input-group">
                  <input 
                    type="text" 
                    bind:value={voucherCode}
                    placeholder="Enter voucher code"
                    class="voucher-input"
                    class:error={voucherError}
                    disabled={voucherLoading}
                  />
                  <button 
                    class="voucher-btn"
                    on:click={handleRedeemVoucher}
                    disabled={voucherLoading || !voucherCode.trim()}
                  >
                    {#if voucherLoading}
                      <div class="btn-spinner"></div>
                    {:else}
                      Redeem
                    {/if}
                  </button>
                </div>
                
                {#if voucherError}
                  <div class="error-message">{voucherError}</div>
                {/if}
                
                {#if voucherSuccess}
                  <div class="success-message">{voucherSuccess}</div>
                {/if}
              </div>
            </div>

            <!-- Top-up Section -->
            <div class="topup-section">
              <h3>{$_('dashboard.topup_title')}</h3>
              <p class="topup-description">
                {$_('dashboard.topup_description')}
                <a href="/faq" class="help-link" title="Learn more about credits" aria-label="Learn more about credits">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <circle cx="12" cy="12" r="10"></circle>
                    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
                    <line x1="12" y1="17" x2="12.01" y2="17"></line>
                  </svg>
                </a>
              </p>
              
              <div class="topup-form">
                <div class="amount-input-group">
                  <label for="topup-amount">{$_('dashboard.topup_amount')}</label>
                  <div class="amount-controls">
                    <button 
                      class="amount-btn"
                      on:click={() => topUpAmount = Math.max(1, topUpAmount - 1)}
                      disabled={topUpAmount <= 1}
                    >−</button>
                    <input 
                      type="number" 
                      id="topup-amount"
                      bind:value={topUpAmount}
                      min="1"
                      max="50"
                      class="amount-input"
                    />
                    <button 
                      class="amount-btn"
                      on:click={() => topUpAmount = Math.min(50, topUpAmount + 1)}
                      disabled={topUpAmount >= 50}
                    >+</button>
                  </div>
                  <div class="amount-range">1 - 50 {$_('dashboard.credits_unit')}</div>
                </div>

                <div class="topup-summary">
                  <div class="summary-row">
                    <span>{$_('dashboard.topup_credits')}</span>
                    <span>{topUpAmount} {$_('dashboard.credits_unit')}</span>
                  </div>
                  <div class="summary-row total">
                    <span>{$_('dashboard.topup_total')}</span>
                    <span>${topUpAmount}.00 USD</span>
                  </div>
                </div>

                {#if topUpError}
                  <div class="error-message">{topUpError}</div>
                {/if}

                <button 
                  class="topup-btn"
                  on:click={handleTopUp}
                  disabled={topUpLoading || topUpAmount < 1 || topUpAmount > 50}
                >
                  {#if topUpLoading}
                    <div class="btn-spinner"></div>
                    {$_('dashboard.processing')}
                  {:else}
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                      <rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect>
                      <line x1="1" y1="10" x2="23" y2="10"></line>
                    </svg>
                    {$_('dashboard.topup_button')}
                  {/if}
                </button>
              </div>
            </div>

            <!-- Redeemed Vouchers -->
            {#if redeemedVouchers.length > 0}
              <div class="history-section">
                <h3>Redeemed Vouchers</h3>
                <ul class="purchase-list">
                  {#each redeemedVouchers as voucher}
                    <li class="purchase-item">
                      <div class="purchase-info">
                        <span class="purchase-amount">+{voucher.credits} {$_('dashboard.credits_unit')}</span>
                        <span class="purchase-date">Code: {voucher.code}</span>
                      </div>
                      <span class="voucher-badge" class:active={voucher.status === 'active'}>
                        {voucher.status === 'active' ? 'Active' : 'Used'}
                      </span>
                    </li>
                  {/each}
                </ul>
              </div>
            {/if}

            <!-- Purchase History -->
            <div class="history-section">
              <h3>{$_('dashboard.purchase_history')}</h3>
              {#if loadingCredits}
                <div class="loading-placeholder"></div>
              {:else if purchases.length === 0 && redeemedVouchers.length === 0}
                <div class="empty-state">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
                    <rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect>
                    <line x1="8" y1="21" x2="16" y2="21"></line>
                    <line x1="12" y1="17" x2="12" y2="21"></line>
                  </svg>
                  <p>{$_('dashboard.no_purchases')}</p>
                </div>
              {:else if purchases.length > 0}
                <ul class="purchase-list">
                  {#each purchases as purchase}
                    <li class="purchase-item">
                      <div class="purchase-info">
                        <span class="purchase-amount">+{purchase.amount} {$_('dashboard.credits_unit')}</span>
                        <span class="purchase-date">{formatDate(purchase.date)}</span>
                      </div>
                      <span class="purchase-price">${purchase.price}</span>
                    </li>
                  {/each}
                </ul>
              {:else}
                <p class="no-purchases-note">No card purchases yet</p>
              {/if}
            </div>
          </div>

        {:else if activeTab === 'realms'}
          <div class="realms-section">
            <!-- Create Realm Button -->
            <div class="create-realm-header">
              <a href="/create-realm" class="create-realm-btn">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M12 5v14M5 12h14"/>
                </svg>
                Create Realm
              </a>
            </div>

            <!-- Wizard drafts (in-progress realm creation) -->
            <div class="realms-group drafts-group">
              <h3>Drafts</h3>
              {#if loadingDrafts}
                <div class="loading-placeholder"></div>
              {:else if visibleDrafts.length === 0}
                <div class="empty-state compact">
                  <p>No drafts yet. Start the wizard to save progress automatically.</p>
                </div>
              {:else}
                <ul class="draft-list">
                  {#each visibleDrafts as draft}
                    <li class="draft-item">
                      <div class="draft-info">
                        <span class="draft-name">{draft.realm_name || 'Untitled Realm'}</span>
                        <span class="draft-meta">
                          Step: {draftStepLabel(draft.current_step)}
                          {#if draft.deploy_version}
                            · v{draft.deploy_version}
                          {/if}
                          · {formatDate(draft.updated_at)}
                        </span>
                      </div>
                      <div class="draft-actions">
                        <a href={draftResumeUrl(draft)} class="btn btn-small btn-primary">Resume</a>
                        <button type="button" class="btn btn-small btn-outline" on:click={() => deleteDraft(draft.id)}>
                          Delete
                        </button>
                      </div>
                    </li>
                  {/each}
                </ul>
              {/if}
            </div>

            <!-- Realms (deployment jobs + on-chain registry status) -->
            {#if loadingDeployments && deployments.length === 0}
              <div class="realms-group deployments-group">
                <h3>{$_('dashboard.your_realms')}</h3>
                <div class="loading-placeholder"></div>
              </div>
            {:else if hasVisibleRealms}
              <div class="realms-group deployments-group">
                <h3>
                  {$_('dashboard.your_realms')}
                  {#if totalDeploymentJobCount > 0}
                    <span class="deployments-summary subtle">
                      {dashboardCards.length} shown
                      {#if totalDeploymentJobCount > deployments.length}
                        · {totalDeploymentJobCount} total jobs
                      {/if}
                    </span>
                  {/if}
                </h3>
                {#if deploymentDeleteError}
                  <p class="deployment-delete-error">{deploymentDeleteError}</p>
                {/if}
                {#if deploymentDestroyError}
                  <p class="deployment-delete-error">{deploymentDestroyError}</p>
                {/if}
                <ul class="deployment-list">
                  {#each dashboardCards as deployment (deployment.deployment_id)}
                    {@const registryEntry = deployment.cardKind === 'live' ? registryEntryFor(deployment) : null}
                    {@const visitUrl = deployment.cardKind === 'live' ? visitUrlFor(deployment) : null}
                    {@const isDestroyCard = deployment.cardKind === 'destroying' || deployment.cardKind === 'destroyed' || deployment.cardKind === 'destroy_failed'}
                    <li
                      class="deployment-item"
                      class:destroying={deployment.cardKind === 'destroying'}
                      class:destroyed={deployment.cardKind === 'destroyed'}
                      class:destroy-failed={deployment.cardKind === 'destroy_failed'}
                    >
                      <div class="deployment-info">
                        <div class="deployment-title-row">
                          <span class="deployment-name">{deployment.realm_name}</span>
                          {#if deployment.cardKind === 'destroyed'}
                            <span class="registry-badge destroyed">{$_('dashboard.destroyed_realm')}</span>
                          {:else if deployment.cardKind === 'destroying'}
                            <span class="registry-badge destroying">{$_('dashboard.destroying_live_realm')}</span>
                          {:else if registryEntry}
                            <span class="registry-badge">{$_('dashboard.on_registry')}</span>
                          {:else if deployment.raw_status === 'completed'}
                            <span class="registry-badge pending">{$_('dashboard.registering_realm')}</span>
                          {/if}
                        </div>
                        <span class="deployment-meta subtle">
                          {#if deployment.backend_canister_id}
                            {deployment.backend_canister_id}
                          {/if}
                          {#if deployment.destroyed_at}
                            · {$_('dashboard.destroyed_realm')} {formatDate(deployment.destroyed_at)}
                          {:else if deployment.created_at}
                            · {formatDate(deployment.created_at)}
                          {/if}
                        </span>
                      </div>

                      {#if isDestroyCard && deployment.destroyProgress}
                        <DeploymentProgress
                          progress={deployment.destroyProgress}
                          variant={deployment.cardKind === 'destroying' ? 'full' : 'compact'}
                          showSteps={deployment.cardKind === 'destroying'}
                        />
                      {:else}
                        <DeploymentProgress
                          progress={deployment.progress}
                          variant={deployment.progress?.isActive ? 'full' : 'compact'}
                          showSteps={deployment.progress?.isActive}
                        />
                      {/if}

                      <div class="deployment-status-row">
                        {#if deployment.cardKind === 'live' && deployment.deployment_id}
                          <a href={deploymentJobUrl(deployment.deployment_id)} class="track-btn">
                            {deployment.progress?.isActive ? 'Track deployment →' : 'View details →'}
                          </a>
                        {/if}
                        {#if deployment.cardKind === 'live' && isFailedDeployment(deployment)}
                          <a href={editDraftUrlForDeployment(deployment)} class="track-btn">Edit draft →</a>
                          <a href={retryDeployUrlForDeployment(deployment)} class="track-btn">Retry deploy →</a>
                          <button
                            type="button"
                            class="delete-deployment-btn"
                            disabled={deletingDeploymentId === deployment.deployment_id}
                            on:click={() => requestDeleteDeployment(deployment)}
                          >
                            {deletingDeploymentId === deployment.deployment_id
                              ? $_('dashboard.removing_failed_job')
                              : $_('dashboard.remove_failed_job')}
                          </button>
                        {/if}
                        {#if deployment.cardKind === 'live' && deployment.raw_status === 'completed' && visitUrl}
                          <a href={visitUrl} target="_blank" rel="noopener noreferrer" class="visit-btn">
                            Visit Realm →
                          </a>
                        {/if}
                        {#if deployment.cardKind === 'live' && deployment.raw_status === 'completed' && deploymentStage(deployment)}
                          <span class="deployment-stage-badge">{stageLabel(deploymentStage(deployment))}</span>
                        {/if}
                        {#if deployment.cardKind === 'live' && canDestroyRealm(deployment, deploymentStage(deployment))}
                          <button
                            type="button"
                            class="delete-deployment-btn"
                            disabled={!!activeDestroys[deployment.deployment_id]}
                            on:click={() => requestDestroyDeployment(deployment)}
                          >
                            {$_('dashboard.destroy_live_realm')}
                          </button>
                        {/if}
                        {#if deployment.cardKind === 'destroyed'}
                          <button
                            type="button"
                            class="delete-deployment-btn"
                            disabled={dismissingDestroyedId === deployment.deployment_id}
                            on:click={() => dismissDestroyedCard(deployment)}
                          >
                            {dismissingDestroyedId === deployment.deployment_id
                              ? $_('dashboard.removing_destroyed_realm')
                              : $_('dashboard.remove_destroyed_realm')}
                          </button>
                        {/if}
                        {#if deployment.cardKind === 'destroy_failed'}
                          <button
                            type="button"
                            class="delete-deployment-btn"
                            on:click={() => retryDestroyDeployment(deployment)}
                          >
                            {$_('dashboard.destroy_failed_retry')}
                          </button>
                        {/if}
                      </div>
                      {#if deployment.cardKind === 'live' && deployment.earlier_deploy_count > 0}
                        <div class="deployment-history">
                          <button
                            type="button"
                            class="deployment-history-toggle"
                            aria-expanded={expandedJobHistory[deployment.deployment_id] ? 'true' : 'false'}
                            on:click={() => toggleJobHistory(deployment.deployment_id)}
                          >
                            {#if expandedJobHistory[deployment.deployment_id]}
                              {$_('dashboard.hide_earlier_jobs')}
                            {:else}
                              + {deployment.earlier_deploy_count} earlier redeploy{deployment.earlier_deploy_count === 1 ? '' : 's'}
                              · {$_('dashboard.show_earlier_jobs')}
                            {/if}
                          </button>
                          {#if expandedJobHistory[deployment.deployment_id] && deployment.earlier_jobs?.length}
                            <p class="deployment-history-heading">{$_('dashboard.earlier_jobs_heading')}</p>
                            <ul class="deployment-history-list">
                              {#each deployment.earlier_jobs as job (job.deployment_id)}
                                <li class="deployment-history-item">
                                  <a
                                    href={deploymentJobUrl(job.deployment_id)}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    class="deployment-history-link"
                                  >
                                    {job.deployment_id}
                                  </a>
                                  <span class="deployment-history-status">{jobHistoryStatusLabel(job.raw_status)}</span>
                                  <span class="deployment-history-date">{formatDate(job.created_at)}</span>
                                </li>
                              {/each}
                            </ul>
                          {/if}
                        </div>
                      {/if}
                      {#if deployment.deployment_id && deployment.cardKind === 'live'}
                        <div class="deployment-id subtle">
                          Job:
                          <a
                            href={deploymentJobUrl(deployment.deployment_id)}
                            target="_blank"
                            rel="noopener noreferrer"
                            class="deployment-id-link"
                          >
                            {deployment.deployment_id}
                          </a>
                        </div>
                      {:else if deployment.deployment_id && deployment.cardKind === 'destroyed'}
                        <div class="deployment-id subtle">Job: {deployment.deployment_id}</div>
                      {/if}
                    </li>
                  {/each}
                </ul>
              </div>
            {:else if !loadingDrafts && visibleDrafts.length === 0}
              <div class="realms-group deployments-group">
                <h3>{$_('dashboard.your_realms')}</h3>
                <div class="empty-state compact">
                  <p>{$_('dashboard.no_realms_yet')}</p>
                </div>
              </div>
            {/if}

          </div>

        {:else if activeTab === 'connect'}
          <ConnectClaude principal={userPrincipal ? userPrincipal.toText() : ''} />
        {/if}
      </div>
    {/if}
  </div>

  <ConfirmModal
    open={!!deleteConfirmDeployment}
    title={$_('dashboard.remove_failed_job_title')}
    message={deleteConfirmDeployment
      ? `${$_('dashboard.remove_failed_job_confirm')} (${deleteConfirmDeployment.realm_name || deleteConfirmDeployment.deployment_id})`
      : $_('dashboard.remove_failed_job_confirm')}
    confirmLabel={$_('dashboard.remove_failed_job')}
    cancelLabel="Cancel"
    variant="danger"
    loading={!!deletingDeploymentId}
    on:cancel={cancelDeleteDeployment}
    on:confirm={confirmDeleteDeployment}
  />

  <ConfirmModal
    open={!!destroyConfirmDeployment}
    title={$_('dashboard.destroy_live_realm_title')}
    message={destroyConfirmDeployment
      ? `${$_('dashboard.destroy_live_realm_confirm')} (${destroyConfirmDeployment.realm_name || destroyConfirmDeployment.deployment_id})`
      : $_('dashboard.destroy_live_realm_confirm')}
    confirmLabel={$_('dashboard.destroy_live_realm')}
    cancelLabel="Cancel"
    variant="danger"
    on:cancel={cancelDestroyDeployment}
    on:confirm={confirmDestroyDeployment}
  />
</div>

<style>
  .dashboard-page {
    min-height: 100vh;
    background: #FAFAFA;
    padding: 2rem;
  }

  .dashboard-container {
    max-width: 800px;
    margin: 0 auto;
  }

  .dashboard-header {
    margin-bottom: 2rem;
  }

  .back-link {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    color: #525252;
    text-decoration: none;
    font-size: 0.875rem;
    margin-bottom: 1rem;
    transition: color 0.15s ease;
  }

  .back-link:hover {
    color: #171717;
  }

  .dashboard-header h1 {
    font-size: 2rem;
    font-weight: 700;
    color: #171717;
    margin: 0 0 1rem 0;
  }

  .principal-display {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    background: #F5F5F5;
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
    font-family: monospace;
    font-size: 0.75rem;
    color: #525252;
    overflow: hidden;
  }

  .principal-text {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .invitation-status {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 0.75rem;
    padding: 0.5rem 0.75rem;
    border-radius: 0.5rem;
    font-size: 0.8rem;
    font-weight: 500;
    background: #FEF3C7;
    color: #92400E;
    border: 1px solid #FDE68A;
  }

  .invitation-status.activated {
    background: #D1FAE5;
    color: #065F46;
    border-color: #A7F3D0;
  }

  .invitation-status a {
    color: inherit;
    font-weight: 600;
    text-decoration: underline;
  }

  .loading-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 4rem;
    color: #525252;
  }

  .spinner {
    width: 40px;
    height: 40px;
    border: 3px solid #E5E5E5;
    border-top-color: #171717;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  .tabs {
    display: flex;
    gap: 0.5rem;
    border-bottom: 1px solid #E5E5E5;
    margin-bottom: 1.5rem;
  }

  .tab {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    border: none;
    background: none;
    color: #525252;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    border-bottom: 2px solid transparent;
    margin-bottom: -1px;
    transition: all 0.15s ease;
  }

  .tab:hover {
    color: #171717;
  }

  .tab.active {
    color: #171717;
    border-bottom-color: #171717;
  }

  .tab-content {
    background: #FFFFFF;
    border-radius: 1rem;
    padding: 1.5rem;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
  }

  /* Credits Section */
  .balance-card {
    background: linear-gradient(135deg, #171717 0%, #404040 100%);
    color: #FFFFFF;
    padding: 2rem;
    border-radius: 1rem;
    text-align: center;
    margin-bottom: 2rem;
  }

  .balance-label {
    font-size: 0.875rem;
    opacity: 0.8;
    margin-bottom: 0.5rem;
  }

  .balance-value {
    font-size: 3rem;
    font-weight: 700;
    line-height: 1;
    margin-bottom: 0.25rem;
  }

  .balance-unit {
    font-size: 0.875rem;
    opacity: 0.8;
  }

  .usage-summary {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
    margin-bottom: 2rem;
  }

  .usage-stat {
    background: #F5F5F5;
    border-radius: 0.75rem;
    padding: 1rem 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .usage-label {
    font-size: 0.8125rem;
    color: #737373;
  }

  .usage-value {
    font-size: 1.25rem;
    font-weight: 600;
    color: #171717;
  }

  .usage-value.loading {
    color: #A3A3A3;
  }

  .balance-loading {
    width: 60px;
    height: 48px;
    background: rgba(255, 255, 255, 0.2);
    border-radius: 0.5rem;
    margin: 0 auto;
    animation: pulse 1.5s ease-in-out infinite;
  }

  @keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
  }

  /* Top-up Section */
  .topup-section {
    background: #F5F5F5;
    border-radius: 1rem;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }

  .topup-section h3 {
    font-size: 1.125rem;
    font-weight: 600;
    color: #171717;
    margin: 0 0 0.5rem 0;
  }

  .topup-description {
    color: #525252;
    font-size: 0.875rem;
    margin: 0 0 1.5rem 0;
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .help-link {
    display: inline-flex;
    align-items: center;
    color: #737373;
    transition: color 0.15s ease;
  }

  .help-link:hover {
    color: #171717;
  }

  .topup-form {
    display: flex;
    flex-direction: column;
    gap: 1.5rem;
  }

  .amount-input-group {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .amount-input-group label {
    font-size: 0.875rem;
    font-weight: 500;
    color: #171717;
  }

  .amount-controls {
    display: flex;
    align-items: center;
    gap: 0.5rem;
  }

  .amount-btn {
    width: 40px;
    height: 40px;
    border: 1px solid #E5E5E5;
    background: #FFFFFF;
    border-radius: 0.5rem;
    font-size: 1.25rem;
    color: #171717;
    cursor: pointer;
    transition: all 0.15s ease;
  }

  .amount-btn:hover:not(:disabled) {
    background: #F5F5F5;
  }

  .amount-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .amount-input {
    width: 100px;
    height: 40px;
    border: 1px solid #E5E5E5;
    border-radius: 0.5rem;
    text-align: center;
    font-size: 1.125rem;
    font-weight: 600;
    color: #171717;
  }

  .amount-input:focus {
    outline: none;
    border-color: #171717;
  }

  .amount-range {
    font-size: 0.75rem;
    color: #737373;
  }

  .topup-summary {
    background: #FFFFFF;
    border-radius: 0.5rem;
    padding: 1rem;
  }

  .summary-row {
    display: flex;
    justify-content: space-between;
    padding: 0.5rem 0;
    font-size: 0.875rem;
    color: #525252;
  }

  .summary-row.total {
    border-top: 1px solid #E5E5E5;
    margin-top: 0.5rem;
    padding-top: 1rem;
    font-weight: 600;
    color: #171717;
    font-size: 1rem;
  }

  .error-message {
    background: #FEE2E2;
    color: #DC2626;
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
    font-size: 0.875rem;
  }

  .success-message {
    background: #D1FAE5;
    color: #059669;
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
    font-size: 0.875rem;
  }

  /* Voucher Section */
  .voucher-section {
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    border-radius: 1rem;
    padding: 1.5rem;
    margin-bottom: 2rem;
  }

  .voucher-section h3 {
    font-size: 1.125rem;
    font-weight: 600;
    color: #171717;
    margin: 0 0 0.5rem 0;
  }

  .voucher-description {
    color: #525252;
    font-size: 0.875rem;
    margin: 0 0 1rem 0;
  }

  .voucher-form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .voucher-input-group {
    display: flex;
    gap: 0.5rem;
  }

  .voucher-input {
    flex: 1;
    height: 44px;
    border: 1px solid #E5E5E5;
    border-radius: 0.5rem;
    padding: 0 1rem;
    font-size: 1rem;
    text-transform: uppercase;
    background: #FFFFFF;
  }

  .voucher-input:focus {
    outline: none;
    border-color: #22C55E;
  }

  .voucher-input.error {
    border-color: #DC2626;
  }

  .voucher-input:disabled {
    background: #F5F5F5;
  }

  .voucher-btn {
    height: 44px;
    padding: 0 1.5rem;
    background: #22C55E;
    color: #FFFFFF;
    border: none;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s ease;
    display: flex;
    align-items: center;
    justify-content: center;
    min-width: 100px;
  }

  .voucher-btn:hover:not(:disabled) {
    background: #16A34A;
  }

  .voucher-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .voucher-badge {
    padding: 0.25rem 0.75rem;
    border-radius: 1rem;
    font-size: 0.75rem;
    font-weight: 500;
    background: #F5F5F5;
    color: #737373;
  }

  .voucher-badge.active {
    background: #D1FAE5;
    color: #059669;
  }

  .no-purchases-note {
    color: #737373;
    font-size: 0.875rem;
    text-align: center;
    padding: 1rem;
    margin: 0;
  }

  .topup-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.5rem;
    width: 100%;
    padding: 1rem;
    background: #171717;
    color: #FFFFFF;
    border: none;
    border-radius: 0.5rem;
    font-size: 1rem;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s ease;
  }

  .topup-btn:hover:not(:disabled) {
    background: #404040;
  }

  .topup-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  .btn-spinner {
    width: 18px;
    height: 18px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: #FFFFFF;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  /* History Section */
  .history-section h3,
  .deployments-summary {
    display: block;
    margin-top: 0.25rem;
    font-size: 0.8125rem;
    font-weight: 400;
  }

  .realms-group h3 {
    font-size: 1rem;
    font-weight: 600;
    color: #171717;
    margin: 0 0 1rem 0;
  }

  .empty-state {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 2rem;
    color: #737373;
    text-align: center;
  }

  .empty-state svg {
    margin-bottom: 1rem;
    opacity: 0.5;
  }

  .empty-state p {
    margin: 0;
    font-size: 0.875rem;
  }

  .create-realm-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 1rem;
    padding: 0.75rem 1.5rem;
    background: #171717;
    color: #FFFFFF;
    border-radius: 0.5rem;
    text-decoration: none;
    font-size: 0.875rem;
    font-weight: 600;
    transition: background 0.15s ease;
  }

  .create-realm-btn:hover {
    background: #404040;
  }

  .loading-placeholder {
    height: 100px;
    background: #F5F5F5;
    border-radius: 0.5rem;
    animation: pulse 1.5s ease-in-out infinite;
  }

  .purchase-list,
  .realm-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .purchase-item,
  .realm-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem;
    border-bottom: 1px solid #F5F5F5;
  }

  .purchase-item:last-child,
  .realm-item:last-child {
    border-bottom: none;
  }

  .purchase-info,
  .realm-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
  }

  .purchase-amount {
    font-weight: 600;
    color: #059669;
  }

  .purchase-date,
  .realm-id {
    font-size: 0.75rem;
    color: #737373;
    font-family: monospace;
  }

  .realm-status-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .realm-visit-link {
    font-size: 0.75rem;
    color: #2563EB;
    text-decoration: none;
  }

  .realm-visit-link:hover {
    text-decoration: underline;
  }

  .purchase-price {
    font-weight: 500;
    color: #171717;
  }

  .realm-name {
    font-weight: 500;
    color: #171717;
  }

  .role-badge {
    padding: 0.25rem 0.75rem;
    border-radius: 1rem;
    font-size: 0.75rem;
    font-weight: 500;
  }

  .role-badge.owner {
    background: #DBEAFE;
    color: #1D4ED8;
  }

  .role-badge.member {
    background: #D1FAE5;
    color: #059669;
  }

  /* Realms Section */
  .create-realm-header {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 1.5rem;
  }

  .realms-group {
    margin-bottom: 2rem;
  }

  .realms-group:last-child {
    margin-bottom: 0;
  }

  /* Deployments Section */
  .drafts-group {
    background: #FFFBEB;
    border: 1px solid #FDE68A;
    border-radius: 0.75rem;
    padding: 1rem;
    margin-bottom: 1rem;
  }

  .draft-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .draft-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 1rem;
    padding: 0.875rem 1rem;
    background: #FFFFFF;
    border-radius: 0.5rem;
    margin-bottom: 0.5rem;
    border: 1px solid #E5E5E5;
  }

  .draft-item:last-child {
    margin-bottom: 0;
  }

  .draft-info {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    min-width: 0;
  }

  .draft-name {
    font-weight: 600;
    color: #171717;
  }

  .draft-meta {
    font-size: 0.8125rem;
    color: #737373;
  }

  .draft-actions {
    display: flex;
    gap: 0.5rem;
    flex-shrink: 0;
  }

  .empty-state.compact {
    padding: 1rem 0;
  }

  .empty-state.compact p {
    margin: 0;
    color: #737373;
    font-size: 0.875rem;
  }

  .deployments-group {
    background: #F0FDF4;
    border: 1px solid #BBF7D0;
    border-radius: 0.75rem;
    padding: 1rem;
  }

  .deployment-list {
    list-style: none;
    padding: 0;
    margin: 0;
  }

  .deployment-item {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    padding: 1rem;
    background: #FFFFFF;
    border-radius: 0.5rem;
    margin-bottom: 0.5rem;
    border: 1px solid #E5E5E5;
  }

  .deployment-item:last-child {
    margin-bottom: 0;
  }

  .deployment-item.destroying {
    border-color: #fdba74;
    background: #fffaf5;
  }

  .deployment-item.destroyed {
    border-color: #d4d4d4;
    background: #fafafa;
    opacity: 0.92;
  }

  .deployment-item.destroy-failed {
    border-color: #fecaca;
    background: #fef2f2;
  }

  .deployment-info {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    margin-bottom: 0.75rem;
  }

  .deployment-title-row {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.5rem;
  }

  .deployment-name {
    font-weight: 600;
    color: #171717;
    font-size: 1.0625rem;
  }

  .deployment-meta {
    font-size: 0.75rem;
    font-family: ui-monospace, monospace;
    word-break: break-all;
  }

  .registry-badge {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    border-radius: 999px;
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    background: #DBEAFE;
    color: #1D4ED8;
  }

  .registry-badge.pending {
    background: #F5F5F5;
    color: #737373;
  }

  .registry-badge.destroying {
    background: #ffedd5;
    color: #c2410c;
  }

  .registry-badge.destroyed {
    background: #e5e5e5;
    color: #525252;
  }

  .deployment-date {
    font-size: 0.75rem;
    color: #737373;
  }

  .deployment-status-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
  }

  .deployment-status {
    display: inline-flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0.25rem 0.75rem;
    border-radius: 1rem;
    font-size: 0.75rem;
    font-weight: 500;
    border: 1px solid;
  }

  .spinner-tiny {
    width: 12px;
    height: 12px;
    border: 2px solid currentColor;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }

  .visit-btn,
  .track-btn {
    font-size: 0.75rem;
    color: #2563EB;
    text-decoration: none;
    font-weight: 500;
  }

  .visit-btn:hover,
  .track-btn:hover {
    text-decoration: underline;
  }

  .delete-deployment-btn {
    font-size: 0.75rem;
    color: #b91c1c;
    background: none;
    border: none;
    padding: 0;
    font-weight: 500;
    cursor: pointer;
  }

  .delete-deployment-btn:hover:not(:disabled) {
    text-decoration: underline;
  }

  .delete-deployment-btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .deployment-stage-badge {
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #0e7490;
    background: rgba(6, 182, 212, 0.14);
    padding: 0.125rem 0.5rem;
    border-radius: 999px;
  }

  .deployment-delete-error {
    margin: 0 0 0.75rem;
    font-size: 0.8125rem;
    color: #b91c1c;
  }

  .deployment-error {
    font-size: 0.75rem;
    color: #EF4444;
    cursor: help;
  }

  .credits-charged {
    font-size: 0.75rem;
    color: #737373;
  }

  .deployment-id,
  .deployment-time,
  .deployment-earlier {
    font-size: 0.75rem;
    color: #737373;
  }

  .deployment-id.subtle {
    margin-top: 0.35rem;
    font-family: ui-monospace, monospace;
  }

  .deployment-earlier.subtle {
    margin-top: 0.35rem;
  }

  .deployment-history {
    margin-top: 0.5rem;
  }

  .deployment-history-toggle {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0;
    border: none;
    background: none;
    font-size: 0.75rem;
    color: #525252;
    cursor: pointer;
    text-align: left;
  }

  .deployment-history-toggle:hover {
    color: #171717;
    text-decoration: underline;
  }

  .deployment-history-heading {
    margin: 0.5rem 0 0.35rem;
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #737373;
  }

  .deployment-history-list {
    list-style: none;
    margin: 0;
    padding: 0;
    border: 1px solid #E5E5E5;
    border-radius: 0.375rem;
    background: #FAFAFA;
    overflow: hidden;
  }

  .deployment-history-item {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto;
    gap: 0.5rem 0.75rem;
    align-items: center;
    padding: 0.5rem 0.625rem;
    font-size: 0.75rem;
    border-bottom: 1px solid #E5E5E5;
  }

  .deployment-history-item:last-child {
    border-bottom: none;
  }

  .deployment-history-link {
    font-family: ui-monospace, monospace;
    color: #2563EB;
    text-decoration: none;
    word-break: break-all;
  }

  .deployment-history-link:hover {
    text-decoration: underline;
  }

  .deployment-history-status {
    font-weight: 500;
    color: #525252;
    white-space: nowrap;
  }

  .deployment-history-date {
    color: #737373;
    white-space: nowrap;
    font-size: 0.6875rem;
  }

  .deployment-id-link {
    color: inherit;
    text-decoration: underline;
    text-underline-offset: 2px;
  }

  .deployment-id-link:hover {
    color: #2563EB;
  }

  .empty-hint {
    font-size: 0.875rem;
    color: #737373;
    margin: 0.75rem auto 0;
    max-width: 22rem;
    line-height: 1.4;
  }

  /* Responsive */
  @media (max-width: 768px) {
    .dashboard-page {
      padding: 1rem;
    }

    .dashboard-header h1 {
      font-size: 1.5rem;
    }

    .balance-value {
      font-size: 2.5rem;
    }

    .tab-content {
      padding: 1rem;
    }

    .topup-section {
      padding: 1rem;
    }

    .usage-summary {
      grid-template-columns: 1fr;
    }
  }
</style>
