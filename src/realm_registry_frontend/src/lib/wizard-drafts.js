/** Persist create-realm wizard drafts on the registry canister. */

import {
  stripWizardMeta,
  withWizardMeta,
  WIZARD_META_KEY,
} from './wizard-draft-utils.js';

export { WIZARD_META_KEY } from './wizard-draft-utils.js';
export {
  filterVisibleDrafts,
  findDraftForDeployment,
  draftResumeUrl,
  isFailedDeployment,
  canDestroyRealm,
  getDraftMeta,
} from './wizard-draft-utils.js';

function parseJson(raw) {
  if (raw == null) return null;
  if (typeof raw === 'object') return raw;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/** Strip non-serializable File objects before saving. */
export function serializeWizardFormData(formData) {
  const clean = stripWizardMeta(formData || {});
  return {
    ...clean,
    logo: null,
    background: null,
  };
}

const DRAFTS_UNAVAILABLE = {
  success: false,
  error: 'Wizard drafts are not available on this registry yet',
};

export async function saveWizardDraft({
  id,
  formData,
  currentStep,
  deployVersion,
  realmName,
  wizardMeta,
}) {
  const { getAuthenticatedRegistryActor } = await import('$lib/canisters.js');
  const registry = await getAuthenticatedRegistryActor();
  if (typeof registry.save_wizard_draft !== 'function') {
    return DRAFTS_UNAVAILABLE;
  }
  const draftPayload = wizardMeta
    ? withWizardMeta(formData || {}, wizardMeta)
    : serializeWizardFormData(formData || {});
  const payload = JSON.stringify({
    id: id || '',
    realm_name: realmName || formData?.name || '',
    current_step: currentStep ?? 0,
    deploy_version: deployVersion || formData?.deploy_version || '',
    draft_json: draftPayload,
  });
  const raw = await registry.save_wizard_draft(payload);
  return parseJson(raw) || { success: false, error: 'invalid response' };
}

export async function listWizardDrafts() {
  const { getAuthenticatedRegistryActor } = await import('$lib/canisters.js');
  const registry = await getAuthenticatedRegistryActor();
  if (typeof registry.list_wizard_drafts !== 'function') {
    return [];
  }
  const raw = await registry.list_wizard_drafts();
  const data = parseJson(raw);
  if (!data?.success) return [];
  return data.drafts || [];
}

export async function loadWizardDraft(draftId) {
  const { getAuthenticatedRegistryActor } = await import('$lib/canisters.js');
  const registry = await getAuthenticatedRegistryActor();
  if (typeof registry.get_wizard_draft !== 'function') {
    return null;
  }
  const raw = await registry.get_wizard_draft(draftId);
  const data = parseJson(raw);
  if (!data?.success || !data.draft) return null;
  let formData = {};
  try {
    formData = stripWizardMeta(JSON.parse(data.draft.draft_json || '{}'));
  } catch {
    formData = {};
  }
  return {
    id: data.draft.id,
    formData,
    currentStep: data.draft.current_step || 0,
    deployVersion: data.draft.deploy_version || '',
    realmName: data.draft.realm_name || '',
    updatedAt: data.draft.updated_at || 0,
  };
}

export async function deleteWizardDraft(draftId) {
  const { getAuthenticatedRegistryActor } = await import('$lib/canisters.js');
  const registry = await getAuthenticatedRegistryActor();
  if (typeof registry.delete_wizard_draft !== 'function') {
    return DRAFTS_UNAVAILABLE;
  }
  const raw = await registry.delete_wizard_draft(draftId);
  return parseJson(raw) || { success: false };
}

/** Link a draft to a deployment job instead of deleting it (hidden while job runs). */
export async function markDraftLinkedToJob({
  id,
  formData,
  currentStep,
  deployVersion,
  jobId,
}) {
  return saveWizardDraft({
    id,
    formData,
    currentStep,
    deployVersion,
    realmName: formData?.name,
    wizardMeta: {
      deployment_job_id: jobId,
      linked_at: Date.now(),
    },
  });
}

/** Clear deployment link so a failed job can be edited and retried. */
export async function clearDraftDeploymentLink({
  id,
  formData,
  currentStep,
  deployVersion,
}) {
  return saveWizardDraft({
    id,
    formData,
    currentStep,
    deployVersion,
    realmName: formData?.name,
    wizardMeta: null,
  });
}

/** Fetch semver versions from registry catalog + always include `main`. */
export async function fetchDeployVersionOptions() {
  const options = [{ value: 'main', label: 'main (latest from file registry)' }];
  try {
    const { backend } = await import('$lib/canisters.js');
    const raw = await backend.list_versions();
    const data = parseJson(raw);
    if (data?.success && Array.isArray(data.versions)) {
      for (const v of data.versions) {
        const ver = (v.version || '').trim();
        if (ver && !options.some((o) => o.value === ver)) {
          options.push({
            value: ver,
            label: ver + (v.is_latest ? ' (latest release)' : ''),
          });
        }
      }
    }
  } catch (e) {
    console.warn('Could not load version catalog:', e);
  }
  const tag = (typeof import.meta !== 'undefined' && import.meta.env?.VITE_DEPLOY_RELEASE_TAG) || '';
  if (tag) {
    const ver = tag.replace(/^v/, '');
    if (ver && !options.some((o) => o.value === ver)) {
      options.push({ value: ver, label: `${ver} (build default)` });
    }
  }
  return options;
}
