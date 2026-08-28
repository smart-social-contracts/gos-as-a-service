<script>
  import { onDestroy } from 'svelte';
  import { browser } from '$app/environment';
  import { withLiveProgressTiming } from '$lib/deployment-progress.js';
  import { getObservedStageStarts } from '$lib/deployment-stage-timing.js';

  /** @type {import('$lib/deployment-progress.js').getDeploymentProgress extends (j: infer J) => infer R ? R : never} */
  export let progress;
  /** @type {'full' | 'compact'} */
  export let variant = 'full';
  /** @type {boolean} */
  export let showSteps = true;
  /** Job id — enables live stage timers from session observations. */
  export let jobId = '';
  /** Updated every second while active; bind from parent for meta rows. */
  export let liveTotalDurationLabel = '';

  /** User toggled extension list visibility; null = follow auto rules. */
  let extensionsExpandedOverride = null;

  function toggleExtensionsExpanded() {
    extensionsExpandedOverride = !extensionsExpanded;
  }

  let nowMs = Date.now();
  /** @type {ReturnType<typeof setInterval>|null} */
  let clockTimer = null;

  $: observedStarts = browser && jobId
    ? getObservedStageStarts(jobId, progress?.startedAtMs ?? null)
    : null;
  $: displayProgress = progress?.isActive
    ? withLiveProgressTiming(progress, nowMs, observedStarts)
    : progress;
  $: liveTotalDurationLabel = displayProgress?.totalDurationLabel || '';

  $: extensionsStage = displayProgress?.stages?.find((stage) => stage.id === 'extensions');
  $: hasExtensionSteps = (displayProgress?.extensionInstallGroups?.length || 0) > 0;
  $: extensionsStageActive = extensionsStage?.state === 'active';
  $: extensionsStageVisible =
    extensionsStage?.state === 'active' ||
    extensionsStage?.state === 'done' ||
    displayProgress?.isFailed;
  $: extensionsExpanded =
    extensionsExpandedOverride != null
      ? extensionsExpandedOverride
      : extensionsStageActive || displayProgress?.isFailed;

  function startClock() {
    stopClock();
    if (!browser || !progress?.isActive) return;
    nowMs = Date.now();
    clockTimer = setInterval(() => {
      nowMs = Date.now();
    }, 1000);
  }

  function stopClock() {
    if (clockTimer) {
      clearInterval(clockTimer);
      clockTimer = null;
    }
  }

  $: if (browser) {
    if (progress?.isActive) {
      if (!clockTimer) startClock();
    } else {
      stopClock();
    }
  }

  onDestroy(stopClock);
</script>

