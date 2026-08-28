import assert from 'node:assert/strict';
import test from 'node:test';
import {
	CARD_PAY_UNAVAILABLE_COPY,
	canStartCardCheckout,
	cardPayButtonLabel,
	isCardBillingDisabled
} from './card-billing-flag.js';

test('unavailable copy is the go-live string', () => {
	assert.equal(CARD_PAY_UNAVAILABLE_COPY, 'Currently not available');
	assert.notEqual(CARD_PAY_UNAVAILABLE_COPY.toLowerCase(), 'coming soon');
	assert.notEqual(CARD_PAY_UNAVAILABLE_COPY, 'Not available in this demo');
});

test('disable_card_billing defaults ON for staging and demo', () => {
	assert.equal(isCardBillingDisabled({ network: 'staging' }), true);
	assert.equal(isCardBillingDisabled({ network: 'demo' }), true);
	assert.equal(isCardBillingDisabled({ network: 'Staging' }), true);
	assert.equal(canStartCardCheckout({ network: 'staging' }), false);
	assert.equal(canStartCardCheckout({ network: 'demo' }), false);
});

test('disable_card_billing defaults OFF for test and production', () => {
	assert.equal(isCardBillingDisabled({ network: 'test' }), false);
	assert.equal(isCardBillingDisabled({ network: 'ic' }), false);
	assert.equal(isCardBillingDisabled({ network: '' }), false);
	assert.equal(canStartCardCheckout({ network: 'test' }), true);
});

test('explicit flag overrides the network default', () => {
	assert.equal(
		isCardBillingDisabled({ disableCardBilling: false, network: 'staging' }),
		false
	);
	assert.equal(
		canStartCardCheckout({ disableCardBilling: false, network: 'staging' }),
		true
	);
	assert.equal(
		isCardBillingDisabled({ disableCardBilling: true, network: 'test' }),
		true
	);
	assert.equal(canStartCardCheckout({ disableCardBilling: true, network: 'test' }), false);
});

test('Pay with Card label becomes the unavailable state when disabled', () => {
	assert.equal(
		cardPayButtonLabel({ network: 'staging', availableLabel: 'Pay with Card' }),
		'Currently not available'
	);
	assert.equal(
		cardPayButtonLabel({
			disableCardBilling: true,
			network: 'test',
			availableLabel: 'Pay with Card'
		}),
		'Currently not available'
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
