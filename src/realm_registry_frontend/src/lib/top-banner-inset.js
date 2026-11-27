/**
 * A Svelte action for the fixed banner at the top of the portal (the test-mode or the demo banner). The page lays
 * itself out below it through `--test-mode-banner-height` on the root element, which follows the banner's height as it
 * wraps or folds, and drops to 0 when the banner goes.
 * @param {HTMLElement} node
 */
export function topBannerInset(node) {
  const root = document.documentElement;
  const apply = () => {
    root.style.setProperty('--test-mode-banner-height', `${node.getBoundingClientRect().height}px`);
    root.classList.add('test-mode-banner-on');
  };
  apply();
  const observer = new ResizeObserver(apply);
  observer.observe(node);
  return {
    destroy() {
      observer.disconnect();
      root.style.setProperty('--test-mode-banner-height', '0px');
      root.classList.remove('test-mode-banner-on');
    },
  };
}
