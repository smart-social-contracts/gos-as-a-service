<script>
  import { onMount, onDestroy } from 'svelte';
  import { browser } from '$app/environment';
  import { page } from '$app/stores';
  import { _, locale } from 'svelte-i18n';
  import { CONFIG } from '$lib/config.js';
  import { buildRealmDeploymentManifest, slugify } from '$lib/deployment-manifest.js';
  import AuthControls from '$lib/components/AuthControls.svelte';
  import {
    GOS_IMPLEMENTATIONS,
    getGosImplementation,
    shouldShowVersionPicker,
    soleDeployVersionOption,
    visibleWizardSteps,
  } from '$lib/gos-implementations.js';
  import SubnetPicker from '$lib/components/SubnetPicker.svelte';
  import { getAuthenticatedRegistryActor } from '$lib/canisters.js';
  import { deploymentJobUrl } from '$lib/deployment-url.js';
  import { friendlyNetworkError, retryOnTransientNetworkError } from '$lib/network-retry.js';
  import {
    findRecentDeploymentJob,
    isAmbiguousDeploymentRequestError,
  } from '$lib/installer-queue.js';
  import {
    openDeployProgress,
    setDeployProgressStep,
    failDeployProgress,
    closeDeployProgress,
  } from '$lib/stores/deployProgress.js';

  // Auth state
  let isLoggedIn = false;
  let userPrincipal = null;
  let authLoading = true;
  let userCredits = 0;
  const REQUIRED_CREDITS = 5;

  // Invitation code gate
  let invitationMode = false;
  let principalActivated = false;
  let invitationCode = '';
  let invitationError = null;
  let invitationLoading = false;
  let checkingActivation = true;

  // Deploy mode
  let deployMode = 'automatic'; // 'automatic' or 'manual'
  
  // Automatic deployment state
  let isDeploying = false;
  let deployError = null;

  // Wizard draft persistence
  let draftId = null;
  let draftSaving = false;
  let draftSaveError = null;
  let draftInitialized = false;
  let draftLockedForDeploy = false;
  let saveDraftTimer = null;

  // Deploy version options (semver catalog + main)
  let deployVersionOptions = [{ value: 'main', label: 'main (latest from file registry)' }];
  let loadingDeployVersions = true;

  let subnetOptions = [];
  let loadingSubnets = false;
  let subnetLoadError = null;
  let subnetsFetched = false;

  async function loadSubnetOptions() {
    loadingSubnets = true;
    subnetLoadError = null;
    try {
      const { listSubnets } = await import('$lib/casals-client.js');
      subnetOptions = await listSubnets();
      subnetsFetched = true;
    } catch (e) {
      const raw = e?.message || '';
      subnetLoadError =
        /process is not defined/i.test(raw) || /canister ID is not set/i.test(raw)
          ? 'Could not load available subnets'
          : raw || 'Could not load subnets';
    } finally {
      loadingSubnets = false;
    }
  }

  function selectSubnetChoice(choice) {
    formData.subnet_choice = choice;
    if (choice !== 'other') {
      formData.subnet_id = '';
      subnetLoadError = null;
      return;
    }
    if (!subnetsFetched && !loadingSubnets) {
      void loadSubnetOptions();
    }
  }

  function subnetSummaryLabel() {
    if (formData.subnet_choice === 'european') return 'European';
    if (formData.subnet_choice === 'other') return formData.subnet_id || '—';
    return 'Automatic';
  }

  function ensureSubnetOptionsForChoice() {
    if (formData.subnet_choice === 'other' && !subnetsFetched && !loadingSubnets) {
      void loadSubnetOptions();
    }
  }

  async function initWizardDraft() {
    if (!isLoggedIn || !userPrincipal) return;
    try {
      const { loadWizardDraft, saveWizardDraft, fetchDeployVersionOptions } = await import(
        '$lib/wizard-drafts.js'
      );
      loadingDeployVersions = true;
      deployVersionOptions = await fetchDeployVersionOptions();
      loadingDeployVersions = false;

      const urlDraft = $page.url.searchParams.get('draft');
      const urlStep = $page.url.searchParams.get('step');
      const editingAfterFailure = $page.url.searchParams.get('edit') === '1';
      if (urlDraft) {
        const loaded = await loadWizardDraft(urlDraft);
        if (loaded) {
          draftId = loaded.id;
          formData = { ...formData, ...loaded.formData };
          if (loaded.deployVersion) formData.deploy_version = loaded.deployVersion;
          if (urlStep != null && urlStep !== '') {
            const stepNum = parseInt(urlStep, 10);
            if (Number.isFinite(stepNum)) {
              const maxStep = visibleWizardSteps(formData.gos_implementation).length - 1;
              currentStep = Math.min(Math.max(stepNum, 0), maxStep);
            }
          } else {
            const maxStep = visibleWizardSteps(formData.gos_implementation).length - 1;
            currentStep = Math.min(Math.max(loaded.currentStep || 0, 0), maxStep);
          }
          if (editingAfterFailure && draftId) {
            const { clearDraftDeploymentLink } = await import('$lib/wizard-drafts.js');
            await clearDraftDeploymentLink({
              id: draftId,
              formData,
              currentStep,
              deployVersion: formData.deploy_version,
            });
          }
          draftInitialized = true;
          return;
        }
      }

      const result = await saveWizardDraft({
        formData,
        currentStep,
        deployVersion: formData.deploy_version,
      });
      if (result?.success && result.id) {
        draftId = result.id;
        const url = new URL(window.location.href);
        url.searchParams.set('draft', draftId);
        window.history.replaceState({}, '', url.pathname + url.search);
      }
      draftInitialized = true;
    } catch (e) {
      console.warn('Wizard draft init skipped:', e?.message || e);
      draftInitialized = true;
      loadingDeployVersions = false;
    }
  }

  async function persistDraft() {
    if (!draftInitialized || !isLoggedIn || !userPrincipal || draftLockedForDeploy) return;
    draftSaving = true;
    draftSaveError = null;
    try {
      const { saveWizardDraft } = await import('$lib/wizard-drafts.js');
      const result = await saveWizardDraft({
        id: draftId,
        formData,
        currentStep,
        deployVersion: formData.deploy_version,
      });
      if (result?.success && result.id) {
        draftId = result.id;
      } else if (result?.error) {
        draftSaveError = result.error;
      }
    } catch (e) {
      draftSaveError = e?.message || 'Failed to save draft';
    } finally {
      draftSaving = false;
    }
  }

  function scheduleDraftSave() {
    if (!browser || !draftInitialized) return;
    if (saveDraftTimer) clearTimeout(saveDraftTimer);
    saveDraftTimer = setTimeout(() => {
      persistDraft();
    }, 800);
  }

  onMount(async () => {
    if (browser) {
      try {
        const { isAuthenticated, getPrincipal, ensureTestAuth } = await import("$lib/auth.js");
        const { getTestModeIIBypass } = await import("$lib/config.js");
        if (getTestModeIIBypass()) {
          const result = await ensureTestAuth();
          if (result.principal) {
            isLoggedIn = true;
            userPrincipal = result.principal;
            await loadUserCredits();
          }
        } else {
          isLoggedIn = await isAuthenticated();
          if (isLoggedIn) {
            userPrincipal = await getPrincipal();
            await loadUserCredits();
          }
        }
      } catch (e) {
        console.error('Auth check failed:', e);
      }
      authLoading = false;

      // Check invitation code mode (staging/test bypasses the platform gate)
      try {
        const { backend } = await import('$lib/canisters.js');
        const { getTestModeIIBypass } = await import('$lib/config.js');
        const modeResult = await backend.get_invitation_mode();
        invitationMode = modeResult?.Ok === 'enabled' && !getTestModeIIBypass();
        if (invitationMode && isLoggedIn && userPrincipal) {
          const actResult = await backend.is_principal_activated(userPrincipal.toText());
          principalActivated = actResult?.Ok === 'activated' || actResult?.Ok === 'open';
        } else if (!invitationMode) {
          principalActivated = true;
        }
      } catch (e) {
        console.error('Invitation mode check failed:', e);
        principalActivated = true;
      }
      checkingActivation = false;

      if (isLoggedIn && userPrincipal) {
        await initWizardDraft();
      } else {
        draftInitialized = true;
        loadingDeployVersions = false;
      }
    }
  });

  async function loadUserCredits() {
    if (!userPrincipal) return;
    try {
      const { fetchUserCreditBalance } = await import('$lib/user-credits.js');
      userCredits = await fetchUserCreditBalance(userPrincipal.toText());
    } catch (e) {
      console.error('Failed to load credits:', e);
    }
  }

  async function handleLogin() {
    const { login, getPrincipal } = await import("$lib/auth");
    const result = await login();
    if (result.principal) {
      isLoggedIn = true;
      userPrincipal = result.principal;
      await loadUserCredits();
      if (!draftInitialized) await initWizardDraft();
    }
  }

  async function handleLogout() {
    const { logout } = await import("$lib/auth");
    await logout();
    isLoggedIn = false;
    userPrincipal = null;
    userCredits = 0;
  }

  async function handleRedeemCode() {
    if (!invitationCode.trim() || !userPrincipal) return;
    invitationError = null;
    invitationLoading = true;
    try {
      const { getAuthenticatedRegistryActor } = await import('$lib/canisters.js');
      const registry = await getAuthenticatedRegistryActor();
      const result = await registry.redeem_invitation_code(invitationCode.trim());
      if (result?.Ok) {
        principalActivated = true;
      } else {
        invitationError = result?.Err || 'Invalid invitation code';
      }
    } catch (e) {
      invitationError = e.message || 'Failed to redeem invitation code';
    } finally {
      invitationLoading = false;
    }
  }

  function closeDeployModal() {
    closeDeployProgress();
    isDeploying = false;
    draftLockedForDeploy = false;
  }

  function failAutomaticDeploy(message) {
    const text = message || 'Deployment failed. Please check your connection and try again.';
    deployError = text;
    isDeploying = false;
    draftLockedForDeploy = false;
    failDeployProgress(text);
  }

  /** Reject if `promise` does not settle within `ms` milliseconds. */
  function withTimeout(promise, ms, message) {
    let timer;
    const timeout = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(message)), ms);
    });
    return Promise.race([promise, timeout]).finally(() => clearTimeout(timer));
  }

  /** @param {'prepare' | 'submit' | 'redirect'} step */
  function setDeployStep(step) {
    setDeployProgressStep(step);
  }

  function onDeployClick() {
    void handleAutomaticDeploy().catch((err) => {
      console.error('Deploy handler rejected:', err);
      failAutomaticDeploy(err?.message || 'Deployment failed');
    });
  }

  async function handleAutomaticDeploy() {
    if (!userPrincipal || userCredits < REQUIRED_CREDITS) return;

    isDeploying = true;
    draftLockedForDeploy = true;
    deployError = null;

    try {
      openDeployProgress();
      setDeployStep('prepare');

      setDeployStep('submit');
      const manifest = await buildRealmDeploymentManifest(
        formData,
        CONFIG.default_deploy_queue_network,
        {
          deployVersion: formData.deploy_version,
          useCasals: true,
          founder: userPrincipal?.toText?.() || '',
        },
      );
      const manifestJson = JSON.stringify(manifest);

      const registry = await getAuthenticatedRegistryActor();
      let result;
      try {
        const raw = await withTimeout(
          retryOnTransientNetworkError(() => registry.request_deployment(manifestJson)),
          120000,
          'Deployment request timed out. Check your dashboard before retrying.',
        );
        result = typeof raw === 'string' ? JSON.parse(raw) : raw;
      } catch (deployErr) {
        if (isAmbiguousDeploymentRequestError(deployErr)) {
          const recovered = await findRecentDeploymentJob({
            callerPrincipal: userPrincipal.toText(),
            realmName: formData.name,
          });
          if (recovered?.job_id) {
            result = { success: true, job_id: recovered.job_id };
          } else {
            throw deployErr;
          }
        } else {
          throw deployErr;
        }
      }

      if (!result?.success) {
        failAutomaticDeploy(result?.error || 'Deployment request failed');
        return;
      }

      setDeployStep('redirect');
      draftLockedForDeploy = true;
      if (draftId) {
        try {
          const { markDraftLinkedToJob } = await import('$lib/wizard-drafts.js');
          await markDraftLinkedToJob({
            id: draftId,
            formData,
            currentStep,
            deployVersion: formData.deploy_version,
            jobId: result.job_id,
          });
        } catch (_) { /* non-fatal */ }
      }
      // Hard navigation avoids SPA teardown races with the progress overlay.
      window.location.assign(deploymentJobUrl(result.job_id));
      return;
    } catch (err) {
      console.error('Automatic deployment failed:', err);
      failAutomaticDeploy(friendlyNetworkError(err));
    }
  }

  // Wizard steps — filtered by GOS implementation (see visibleSteps).
  // Extensions and initial data are codex-driven (issue #242).
  $: visibleSteps = visibleWizardSteps(formData.gos_implementation);
  $: currentStepId = visibleSteps[currentStep]?.id ?? 'platform';
  $: if (currentStep >= visibleSteps.length) {
    currentStep = Math.max(0, visibleSteps.length - 1);
  }
  $: if (currentStepId === 'subnet') {
    ensureSubnetOptionsForChoice();
  }
  $: soleDeployVersion = soleDeployVersionOption(deployVersionOptions);
  $: if (soleDeployVersion && formData.deploy_version !== soleDeployVersion.value) {
    formData.deploy_version = soleDeployVersion.value;
  }

  function selectGosImplementation(id) {
    const impl = getGosImplementation(id);
    if (!impl?.available) return;
    formData.gos_implementation = id;
  }

  // Form data — platform-only; codex/token/branding configured in-realm post-deploy.
  let formData = {
    gos_implementation: 'realms-gos',
    name: '',
    slug: '',
    deploy_version: CONFIG.default_deploy_version || 'main',
    subnet_choice: 'automatic',
    subnet_id: '',
  };

  let slugTouched = false;

  $: if (formData.name && !slugTouched) {
    formData.slug = slugify(formData.name);
  }

  $: portalPreviewPath = formData.slug ? `/r/${slugify(formData.slug)}` : '';

  onDestroy(() => {
    closeDeployProgress();
    isDeploying = false;
    draftLockedForDeploy = false;
  });
  let isSubmitting = false;
  let submitError = null;

  let currentStep = 0;

  $: if (draftInitialized && browser && !draftLockedForDeploy) {
    void formData;
    void currentStep;
    scheduleDraftSave();
  }

  // Validation
  let errors = {};

  function validateStep(step) {
    errors = {};
    const stepId = visibleSteps[step]?.id;

    if (stepId === 'platform') {
      if (!formData.gos_implementation?.trim()) {
        errors.gos_implementation = 'Please select a platform';
      } else {
        const impl = getGosImplementation(formData.gos_implementation);
        if (impl && !impl.available) {
          errors.gos_implementation = 'This platform is not yet available';
        }
      }
      if (loadingDeployVersions) {
        errors.deploy_version = 'Loading available versions…';
      } else if (!formData.deploy_version?.trim()) {
        errors.deploy_version = 'Please select a software version';
      } else if (
        deployVersionOptions.length > 0 &&
        !deployVersionOptions.some((opt) => opt.value === formData.deploy_version)
      ) {
        errors.deploy_version = 'Please select a valid software version';
      }
    }

    // Basics
    if (stepId === 'basics') {
      if (!formData.name.trim()) {
        errors.name = 'Realm name is required';
      } else if (formData.name.length < 3) {
        errors.name = 'Name must be at least 3 characters';
      }
      const slug = slugify((formData.slug || formData.name || '').trim());
      if (!slug) {
        errors.slug = 'URL slug is required';
      } else if (slug.length < 3) {
        errors.slug = 'Slug must be at least 3 characters';
      }
    }

    if (stepId === 'subnet') {
      if (formData.subnet_choice === 'other') {
        if (loadingSubnets) {
          errors.subnet_id = 'Loading available subnets…';
        } else if (!formData.subnet_id?.trim()) {
          errors.subnet_id = 'Please select a subnet';
        }
      }
    }

    return Object.keys(errors).length === 0;
  }

  function nextStep() {
    if (validateStep(currentStep)) {
      if (currentStep < visibleSteps.length - 1) {
        currentStep++;
      }
    }
  }

  function prevStep() {
    if (currentStep > 0) {
      currentStep--;
    }
  }

  function goToStep(index) {
    // Only allow going back or to validated steps
    if (index < currentStep) {
      currentStep = index;
    }
  }

  function copyToClipboard(text) {
    if (browser) {
      navigator.clipboard.writeText(text);
    }
  }

  function generateManifest() {
    return buildRealmDeploymentManifest(formData, CONFIG.default_deploy_queue_network, {
      deployVersion: formData.deploy_version,
      useCasals: true,
      founder: userPrincipal?.toText?.() || '',
    });
  }

  async function handleSubmit() {
    if (!validateStep(currentStep)) return;
    
    isSubmitting = true;
    submitError = null;

    try {
      const manifest = await generateManifest();
      
      // For now, download the manifest as a file
      // In the future, this could directly deploy via the backend
      const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'manifest.json';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);

      // Show success (no redirect, stay on deploy page)
      // User can use the downloaded manifest with the CLI
    } catch (err) {
      submitError = err.message || 'Failed to create realm';
    } finally {
      isSubmitting = false;
    }
  }