<div class="deployment-progress" class:compact={variant === 'compact'}>
  <div class="progress-header">
    <div class="progress-label-row">
      <span
        class="progress-label"
        class:failed={displayProgress.isFailed}
        class:blocked={displayProgress.isBlocked && !displayProgress.isFailed}
        class:retrying={displayProgress.isAutoRetrying}
      >{displayProgress.currentLabel}</span>
      <span class="progress-percent" aria-hidden="true">{displayProgress.percent}%</span>
    </div>
    <div
      class="progress-track"
      class:active={displayProgress.isActive && !displayProgress.isFailed}
      role="progressbar"
      aria-valuenow={displayProgress.percent}
      aria-valuemin="0"
      aria-valuemax="100"
      aria-label="Deployment progress"
    >
      <div
        class="progress-fill"
        class:failed={displayProgress.isFailed}
        class:complete={displayProgress.isComplete}
        class:active={displayProgress.isActive && !displayProgress.isFailed && !displayProgress.isComplete}
        style="width: {displayProgress.percent}%"
      ></div>
    </div>
    <p class="progress-description">{displayProgress.currentDescription}</p>
  </div>

  {#if displayProgress.error && displayProgress.error !== displayProgress.currentDescription}
    <div class="progress-error" role="alert">
      {#if displayProgress.isFailed}
        <strong>Deployment failed</strong>
      {:else if displayProgress.isBlocked}
        <strong>Blocked — retrying cannot fix this</strong>
      {/if}
      <p>{displayProgress.error}</p>
    </div>
  {/if}

  {#if showSteps && variant === 'full'}
    <ol class="progress-steps">
      {#each displayProgress.stages as stage, i}
        {#if stage.id !== 'complete' || displayProgress.isComplete}
          <li class="progress-step" class:done={stage.state === 'done'} class:active={stage.state === 'active'} class:failed={stage.state === 'failed'}>
            <span class="step-marker" aria-hidden="true">
              {#if stage.state === 'done'}
                ✓
              {:else if stage.state === 'failed'}
                ✕
              {:else if stage.state === 'active'}
                …
              {:else}
                {i + 1}
              {/if}
            </span>
            {#if stage.id === 'extensions' && hasExtensionSteps && extensionsStageVisible}
              <button
                type="button"
                class="step-toggle"
                aria-expanded={extensionsExpanded}
                aria-controls="extension-install-steps"
                on:click={toggleExtensionsExpanded}
              >
                <span class="step-label">{stage.label}</span>
                {#if displayProgress.extensionTotal > 0}
                  <span class="step-detail">
                    {displayProgress.extensionCompleted}/{displayProgress.extensionTotal}
                  </span>
                {/if}
                <span class="step-chevron" class:expanded={extensionsExpanded} aria-hidden="true">▸</span>
              </button>
            {:else}
              <span class="step-label">{stage.label}</span>
              {#if stage.id === 'extensions' && stage.state === 'active' && displayProgress.extensionTotal > 0}
                <span class="step-detail">{displayProgress.extensionCompleted}/{displayProgress.extensionTotal}</span>
              {/if}
            {/if}
            {#if stage.durationLabel && stage.state !== 'upcoming'}
              <span
                class="step-duration"
                class:estimated={stage.durationEstimated}
                class:ticking={stage.state === 'active'}
                title={stage.durationEstimated ? 'Estimated stage duration' : 'Stage duration'}
              >
                {stage.durationLabel}{#if stage.durationEstimated}~{/if}
              </span>
            {:else if stage.state === 'active'}
              <span class="step-duration active ticking">&lt;1s</span>
            {/if}
          </li>
          {#if stage.id === 'provision' && displayProgress.provisionSubSteps?.length && (stage.state === 'active' || stage.state === 'done')}
            <li class="sub-steps-wrap" aria-label="Canister provisioning steps">
              <ol class="sub-steps">
                {#each displayProgress.provisionSubSteps as subStep}
                  <li class="sub-step" class:done={subStep.state === 'done'} class:active={subStep.state === 'active'}>
                    <span class="sub-marker" aria-hidden="true">
                      {#if subStep.state === 'done'}
                        ✓
                      {:else if subStep.state === 'active'}
                        …
                      {:else}
                        ·
                      {/if}
                    </span>
                    <span class="sub-label">
                      {subStep.label}{#if subStep.detail} ({subStep.detail}){/if}
                    </span>
                  </li>
                {/each}
              </ol>
            </li>
          {/if}
          {#if stage.id === 'extensions' && hasExtensionSteps && extensionsStageVisible && extensionsExpanded}
            <li class="sub-steps-wrap" id="extension-install-steps" aria-label="Extension install steps">
              {#each displayProgress.extensionInstallGroups as group (group.id)}
                <div class="install-group">
                  {#if displayProgress.extensionInstallGroups.length > 1}
                    <div class="install-group-header">
                      <span class="install-group-label">{group.label}</span>
                      <span class="install-group-count">{group.completed}/{group.total}</span>
                    </div>
                  {/if}
                  <ol class="sub-steps">
                    {#each group.steps as subStep (subStep.id)}
                      <li
                        class="sub-step"
                        class:done={subStep.state === 'done'}
                        class:active={subStep.state === 'active'}
                        class:failed={subStep.state === 'failed'}
                      >
                        <span class="sub-marker" aria-hidden="true">
                          {#if subStep.state === 'done'}
                            ✓
                          {:else if subStep.state === 'failed'}
                            ✕
                          {:else if subStep.state === 'active'}
                            …
                          {:else}
                            ·
                          {/if}
                        </span>
                        <span class="sub-label">{subStep.label}</span>
                        <span
                          class="sub-status"
                          class:done={subStep.state === 'done'}
                          class:active={subStep.state === 'active'}
                          class:failed={subStep.state === 'failed'}
                        >
                          {subStep.statusLabel}
                        </span>
                        {#if subStep.state === 'failed' && subStep.error}
                          <span class="sub-error" title={subStep.error}>failed</span>
                        {/if}
                      </li>
                    {/each}
                  </ol>
                </div>
              {/each}
            </li>
          {/if}
        {/if}
      {/each}
    </ol>
  {/if}

  {#if displayProgress.backendCanisterId || displayProgress.frontendCanisterId}
    <div class="canister-ids subtle">
      {#if displayProgress.backendCanisterId}
        <span>Backend: {displayProgress.backendCanisterId}</span>
      {/if}
      {#if displayProgress.frontendCanisterId}
        <span>Frontend: {displayProgress.frontendCanisterId}</span>
      {/if}
    </div>
  {/if}
</div>

<style>
  .deployment-progress {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }

  .deployment-progress.compact {
    gap: 0.5rem;
  }

  .progress-header {
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .progress-label-row {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    gap: 0.5rem;
  }

  .progress-label {
    font-weight: 600;
    font-size: 0.875rem;
    color: #171717;
  }

  .progress-label.failed {
    color: #b91c1c;
  }

  .progress-label.retrying {
    color: #b45309;
  }

  .progress-label.blocked {
    color: #b91c1c;
  }

  .progress-percent {
    font-size: 0.75rem;
    font-weight: 600;
    color: #525252;
    font-variant-numeric: tabular-nums;
  }

  .progress-track {
    height: 0.5rem;
    background: #e5e5e5;
    border-radius: 999px;
    overflow: hidden;
    position: relative;
  }

  .progress-track.active::after {
    content: '';
    position: absolute;
    inset: 0;
    background: linear-gradient(
      90deg,
      transparent 0%,
      rgba(255, 255, 255, 0.45) 50%,
      transparent 100%
    );
    background-size: 200% 100%;
    animation: progress-shimmer 2s linear infinite;
    pointer-events: none;
  }

  .progress-fill {
    height: 100%;
    background: linear-gradient(90deg, #3b82f6, #2563eb);
    border-radius: 999px;
    transition: width 0.6s ease;
    position: relative;
    z-index: 1;
  }

  .progress-fill.active {
    animation: progress-breathe 2.4s ease-in-out infinite;
  }

  .progress-fill.complete {
    background: linear-gradient(90deg, #22c55e, #16a34a);
  }

  .progress-fill.failed {
    background: linear-gradient(90deg, #ef4444, #dc2626);
  }

  .progress-description {
    margin: 0;
    font-size: 0.8125rem;
    color: #525252;
    line-height: 1.4;
  }

  .progress-error {
    padding: 0.625rem 0.75rem;
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 0.5rem;
    font-size: 0.8125rem;
    color: #991b1b;
  }

  .progress-error strong {
    display: block;
    margin-bottom: 0.25rem;
  }

  .progress-error p {
    margin: 0;
    word-break: break-word;
  }

  .progress-steps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.375rem;
  }

  .compact .progress-steps {
    display: none;
  }

  .progress-step {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-size: 0.8125rem;
    color: #a3a3a3;
  }

  .step-label {
    flex: 1;
    min-width: 0;
  }

  .step-toggle {
    flex: 1;
    min-width: 0;
    display: flex;
    align-items: center;
    gap: 0.375rem;
    padding: 0;
    border: none;
    background: none;
    font: inherit;
    color: inherit;
    text-align: left;
    cursor: pointer;
  }

  .step-toggle:hover .step-chevron {
    color: #171717;
  }

  .step-chevron {
    margin-left: auto;
    font-size: 0.75rem;
    color: #737373;
    transition: transform 0.15s ease;
    flex-shrink: 0;
  }

  .step-chevron.expanded {
    transform: rotate(90deg);
  }

  .install-group + .install-group {
    margin-top: 0.5rem;
  }

  .install-group-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    margin: 0 0 0.25rem 0.625rem;
    font-size: 0.6875rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    color: #737373;
  }

  .install-group-count {
    font-variant-numeric: tabular-nums;
    color: #525252;
  }

  .install-group-label {
    min-width: 0;
  }

  .step-detail {
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: #2563eb;
    flex-shrink: 0;
  }

  .sub-steps-wrap {
    list-style: none;
    margin: 0 0 0.25rem 1.75rem;
    padding: 0;
  }

  .sub-steps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.25rem;
    border-left: 2px solid #e5e5e5;
    padding-left: 0.625rem;
  }

  .sub-step {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    font-size: 0.75rem;
    color: #a3a3a3;
  }

  .sub-step.done {
    color: #16a34a;
  }

  .sub-step.active {
    color: #2563eb;
    font-weight: 600;
  }

  .sub-step.failed {
    color: #dc2626;
  }

  .sub-marker {
    width: 0.875rem;
    text-align: center;
    flex-shrink: 0;
  }

  .sub-label {
    flex: 1;
    min-width: 0;
    word-break: break-word;
  }

  .sub-status {
    margin-left: auto;
    font-size: 0.6875rem;
    font-weight: 600;
    color: #a3a3a3;
    white-space: nowrap;
    flex-shrink: 0;
  }

  .sub-status.done {
    color: #16a34a;
  }

  .sub-status.active {
    color: #2563eb;
  }

  .sub-status.failed {
    color: #dc2626;
  }

  .sub-error {
    font-size: 0.6875rem;
    color: #b91c1c;
    flex-shrink: 0;
  }

  .step-duration {
    margin-left: auto;
    font-size: 0.75rem;
    font-variant-numeric: tabular-nums;
    color: #737373;
    flex-shrink: 0;
  }

  .step-duration.estimated {
    color: #a3a3a3;
  }

  .step-duration.active,
  .step-duration.ticking {
    color: #2563eb;
  }

  .progress-step.done .step-duration {
    color: #15803d;
  }

  .progress-step.failed .step-duration {
    color: #b91c1c;
  }

  .progress-step.done {
    color: #16a34a;
  }

  .progress-step.active {
    color: #2563eb;
    font-weight: 600;
  }

  .progress-step.failed {
    color: #dc2626;
    font-weight: 600;
  }

  .step-marker {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.25rem;
    height: 1.25rem;
    border-radius: 999px;
    background: #f5f5f5;
    font-size: 0.6875rem;
    flex-shrink: 0;
  }

  .progress-step.active .step-marker {
    background: #dbeafe;
  }

  .progress-step.done .step-marker {
    background: #dcfce7;
  }

  .progress-step.failed .step-marker {
    background: #fee2e2;
  }

  .canister-ids {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    font-size: 0.6875rem;
    color: #737373;
    word-break: break-all;
  }

  .subtle {
    opacity: 0.9;
  }

  @keyframes progress-shimmer {
    from {
      background-position: 200% 0;
    }
    to {
      background-position: -200% 0;
    }
  }

  @keyframes progress-breathe {
    0%,
    100% {
      filter: brightness(1);
    }
    50% {
      filter: brightness(1.08);
    }
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }

  .spinner {
    width: 0.75rem;
    height: 0.75rem;
    border: 2px solid #2563eb;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
</style>
