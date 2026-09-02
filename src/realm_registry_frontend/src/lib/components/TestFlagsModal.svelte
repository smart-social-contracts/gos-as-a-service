<script>
  import { createEventDispatcher } from 'svelte';
  import { backend } from '$lib/canisters.js';
  import {
    registryRuntimeFlags,
    getRegistryRuntimeFlagsSnapshot
  } from '$lib/stores/registryRuntimeFlags.js';
  import { authSession } from '$lib/stores/authSession.js';
  import {
    getTestIdentityIndex,
    switchTestIdentity
  } from '$lib/auth.js';
  import {
    listTestIdentities,
    shortPrincipal,
    getTestIdentityPersona,
    identityNumberToIndex,
    isValidCustomIdentityNumber,
    testIdentityNumber,
    TEST_IDENTITY_FIXED_PICKER_MAX_INDEX,
    TEST_IDENTITY_MAX_INDEX,
  } from '$lib/test-identities.js';
  import { isCardBillingDisabled } from '$lib/card-billing-flag.js';
  import { isAssistantExperimentalNoticeEnabled } from '$lib/assistant-experimental-flag.js';

  export let open = false;

  const dispatch = createEventDispatcher();

  const FLAGS = [
    { key: 'test_mode', store: 'testMode', label: 'Test mode', hint: 'Master switch — turning this off hides this editor and locks flags to controllers' },
    { key: 'ii_bypass', store: 'testModeIIBypass', label: 'II bypass', hint: 'Skip Internet Identity and sign in with deterministic test identities' },
    { key: 'user_self_registration', store: 'testModeUserSelfRegistration', label: 'User self-registration', hint: 'Allow users to join without an invitation code' },
    { key: 'demo_data', store: 'testModeDemoData', label: 'Demo data', hint: 'Auto-activate the demo data simulator' },
    { key: 'skip_terms', store: 'testModeSkipTerms', label: 'Skip terms', hint: 'Skip the terms & conditions step on join' },
    { key: 'skip_passport_zkproof', store: 'testModeSkipPassportZkproof', label: 'Skip passport ZK-proof', hint: 'Bypass passport zero-knowledge verification' },
    { key: 'disable_card_billing', store: 'testModeDisableCardBilling', label: 'Disable card billing', hint: 'Keep Top Up Credits visible; Pay with Card cannot charge (Currently not available)' },
    { key: 'assistant_experimental_notice', store: 'testModeAssistantExperimentalNotice', label: 'Assistant experimental notice', hint: 'Keep the assistant available; show the unofficial / not legal-advice line in chrome' }
  ];

  let values = {};
  let saving = false;
  let error = '';
  let message = '';
  let testIdentities = listTestIdentities();
  let selectedTestIdentityIndex = 0;
  let customIdentityNumber = 3;
  let switchingIdentity = false;
  let identityError = '';

  $: customIdentityIndex = isValidCustomIdentityNumber(customIdentityNumber)
    ? identityNumberToIndex(customIdentityNumber)
    : null;
  $: customPersona = customIdentityIndex != null ? getTestIdentityPersona(customIdentityIndex) : null;
  $: maxCustomIdentityNumber = testIdentityNumber(TEST_IDENTITY_MAX_INDEX);

  $: showIdentityPicker = !!values.ii_bypass;
  $: currentPrincipalText = $authSession.principal?.toText?.() || '';
  $: activeIdentityIndex = $authSession.identityIndex;
  $: if (open) syncFromStore();

  async function syncFromStore() {
    const snapshot = getRegistryRuntimeFlagsSnapshot();
    const next = {};
    for (const f of FLAGS) {
      if (f.key === 'disable_card_billing') {
        next[f.key] = isCardBillingDisabled({
          disableCardBilling: snapshot.testModeDisableCardBilling,
          network: snapshot.network,
        });
      } else if (f.key === 'assistant_experimental_notice') {
        next[f.key] = isAssistantExperimentalNoticeEnabled({
          assistantExperimentalNotice: snapshot.testModeAssistantExperimentalNotice,
          network: snapshot.network,
        });
      } else {
        next[f.key] = !!snapshot[f.store];
      }
    }
    values = next;
    error = '';
    message = '';
    identityError = '';
    testIdentities = listTestIdentities();
    selectedTestIdentityIndex = getTestIdentityIndex();
    if (selectedTestIdentityIndex > TEST_IDENTITY_FIXED_PICKER_MAX_INDEX) {
      customIdentityNumber = testIdentityNumber(selectedTestIdentityIndex);
    } else {
      customIdentityNumber = 3;
    }
  }

  async function selectIdentity(index) {
    selectedTestIdentityIndex = index;
    const persona = getTestIdentityPersona(index);
    if (
      persona &&
      currentPrincipalText &&
      persona.loginPrincipal === currentPrincipalText
    ) {
      identityError = '';
      return;
    }
    await applyIdentitySwitch(index);
  }

  async function selectCustomIdentity() {
    if (!isValidCustomIdentityNumber(customIdentityNumber)) {
      identityError = `Enter an identity number from 3 to ${maxCustomIdentityNumber.toLocaleString()}.`;
      return;
    }
    await selectIdentity(identityNumberToIndex(customIdentityNumber));
  }

  function handleCustomInputKeydown(event) {
    event.stopPropagation();
    if (event.key === 'Enter') {
      event.preventDefault();
      selectCustomIdentity();
    }
  }

  function handleCustomInputClick(event) {
    event.stopPropagation();
  }

  async function applyIdentitySwitch(index = selectedTestIdentityIndex) {
    if (switchingIdentity) return;
    switchingIdentity = true;
    identityError = '';

    try {
      const result = await switchTestIdentity(index);
      if (!result?.principal) {
        throw new Error('Failed to switch test identity.');
      }

      dispatch('identitychange', {
        index,
        principal: result.principal
      });
    } catch (e) {
      identityError = e instanceof Error ? e.message : String(e);
    } finally {
      switchingIdentity = false;
    }
  }

  function close() {
    if (saving || switchingIdentity) return;
    open = false;
  }

  async function save() {
    saving = true;
    error = '';
    message = '';
    try {
      const raw = await backend.set_test_flags_json(JSON.stringify({ test_flags: values }));
      const result = typeof raw === 'string' ? JSON.parse(raw) : raw;
      if (!result?.success) {
        throw new Error(result?.error || 'Failed to update test flags');
      }
      await registryRuntimeFlags.fetch();
      message = 'Test flags updated';
      if (!values.test_mode) open = false;
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    } finally {
      saving = false;
    }
  }

  function handleWindowKeydown(event) {
    if (!open || saving || switchingIdentity) return;
    if (event.key === 'Escape') close();
  }
