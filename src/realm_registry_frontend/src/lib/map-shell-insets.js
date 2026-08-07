/**
 * Compute how much the registry map should inset when side panels are open (desktop).
 * Keeps the globe canvas in the visible band between panels instead of under them.
 */

/** @typedef {{ open: boolean, width: number, resizing?: boolean }} PanelChrome */
/** @typedef {{ open: boolean, docked: boolean, width: number, resizing?: boolean }} AssistantChrome */

/**
 * @param {PanelChrome} realmChrome
 * @param {AssistantChrome} assistantChrome
 * @param {boolean} desktopLayout
 * @returns {{ left: number, right: number }}
 */
export function mapShellInsets(realmChrome, assistantChrome, desktopLayout) {
  if (!desktopLayout) {
    return { left: 0, right: 0 };
  }
  const left = realmChrome.open ? Math.max(0, realmChrome.width || 0) : 0;
  const right =
    assistantChrome.open && assistantChrome.docked
      ? Math.max(0, assistantChrome.width || 0)
      : 0;
  return { left, right };
}
