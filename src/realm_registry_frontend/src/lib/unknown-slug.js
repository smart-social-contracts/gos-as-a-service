import { slugify } from './deployment-manifest-core.js';
import { deploymentJobUrl } from './deployment-url.js';

export const ACTIVE_DEPLOY_STATUSES = new Set([
  'queued',
  'pending',
  'provisioning',
  'verifying',
  'extensions',
  'registering',
  'in_progress',
]);

export const FAILED_DEPLOY_STATUSES = new Set([
  'failed',
  'failed_verification',
  'cancelled',
]);

export function isUnknownSlugError(err, slug) {
  const msg = err instanceof Error ? err.message : String(err || '');
  const key = (slug || '').trim().toLowerCase();
  return msg.includes('Unknown slug') && (!key || msg.includes(key));
}

export function jobMatchesSlug(job, slug) {
  const key = slugify(slug || '');
  if (!key || key === 'realm') return false;
  const realmSlug = slugify(job?.realm_name || '');
  if (realmSlug === key) return true;
  const manifestSlug = slugify(job?.federation_slug || job?.slug || '');
  return Boolean(manifestSlug) && manifestSlug === key;
}

/** Newest matching job wins (caller should pass newest-first). */
export function findJobForSlug(jobs, slug) {
  const list = Array.isArray(jobs) ? jobs : [];
  return list.find((job) => jobMatchesSlug(job, slug)) || null;
}

export function unknownSlugView(slug, job) {
  const key = (slug || '').trim().toLowerCase() || 'this-realm';
  const status = (job?.status || job?.raw_status || '').toLowerCase();
  const realmName = (job?.realm_name || '').trim() || key;

  if (job && ACTIVE_DEPLOY_STATUSES.has(status)) {
    return {
      kind: 'creating',
      title: `${realmName} is still being created.`,
      body: 'This page will work when registration finishes.',
      jobId: job.job_id || '',
      href: deploymentJobUrl(job.job_id),
    };
  }
  if (job && FAILED_DEPLOY_STATUSES.has(status)) {
    return {
      kind: 'failed',
      title: 'Creation failed.',
      body: 'Open the deployment to see why.',
      jobId: job.job_id || '',
      href: deploymentJobUrl(job.job_id),
    };
  }
  return {
    kind: 'missing',
    title: `No realm named ${key} on this portal.`,
    body: '',
    jobId: '',
    href: '',
  };
}
