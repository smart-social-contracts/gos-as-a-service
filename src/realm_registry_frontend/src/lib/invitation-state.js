/** Invitation mode and activation, as the portal pages read them from the registry. */

/**
 * Codes are issued in upper case and the registry hashes them exactly as sent, so a code
 * typed in lower case would be refused: normalise before sending.
 */
export function normalizeInvitationCode(code) {
	return String(code ?? '').trim().toUpperCase();
}

/** Signed in, invitation mode on, no code redeemed yet: the user must be invited first. */
export function awaitingInvitation({ invitationMode, signedIn, activated } = {}) {
	return invitationMode === true && signedIn === true && activated !== true;
}

/**
 * Read the mode and, when it is on and someone is signed in, whether they are activated.
 * If the registry cannot be read nobody is locked out of a page; the registry still
 * refuses a non-activated principal when it creates a deployment.
 *
 * @param {{ get_invitation_mode: Function, is_principal_activated: Function }} registry
 * @param {string | null} principalText the signed-in principal, or null when signed out
 * @param {boolean} iiBypass test mode: the invitation gate is off
 */
export async function loadInvitationState(registry, principalText, iiBypass) {
	try {
		const mode = await registry.get_invitation_mode();
		const invitationMode = mode?.Ok === 'enabled' && !iiBypass;
		if (!invitationMode) return { invitationMode, activated: true };
		if (!principalText) return { invitationMode, activated: false };
		const reply = await registry.is_principal_activated(principalText);
		return { invitationMode, activated: reply?.Ok === 'activated' || reply?.Ok === 'open' };
	} catch (e) {
		console.error('Invitation mode check failed:', e);
		return { invitationMode: false, activated: true };
	}
}
