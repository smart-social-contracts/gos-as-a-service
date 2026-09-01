/** Canonical destinations for the registry “What is this?” intro. */
export const INTRO_LINKS = {
  ggg: 'https://github.com/smart-social-contracts/ggg',
  realm: 'https://github.com/smart-social-contracts/ggg',
  ssc: 'https://smartsocialcontracts.org',
  ic: 'https://internetcomputer.org',
};

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

/**
 * Replace `[[token]]` placeholders with new-tab links.
 *
 * @param {string} template
 * @param {Record<string, { href: string, label: string }>} tokens
 * @returns {string}
 */
export function applyIntroLinks(template, tokens) {
  const escaped = escapeHtml(String(template || ''));
  return escaped.replace(/\[\[(\w+)\]\]/g, (_, key) => {
    const token = tokens?.[key];
    if (!token?.href || token.label == null || token.label === '') return '';
    return `<a class="intro-inline-link" href="${escapeHtml(token.href)}" target="_blank" rel="noopener noreferrer">${escapeHtml(token.label)}</a>`;
  });
}
