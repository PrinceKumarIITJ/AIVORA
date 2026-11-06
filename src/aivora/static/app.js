"use strict";
const $ = (s, root = document) => root.querySelector(s);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const fmtDate = (t) =>
  new Date(t * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
const short = (id) => String(id).slice(0, 8).toUpperCase();
const badge = (t) =>
  `<span class="badge ${esc(t)}">${esc(t.replaceAll("_", " "))}</span>`;
const state = {
  me: null,
  page: "overview",
  csrf: "",
  conversation: null,
  messages: [],
  sending: false,
  sessionEpoch: 0,
};
const pages = {};
class CancelledRequest extends Error {}
function clearSessionState() {
  window.dispatchEvent(new Event("aivora:session-reset"));
  state.sessionEpoch += 1;
  state.me = null;
  state.csrf = "";
  state.messages = [];
  state.conversation = null;
  state.sending = false;
  $("#dialog").close();
}
let toastTimer;
function toast(message, error = false) {
  const box = $("#toast");
  box.textContent = message;
  box.className = "show" + (error ? " error" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (box.className = ""), 5500);
}
function dialog(html) {
  $("#dialog-body").innerHTML = html;
  $("#dialog").showModal();
}
$("#close-dialog").addEventListener("click", () => $("#dialog").close());
async function api(path, options = {}) {
  const epoch = state.sessionEpoch;
  const page = state.page;
  const headers = { ...(options.headers || {}) };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(options.body);
  }
  if (state.csrf) headers["X-CSRF-Token"] = state.csrf;
  const response = await fetch("/api" + path, {
    ...options,
    headers,
    credentials: "same-origin",
  });
  if (
    epoch !== state.sessionEpoch ||
    (state.me && page !== state.page && !options.method)
  )
    throw new CancelledRequest();
  if (!response.ok) {
    let detail = "Request failed. Please retry.";
    try {
      const d = await response.json();
      detail =
        typeof d.detail === "string" ? d.detail : d.detail?.[0]?.msg || detail;
    } catch (_) {}
    if (response.status === 401 && state.me) {
      clearSessionState();
      authView();
    }
    throw new Error(detail);
  }
  const data = await response.json();
  if (epoch !== state.sessionEpoch) throw new CancelledRequest();
  return data;
}
const empty = (title, text, icon = "◇") =>
  `<div class="empty"><span class="empty-icon">${icon}</span><strong>${esc(title)}</strong>${esc(text)}</div>`;
const field = (label, name, placeholder = "", type = "text", extra = "") =>
  `<label class="field">${esc(label)}<input name="${esc(name)}" type="${type}" placeholder="${esc(placeholder)}" ${extra}></label>`;
const heading = (eyebrow, title, text, action = "") =>
  `<div class="page-heading"><div><div class="eyebrow">${esc(eyebrow)}</div><h1>${esc(title)}</h1><p>${esc(text)}</p></div>${action}</div>`;
const submitButton = (text = "Save changes") =>
  `<button class="button" type="submit">${esc(text)} <span aria-hidden="true">↗</span></button>`;
