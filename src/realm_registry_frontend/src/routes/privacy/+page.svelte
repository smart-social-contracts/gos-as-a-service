<script>
  import LegalPage from '$lib/components/LegalPage.svelte';
  import { CONFIG } from '$lib/config.js';
  import { isDemoEnvironment } from '$lib/demo-environment.js';
  import { demoPrivacy } from '$lib/legal/demo.js';
  import { PRIVACY } from '$lib/legal/privacy.js';
</script>

<LegalPage texts={isDemoEnvironment(CONFIG.gos_environment) ? demoPrivacy(PRIVACY) : PRIVACY} />
