const TOUR_DONE_KEY = 'registry_navigation_tour_done';

export function isRegistryTourComplete() {
  if (typeof window === 'undefined') return true;
  try {
    return localStorage.getItem(TOUR_DONE_KEY) === '1';
  } catch {
    return false;
  }
}

export function markRegistryTourComplete() {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(TOUR_DONE_KEY, '1');
  } catch {
    /* ignore quota / private mode */
  }
}

export function clearRegistryTourComplete() {
  if (typeof window === 'undefined') return;
  try {
    localStorage.removeItem(TOUR_DONE_KEY);
  } catch {
    /* ignore */
  }
}
