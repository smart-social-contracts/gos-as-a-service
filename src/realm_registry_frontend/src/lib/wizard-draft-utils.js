/** Shared helpers for wizard draft ↔ deployment lifecycle. */

export const WIZARD_META_KEY = '_wizard_meta';

const FAILED_DEPLOYMENT_STATUSES = new Set(['failed', 'failed_verification', 'cancelled']);

export function isFailedDeployment(deployment) {
  const st = (deployment?.raw_status || deployment?.status || '').toLowerCase();
  return FAILED_DEPLOYMENT_STATUSES.has(st);
}

/** Completed deployment whose realm is still in alpha and may be destroyed. */
export function canDestroyRealm(deployment, realmStage) {
  const st = (deployment?.raw_status || deployment?.status || '').toLowerCase();
  if (st !== 'completed') return false;
  if (!(deployment?.backend_canister_id || '').trim()) return false;
  if (!realmStage) return false;
  return realmStage === 'alpha';
}

export function isActiveDeployment(deployment) {
  if (!deployment) return false;
  if (deployment.progress?.isActive != null) return deployment.progress.isActive;
  const st = (deployment?.raw_status || deployment?.status || '').toLowerCase();
  return !FAILED_DEPLOYMENT_STATUSES.has(st) && st !== 'completed';
}

export function parseDraftJson(raw) {
  if (!raw) return {};
  if (typeof raw === 'object') return raw;
  try {
    return JSON.parse(raw);
  } catch {
    return {};
  }
}

export function getDraftMeta(draftOrJson) {
  const parsed =
    typeof draftOrJson === 'string'
      ? parseDraftJson(draftOrJson)
      : parseDraftJson(draftOrJson?.draft_json);
  return parsed[WIZARD_META_KEY] || null;
}

export function stripWizardMeta(formData) {
  if (!formData || typeof formData !== 'object') return formData;
  const { [WIZARD_META_KEY]: _meta, ...rest } = formData;
  return rest;
}

export function withWizardMeta(formData, meta) {
  const base = stripWizardMeta(formData);
  if (!meta || !Object.keys(meta).length) return base;
  return { ...base, [WIZARD_META_KEY]: meta };
}

/** Hide drafts tied to in-progress or successful deployments. */
export function filterVisibleDrafts(drafts, deployments) {
  return (drafts || []).filter((draft) => !shouldHideDraft(draft, deployments));
}

export function shouldHideDraft(draft, deployments) {
  const meta = getDraftMeta(draft);
  if (meta?.deployment_job_id) {
    const dep = (deployments || []).find((d) => d.deployment_id === meta.deployment_job_id);
    if (dep && !isFailedDeployment(dep)) return true;
    return false;
  }

  const name = (draft.realm_name || '').trim().toLowerCase();
  if (!name) return false;
  return (deployments || []).some(
    (d) => (d.realm_name || '').trim().toLowerCase() === name && !isFailedDeployment(d),
  );
}

export function findDraftForDeployment(drafts, deployment) {
  if (!deployment) return null;
  const jobId = deployment.deployment_id;
  const realmName = (deployment.realm_name || '').trim().toLowerCase();

  for (const draft of drafts || []) {
    const meta = getDraftMeta(draft);
    if (jobId && meta?.deployment_job_id === jobId) return draft;
  }

  if (realmName) {
    for (const draft of drafts || []) {
      if ((draft.realm_name || '').trim().toLowerCase() === realmName) return draft;
    }
  }

  return null;
}

export function draftResumeUrl(draft, step) {
  const id = (draft?.id || '').trim();
  if (!id) return '/create-realm';
  const base = `/create-realm?draft=${encodeURIComponent(id)}`;
  if (step == null) return base;
  return `${base}&step=${encodeURIComponent(String(step))}`;
}
