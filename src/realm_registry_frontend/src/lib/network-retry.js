/**
 * Retry an async operation when the browser reports a transient network failure.
 * @template T
 * @param {() => Promise<T>} fn
 * @param {{ attempts?: number, delayMs?: number }} [options]
 * @returns {Promise<T>}
 */
export async function retryOnTransientNetworkError(fn, { attempts = 3, delayMs = 800 } = {}) {
  /** @type {unknown} */
  let lastError;

  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      return await fn();
    } catch (error) {
      lastError = error;
      const message = error instanceof Error ? error.message : String(error);
      const transient = /network|fetch|ERR_NETWORK|Failed to fetch|dynamically imported module/i.test(
        message,
      );
      if (!transient || attempt === attempts - 1) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, delayMs * (attempt + 1)));
    }
  }

  throw lastError;
}

/** @param {unknown} error */
export function friendlyNetworkError(error) {
  const message = error instanceof Error ? error.message : String(error);
  if (/network|fetch|ERR_NETWORK|Failed to fetch|dynamically imported module/i.test(message)) {
    return 'Network connection changed or dropped. Check your connection and click Deploy again.';
  }
  return message || 'Deployment failed. Please try again.';
}
