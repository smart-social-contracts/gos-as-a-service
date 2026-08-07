/** Realm lifecycle stages — shared labels and colors across browse UI. */

export const REALM_STAGES = [
  {
    id: 'alpha',
    label: 'Alpha',
    color: '#06b6d4',
    /** Brighter pin fill for map markers (sidebar badges keep `color`). */
    marker: '#22d3ee',
    bg: 'rgba(6, 182, 212, 0.14)',
  },
  {
    id: 'beta',
    label: 'Beta',
    color: '#ca8a04',
    marker: '#facc15',
    bg: 'rgba(234, 179, 8, 0.18)',
  },
  {
    id: 'production',
    label: 'Live',
    color: '#16a34a',
    marker: '#22c55e',
    bg: 'rgba(34, 197, 94, 0.14)',
  },
  {
    id: 'deprecation',
    label: 'Winding Down',
    color: '#ea580c',
    marker: '#fb923c',
    bg: 'rgba(249, 115, 22, 0.14)',
  },
  {
    id: 'terminated',
    label: 'Archived',
    color: '#dc2626',
    marker: '#f87171',
    bg: 'rgba(239, 68, 68, 0.14)',
  },
];

const DIMMED_MARKER = '#64748B';

/** @param {string | undefined | null} stageId */
export function stageMeta(stageId) {
  if (!stageId) return null;
  return REALM_STAGES.find((stage) => stage.id === stageId) ?? null;
}

/** @param {string | undefined | null} stageId */
export function stageLabel(stageId) {
  return stageMeta(stageId)?.label ?? 'Alpha';
}

/**
 * Map pin fill for a realm stage. Dimmed search mismatches use a neutral gray.
 * @param {string | undefined | null} stageId
 * @param {{ dimmed?: boolean }} [options]
 */
export function stageMarkerColor(stageId, { dimmed = false } = {}) {
  if (dimmed) return DIMMED_MARKER;
  return stageMeta(stageId)?.marker ?? stageMeta(stageId)?.color ?? '#22d3ee';
}
