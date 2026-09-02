/** Go-live copy for the registry assistant chrome. Do not substitute. */
export const ASSISTANT_EXPERIMENTAL_NOTICE =
	'Experimental. Not official. Not legal advice. Do not enter personal data. Chats may be stored.';

/**
 * Extra Geister page_context when the go-live flag is ON. Not shown in chat
 * history. The assistant stays available; this only constrains how it speaks.
 */
export const ASSISTANT_EXPERIMENTAL_PROMPT_RULES = [
	'HOST GO-LIVE NOTICE (always in force on this portal):',
	`The user-visible notice is: "${ASSISTANT_EXPERIMENTAL_NOTICE}"`,
	'You are an unofficial, experimental helper. You do not speak for the realm, the operator, a government, or a lawyer.',
	'Do not give legal advice. Do not invent binding rules, rights, or official procedures.',
	'If asked for legal rights, binding rules, or what someone can do in this community as if it were official, say you are unofficial and experimental and point the user to the written notice / codex. Do not invent rules.',
].join(' ');

const DEFAULT_ON_NETWORKS = new Set(['staging', 'demo']);

/**
 * Explicit boolean wins. When the runtime value is unknown, staging/demo
 * default ON so gos.earth shows the experimental assistant notice.
 *
 * @param {{ assistantExperimentalNotice?: boolean, network?: string }} [options]
 */
export function isAssistantExperimentalNoticeEnabled({
	assistantExperimentalNotice,
	network = '',
} = {}) {
	if (assistantExperimentalNotice === true) return true;
	if (assistantExperimentalNotice === false) return false;
	return DEFAULT_ON_NETWORKS.has(String(network || '').toLowerCase());
}