</script>

<svelte:window on:keydown={handleWindowKeydown} />

{#if open}
  <div class="overlay-wrap">
    <button type="button" class="backdrop" aria-label="Close" on:click={close}></button>
    <div
      class="dialog"
      class:dialog-wide={showIdentityPicker}
      role="dialog"
      aria-modal="true"
      tabindex="-1"
      aria-labelledby="test-flags-modal-title"
    >
      <h2 id="test-flags-modal-title" class="title">Test flags</h2>
      <p class="subtitle">
        This registry runs in test mode. Anyone can view and change these runtime flags while
        test mode is enabled.
      </p>
      <p class="warning">
        WARNING: turning off &quot;Test mode&quot; hides this editor and locks further flag
        changes to canister controllers.
      </p>

      <div class="flags">
        {#each FLAGS as flag}
          <label class="flag-row">
            <span class="flag-text">
              <span class="flag-label">{flag.label}</span>
              <span class="flag-hint">{flag.hint}</span>
            </span>
            <input type="checkbox" bind:checked={values[flag.key]} disabled={saving || switchingIdentity} />
          </label>
        {/each}
      </div>

      {#if showIdentityPicker}
        <section class="identity-section" aria-labelledby="test-identity-picker-title">
          <h3 id="test-identity-picker-title" class="identity-title">Test identity</h3>
          <p class="identity-subtitle">
            Click an identity to sign in immediately. The header updates as soon as you switch.
          </p>
          {#if currentPrincipalText}
            <p class="identity-current">
              Signed in as <code>{shortPrincipal(currentPrincipalText)}</code>
            </p>
          {/if}

          <div class="identity-list">
            {#each testIdentities as persona (persona.index)}
              <button
                type="button"
                class="identity-option"
                class:selected={activeIdentityIndex === persona.index}
                class:active={currentPrincipalText && persona.loginPrincipal === currentPrincipalText}
                disabled={saving || switchingIdentity}
                on:click={() => selectIdentity(persona.index)}
              >
                <span class="identity-option-head">
                  <span class="identity-option-label">{persona.label}</span>
                  {#if activeIdentityIndex === persona.index}
                    <span class="identity-badge active-badge">Active</span>
                  {:else if switchingIdentity && selectedTestIdentityIndex === persona.index}
                    <span class="identity-badge">Switching…</span>
                  {/if}
                </span>
                <span class="identity-option-principal">{shortPrincipal(persona.principal)}</span>
                <span class="identity-option-hint">{persona.description}</span>
              </button>
            {/each}

            <button
              type="button"
              class="identity-option identity-option-custom"
              class:selected={customIdentityIndex != null && activeIdentityIndex === customIdentityIndex}
              class:active={customPersona && currentPrincipalText && customPersona.loginPrincipal === currentPrincipalText}
              class:invalid={customIdentityIndex == null}
              disabled={saving || switchingIdentity}
              on:click={selectCustomIdentity}
            >
              <span class="identity-option-head">
                <span class="identity-custom-head">
                  <span class="identity-option-label">Identity</span>
                  <input
                    id="custom-identity-number"
                    class="identity-custom-input"
                    type="number"
                    min="3"
                    max={maxCustomIdentityNumber}
                    step="1"
                    inputmode="numeric"
                    placeholder="3"
                    bind:value={customIdentityNumber}
                    disabled={saving || switchingIdentity}
                    on:click={handleCustomInputClick}
                    on:keydown={handleCustomInputKeydown}
                    aria-label="Identity number"
                  />
                </span>
                {#if customIdentityIndex != null && activeIdentityIndex === customIdentityIndex}
                  <span class="identity-badge active-badge">Active</span>
                {:else if switchingIdentity && customIdentityIndex != null && selectedTestIdentityIndex === customIdentityIndex}
                  <span class="identity-badge">Switching…</span>
                {/if}
              </span>
              {#if customPersona}
                <span class="identity-option-principal">{shortPrincipal(customPersona.principal)}</span>
                <span class="identity-option-hint">{customPersona.description}</span>
              {:else}
                <span class="identity-option-hint">
                  Click to sign in · numbers 3–{maxCustomIdentityNumber.toLocaleString()}
                </span>
              {/if}
            </button>
          </div>

          {#if identityError}
            <p class="feedback error">{identityError}</p>
          {/if}
        </section>
      {/if}

      {#if error}
        <p class="feedback error">{error}</p>
      {/if}
      {#if message}
        <p class="feedback success">{message}</p>
      {/if}

      <div class="actions">
        <button type="button" class="btn btn-cancel" disabled={saving || switchingIdentity} on:click={close}>
          Close
        </button>
        <button type="button" class="btn btn-confirm" disabled={saving || switchingIdentity} on:click={save}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>
    </div>
  </div>
{/if}

<style>
  .overlay-wrap {
    position: fixed;
    inset: 0;
    z-index: 2000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1rem;
  }

  .backdrop {
    position: absolute;
    inset: 0;
    border: none;
    padding: 0;
    margin: 0;
    background: rgba(0, 0, 0, 0.45);
    backdrop-filter: blur(2px);
    cursor: default;
  }

  .dialog {
    position: relative;
    z-index: 1;
    width: 100%;
    max-width: 460px;
    max-height: min(90vh, 860px);
    overflow: auto;
    background: #fff;
    border-radius: 0.875rem;
    padding: 1.5rem;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.25);
  }

  .dialog-wide {
    max-width: 520px;
  }

  .title {
    margin: 0 0 0.25rem;
    font-size: 1.125rem;
    font-weight: 700;
    color: #171717;
  }

  .subtitle {
    margin: 0 0 1rem;
    font-size: 0.8125rem;
    line-height: 1.45;
    color: #737373;
  }

  .warning {
    margin: 0 0 1rem;
    padding: 0.5rem 0.75rem;
    border: 1px solid #fecaca;
    border-radius: 0.5rem;
    background: #fef2f2;
    color: #b91c1c;
    font-size: 0.75rem;
    font-weight: 600;
    line-height: 1.4;
  }

  .flags {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-bottom: 1rem;
  }

  .flag-row {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 1rem;
    cursor: pointer;
  }

  .flag-text {
    display: flex;
    flex-direction: column;
    gap: 0.125rem;
  }

  .flag-label {
    font-size: 0.875rem;
    font-weight: 600;
    color: #171717;
  }

  .flag-hint {
    font-size: 0.75rem;
    line-height: 1.4;
    color: #737373;
  }

  .flag-row input[type='checkbox'] {
    margin-top: 0.2rem;
    width: 1.05rem;
    height: 1.05rem;
    accent-color: #171717;
    flex-shrink: 0;
  }

  .identity-section {
    margin-bottom: 1rem;
    padding-top: 0.25rem;
    border-top: 1px solid #e5e5e5;
  }

  .identity-title {
    margin: 0.75rem 0 0.25rem;
    font-size: 0.9375rem;
    font-weight: 700;
    color: #171717;
  }

  .identity-subtitle,
  .identity-current {
    margin: 0 0 0.75rem;
    font-size: 0.75rem;
    line-height: 1.45;
    color: #737373;
  }

  .identity-current code {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.6875rem;
    color: #404040;
  }

  .identity-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 0.75rem;
  }

  .identity-option {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    gap: 0.2rem;
    width: 100%;
    padding: 0.75rem;
    border: 1px solid #e5e5e5;
    border-radius: 0.625rem;
    background: #fff;
    text-align: left;
    cursor: pointer;
    transition: border-color 0.15s ease, background 0.15s ease;
  }

  .identity-option:hover:not(:disabled) {
    border-color: #d4d4d4;
    background: #fafafa;
  }

  .identity-option.selected {
    border-color: #171717;
    background: #fafafa;
  }

  .identity-option.active:not(.selected) {
    border-color: #15803d;
  }

  .identity-option:disabled {
    opacity: 0.65;
    cursor: not-allowed;
  }

  .identity-option-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 0.5rem;
    width: 100%;
  }

  .identity-option-label {
    font-size: 0.8125rem;
    font-weight: 600;
    color: #171717;
  }

  .identity-badge {
    font-size: 0.625rem;
    font-weight: 600;
    padding: 0.125rem 0.375rem;
    border-radius: 999px;
    background: #e5e5e5;
    color: #404040;
    flex-shrink: 0;
  }

  .active-badge {
    background: #dcfce7;
    color: #166534;
  }

  .identity-option-principal {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    font-size: 0.6875rem;
    line-height: 1.35;
    color: #525252;
    word-break: break-all;
  }

  .identity-option-hint {
    font-size: 0.6875rem;
    line-height: 1.35;
    color: #a3a3a3;
  }

  .identity-option-custom.invalid {
    cursor: default;
  }

  .identity-option-custom.invalid:hover:not(:disabled) {
    border-color: #e5e5e5;
    background: #fff;
  }

  .identity-custom-head {
    display: flex;
    align-items: center;
    gap: 0.375rem;
    min-width: 0;
  }

  .identity-custom-input {
    width: 4.75rem;
    min-width: 4.75rem;
    padding: 0.2rem 0.375rem;
    border: 1px solid #d4d4d4;
    border-radius: 0.375rem;
    font-size: 0.8125rem;
    font-weight: 600;
    color: #171717;
    text-align: center;
    background: #fff;
    cursor: text;
  }

  .identity-custom-input:focus {
    outline: none;
    border-color: #171717;
  }

  .identity-custom-input:disabled {
    opacity: 0.65;
    cursor: not-allowed;
  }

  .feedback {
    margin: 0 0 0.75rem;
    font-size: 0.8125rem;
  }

  .feedback.error {
    color: #b91c1c;
  }

  .feedback.success {
    color: #15803d;
  }

  .actions {
    display: flex;
    justify-content: flex-end;
    gap: 0.5rem;
  }

  .btn {
    padding: 0.5rem 1rem;
    border-radius: 0.5rem;
    font-size: 0.875rem;
    font-weight: 600;
    cursor: pointer;
    border: 1px solid transparent;
  }

  .btn:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .btn-cancel {
    background: #fff;
    color: #171717;
    border-color: #d4d4d4;
  }

  .btn-cancel:hover:not(:disabled) {
    background: #fafafa;
  }

  .btn-confirm {
    background: #171717;
    color: #fff;
  }

  .btn-confirm:hover:not(:disabled) {
    filter: brightness(1.05);
  }
</style>
