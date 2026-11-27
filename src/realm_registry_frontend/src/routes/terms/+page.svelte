<script>
  import LegalPage from '$lib/components/LegalPage.svelte';
  import { CONFIG } from '$lib/config.js';
  import { isDemoEnvironment } from '$lib/demo-environment.js';
  import { demoTerms } from '$lib/legal/demo.js';
  import { TERMS } from '$lib/legal/terms.js';
</script>

<LegalPage texts={isDemoEnvironment(CONFIG.gos_environment) ? demoTerms(TERMS) : TERMS} />
