<!--
  Mundus-level AI assistant (issue #233).

  Owned by the registry/portal (canonical II origin). Toggleable between a
  floating bottom-right card and a docked right-side panel; dock preference and
  open state persist in localStorage. On the registry home it talks to Geister
  in GENERAL mode (no `context_realm`) for cross-realm / platform help. When
  the user is browsing a portal realm page (`/r/<slug>/...`) it is
  realm-scoped: it resolves the realm's backend canister id and sends
  `context_realm` plus `page_context` (and optional document focus from the
  embedded iframe) so Geister can enrich answers with realm status / tools.

  It deliberately does NOT consult any realm's `ai_assistant_enabled` flag — a
  realm cannot disable the user's global assistant. When the user is signed in
  with Internet Identity (canonical principal), conversations persist via the
  same Geister endpoints used inside realms, so history follows the user between
  the registry and every realm.

  Svelte 4 (the registry frontend is Svelte 4, so this does not reuse the
  Svelte 5 `LlmChat.svelte` extension component).
-->
<script>
  import { onMount, onDestroy, tick } from 'svelte';
  import { _ } from 'svelte-i18n';
  import { page } from '$app/stores';
  import { get } from 'svelte/store';
  import { goto } from '$app/navigation';
  import { portalDocumentFocus } from '$lib/portal-focus.js';
  import { assistantChrome } from '$lib/assistant-chrome.js';
  import { assistantOpenRequest, assistantToggleRequest, assistantCloseRequest } from '$lib/assistant-open.js';
  import { API_URL, CHAT_REQUEST_TIMEOUT_MS, geisterNetwork } from '$lib/geister/constants.js';
  import { renderMarkdown } from '$lib/geister/assistant-markdown.js';
  import { loadPrefs, loadPanelWidth, savePanelWidth } from '$lib/geister/assistant-prefs.js';
  import { clampPanelWidth, defaultPanelWidth } from '$lib/panel-width.js';
  import {
    fetchConversations,
    createConversation,
    loadConversationMessages,
    deleteConversation,
    formatConversationDate,
    newConversationId,
    touchConversation,
  } from '$lib/geister/conversations.js';
  import { fetchAssistants } from '$lib/geister/personas.js';
  import { fetchSuggestions } from '$lib/geister/suggestions.js';
  import { classifyChatError, isLlmBackendError } from '$lib/geister/errors.js';

  const DOCKED_KEY = 'mundus_assistant_docked';
  const OPEN_KEY = 'mundus_assistant_open';
  const LAST_CONV_KEY = 'mundus_assistant_last_conv';
  const HISTORY_KEY = 'mundus_assistant_history_open';

  let open = false;
  let docked = false;
  let panelWidth = defaultPanelWidth();
  /** @type {{ text: string, isUser: boolean }[]} */
  let messages = [];
  let newMessage = '';
  let loadingStatus = '';
  let error = '';
  let userPrincipal = '';
  /** @type {HTMLElement | undefined} */
  let messagesContainer;
  function scrollRegion(node) {
    messagesContainer = node;
    return {
      destroy() {
        messagesContainer = undefined;
      },
    };
  }

  /** @type {string | null} */
  let portalSlug = null;
  /** @type {string} */
  let inRealmPath = '/';
  /** @type {string | null} */
  let contextRealmId = null;
  /** @type {string | null} */
  let frontendCanisterId = null;
  /** @type {{ source?: string, uri?: string, label?: string } | null} */
  let documentFocus = null;
  /** @type {(() => void) | undefined} */
  let unsubFocus;
  /** @type {(() => void) | undefined} */
  let unsubPage;
  /** @type {(() => void) | undefined} */
  let unsubOpenRequest;
  /** @type {(() => void) | undefined} */
  let unsubToggleRequest;
  /** @type {(() => void) | undefined} */
  let unsubCloseRequest;
  /** @type {(() => void) | undefined} */
  let unsubPrefsFocus;

  /** @type {Record<string, { backend: string, frontend: string }>} */
  const realmCache = Object.create(null);

  // Prefs / personas / history / suggestions
  let showSuggestions = true;
  let sharePageContext = true;
  let defaultAssistantId = '';
  /** @type {{ id: string, name: string, emoji?: string, description?: string }[]} */
  let availableAssistants = [];
  /** @type {{ id: string, name: string, emoji?: string, description?: string } | null} */
  let selectedAssistant = null;
  /** @type {string | null} */
  let conversationId = null;
  /** @type {import('$lib/geister/conversations.js').Conversation[]} */
  let conversations = [];
  let showHistory = false;
  let isLoadingHistory = false;
  let historyError = '';
  /** @type {string[]} */
  let suggestions = [];
  let isLoadingSuggestions = false;
  /** @type {number | null} */
  let copiedIndex = null;

  // Resize drag state
  let isResizing = false;

  function syncChrome() {
    assistantChrome.set({ open, docked, width: panelWidth, resizing: isResizing });
  }

  function persistLastConversation(id) {
    try {
      if (id) localStorage.setItem(LAST_CONV_KEY, id);
      else localStorage.removeItem(LAST_CONV_KEY);
    } catch (e) {
      /* private mode */
    }
  }

  function readLastConversation() {
    try {
      return localStorage.getItem(LAST_CONV_KEY) || null;
    } catch (e) {
      return null;
    }
  }

  function persistShowHistory(value) {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(!!value));
    } catch (e) {
      /* private mode */
    }
  }

  function readShowHistory(defaultValue = false) {
    try {
      const raw = localStorage.getItem(HISTORY_KEY);
      if (raw === null) return defaultValue;
      return JSON.parse(raw) === true;
    } catch (e) {
      return defaultValue;
    }
  }

  /** @type {Record<string, boolean>} */
  let pendingSendIds = {};

  function isPending(id) {
    return !!(id && pendingSendIds[id]);
  }

  function markPending(id) {
    if (!id) return;
    pendingSendIds = { ...pendingSendIds, [id]: true };
  }

  function clearPending(id) {
    if (!id || !pendingSendIds[id]) return;
    const next = { ...pendingSendIds };
    delete next[id];
    pendingSendIds = next;
  }

  function isViewingConversation(id) {
    if (!id && !conversationId) return true;
    return !!id && conversationId === id;
  }

  function detachUiFromSend() {
    loadingStatus = '';
  }

  // Reference pendingSendIds directly so Svelte tracks pending state reliably.
  $: viewingPending = conversationId
    ? !!pendingSendIds[conversationId]
    : !!pendingSendIds['__anonymous__'];
  $: awaitingReply =
    viewingPending && messages.length > 0 && messages[messages.length - 1]?.isUser;

  function mergeConversationLists(serverList, previousList) {
    /** @type {Map<string, import('$lib/geister/conversations.js').Conversation>} */
    const byId = new Map();
    for (const c of serverList || []) {
      if (c?.conversation_id) byId.set(c.conversation_id, c);
    }
    for (const c of previousList || []) {
      if (c?.conversation_id && c.conversation_id !== '__current__' && !byId.has(c.conversation_id)) {
        byId.set(c.conversation_id, c);
      }
    }
    return [...byId.values()].sort(
      (a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime(),
    );
  }

  async function refreshConversations() {
    historyError = '';
    if (!userPrincipal) {
      conversations = [];
      return;
    }
    isLoadingHistory = true;
    const previous = conversations;
    try {
      const { conversations: list, error } = await fetchConversations(userPrincipal);
      conversations = mergeConversationLists(list, previous);
      historyError = error || '';
    } catch (e) {
      console.warn('[RegistryAssistant] fetchConversations failed:', e);
      historyError = e?.message || 'Failed to load conversations';
    } finally {
      isLoadingHistory = false;
    }
  }

  function titleFromMessages(msgs) {
    const first = msgs.find((m) => m.isUser && m.text?.trim());
    if (!first) return $_('assistant.current_chat', { default: 'Current chat' });
    const t = first.text.trim().replace(/\s+/g, ' ');
    return t.length > 60 ? `${t.slice(0, 57)}…` : t;
  }

  /** Keep the active thread visible in history, including a fresh empty New chat. */
  function mergeCurrentConversation(list) {
    if (messages.length === 0 && !conversationId) return list;
    const id = conversationId || '__current__';
    const entry = {
      conversation_id: id,
      title: messages.length ? titleFromMessages(messages) : null,
      persona: selectedAssistant?.id || 'ashoka',
      updated_at: new Date().toISOString(),
      message_count: messages.length,
    };
    const idx = list.findIndex((c) => c.conversation_id === id);
    if (idx >= 0) {
      const next = [...list];
      next[idx] = { ...next[idx], ...entry };
      return next;
    }
    return [entry, ...list];
  }

  function upsertConversationInList(forId = conversationId, msgCount = messages.length, title = null) {
    if (!forId || !userPrincipal) return;
    let resolvedTitle = title;
    if (resolvedTitle == null) {
      const titleSource =
        forId === conversationId
          ? messages
          : conversations.find((c) => c.conversation_id === forId)?.title || '';
      resolvedTitle =
        typeof titleSource === 'string' ? titleSource : titleFromMessages(titleSource);
    }
    const entry = {
      conversation_id: forId,
      title: resolvedTitle,
      persona: selectedAssistant?.id || 'ashoka',
      updated_at: new Date().toISOString(),
      message_count: msgCount,
    };
    const idx = conversations.findIndex((c) => c.conversation_id === forId);
    if (idx >= 0) {
      conversations = conversations.map((c, i) => (i === idx ? { ...c, ...entry } : c));
    } else {
      conversations = [entry, ...conversations];
    }
  }

  $: displayConversations = mergeCurrentConversation(conversations);

  function persistOpen(value) {
    try {
      localStorage.setItem(OPEN_KEY, JSON.stringify(!!value));
    } catch (e) {
      /* private mode */
    }
  }

  function persistDocked(value) {
    try {
      localStorage.setItem(DOCKED_KEY, JSON.stringify(!!value));
    } catch (e) {
      /* private mode */
    }
  }

  function setOpen(value) {
    open = !!value;
    persistOpen(open);
    if (open && isRegistryHome()) {
      setDocked(true);
    }
    syncChrome();
    if (open) {
      void refreshAuth().then(() => {
        if (userPrincipal) void refreshConversations();
      });
    }
  }

  function setDocked(value) {
    docked = !!value;
    persistDocked(docked);
    syncChrome();
  }

  function toggleDock() {
    setDocked(!docked);
  }

  function isRegistryHome() {
    return ($page?.url?.pathname || '/') === '/';
  }

  function openSettings() {
    goto('/assistant/settings');
  }

  $: showFab = !(docked && open) && $page.url.pathname !== '/';

  function applyPrefs() {
    const prefs = loadPrefs();
    showSuggestions = prefs.showSuggestions;
    sharePageContext = prefs.sharePageContext;
    defaultAssistantId = prefs.defaultAssistant || '';
    if (defaultAssistantId && availableAssistants.length > 0) {
      const match = availableAssistants.find((a) => a.id === defaultAssistantId);
      if (match) selectedAssistant = match;
    }
  }

  async function ensureRealmContext(slug) {
    const key = (slug || '').trim().toLowerCase();
    if (!key) {
      contextRealmId = null;
      frontendCanisterId = null;
      return;
    }
    const cached = realmCache[key];
    if (cached) {
      contextRealmId = cached.backend;
      frontendCanisterId = cached.frontend;
      return;
    }
    try {
      const { resolveSlug } = await import('$lib/slug-resolver.js');
      const data = await resolveSlug(key);
      const backend = data.backend_canister_id || null;
      const frontend = data.frontend_canister_id || null;
      if (backend) realmCache[key] = { backend, frontend: frontend || '' };
      if (portalSlug === slug) {
        contextRealmId = backend;
        frontendCanisterId = frontend;
      }
    } catch (e) {
      console.warn('[RegistryAssistant] resolveSlug failed:', e);
      if (portalSlug === slug) {
        contextRealmId = null;
        frontendCanisterId = null;
      }
    }
  }

  function syncPortalRoute(pathname) {
    const match = (pathname || '').match(/^\/r\/([^/]+)(\/.*)?$/);
    const nextSlug = match ? match[1] : null;
    inRealmPath = match ? match[2] || '/' : '/';
    if (nextSlug === portalSlug) return;
    portalSlug = nextSlug;
    if (nextSlug) {
      void ensureRealmContext(nextSlug);
    } else {
      contextRealmId = null;
      frontendCanisterId = null;
    }
  }

  function extensionIdFromPath(path) {
    const m = (path || '').match(/^\/extensions\/([^/]+)/);
    return m ? m[1] : null;
  }

  function buildPageContext() {
    if (!sharePageContext || !portalSlug) return null;
    const extensionId = extensionIdFromPath(inRealmPath);
    const title = extensionId ? `${portalSlug} · ${extensionId}` : `Realm ${portalSlug}`;
    const parts = [`slug=${portalSlug}`];
    if (frontendCanisterId) parts.push(`frontend=${frontendCanisterId}`);
    if (documentFocus?.label) parts.push(`focus=${documentFocus.label}`);
    else if (documentFocus?.uri) parts.push(`focus=${documentFocus.uri}`);
    /** @type {Record<string, string>} */
    const ctx = {
      pathname: inRealmPath,
      title,
      description: parts.join('; '),
    };
    if (extensionId) ctx.extensionId = extensionId;
    return ctx;
  }

  async function loadAssistants() {
    try {
      availableAssistants = await fetchAssistants();
      if (availableAssistants.length > 0 && !selectedAssistant) {
        const match = defaultAssistantId
          ? availableAssistants.find((a) => a.id === defaultAssistantId)
          : null;
        selectedAssistant = match || availableAssistants[0];
      }
    } catch (e) {
      console.warn('[RegistryAssistant] fetchAssistants failed:', e);
    }
  }

  async function loadSuggestions() {
    if (!showSuggestions || isLoadingSuggestions) return;
    isLoadingSuggestions = true;
    try {
      suggestions = await fetchSuggestions({
        userPrincipal,
        contextRealm: contextRealmId || '',
        persona: selectedAssistant?.id || 'ashoka',
      });
    } catch (e) {
      console.warn('[RegistryAssistant] fetchSuggestions failed:', e);
    } finally {
      isLoadingSuggestions = false;
    }
  }

  async function startNewConversation() {
    detachUiFromSend();
    messages = [];
    error = '';
    suggestions = [];
    await refreshAuth();
    if (userPrincipal) {
      conversationId = newConversationId();
      persistLastConversation(conversationId);
      upsertConversationInList(conversationId, 0, null);
    } else {
      conversationId = null;
      persistLastConversation(null);
    }
    await loadSuggestions();
  }

  async function allocateConversationId() {
    if (!userPrincipal) return null;
    if (conversationId) return conversationId;
    conversationId = newConversationId();
    persistLastConversation(conversationId);
    return conversationId;
  }

  async function ensureConversation() {
    if (!userPrincipal) return;
    if (!conversationId) await allocateConversationId();
  }

  function displayTitle(conv) {
    const t = (conv?.title || '').trim();
    if (t && !['new conversation', 'new chat', 'untitled', 'current chat'].includes(t.toLowerCase())) {
      return t;
    }
    if (
      messages.length &&
      (conversationId === conv.conversation_id || conv.conversation_id === '__current__')
    ) {
      return titleFromMessages(messages);
    }
    if (
      !messages.length &&
      (conversationId === conv.conversation_id || conv.conversation_id === '__current__') &&
      !(conv.message_count || 0)
    ) {
      return $_('assistant.new_chat', { default: 'New chat' });
    }
    return $_('assistant.untitled', { default: 'Untitled' });
  }

  async function refreshAuth() {
    try {
      const { isAuthenticated, getPrincipal } = await import('$lib/auth.js');
      const wasPrincipal = userPrincipal;
      if (await isAuthenticated()) {
        const p = await getPrincipal();
        userPrincipal = p ? p.toText() : '';
      } else {
        userPrincipal = '';
      }
      if (userPrincipal && !wasPrincipal && messages.length > 0 && !conversationId) {
        await ensureConversation();
      }
    } catch (e) {
      // Anonymous use is allowed (no persistence); ignore auth errors.
    }
  }

  async function openHistory() {
    showHistory = !showHistory;
    persistShowHistory(showHistory);
    if (!showHistory) return;
    await refreshAuth();
    if (!userPrincipal) {
      conversations = [];
      historyError = '';
      return;
    }
    await refreshConversations();
  }

  async function loadConversation(conv) {
    if (conv.conversation_id === '__current__') return;
    if (conversationId === conv.conversation_id && messages.length > 0 && !isPending(conv.conversation_id))
      return;
    detachUiFromSend();
    messages = [];
    conversationId = conv.conversation_id;
    persistLastConversation(conv.conversation_id);
    error = '';
    const match = availableAssistants.find((a) => a.id === conv.persona);
    if (match) selectedAssistant = match;
    try {
      messages = await loadConversationMessages(conv.conversation_id);
      await tick();
      await scrollToBottom();
    } catch (e) {
      console.warn('[RegistryAssistant] loadConversationMessages failed:', e);
      error = $_('assistant.history_load_failed', { default: 'Could not load this conversation.' });
    }
  }

  async function removeConversation(id, e) {
    e.stopPropagation();
    if (id === '__current__') return;
    try {
      await deleteConversation(id);
      conversations = conversations.filter((c) => c.conversation_id !== id);
      if (conversationId === id) {
        messages = [];
        conversationId = null;
        persistLastConversation(null);
      }
    } catch (err) {
      console.warn('[RegistryAssistant] deleteConversation failed:', err);
    }
  }

  function selectAssistant(assistant) {
    selectedAssistant = assistant;
    void loadSuggestions();
  }

  function handleSuggestionClick(text) {
    newMessage = text;
    void send();
  }

  function copyText(text, index) {
    const markCopied = () => {
      copiedIndex = index;
      setTimeout(() => {
        copiedIndex = null;
      }, 1500);
    };
    const fallback = () => {
      const ta = document.createElement('textarea');
      ta.value = text;
      ta.style.position = 'fixed';
      ta.style.left = '-9999px';
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
        markCopied();
      } catch (e) {
        /* ignore */
      }
      document.body.removeChild(ta);
    };
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(markCopied).catch(fallback);
    } else {
      fallback();
    }
  }

  function onResizeStart(event) {
    if (typeof window !== 'undefined' && window.innerWidth < 768) return;
    event.preventDefault();
    event.stopPropagation();
    isResizing = true;
    syncChrome();
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    const handle = event.currentTarget;
    handle.setPointerCapture(event.pointerId);
    const startX = event.clientX;
    const startWidth = panelWidth;

    const onMove = (e) => {
      const delta = startX - e.clientX;
      panelWidth = clampPanelWidth(startWidth + delta);
      syncChrome();
    };

    const onUp = (e) => {
      isResizing = false;
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
      panelWidth = clampPanelWidth(panelWidth);
      savePanelWidth(panelWidth);
      syncChrome();
      handle.releasePointerCapture(e.pointerId);
      handle.removeEventListener('pointermove', onMove);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
    };

    handle.addEventListener('pointermove', onMove);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  }

  onMount(async () => {
    try {
      const savedDocked = localStorage.getItem(DOCKED_KEY);
      if (savedDocked !== null) docked = JSON.parse(savedDocked) === true;
      const savedOpen = localStorage.getItem(OPEN_KEY);
      if (savedOpen !== null) open = JSON.parse(savedOpen) === true;
      showHistory = readShowHistory(false);
    } catch (e) {
      /* private mode */
    }
    panelWidth = clampPanelWidth(loadPanelWidth(defaultPanelWidth()));
    if (open && (get(page).url.pathname || '/') === '/') {
      setDocked(true);
    }
    applyPrefs();
    syncChrome();

    unsubPage = page.subscribe(($p) => {
      syncPortalRoute($p.url.pathname || '');
      if (($p.url.pathname || '/') === '/' && open) {
        setDocked(true);
      }
    });
    unsubFocus = portalDocumentFocus.subscribe((focus) => {
      documentFocus = focus;
    });
    unsubOpenRequest = assistantOpenRequest.subscribe((n) => {
      if (n > 0) setOpen(true);
    });
    unsubToggleRequest = assistantToggleRequest.subscribe((n) => {
      if (n > 0) setOpen(!open);
    });
    unsubCloseRequest = assistantCloseRequest.subscribe((n) => {
      if (n > 0) setOpen(false);
    });

    await refreshAuth();

    await loadAssistants();
    applyPrefs();
    if (showSuggestions) await loadSuggestions();
    if (userPrincipal) {
      await refreshConversations();
      // Restore last thread only when reopening the panel, not after explicit New chat.
      const lastId = readLastConversation();
      if (lastId && open && messages.length === 0 && !conversationId) {
        const lastConv = conversations.find((c) => c.conversation_id === lastId);
        if (lastConv) await loadConversation(lastConv);
      }
    } else if (showHistory) {
      conversations = [];
    }

    // Re-read prefs + auth when returning from settings / login (visibilitychange / focus).
    const onFocus = () => {
      applyPrefs();
      void refreshAuth().then(() => {
        if (userPrincipal) void refreshConversations();
      });
      if (showSuggestions && suggestions.length === 0) void loadSuggestions();
    };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onFocus);
    unsubPrefsFocus = () => {
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onFocus);
    };
  });

  onDestroy(() => {
    unsubPage?.();
    unsubFocus?.();
    unsubOpenRequest?.();
    unsubToggleRequest?.();
    unsubCloseRequest?.();
    unsubPrefsFocus?.();
    document.body.style.userSelect = '';
    document.body.style.cursor = '';
  });

  async function scrollToBottom() {
    await tick();
    if (messagesContainer) messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  function appendAssistantToView(text) {
    if (!isViewingConversation(conversationId)) return;
    const last = messages[messages.length - 1];
    if (!last || last.isUser) {
      messages = [...messages, { text, isUser: false }];
    } else {
      messages = messages.map((m, i) => (i === messages.length - 1 ? { ...m, text } : m));
    }
    void scrollToBottom();
  }

  /**
   * @param {{
   *   sendConversationId: string | null,
   *   question: string,
   *   principal: string,
   *   persona: string,
   *   ctxRealm: string,
   *   pageContext: Record<string, string> | null,
   *   focus: { uri?: string, label?: string, source?: string } | null,
   * }} opts
   */
  async function runBackgroundSend(opts) {
    const { sendConversationId, question, principal, persona, ctxRealm, pageContext, focus } = opts;

    const pendingKey = sendConversationId || '__anonymous__';
    markPending(pendingKey);
    const viewing = () =>
      sendConversationId ? isViewingConversation(sendConversationId) : !conversationId;

    if (viewing() && !loadingStatus) {
      loadingStatus = get(_)('assistant.thinking', { default: 'Thinking…' });
    }

    /** @type {ReturnType<typeof setTimeout> | null} */
    let timeoutId = null;

    try {
      /** @type {Record<string, unknown>} */
      const payload = {
        question,
        user_principal: principal,
        stream: true,
        verbosity: 1,
        persona,
        network: geisterNetwork(),
      };
      if (sendConversationId) payload.conversation_id = sendConversationId;

      if (ctxRealm) {
        payload.context_realm = ctxRealm;
        payload.realm_principal = ctxRealm;
        if (pageContext) payload.page_context = pageContext;
      }

      if (focus?.uri) payload.focus = focus;

      const timeoutController = new AbortController();
      timeoutId = setTimeout(() => timeoutController.abort(), CHAT_REQUEST_TIMEOUT_MS);

      const response = await fetch(API_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
        body: JSON.stringify(payload),
        signal: timeoutController.signal,
      });

      if (!response.ok) {
        let detail = '';
        try {
          const body = await response.json();
          detail = typeof body?.error === 'string' ? body.error : '';
        } catch (e) {
          /* ignore */
        }
        if (detail) {
          throw Object.assign(new Error(detail), { httpStatus: response.status });
        }
        throw Object.assign(new Error(`HTTP error! Status: ${response.status}`), {
          httpStatus: response.status,
        });
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('Response body is not readable');
      const decoder = new TextDecoder();
      const state = { text: '' };

      try {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          for (const line of chunk.split('\n')) {
            if (line.startsWith('data: ')) {
              const pl = line.slice(6);
              if (pl === '[DONE]') continue;
              try {
                const parsed = JSON.parse(pl);
                const eventType = typeof parsed.type === 'string' ? parsed.type : parsed.text ? 'text' : '';
                const piece = typeof parsed.text === 'string' ? parsed.text : '';
                if (eventType === 'status' && piece && viewing()) {
                  loadingStatus = piece;
                  continue;
                }
                if (eventType === 'thinking') continue;
                if (piece) {
                  state.text += piece;
                  if (viewing()) {
                    loadingStatus = '';
                    appendAssistantToView(state.text);
                  }
                }
              } catch (e) {
                state.text += pl;
                if (viewing()) appendAssistantToView(state.text);
              }
            } else if (line.trim() && !line.startsWith(':')) {
              state.text += line;
              if (viewing()) appendAssistantToView(state.text);
            }
          }
        }
      } finally {
        reader.releaseLock();
      }

      if (viewing()) {
        if (!state.text.trim()) {
          appendAssistantToView($_('assistant.no_response', { default: 'No response from the assistant.' }));
        } else if (isLlmBackendError(state.text)) {
          error = classifyChatError(new Error(state.text), 503);
        }
        await loadSuggestions();
      }

      if (principal) {
        upsertConversationInList(sendConversationId, state.text.trim() ? 2 : 1);
        if (showHistory) await refreshConversations();
      }
    } catch (err) {
      if (err?.name === 'AbortError') return;
      console.error('Registry assistant error:', err);
      if (viewing()) {
        error = classifyChatError(err, err?.httpStatus);
        if (messages.length && !messages[messages.length - 1].isUser && !messages[messages.length - 1].text) {
          messages = messages.slice(0, -1);
        }
      }
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
      clearPending(pendingKey);
      if (viewing()) loadingStatus = '';
    }
  }

  async function send() {
    const question = newMessage.trim();
    if (!question) return;
    error = '';
    await refreshAuth();
    await ensureConversation();

    if (conversationId && isPending(conversationId)) return;

    messages = [...messages, { text: question, isUser: true }];
    newMessage = '';
    suggestions = [];

    const sendConversationId = conversationId;
    const pendingKey = sendConversationId || '__anonymous__';
    markPending(pendingKey);
    loadingStatus = get(_)('assistant.thinking', { default: 'Thinking…' });
    void scrollToBottom();

    const principal = userPrincipal;
    const persona = selectedAssistant?.id || 'ashoka';
    const ctxRealm = contextRealmId || '';
    const pageContext = buildPageContext();
    const focus = documentFocus?.uri
      ? { uri: documentFocus.uri, label: documentFocus.label, source: documentFocus.source }
      : null;

    if (sendConversationId && principal) {
      await touchConversation({
        conversationId: sendConversationId,
        userPrincipal: principal,
        question,
        persona,
        contextRealm: ctxRealm,
      });
      upsertConversationInList(sendConversationId, messages.length);
    }

    void runBackgroundSend({
      sendConversationId,
      question,
      principal,
      persona,
      ctxRealm,
      pageContext,
      focus,
    });
  }

  function onKeydown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  }
