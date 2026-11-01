import assert from 'node:assert/strict';
import test from 'node:test';
import { awaitingInvitation, loadInvitationState, normalizeInvitationCode } from './invitation-state.js';

const PRINCIPAL = 'kpbof-gom7k-b4gsj-sfmka-fvbac-y72nv-sb7f2-b4v4e-4557j-erlzq-2qe';

function fakeRegistry({ mode = 'enabled', activated = 'not activated', fail = false } = {}) {
	return {
		get_invitation_mode: async () => {
			if (fail) throw new Error('registry down');
			return { Ok: mode };
		},
		is_principal_activated: async () => ({ Ok: activated })
	};
}

test('only a signed-in, non-activated user in invitation mode awaits an invitation', () => {
	assert.equal(
		awaitingInvitation({ invitationMode: true, signedIn: true, activated: false }),
		true
	);
	// activated: hidden once the code is redeemed
	assert.equal(
		awaitingInvitation({ invitationMode: true, signedIn: true, activated: true }),
		false
	);
	// signed out: the landing notice and sign-in gate cover them, not the signed-in prompts
	assert.equal(
		awaitingInvitation({ invitationMode: true, signedIn: false, activated: false }),
		false
	);
	// mode off: nobody needs an invitation
	assert.equal(
		awaitingInvitation({ invitationMode: false, signedIn: true, activated: false }),
		false
	);
	assert.equal(awaitingInvitation(), false);
});

test('invitation mode off: everyone counts as activated', async () => {
	const state = await loadInvitationState(fakeRegistry({ mode: 'disabled' }), PRINCIPAL, false);
	assert.deepEqual(state, { invitationMode: false, activated: true });
});

test('invitation mode on: activation comes from the registry', async () => {
	const pending = await loadInvitationState(fakeRegistry(), PRINCIPAL, false);
	assert.deepEqual(pending, { invitationMode: true, activated: false });

	const done = await loadInvitationState(fakeRegistry({ activated: 'activated' }), PRINCIPAL, false);
	assert.deepEqual(done, { invitationMode: true, activated: true });

	const open = await loadInvitationState(fakeRegistry({ activated: 'open' }), PRINCIPAL, false);
	assert.deepEqual(open, { invitationMode: true, activated: true });
});

test('signed out in invitation mode: not activated, nothing to look up', async () => {
	const state = await loadInvitationState(fakeRegistry(), null, false);
	assert.deepEqual(state, { invitationMode: true, activated: false });
});

test('test-mode II bypass turns the gate off', async () => {
	const state = await loadInvitationState(fakeRegistry(), PRINCIPAL, true);
	assert.deepEqual(state, { invitationMode: false, activated: true });
});

test('an unreadable registry never locks the user out of the page', async () => {
	const original = console.error;
	console.error = () => {};
	try {
		const state = await loadInvitationState(fakeRegistry({ fail: true }), PRINCIPAL, false);
		assert.deepEqual(state, { invitationMode: false, activated: true });
	} finally {
		console.error = original;
	}
});

test('a code is sent trimmed and in upper case, as invite.py issues it', () => {
	assert.equal(normalizeInvitationCode('  a1b2c3  '), 'A1B2C3');
	assert.equal(normalizeInvitationCode('A1B2C3'), 'A1B2C3');
	assert.equal(normalizeInvitationCode(undefined), '');
});
