// IC File Registry browser
// ----------------------------------------------------------------------
// Vanilla ES module. No build step. @dfinity/* loaded from esm.sh CDN.
//
// Talks to the file_registry canister at FILE_REGISTRY_CANISTER_ID over
// two channels:
//   - HTTP gateway (https://<id>.icp0.io/...) for read-only browsing
//     and downloads. No auth, fast.
//   - Authenticated agent (II login) for writes:
//       store_file, store_file_chunk, finalize_chunked_file,
//       finalize_chunked_file_step, delete_file, delete_namespace,
//       publish_namespace.
//
// Files larger than CHUNK_THRESHOLD are uploaded via store_file_chunk +
// finalize_chunked_file_step (browser-computed SHA-256 passed in to
// avoid the WASI Python runtime's per-message instruction budget).

// Dynamic imports (loaded in boot() so failures surface as a visible
// error in the UI instead of silently aborting the whole module).
let HttpAgent, Actor, AuthClient;

// ---- Configuration --------------------------------------------------

// Map each file_registry_frontend canister to its backend.
// Falls back to staging if the hosting canister isn't recognized,
// and can always be overridden with ?canister=<id> in the URL.
const _FR_BACKEND_MAP = {
  "2no7h-xqaaa-aaaad-qlxeq-cai": "uq2mu-kaaaa-aaaah-avqcq-cai",   // test
  "rbex3-xyaaa-aaaah-qumma-cai": "iebdk-kqaaa-aaaau-agoxq-cai",   // staging
  "7ja5c-dqaaa-aaaae-qj5oa-cai": "vi64l-3aaaa-aaaae-qj4va-cai",   // demo
};
const _hostCanister = location.hostname.replace(".icp0.io", "").replace(".ic0.app", "");
const DEFAULT_REGISTRY = _FR_BACKEND_MAP[_hostCanister] || "iebdk-kqaaa-aaaau-agoxq-cai";
const II_PROVIDER_URL = "https://identity.ic0.app";

const params = new URLSearchParams(location.search);
const REGISTRY_ID = params.get("canister") || DEFAULT_REGISTRY;
const isLocal = location.hostname.includes("localhost") || location.hostname.includes("127.0.0.1");
const HOST = isLocal ? `http://${REGISTRY_ID}.localhost:4943` : `https://${REGISTRY_ID}.icp0.io`;
const ROOT_HTTP = HOST; // file_registry's own HTTP gateway

// Single-shot uploads <= CHUNK_THRESHOLD bytes; chunked above.
const CHUNK_THRESHOLD = 400 * 1024; // 400 KB
const CHUNK_SIZE = 100 * 1024;      // 100 KB per chunk for chunked uploads

// ---- Candid IDL (file_registry, all methods are text -> text) -------

const idlFactory = ({ IDL }) => {
  const T = IDL.Text;
  return IDL.Service({
    list_namespaces: IDL.Func([], [T], ["query"]),
    list_files: IDL.Func([T], [T], ["query"]),
    get_file: IDL.Func([T], [T], ["query"]),
    get_file_chunk: IDL.Func([T], [T], ["query"]),
    get_stats: IDL.Func([], [T], ["query"]),
    get_acl: IDL.Func([], [T], ["query"]),
    store_file: IDL.Func([T], [T], []),
    store_file_chunk: IDL.Func([T], [T], []),
    finalize_chunked_file: IDL.Func([T], [T], []),
    finalize_chunked_file_step: IDL.Func([T], [T], []),
    delete_file: IDL.Func([T], [T], []),
    delete_namespace: IDL.Func([T], [T], []),
    publish_namespace: IDL.Func([T], [T], []),
    update_namespace: IDL.Func([T], [T], []),
    grant_publish: IDL.Func([T], [T], []),
    revoke_publish: IDL.Func([T], [T], []),
  });
};

// ---- Module state ---------------------------------------------------

let authClient = null;
let identity = null;        // anonymous until login
let agent = null;           // refreshed on login/logout
let actor = null;
let namespaces = [];        // [{namespace, file_count, total_bytes, owner, ...}]
let selectedNs = null;      // string | null
let filesInSelected = [];   // [{path, size, content_type, sha256, updated}]

// ---- Boot -----------------------------------------------------------

