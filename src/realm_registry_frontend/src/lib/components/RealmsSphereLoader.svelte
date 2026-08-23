<script>
  /** Realms GOS sphere mark — used only while a realm iframe is preparing. */
  export let size = 72;
</script>

<img
  src="/images/logo_sphere_only.svg"
  alt=""
  class="sphere-mark"
  width={size}
  height={Math.round(size * (448 / 398))}
  style="--sphere-size: {size}px"
  aria-hidden="true"
/>

<style>
  .sphere-mark {
    display: block;
    width: var(--sphere-size, 72px);
    height: auto;
    opacity: 0.38;
    filter: brightness(0) invert(0.68)
      drop-shadow(0 0 8px rgba(163, 163, 163, 0.28));
    animation: sphere-pulse 2.4s ease-in-out infinite;
  }

  @keyframes sphere-pulse {
    0%,
    100% {
      opacity: 0.28;
      filter: brightness(0) invert(0.64)
        drop-shadow(0 0 5px rgba(163, 163, 163, 0.16));
    }
    50% {
      opacity: 0.72;
      filter: brightness(0) invert(0.76)
        drop-shadow(0 0 16px rgba(180, 180, 180, 0.5));
    }
  }

  @media (prefers-reduced-motion: reduce) {
    .sphere-mark {
      animation: none;
      opacity: 0.5;
      filter: brightness(0) invert(0.7)
        drop-shadow(0 0 8px rgba(163, 163, 163, 0.22));
    }
  }
</style>
