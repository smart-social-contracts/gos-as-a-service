<script>
  import { acceptSplashLogoUrl, firstSplashLogoUrl, splashLogoCandidates } from '$lib/realm-utils.js';

  /** Pulse mark for the realm brand at `/custom/logo.png` — never clover or GOS planet. */
  export let size = 128;
  /** Frontend asset canister; `/custom/logo.png` is the configured brand. */
  export let frontendCanisterId = '';
  /** Realm `logo_url` from get_runtime_flags / status. */
  export let configuredLogoUrl = '';
  /**
   * True when the URL already names a realm (`/r/{slug}`).
   * Identified realms never paint the GOS planet or retired clover.
   */
  export let identified = false;

  // First render must already include the realm mark when the canister is known.
  // Do not start as text-only and wait for the leftover-hash probe.
  let displaySrc = firstSplashLogoUrl({
    frontendCanisterId,
    configuredLogoUrl,
  });
  let branded = Boolean(displaySrc);
  let probeGen = 0;

  $: probeBranding(frontendCanisterId, configuredLogoUrl, identified);

  async function probeBranding(canisterId, configured, isIdentified) {
    const gen = ++probeGen;
    // Slug routes identify the realm from the first paint. Do not flash
    // `/images/logo_sphere_only.svg` (or any other platform default) while
    // waiting for the configured brand.
    if (!isIdentified && !String(canisterId || '').trim()) {
      branded = false;
      displaySrc = '';
      return;
    }

    const urls = splashLogoCandidates({
      frontendCanisterId: canisterId,
      configuredLogoUrl: configured,
    });
    if (!urls.length) {
      branded = false;
      displaySrc = '';
      return;
    }

    // Paint `/custom/logo.png` (or the configured brand) on this frame.
    // Leftover clover / GOS planet rejection is async and must not blank
    // the first splash paint.
    const immediate = firstSplashLogoUrl({
      frontendCanisterId: canisterId,
      configuredLogoUrl: configured,
    });
    displaySrc = immediate || urls[0];
    branded = Boolean(displaySrc);

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
    if (gen !== probeGen) return;
    branded = false;
    displaySrc = '';
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
