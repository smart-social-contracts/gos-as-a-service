import assert from 'node:assert/strict';
import test from 'node:test';
import {
	CARD_PAY_UNAVAILABLE_COPY,
	canStartCardCheckout,
	cardPayButtonLabel,
	isCardBillingDisabled
} from './card-billing-flag.js';

test('unavailable copy is the Alpha string', () => {
	assert.equal(CARD_PAY_UNAVAILABLE_COPY, 'Coming soon');
});

test('disable_card_billing is OFF unless the registry stored it — no network default', () => {
	for (const network of ['staging', 'demo', 'Staging', 'test', 'local', 'ic', '']) {
		assert.equal(isCardBillingDisabled({ network }), false, network);
		assert.equal(canStartCardCheckout({ network }), true, network);
	}
});

test('the stored flag is the only switch', () => {
	assert.equal(isCardBillingDisabled({ disableCardBilling: true, network: 'ic' }), true);
	assert.equal(canStartCardCheckout({ disableCardBilling: true, network: 'ic' }), false);
	assert.equal(isCardBillingDisabled({ disableCardBilling: false, network: 'staging' }), false);
});

test('Pay with Card label becomes the unavailable state when disabled', () => {
	assert.equal(
		cardPayButtonLabel({ network: 'staging', availableLabel: 'Pay with Card' }),
		'Pay with Card'
	);
	assert.equal(
		cardPayButtonLabel({
			disableCardBilling: true,
			network: 'test',
			availableLabel: 'Pay with Card'
		}),
		'Coming soon'
	);
	assert.equal(
		cardPayButtonLabel({
			disableCardBilling: false,
			network: 'staging',
			availableLabel: 'Pay with Card'
		}),
		'Pay with Card'
	);
});
