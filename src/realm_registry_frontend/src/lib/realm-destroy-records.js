/** Persist destroyed-realm cards locally until the user dismisses them. */

import { browser } from '$app/environment';

const STORAGE_VERSION = 1;

function storageKey(principalText) {
  const p = (principalText || 'anonymous').trim();
  return `realms_destroyed_cards_v${STORAGE_VERSION}_${p}`;
}

function readStore(principalText) {
  if (!browser || typeof localStorage === 'undefined') {
    return { records: [], dismissed: [] };
  }
  try {
    const raw = localStorage.getItem(storageKey(principalText));
    if (!raw) return { records: [], dismissed: [] };
    const data = JSON.parse(raw);
    return {
      records: Array.isArray(data.records) ? data.records : [],
      dismissed: Array.isArray(data.dismissed) ? data.dismissed : [],
    };
  } catch {
    return { records: [], dismissed: [] };
  }
}

function writeStore(principalText, store) {
  if (!browser || typeof localStorage === 'undefined') return;
  localStorage.setItem(storageKey(principalText), JSON.stringify(store));
}

/** @returns {object[]} visible destroyed records (not dismissed) */
export function loadDestroyRecords(principalText) {
  const store = readStore(principalText);
  const dismissed = new Set(store.dismissed || []);
  return (store.records || []).filter((rec) => rec?.job_id && !dismissed.has(rec.job_id));
}

/**
 * @param {string} principalText
 * @param {object} record from deploymentToDestroyRecord
 */
export function saveDestroyRecord(principalText, record) {
  if (!record?.job_id) return;
  const store = readStore(principalText);
  const records = (store.records || []).filter((r) => r.job_id !== record.job_id);
  records.unshift(record);
  writeStore(principalText, {
    records: records.slice(0, 50),
    dismissed: store.dismissed || [],
  });
}

/** Hide a destroyed card from the dashboard (local only). */
export function dismissDestroyRecord(principalText, jobId) {
  if (!jobId) return;
  const store = readStore(principalText);
  const dismissed = new Set(store.dismissed || []);
  dismissed.add(jobId);
  writeStore(principalText, {
    records: store.records || [],
    dismissed: [...dismissed],
  });
}
