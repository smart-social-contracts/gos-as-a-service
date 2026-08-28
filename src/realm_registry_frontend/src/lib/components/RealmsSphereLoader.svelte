<script>
  import { acceptSplashLogoUrl, splashLogoCandidates } from '$lib/realm-utils.js';

  /** Pulse mark for a founder-set realm brand — never clover, GOS planet, or shipped Syntropia DNA. */
  export let size = 128;
  /** Frontend asset canister; `/custom/logo.png` is probed and hashed before paint. */
  export let frontendCanisterId = '';
  /** Realm `logo_url` from get_runtime_flags / status. */
  export let configuredLogoUrl = '';
  /**
   * True when the URL already names a realm (`/r/{slug}`).
   * Identified realms never paint the GOS planet, retired clover, or template DNA.
   */
  export let identified = false;

  // Do not paint `/custom/logo.png` until leftover hashes are checked.
  // Fresh frontends ship the Syntropia DNA there; that is not a realm brand.
  let displaySrc = '';
  let branded = false;
  let probeGen = 0;

  $: probeBranding(frontendCanisterId, configuredLogoUrl, identified);

  async function probeBranding(canisterId, configured, isIdentified) {
    const gen = ++probeGen;
    branded = false;
    displaySrc = '';
    // Slug routes identify the realm from the first paint. Do not flash
    // `/images/logo_sphere_only.svg` (or any other platform default) while
    // waiting for the configured brand.
    if (!isIdentified && !String(canisterId || '').trim()) {
      return;
    }

    const urls = splashLogoCandidates({
      frontendCanisterId: canisterId,
      configuredLogoUrl: configured,
    });
    if (!urls.length) {
      return;
    }

    for (const url of urls) {
      if (gen !== probeGen) return;
      try {
        const ok = await acceptSplashLogoUrl(url);
        if (gen !== probeGen) return;
        if (ok) {
          displaySrc = url;
          branded = true;
          return;
        }
      } catch {
        /* try the next candidate */
      }
    }
  }
</script>

{#if branded && displaySrc}
  <div class="sphere-stage branded" style="--sphere-size: {size}px" aria-hidden="true">
    <span class="sphere-halo"></span>
    <img
      src={displaySrc}
      alt=""
      class="sphere-mark branded"
      width={size}
      height={size}
    />
  </div>
{/if}

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

  .sphere-mark.branded {
    position: relative;
    display: block;
    width: calc(var(--sphere-size, 128px) * 0.9);
    height: calc(var(--sphere-size, 128px) * 0.9);
    object-fit: contain;
    filter: drop-shadow(0 8px 18px rgba(0, 0, 0, 0.16));
    animation: brand-breathe 2.2s ease-in-out infinite;
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

    .sphere-mark.branded {
      opacity: 1;
      filter: drop-shadow(0 6px 14px rgba(0, 0, 0, 0.14));
    }
  }
</style>
