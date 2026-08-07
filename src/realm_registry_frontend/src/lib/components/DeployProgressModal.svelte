<script>
  import { createEventDispatcher } from 'svelte';

  /** @type {'prepare' | 'upload' | 'submit' | 'redirect'} */
  export let activeStep = 'prepare';
  export let open = false;
  /** @type {'running' | 'error'} */
  export let phase = 'running';
  export let uploadDetail = '';
  export let errorMessage = '';

  const dispatch = createEventDispatcher();

  const STEPS = [
    {
      id: 'prepare',
      label: 'Preparing your realm artwork',
      hint: 'Generating logo and background images when needed.',
    },
    {
      id: 'upload',
      label: 'Uploading branding to the network',
      hint: 'Publishing your images to the decentralized file registry.',
    },
    {
      id: 'submit',
      label: 'Submitting deployment request',
      hint: 'Reserving credits and queuing your realm on the Internet Computer.',
    },
    {
      id: 'redirect',
      label: 'Opening deployment tracker',
      hint: 'Next you will watch canister creation and registration live.',
    },
  ];

  const stepOrder = STEPS.map((s) => s.id);

  $: renderedSteps = STEPS.map((step, i) => ({
    ...step,
    index: i,
    state: stepState(step.id),
  }));

  /** @param {string} id */
  function stepState(id) {
    if (phase === 'error' && id === activeStep) return 'failed';
    const activeIndex = stepOrder.indexOf(activeStep);
    const index = stepOrder.indexOf(id);
    if (index < activeIndex) return 'done';
    if (index === activeIndex) return 'active';
    return 'upcoming';
  }

  function dismiss() {
    dispatch('dismiss');
  }
</script>

{#if open}
  <div class="overlay-wrap" aria-busy={phase === 'running'}>
    <div class="backdrop" aria-hidden="true"></div>
    <div
      class="dialog"
      role="dialog"
      aria-modal="true"
      aria-labelledby="deploy-progress-title"
    >
  {#if phase === 'error'}
    <h2 id="deploy-progress-title" class="title error-title">Deployment could not start</h2>
    <div class="error-box" role="alert">
      <p class="error-label">Error:</p>
      <p class="error-text">{errorMessage || 'Something went wrong. Please try again.'}</p>
    </div>
    <p class="lead">You can close this dialog and retry the deployment from the wizard.</p>
    <div class="actions">
      <button type="button" class="btn btn-primary" on:click={dismiss}>Close</button>
    </div>
  {:else}
        <h2 id="deploy-progress-title" class="title">Starting your deployment</h2>
        <p class="lead">
          This usually takes one to two minutes. Please keep this tab open — you will be
          redirected to the deployment status page automatically.
        </p>

        <ol class="steps" aria-label="Deployment preparation steps">
          {#each renderedSteps as step (step.id)}
            <li
              class="step"
              class:done={step.state === 'done'}
              class:active={step.state === 'active'}
              class:failed={step.state === 'failed'}
            >
              <span class="marker" aria-hidden="true">
                {#if step.state === 'done'}
                  ✓
                {:else if step.state === 'failed'}
                  ✕
                {:else if step.state === 'active'}
                  <span class="spinner"></span>
                {:else}
                  {step.index + 1}
                {/if}
              </span>
              <div class="step-body">
                <span class="step-label">{step.label}</span>
                {#if step.state === 'active'}
                  <span class="step-hint">{step.hint}</span>
                  {#if step.id === 'upload' && uploadDetail}
                    <span class="step-detail">{uploadDetail}</span>
                  {/if}
                {/if}
              </div>
            </li>
          {/each}
        </ol>

        <p class="next-note">
          <strong>What happens next:</strong> Casals will create your realm canisters, install
          software, and register your realm. You can follow each stage on the tracker screen.
        </p>
      {/if}
    </div>
  </div>
{/if}

<style>
  .overlay-wrap {
    position: fixed;
    inset: 0;
    z-index: 2500;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
    animation: fadeIn 0.15s ease-out;
  }

  .backdrop {
    position: absolute;
    inset: 0;
    background: rgba(0, 0, 0, 0.45);
    backdrop-filter: blur(2px);
  }

  .dialog {
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 480px;
    max-height: min(90vh, 640px);
    overflow: auto;
    background: #fff;
    border-radius: 0.875rem;
    padding: 1.5rem;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
    animation: slideUp 0.2s ease-out;
  }

  .title {
    margin: 0 0 0.5rem;
    font-size: 1.125rem;
    font-weight: 700;
    color: #171717;
  }

  .lead {
    margin: 0 0 1.25rem;
    font-size: 0.9375rem;
    line-height: 1.5;
    color: #525252;
  }

  .lead.error-text {
    color: #991b1b;
  }

  .title.error-title {
    color: #991b1b;
  }

  .error-box {
    margin: 0 0 1.25rem;
    padding: 0.875rem 1rem;
    border-radius: 0.5rem;
    background: #fef2f2;
    border: 1px solid #fecaca;
  }

  .error-label {
    margin: 0 0 0.25rem;
    font-size: 0.75rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.025em;
    color: #b91c1c;
  }

  .error-box .error-text {
    margin: 0;
    font-size: 0.875rem;
    line-height: 1.5;
    color: #7f1d1d;
    word-break: break-word;
    max-height: 200px;
    overflow-y: auto;
  }

  .steps {
    list-style: none;
    margin: 0 0 1.25rem;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 0.625rem;
  }

  .step {
    display: flex;
    align-items: flex-start;
    gap: 0.625rem;
    font-size: 0.875rem;
    color: #a3a3a3;
  }

  .step.done {
    color: #16a34a;
  }

  .step.active {
    color: #171717;
  }

  .step.failed {
    color: #dc2626;
  }

  .marker {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.375rem;
    height: 1.375rem;
    margin-top: 0.0625rem;
    border-radius: 999px;
    background: #f5f5f5;
    font-size: 0.6875rem;
    font-weight: 700;
    flex-shrink: 0;
  }

  .step.active .marker {
    background: #dbeafe;
  }

  .step.done .marker {
    background: #dcfce7;
  }

  .step.failed .marker {
    background: #fee2e2;
  }

  .step-body {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
    min-width: 0;
  }

  .step-label {
    font-weight: 600;
    line-height: 1.35;
  }

  .step-hint {
    font-size: 0.8125rem;
    color: #737373;
    line-height: 1.4;
  }

  .step-detail {
    font-size: 0.75rem;
    color: #2563eb;
    font-variant-numeric: tabular-nums;
  }

  .next-note {
    margin: 0;
    padding: 0.75rem 0.875rem;
    background: #f5f5f5;
    border-radius: 0.5rem;
    font-size: 0.8125rem;
    line-height: 1.45;
    color: #525252;
  }

  .next-note strong {
    color: #171717;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
  }

  .btn {
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    border: 1px solid transparent;
  }

  .btn-primary {
    background: #171717;
    color: #fff;
  }

  .btn-primary:hover {
    filter: brightness(1.05);
  }

  .spinner {
    width: 0.75rem;
    height: 0.75rem;
    border: 2px solid #2563eb;
    border-top-color: transparent;
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }

  @keyframes fadeIn {
    from {
      opacity: 0;
    }
    to {
      opacity: 1;
    }
  }

  @keyframes slideUp {
    from {
      opacity: 0;
      transform: translateY(12px);
    }
    to {
      opacity: 1;
      transform: translateY(0);
    }
  }

  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
</style>
