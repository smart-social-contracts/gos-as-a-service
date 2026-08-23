<script>
  /** Realms GOS sphere mark — used only while a realm iframe is preparing. */
  export let size = 128;
</script>

<div class="sphere-stage" style="--sphere-size: {size}px" aria-hidden="true">
  <span class="sphere-halo"></span>
  <span class="sphere-ring"></span>
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
      rgba(23, 23, 23, 0.14) 0%,
      rgba(23, 23, 23, 0.05) 46%,
      transparent 72%
    );
    animation: sphere-glow 2.2s ease-in-out infinite;
  }

  .sphere-ring {
    position: absolute;
    inset: -8%;
    border-radius: 50%;
    border: 1.5px solid transparent;
    border-top-color: rgba(23, 23, 23, 0.55);
    border-right-color: rgba(23, 23, 23, 0.12);
    animation: sphere-orbit 1.6s linear infinite;
  }

  .sphere-mark {
    position: relative;
    display: block;
    width: calc(var(--sphere-size, 128px) * 0.86);
    height: auto;
    opacity: 0.95;
    filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.2));
    animation: sphere-breathe 2.2s ease-in-out infinite;
  }

  @keyframes sphere-orbit {
    to {
      transform: rotate(360deg);
    }
  }

  @keyframes sphere-breathe {
    0%,
    100% {
      opacity: 0.82;
      transform: scale(0.96);
      filter: drop-shadow(0 4px 10px rgba(0, 0, 0, 0.14));
    }
    50% {
      opacity: 1;
      transform: scale(1.04);
      filter: drop-shadow(0 12px 24px rgba(0, 0, 0, 0.24));
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
    .sphere-halo,
    .sphere-ring {
      animation: none;
    }

    .sphere-mark {
      opacity: 0.96;
      transform: none;
      filter: drop-shadow(0 6px 14px rgba(0, 0, 0, 0.16));
    }

    .sphere-ring {
      border-top-color: rgba(23, 23, 23, 0.35);
    }
  }
</style>
