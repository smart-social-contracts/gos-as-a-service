import { stageLabel, stageMeta } from '$lib/realm-stages.js';

/** @param {string} value */
function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** @param {number | undefined | null} value */
function formatCount(value) {
  const n = Number(value) || 0;
  return n.toLocaleString();
}

/**
 * @param {string} key
 * @param {Record<string, unknown>} [values]
 */
function t(translate, key, values = {}) {
  return translate(key, { values, default: key });
}

/**
 * @param {{
 *   primaryName: string,
 *   stageId?: string | null,
 *   zoneUsers?: number,
 *   totalUsers?: number,
 *   locations?: string[],
 *   manifesto?: string,
 *   influenceLabel?: string,
 *   realmCount?: number,
 *   isCenter?: boolean,
 * }} data
 * @param {(key: string, opts?: { values?: Record<string, unknown>, default?: string }) => string} translate
 */
export function buildRealmHoverPopupHtml(data, translate) {
  const name = escapeHtml(data.primaryName || 'Realm');
  const stage = stageMeta(data.stageId);
  const stageText = escapeHtml(stageLabel(data.stageId));
  const stageColor = stage?.color ?? '#06b6d4';
  const stageBg = stage?.bg ?? 'rgba(6, 182, 212, 0.14)';

  const metaRows = [];

  if (data.locations?.length) {
    metaRows.push(
      `<div class="realm-hover-locations">${escapeHtml(data.locations.join(' · '))}</div>`
    );
  }

  if (data.isCenter && data.zoneUsers != null && data.zoneUsers > 0) {
    metaRows.push(
      `<div class="realm-hover-stat">
        <span class="realm-hover-stat-icon" aria-hidden="true">◉</span>
        ${escapeHtml(t(translate, 'map.users_in_zone', { count: formatCount(data.zoneUsers) }))}
      </div>`
    );
  } else if (data.influenceLabel) {
    metaRows.push(`<div class="realm-hover-influence">${escapeHtml(data.influenceLabel)}</div>`);
  }

  if (data.realmCount && data.realmCount > 1) {
    const influenceKey = data.realmCount === 1 ? 'map.realm_influence' : 'map.realms_influence';
    metaRows.push(
      `<div class="realm-hover-stat muted">
        ${escapeHtml(t(translate, influenceKey, { count: formatCount(data.realmCount) }))}
      </div>`
    );
  }

  if (data.isCenter && data.totalUsers != null && data.totalUsers > 0 && data.totalUsers !== data.zoneUsers) {
    metaRows.push(
      `<div class="realm-hover-stat muted">
        ${escapeHtml(t(translate, 'globe.popup_total_users', { count: formatCount(data.totalUsers) }))}
      </div>`
    );
  }

  const manifesto = data.manifesto?.trim();
  const manifestoHtml = manifesto
    ? `<p class="realm-hover-manifesto">${escapeHtml(manifesto)}</p>`
    : '';

  const hint = escapeHtml(t(translate, 'globe.popup_click'));

  return `<div class="realm-hover-card">
    <div class="realm-hover-header">
      <h3 class="realm-hover-title">${name}</h3>
      <span class="realm-hover-stage" style="color:${stageColor};background:${stageBg}">${stageText}</span>
    </div>
    ${metaRows.join('')}
    ${manifestoHtml}
    <div class="realm-hover-footer">${hint}</div>
  </div>`;
}

/**
 * @param {import('./hex-data.js').HexPolygon} polygon
 * @param {(key: string, opts?: { values?: Record<string, unknown>, default?: string }) => string} translate
 */
export function buildHexHoverPopupHtml(polygon, translate) {
  const primary = polygon.realms?.[0];
  if (!primary?.realm) return '';

  const realm = primary.realm;
  const isCenter = polygon.minDistance === 0;
  const locations = [
    ...new Set(
      polygon.realms
        .filter((entry) => entry.isCenter)
        .flatMap((entry) => entry.locations || [])
        .filter(Boolean)
    ),
  ];

  return buildRealmHoverPopupHtml(
    {
      primaryName: realm.name || realm.realm_name || realm.id,
      stageId: realm.realm_stage,
      zoneUsers: isCenter ? polygon.totalUsers : undefined,
      totalUsers: realm.users_count,
      locations: isCenter ? locations : undefined,
      manifesto: isCenter ? realm.manifesto : undefined,
      influenceLabel: isCenter ? undefined : t(translate, 'globe.popup_influence_zone'),
      realmCount: polygon.realms.length > 1 ? polygon.realms.length : undefined,
      isCenter,
    },
    translate
  );
}

/**
 * @param {{
 *   realmName?: string,
 *   stage?: string,
 *   users?: number,
 *   totalUsers?: number,
 *   location?: string,
 *   manifesto?: string,
 * }} point
 * @param {(key: string, opts?: { values?: Record<string, unknown>, default?: string }) => string} translate
 */
export function buildMarkerHoverPopupHtml(point, translate) {
  return buildRealmHoverPopupHtml(
    {
      primaryName: point.realmName || 'Realm',
      stageId: point.stage,
      zoneUsers: point.users,
      totalUsers: point.totalUsers ?? point.users,
      locations: point.location ? [point.location] : undefined,
      manifesto: point.manifesto,
      isCenter: true,
    },
    translate
  );
}
