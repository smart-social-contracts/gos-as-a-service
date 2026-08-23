<script>
  /** Realms GOS sphere mark — used only while a realm iframe is preparing. */
  export let size = 128;
</script>

<div class="sphere-stage" style="--sphere-size: {size}px" aria-hidden="true">
  <span class="sphere-halo"></span>
  <img
    src="/images/logo_sphere_only.svg"
    alt=""
    class="sphere-mark"
    width={size}
    height={Math.round(size * (448 / 398))}
  />
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
    width: calc(var(--sphere-size, 128px) * 0.86);
    height: auto;
    /* Black SVG → mid-gray (#737373). */
    filter: brightness(0) invert(0.45) drop-shadow(0 8px 18px rgba(115, 115, 115, 0.28));
    animation: sphere-breathe 2.2s ease-in-out infinite;
  }

  @keyframes sphere-breathe {
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
    .sphere-mark,
    .sphere-halo {
      animation: none;
    }

    .sphere-mark {
      opacity: 0.92;
      transform: none;
      filter: brightness(0) invert(0.45) drop-shadow(0 6px 14px rgba(115, 115, 115, 0.22));
    }
  }
</style>
