import { createScopedDelegation } from '$lib/delegation.js';
import { resolveRealmDelegationTargets } from '$lib/delegation-targets.js';
import { getIdentity } from '$lib/auth.js';
import { CONFIG } from '$lib/config.js';
import { portalPath } from '$lib/federation.js';

const BRIDGE_VERSION = '1';

/** How often an open embed checks whether the portal's own delegation was replaced. */
const KEEP_FRESH_INTERVAL_MS = 5000;

/** Canisters a realm must never receive the visitor's delegation for. */
function platformCanisterIds() {
	return [
		CONFIG.realm_registry_backend_canister_id,
		CONFIG.realm_installer_canister_id,
		CONFIG.file_registry_canister_id,
		CONFIG.marketplace_canister_id,
		CONFIG.casals_backend_canister_id
	].filter(Boolean);
}

/**
 * Host-side portal bridge: MessageChannel handshake + scoped delegation to iframe.
 * @param {HTMLIFrameElement} iframe
 * @param {{ slug: string, backendCanisterId: string, frontendCanisterId: string, env?: string }} realm
 *   as recorded by the registry.
 * @param {{ onAuthState?: (needsLogin: boolean) => void, onFocus?: (focus: { source: string, uri: string, label?: string } | null) => void, onAssistantOpen?: () => void, onAssistantPrompt?: (payload: unknown) => void, onUiReady?: () => void }} [opts]
 *   `onAuthState(true)` fires when the iframe asks for a delegation but the
 *   portal has no session. Sign-in itself is `auth:open-login`, which leaves
 *   this embed for the portal `/join` page. `onAuthState(false)` fires once a
 *   delegation is delivered.
 *   `onFocus` receives document focus pushed from the iframe (`focus:push`);
 *   payload may be null to clear.
 *   `onAssistantOpen` fires when the iframe requests opening the mundus assistant.
 *   `onAssistantPrompt` receives a question the iframe wants the assistant to
 *   take (`assistant:prompt`), with the text it is about. The payload comes
 *   from the realm, so the receiver validates it (see `assistant-prompt.js`).
 *   An older realm never sends it and only asks to open the panel.
 *   `onUiReady` fires when the embedded realm reports real content on screen
 *   (`ui:ready`); may never fire on older realm builds — callers need a fallback.
 */
export function attachPortalBridge(iframe, realm, opts = {}) {
	let port = null;
	let disposed = false;
	/** Bumped on logout so an in-flight delegation is not delivered afterwards. */
	let authEpoch = 0;
	/** @type {Uint8Array | null} */
	let lastSessionKeyDer = null;
	/** The portal's own delegation that the last one delivered extends. */
	let deliveredFrom = null;

	const dispose = () => {
		if (disposed) return;
		disposed = true;
		clearInterval(keepFreshTimer);
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
			case 'auth:logout': {
				authEpoch += 1;
				lastSessionKeyDer = null;
				try {
					const { logout } = await import('$lib/auth.js');
					await logout();
				} catch (e) {
					console.error('[portal-bridge] logout failed:', e);
				}
				post({ type: 'auth:logout', payload: {} });
				opts.onAuthState?.(false);
				break;
			}
			case 'auth:open-login': {
				const requested = msg.payload?.returnPath;
				const path =
					typeof requested === 'string' &&
					requested.startsWith('/') &&
					!requested.startsWith('//')
						? requested
						: '/join';
				const returnTo = portalPath(realm.slug, path);
				window.location.assign(`/join?returnTo=${encodeURIComponent(returnTo)}`);
				break;
			}
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
			case 'assistant:prompt':
				opts.onAssistantPrompt?.(msg.payload);
				break;
			case 'ui:ready':
				opts.onUiReady?.();
				break;
			default:
				break;
		}
	};

	async function sendDelegation(sessionPublicKeyDer, interactive = false) {
		const epoch = authEpoch;
		try {
			if (!sessionPublicKeyDer?.length) return;
			const identity = await getIdentity();
			if (epoch !== authEpoch) return;
			if (!identity) {
				// No session. A Sign in click navigates via auth:open-login;
				// a probe just waits. Neither one covers the realm with a card.
				if (interactive) opts.onAuthState?.(true);
				post({
					type: 'auth:pending',
					error: 'Portal session required — complete sign-in on the portal'
				});
				return;
			}
			// Delegate to the capital and its verified quarters: auto-scaled realms
			// route joins/calls to quarter canisters, which must be delegation
			// targets or the replica rejects the signed calls. Resolved fresh on
			// each request so a quarter minted mid-session is covered on renewal.
			const targets = await resolveRealmDelegationTargets(
				realm.backendCanisterId,
				platformCanisterIds()
			);
			// A delegation with life left to extend: this replaces one that is nearly spent.
			await identity.refresh?.();
			// One retry: transient net::ERR_NETWORK_CHANGED / chunk-fetch blips
			// used to surface as a fatal "Login was cancelled" in the iframe.
			let scoped;
			let lastErr;
			for (let attempt = 0; attempt < 2; attempt++) {
				try {
					// Read in the same tick createScopedDelegation reads it, so it names
					// the delegation the realm's actually extends.
					const from = identity.getDelegation?.();
					scoped = await createScopedDelegation(identity, targets, sessionPublicKeyDer);
					deliveredFrom = from;
					lastErr = null;
					break;
				} catch (e) {
					lastErr = e;
					if (attempt === 0) await new Promise((r) => setTimeout(r, 400));
				}
			}
			if (lastErr || !scoped) throw lastErr || new Error('delegation failed');
			if (epoch !== authEpoch) return;
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
				env: realm.env || '',
				origin: window.location.origin
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

	// Internet Identity's app delegations last five minutes, and @icp-sdk/auth
	// replaces the portal's own shortly before it lapses. The realm's delegation
	// extends the portal's, so it lapses with it: while the realm is on screen,
	// push a fresh one as soon as the portal's own was replaced. Realm frontends
	// already deployed only ask again near `expiresAt` (see delegation.js), so the
	// portal has to be the one that keeps them current.
	let keepingFresh = false;
	async function keepEmbedFresh() {
		if (keepingFresh || disposed || !lastSessionKeyDer || document.visibilityState !== 'visible') return;
		keepingFresh = true;
		try {
			const identity = await getIdentity();
			// Test identities never rotate, and a signed-out portal has nothing to extend.
			if (!identity?.refresh) return;
			// Counts as use, and mints only once the current delegation is nearly spent.
			await identity.refresh();
			if (identity.getDelegation() !== deliveredFrom) await sendDelegation(lastSessionKeyDer);
		} finally {
			keepingFresh = false;
		}
	}
	const keepFreshTimer = setInterval(() => void keepEmbedFresh(), KEEP_FRESH_INTERVAL_MS);

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
