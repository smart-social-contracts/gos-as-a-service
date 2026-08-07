/** Canonical URL for tracking a single deployment job. */
export function deploymentJobUrl(jobId) {
  const id = (jobId || '').trim();
  if (!id) return '/my-dashboard?tab=realms';
  return `/my-dashboard/deployments?job=${encodeURIComponent(id)}`;
}
