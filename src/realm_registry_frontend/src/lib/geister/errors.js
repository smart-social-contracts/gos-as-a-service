/**
 * @param {any} err
 * @param {number} [httpStatus]
 * @returns {string}
 */
export function classifyChatError(err, httpStatus) {
  if (err?.name === 'TimeoutError' || err?.name === 'AbortError') {
    return 'The assistant took too long to respond. Please try again.';
  }
  const msg = typeof err?.message === 'string' ? err.message : '';
  if (httpStatus === 503 || /waking|cold start|starting/i.test(msg)) {
    return 'The AI backend is waking up. Please try again in a moment.';
  }
  if (httpStatus && httpStatus >= 500) {
    return 'The AI assistant is temporarily unavailable. Please try again shortly.';
  }
  if (msg && !/^HTTP error/i.test(msg)) return msg;
  return 'The AI assistant is temporarily unavailable. Please try again shortly.';
}

/** @param {string} text */
export function isLlmBackendError(text) {
  return /backend.*(offline|unavailable|error)|model.*(unavailable|error)/i.test(text || '');
}
