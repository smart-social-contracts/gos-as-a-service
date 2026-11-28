/**
 * The environments that are a public demo with simulated data. demo.gos.earth is the demo portal, and staging shares
 * its registry, installer and realms (and anyone can sign in there too), so both show the demo banner and the demo's
 * privacy and terms. Production never does.
 */
const DEMO_ENVIRONMENTS = new Set(['demo', 'staging']);

/** @param {string | undefined | null} gosEnvironment the portal's `gos_environment` from /canister_ids.js */
export function isDemoEnvironment(gosEnvironment) {
  return DEMO_ENVIRONMENTS.has((gosEnvironment || '').trim().toLowerCase());
}
