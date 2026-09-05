<script>
  import { createEventDispatcher } from 'svelte';
  import { HOST_SPLASH_MARK_PATH } from '$lib/realm-utils.js';

  /** Realms GOS host orb — portal chrome while a realm iframe is preparing. */
  export let size = 128;
  /** Optional realm branding logo; falls back to the host orb on error or while loading. */
  export let logoUrl = '';

  const dispatch = createEventDispatcher();

  let realmLoaded = false;
  let realmFailed = false;
  let activeLogoUrl = '';

  $: if (logoUrl !== activeLogoUrl) {
    activeLogoUrl = logoUrl;
    realmLoaded = false;
    realmFailed = false;
  }

  $: showRealmLogo = !!activeLogoUrl && !realmFailed && realmLoaded;
  $: showFallback = !activeLogoUrl || realmFailed || !realmLoaded;

  function handleRealmLoad() {
    realmLoaded = true;
    dispatch('realmLogoLoad');
  }

  function handleRealmError() {
    realmFailed = true;
  }
</script>

<div class="sphere-stage" style="--sphere-size: {size}px" aria-hidden="true">
  <span class="sphere-halo"></span>
  {#if activeLogoUrl && !realmFailed}
    <img
      src={activeLogoUrl}
      alt=""
      class="sphere-mark sphere-mark--realm"
      class:sphere-mark--visible={showRealmLogo}
      width={size}
      height={size}
      on:load={handleRealmLoad}
      on:error={handleRealmError}
    />
  {/if}
  {#if showFallback}
    <img
      src={HOST_SPLASH_MARK_PATH}
      alt=""
      class="sphere-mark sphere-mark--fallback"
      width={size}
      height={Math.round(size * (448 / 398))}
    />
  {/if}
</div>

<style>
  .sphere-stage {
    position: relative;
    width: var(--sphere-size, 128px);
    height: var(--sphere-size, 128px);
    display: grid;
    place-items: center;
  }

  .sphere-halo {
    position: absolute;
    inset: -22%;
    border-radius: 50%;
    background: radial-gradient(
      circle,
      rgba(115, 115, 115, 0.16) 0%,
      rgba(115, 115, 115, 0.05) 46%,
      transparent 72%
    );
    animation: sphere-glow 2.2s ease-in-out infinite;
  }

  .sphere-mark {
    position: relative;
    display: block;
    grid-area: 1 / 1;
  }

  .sphere-mark--fallback {
    width: calc(var(--sphere-size, 128px) * 0.86);
    height: auto;
    /* Black SVG → mid-gray (#737373). */
    filter: brightness(0) invert(0.45) drop-shadow(0 8px 18px rgba(115, 115, 115, 0.28));
    animation: sphere-breathe-fallback 2.2s ease-in-out infinite;
  }

  .sphere-mark--realm {
    width: calc(var(--sphere-size, 128px) * 0.86);
    height: calc(var(--sphere-size, 128px) * 0.86);
    object-fit: contain;
    opacity: 0;
    filter: drop-shadow(0 8px 18px rgba(115, 115, 115, 0.28));
    animation: sphere-breathe-realm 2.2s ease-in-out infinite;
  }

  .sphere-mark--realm.sphere-mark--visible {
    opacity: 1;
  }

  @keyframes sphere-breathe-fallback {
    0%,
    100% {
      opacity: 0.78;
      transform: scale(0.96);
      filter: brightness(0) invert(0.45) drop-shadow(0 4px 10px rgba(115, 115, 115, 0.18));
    }
    50% {
      opacity: 1;
      transform: scale(1.04);
      filter: brightness(0) invert(0.45) drop-shadow(0 12px 24px rgba(115, 115, 115, 0.32));
    }
  }

  @keyframes sphere-breathe-realm {
    0%,
    100% {
      transform: scale(0.96);
      filter: drop-shadow(0 4px 10px rgba(115, 115, 115, 0.18));
    }
    50% {
      transform: scale(1.04);
      filter: drop-shadow(0 12px 24px rgba(115, 115, 115, 0.32));
    }
  }

  @keyframes sphere-glow {
    0%,
    100% {
      opacity: 0.5;
      transform: scale(0.94);
    }
    50% {
      opacity: 1;
      transform: scale(1.08);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .sphere-mark--fallback,
    .sphere-mark--realm,
    .sphere-halo {
      animation: none;
    }

    .sphere-mark--fallback {
      opacity: 0.92;
      transform: none;
      filter: brightness(0) invert(0.45) drop-shadow(0 6px 14px rgba(115, 115, 115, 0.22));
    }

    .sphere-mark--realm.sphere-mark--visible {
      opacity: 1;
      transform: none;
      filter: drop-shadow(0 6px 14px rgba(115, 115, 115, 0.22));
    }
  }
</style>