async function boot() {
  qs("#canisterPill").textContent = REGISTRY_ID;

  // Render namespaces from the HTTP gateway as soon as possible — this
  // path needs no auth and no @dfinity packages, so the user sees data
  // even if the agent libs are slow to load (or fail to load entirely).
  refresh().catch((e) => {
    console.error("initial refresh failed:", e);
    toast("Failed to load namespaces: " + e.message, "error");
  });

  // Load the agent / auth-client from a self-hosted, pre-bundled file
  // (see scripts/build-dfinity-bundle.sh). Avoids the CDN dedup hazard
  // where esm.sh resolves @dfinity/agent and @dfinity/auth-client to
  // mismatched transitive @dfinity/candid versions, which broke an
  // export named bufFromBufLike at runtime.
  try {
    const mod = await import("./dfinity.js");
    HttpAgent = mod.HttpAgent;
    Actor = mod.Actor;
    AuthClient = mod.AuthClient;
  } catch (e) {
    console.error("failed to load ./dfinity.js:", e);
    toast(
      "Could not load the @dfinity client libs (./dfinity.js). " +
        "Read-only browse will still work, but login/upload/delete are disabled. " +
        "Check the browser console for details.",
      "error"
    );
    qs("#loginBtn").disabled = true;
    qs("#loginBtn").classList.add("opacity-50", "cursor-not-allowed");
    qs("#loginBtn").title = "Auth libraries failed to load";
    wireReadOnlyHandlers();
    return;
  }

  authClient = await AuthClient.create({ idleOptions: { disableIdle: true } });
  identity = authClient.getIdentity();
  await rebuildAgent();
  if (await authClient.isAuthenticated()) renderLogin(true);

  qs("#loginBtn").addEventListener("click", login);
  qs("#logoutBtn").addEventListener("click", logout);
  qs("#newNsBtn").addEventListener("click", onNewNamespace);
  wireReadOnlyHandlers();
}

function wireReadOnlyHandlers() {
  qs("#refreshBtn").addEventListener("click", () => refresh());
  qs("#nsSearch").addEventListener("input", renderNamespaces);
}

async function rebuildAgent() {
  agent = await HttpAgent.create({ host: HOST, identity });
  if (isLocal) {
    try { await agent.fetchRootKey(); } catch {}
  }
  actor = Actor.createActor(idlFactory, { agent, canisterId: REGISTRY_ID });
}

// ---- Auth -----------------------------------------------------------

async function login() {
  await new Promise((resolve, reject) => {
    authClient.login({
      identityProvider: II_PROVIDER_URL,
      maxTimeToLive: BigInt(7 * 24 * 60 * 60 * 1_000_000_000),
      onSuccess: resolve,
      onError: reject,
    });
  });
  identity = authClient.getIdentity();
  await rebuildAgent();
  renderLogin(true);
  toast("Logged in as " + shortPrincipal(identity.getPrincipal().toText()), "success");
}

async function logout() {
  await authClient.logout();
  identity = authClient.getIdentity();
  await rebuildAgent();
  renderLogin(false);
  toast("Logged out", "info");
}

function renderLogin(authed) {
  if (authed) {
    qs("#loginBtn").classList.add("hidden");
    qs("#logoutBtn").classList.remove("hidden");
    const principal = identity.getPrincipal().toText();
    const pill = qs("#principalPill");
    pill.textContent = shortPrincipal(principal);
    pill.title = principal;
    pill.classList.remove("hidden");
  } else {
    qs("#loginBtn").classList.remove("hidden");
    qs("#logoutBtn").classList.add("hidden");
    qs("#principalPill").classList.add("hidden");
  }
}

// ---- Data fetch -----------------------------------------------------

async function refresh() {
  // Use HTTP gateway for the namespace list — fewer round-trips, cached.
  try {
    const res = await fetch(`${ROOT_HTTP}/`, { credentials: "omit" });
    namespaces = await res.json();
  } catch (e) {
    toast("Failed to load namespaces: " + e.message, "error");
    namespaces = [];
  }
  renderStats();
  renderNamespaces();
  if (selectedNs) {
    if (namespaces.find((n) => n.namespace === selectedNs)) {
      await loadFiles(selectedNs);
    } else {
      selectedNs = null;
      filesInSelected = [];
      renderNamespaceDetails();
    }
  }
}

async function loadFiles(ns) {
  try {
    const res = await fetch(`${ROOT_HTTP}/${encodeURI(ns)}`, { credentials: "omit" });
    if (!res.ok) {
      filesInSelected = [];
      toast(`Failed to list files in '${ns}' (${res.status})`, "error");
    } else {
      filesInSelected = await res.json();
    }
  } catch (e) {
    filesInSelected = [];
    toast("Failed to list files: " + e.message, "error");
  }
  renderNamespaceDetails();
}