</script>

<svelte:head>
  <title>Deploy your GOS | Realms</title>
</svelte:head>

<div class="page-shell">
  <header class="site-header">
    <a href="/" class="site-home-link">Home</a>
    <AuthControls
      {authLoading}
      {isLoggedIn}
      {userPrincipal}
      onLogin={handleLogin}
      onLogout={handleLogout}
    />
  </header>

{#if checkingActivation || authLoading}
  <div class="wizard-container">
    <div class="invitation-gate">
      <p>Loading...</p>
    </div>
  </div>
{:else if invitationMode && isLoggedIn && !principalActivated}
  <div class="wizard-container">
    <div class="invitation-gate">
      <div class="invitation-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="1.5">
          <rect x="2" y="6" width="20" height="12" rx="2"/>
          <path d="M2 8l10 6 10-6"/>
        </svg>
      </div>
      <h2>Invitation Required</h2>
      <p class="invitation-desc">Realm creation is currently available by invitation only. Enter your invitation code below to get started.</p>
      <div class="invitation-form">
        <input
          type="text"
          bind:value={invitationCode}
          placeholder="Enter your invitation code"
          class="invitation-input"
          class:error={invitationError}
          on:keydown={(e) => { if (e.key === 'Enter') handleRedeemCode(); }}
          disabled={invitationLoading}
        />
        {#if invitationError}
          <p class="invitation-error">{invitationError}</p>
        {/if}
        <button
          class="btn btn-primary invitation-submit"
          on:click={handleRedeemCode}
          disabled={invitationLoading || !invitationCode.trim()}
        >
          {invitationLoading ? 'Verifying...' : 'Submit Code'}
        </button>
      </div>
      <div class="invitation-request-info">
        <p>Don't have an invitation code?</p>
        <p class="invitation-request-channels">Request one by reaching out to us on <a href="https://oc.app/community/x2nkd-waaaa-aaaar-bhh4q-cai" target="_blank" rel="noopener">OpenChat</a>.</p>
      </div>
    </div>
  </div>
{:else if invitationMode && !isLoggedIn}
  <div class="wizard-container">
    <div class="invitation-gate">
      <div class="invitation-icon">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="#6366f1" stroke-width="1.5">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
          <circle cx="12" cy="7" r="4"/>
        </svg>
      </div>
      <h2>Sign In Required</h2>
      <p class="invitation-desc">Please sign in with Internet Identity to continue. An invitation code is required to create a realm.</p>
      <button class="btn btn-primary" on:click={handleLogin}>Sign In</button>
    </div>
  </div>
{:else}
<div class="wizard-container">
  <header class="wizard-header">
    <h1>Deploy your GOS</h1>
    <p class="subtitle">Deploy your realm on the platform — configure codex, token, and branding inside the realm afterward</p>
  </header>

  <!-- Progress Steps -->
  <div class="steps-container">
    <div class="steps">
      {#each visibleSteps as step, index}
        <button 
          class="step" 
          class:active={currentStep === index}
          class:completed={currentStep > index}
          on:click={() => goToStep(index)}
          disabled={index > currentStep}
        >
          <div class="step-number">
            {#if currentStep > index}
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                <polyline points="20 6 9 17 4 12"></polyline>
              </svg>
            {:else}
              {index + 1}
            {/if}
          </div>
          <span class="step-label">{step.label}</span>
        </button>
        {#if index < visibleSteps.length - 1}
          <div class="step-connector" class:completed={currentStep > index}></div>
        {/if}
      {/each}
    </div>
  </div>

  <!-- Navigation Buttons (at top) -->
  <div class="wizard-nav wizard-nav-top">
    {#if currentStep > 0}
      <button class="btn btn-secondary" on:click={prevStep}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        Back
      </button>
    {:else}
      <div></div>
    {/if}

    {#if currentStep < visibleSteps.length - 1}
      <button class="btn btn-primary" on:click={nextStep}>
        Continue
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12h14M12 5l7 7-7 7"/>
        </svg>
      </button>
    {:else}
      <div></div>
    {/if}
  </div>

  <!-- Form Content -->
  <div class="form-container">
    {#if currentStepId === 'basics'}
      <!-- Basics -->
      <div class="form-step">
        <h2>Basic Information</h2>
        <p class="step-description">Give your realm a unique identity</p>

        <div class="form-group">
          <label for="name">Realm Name <span class="required">*</span></label>
          <input 
            type="text" 
            id="name" 
            bind:value={formData.name}
            placeholder="e.g., Atlantis, New Eden, Arcadia"
            class:error={errors.name}
          />
          {#if errors.name}
            <span class="error-message">{errors.name}</span>
          {/if}
        </div>

        <div class="form-group">
          <label for="slug">URL Slug <span class="required">*</span></label>
          <input
            type="text"
            id="slug"
            bind:value={formData.slug}
            on:input={() => { slugTouched = true; }}
            placeholder="e.g., atlantis"
            class:error={errors.slug}
          />
          {#if portalPreviewPath}
            <p class="hint">Portal path: <code>{portalPreviewPath}</code></p>
          {/if}
          <p class="hint">Codex, token, and branding are configured inside your realm after deployment.</p>
          {#if errors.slug}
            <span class="error-message">{errors.slug}</span>
          {/if}
        </div>
      </div>

    {:else if currentStepId === 'platform'}
      <!-- Platform -->
      <div class="form-step">
        <h2>Choose Platform</h2>
        <p class="step-description">Select the Governance Operating System implementation for your realm</p>

        <div class="form-group">
          <label>GOS Implementation</label>
          <div class="codex-options">
            {#each GOS_IMPLEMENTATIONS as impl}
              {#if impl.available}
                <button
                  type="button"
                  class="codex-card"
                  class:selected={formData.gos_implementation === impl.id}
                  on:click={() => selectGosImplementation(impl.id)}
                >
                  <div class="codex-radio">
                    {#if formData.gos_implementation === impl.id}
                      <div class="codex-radio-dot"></div>
                    {/if}
                  </div>
                  <div class="codex-info">
                    <span class="codex-name">{impl.name}</span>
                    <span class="codex-tagline">{impl.tagline}</span>
                    <span class="codex-desc">{impl.description}</span>
                  </div>
                </button>
              {:else}
                <div
                  class="codex-card disabled"
                  aria-disabled="true"
                >
                  <div class="codex-radio"></div>
                  <div class="codex-info">
                    <span class="codex-name">
                      {impl.name}
                      <span class="coming-soon-badge">Coming soon</span>
                    </span>
                    <span class="codex-tagline">{impl.tagline}</span>
                    <span class="codex-desc">{impl.description}</span>
                  </div>
                </div>
              {/if}
            {/each}
          </div>
          {#if errors.gos_implementation}
            <span class="error-message">{errors.gos_implementation}</span>
          {/if}
        </div>

        <div class="deploy-version-card">
          <label for="deploy-version">Software version</label>
          {#if loadingDeployVersions}
            <p class="field-hint">Loading available versions…</p>
          {:else if shouldShowVersionPicker(deployVersionOptions)}
            <select id="deploy-version" bind:value={formData.deploy_version} class="deploy-version-select">
              {#each deployVersionOptions as opt}
                <option value={opt.value}>{opt.label}</option>
              {/each}
            </select>
          {:else if soleDeployVersion}
            <p class="deploy-version-value" id="deploy-version">{soleDeployVersion.label}</p>
          {/if}
          {#if errors.deploy_version}
            <span class="error-message">{errors.deploy_version}</span>
          {/if}
        </div>
      </div>

    {:else if currentStepId === 'subnet'}
      <!-- Subnet placement -->
      <div class="form-step">
        <h2>Subnet placement</h2>
        <p class="step-description">Choose where your realm's canisters should land</p>

        <div class="deploy-version-card">
          <span class="subnet-placement-label">Subnet placement</span>
          <p class="field-hint">Advanced — leave on Automatic unless you have data-residency requirements.</p>
          <div class="codex-options" role="group" aria-label="Subnet placement">
            <button
              type="button"
              class="codex-card"
              class:selected={formData.subnet_choice === 'automatic'}
              on:click={() => selectSubnetChoice('automatic')}
            >
              <div class="codex-radio">
                {#if formData.subnet_choice === 'automatic'}
                  <div class="codex-radio-dot"></div>
                {/if}
              </div>
              <div class="codex-info">
                <span class="codex-name">Automatic (recommended)</span>
                <span class="codex-desc">The platform picks a healthy subnet for you.</span>
              </div>
            </button>
            <button
              type="button"
              class="codex-card"
              class:selected={formData.subnet_choice === 'european'}
              on:click={() => selectSubnetChoice('european')}
            >
              <div class="codex-radio">
                {#if formData.subnet_choice === 'european'}
                  <div class="codex-radio-dot"></div>
                {/if}
              </div>
              <div class="codex-info">
                <span class="codex-name">European</span>
                <span class="codex-desc">Deploy on the European subnet. Helps with GDPR and data-residency requirements.</span>
              </div>
            </button>
            <button
              type="button"
              class="codex-card"
              class:selected={formData.subnet_choice === 'other'}
              on:click={() => selectSubnetChoice('other')}
            >
              <div class="codex-radio">
                {#if formData.subnet_choice === 'other'}
                  <div class="codex-radio-dot"></div>
                {/if}
              </div>
              <div class="codex-info">
                <span class="codex-name">Other</span>
                <span class="codex-desc">Choose a specific subnet from the list of available subnets.</span>
              </div>
            </button>
          </div>
          {#if formData.subnet_choice === 'other'}
            {#if loadingSubnets}
              <p class="field-hint">Loading available subnets…</p>
            {:else if subnetOptions.length > 0}
              <SubnetPicker bind:value={formData.subnet_id} subnetIds={subnetOptions} />
            {:else}
              <p class="field-hint">No subnets available. Leave on Automatic or try again later.</p>
            {/if}
          {/if}
          {#if formData.subnet_choice === 'other' && subnetLoadError}
            <span class="error-message">{subnetLoadError}</span>
          {/if}
          {#if errors.subnet_id}
            <span class="error-message">{errors.subnet_id}</span>
          {/if}
        </div>
      </div>

    {:else if currentStepId === 'deploy'}
      <!-- Review & Deploy -->
      <div class="form-step">
        <h2>Review & Deploy</h2>
        <p class="step-description">Confirm platform settings, then deploy your realm</p>

        <div class="codex-manifest-details review-summary">
          <div class="codex-detail-row">
            <span class="codex-detail-label">Realm</span>
            <span class="codex-detail-value"><strong>{formData.name || '—'}</strong></span>
          </div>
          <div class="codex-detail-row">
            <span class="codex-detail-label">Slug</span>
            <span class="codex-detail-value"><code>{slugify(formData.slug || formData.name || '') || '—'}</code></span>
          </div>
          {#if portalPreviewPath}
            <div class="codex-detail-row">
              <span class="codex-detail-label">Portal</span>
              <span class="codex-detail-value"><code>{portalPreviewPath}</code></span>
            </div>
          {/if}
          <div class="codex-detail-row">
            <span class="codex-detail-label">Platform</span>
            <span class="codex-detail-value">{getGosImplementation(formData.gos_implementation)?.name || formData.gos_implementation}</span>
          </div>
          <div class="codex-detail-row">
            <span class="codex-detail-label">Software version</span>
            <span class="codex-detail-value">{formData.deploy_version}</span>
          </div>
          <div class="codex-detail-row">
            <span class="codex-detail-label">Subnet</span>
            <span class="codex-detail-value">{subnetSummaryLabel()}</span>
          </div>
          <p class="codex-details-note">After deployment you will finish codex, token, and branding setup inside the realm.</p>
        </div>

        <h3 class="review-deploy-heading">Deployment</h3>
        <p class="step-description">Choose how you want to deploy your governance system</p>

        <div class="deploy-options">
          <!-- Option 1: Automatic Deployment -->
          <div 
            class="deploy-option" 
            class:active={deployMode === 'automatic'}
            class:disabled={!isLoggedIn || userCredits < REQUIRED_CREDITS}
            on:click={() => { if (isLoggedIn && userCredits >= REQUIRED_CREDITS) deployMode = 'automatic'; }}
            on:keydown={(e) => { if (e.key === 'Enter' && isLoggedIn && userCredits >= REQUIRED_CREDITS) deployMode = 'automatic'; }}
            role="button"
            tabindex="0"
          >
            <div class="deploy-option-header">
              <div class="deploy-option-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"></path>
                </svg>
              </div>
              <div>
                <h3>Automatic Deployment</h3>
                {#if !isLoggedIn}
                  <span class="badge-warning">Login Required</span>
                {:else if userCredits < REQUIRED_CREDITS}
                  <span class="badge-warning">Credits Required</span>
                {:else}
                  <span class="badge-recommended">Recommended</span>
                {/if}
              </div>
            </div>
            <p class="deploy-option-desc">Deploy via Casals on the Internet Computer — fully on-chain, no servers required.</p>
            
            {#if !isLoggedIn}
              <div class="deploy-requirement">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                  <circle cx="12" cy="7" r="4"></circle>
                </svg>
                <span>Please log in to use automatic deployment</span>
                <button type="button" class="btn btn-small btn-dark" on:click|stopPropagation={handleLogin}>
                  Log In
                </button>
              </div>
            {:else if userCredits < REQUIRED_CREDITS}
              <div class="deploy-requirement">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <path d="M12 6v6l4 2"></path>
                </svg>
                <span>You need at least {REQUIRED_CREDITS} credits (you have {userCredits})</span>
                <button type="button" class="btn btn-small btn-outline" on:click|stopPropagation={loadUserCredits}>
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 12a9 9 0 1 1-9-9c2.52 0 4.93 1 6.74 2.74L21 8"></path>
                    <path d="M21 3v5h-5"></path>
                  </svg>
                  Refresh
                </button>
                <a href="/my-dashboard" class="btn btn-small btn-dark" on:click|stopPropagation>
                  Buy Credits
                </a>
              </div>
            {:else if deployMode === 'automatic'}
              <!-- Deploy button when automatic mode is selected and user has credits -->
              <div class="deploy-action">
                  <p class="deploy-cost">Cost: <strong>{REQUIRED_CREDITS} credits</strong> (you have {userCredits})</p>
                  <button 
                    type="button" 
                    class="btn btn-primary btn-deploy" 
                    on:click|stopPropagation={onDeployClick}
                    disabled={isDeploying}
                  >
                    {#if isDeploying}
                      <span class="spinner-small"></span>
                      Deploying...
                    {:else}
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z"></path>
                      </svg>
                      Deploy Now
                    {/if}
                  </button>
                  {#if deployError}
                    <p class="deploy-error">{deployError}</p>
                  {/if}
                </div>
            {/if}
          </div>

          <!-- Option 2: Manual Deployment -->
          <div 
            class="deploy-option" 
            class:active={deployMode === 'manual'}
            on:click={() => deployMode = 'manual'}
            on:keydown={(e) => { if (e.key === 'Enter') deployMode = 'manual'; }}
            role="button"
            tabindex="0"
          >
            <div class="deploy-option-header">
              <div class="deploy-option-icon">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                  <polyline points="16 18 22 12 16 6"></polyline>
                  <polyline points="8 6 2 12 8 18"></polyline>
                </svg>
              </div>
              <div>
                <h3>Manual Deployment</h3>
                <span class="badge-developer">For Developers</span>
              </div>
            </div>
            <p class="deploy-option-desc">Deploy your own governance system in minutes using the CLI.</p>

            {#if deployMode === 'manual'}
            <div class="deploy-steps">
              <div class="deploy-step">
                <div class="deploy-step-number">1</div>
                <div class="deploy-step-content">
                  <h4>Install the CLI</h4>
                  <div class="code-block">
                    <code>pip install realms-gos</code>
                    <button type="button" class="copy-btn" on:click={() => copyToClipboard('pip install realms-gos')} aria-label="Copy command">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                      </svg>
                    </button>
                  </div>
                </div>
              </div>

              <div class="deploy-step">
                <div class="deploy-step-number">2</div>
                <div class="deploy-step-content">
                  <h4>Create and Deploy</h4>
                  <div class="code-block">
                    <code>realms realm create --deploy --network staging</code>
                    <button type="button" class="copy-btn" on:click={() => copyToClipboard('realms realm create --deploy --network staging')} aria-label="Copy command">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                        <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                      </svg>
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <a href="https://github.com/smart-social-contracts/realms" target="_blank" rel="noopener noreferrer" class="docs-link" on:click|stopPropagation>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
              </svg>
              View Documentation
            </a>

            <div class="download-config-inline">
              <div class="download-config-text">
                <strong>Download Configuration</strong>
                <span>Download your realm configuration to use with the CLI or save for later.</span>
              </div>
              <button type="button" class="btn btn-small" on:click|stopPropagation={handleSubmit} disabled={isSubmitting}>
                {#if isSubmitting}
                  <span class="spinner-small"></span>
                {:else}
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                    <polyline points="7 10 12 15 17 10"></polyline>
                    <line x1="12" y1="15" x2="12" y2="3"></line>
                  </svg>
                  Download
                {/if}
              </button>
            </div>
            {/if}
          </div>
        </div>

        {#if submitError}
          <div class="error-banner">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="12" y1="8" x2="12" y2="12"></line>
              <line x1="12" y1="16" x2="12.01" y2="16"></line>
            </svg>
            {submitError}
          </div>
        {/if}
      </div>
    {/if}
  </div>

</div>
{/if}
</div>

<style>
  .page-shell {
    min-height: 100vh;
    background: #FAFAFA;
  }

  .site-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    max-width: 1200px;
    margin: 0 auto;
    padding: 1rem 2rem 0;
  }

  .site-home-link {
    font-size: 0.9375rem;
    font-weight: 600;
    color: #171717;
    text-decoration: none;
  }

  .site-home-link:hover {
    color: #525252;
  }

  .invitation-gate {
    text-align: center;
    padding: 3rem 2rem;
    max-width: 480px;
    margin: 4rem auto;
  }

  .invitation-icon {
    margin-bottom: 1.5rem;
  }

  .invitation-gate h2 {
    font-size: 1.5rem;
    font-weight: 700;
    color: #171717;
    margin: 0 0 0.75rem;
  }

  .invitation-desc {
    color: #525252;
    font-size: 0.95rem;
    line-height: 1.6;
    margin: 0 0 2rem;
  }

  .invitation-form {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    align-items: center;
  }

  .invitation-input {
    width: 100%;
    max-width: 360px;
    padding: 0.75rem 1rem;
    font-size: 1rem;
    border: 2px solid #e5e5e5;
    border-radius: 8px;
    text-align: center;
    letter-spacing: 0.05em;
    transition: border-color 0.15s;
  }

  .invitation-input:focus {
    outline: none;
    border-color: #6366f1;
  }

  .invitation-input.error {
    border-color: #ef4444;
  }

  .invitation-input:disabled {
    opacity: 0.6;
    background: #f5f5f5;
  }

  .invitation-error {
    color: #ef4444;
    font-size: 0.875rem;
    margin: 0;
  }

  .invitation-submit {
    min-width: 160px;
  }

  .invitation-request-info {
    margin-top: 2.5rem;
    padding-top: 1.5rem;
    border-top: 1px solid #e5e5e5;
  }

  .invitation-request-info p {
    margin: 0 0 0.5rem;
    color: #737373;
    font-size: 0.875rem;
  }

  .invitation-request-channels {
    color: #525252;
  }

  .invitation-request-channels a {
    color: #6366f1;
    text-decoration: none;
    font-weight: 500;
  }

  .invitation-request-channels a:hover {
    text-decoration: underline;
  }

  .wizard-container {
    max-width: 800px;
    margin: 0 auto;
    padding: 2rem;
    min-height: 100vh;
  }

  .wizard-header {
    text-align: center;
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
    transition: color 0.15s;
  }

  .back-link:hover {
    color: #171717;
  }

  .wizard-header h1 {
    font-size: 2rem;
    font-weight: 700;
    color: #171717;
    margin: 0 0 0.5rem;
  }

  .subtitle {
    color: #737373;
    margin: 0;
  }

  /* Steps */
  .steps-container {
    margin-bottom: 2rem;
  }

  .steps {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0;
  }

  .step {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    background: none;
    border: none;
    cursor: pointer;
    padding: 0.5rem 1rem;
    transition: all 0.15s;
  }

  .step:disabled {
    cursor: not-allowed;
    opacity: 0.5;
  }

  .step-number {
    width: 36px;
    height: 36px;
    border-radius: 50%;
    background: #E5E5E5;
    color: #737373;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 600;
    font-size: 0.875rem;
    transition: all 0.15s;
  }

  .step.active .step-number {
    background: #171717;
    color: #FFFFFF;
  }

  .step.completed .step-number {
    background: #22C55E;
    color: #FFFFFF;
  }

  .step-label {
    font-size: 0.75rem;
    color: #737373;
    font-weight: 500;
  }

  .step.active .step-label {
    color: #171717;
  }

  .step-connector {
    width: 60px;
    height: 2px;
    background: #E5E5E5;
    margin: 0 -0.5rem;
    margin-bottom: 1.5rem;
  }

  .step-connector.completed {
    background: #22C55E;
  }

  /* Form */
  .form-container {
    background: #FFFFFF;
    border-radius: 1rem;
    padding: 2rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    margin-bottom: 1.5rem;
  }

  .form-step h2 {
    font-size: 1.5rem;
    font-weight: 600;
    color: #171717;
    margin: 0 0 0.25rem;
  }

  .step-description {
    color: #737373;
    font-size: 0.95rem;
    margin: 0 0 1.5rem;
  }

  .info-tooltip {
    position: relative;
    display: inline-flex;
    align-items: center;
    vertical-align: middle;
    margin-left: 0.35rem;
    cursor: help;
    color: #a3a3a3;
  }

  .info-tooltip:hover {
    color: #525252;
  }

  .info-tooltip .info-tooltip-text {
    visibility: hidden;
    opacity: 0;
    position: absolute;
    left: 50%;
    top: calc(100% + 8px);
    transform: translateX(-50%);
    background: #171717;
    color: #fff;
    font-size: 0.8rem;
    font-weight: 400;
    line-height: 1.4;
    padding: 0.6rem 0.75rem;
    border-radius: 6px;
    width: 260px;
    z-index: 10;
    pointer-events: none;
    transition: opacity 0.15s;
    white-space: normal;
  }

  .info-tooltip:hover .info-tooltip-text {
    visibility: visible;
    opacity: 1;
  }

  .form-group {
    margin-bottom: 1.25rem;
  }

  .form-group label {
    display: block;
    font-size: 0.875rem;
    font-weight: 500;
    color: #171717;
    margin-bottom: 0.5rem;
  }

  .required {
    color: #EF4444;
  }

  .form-group input[type="text"],
  .form-group input[type="number"],
  .form-group textarea {
    width: 100%;
    padding: 0.75rem 1rem;
    border: 1px solid #E5E5E5;
    border-radius: 0.5rem;
    font-size: 1rem;
    transition: all 0.15s;
    background: #FAFAFA;
  }

  .form-group input:focus,
  .form-group textarea:focus {
    outline: none;
    border-color: #171717;
    background: #FFFFFF;
  }

  .form-group input.error,
  .form-group textarea.error {
    border-color: #EF4444;
  }

  .error-message {
    color: #EF4444;
    font-size: 0.75rem;
    margin-top: 0.25rem;
    display: block;
  }

  .char-count {
    font-size: 0.75rem;
    color: #A3A3A3;
    float: right;
    margin-top: 0.25rem;
  }

  .hint {
    font-size: 0.75rem;
    color: #737373;
    margin-top: 0.25rem;
    display: block;
  }

  .form-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 1rem;
  }

  @media (max-width: 600px) {
    .form-row {
      grid-template-columns: 1fr;
    }
  }

  /* Upload Area */
  .upload-area {
    position: relative;
    border: 2px dashed #E5E5E5;
    border-radius: 0.75rem;
    padding: 1.5rem;
    text-align: center;
    transition: all 0.15s;
    min-height: 150px;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .upload-area:hover {
    border-color: #A3A3A3;
  }

  .upload-area.has-preview {
    padding: 0.5rem;
    border-style: solid;
  }

  .upload-area input[type="file"] {
    position: absolute;
    inset: 0;
    opacity: 0;
    cursor: pointer;
  }

  .btn-generate-branding {
    margin-top: 0.5rem;
    width: 100%;
    padding: 0.45rem 0.75rem;
    border: 1px dashed #d4d4d4;
    border-radius: 0.5rem;
    background: #fafafa;
    color: #404040;
    font-size: 0.8125rem;
    font-weight: 600;
    cursor: pointer;
  }

  .btn-generate-branding:hover:not(:disabled) {
    background: #f5f5f5;
    border-color: #a3a3a3;
  }

  .btn-generate-branding:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .branding-generate-hint {
    margin: 0.5rem 0 1.25rem;
    font-size: 0.8125rem;
    color: #737373;
  }

  .upload-placeholder {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.5rem;
    color: #737373;
  }

  .upload-placeholder span {
    font-size: 0.875rem;
  }

  .upload-placeholder .hint {
    font-size: 0.75rem;
    color: #A3A3A3;
  }

  .preview-image {
    max-width: 100%;
    max-height: 140px;
    border-radius: 0.5rem;
    object-fit: contain;
  }

  .welcome-upload .preview-image {
    max-height: 100px;
    width: 100%;
    object-fit: cover;
  }

  .remove-btn {
    position: absolute;
    top: 0.5rem;
    right: 0.5rem;
    background: rgba(0, 0, 0, 0.7);
    color: #FFFFFF;
    border: none;
    border-radius: 50%;
    width: 28px;
    height: 28px;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    transition: background 0.15s;
  }

  .remove-btn:hover {
    background: #EF4444;
  }

  /* Toggle */
  .toggle-label {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    cursor: pointer;
  }

  .toggle-label input[type="checkbox"] {
    position: absolute;
    opacity: 0;
    width: 0;
    height: 0;
    pointer-events: none;
  }

  .toggle-label > span:last-child {
    flex: 1;
  }

  .toggle-switch {
    width: 44px;
    min-width: 44px;
    flex-shrink: 0;
    height: 24px;
    background: #E5E5E5;
    border-radius: 12px;
    position: relative;
    transition: background 0.2s;
    display: inline-block;
  }

  .toggle-switch::after {
    content: '';
    position: absolute;
    width: 20px;
    height: 20px;
    background: #FFFFFF;
    border-radius: 50%;
    top: 2px;
    left: 2px;
    transition: transform 0.2s;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.2);
  }

  .toggle-label input:checked + .toggle-switch {
    background: #171717;
  }

  .toggle-label input:checked + .toggle-switch::after {
    transform: translateX(20px);
  }

  .divider {
    height: 1px;
    background: #E5E5E5;
    margin: 1.5rem 0;
  }

  /* Language Selection */
  .language-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .language-chip {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: #FAFAFA;
    border: 2px solid #E5E5E5;
    border-radius: 0.5rem;
    cursor: pointer;
    transition: all 0.15s;
    font-size: 0.875rem;
  }

  .language-chip:hover {
    border-color: #A3A3A3;
  }

  .language-chip.selected {
    background: #F0FDF4;
    border-color: #22C55E;
  }

  .lang-code {
    font-size: 0.75rem;
    font-weight: 700;
    background: #E5E5E5;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    color: #525252;
  }

  .language-chip.selected .lang-code {
    background: #D1FAE5;
    color: #059669;
  }

  .lang-code-small {
    font-size: 0.625rem;
    font-weight: 700;
    background: #E5E5E5;
    padding: 0.125rem 0.25rem;
    border-radius: 0.125rem;
    color: #525252;
  }

  .lang-name {
    color: #171717;
  }

  .lang-check {
    color: #22C55E;
    font-weight: 600;
    font-size: 0.75rem;
  }

  .registration-type-options {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .registration-option {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem;
    border: 2px solid #E5E5E5;
    border-radius: 0.75rem;
    background: white;
    cursor: pointer;
    transition: all 0.15s;
    text-align: left;
    width: 100%;
  }

  .registration-option:hover {
    border-color: #A3A3A3;
  }

  .registration-option.selected {
    border-color: #171717;
    background: #FAFAFA;
  }

  .registration-option-icon {
    flex-shrink: 0;
    width: 2.5rem;
    height: 2.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 0.5rem;
    background: #F5F5F5;
    color: #525252;
  }

  .registration-option.selected .registration-option-icon {
    background: #171717;
    color: white;
  }

  .registration-option-text {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .registration-option-text strong {
    font-size: 0.875rem;
    color: #171717;
  }

  .registration-option-text span {
    font-size: 0.8125rem;
    color: #737373;
  }

  /* Multi-language inputs */
  .multilang-inputs {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .multilang-input {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  .multilang-label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.875rem;
    font-weight: 500;
    color: #525252;
  }

  .multilang-label .lang-code-small {
    font-size: 0.625rem;
  }

  .token-section {
    margin-bottom: 0.5rem;
  }

  .token-config {
    background: #F5F5F5;
    border-radius: 0.75rem;
    padding: 1.25rem;
    margin-top: 1rem;
  }

  .land-token-config {
    background: #F5F5F5;
    border-radius: 0.75rem;
    padding: 1.25rem;
    margin-top: 1rem;
  }

  /* Review */
  .review-card {
    background: #FAFAFA;
    border-radius: 0.75rem;
    overflow: hidden;
  }

  .review-header {
    display: flex;
    gap: 1rem;
    padding: 1.5rem;
    align-items: flex-start;
  }

  .review-logo {
    width: 64px;
    height: 64px;
    border-radius: 0.75rem;
    object-fit: cover;
    flex-shrink: 0;
  }

  .review-logo-placeholder {
    width: 64px;
    height: 64px;
    background: #E5E5E5;
    border-radius: 0.75rem;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #A3A3A3;
    flex-shrink: 0;
  }

  .review-header h3 {
    margin: 0 0 0.25rem;
    font-size: 1.25rem;
    color: #171717;
  }

  .review-description {
    margin: 0;
    color: #737373;
    font-size: 0.875rem;
    line-height: 1.5;
  }

  .review-welcome-image {
    padding: 0 1.5rem;
  }

  .review-welcome-image img {
    width: 100%;
    height: 120px;
    object-fit: cover;
    border-radius: 0.5rem;
  }

  .review-section {
    padding: 1rem 1.5rem;
    border-top: 1px solid #E5E5E5;
  }

  .review-section h4 {
    margin: 0 0 0.5rem;
    font-size: 0.75rem;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #737373;
  }

  .review-section p {
    margin: 0;
    color: #171717;
  }

  .review-tokens {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .token-badge {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    background: #FFFFFF;
    border: 1px solid #E5E5E5;
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    min-width: 120px;
  }

  .token-badge.land {
    background: #FEF3C7;
    border-color: #F59E0B;
  }

  .token-symbol {
    font-weight: 700;
    font-size: 1rem;
    color: #171717;
  }

  .token-name {
    font-size: 0.75rem;
    color: #737373;
  }

  .token-supply {
    font-size: 0.625rem;
    color: #A3A3A3;
  }

  .error-banner {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    background: #FEF2F2;
    border: 1px solid #FECACA;
    color: #DC2626;
    padding: 1rem;
    border-radius: 0.5rem;
    margin-top: 1rem;
    font-size: 0.875rem;
  }

  /* Navigation */
  .wizard-nav {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .wizard-nav-top {
    margin-bottom: 1.5rem;
    padding-bottom: 1rem;
    border-bottom: 1px solid #E5E5E5;
  }

  .btn {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    border-radius: 0.5rem;
    font-size: 0.9375rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
    border: none;
  }

  .btn-primary {
    background: #171717;
    color: #FFFFFF;
  }

  .btn-primary:hover {
    background: #404040;
  }

  .btn-primary:disabled {
    background: #A3A3A3;
    cursor: not-allowed;
  }

  .btn-secondary {
    background: #FFFFFF;
    color: #525252;
    border: 1px solid #E5E5E5;
  }

  .btn-secondary:hover {
    border-color: #525252;
    color: #171717;
  }

  .btn-outline {
    background: #FFFFFF;
    color: #171717;
    border: 1px solid #E5E5E5;
  }

  .btn-outline:hover {
    background: #F5F5F5;
    border-color: #D4D4D4;
  }

  .btn-create {
    background: #22C55E;
  }

  .btn-create:hover {
    background: #16A34A;
  }

  .spinner {
    width: 16px;
    height: 16px;
    border: 2px solid rgba(255, 255, 255, 0.3);
    border-top-color: #FFFFFF;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  /* File upload with info */
  .file-upload.has-file {
    border-style: solid;
    border-color: #22C55E;
    background: #F0FDF4;
  }

  .file-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    padding: 0.5rem;
    width: 100%;
  }

  .file-info span {
    flex: 1;
    font-size: 0.875rem;
    color: #171717;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .remove-file-btn {
    background: none;
    border: none;
    color: #737373;
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 0.25rem;
    transition: all 0.15s;
  }

  .remove-file-btn:hover {
    color: #EF4444;
    background: #FEE2E2;
  }

  /* Source tabs for codex */
  .source-tabs {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 1rem;
  }

  .source-tab {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.25rem;
    background: #FAFAFA;
    border: 1px solid #E5E5E5;
    border-radius: 0.5rem;
    color: #525252;
    font-size: 0.875rem;
    font-weight: 500;
    cursor: pointer;
    transition: all 0.15s;
  }

  .source-tab:hover {
    border-color: #A3A3A3;
  }

  .source-tab.active {
    background: #171717;
    border-color: #171717;
    color: #FFFFFF;
  }

  /* Codex sorting */
  .codex-sort-row {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .codex-sort-label {
    font-size: 0.8125rem;
    color: #737373;
    margin-right: 0.125rem;
  }

  .codex-sort-btn {
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    padding: 0.3rem 0.6rem;
    font-size: 0.8rem;
    border: 1px solid #e5e5e5;
    border-radius: 6px;
    background: #fff;
    color: #525252;
    cursor: pointer;
    transition: all 0.15s;
  }

  .codex-sort-btn:hover {
    border-color: #a3a3a3;
    background: #fafafa;
  }

  .codex-sort-btn.active {
    background: #171717;
    color: #fff;
    border-color: #171717;
  }

  /* Codex selection */
  .codex-options {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .codex-card {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem;
    border: 2px solid #E5E5E5;
    border-radius: 0.5rem;
    background: #FFFFFF;
    cursor: pointer;
    transition: all 0.15s ease;
    text-align: left;
  }

  .codex-card:hover {
    border-color: #A3A3A3;
  }

  .codex-card.selected {
    background: #F0FDF4;
    border-color: #22C55E;
  }

  .codex-card.disabled {
    cursor: not-allowed;
    opacity: 0.65;
    background: #FAFAFA;
  }

  .codex-card.disabled:hover {
    border-color: #E5E5E5;
  }

  .codex-tagline {
    font-size: 0.8125rem;
    color: #737373;
    line-height: 1.4;
  }

  .coming-soon-badge {
    display: inline-block;
    margin-left: 0.5rem;
    padding: 0.125rem 0.5rem;
    font-size: 0.6875rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: #525252;
    background: #F5F5F5;
    border: 1px solid #E5E5E5;
    border-radius: 9999px;
    vertical-align: middle;
  }

  .codex-radio {
    width: 20px;
    height: 20px;
    min-width: 20px;
    border: 2px solid #D4D4D4;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 0.125rem;
  }

  .codex-card.selected .codex-radio {
    border-color: #22C55E;
  }

  .codex-radio-dot {
    width: 10px;
    height: 10px;
    background: #22C55E;
    border-radius: 50%;
  }

  .codex-info {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
  }

  .codex-name {
    font-weight: 600;
    color: #171717;
    font-size: 0.9375rem;
  }

  .codex-desc {
    font-size: 0.8125rem;
    line-height: 1.5;
    color: #525252;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }

  .codex-desc.expanded {
    display: block;
    -webkit-line-clamp: unset;
    overflow: visible;
  }

  .codex-expand-btn {
    background: none;
    border: none;
    padding: 0;
    font-size: 0.75rem;
    color: #2563EB;
    cursor: pointer;
    text-align: left;
    font-weight: 500;
  }

  .codex-expand-btn:hover {
    text-decoration: underline;
  }

  .doc-link {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.75rem;
    color: #2563EB;
    text-decoration: none;
    margin-top: 0.25rem;
  }

  .doc-link:hover {
    text-decoration: underline;
  }

  /* Codex manifest details panel */
  .codex-manifest-details {
    margin-top: 1.25rem;
    padding: 1.25rem;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
  }

  .codex-manifest-details h3 {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin: 0 0 1rem;
    font-size: 0.95rem;
    font-weight: 600;
    color: #171717;
  }

  .codex-version-badge {
    font-size: 0.7rem;
    font-weight: 600;
    color: #4f46e5;
    background: #eef2ff;
    padding: 0.15rem 0.5rem;
    border-radius: 999px;
  }

  .codex-detail-row {
    display: flex;
    flex-direction: column;
    gap: 0.35rem;
    margin-bottom: 0.85rem;
  }

  .codex-detail-label {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #64748b;
  }

  .codex-detail-value {
    font-size: 0.85rem;
    color: #334155;
  }

  .codex-dep-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.4rem;
  }

  .codex-dep-chip {
    font-size: 0.75rem;
    font-family: ui-monospace, monospace;
    color: #334155;
    background: #fff;
    border: 1px solid #e2e8f0;
    padding: 0.2rem 0.55rem;
    border-radius: 6px;
  }

  .codex-dep-chip.override {
    color: #92400e;
    background: #fffbeb;
    border-color: #fde68a;
  }

  .codex-details-note {
    margin: 0.5rem 0 0;
    font-size: 0.8rem;
    color: #64748b;
  }

  /* Codex parameters (issue #253) */
  .codex-params-panel {
    margin-top: 1rem;
  }

  .codex-param-group {
    margin-bottom: 1rem;
  }

  .codex-param-group input[type='number'] {
    max-width: 16rem;
  }

  .codex-param-default {
    margin-left: 0.5rem;
    font-size: 0.72rem;
    font-weight: 400;
    color: #94a3b8;
  }

  .codex-param-hint {
    margin: 0.15rem 0 0.4rem;
    font-size: 0.75rem;
  }

  /* Select all row */
  .select-all-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1.5rem;
    padding: 0.75rem 1rem;
    background: #F5F5F5;
    border-radius: 0.5rem;
  }

  .selected-count {
    font-size: 0.875rem;
    color: #525252;
  }

  /* Extension categories */
  .extension-category {
    margin-bottom: 1.5rem;
  }

  .category-title {
    font-size: 1rem;
    font-weight: 600;
    color: #171717;
    margin: 0 0 0.25rem 0;
  }

  .category-desc {
    font-size: 0.8125rem;
    color: #737373;
    margin: 0 0 0.75rem 0;
  }

  /* Extensions grid */
  .extensions-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 0.75rem;
  }

  @media (max-width: 600px) {
    .extensions-grid {
      grid-template-columns: 1fr;
    }
  }

  .extension-card {
    display: flex;
    align-items: flex-start;
    gap: 0.75rem;
    padding: 1rem;
    background: #FAFAFA;
    border: 1px solid #E5E5E5;
    border-radius: 0.5rem;
    cursor: pointer;
    transition: all 0.15s;
    text-align: left;
  }

  .extension-card:hover {
    border-color: #A3A3A3;
  }

  .extension-card.selected {
    background: #F0FDF4;
    border-color: #22C55E;
  }

  .extension-card.mandatory {
    cursor: default;
    opacity: 0.9;
  }

  .extension-card.mandatory:hover {
    border-color: #22C55E;
  }

  .mandatory-badge {
    display: inline-block;
    font-size: 0.625rem;
    font-weight: 600;
    text-transform: uppercase;
    background: #22C55E;
    color: white;
    padding: 0.125rem 0.375rem;
    border-radius: 0.25rem;
    margin-left: 0.5rem;
    vertical-align: middle;
  }

  .extension-check {
    width: 20px;
    height: 20px;
    min-width: 20px;
    border: 2px solid #D4D4D4;
    border-radius: 0.25rem;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 0.125rem;
  }

  .extension-card.selected .extension-check {
    background: #22C55E;
    border-color: #22C55E;
    color: #FFFFFF;
  }

  .extension-info {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .extension-name {
    font-weight: 500;
    color: #171717;
    font-size: 0.9375rem;
  }

  .extension-desc {
    font-size: 0.75rem;
    color: #737373;
    line-height: 1.4;
  }

  /* Custom extensions section */
  .custom-extensions-section {
    margin-top: 1rem;
  }

  .section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 1rem;
  }

  .section-header h3 {
    margin: 0;
    font-size: 1rem;
    font-weight: 600;
    color: #171717;
  }

  .btn-small {
    padding: 0.5rem 1rem;
    font-size: 0.8125rem;
    background: #FAFAFA;
    border: 1px solid #E5E5E5;
    color: #525252;
  }

  .btn-small:hover {
    border-color: #525252;
    color: #171717;
  }

  .empty-state {
    text-align: center;
    color: #A3A3A3;
    font-size: 0.875rem;
    padding: 2rem;
    background: #FAFAFA;
    border-radius: 0.5rem;
  }

  .custom-extension-row {
    display: flex;
    gap: 0.75rem;
    align-items: flex-end;
    padding: 1rem;
    background: #FAFAFA;
    border-radius: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .custom-extension-row .form-group {
    margin-bottom: 0;
  }

  .custom-extension-row .form-group label {
    font-size: 0.75rem;
    margin-bottom: 0.25rem;
  }

  .custom-extension-row input[type="text"] {
    padding: 0.5rem 0.75rem;
    font-size: 0.875rem;
  }

  .flex-grow {
    flex: 1;
  }

  .mini-tabs {
    display: flex;
  }

  .mini-tab {
    padding: 0.5rem 0.75rem;
    font-size: 0.75rem;
    background: #FFFFFF;
    border: 1px solid #E5E5E5;
    color: #525252;
    cursor: pointer;
    transition: all 0.15s;
  }

  .mini-tab:first-child {
    border-radius: 0.25rem 0 0 0.25rem;
  }

  .mini-tab:last-child {
    border-radius: 0 0.25rem 0.25rem 0;
    border-left: none;
  }

  .mini-tab.active {
    background: #171717;
    border-color: #171717;
    color: #FFFFFF;
  }

  .file-pill {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.5rem 0.75rem;
    background: #E5E5E5;
    border-radius: 0.25rem;
    font-size: 0.8125rem;
  }

  .file-pill button {
    background: none;
    border: none;
    color: #737373;
    cursor: pointer;
    font-size: 1rem;
    line-height: 1;
    padding: 0;
  }

  .file-pill button:hover {
    color: #EF4444;
  }

  .remove-ext-btn {
    background: none;
    border: none;
    color: #A3A3A3;
    cursor: pointer;
    padding: 0.5rem;
    border-radius: 0.25rem;
    transition: all 0.15s;
  }

  .remove-ext-btn:hover {
    color: #EF4444;
    background: #FEE2E2;
  }

  /* Review extensions */
  .review-extensions {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .extension-pill {
    padding: 0.375rem 0.75rem;
    background: #E5E5E5;
    border-radius: 1rem;
    font-size: 0.75rem;
    color: #525252;
  }

  .extension-pill.custom {
    background: #DBEAFE;
    color: #1D4ED8;
  }

  .review-file {
    margin-top: 0.75rem;
    font-size: 0.875rem;
  }

  .deploy-version-card {
    background: #FAFAFA;
    border: 1px solid #E5E5E5;
    border-radius: 0.75rem;
    padding: 1.25rem;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .deploy-version-card label {
    font-size: 1.125rem;
    font-weight: 600;
    color: #171717;
  }

  .subnet-placement-label {
    font-size: 1.125rem;
    font-weight: 600;
    color: #171717;
  }

  .deploy-version-select {
    width: 100%;
    padding: 0.6rem 0.75rem;
    border: 1px solid var(--border-color, #e5e7eb);
    border-radius: 8px;
    font-size: 0.95rem;
    background: var(--bg-primary, #fff);
  }

  .deploy-version-value {
    margin: 0;
    font-size: 0.95rem;
    color: #404040;
  }

  .field-hint {
    margin: 0;
    font-size: 0.875rem;
    color: #737373;
  }

  /* Deploy Step */
  .deploy-options {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .deploy-option {
    background: #FAFAFA;
    border: 1px solid #E5E5E5;
    border-radius: 0.75rem;
    padding: 1.25rem;
    transition: all 0.15s;
  }

  .deploy-option.coming-soon {
    opacity: 0.6;
  }

  .deploy-option.active {
    background: #FFFFFF;
    border-color: #171717;
  }

  .deploy-option-header {
    display: flex;
    align-items: flex-start;
    gap: 1rem;
    margin-bottom: 0.75rem;
  }

  .deploy-option-icon {
    width: 48px;
    height: 48px;
    min-width: 48px;
    background: #F5F5F5;
    border-radius: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #525252;
  }

  .deploy-option.active .deploy-option-icon {
    background: #171717;
    color: #FFFFFF;
  }

  .deploy-option-header h3 {
    margin: 0 0 0.25rem;
    font-size: 1.125rem;
    font-weight: 600;
    color: #171717;
  }

  .badge-coming-soon {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    background: #FEF3C7;
    color: #92400E;
    font-size: 0.6875rem;
    font-weight: 500;
    border-radius: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .badge-recommended {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    background: #DCFCE7;
    color: #166534;
    font-size: 0.6875rem;
    font-weight: 500;
    border-radius: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .badge-warning {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    background: #FEF3C7;
    color: #92400E;
    font-size: 0.6875rem;
    font-weight: 500;
    border-radius: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .badge-developer {
    display: inline-block;
    padding: 0.125rem 0.5rem;
    background: #E0E7FF;
    color: #3730A3;
    font-size: 0.6875rem;
    font-weight: 500;
    border-radius: 1rem;
    text-transform: uppercase;
    letter-spacing: 0.025em;
  }

  .deploy-option.disabled {
    opacity: 0.7;
    cursor: not-allowed;
  }

  .deploy-requirement {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-top: 1rem;
    padding: 0.75rem 1rem;
    background: #FEF3C7;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    color: #92400E;
  }

  .deploy-requirement span {
    flex: 1;
  }

  .btn-dark {
    background: #171717;
    color: #FFFFFF;
    border: none;
  }

  .btn-dark:hover {
    background: #404040;
  }

  button.deploy-option {
    width: 100%;
    text-align: left;
    cursor: pointer;
  }

  .deploy-option-desc {
    margin: 0;
    color: #737373;
    font-size: 0.875rem;
    line-height: 1.5;
  }

  .deploy-steps {
    margin-top: 1.5rem;
  }

  .deploy-step {
    display: flex;
    gap: 1rem;
    margin-bottom: 1.25rem;
  }

  .deploy-step:last-child {
    margin-bottom: 0;
  }

  .deploy-step-number {
    width: 28px;
    height: 28px;
    min-width: 28px;
    background: #171717;
    color: #FFFFFF;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.8125rem;
    font-weight: 600;
  }

  .deploy-step-content {
    flex: 1;
  }

  .deploy-step-content h4 {
    margin: 0 0 0.5rem;
    font-size: 0.9375rem;
    font-weight: 500;
    color: #171717;
  }

  .code-block {
    display: flex;
    align-items: center;
    background: #171717;
    border-radius: 0.5rem;
    padding: 0.75rem 1rem;
    gap: 0.75rem;
  }

  .code-block code {
    flex: 1;
    color: #FFFFFF;
    font-family: 'SF Mono', 'Fira Code', monospace;
    font-size: 0.875rem;
    white-space: nowrap;
    overflow-x: auto;
  }

  .copy-btn {
    background: none;
    border: none;
    color: #737373;
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 0.25rem;
    transition: all 0.15s;
    flex-shrink: 0;
  }

  .copy-btn:hover {
    color: #FFFFFF;
    background: rgba(255, 255, 255, 0.1);
  }

  .docs-link {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    margin-top: 1.25rem;
    color: #525252;
    text-decoration: none;
    font-size: 0.875rem;
    font-weight: 500;
    transition: color 0.15s;
  }

  .docs-link:hover {
    color: #171717;
  }

  .download-config-inline {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-top: 1.25rem;
    padding: 1rem;
    background: #F5F5F5;
    border-radius: 0.5rem;
  }

  .download-config-text {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .download-config-text strong {
    font-size: 0.875rem;
    color: #171717;
  }

  .download-config-text span {
    font-size: 0.75rem;
    color: #737373;
  }

  .spinner-small {
    width: 14px;
    height: 14px;
    border: 2px solid rgba(0, 0, 0, 0.1);
    border-top-color: #525252;
    border-radius: 50%;
    animation: spin 0.6s linear infinite;
  }

  /* Assistant Cards */
  .assistant-options {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .assistant-card {
    display: flex;
    align-items: flex-start;
    gap: 1rem;
    padding: 1.25rem;
    background: #FAFAFA;
    border: 2px solid #E5E5E5;
    border-radius: 0.75rem;
    cursor: pointer;
    transition: all 0.15s;
    text-align: left;
    width: 100%;
  }

  .assistant-card:hover {
    border-color: #A3A3A3;
  }

  .assistant-card.selected {
    background: #F0FDF4;
    border-color: #22C55E;
  }

  .assistant-check {
    width: 24px;
    height: 24px;
    min-width: 24px;
    border: 2px solid #D4D4D4;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-top: 0.25rem;
  }

  .assistant-card.selected .assistant-check {
    background: #22C55E;
    border-color: #22C55E;
    color: #FFFFFF;
  }

  .assistant-info {
    display: flex;
    gap: 1rem;
    flex: 1;
  }

  .assistant-avatar {
    font-size: 2.5rem;
    line-height: 1;
  }

  .assistant-details {
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    flex: 1;
  }

  .assistant-name {
    font-weight: 600;
    font-size: 1.125rem;
    color: #171717;
  }

  .assistant-desc {
    font-size: 0.875rem;
    color: #737373;
    line-height: 1.5;
  }

  .assistant-features {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
    margin-top: 0.5rem;
  }

  .feature-tag {
    padding: 0.25rem 0.625rem;
    background: #E5E5E5;
    border-radius: 1rem;
    font-size: 0.75rem;
    color: #525252;
  }

  .assistant-card.selected .feature-tag {
    background: #DCFCE7;
    color: #166534;
  }

  /* Inline Assistant Selection (inside Extensions) */
  .section-title {
    font-size: 1rem;
    font-weight: 600;
    color: #171717;
    margin: 0 0 0.25rem;
  }

  .section-desc {
    font-size: 0.875rem;
    color: #737373;
    margin: 0 0 1rem;
  }

  .assistant-inline-options {
    display: flex;
    gap: 0.75rem;
    flex-wrap: wrap;
  }

  .assistant-inline-card {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.625rem 1rem;
    background: #FAFAFA;
    border: 2px solid #E5E5E5;
    border-radius: 0.5rem;
    cursor: pointer;
    transition: all 0.15s;
  }

  .assistant-inline-card:hover {
    border-color: #A3A3A3;
  }

  .assistant-inline-card.selected {
    background: #F0FDF4;
    border-color: #22C55E;
  }

  .assistant-inline-check {
    width: 18px;
    height: 18px;
    min-width: 18px;
    border: 2px solid #D4D4D4;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.625rem;
    color: transparent;
  }

  .assistant-inline-card.selected .assistant-inline-check {
    background: #22C55E;
    border-color: #22C55E;
    color: #FFFFFF;
  }

  .assistant-inline-icon {
    font-size: 1.25rem;
  }

  .assistant-inline-name {
    font-weight: 500;
    color: #171717;
  }

  .assistant-selected-info {
    margin-top: 1rem;
    padding: 0.875rem;
    background: #F0FDF4;
    border: 1px solid #86EFAC;
    border-radius: 0.5rem;
  }

  .assistant-selected-info p {
    margin: 0 0 0.75rem;
    font-size: 0.8125rem;
    color: #166534;
    line-height: 1.5;
  }

  .assistant-features-inline {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem;
  }

  .feature-tag-inline {
    padding: 0.25rem 0.625rem;
    background: #DCFCE7;
    border-radius: 1rem;
    font-size: 0.6875rem;
    color: #166534;
  }

  /* Data Upload Section */
  .data-upload-section {
    display: flex;
    flex-direction: column;
    gap: 1.25rem;
  }

  .data-info-box {
    display: flex;
    gap: 1rem;
    padding: 1rem;
    background: #F0F9FF;
    border: 1px solid #BAE6FD;
    border-radius: 0.5rem;
  }

  .data-info-icon {
    width: 48px;
    height: 48px;
    min-width: 48px;
    background: #0EA5E9;
    border-radius: 0.5rem;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #FFFFFF;
  }

  .data-info-text {
    flex: 1;
  }

  .data-info-text strong {
    display: block;
    font-size: 0.9375rem;
    color: #0C4A6E;
    margin-bottom: 0.25rem;
  }

  .data-info-text p {
    margin: 0;
    font-size: 0.8125rem;
    color: #0369A1;
    line-height: 1.5;
  }

  .file-uploaded {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
    background: #F0FDF4;
    border: 1px solid #86EFAC;
    border-radius: 0.5rem;
  }

  .file-info {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: #166534;
  }

  .file-info span {
    font-weight: 500;
  }

  .remove-file-btn {
    background: none;
    border: none;
    color: #DC2626;
    cursor: pointer;
    padding: 0.25rem;
    border-radius: 0.25rem;
    transition: background 0.15s;
  }

  .remove-file-btn:hover {
    background: #FEE2E2;
  }

  .optional-note {
    margin: 0;
    font-size: 0.8125rem;
    color: #737373;
    text-align: center;
    font-style: italic;
  }

  .download-manifest-section {
    text-align: center;
    padding: 1rem 0;
  }

  .download-manifest-section h3 {
    margin: 0 0 0.25rem;
    font-size: 1rem;
    font-weight: 600;
    color: #171717;
  }

  .download-manifest-section p {
    margin: 0 0 1rem;
    color: #737373;
    font-size: 0.875rem;
  }

  /* Automatic Deployment Styles */
  .deploy-action {
    margin-top: 1rem;
    padding: 1rem;
    background: #F0FDF4;
    border: 1px solid #86EFAC;
    border-radius: 0.5rem;
    text-align: center;
  }

  .deploy-cost {
    margin: 0 0 1rem;
    color: #166534;
    font-size: 0.875rem;
  }

  .btn-deploy {
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    padding: 0.75rem 1.5rem;
    font-size: 1rem;
  }

  .deploy-error {
    margin: 1rem 0 0;
    color: #DC2626;
    font-size: 0.875rem;
  }

  .deploy-success {
    display: flex;
    align-items: center;
    gap: 1rem;
    margin-top: 1rem;
    padding: 1rem;
    background: #F0FDF4;
    border: 1px solid #86EFAC;
    border-radius: 0.5rem;
    color: #166534;
  }

  .deploy-success svg {
    color: #22C55E;
    flex-shrink: 0;
  }

  .deploy-success a {
    color: #166534;
    font-weight: 500;
    text-decoration: underline;
  }

  .deploy-success.deploy-completed {
    background: #F0FDF4;
    border-color: #86EFAC;
    color: #166534;
    flex-direction: column;
    align-items: flex-start;
  }

  .deploy-success.deploy-completed svg {
    color: #22C55E;
  }

  .deploy-success.deploy-in-progress {
    background: #FEF3C7;
    border-color: #FCD34D;
    color: #92400E;
    flex-direction: column;
    align-items: flex-start;
  }

  .deploy-success.deploy-in-progress svg {
    color: #F59E0B;
  }

  .deploy-success.deploy-in-progress svg.spinning {
    animation: spin 1s linear infinite;
  }

  .deploy-progress-panel {
    width: 100%;
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .deploy-progress-panel strong {
    font-size: 1rem;
  }

  .deploy-success .deploy-info {
    margin: 0.5rem 0;
    font-size: 0.875rem;
    opacity: 0.9;
  }

  .deploy-success .deploy-status-note {
    margin: 0.25rem 0 0;
    font-size: 0.8rem;
    opacity: 0.7;
  }

  .deploy-success .realm-url {
    display: inline-block;
    font-family: monospace;
    font-size: 0.9rem;
    padding: 0.25rem 0.5rem;
    background: rgba(0,0,0,0.05);
    border-radius: 0.25rem;
    color: inherit;
    text-decoration: none;
    word-break: break-all;
  }

  .deploy-success .realm-url:hover {
    text-decoration: underline;
  }

  .deploy-success .btn {
    margin-top: 0.5rem;
  }

  .spinner-small {
    width: 16px;
    height: 16px;
    border: 2px solid #FFFFFF;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes spin {
    to { transform: rotate(360deg); }
  }

  @media (max-width: 600px) {
    .wizard-container {
      padding: 1rem;
    }

    .form-container {
      padding: 1.25rem;
    }

    .steps {
      gap: 0;
    }

    .step {
      padding: 0.25rem 0.5rem;
    }

    .step-label {
      display: none;
    }

    .step-connector {
      width: 30px;
      margin-bottom: 0;
    }

    .source-tabs {
      flex-direction: column;
    }

    .custom-extension-row {
      flex-direction: column;
      align-items: stretch;
    }

    .remove-ext-btn {
      align-self: flex-end;
    }
  }
</style>