function bindForm(selector, handler) {
  const form = $(selector);
  if (!form) return;
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const button = $("button[type=submit]", form);
    if (button.disabled) return;
    button.disabled = true;
    try {
      await handler(Object.fromEntries(new FormData(form)), form);
    } catch (error) {
      if (!(error instanceof CancelledRequest)) toast(error.message, true);
    } finally {
      button.disabled = false;
    }
  });
}
function authView(mode = "login") {
  const invite = new URLSearchParams(location.search).get("invite");
  if (invite) mode = "invite";
  $("#app").innerHTML =
    `<main id="main" class="auth-layout"><section class="auth-story"><div class="brand"><span class="mark">a</span><div>AIVORA<small>Enterprise workspace</small></div></div><div class="auth-copy"><div class="eyebrow">Knowledge. Connected to action.</div><h1>Your organization.<br>Working with<br><em>intelligence.</em></h1><p>Bring trusted answers, thoughtful approvals and everyday operations into one shared workspace.</p><div class="auth-features"><span>◎ Permission-aware knowledge</span><span>↗ Approved workflows</span><span>◷ Durable automation</span></div></div><div class="auth-foot">Built for teams across industries · Local pilot v0.2</div></section><section class="auth-form-side"><div class="auth-box"><div class="eyebrow">Welcome to AIVORA</div><h2>${mode === "login" ? "Your workspace awaits." : mode === "invite" ? "Join your team." : "Make room for better work."}</h2><p>${mode === "login" ? "Sign in to your organization’s intelligent workspace." : mode === "invite" ? "Your invitation is tied to your email and department." : "Create your organization and start with your own knowledge."}</p>${mode !== "invite" ? `<div class="auth-tabs"><button data-auth="login" class="${mode === "login" ? "active" : ""}">Sign in</button><button data-auth="signup" class="${mode === "signup" ? "active" : ""}">Create workspace</button></div>` : ""}<form id="auth-form"><div class="fields">${mode !== "login" ? field("Your name", "name", "Alex Morgan", "text", 'required minlength="2" maxlength="80" autocomplete="name"') : ""}${mode === "signup" ? field("Organization name", "organization", "Acme Studio", "text", 'required minlength="2" maxlength="100"') + field("Industry", "industry", "Technology, education, healthcare…", "text", 'maxlength="80"') : ""}${field("Work email", "email", "you@organization.com", "email", 'required autocomplete="username" maxlength="254"')}${field("Password", "password", "At least 12 characters", "password", `required minlength="12" maxlength="128" autocomplete="${mode === "login" ? "current-password" : "new-password"}"`)}</div>${submitButton(mode === "login" ? "Sign in" : mode === "invite" ? "Accept invitation" : "Create workspace")}<p id="auth-error" class="auth-error" role="alert"></p></form><div class="auth-fine">Your organization controls its knowledge and access.<br>No documents are shared between workspaces.</div></div></section></main>`;
  document
    .querySelectorAll("[data-auth]")
    .forEach((b) => (b.onclick = () => authView(b.dataset.auth)));
  bindForm("#auth-form", async (values) => {
    try {
      if (mode === "signup" && !values.industry) values.industry = "General";
      if (mode === "invite") values.token = invite;
      const r = await api(
        "/auth/" + (mode === "invite" ? "accept-invite" : mode),
        { method: "POST", body: values },
      );
      clearSessionState();
      state.csrf = r.csrf;
      state.me = await api("/me");
      history.replaceState(null, "", location.pathname);
      await navigate("missions");
    } catch (e) {
      $("#auth-error").textContent = e.message;
    }
  });
}
const navItems = [
  ["overview", "▦", "Overview"],
  ["chat", "✧", "Ask AIVORA"],
  ["knowledge", "▤", "Knowledge"],
  ["workflows", "⌘", "Workflows"],
  ["requests", "↗", "Requests"],
  ["automations", "◷", "Automations"],
  ["team", "♧", "Team & access"],
  ["integrations", "⊞", "Integrations"],
  ["audit", "≋", "Audit trail"],
  ["settings", "⚙", "Settings"],
  ["account", "◎", "Your account"],
];
const adminPages = new Set(["automations", "team", "audit", "settings"]);
function shell(page) {
  const { user, organization: org } = state.me;
  const item = navItems.find((n) => n[0] === page);
  $("#app").innerHTML =
    `<div class="layout"><aside class="sidebar"><div class="brand"><span class="mark">a</span><div>AIVORA<small>Enterprise workspace</small></div></div><div class="workspace"><span class="workspace-symbol">${esc(org.name.slice(0, 1).toUpperCase())}</span><div><strong>${esc(org.name)}</strong><small>${esc(org.industry)} workspace</small></div></div><div class="nav-label">WORKSPACE</div><nav class="nav" aria-label="Workspace navigation">${navItems
      .filter((n) => user.role === "admin" || !adminPages.has(n[0]))
      .map(
        ([id, icon, label]) =>
          `<button data-nav="${id}" class="${id === page ? "active" : ""}" ${id === page ? 'aria-current="page"' : ""}><span class="icon" aria-hidden="true">${icon}</span>${label}</button>`,
      )
      .join(
        "",
      )}</nav><div class="sidebar-footer"><div class="pilot"><span class="dot"></span> Local pilot · v0.2</div><div class="user-strip"><span class="avatar">${esc(
      user.name
        .split(" ")
        .map((n) => n[0])
        .slice(0, 2)
        .join(""),
    )}</span><div><strong>${esc(user.name)}</strong><small>${esc(user.role)} · ${esc(user.department)}</small></div></div></div></aside><div class="main-wrap"><header class="topbar"><div class="breadcrumb">Workspace / <b>${esc(item?.[2] || page)}</b></div><div class="top-status"><span class="dot"></span>${state.me.provider === "extractive" ? "Offline · source passages" : esc(state.me.provider + " · " + state.me.model)}<button class="text-button" id="logout">Sign out</button></div></header><main id="main" class="content" tabindex="-1"><div class="loading">Loading workspace…</div></main></div></div>`;
  document
    .querySelectorAll("[data-nav]")
    .forEach((b) => (b.onclick = () => navigate(b.dataset.nav)));
  $("#logout").onclick = async () => {
    try {
      await api("/auth/logout", { method: "POST" });
      clearSessionState();
      authView();
    } catch (e) {
      toast(e.message, true);
    }
  };
}
async function navigate(page) {
  if (!state.me) return authView();
  if (adminPages.has(page) && state.me.user.role !== "admin") page = "overview";
  state.page = page;
  shell(page);
  try {
    await pages[page]();
  } catch (e) {
    if (state.me && !(e instanceof CancelledRequest)) {
      $("#main").innerHTML =
        `<div class="error-page"><h2>Couldn’t open this view</h2><p>${esc(e.message)}</p><button class="button secondary" id="retry">Try again</button></div>`;
      $("#retry").onclick = () => navigate(page);
    }
  }
}
pages.overview = async () => {
  const d = await api("/overview"),
    runs = d.recent_runs;
  const latency = runs.length
    ? Math.round(runs.reduce((s, r) => s + r.latency_ms, 0) / runs.length)
    : null;
  $("#main").innerHTML =
    heading(
      "Your workspace, at a glance",
      `Good to see you, ${state.me.user.name.split(" ")[0]}.`,
      "A little less searching. A lot more getting things done.",
      '<button class="button" id="ask-now">✧ Ask your assistant</button>',
    ) +
    `<div class="stats">${[
      [
        "Accessible documents",
        d.documents,
        "Only knowledge you have access to",
        "▤",
      ],
      [
        "Pending requests",
        d.pending_actions,
        "Your requests and review queue",
        "↗",
      ],
      [
        "Your requests today",
        d.requests_today + " / " + d.daily_limit,
        "Daily quota resets at 00:00 UTC",
        "◷",
      ],
      [
        "Average response",
        latency === null ? "—" : latency + " ms",
        `Across ${runs.length} recent visible runs`,
        "⌁",
      ],
    ]
      .map(
        ([l, v, n, i]) =>
          `<div class="stat"><div class="stat-label">${esc(l)}<span>${i}</span></div><div class="stat-value">${esc(v)}</div><div class="stat-note">${esc(n)}</div></div>`,
      )
      .join(
        "",
      )}</div><section class="hero-panel"><div><div class="eyebrow">Make knowledge work</div><h2>The answer is already<br>somewhere in your organization.</h2><p>Find it with source-backed answers, then turn the next step into a request your team can review and act on.</p><button class="button secondary" id="explore">Explore your knowledge ↗</button></div><div class="orbit" aria-hidden="true"><span class="mark">a</span></div></section><div class="grid-two"><section class="panel"><div class="panel-title"><h2>Where would you like to start?</h2><span class="eyebrow">Quick access</span></div><div class="quick-grid">${[
      [
        "chat",
        "✧",
        "Ask a question",
        "Answers grounded in your team’s documents.",
      ],
      [
        "knowledge",
        "▤",
        "Explore knowledge",
        "Find policies, procedures and team guides.",
      ],
      [
        "workflows",
        "↗",
        "Start a request",
        "Get help through an approved workflow.",
      ],
      [
        "requests",
        "◎",
        "Track your requests",
        "See decisions, tickets and next steps.",
      ],
    ]
      .map(
        ([id, i, t, p]) =>
          `<button class="quick-card" data-quick="${id}"><span>${i}</span><strong>${t}</strong><small>${p}</small></button>`,
      )
      .join(
        "",
      )}</div></section><section class="panel"><div class="panel-title"><h2>Recent AI activity</h2><button class="text-button" id="all-runs">Inspect runs ↗</button></div>${
      runs.length
        ? runs
            .slice(0, 5)
            .map(
              (r) =>
                `<div class="activity-row"><span class="activity-icon">${r.status === "answered" ? "✓" : "◇"}</span><div>${badge(r.status)}<small>${esc(r.provider)} · ${r.retrieved} passages · ${r.latency_ms} ms<br>${fmtDate(r.created)}</small></div></div>`,
            )
            .join("")
        : empty(
            "A fresh start",
            "Ask your first question to see real activity here.",
          )
    }</section></div><div class="footer-note"><span>One workspace. Your organization’s knowledge and workflows.</span><span>Access checks apply to every answer and action.</span></div>`;
  $("#ask-now").onclick = () => navigate("chat");
  $("#explore").onclick = () => navigate("knowledge");
  document
    .querySelectorAll("[data-quick]")
    .forEach((b) => (b.onclick = () => navigate(b.dataset.quick)));
  $("#all-runs").onclick = () =>
    dialog(
      `<h2>Recent runs</h2>${runs.length ? runs.map((r) => `<div class="request-card"><div class="request-top"><code>${short(r.id)}</code>${badge(r.status)}</div><p>${esc(r.provider)} · ${esc(r.model || "source extraction")} · ${r.latency_ms} ms<br>Reported tokens: ${r.input_tokens} input / ${r.output_tokens} output</p><pre>${esc(JSON.stringify(r.stages, null, 2))}</pre></div>`).join("") : empty("No runs yet", "Traces appear after questions.")}`,
    );
};
function citationButtons(c) {
  return c?.length
    ? `<div class="citation-list">${c.map((s, i) => `<button class="citation" data-source="${esc(s.document_id)}">[${i + 1}] ${esc(s.title)} · p.${s.page} ↗</button>`).join("")}</div>`
    : "";
}
function bindSources() {
  document.querySelectorAll("[data-source]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          const d = await api("/documents/" + b.dataset.source);
          dialog(
            `<div class="eyebrow">Source document · version ${d.version}</div><h2>${esc(d.title)}</h2>${d.chunks.map((c) => `<h3>Page ${c.page}</h3><div class="detail-text">${esc(c.text)}</div><hr>`).join("")}`,
          );
        } catch (e) {
          toast(e.message, true);
        }
      }),
  );
}
function renderMessages() {
  const box = $("#messages");
  if (!box) return;
  box.innerHTML =
    state.messages
      .map(
        (m) =>
          `<article class="message ${esc(m.role)}"><span class="message-avatar">${m.role === "user" ? "↗" : "✧"}</span><div class="message-body"><div class="message-label">${m.role === "user" ? "You" : esc(state.me.organization.assistant_name)}</div><div class="message-text">${esc(m.content)}</div>${citationButtons(m.citations)}</div></article>`,
      )
      .join("") +
    (state.sending
      ? '<div class="message"><span class="message-avatar">✧</span><div class="muted">Checking your accessible documents…</div></div>'
      : "");
  box.scrollTop = box.scrollHeight;
  bindSources();
}
pages.chat = async () => {
  const conversations = await api("/conversations");
  $("#main").innerHTML =
    heading(
      "Trusted knowledge, useful answers",
      `Ask ${state.me.organization.assistant_name}`,
      "Every answer starts with the documents you’re allowed to see.",
    ) +
    `<div class="chat-layout"><section class="chat-main"><div class="chat-top"><div><strong>✧ ${esc(state.me.organization.assistant_name)}</strong><small>${esc(state.me.retrieval)} · ${state.me.provider === "extractive" ? "Extracted passages, no LLM" : "AI-generated with source references"}</small></div><span class="badge">Permission-aware</span></div><div class="chat-messages" id="messages">${state.messages.length ? "" : `<div class="chat-welcome"><span class="mark">a</span><h2>What would you like to know?</h2><p>Ask about policies, processes and team guides. I’ll find relevant evidence and show you where it came from.</p><div class="suggestions">${["What is the annual leave allowance?", "How do I request software access?", "What is the onboarding process?", "How should I report a security incident?"].map((q) => `<button data-question="${q}">${q} ↗</button>`).join("")}</div></div>`}</div><div class="composer"><form id="chat-form"><textarea aria-label="Your question" id="question" name="question" placeholder="Ask about your organization’s knowledge…" required minlength="2" maxlength="2000" rows="2"></textarea><button class="button" type="submit" aria-label="Send question" ${state.sending ? "disabled" : ""}>↗</button></form><small>Verify important decisions against the source. Actions need a separate approved request.</small></div></section><aside class="chat-aside"><button class="button secondary small" id="new-chat">＋ New conversation</button><h3 class="history-title">YOUR CONVERSATIONS</h3><div class="history-list">${conversations.map((c) => `<button class="history-item ${state.conversation === c.id ? "active" : ""}" data-conversation="${esc(c.id)}">${esc(c.title)}</button>`).join("") || '<span class="muted">No conversations yet</span>'}</div><div class="chat-tip"><strong>Better questions, better answers.</strong><p>Include a topic or procedure name. If a source is missing, ask your administrator to add it.</p></div></aside></div>`;
  if (state.messages.length || state.sending) renderMessages();
  $("#new-chat").onclick = () => {
    if (state.sending) return;
    state.messages = [];
    state.conversation = null;
    pages.chat();
  };
  document.querySelectorAll("[data-conversation]").forEach(
    (b) =>
      (b.onclick = async () => {
        if (state.sending) return;
        try {
          const c = await api("/conversations/" + b.dataset.conversation);
          state.messages = c.messages;
          state.conversation = c.id;
          await pages.chat();
        } catch (e) {
          toast(e.message, true);
        }
      }),
  );
  document.querySelectorAll("[data-question]").forEach(
    (b) =>
      (b.onclick = () => {
        $("#question").value = b.dataset.question;
        $("#question").focus();
      }),
  );
  $("#question").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("#chat-form").requestSubmit();
    }
  });
  bindForm("#chat-form", async (v, f) => {
    if (state.sending) return;
    const epoch = state.sessionEpoch;
    const q = v.question.trim();
    if (q.length < 2) return;
    state.messages.push({ role: "user", content: q });
    state.sending = true;
    renderMessages();
    f.reset();
    try {
      const r = await api("/chat", {
        method: "POST",
        body: { question: q, conversation_id: state.conversation },
      });
      state.conversation = r.conversation_id;
      state.messages.push({
        role: "assistant",
        content: r.answer,
        citations: r.citations,
      });
    } catch (e) {
      if (epoch !== state.sessionEpoch || e instanceof CancelledRequest) return;
      state.messages.push({
        role: "assistant",
        content: "Request could not complete: " + e.message,
      });
      toast(e.message, true);
    } finally {
      if (epoch === state.sessionEpoch) {
        state.sending = false;
        if (state.page === "chat" && state.me) await pages.chat();
      }
    }
  });
};
pages.knowledge = async () => {
  const docs = await api("/documents"),
    admin = state.me.user.role === "admin";
  $("#main").innerHTML =
    heading(
      "The source of better answers",
      "Your knowledge, connected.",
      "A searchable home for policies, guides and procedures.",
      admin
        ? '<button class="button" id="upload-open">＋ Add document</button>'
        : "",
    ) +
    `<section class="panel"><div class="panel-title"><h2>Knowledge library <span class="inline-count">${docs.length} accessible documents</span></h2><label class="field"><input id="doc-search" aria-label="Filter documents" placeholder="Find a document…"></label></div>${docs.length ? `<div class="table-wrap"><table><thead><tr><th>Document</th><th>Visibility</th><th>Version</th><th>Indexed</th><th>Actions</th></tr></thead><tbody>${docs.map((d) => `<tr data-doc-title="${esc(d.title.toLowerCase())}"><td><button class="text-button" data-source="${esc(d.id)}">▤ ${esc(d.title)}</button><span class="sub">${d.chunks} searchable passages</span></td><td>${badge(d.visibility)}<span class="sub">${esc(d.department)}</span></td><td>v${d.version}</td><td>${fmtDate(d.created)}</td><td>${admin ? `<button class="text-button" data-replace="${esc(d.id)}">Replace</button> · <button class="text-button" data-delete-doc="${esc(d.id)}">Delete</button>` : "View only"}</td></tr>`).join("")}</tbody></table></div>` : empty("Start with what your team knows", "Add a policy or guide to make it searchable.", "▤")}</section><div class="note">Source previews and retrieval follow role and department permissions. PDF uploads must contain selectable text; scanned-document OCR is not included.</div>`;
  bindSources();
  $("#doc-search").oninput = (e) =>
    document
      .querySelectorAll("[data-doc-title]")
      .forEach(
        (row) =>
          (row.hidden = !row.dataset.docTitle.includes(
            e.target.value.toLowerCase(),
          )),
      );
  const uploadDialog = (replace = "") => {
    const old = docs.find((d) => d.id === replace);
    dialog(
      `<div class="eyebrow">Knowledge ingestion</div><h2>${replace ? "Publish a new version" : "Add a document"}</h2><form id="upload-form"><div class="fields">${field("Document title", "title", "Employee handbook", "text", `required minlength="2" maxlength="200" value="${esc(old?.title || "")}"`)}<label class="field">File<input type="file" name="file" accept=".pdf,.md,.txt" required><small>PDF, Markdown or UTF-8 text · up to 5 MB</small></label><label class="field">Visibility<select name="visibility"><option value="organization">Entire organization</option><option value="department">Your department only</option><option value="admin">Administrators only</option></select></label>${field("Department", "department", "", "text", `required maxlength="60" value="${esc(state.me.user.department)}"`)}</div><div class="form-actions">${submitButton("Upload and index")}</div></form>`,
    );
    bindForm("#upload-form", async (_, f) => {
      const body = new FormData(f);
      if (replace) body.set("replace_id", replace);
      await api("/documents", { method: "POST", body });
      $("#dialog").close();
      toast("Document indexed and ready to search");
      await pages.knowledge();
    });
  };
  $("#upload-open")?.addEventListener("click", () => uploadDialog());
  document
    .querySelectorAll("[data-replace]")
    .forEach((b) => (b.onclick = () => uploadDialog(b.dataset.replace)));
  document.querySelectorAll("[data-delete-doc]").forEach(
    (b) =>
      (b.onclick = () => {
        dialog(
          '<h2>Delete this document?</h2><p class="muted">Its passages will be removed from search. Previous answers using it will be hidden.</p><button class="button danger" id="confirm-delete">Delete document</button>',
        );
        $("#confirm-delete").onclick = async () => {
          try {
            await api("/documents/" + b.dataset.deleteDoc, {
              method: "DELETE",
            });
            $("#dialog").close();
            toast("Document deleted");
            await pages.knowledge();
          } catch (e) {
            toast(e.message, true);
          }
        };
      }),
  );
};
function requestDialog(w) {
  dialog(
    `<div class="eyebrow">${esc(w.department)} workflow</div><h2>${esc(w.name)}</h2><p class="muted">${esc(w.description)}</p><form id="request-form"><div class="fields">${field("Request title", "title", "What do you need help with?", "text", 'required minlength="3" maxlength="160"')}<label class="field">Details<textarea name="description" required minlength="5" maxlength="4000" placeholder="Include the context your reviewer needs."></textarea></label><label class="field">Priority<select name="priority"><option value="normal">Normal</option><option value="low">Low</option><option value="high">High</option></select></label></div><p class="note">A separate reviewer must approve this request. Approval creates an internal AIVORA ticket; no external system is contacted.</p>${submitButton("Submit for approval")}</form>`,
  );
  const key = crypto.randomUUID();
  bindForm("#request-form", async (v) => {
    await api("/actions", {
      method: "POST",
      body: { ...v, workflow_id: w.id, idempotency_key: key },
    });
    $("#dialog").close();
    toast("Request submitted for approval");
    await navigate("requests");
  });
}
pages.workflows = async () => {
  const workflows = await api("/workflows");
  $("#main").innerHTML =
    heading(
      "From question to next step",
      "Work that moves forward.",
      "Configured for your organization. Reviewed before execution.",
      state.me.user.role === "admin"
        ? '<button class="button" id="workflow-add">＋ Create workflow</button>'
        : "",
    ) +
    `<div class="cards">${workflows.map((w) => `<article class="card"><div class="card-icon">↗</div><h2>${esc(w.name)}</h2><p>${esc(w.description)}</p><div class="card-footer">${badge(w.department)}<button class="text-button" data-request="${esc(w.id)}">Start request ↗</button></div></article>`).join("")}</div><p class="note">Configure request categories for HR, IT, facilities or operations without changing code. This release executes internal tickets.</p>`;
  document
    .querySelectorAll("[data-request]")
    .forEach(
      (b) =>
        (b.onclick = () =>
          requestDialog(workflows.find((w) => w.id === b.dataset.request))),
    );
  $("#workflow-add")?.addEventListener("click", () => {
    dialog(
      `<h2>Create a request workflow</h2><form id="workflow-form"><div class="fields">${field("Workflow name", "name", "Facilities support", "text", 'required minlength="2" maxlength="100"')}${field("Handling department", "department", "Facilities", "text", 'required maxlength="60"')}<label class="field">Description<textarea name="description" required minlength="5" maxlength="1000"></textarea></label></div><div class="form-actions">${submitButton("Create workflow")}</div></form>`,
    );
    bindForm("#workflow-form", async (v) => {
      await api("/workflows", { method: "POST", body: v });
      $("#dialog").close();
      toast("Workflow created");
      await pages.workflows();
    });
  });
};
pages.requests = async () => {
  const actions = await api("/actions");
  $("#main").innerHTML =
    heading(
      "Accountable action, at every step",
      "Requests & approvals",
      "Track your requests and review the work assigned to your team.",
      '<button class="button" id="new-request">＋ New request</button>',
    ) +
    `<div class="note">Requesters cannot approve their own actions. Approvals expire after seven days. Decisions and ticket creation are saved together to prevent duplicates.</div><section class="panel"><div class="panel-title"><h2>Request inbox</h2><span class="inline-count">${actions.length} visible requests</span></div>${actions.length ? actions.map((a) => `<article class="request-card"><div class="request-top"><div><span class="eyebrow">${esc(a.workflow)} · ${short(a.id)}</span><h3>${esc(a.title)}</h3></div>${badge(a.status)}</div><p>${esc(a.description)}</p><div class="request-meta"><span>${a.mine ? "Your request" : "Review queue"}</span><span>${esc(a.department)}</span><span>${esc(a.priority)} priority</span><span>${fmtDate(a.created)}</span></div>${a.reason ? `<p>Reviewer note: ${esc(a.reason)}</p>` : ""}<div class="request-bottom">${a.can_review ? `<button class="button small" data-decide="${esc(a.id)}" data-decision="approve">Approve & create ticket</button><button class="button secondary small" data-decide="${esc(a.id)}" data-decision="reject">Reject</button>` : ""}${a.ticket_id ? `<span class="badge">Ticket ${short(a.ticket_id)} · ${esc(a.ticket_status)}</span>${!a.mine && a.ticket_status === "open" ? `<button class="text-button" data-resolve="${esc(a.id)}">Mark resolved</button>` : ""}` : ""}${a.mine && a.status === "pending" ? '<span class="muted">Waiting for a separate reviewer.</span>' : ""}</div></article>`).join("") : empty("No requests yet", "Start a workflow when you need your team to act.", "↗")}</section>`;
  $("#new-request").onclick = () => navigate("workflows");
  document.querySelectorAll("[data-decide]").forEach(
    (b) =>
      (b.onclick = () => {
        const a = actions.find((a) => a.id === b.dataset.decide);
        dialog(
          `<h2>${b.dataset.decision === "approve" ? "Approve this request?" : "Reject this request?"}</h2><h3>${esc(a.title)}</h3><div class="detail-text">${esc(a.description)}</div><form id="decision-form"><label class="field">Reviewer note<textarea name="reason" maxlength="500"></textarea></label><div class="form-actions">${submitButton(b.dataset.decision === "approve" ? "Approve & create internal ticket" : "Reject request")}</div></form>`,
        );
        bindForm("#decision-form", async (v) => {
          await api("/actions/" + a.id + "/decision", {
            method: "POST",
            body: { decision: b.dataset.decision, reason: v.reason },
          });
          $("#dialog").close();
          toast("Decision recorded");
          await pages.requests();
        });
      }),
  );
  document.querySelectorAll("[data-resolve]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          await api("/actions/" + b.dataset.resolve + "/resolve", {
            method: "POST",
          });
          toast("Ticket resolved");
          await pages.requests();
        } catch (e) {
          toast(e.message, true);
        }
      }),
  );
};
pages.automations = async () => {
  const d = await api("/automations");
  $("#main").innerHTML =
    heading(
      "Keep routine work moving",
      "Automations with a purpose.",
      "Scheduled follow-ups that stay inside your organization.",
      '<button class="button" id="automation-add">＋ New automation</button>',
    ) +
    `<div class="note">Run the scheduler worker for unattended execution. “Run due schedules” processes schedules due now. Automations create internal tasks; no email or message is sent.</div><div class="grid-two"><section class="panel"><div class="panel-title"><h2>Your schedules</h2><button class="text-button" id="run-schedules">Run due schedules ↗</button></div>${d.schedules.length ? d.schedules.map((s) => `<div class="request-card"><div class="request-top"><h3>${esc(s.name)}</h3>${badge(s.enabled ? "enabled" : "paused")}</div><p>${s.kind === "document_review" ? "Find documents older than 30 days and create review tasks." : "Find pending approvals older than 24 hours and create follow-up tasks."}</p><div class="request-meta"><span>Every ${s.interval_hours} hours</span><span>Next: ${fmtDate(s.next_run)}</span></div><div class="request-bottom"><button class="text-button" data-toggle="${esc(s.id)}">${s.enabled ? "Pause schedule" : "Resume schedule"}</button></div></div>`).join("") : empty("Give routine work a schedule", "Start with document reviews or overdue approvals.", "◷")}</section><section class="panel"><div class="panel-title"><h2>Execution history</h2></div>${d.runs.length ? d.runs.map((r) => `<div class="activity-row"><span class="activity-icon">✓</span><div>${esc(r.summary)}<small>${fmtDate(r.created)}</small></div></div>`).join("") : empty("No executions yet", "Completed runs leave an accountable record.")}</section></div><section class="panel"><div class="panel-title"><h2>Follow-up tasks</h2><span class="inline-count">${d.tasks.filter((t) => t.status === "open").length} open</span></div>${d.tasks.length ? `<div class="table-wrap"><table><thead><tr><th>Task</th><th>Source</th><th>Status</th><th>Action</th></tr></thead><tbody>${d.tasks.map((t) => `<tr><td>${esc(t.title)}<span class="sub">${fmtDate(t.created)}</span></td><td>${esc(t.source_type)} · ${short(t.source_id)}</td><td>${badge(t.status)}</td><td>${t.status === "open" ? `<button class="text-button" data-complete="${esc(t.id)}">Mark complete</button>` : "—"}</td></tr>`).join("")}</tbody></table></div>` : empty("Your follow-up queue is clear", "Tasks appear when a schedule finds something needing attention.")}</section>`;
  $("#run-schedules").onclick = async () => {
    try {
      const r = await api("/automations/run", { method: "POST" });
      toast(
        r.runs.length
          ? `Executed ${r.runs.length} due schedule(s)`
          : "No schedules are due",
      );
      await pages.automations();
    } catch (e) {
      toast(e.message, true);
    }
  };
  $("#automation-add").onclick = () => {
    dialog(
      `<h2>Schedule a useful follow-up</h2><form id="automation-form"><div class="fields">${field("Name", "name", "Weekly knowledge hygiene", "text", 'required minlength="2" maxlength="100"')}<label class="field">Automation<select name="kind"><option value="document_review">Document review · older than 30 days</option><option value="approval_reminder">Approval reminder · pending over 24 hours</option></select></label>${field("Run every (hours)", "interval_hours", "24", "number", 'required min="1" max="720" value="24"')}</div><div class="form-actions">${submitButton("Create schedule")}</div></form>`,
    );
    bindForm("#automation-form", async (v) => {
      v.interval_hours = Number(v.interval_hours);
      await api("/automations", { method: "POST", body: v });
      $("#dialog").close();
      toast("Schedule created; first run is due now");
      await pages.automations();
    });
  };
  document.querySelectorAll("[data-toggle]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          await api("/automations/" + b.dataset.toggle + "/toggle", {
            method: "POST",
          });
          await pages.automations();
        } catch (e) {
          toast(e.message, true);
        }
      }),
  );
  document.querySelectorAll("[data-complete]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          await api("/tasks/" + b.dataset.complete + "/complete", {
            method: "POST",
          });
          await pages.automations();
        } catch (e) {
          toast(e.message, true);
        }
      }),
  );
};
pages.team = async () => {
  const users = await api("/users");
  $("#main").innerHTML =
    heading(
      "The right access, for every person",
      "A workspace for your team.",
      "Invite colleagues and map access to their role and department.",
      '<button class="button" id="invite-open">＋ Invite member</button>',
    ) +
    `<section class="panel"><div class="panel-title"><h2>Organization members</h2><span class="inline-count">${users.length} members</span></div><div class="table-wrap"><table><thead><tr><th>Member</th><th>Department</th><th>Role</th><th>Status</th><th></th></tr></thead><tbody>${users.map((u) => `<tr><td>${esc(u.name)}<span class="sub">${esc(u.email)}</span></td><td>${esc(u.department)}</td><td>${badge(u.role)}</td><td>${badge(u.active ? "active" : "inactive")}</td><td>${u.id !== state.me.user.id ? `<button class="text-button" data-user="${esc(u.id)}">Manage access</button>` : "You"}</td></tr>`).join("")}</tbody></table></div></section><div class="cards"><article class="card"><h3>Employee</h3><p>Read accessible knowledge, ask questions and submit requests.</p></article><article class="card"><h3>Reviewer</h3><p>Employee capabilities plus review other people’s requests for their handling department.</p></article><article class="card"><h3>Administrator</h3><p>Configure the organization, manage memberships and review requests. Department restrictions still apply to documents.</p></article></div>`;
  $("#invite-open").onclick = () => {
    dialog(
      `<h2>Invite a colleague</h2><form id="invite-form"><div class="fields">${field("Work email", "email", "colleague@organization.com", "email", 'required maxlength="254"')}${field("Department", "department", "General", "text", 'required maxlength="60" value="General"')}<label class="field">Role<select name="role"><option value="employee">Employee</option><option value="reviewer">Reviewer</option><option value="admin">Administrator</option></select></label></div><div class="form-actions">${submitButton("Create invitation link")}</div></form>`,
    );
    bindForm("#invite-form", async (v) => {
      const r = await api("/invites", { method: "POST", body: v });
      dialog(
        `<h2>Invitation ready</h2><p>Share this link privately. It expires in 24 hours and can be used once by the invited email. No email has been sent.</p><div class="result-secret">${esc(r.url)}</div>`,
      );
    });
  };
  document.querySelectorAll("[data-user]").forEach(
    (b) =>
      (b.onclick = () => {
        const u = users.find((u) => u.id === b.dataset.user);
        dialog(
          `<h2>Manage ${esc(u.name)}’s access</h2><form id="access-form"><div class="fields">${field("Department", "department", "", "text", `required maxlength="60" value="${esc(u.department)}"`)}<label class="field">Role<select name="role">${["employee", "reviewer", "admin"].map((r) => `<option ${r === u.role ? "selected" : ""}>${r}</option>`).join("")}</select></label><label class="field">Account status<select name="active"><option value="true" ${u.active ? "selected" : ""}>Active</option><option value="false" ${!u.active ? "selected" : ""}>Inactive</option></select></label></div><p class="muted">Changes revoke all this member’s existing sessions and API tokens.</p>${submitButton("Update access")}</form>`,
        );
        bindForm("#access-form", async (v) => {
          v.active = v.active === "true";
          await api("/users/" + u.id, { method: "PUT", body: v });
          $("#dialog").close();
          toast("Access updated; existing credentials revoked");
          await pages.team();
        });
      }),
  );
};
pages.integrations = async () => {
  const tokens = await api("/tokens");
  const example = [
    "POST /api/chat",
    "Authorization: Bearer YOUR_SCOPED_TOKEN",
    "Content-Type: application/json",
    "",
    "{",
    '  "question": "How do I request software access?"',
    "}",
  ].join("\n");
  $("#main").innerHTML =
    heading(
      "Bring intelligence into your systems",
      "Built to fit your organization.",
      "Use scoped API tokens to connect AIVORA to portals and internal applications.",
    ) +
    `<div class="split-form"><section class="panel"><div class="eyebrow">Your API credentials</div><h2>Create a scoped token</h2><p class="muted">Tokens inherit your current membership and document permissions. Keep them on your server.</p><form id="token-form"><div class="fields">${field("Token name", "label", "Internal employee portal", "text", 'required minlength="2" maxlength="80"')}${field("Expires in (days)", "days", "30", "number", 'required value="30" min="1" max="90"')}<label class="field">Allowed capabilities</label><div class="checklist">${["knowledge:read", "chat:write", "actions:read", "actions:write", "workflows:read", "missions:read", "missions:write"].map((s, i) => `<label><input type="checkbox" name="scopes" value="${s}" ${i < 2 ? "checked" : ""}>${s}</label>`).join("")}</div></div><div class="form-actions">${submitButton("Generate token")}</div></form></section><section class="panel"><div class="eyebrow">REST API · OpenAPI documented</div><h2>A useful answer, inside your own app.</h2><p class="muted">Your backend calls AIVORA as the token owner. Membership determines organization and permissions.</p><pre>${esc(example)}</pre><p class="muted">Responses include citations, conversation ID and run ID. Event delivery: <code>/api/chat/stream</code>.</p><a class="button secondary small" href="/docs" target="_blank" rel="noopener">Explore API reference ↗</a></section></div><section class="panel"><div class="panel-title"><h2>Your active tokens</h2></div>${tokens.length ? `<div class="table-wrap"><table><thead><tr><th>Label</th><th>Scopes</th><th>Expires</th><th>Action</th></tr></thead><tbody>${tokens.map((t) => `<tr><td>${esc(t.label)}</td><td>${t.scopes.map((s) => `<code>${esc(s)}</code>`).join(" · ")}</td><td>${fmtDate(t.expires)}</td><td><button class="text-button" data-revoke="${esc(t.id)}">Revoke</button></td></tr>`).join("")}</tbody></table></div>` : empty("No active tokens", "Create a token when you’re ready to integrate.")}</section><div class="note">Connect GitHub and Slack in Connected tools. The local MCP bridge also supports missions. Enterprise OIDC and hosted OAuth MCP remain separate deployment work.</div>`;
  bindForm("#token-form", async (v, f) => {
    v.days = Number(v.days);
    v.scopes = new FormData(f).getAll("scopes");
    if (!v.scopes.length) throw new Error("Select at least one scope");
    const r = await api("/tokens", { method: "POST", body: v });
    await pages.integrations();
    dialog(
      `<h2>Copy your token now</h2><p>The complete token is shown once. Store it securely in your application’s server environment.</p><div class="result-secret" id="new-token">${esc(r.token)}</div>`,
    );
  });
  document.querySelectorAll("[data-revoke]").forEach(
    (b) =>
      (b.onclick = async () => {
        try {
          await api("/tokens/" + b.dataset.revoke, { method: "DELETE" });
          toast("Token revoked");
          await pages.integrations();
        } catch (e) {
          toast(e.message, true);
        }
      }),
  );
};
pages.audit = async () => {
  const events = await api("/audit");
  $("#main").innerHTML =
    heading(
      "A clear record of what happened",
      "Accountability, built in.",
      "Organization activity with actor IDs, resource IDs and timestamps.",
    ) +
    `<section class="panel"><div class="panel-title"><h2>Audit events</h2><span class="inline-count">Latest ${events.length} events</span></div>${events.length ? `<div class="table-wrap"><table><thead><tr><th>Event</th><th>Actor</th><th>Resource</th><th>Time</th></tr></thead><tbody>${events.map((a) => `<tr><td><code>${esc(a.event)}</code></td><td><code>${a.actor_id === "scheduler" ? "scheduler" : short(a.actor_id)}</code></td><td><code>${a.object_id ? short(a.object_id) : "—"}</code></td><td>${fmtDate(a.created)}</td></tr>`).join("")}</tbody></table></div>` : empty("No events yet", "Changes appear here.")}</section><div class="note">Audit events omit prompts, document contents and credentials. The local database audit is not tamper-evident; immutable retention is a deployment hardening requirement.</div>`;
};
pages.settings = async () => {
  const o = state.me.organization;
  $("#main").innerHTML =
    heading(
      "Your company, your workspace",
      "Make AIVORA your own.",
      "Adapt the assistant and organization profile without company-specific code.",
    ) +
    `<div class="split-form"><section class="panel"><div class="eyebrow">Organization settings</div><h2>A familiar workspace</h2><p class="muted">Use your team’s name and terminology. Access controls remain enforced by the application.</p><div class="note">Style guidance changes presentation. It cannot grant access or approve actions.</div></section><section class="panel"><form id="settings-form"><div class="fields">${field("Organization name", "name", "", "text", `required minlength="2" maxlength="100" value="${esc(o.name)}"`)}${field("Industry", "industry", "", "text", `required maxlength="80" value="${esc(o.industry)}"`)}${field("Assistant name", "assistant_name", "", "text", `required minlength="2" maxlength="60" value="${esc(o.assistant_name)}"`)}<label class="field">Style guidance<textarea name="guidance" required maxlength="1000">${esc(o.guidance)}</textarea><small>Used in cloud generation. Offline mode quotes sources directly.</small></label></div><div class="form-actions">${submitButton()}</div></form></section></div>`;
  bindForm("#settings-form", async (v) => {
    state.me.organization = await api("/organization", {
      method: "PUT",
      body: v,
    });
    toast("Workspace settings saved");
    await navigate("settings");
  });
};
pages.account = async () => {
  const u = state.me.user;
  $("#main").innerHTML =
    heading(
      "Your personal workspace access",
      "Your account",
      "Change your password and revoke old credentials.",
    ) +
    `<div class="split-form"><section class="panel"><h2>${esc(u.name)}</h2><p class="muted">${esc(u.email)}<br>${esc(u.department)} · ${esc(u.role)}</p><p class="note">A password change signs out other sessions and revokes every API token for this account. Your current browser gets a new session.</p></section><section class="panel"><h2>Change password</h2><form id="password-form"><div class="fields">${field("Current password", "current_password", "", "password", 'required minlength="12" maxlength="128" autocomplete="current-password"')}${field("New password", "new_password", "", "password", 'required minlength="12" maxlength="128" autocomplete="new-password"')}</div><div class="form-actions">${submitButton("Change password")}</div></form></section></div>`;
  bindForm("#password-form", async (v, f) => {
    const r = await api("/account/password", { method: "POST", body: v });
    state.csrf = r.csrf;
    f.reset();
    toast(r.message);
  });
};
window.addEventListener("DOMContentLoaded", async () => {
  try {
    state.me = await api("/me");
    state.csrf = state.me.csrf;
    await navigate("missions");
  } catch (_) {
    authView();
  }
});
