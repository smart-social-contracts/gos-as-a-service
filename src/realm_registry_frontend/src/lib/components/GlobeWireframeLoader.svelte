<script>
  import { HOST_SPLASH_MARK_PATH } from '$lib/realm-utils.js';

  /** Platform logo while the MapLibre globe or realm data loads. */
  export let label = '';
  /** Mark diameter in px */
  export let size = 56;
</script>

<div class="globe-loader" style="--globe-size: {size}px" role="status" aria-live="polite">
  <div class="mark-stage">
    <span class="mark-glow" aria-hidden="true"></span>
    <img class="mark" src={HOST_SPLASH_MARK_PATH} alt="" width={size} height={size} />
  </div>
  {#if label}
    <span class="globe-loader-label">{label}</span>
  {/if}
</div>

<style>
  .globe-loader {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.875rem;
    color: var(--text-faint, #a3a3a3);
  }

  .mark-stage {
    position: relative;
    width: var(--globe-size);
    height: var(--globe-size);
    display: grid;
    place-items: center;
  }

  .mark-glow {
    position: absolute;
    inset: -28%;
    border-radius: 50%;
    background: radial-gradient(
      circle,
      rgba(115, 115, 115, 0.22) 0%,
      rgba(163, 163, 163, 0.08) 38%,
      transparent 68%
    );
    animation: logo-glow 2.4s ease-in-out infinite;
  }

  .mark {
    position: relative;
    z-index: 1;
    width: var(--globe-size);
    height: var(--globe-size);
    object-fit: contain;
  }

  .globe-loader-label {
    font-size: 0.75rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--text-faint, #a3a3a3);
  }

  @keyframes logo-glow {
    0%,
    100% {
      transform: scale(0.92);
      opacity: 0.55;
    }
    50% {
      transform: scale(1.08);
      opacity: 1;
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .mark-glow {
      animation: none;
      opacity: 0.7;
      transform: none;
    }
  }
</style>