// ---- Render: stats + namespace list ---------------------------------

function renderStats() {
  qs("#statNamespaces").textContent = namespaces.length.toLocaleString();
  qs("#statFiles").textContent = namespaces
    .reduce((a, n) => a + (n.file_count || 0), 0)
    .toLocaleString();
  qs("#statBytes").textContent = humanBytes(
    namespaces.reduce((a, n) => a + (n.total_bytes || 0), 0)
  );
}

function renderNamespaces() {
  const q = qs("#nsSearch").value.trim().toLowerCase();
  const filtered = q
    ? namespaces.filter((n) => n.namespace.toLowerCase().includes(q))
    : namespaces;
  const list = qs("#nsList");
  list.innerHTML = "";
  if (filtered.length === 0) {
    list.innerHTML = `<div class="p-4 text-slate-500 text-sm">No namespaces${q ? " matching that filter" : ""}.</div>`;
    return;
  }
  for (const ns of filtered) {
    const row = document.createElement("button");
    row.className =
      "row w-full text-left px-3 py-2 border-l-4 border-transparent " +
      (ns.namespace === selectedNs ? "selected" : "");
    row.innerHTML = `
      <div class="font-mono text-sm truncate">${escape(ns.namespace)}</div>
      <div class="text-xs text-slate-400 mt-0.5">
        ${ns.file_count} files · ${humanBytes(ns.total_bytes)}
      </div>
    `;
    row.addEventListener("click", () => {
      selectedNs = ns.namespace;
      renderNamespaces();
      loadFiles(ns.namespace);
    });
    list.appendChild(row);
  }
}

// ---- Render: namespace details (right pane) -------------------------

