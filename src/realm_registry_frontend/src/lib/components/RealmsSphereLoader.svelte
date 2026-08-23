<script>
  import { brandingLogoUrls } from '$lib/realm-utils.js';

  /** Realms GOS sphere mark — used only while a realm iframe is preparing. */
  export let size = 128;
  /** When set, the realm's branding logo is used if it actually loads. */
  export let frontendCanisterId = '';

  const DEFAULT_SRC = '/images/logo_sphere_only.svg';
  const DEFAULT_ASPECT = 448 / 398;

  let displaySrc = DEFAULT_SRC;
  let branded = false;
  let probeGen = 0;

  $: probeBranding(frontendCanisterId);

  function probeBranding(canisterId) {
    const gen = ++probeGen;
    branded = false;
    displaySrc = DEFAULT_SRC;
    const urls = brandingLogoUrls(canisterId);
    if (!urls.length || typeof Image === 'undefined') return;

    let i = 0;
    const tryNext = () => {
      if (gen !== probeGen || i >= urls.length) return;
      const url = urls[i++];
      const img = new Image();
      img.onload = () => {
        if (gen !== probeGen) return;
        displaySrc = url;
        branded = true;
      };
      img.onerror = tryNext;
      img.src = url;
    };
    tryNext();
  }
</script>

<div class="sphere-stage" class:branded style="--sphere-size: {size}px" aria-hidden="true">
  <span class="sphere-halo"></span>
  <img
    src={displaySrc}
    alt=""
    class="sphere-mark"
    class:branded
    width={size}
    height={branded ? size : Math.round(size * DEFAULT_ASPECT)}
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

  .sphere-mark.branded {
    width: calc(var(--sphere-size, 128px) * 0.9);
    height: calc(var(--sphere-size, 128px) * 0.9);
    object-fit: contain;
    filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.16));
    animation: brand-breathe 2.2s ease-in-out infinite;
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

  @keyframes brand-breathe {
    0%,
    100% {
      opacity: 0.86;
      transform: scale(0.96);
    }
    50% {
      opacity: 1;
      transform: scale(1.04);
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

    .sphere-mark.branded {
      opacity: 1;
      filter: drop-shadow(0 6px 14px rgba(0, 0, 0, 0.14));
    }
  }
</style>
