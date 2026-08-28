/** Go-live copy for disabled portal card checkout. Do not substitute. */
export const CARD_PAY_UNAVAILABLE_COPY = 'Not available in this demo';

const DEFAULT_ON_NETWORKS = new Set(['staging', 'demo']);

/**
 * Card checkout stays in the Stripe path; this flag only disables charging.
 *
 * Explicit boolean wins. When the runtime value is unknown, staging/demo
 * default ON so Pay with Card cannot charge on those portals.
 *
 * @param {{ disableCardBilling?: boolean, network?: string }} [options]
 */
export function isCardBillingDisabled({ disableCardBilling, network = '' } = {}) {
	if (disableCardBilling === true) return true;
	if (disableCardBilling === false) return false;
	return DEFAULT_ON_NETWORKS.has(String(network || '').toLowerCase());
}

/** True only when the Stripe create-session path may run. */
export function canStartCardCheckout(options = {}) {
	return !isCardBillingDisabled(options);
}

export function cardPayButtonLabel({ disableCardBilling, network, availableLabel } = {}) {
	if (isCardBillingDisabled({ disableCardBilling, network })) {
		return CARD_PAY_UNAVAILABLE_COPY;
	}
	return availableLabel || 'Pay with Card';
}
