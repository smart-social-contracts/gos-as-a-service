import { createScopedDelegation, resolveRealmDelegationTargets } from '$lib/delegation.js';
import { getIdentity } from '$lib/auth.js';
import { portalPath } from '$lib/federation.js';

const BRIDGE_VERSION = '1';

/**
 * Host-side portal bridge: MessageChannel handshake + scoped delegation to iframe.
 * @param {HTMLIFrameElement} iframe
 * @param {{ slug: string, backendCanisterId: string, frontendCanisterId: string, env?: string }} realm
 * @param {{ onAuthState?: (needsLogin: boolean) => void, onFocus?: (focus: { source: string, uri: string, label?: string } | null) => void, onAssistantOpen?: () => void }} [opts]
 *   `onAuthState(true)` fires when the iframe asks for a delegation but the
 *   portal has no session (the page should offer II sign-in on this origin);
 *   `onAuthState(false)` fires once a delegation is delivered.
 *   `onFocus` receives document focus pushed from the iframe (`focus:push`);
 *   payload may be null to clear.
 *   `onAssistantOpen` fires when the iframe requests opening the mundus assistant.
 */
export function attachPortalBridge(iframe, realm, opts = {}) {
	let port = null;
	let disposed = false;
	/** @type {Uint8Array | null} */
	let lastSessionKeyDer = null;

	const dispose = () => {
		if (disposed) return;
		disposed = true;
		window.removeEventListener('message', onWindowMessage);
		iframe.removeEventListener('load', handshake);
		if (port) {
			port.onmessage = null;
			port.close?.();
		}
	};

	const onPortMessage = async (event) => {
		const msg = event.data;
		if (!msg || typeof msg.type !== 'string') return;

		switch (msg.type) {
			case 'bridge:ready':
				await sendDelegation(lastSessionKeyDer, false);
				break;
			case 'auth:request-delegation':
				lastSessionKeyDer = msg.payload?.sessionPublicKeyDer?.length
					? new Uint8Array(msg.payload.sessionPublicKeyDer)
					: null;
				await sendDelegation(lastSessionKeyDer, msg.payload?.interactive === true);
				break;
			case 'nav:push': {
				const path = msg.payload?.path || '/';
				const full = portalPath(realm.slug, path);
				// replace=true for auth redirects / initial sync so the back
				// button doesn't trap users on /join after they land elsewhere.
				if (msg.payload?.replace) {
					window.history.replaceState({}, '', full);
				} else {
					window.history.pushState({}, '', full);
				}
				break;
			}
			case 'nav:external': {
				const url = msg.payload?.url;
				if (url && /^https?:\/\//.test(url)) {
					window.open(url, '_blank', 'noopener,noreferrer');
				}
				break;
			}
			case 'resize:report':
				if (typeof msg.payload?.height === 'number' && iframe) {
					const viewportMin = Math.max(window.innerHeight, 320);
					iframe.style.height = `${Math.min(Math.max(msg.payload.height, viewportMin), 4000)}px`;
				}
				break;
			case 'focus:push':
				opts.onFocus?.(msg.payload ?? null);
				break;
			case 'assistant:open':
				opts.onAssistantOpen?.();
				break;
			default:
				break;
		}
	};

	async function sendDelegation(sessionPublicKeyDer, interactive = false) {
		try {
			if (!sessionPublicKeyDer?.length) return;
			const identity = await getIdentity();
			if (!identity) {
				// Only user-initiated requests raise the portal's sign-in overlay;
				// silent probes at bridge init would flash it on every visit. The
				// iframe keeps waiting either way (auth:pending is not fatal).
				if (interactive) opts.onAuthState?.(true);
				post({
					type: 'auth:pending',
					error: 'Portal session required — complete sign-in on the portal'
				});
				return;
			}
			// Delegate to the capital and all of its quarters: auto-scaled realms
			// route joins/calls to quarter canisters, which must be delegation
			// targets or the replica rejects the signed calls. Resolved fresh on
			// each request so a quarter minted mid-session is covered on renewal.
			// One retry: transient net::ERR_NETWORK_CHANGED / chunk-fetch blips
			// used to surface as a fatal "Login was cancelled" in the iframe.
			let scoped;
			let lastErr;
			for (let attempt = 0; attempt < 2; attempt++) {
				try {
					const targets = await resolveRealmDelegationTargets(realm.backendCanisterId);
					scoped = await createScopedDelegation(identity, targets, sessionPublicKeyDer);
					lastErr = null;
					break;
				} catch (e) {
					lastErr = e;
					if (attempt === 0) await new Promise((r) => setTimeout(r, 400));
				}
			}
			if (lastErr || !scoped) throw lastErr || new Error('delegation failed');
			post({
				type: 'auth:delegation',
				payload: {
					delegation: scoped.delegationChain,
					backendCanisterId: realm.backendCanisterId,
					expiresAt: scoped.expiresAt
				}
			});
			opts.onAuthState?.(false);
		} catch (e) {
			console.error('[portal-bridge] delegation failed:', e);
			post({ type: 'auth:error', error: String(e?.message || e) });
		}
	}

	function post(msg) {
		if (disposed || !port) return;
		port.postMessage({ ...msg, id: msg.id });
	}

	function handshake() {
		if (disposed || !iframe?.contentWindow) return;
		// Fresh channel each attempt: a transferred port is consumed with its
		// postMessage, so a handshake the iframe missed (listener not yet
		// attached during hydration) also loses the port.
		const channel = new MessageChannel();
		if (port) {
			port.onmessage = null;
			port.close?.();
		}
		port = channel.port1;
		port.onmessage = onPortMessage;
		post({
			type: 'config:realm',
			payload: {
				slug: realm.slug,
				backendCanisterId: realm.backendCanisterId,
				frontendCanisterId: realm.frontendCanisterId,
				env: realm.env || ''
			}
		});
		iframe.contentWindow.postMessage(
			{ type: 'bridge:init', port: channel.port2, version: BRIDGE_VERSION },
			'*',
			[channel.port2]
		);
	}

	// Re-handshake whenever the embedded realm announces itself — this is the
	// reliable path: the iframe's listener only exists after late hydration, so
	// load-time handshakes usually arrive too early and are dropped.
	const onWindowMessage = (event) => {
		if (disposed) return;
		if (event.source !== iframe?.contentWindow) return;
		if (event.data?.type !== 'bridge:hello') return;
		handshake();
	};
	window.addEventListener('message', onWindowMessage);

	iframe.addEventListener('load', handshake);
	// Parent usually calls attachPortalBridge from a load handler — run handshake now too.
	queueMicrotask(handshake);

	return {
		dispose,
		syncPath(path) {
			post({ type: 'nav:sync', payload: { path } });
		},
		logout() {
			post({ type: 'auth:logout', payload: {} });
		},
		/** Re-send the delegation for the last requested session key — call after the host signs in. */
		async refreshDelegation() {
			await sendDelegation(lastSessionKeyDer);
		}
	};
}
