/** Alpha copy for disabled portal card checkout: billing is not open yet. */
export const CARD_PAY_UNAVAILABLE_COPY = 'Coming soon';

/**
 * Card checkout stays in the Stripe path; this flag only disables charging.
 *
 * The registry's stored flag (casals.json `test_flags.disable_card_billing`)
 * is the only switch; no network name turns it on.
 *
 * @param {{ disableCardBilling?: boolean, network?: string }} [options]
 */
export function isCardBillingDisabled({ disableCardBilling } = {}) {
	return disableCardBilling === true;
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
