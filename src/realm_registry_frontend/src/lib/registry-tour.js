import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';

/** @type {(() => void) | null} */
let replayHandler = null;

export function registerTourReplay(handler) {
  replayHandler = handler ?? null;
}

export function requestRegistryTour() {
  replayHandler?.();
}

/**
 * @param {{
 *   t: (key: string) => string,
 *   isMobile: () => boolean,
 *   actions: {
 *     openPanel: () => Promise<void>,
 *     closePanel: () => Promise<void>,
 *     closeAssistant: () => Promise<void>,
 *     openAssistant: () => Promise<void>,
 *   },
 *   onComplete?: () => void,
 * }} opts
 */
export function createRegistryTour({ t, isMobile, actions, onComplete }) {
  const mobile = isMobile();

  /** @type {import('driver.js').DriveStep[]} */
  const steps = [
    {
      element: '[data-tour="globe"]',
      popover: {
        title: t('tour.globe_title'),
        description: t('tour.globe_body'),
        side: 'top',
        align: 'center',
      },
    },
    {
      element: '[data-tour="top-rail"]',
      popover: {
        title: t('tour.rail_title'),
        description: t('tour.rail_body'),
        side: 'bottom',
        align: 'center',
      },
    },
    {
      element: mobile ? '[data-tour="browse-ear-mobile"]' : '[data-tour="browse-ear-desktop"]',
      popover: {
        title: t('tour.browse_title'),
        description: t('tour.browse_body'),
        side: mobile ? 'top' : 'right',
        align: 'start',
      },
    },
    {
      element: '[data-tour="realm-panel"]',
      popover: {
        title: t('tour.panel_title'),
        description: t('tour.panel_body'),
        side: mobile ? 'top' : 'right',
        align: 'start',
      },
      onHighlightStarted: async (_el, _step, { driver: tour }) => {
        await actions.openPanel();
        requestAnimationFrame(() => tour.refresh());
      },
      onDeselected: async () => {
        await actions.closePanel();
      },
    },
    {
      element: mobile ? '[data-tour="assistant-ear-mobile"]' : '[data-tour="assistant-ear-desktop"]',
      popover: {
        title: t('tour.assistant_title'),
        description: t('tour.assistant_body'),
        side: mobile ? 'top' : 'left',
        align: 'start',
      },
      onHighlightStarted: async (_el, _step, { driver: tour }) => {
        await actions.closePanel();
        await actions.closeAssistant();
        requestAnimationFrame(() => tour.refresh());
      },
    },
    {
      element: '[data-tour="assistant-compose"]',
      popover: {
        title: t('tour.assistant_compose_title'),
        description: t('tour.assistant_compose_body'),
        side: mobile ? 'top' : 'left',
        align: 'end',
      },
      onHighlightStarted: async (_el, _step, { driver: tour }) => {
        await actions.closePanel();
        await actions.openAssistant();
        requestAnimationFrame(() => tour.refresh());
      },
      onDeselected: async () => {
        await actions.closeAssistant();
      },
    },
    {
      element: mobile ? '[data-tour="mobile-stats"]' : '[data-tour="desktop-stats"]',
      popover: {
        title: t('tour.stats_title'),
        description: t('tour.stats_body'),
        side: 'top',
        align: 'center',
      },
      onHighlightStarted: async (_el, _step, { driver: tour }) => {
        await actions.closePanel();
        await actions.closeAssistant();
        requestAnimationFrame(() => tour.refresh());
      },
    },
    {
      popover: {
        title: t('tour.complete_title'),
        description: t('tour.complete_body'),
        side: 'over',
        align: 'center',
      },
      onHighlightStarted: async () => {
        await actions.closePanel();
        await actions.closeAssistant();
      },
    },
  ];

  const instance = driver({
    animate: true,
    showProgress: true,
    progressText: t('tour.progress'),
    nextBtnText: t('tour.next'),
    prevBtnText: t('tour.prev'),
    doneBtnText: t('tour.done'),
    popoverClass: 'registry-tour-popover',
    stagePadding: 8,
    stageRadius: 10,
    overlayOpacity: 0.55,
    steps,
    onDestroyed: () => {
      void actions.closePanel();
      void actions.closeAssistant();
      onComplete?.();
    },
  });

  return {
    start: () => instance.drive(),
    destroy: () => instance.isActive() && instance.destroy(),
  };
}