function renderNamespaceDetails() {
  const titleEl = qs("#nsTitle");
  const delBtn = qs("#deleteNsBtn");
  const body = qs("#nsBody");

  if (!selectedNs) {
    titleEl.textContent = "Select a namespace";
    titleEl.className = "text-lg font-semibold flex-1 text-slate-400";
    delBtn.classList.add("hidden");
    body.innerHTML = `<p class="text-slate-500 text-sm">Pick a namespace from the left, or create a new one to start uploading files. Authenticated callers can write; anyone can read via the HTTP gateway.</p>`;
    return;
  }

  titleEl.innerHTML = `<span class="font-mono">${escape(selectedNs)}</span>`;
  titleEl.className = "text-lg font-semibold flex-1";
  delBtn.classList.remove("hidden");
  delBtn.onclick = onDeleteNamespace;

  body.innerHTML = "";

  // Drag-and-drop upload zone
  const drop = document.createElement("div");
  drop.className =
    "drop-zone border-2 border-dashed border-slate-600 rounded-lg p-6 text-center text-sm text-slate-400";
  drop.innerHTML = `
    <div class="space-y-2">
      <svg class="mx-auto w-8 h-8 text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
        <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 20h16"/>
      </svg>
      <div>Drag &amp; drop files here, or
        <label class="text-blue-400 hover:text-blue-300 cursor-pointer">
          <span class="underline">choose files</span>
          <input type="file" multiple class="hidden" />
        </label>
      </div>
      <div class="text-xs text-slate-500">
        Files &gt; ${humanBytes(CHUNK_THRESHOLD)} are uploaded in chunks of ${humanBytes(CHUNK_SIZE)}.
        Login required for writes.
      </div>
    </div>
    <div class="upload-progress mt-3 space-y-1"></div>
  `;
  body.appendChild(drop);

  const fileInput = drop.querySelector('input[type="file"]');
  fileInput.addEventListener("change", (e) => handleFiles(e.target.files, drop));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("is-over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("is-over"));
  drop.addEventListener("drop", (e) => {
    e.preventDefault();
    drop.classList.remove("is-over");
    handleFiles(e.dataTransfer.files, drop);
  });

  // File list
  if (filesInSelected.length === 0) {
    const empty = document.createElement("div");
    empty.className = "text-slate-500 text-sm py-8 text-center";
    empty.textContent = "No files in this namespace yet.";
    body.appendChild(empty);
  } else {
    const tbl = document.createElement("div");
    tbl.className = "rounded border border-slate-700 divide-y divide-slate-700";
    for (const f of filesInSelected) {
      const url = `${ROOT_HTTP}/${encodeURI(selectedNs)}/${encodeURI(f.path)}`;
      const row = document.createElement("div");
      row.className = "row grid grid-cols-12 gap-2 items-center px-3 py-2";
      row.innerHTML = `
        <div class="col-span-6 path-cell">${escape(f.path)}</div>
        <div class="col-span-2 text-xs text-slate-400 text-right">${humanBytes(f.size)}</div>
        <div class="col-span-3 text-[10px] text-slate-500 font-mono truncate" title="${escape(f.sha256 || "")}">
          ${f.sha256 ? f.sha256.slice(0, 12) + "…" : "no sha"}
        </div>
        <div class="col-span-1 text-right space-x-1 whitespace-nowrap">
          <a href="${url}" target="_blank" rel="noopener" title="Download" class="inline-flex items-center justify-center w-7 h-7 rounded hover:bg-slate-700">
            <svg class="w-4 h-4 text-blue-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3v12m0 0l-4-4m4 4l4-4M4 21h16"/></svg>
          </a>
          <button data-path="${escape(f.path)}" title="Delete" class="js-del inline-flex items-center justify-center w-7 h-7 rounded hover:bg-red-600/30">
            <svg class="w-4 h-4 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2m-7 0v14a2 2 0 002 2h6a2 2 0 002-2V6"/></svg>
          </button>
        </div>
      `;
      tbl.appendChild(row);
    }
    body.appendChild(tbl);
    tbl.addEventListener("click", (e) => {
      const btn = e.target.closest(".js-del");
      if (!btn) return;
      onDeleteFile(btn.dataset.path);
    });
  }
}

// ---- Mutations ------------------------------------------------------

async function onNewNamespace() {
  const name = prompt(
    "New namespace (e.g. 'wasm', 'ext/myext/0.1.0', 'codex/foo/1.0.0'):"
  );
  if (!name) return;
  if (!(await ensureLoggedIn())) return;
  // Namespaces are created lazily by the first store_file call. Create
  // a sentinel placeholder file so the namespace appears in the list,
  // then let the user upload real files into it.
  try {
    await callActor("store_file", {
      namespace: name,
      path: ".keep",
      content_b64: "",
      content_type: "text/plain",
    });
    toast(`Created namespace '${name}'`, "success");
    await refresh();
    selectedNs = name;
    renderNamespaces();
    await loadFiles(name);
  } catch (e) {
    toast("Create failed: " + e.message, "error");
  }
}

async function onDeleteNamespace() {
  if (!selectedNs) return;
  if (!confirm(`Delete entire namespace '${selectedNs}' and ALL its files? This cannot be undone.`)) return;
  if (!(await ensureLoggedIn())) return;
  try {
    await callActor("delete_namespace", { namespace: selectedNs });
    toast(`Deleted namespace '${selectedNs}'`, "success");
    selectedNs = null;
    filesInSelected = [];
    await refresh();
  } catch (e) {
    toast("Delete failed: " + e.message, "error");
  }
}

async function onDeleteFile(path) {
  if (!selectedNs) return;
  if (!confirm(`Delete '${selectedNs}/${path}'?`)) return;
  if (!(await ensureLoggedIn())) return;
  try {
    await callActor("delete_file", { namespace: selectedNs, path });
    toast(`Deleted ${path}`, "success");
    await loadFiles(selectedNs);
    await refresh();
  } catch (e) {
    toast("Delete failed: " + e.message, "error");
  }
}

async function handleFiles(fileList, dropEl) {
  if (!fileList || fileList.length === 0) return;
  if (!(await ensureLoggedIn())) return;
  const progressBox = dropEl.querySelector(".upload-progress");
  progressBox.innerHTML = "";
  for (const file of Array.from(fileList)) {
    const row = document.createElement("div");
    row.className = "text-xs text-slate-300 flex items-center gap-2";
    row.innerHTML = `<span class="spinner"></span><span class="font-mono">${escape(file.name)}</span><span class="text-slate-500">${humanBytes(file.size)}</span><span class="status flex-1 text-slate-400"></span>`;
    progressBox.appendChild(row);
    const setStatus = (s) => row.querySelector(".status").textContent = s;
    try {
      if (file.size <= CHUNK_THRESHOLD) {
        setStatus("uploading…");
        await uploadSingleShot(selectedNs, file, setStatus);
      } else {
        setStatus("uploading chunks…");
        await uploadChunked(selectedNs, file, setStatus);
      }
      row.querySelector(".spinner").outerHTML = `<svg class="w-4 h-4 text-emerald-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M5 13l4 4L19 7"/></svg>`;
      setStatus("ok");
    } catch (e) {
      console.error(e);
      row.querySelector(".spinner").outerHTML = `<svg class="w-4 h-4 text-red-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 18L18 6M6 6l12 12"/></svg>`;
      setStatus("FAILED: " + e.message);
    }
  }
  await loadFiles(selectedNs);
  await refresh();
}

// ---- Upload paths ---------------------------------------------------

async function uploadSingleShot(namespace, file, setStatus) {
  const ab = await file.arrayBuffer();
  const b64 = arrayBufferToBase64(ab);
  setStatus(`encoding ${humanBytes(file.size)}…`);
  await callActor("store_file", {
    namespace,
    path: file.name,
    content_b64: b64,
    content_type: file.type || "application/octet-stream",
  });
}

async function uploadChunked(namespace, file, setStatus) {
  const ab = await file.arrayBuffer();
  const sha = await sha256Hex(ab);
  const totalChunks = Math.ceil(ab.byteLength / CHUNK_SIZE);
  setStatus(`hashing → ${sha.slice(0, 8)}…, ${totalChunks} chunks`);
  for (let i = 0; i < totalChunks; i++) {
    const slice = ab.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE);
    const b64 = arrayBufferToBase64(slice);
    setStatus(`uploading chunk ${i + 1}/${totalChunks} (${humanBytes(slice.byteLength)})`);
    const resp = await callActor("store_file_chunk", {
      namespace,
      path: file.name,
      chunk_index: i,
      total_chunks: totalChunks,
      data_b64: b64,
      content_type: file.type || "application/octet-stream",
    });
    if (resp.error) throw new Error(resp.error);
  }
  setStatus("finalizing…");
  let step = 0;
  while (true) {
    step++;
    const resp = await callActor("finalize_chunked_file_step", {
      namespace,
      path: file.name,
      expected_sha256: sha,
      batch_size: 1,
    });
    if (resp.error) throw new Error(resp.error);
    if (resp.done) {
      setStatus(`done (size=${humanBytes(resp.size)} sha=${resp.sha256.slice(0, 8)}…)`);
      return;
    }
    setStatus(`finalizing chunk ${resp.processed}/${resp.total}`);
    if (step > 5000) throw new Error("finalize bailed after 5000 polls");
  }
}

