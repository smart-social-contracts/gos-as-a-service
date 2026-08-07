<script>
  import {
    parseDeploymentManifest,
    summarizeManifest,
    brandingAssetsFromManifest,
    formatManifestJson,
  } from '$lib/deployment-manifest-view.js';

  /** @type {string|null} */
  export let manifestRaw = null;
  /** @type {string} */
  export let frontendCanisterId = '';
  /** @type {boolean} */
  export let loading = false;
  /** On-chain job status — used to pick registry vs realm branding URLs. */
  export let rawStatus = '';
  /** @type {string|null} */
  export let error = null;

  let showFullJson = false;

  $: manifest = parseDeploymentManifest(manifestRaw);
  $: summary = summarizeManifest(manifest);
  $: brandingAssets = brandingAssetsFromManifest(manifest, {
    frontendCanisterId,
    rawStatus,
  });
  $: manifestJson = formatManifestJson(manifest);
</script>

<section class="manifest-panel">
  <h2 class="panel-title">Deployment manifest</h2>

  {#if loading}
    <p class="muted">Loading manifest…</p>
  {:else if error}
    <p class="error">{error}</p>
  {:else if !manifest}
    <p class="muted">Manifest not available for this deployment.</p>
  {:else}
    <dl class="summary-grid">
      {#if summary.name}
        <div><dt>Realm</dt><dd>{summary.name}</dd></div>
      {/if}
      {#if summary.network}
        <div><dt>Network</dt><dd>{summary.network}</dd></div>
      {/if}
      <div>
        <dt>Registration</dt>
        <dd>{summary.openRegistration ? 'Open' : 'Invitation only'}</dd>
      </div>
      {#if summary.codex}
        <div><dt>Codex</dt><dd>{summary.codex}{summary.codexVersion ? `@${summary.codexVersion}` : ''}</dd></div>
      {/if}
      {#if summary.slug}
        <div><dt>Slug</dt><dd><code>{summary.slug}</code></dd></div>
      {/if}
      {#if summary.portalUrl}
        <div><dt>Portal</dt><dd><a href={summary.portalUrl} target="_blank" rel="noopener noreferrer">{summary.portalUrl}</a></dd></div>
      {/if}
      {#if summary.requestingPrincipal}
        <div><dt>Creator</dt><dd><code class="principal">{summary.requestingPrincipal}</code></dd></div>
      {/if}
    </dl>

    {#if brandingAssets.length > 0}
      <h3 class="subheading">Branding</h3>
      <div class="branding-grid">
        {#each brandingAssets as asset (asset.key)}
          <div class="branding-card">
            <div class="branding-label">{asset.label}</div>
            {#if asset.primaryUrl}
              <a href={asset.primaryUrl} target="_blank" rel="noopener noreferrer" class="branding-link">
                <img src={asset.primaryUrl} alt={asset.label} class="branding-img" loading="lazy" />
              </a>
              <div class="branding-caption">
                {#if asset.primarySource === 'registry'}
                  Uploaded to file registry
                {:else}
                  Live on realm
                {/if}
              </div>
            {/if}
          </div>
        {/each}
      </div>
    {/if}

    <div class="json-toggle-row">
      <button type="button" class="json-toggle" on:click={() => (showFullJson = !showFullJson)}>
        {showFullJson ? 'Hide' : 'Show'} full manifest.json
      </button>
    </div>
    {#if showFullJson}
      <pre class="manifest-json"><code>{manifestJson}</code></pre>
    {/if}
  {/if}
</section>

<style>
  .manifest-panel {
    border-top: 1px solid #e5e5e5;
    padding-top: 1rem;
    margin-top: 0.25rem;
  }

  .panel-title {
    margin: 0 0 0.75rem;
    font-size: 1rem;
    font-weight: 700;
    color: #171717;
  }

  .subheading {
    margin: 1rem 0 0.5rem;
    font-size: 0.875rem;
    font-weight: 600;
    color: #404040;
  }

  .summary-grid {
    display: grid;
    gap: 0.5rem 1rem;
    margin: 0;
  }

  @media (min-width: 520px) {
    .summary-grid {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  .summary-grid div {
    min-width: 0;
  }

  .summary-grid dt {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    color: #737373;
    margin: 0;
  }

  .summary-grid dd {
    margin: 0.125rem 0 0;
    font-size: 0.875rem;
    color: #171717;
    word-break: break-word;
  }

  .summary-grid a {
    color: #2563eb;
    text-decoration: none;
  }

  .summary-grid a:hover {
    text-decoration: underline;
  }

  .principal {
    font-size: 0.75rem;
    word-break: break-all;
  }

  .branding-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: 0.75rem;
  }

  .branding-card {
    border: 1px solid #e5e5e5;
    border-radius: 0.5rem;
    padding: 0.5rem;
    background: #fafafa;
  }

  .branding-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: #525252;
    margin-bottom: 0.35rem;
  }

  .branding-link {
    display: block;
  }

  .branding-img {
    width: 100%;
    max-height: 120px;
    object-fit: contain;
    border-radius: 0.25rem;
    background: #fff;
  }

  .branding-caption {
    margin-top: 0.35rem;
    font-size: 0.6875rem;
    color: #737373;
  }

  .json-toggle-row {
    margin-top: 0.75rem;
  }

  .json-toggle {
    background: none;
    border: none;
    padding: 0;
    font-size: 0.8125rem;
    font-weight: 600;
    color: #525252;
    cursor: pointer;
    text-decoration: underline;
  }

  .manifest-json {
    margin: 0.5rem 0 0;
    padding: 0.75rem;
    background: #fafafa;
    border: 1px solid #e5e5e5;
    border-radius: 0.5rem;
    font-size: 0.6875rem;
    line-height: 1.45;
    overflow: auto;
    max-height: 320px;
  }

  .muted {
    margin: 0;
    font-size: 0.875rem;
    color: #737373;
  }

  .error {
    margin: 0;
    font-size: 0.875rem;
    color: #b91c1c;
  }
</style>