</script>

{#if showFab}
  <button
    class="assistant-fab"
    class:open
    on:click={() => setOpen(!open)}
    aria-label={$_('assistant.toggle', { default: 'AI Assistant' })}
    title={$_('assistant.toggle', { default: 'AI Assistant' })}
  >
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
      <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"></path>
      <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"></path>
      <path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"></path>
      <path d="M17.599 6.5a3 3 0 0 0 .399-1.375"></path>
      <path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"></path>
      <path d="M3.023 10.125A4 4 0 0 0 3 11"></path>
      <path d="M20.977 10.125A4 4 0 0 1 21 11"></path>
      <path d="M12 21v-3"></path>
      <path d="M15.6 17.5a4 4 0 0 1-7.2 0"></path>
    </svg>
  </button>
{/if}

{#if docked || open}
  <section
    class="assistant-panel"
    class:docked
    class:open
    class:resizing={isResizing}
    style="width: {docked ? panelWidth + 'px' : 'min(' + panelWidth + 'px, calc(100vw - 48px))'}"
    aria-hidden={!open}
    aria-label={$_('assistant.title', { default: 'Realms AI Assistant' })}
  >
    {#if docked}
      <button
        type="button"
        class="resize-handle"
        on:pointerdown|stopPropagation={onResizeStart}
        aria-label={$_('assistant.resize', { default: 'Resize panel' })}
      ></button>
    {/if}

    <header class="assistant-header">
      <span class="assistant-title">{$_('assistant.title', { default: 'Realms AI Assistant' })}</span>
      <div class="assistant-header-actions">
        <button
          class="assistant-icon-btn"
          on:click={openSettings}
          aria-label={$_('assistant.settings', { default: 'Settings' })}
          title={$_('assistant.settings', { default: 'Settings' })}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="3" />
            <path
              d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"
            />
          </svg>
        </button>
        <button
          class="assistant-icon-btn"
          on:click={toggleDock}
          aria-label={docked
            ? $_('assistant.undock', { default: 'Undock' })
            : $_('assistant.dock', { default: 'Dock to side' })}
          title={docked
            ? $_('assistant.undock', { default: 'Undock' })
            : $_('assistant.dock', { default: 'Dock to side' })}
        >
          {#if docked}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="4" y="6" width="16" height="12" rx="2" />
              <path d="M4 10h16" />
            </svg>
          {:else}
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <rect x="3" y="4" width="18" height="16" rx="2" />
              <path d="M15 4v16" />
            </svg>
          {/if}
        </button>
        <button
          class="assistant-icon-btn"
          on:click={() => setOpen(false)}
          aria-label={$_('assistant.close', { default: 'Close' })}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
            ><path d="M18 6L6 18M6 6l12 12" /></svg
          >
        </button>
      </div>
    </header>

    <div class="chat-toolbar">
      <button
        class="toolbar-btn"
        on:click={startNewConversation}
        title={$_('assistant.new_chat', { default: 'New chat' })}
      >
        <svg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"
          ><path d="M10 4v12M4 10h12" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" /></svg
        >
        <span>{$_('assistant.new_chat', { default: 'New chat' })}</span>
      </button>
      <button
        class="toolbar-btn"
        class:active={showHistory}
        on:click={openHistory}
        title={$_('assistant.history', { default: 'History' })}
      >
        <svg viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg"
          ><circle cx="10" cy="10" r="7.5" stroke="currentColor" stroke-width="1.5" /><path
            d="M10 6.5V10l2.5 2"
            stroke="currentColor"
            stroke-width="1.5"
            stroke-linecap="round"
            stroke-linejoin="round"
          /></svg
        >
        <span>{$_('assistant.history', { default: 'History' })}</span>
      </button>
    </div>

    {#if availableAssistants.length > 1}
      <div class="assistant-selector">
        {#each availableAssistants as assistant (assistant.id)}
          <button
            class="assistant-btn"
            class:active={selectedAssistant?.id === assistant.id}
            on:click={() => selectAssistant(assistant)}
            title={assistant.description || assistant.name}
          >
            {#if assistant.emoji}<span class="assistant-emoji">{assistant.emoji}</span>{/if}
            <span class="assistant-name">{assistant.name}</span>
          </button>
        {/each}
      </div>
    {/if}

    <div class="assistant-body" class:with-history={showHistory}>
      {#if showHistory}
        <aside class="history-sidebar" aria-label={$_('assistant.history', { default: 'History' })}>
          {#if isLoadingHistory}
            <div class="history-loading">{$_('assistant.history_loading', { default: 'Loading conversations…' })}</div>
          {:else if !userPrincipal && messages.length === 0}
            <div class="history-empty">
              {$_('assistant.history_sign_in', {
                default: 'Sign in with Internet Identity to save and browse conversation history.',
              })}
            </div>
          {:else if historyError}
            <div class="history-empty history-error">{historyError}</div>
          {:else if displayConversations.length === 0}
            <div class="history-empty">{$_('assistant.history_empty', { default: 'No past conversations yet. Start chatting!' })}</div>
          {:else}
            {#if !userPrincipal && messages.length > 0}
              <div class="history-empty history-hint">
                {$_('assistant.history_sign_in_save', {
                  default: 'Sign in to save this conversation to your history.',
                })}
              </div>
            {/if}
            {#each displayConversations as conv (conv.conversation_id)}
              <div
                class="history-item"
                class:active={conversationId === conv.conversation_id || (conv.conversation_id === '__current__' && !conversationId)}
                on:click={() => loadConversation(conv)}
                on:keydown={(e) => e.key === 'Enter' && loadConversation(conv)}
                role="button"
                tabindex="0"
              >
                <div class="history-item-body">
                  <div class="history-title">{displayTitle(conv)}</div>
                  <div class="history-meta">
                    {#if isPending(conv.conversation_id)}
                      {$_('assistant.thinking', { default: 'Thinking…' })}
                    {:else}
                      {formatConversationDate(conv.updated_at)} · {conv.message_count || 0}
                      {$_('assistant.messages_abbr', { default: 'msgs' })}
                    {/if}
                  </div>
                </div>
                <button
                  class="history-delete"
                  on:click={(e) => removeConversation(conv.conversation_id, e)}
                  title={$_('assistant.delete', { default: 'Delete' })}
                  disabled={conv.conversation_id === '__current__'}
                >
                  <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg"
                    ><path
                      d="M3 4h10M6 4V3h4v1M5 4v8h6V4H5z"
                      stroke="currentColor"
                      stroke-width="1.2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    /></svg
                  >
                </button>
              </div>
            {/each}
          {/if}
        </aside>
      {/if}

      <div class="assistant-main">
    <div class="assistant-messages" use:scrollRegion>
      {#if messages.length === 0}
        <div class="assistant-empty">
          {$_('assistant.empty', {
            default:
              'Ask me anything about the realms in the registry — which to join, how to create one, or how Realms works.',
          })}
        </div>
      {/if}
      {#each messages as m, i (i)}
        <div class="assistant-msg" class:user={m.isUser}>
          {#if m.isUser}
            <div class="msg-wrap user-wrap">
              <button
                class="copy-btn"
                on:click={() => copyText(m.text, i)}
                title={copiedIndex === i
                  ? $_('assistant.copied', { default: 'Copied' })
                  : $_('assistant.copy', { default: 'Copy' })}
              >
                {#if copiedIndex === i}
                  <svg viewBox="0 0 16 16" fill="none"
                    ><path
                      d="M3 8l3.5 3.5L13 4.5"
                      stroke="currentColor"
                      stroke-width="1.6"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    /></svg
                  >
                {:else}
                  <svg viewBox="0 0 16 16" fill="none"
                    ><rect x="5" y="5" width="9" height="9" rx="1.5" stroke="currentColor" stroke-width="1.3" /><path
                      d="M11 5V3.5A1.5 1.5 0 0 0 9.5 2h-6A1.5 1.5 0 0 0 2 3.5v6A1.5 1.5 0 0 0 3.5 11H5"
                      stroke="currentColor"
                      stroke-width="1.3"
                      stroke-linecap="round"
                    /></svg
                  >
                {/if}
              </button>
              <div class="assistant-bubble">{m.text}</div>
            </div>
          {:else}
            <div class="msg-wrap assistant-wrap">
              <div class="assistant-bubble markdown-content">
                {@html renderMarkdown(m.text)}
              </div>
              <button
                class="copy-btn copy-btn--assistant"
                on:click={() => copyText(m.text, i)}
                title={copiedIndex === i
                  ? $_('assistant.copied', { default: 'Copied' })
                  : $_('assistant.copy', { default: 'Copy' })}
              >
                {#if copiedIndex === i}
                  <svg viewBox="0 0 16 16" fill="none"
                    ><path
                      d="M3 8l3.5 3.5L13 4.5"
                      stroke="currentColor"
                      stroke-width="1.6"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    /></svg
                  >
                {:else}
                  <svg viewBox="0 0 16 16" fill="none"
                    ><rect x="5" y="5" width="9" height="9" rx="1.5" stroke="currentColor" stroke-width="1.3" /><path
                      d="M11 5V3.5A1.5 1.5 0 0 0 9.5 2h-6A1.5 1.5 0 0 0 2 3.5v6A1.5 1.5 0 0 0 3.5 11H5"
                      stroke="currentColor"
                      stroke-width="1.3"
                      stroke-linecap="round"
                    /></svg
                  >
                {/if}
              </button>
            </div>
          {/if}
        </div>
      {/each}
      {#if awaitingReply}
        <div class="assistant-msg">
          <div class="msg-wrap assistant-wrap">
            <div class="assistant-bubble typing-indicator" aria-live="polite" aria-busy="true">
              <span class="typing-label">
                {loadingStatus || $_('assistant.thinking', { default: 'Thinking…' })}
              </span>
              <span class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></span>
            </div>
          </div>
        </div>
      {/if}
      {#if error}
        <div class="assistant-error">
          <span>{error}</span>
          <button class="error-dismiss" on:click={() => (error = '')} title={$_('assistant.dismiss', { default: 'Dismiss' })}
            >&times;</button
          >
        </div>
      {/if}
    </div>

      <div class="assistant-input" data-tour="assistant-compose">
        {#if showSuggestions && (suggestions.length > 0 || isLoadingSuggestions)}
          <div class="suggestions">
            {#if isLoadingSuggestions}
              <span class="suggestion-loading"
                >{$_('assistant.suggestions_loading', { default: 'Loading suggestions…' })}</span
              >
            {:else}
              {#each suggestions as suggestion (suggestion)}
                <button class="suggestion-chip" on:click={() => handleSuggestionClick(suggestion)}>
                  {suggestion}
                </button>
              {/each}
            {/if}
          </div>
        {/if}
        <div class="input-row">
          <textarea
            bind:value={newMessage}
            on:keydown={onKeydown}
            rows="1"
            placeholder={$_('assistant.placeholder', { default: 'Type your message…' })}
            disabled={viewingPending}
          ></textarea>
          <button class="assistant-send" on:click={send} disabled={viewingPending || !newMessage.trim()}>
            {$_('assistant.send', { default: 'Send' })}
          </button>
        </div>
      </div>
      </div>
    </div>
  </section>
{/if}

<style>
  .assistant-fab {
    position: fixed;
    bottom: 24px;
    right: 24px;
    width: 52px;
    height: 52px;
    border-radius: 50%;
    background: #111;
    color: #fff;
    border: none;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: pointer;
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.25);
    z-index: 1000;
    transition: transform 0.15s ease;
  }
  .assistant-fab:hover {
    transform: scale(1.05);
  }
  .assistant-fab.open {
    background: #333;
  }

  .assistant-panel {
    position: fixed;
    bottom: 88px;
    right: 24px;
    height: min(560px, calc(100vh - 130px));
    background: #fff;
    border: 1px solid #e5e5e5;
    border-radius: 14px;
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.18);
    display: flex;
    flex-direction: column;
    overflow: hidden;
    z-index: 1000;
  }

  .assistant-panel.docked {
    top: 0;
    right: 0;
    bottom: 0;
    height: 100vh;
    border-radius: 0;
    border: none;
    border-left: 1px solid #e5e5e5;
    box-shadow: -4px 0 24px rgba(0, 0, 0, 0.08);
    z-index: 1100;
    transform: translateX(100%);
    transition: transform 0.25s ease;
    pointer-events: none;
  }

  .assistant-panel.docked.open {
    transform: translateX(0);
    pointer-events: auto;
  }

  .assistant-panel.resizing {
    user-select: none;
  }

  .assistant-panel.docked.resizing {
    transition: none;
  }

  .assistant-body {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }
  .assistant-body.with-history {
    flex-direction: row;
  }
  .assistant-main {
    flex: 1;
    min-width: 0;
    min-height: 0;
    display: flex;
    flex-direction: column;
  }

  .history-sidebar {
    flex: 0 0 220px;
    min-width: 180px;
    max-width: 45%;
    border-right: 1px solid #eee;
    overflow-y: auto;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
    background: #fafafa;
  }

  .resize-handle {
    position: absolute;
    left: -4px;
    top: 0;
    bottom: 0;
    width: 12px;
    cursor: col-resize;
    z-index: 3;
    background: transparent;
    border: none;
    padding: 0;
    margin: 0;
    touch-action: none;
  }
  .resize-handle:hover,
  .assistant-panel.resizing .resize-handle {
    background: rgba(0, 0, 0, 0.06);
  }

  @media (max-width: 767px) {
    .assistant-panel.docked {
      width: 100% !important;
    }
    .resize-handle {
      display: none;
    }
  }

  .assistant-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 12px 14px;
    border-bottom: 1px solid #eee;
    flex-shrink: 0;
  }
  .assistant-title {
    font-weight: 600;
    font-size: 0.95rem;
    color: #111;
  }
  .assistant-header-actions {
    display: flex;
    align-items: center;
    gap: 2px;
  }
  .assistant-icon-btn {
    background: none;
    border: none;
    cursor: pointer;
    color: #666;
    padding: 4px;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .assistant-icon-btn:hover {
    color: #111;
  }

  .chat-toolbar {
    display: flex;
    gap: 6px;
    padding: 6px 14px;
    border-bottom: 1px solid #eee;
    flex-shrink: 0;
  }
  .toolbar-btn {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 5px 10px;
    border-radius: 8px;
    border: 1px solid #e5e5e5;
    background: #f9f9f9;
    color: #555;
    font-size: 13px;
    cursor: pointer;
  }
  .toolbar-btn svg {
    width: 15px;
    height: 15px;
    flex-shrink: 0;
  }
  .toolbar-btn:hover {
    background: #f0f0f0;
    color: #111;
  }
  .toolbar-btn.active {
    background: #111;
    border-color: #111;
    color: #fff;
  }

  .assistant-selector {
    display: flex;
    gap: 6px;
    padding: 8px 14px;
    border-bottom: 1px solid #eee;
    flex-shrink: 0;
    overflow-x: auto;
  }
  .assistant-btn {
    display: flex;
    align-items: center;
    gap: 5px;
    padding: 5px 10px;
    border-radius: 8px;
    border: 1px solid #e5e5e5;
    background: #fff;
    cursor: pointer;
    white-space: nowrap;
    font-size: 13px;
    color: #444;
  }
  .assistant-btn:hover {
    background: #f5f5f5;
  }
  .assistant-btn.active {
    border-color: #111;
    background: #111;
    color: #fff;
  }
  .assistant-emoji {
    font-size: 14px;
  }
  .assistant-name {
    font-weight: 500;
  }

  .history-panel {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: 8px 14px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .history-loading,
  .history-empty {
    padding: 24px 8px;
    text-align: center;
    color: #999;
    font-size: 13px;
  }
  .history-error {
    color: #b42318;
  }
  .history-hint {
    padding: 12px 8px;
    font-size: 12px;
    color: #666;
    text-align: left;
    border-bottom: 1px solid #eee;
    margin-bottom: 4px;
  }
  .history-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 10px 12px;
    border-radius: 10px;
    border: 1px solid #f0f0f0;
    background: #fff;
    cursor: pointer;
  }
  .history-item:hover {
    background: #f0f0f0;
    border-color: #ddd;
  }
  .history-item.active {
    background: #111;
    border-color: #111;
  }
  .history-item.active .history-title {
    color: #fff;
  }
  .history-item.active .history-meta {
    color: rgba(255, 255, 255, 0.7);
  }
  .history-item.active .history-delete {
    color: rgba(255, 255, 255, 0.55);
  }
  .history-item.active .history-delete:hover {
    color: #fff;
    background: rgba(255, 255, 255, 0.12);
  }
  .history-item-body {
    flex: 1;
    min-width: 0;
  }
  .history-title {
    font-size: 13px;
    font-weight: 500;
    color: #222;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .history-meta {
    font-size: 11px;
    color: #999;
    margin-top: 2px;
  }
  .history-delete {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 26px;
    height: 26px;
    border: none;
    background: transparent;
    color: #ccc;
    cursor: pointer;
    border-radius: 6px;
    padding: 4px;
  }
  .history-delete svg {
    width: 14px;
    height: 14px;
  }
  .history-delete:hover {
    color: #b00020;
    background: #fef2f2;
  }

  .assistant-messages {
    flex: 1;
    overflow-y: auto;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 0;
  }
  .assistant-empty {
    color: #888;
    font-size: 0.88rem;
    line-height: 1.5;
  }

  .assistant-msg {
    display: flex;
  }
  .assistant-msg.user {
    justify-content: flex-end;
  }

  .msg-wrap {
    display: flex;
    max-width: 90%;
    gap: 4px;
  }
  .user-wrap {
    align-items: flex-end;
    flex-direction: row;
  }
  .assistant-wrap {
    flex-direction: column;
    align-items: flex-start;
    max-width: 95%;
  }

  .assistant-bubble {
    max-width: 100%;
    padding: 8px 12px;
    border-radius: 12px;
    font-size: 0.9rem;
    line-height: 1.45;
    word-break: break-word;
    background: #f3f3f3;
    color: #111;
  }
  .assistant-msg.user .assistant-bubble {
    background: #111;
    color: #fff;
    white-space: pre-wrap;
  }
  .assistant-msg:not(.user) .assistant-bubble {
    white-space: normal;
  }

  .markdown-content :global(h1),
  .markdown-content :global(h2),
  .markdown-content :global(h3) {
    margin-top: 10px;
    margin-bottom: 4px;
    font-weight: 600;
  }
  .markdown-content :global(h1) {
    font-size: 1.1rem;
  }
  .markdown-content :global(h2) {
    font-size: 1rem;
  }
  .markdown-content :global(h3) {
    font-size: 0.95rem;
  }
  .markdown-content :global(li) {
    margin-left: 1.1em;
  }
  .markdown-content :global(a) {
    color: #2563eb;
    text-decoration: underline;
  }
  .markdown-content :global(pre),
  .markdown-content :global(.md-pre) {
    background: #f0f0f0;
    padding: 8px;
    border-radius: 6px;
    overflow-x: auto;
    font-size: 0.82rem;
  }
  .markdown-content :global(code),
  .markdown-content :global(.md-code) {
    font-family: ui-monospace, monospace;
    font-size: 0.85em;
    background: rgba(0, 0, 0, 0.06);
    padding: 1px 4px;
    border-radius: 3px;
  }

  .copy-btn {
    flex-shrink: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border: none;
    background: transparent;
    color: #aaa;
    cursor: pointer;
    border-radius: 6px;
    padding: 3px;
  }
  .copy-btn:hover {
    color: #333;
    background: #f0f0f0;
  }
  .copy-btn svg {
    width: 14px;
    height: 14px;
  }
  .copy-btn--assistant {
    align-self: flex-start;
  }

  .typing-indicator {
    display: inline-flex;
    align-items: center;
    gap: 10px;
    min-height: 1.25rem;
    color: #666;
  }
  .typing-label {
    font-size: 0.85rem;
    font-style: italic;
  }
  .typing-dots {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .typing-dots span {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #999;
    animation: typing-bounce 1.2s ease-in-out infinite;
  }
  .typing-dots span:nth-child(2) {
    animation-delay: 0.15s;
  }
  .typing-dots span:nth-child(3) {
    animation-delay: 0.3s;
  }
  @keyframes typing-bounce {
    0%,
    80%,
    100% {
      transform: translateY(0);
      opacity: 0.45;
    }
    40% {
      transform: translateY(-4px);
      opacity: 1;
    }
  }
  .assistant-error {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    color: #b00020;
    font-size: 0.85rem;
    background: #fef2f2;
    border: 1px solid #fecaca;
    border-radius: 8px;
    padding: 8px 10px;
  }
  .error-dismiss {
    background: none;
    border: none;
    font-size: 16px;
    cursor: pointer;
    color: #b00020;
    padding: 0 4px;
    line-height: 1;
    opacity: 0.7;
  }
  .error-dismiss:hover {
    opacity: 1;
  }

  .assistant-input {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 10px;
    border-top: 1px solid #eee;
    flex-shrink: 0;
  }
  .suggestions {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    justify-content: center;
  }
  .suggestion-loading {
    font-size: 12px;
    color: #999;
  }
  .suggestion-chip {
    padding: 5px 12px;
    font-size: 12px;
    border-radius: 16px;
    border: 1px solid #e5e5e5;
    background: #f9f9f9;
    color: #555;
    cursor: pointer;
    white-space: nowrap;
  }
  .suggestion-chip:hover {
    background: #eee;
    color: #111;
  }
  .input-row {
    display: flex;
    gap: 8px;
  }
  .assistant-input textarea {
    flex: 1;
    resize: none;
    border: 1px solid #ddd;
    border-radius: 8px;
    padding: 8px 10px;
    font: inherit;
    font-size: 0.9rem;
    max-height: 120px;
  }
  .assistant-send {
    background: #111;
    color: #fff;
    border: none;
    border-radius: 8px;
    padding: 0 14px;
    font-size: 0.88rem;
    cursor: pointer;
  }
  .assistant-send:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
</style>
