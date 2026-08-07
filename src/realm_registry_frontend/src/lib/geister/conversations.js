import { CONVERSATIONS_API_URL } from './constants.js';

/**
 * @typedef {{ conversation_id: string, title?: string, persona?: string, updated_at: string, message_count?: number, context_realm?: string | null }} Conversation
 * @typedef {{ conversations: Conversation[], error: string | null }} ConversationListResult
 */

/** @returns {string} */
export function newConversationId() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

/**
 * User-global inbox (optional context_realm filter). Prefer omitting realm filter
 * so history follows the user across registry + portal realms.
 * @param {string} userPrincipal
 * @param {string} [contextRealm]
 * @returns {Promise<ConversationListResult>}
 */
export async function fetchConversations(userPrincipal, contextRealm = '') {
  if (!userPrincipal) return { conversations: [], error: null };
  const params = new URLSearchParams({ user_principal: userPrincipal });
  if (contextRealm) {
    params.set('context_realm', contextRealm);
    params.set('realm_principal', contextRealm);
  }
  try {
    const res = await fetch(`${CONVERSATIONS_API_URL}?${params}`, {
      headers: { 'Content-Type': 'application/json' },
    });
    if (!res.ok) {
      let detail = '';
      try {
        const body = await res.json();
        detail = typeof body?.error === 'string' ? body.error : '';
      } catch (e) {
        /* ignore */
      }
      return { conversations: [], error: detail || `HTTP ${res.status}` };
    }
    const data = await res.json();
    const conversations = (data.conversations || []).sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );
    return { conversations, error: null };
  } catch (e) {
    return { conversations: [], error: e?.message || 'Failed to load conversations' };
  }
}

/**
 * @param {string} userPrincipal
 * @param {string} persona
 * @param {string} [contextRealm]
 * @returns {Promise<string|null>}
 */
export async function createConversation(userPrincipal, persona, contextRealm = '') {
  if (!userPrincipal) return null;
  /** @type {Record<string, string>} */
  const body = {
    user_principal: userPrincipal,
    persona: persona || 'ashoka',
  };
  if (contextRealm) {
    body.context_realm = contextRealm;
    body.realm_principal = contextRealm;
  }
  try {
    const res = await fetch(CONVERSATIONS_API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.conversation_id || null;
  } catch (e) {
    return null;
  }
}

/**
 * @param {string} conversationId
 * @returns {Promise<{ text: string, isUser: boolean }[]>}
 */
export async function loadConversationMessages(conversationId) {
  if (!conversationId) return [];
  const res = await fetch(`${CONVERSATIONS_API_URL}/${conversationId}/messages`, {
    headers: { 'Content-Type': 'application/json' },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return normalizeHistoryMessages(data.messages || []);
}

/** @param {string} conversationId */
export async function deleteConversation(conversationId) {
  if (!conversationId) return;
  await fetch(`${CONVERSATIONS_API_URL}/${conversationId}`, { method: 'DELETE' });
}

/**
 * Register that the user sent a message — creates/updates the session title immediately,
 * before the assistant finishes replying.
 * @param {{ conversationId: string, userPrincipal: string, question: string, persona?: string, contextRealm?: string }} opts
 */
export async function touchConversation(opts) {
  const { conversationId, userPrincipal, question } = opts;
  if (!conversationId || !userPrincipal || !question?.trim()) return null;
  /** @type {Record<string, string>} */
  const body = {
    user_principal: userPrincipal,
    question: question.trim(),
    persona: opts.persona || 'ashoka',
  };
  if (opts.contextRealm) {
    body.context_realm = opts.contextRealm;
    body.realm_principal = opts.contextRealm;
  }
  try {
    const res = await fetch(`${CONVERSATIONS_API_URL}/${conversationId}/touch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) return null;
    const data = await res.json();
    return data.title || null;
  } catch (e) {
    return null;
  }
}

/**
 * @param {string} userPrincipal
 * @param {string} [contextRealm]
 */
export async function clearAllHistory(userPrincipal, contextRealm = '') {
  const { conversations } = await fetchConversations(userPrincipal, contextRealm);
  await Promise.all(conversations.map((c) => deleteConversation(c.conversation_id)));
}

/**
 * @param {any[]} rows
 * @returns {{ text: string, isUser: boolean }[]}
 */
export function normalizeHistoryMessages(rows) {
  /** @type {{ text: string, isUser: boolean }[]} */
  const out = [];
  for (const row of rows || []) {
    if (row.role === 'user' || row.role === 'assistant') {
      const text = String(row.content ?? row.text ?? '').trim();
      if (text) out.push({ text, isUser: row.role === 'user' });
      continue;
    }
    if (row.question != null && String(row.question).trim()) {
      out.push({ text: String(row.question), isUser: true });
    }
    if (row.response != null && String(row.response).trim()) {
      out.push({ text: String(row.response), isUser: false });
    }
  }
  return out;
}

/** @param {string} dateStr */
export function formatConversationDate(dateStr) {
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - d.getTime();
  const diffDays = Math.floor(diffMs / 86400000);
  if (diffDays === 0) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return d.toLocaleDateString([], { weekday: 'short' });
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}
