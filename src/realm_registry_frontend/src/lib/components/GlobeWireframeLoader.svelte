<script>
  /** Minimal wireframe globe — used while the MapLibre globe or realm data loads. */
  export let label = '';
  /** SVG diameter in px */
  export let size = 56;
</script>

<div class="globe-loader" style="--globe-size: {size}px" role="status" aria-live="polite">
  <svg class="globe-svg" viewBox="0 0 64 64" aria-hidden="true">
    <g class="globe-spin">
      <circle cx="32" cy="32" r="28" fill="none" stroke="currentColor" stroke-width="1" class="ring outer" />
      <ellipse cx="32" cy="32" rx="28" ry="11" fill="none" stroke="currentColor" stroke-width="1" class="ring lat" />
      <ellipse cx="32" cy="32" rx="28" ry="20" fill="none" stroke="currentColor" stroke-width="1" class="ring lat faint" />
      <ellipse cx="32" cy="32" rx="11" ry="28" fill="none" stroke="currentColor" stroke-width="1" class="ring meridian" />
      <ellipse cx="32" cy="32" rx="22" ry="28" fill="none" stroke="currentColor" stroke-width="1" class="ring meridian faint" />
      <circle cx="32" cy="6" r="2.25" fill="currentColor" class="orbit-dot" />
    </g>
  </svg>
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

  .globe-svg {
    width: var(--globe-size);
    height: var(--globe-size);
    overflow: visible;
  }

  .globe-spin {
    transform-origin: 32px 32px;
    animation: globe-rotate 18s linear infinite;
  }

  .ring.outer {
    opacity: 0.35;
  }

  .ring.lat {
    opacity: 0.55;
  }

  .ring.lat.faint {
    opacity: 0.28;
  }

  .ring.meridian {
    opacity: 0.4;
  }

  .ring.meridian.faint {
    opacity: 0.22;
  }

  .orbit-dot {
    opacity: 0.7;
    filter: drop-shadow(0 0 3px rgba(115, 115, 115, 0.35));
  }

  .globe-loader-label {
    font-size: 0.75rem;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: var(--text-faint, #a3a3a3);
  }

  @keyframes globe-rotate {
    to {
      transform: rotate(360deg);
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .globe-spin {
      animation: none;
    }

    .orbit-dot {
      opacity: 0.45;
    }
  }
</style>