// ---- Actor call helper (handles JSON envelope) ----------------------

async function callActor(method, payload) {
  const json = JSON.stringify(payload);
  let raw;
  try {
    raw = await actor[method](json);
  } catch (e) {
    throw new Error(`canister rejected ${method}: ${e.message || e}`);
  }
  let parsed;
  try { parsed = JSON.parse(raw); } catch { return { ok: true, raw }; }
  if (parsed && parsed.error) {
    throw new Error(parsed.error);
  }
  return parsed;
}

async function ensureLoggedIn() {
  if (await authClient.isAuthenticated()) return true;
  toast("Login required for writes — click 'Login with Internet Identity' first.", "info");
  return false;
}

// ---- Utilities ------------------------------------------------------

function qs(sel) { return document.querySelector(sel); }

function escape(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function shortPrincipal(p) {
  if (!p || p.length < 12) return p || "";
  return p.slice(0, 5) + "…" + p.slice(-3);
}

function humanBytes(n) {
  if (!Number.isFinite(n)) return "—";
  if (n < 1024) return `${n} B`;
  const kb = n / 1024;
  if (kb < 1024) return `${kb.toFixed(kb < 10 ? 2 : 1)} KB`;
  const mb = kb / 1024;
  if (mb < 1024) return `${mb.toFixed(mb < 10 ? 2 : 1)} MB`;
  return `${(mb / 1024).toFixed(2)} GB`;
}

function arrayBufferToBase64(ab) {
  const bytes = new Uint8Array(ab);
  let s = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    s += String.fromCharCode.apply(null, bytes.subarray(i, i + CHUNK));
  }
  return btoa(s);
}

async function sha256Hex(ab) {
  const buf = await crypto.subtle.digest("SHA-256", ab);
  return Array.from(new Uint8Array(buf))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

function toast(msg, kind = "info") {
  const el = document.createElement("div");
  const colors = {
    info: "bg-slate-700 text-slate-100",
    success: "bg-emerald-600 text-white",
    error: "bg-red-600 text-white",
  };
  el.className = `${colors[kind] || colors.info} px-4 py-2 rounded shadow-lg text-sm max-w-md`;
  el.textContent = msg;
  qs("#toasts").appendChild(el);
  setTimeout(() => el.remove(), kind === "error" ? 8000 : 4000);
}

// ---- Go -------------------------------------------------------------

boot().catch((e) => {
  console.error(e);
  toast("Boot failed: " + e.message, "error");
});
