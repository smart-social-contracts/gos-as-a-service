/**
 * Read the live test-mode banner height from the document root CSS variable.
 * @param {Document | undefined} doc
 */
export function readTestModeBannerHeightPx(doc = typeof document !== 'undefined' ? document : undefined) {
  if (!doc) return 0;
  const raw = doc.documentElement.style.getPropertyValue('--test-mode-banner-height').trim()
    || getComputedStyle(doc.documentElement).getPropertyValue('--test-mode-banner-height').trim();
  const value = parseFloat(raw);
  return Number.isFinite(value) ? value : 0;
}
