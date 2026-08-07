<script>
  import { createEventDispatcher } from 'svelte';

  export let open = false;
  export let title = 'Confirm';
  export let message = '';
  export let confirmLabel = 'Confirm';
  export let cancelLabel = 'Cancel';
  /** @type {'default' | 'danger'} */
  export let variant = 'default';
  export let loading = false;

  const dispatch = createEventDispatcher();

  function cancel() {
    if (loading) return;
    open = false;
    dispatch('cancel');
  }

  function confirm() {
    if (loading) return;
    dispatch('confirm');
  }

  function handleWindowKeydown(event) {
    if (!open || loading) return;
    if (event.key === 'Escape') cancel();
  }
</script>

<svelte:window on:keydown={handleWindowKeydown} />

{#if open}
  <div class="overlay-wrap">
    <button type="button" class="backdrop" aria-label="Cancel" on:click={cancel}></button>
    <div
      class="dialog"
      role="alertdialog"
      aria-modal="true"
      tabindex="-1"
      aria-labelledby="confirm-modal-title"
      aria-describedby="confirm-modal-message"
    >
      <h2 id="confirm-modal-title" class="title">{title}</h2>
      <p id="confirm-modal-message" class="message">{message}</p>
      <div class="actions">
        <button type="button" class="btn btn-cancel" disabled={loading} on:click={cancel}>
          {cancelLabel}
        </button>
        <button
          type="button"
          class="btn btn-confirm"
          class:danger={variant === 'danger'}
          disabled={loading}
          on:click={confirm}
        >
          {loading ? 'Please wait…' : confirmLabel}
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
    animation: fadeIn 0.15s ease-out;
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
    max-width: 420px;
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

  .message {
    margin: 0 0 1.25rem;
    font-size: 0.9375rem;
    line-height: 1.5;
    color: #525252;
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

  .btn-confirm.danger {
    background: #b91c1c;
  }

  .btn-confirm:hover:not(:disabled) {
    filter: brightness(1.05);
  }

  @keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
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
</style>
