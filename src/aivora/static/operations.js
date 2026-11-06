"use strict";
(() => {
  navItems.unshift(
    ["missions", "◈", "Mission Control"],
    ["agent_studio", "✧", "Agent Studio"],
    ["business_data", "▥", "Business data"],
    ["tool_connections", "⊞", "Connected tools"],
    ["op_approvals", "✓", "Action approvals"],
    ["work_board", "▦", "Work board"],
    ["mission_triggers", "◷", "Mission triggers"],
  );
  const ops = { selected: null, poll: null, detail: null };
  $("#close-dialog").addEventListener("click", () => {
    if (
      state.me &&
      state.page === "missions" &&
      ops.selected &&
      ["queued", "running", "waiting_provider"].includes(ops.detail?.status)
    )
      handle(() => showMission(ops.selected))();
  });
  window.addEventListener("aivora:session-reset", () => {
    clearTimeout(ops.poll);
    ops.selected = null;
    ops.detail = null;
  });
  const handle =
    (fn) =>
    async (...args) => {
      try {
        await fn(...args);
      } catch (e) {
        if (!(e instanceof CancelledRequest)) toast(e.message, true);
      }
    };
  const modeLabel = (m) =>
    m === "ai" ? "Live AI agents" : "Deterministic evidence mode";
  const userAdmin = () => state.me?.user.role === "admin";
  const opPost = (path, body) =>
    api("/ops" + path, { method: "POST", ...(body ? { body } : {}) });
  function receiptButton(container, operation, refresh) {
    if (operation.status !== "uncertain") return;
    const button = document.createElement("button");
    button.className = "button secondary small";
    button.textContent = "Verify correlated receipt";
    button.onclick = handle(async () => {
      const result = await opPost("/operations/" + operation.id + "/reconcile");
      toast(result.message, !result.verified);
      await refresh();
    });
    container.append(button);
  }
  const openMission = async (id) => {
    ops.selected = id;
    await navigate("missions");
  };
  const sourceName = (evidence, id) =>
    evidence.find((e) => e.id === id)?.title || short(id);
  function findings(output, evidence) {
    return (output?.findings || [])
      .map(
        (f) =>
          `<div class="finding">${badge(f.category)} ${esc(f.statement)}<div class="finding-sources">${f.evidence_ids.map((id) => `<button class="evidence-link" data-evidence="${esc(id)}">${esc(sourceName(evidence, id))} ↗</button>`).join("")}</div></div>`,
      )
      .join("");
  }
  function evidenceButtons(evidence) {
    document.querySelectorAll("[data-evidence]").forEach(
      (b) =>
        (b.onclick = () => {
          const value = evidence.find((v) => v.id === b.dataset.evidence);
          if (value)
            dialog(
              `<div class="eyebrow">${esc(value.type)} evidence</div><h2>${esc(value.title)}</h2>${value.type === "document" ? `<div class="detail-text">${esc(value.text)}</div><p class="muted">Page ${value.page} · version ${value.version}</p>` : `<pre>${esc(JSON.stringify(value.profile || value.data, null, 2))}</pre>`}`,
            );
        }),
    );
  }
  async function newMission(template) {
    const [catalog, teams, data, connections] = await Promise.all([
      api("/ops/catalog"),
      api("/ops/teams"),
      api("/ops/datasets"),
      api("/ops/connectors"),
    ]);
    const chosen = template || catalog.templates[0];
    dialog(
      `<div class="eyebrow">Multi-agent operations</div><h2>Give your team an objective.</h2><form id="mission-form"><div class="fields">${field("Mission title", "title", "", "text", `required minlength="3" maxlength="150" value="${esc(chosen.title)}"`)}<label class="field">Business objective<textarea name="objective" required minlength="15" maxlength="5000" rows="5">${esc(chosen.objective)}</textarea></label><div class="form-grid"><label class="field">Agent team<select name="team_id">${teams.map((t) => `<option value="${esc(t.id)}">${esc(t.name)}</option>`).join("")}</select></label><label class="field">Execution mode<select name="mode"><option value="ai" ${catalog.ai_ready ? "selected" : ""} ${!catalog.ai_ready ? "disabled" : ""}>Live AI agents</option><option value="evidence" ${!catalog.ai_ready ? "selected" : ""}>Evidence tools only · no AI reasoning</option></select></label><label class="field wide">Business dataset (optional)<select name="dataset_id" id="mission-dataset"><option value="">No dataset</option>${data.map((d) => `<option value="${esc(d.id)}">${esc(d.title)} · ${d.profile.row_count} rows</option>`).join("")}</select></label><label class="field">Group rows by<select name="group_by" id="mission-group"><option value="">No grouping</option></select></label><label class="field">Numeric metric<select name="metric" id="mission-metric"><option value="">Counts only</option></select></label></div><label class="field">Read context from selected tools</label><div class="checklist">${
        connections
          .filter((c) => c.enabled)
          .map(
            (c) =>
              `<label><input type="checkbox" name="connector_ids" value="${esc(c.id)}">${esc(c.name)}</label>`,
          )
          .join("") ||
        '<span class="muted">No connected tools. Knowledge and datasets still work.</span>'
      }</div>${field("Conservative per-mission token reservation limit", "max_tokens", "120000", "number", 'required value="120000" min="12000" max="250000"')}</div><p class="mission-form-note">${catalog.ai_ready ? `AI model: ${esc(catalog.model.provider)} / ${esc(catalog.model.model)}. Selected evidence is sent to this provider.` : "Configure a company model in Agent Studio for real AI reasoning. Evidence mode performs extraction, arithmetic and a conservative template plan only."} Agent writes remain private drafts until you submit them to a separate reviewer.</p><div class="form-actions">${submitButton("Create mission")}</div></form>`,
    );
    $("#mission-dataset").onchange = (e) => {
      const profile = data.find((d) => d.id === e.target.value)?.profile;
      $("#mission-group").innerHTML =
        '<option value="">No grouping</option>' +
        (profile
          ? Object.keys(profile.columns)
              .map((c) => `<option value="${esc(c)}">${esc(c)}</option>`)
              .join("")
          : "");
      $("#mission-metric").innerHTML =
        '<option value="">Counts only</option>' +
        (profile
          ? Object.entries(profile.columns)
              .filter(([, v]) => v.type === "numeric")
              .map(([c]) => `<option value="${esc(c)}">${esc(c)}</option>`)
              .join("")
          : "");
    };
    const key = crypto.randomUUID();
    bindForm("#mission-form", async (v, f) => {
      const body = {
        title: v.title,
        objective: v.objective,
        team_id: v.team_id,
        mode: v.mode,
        dataset_ids: v.dataset_id ? [v.dataset_id] : [],
        connector_ids: new FormData(f).getAll("connector_ids"),
        group_by: v.group_by,
        metric: v.metric,
        max_tokens: Number(v.max_tokens),
        request_key: key,
      };
      const result = await opPost("/missions", body);
      $("#dialog").close();
      await openMission(result.id);
      toast("Mission queued. Run now or let the operations worker pick it up.");
    });
  }
  function startMission(id) {
    const epoch = state.sessionEpoch;
    opPost("/missions/" + id + "/run")
      .then(() => {
        if (
          state.me &&
          state.sessionEpoch === epoch &&
          state.page === "missions" &&
          ops.selected === id
        )
          showMission(id);
      })
      .catch((e) => {
        if (!(e instanceof CancelledRequest)) toast(e.message, true);
      });
    setTimeout(() => {
      if (
        state.me &&
        state.sessionEpoch === epoch &&
        state.page === "missions" &&
        ops.selected === id
      )
        showMission(id);
    }, 300);
  }
  pages.missions = async () => {
    clearTimeout(ops.poll);
    if (ops.selected) return showMission(ops.selected);
    const [missions, catalog] = await Promise.all([
      api("/ops/missions"),
      api("/ops/catalog"),
    ]);
    $("#main").innerHTML =
      heading(
        "Your organization’s agent operating layer",
        "From objective to accountable work.",
        "A team of specialists that investigates, analyzes, plans and reviews before anything is executed.",
        '<button class="button" id="new-mission">＋ New mission</button>',
      ) +
      `<section class="mission-banner"><div><div class="eyebrow">Cross-department operations</div><h2>Give the problem to a team.<br>Keep control of the outcome.</h2><p>Combine live business context, procedures and quantitative data. Watch specialist agents collaborate, inspect their evidence, approve actions and track the work to resolution.</p></div><button class="button" id="mission-demo">Explore mission templates ↗</button></section><div class="stats">${[
        ["Your missions", missions.length, "Private to your account"],
        [
          "Working",
          missions.filter((m) =>
            ["queued", "running", "waiting_provider"].includes(m.status),
          ).length,
          "Durable agent checkpoints",
        ],
        [
          "Briefs ready",
          missions.filter((m) =>
            ["ready", "review_required"].includes(m.status),
          ).length,
          "Review findings before acting",
        ],
        [
          "Execution mode",
          catalog.ai_ready ? "AI ready" : "Evidence tools",
          catalog.ai_ready
            ? catalog.model.provider + " / " + catalog.model.model
            : "Configure a model in Agent Studio",
        ],
      ]
        .map(
          ([l, v, n]) =>
            `<div class="stat"><div class="stat-label">${esc(l)}</div><div class="stat-value">${esc(v)}</div><div class="stat-note">${esc(n)}</div></div>`,
        )
        .join(
          "",
        )}</div><div class="mission-templates">${catalog.templates.map((t, i) => `<button class="mission-template" data-template="${esc(t.id)}"><span class="icon">${["⌁", "◎", "↗", "▥"][i]}</span><strong>${esc(t.title)}</strong><small>Research → analyze → plan → review</small></button>`).join("")}</div><section class="panel"><div class="panel-title"><h2>Your missions</h2><span class="inline-count">${missions.length} runs</span></div>${missions.length ? missions.map((m) => `<div class="mission-row"><div><button class="text-button" data-mission="${esc(m.id)}"><strong>${esc(m.title)}</strong></button><p>${esc(m.objective.slice(0, 190))}</p><div class="agent-metrics"><span>${modeLabel(m.mode)}</span><span>${m.completed_agents}/${m.total_agents} agents complete</span><span>${fmtDate(m.created)}</span></div><div class="progress-track"><progress aria-label="Completed agents" max="${m.total_agents}" value="${m.completed_agents}"></progress></div></div><div class="mission-row-meta">${badge(m.status)}<button class="text-button" data-mission="${esc(m.id)}">Open ↗</button></div></div>`).join("") : empty("Start with a real business objective", "Attach data, use your organization’s knowledge and choose an agent team.", "◈")}</section>`;
    $("#new-mission").onclick = handle(() => newMission());
    $("#mission-demo").onclick = handle(() => newMission(catalog.templates[0]));
    document
      .querySelectorAll("[data-template]")
      .forEach(
        (b) =>
          (b.onclick = handle(() =>
            newMission(
              catalog.templates.find((t) => t.id === b.dataset.template),
            ),
          )),
      );
    document
      .querySelectorAll("[data-mission]")
      .forEach((b) => (b.onclick = () => openMission(b.dataset.mission)));
  };
  async function showMission(id) {
    clearTimeout(ops.poll);
    const m = await api("/ops/missions/" + id);
    if (state.page !== "missions" || ops.selected !== id) return;
    ops.detail = m;
    const report = m.agents.find((a) => a.role === "writer")?.output;
    const reviewer = m.agents.find((a) => a.role === "reviewer")?.output;
    $("#main").innerHTML =
      heading(
        "Mission workspace",
        m.title,
        m.objective,
        `<div class="mission-top-actions"><button class="button secondary small" id="mission-back">← All missions</button>${["queued", "running", "waiting_provider"].includes(m.status) ? `<button class="button small" id="mission-run" ${m.status === "running" ? "disabled" : ""}>${m.status === "running" ? "Agents working…" : "Run now"}</button>` : ""}${m.status === "failed" ? '<button class="button small" id="mission-retry">Resume checkpoints</button>' : ""}${["queued", "running", "waiting_provider", "failed", "ready", "review_required"].includes(m.status) ? '<button class="button secondary small" id="mission-cancel">Cancel</button>' : ""}<a class="button secondary small" href="/api/ops/missions/${esc(id)}/export">Export brief ↗</a></div>`,
      ) +
      `${!m.access_valid ? '<div class="note">Source access or document versions changed. Outputs and actions are hidden; create a new mission with current evidence.</div>' : ""}<div class="agent-metrics">${badge(m.status)}<span>${modeLabel(m.mode)}</span><span>${m.model_calls} model calls</span><span>${m.input_tokens} input / ${m.output_tokens} output tokens</span><span>Conservative reservation ${m.reserved_tokens} / ${m.max_tokens}</span></div>${m.error_code ? `<div class="note">Execution stopped: <code>${esc(m.error_code)}</code>. Completed agent checkpoints are preserved. Resolve the cause before resuming.</div>` : ""}<div class="agent-dag">${m.agents.map((a, i) => `<button class="agent-node ${esc(a.status)}" data-agent="${esc(a.id)}"><div class="agent-node-head"><span class="agent-number">${String(i + 1).padStart(2, "0")} · ${esc(a.role)}</span>${badge(a.status)}</div><strong>${esc(a.name)}</strong><small>${a.depends_on.length ? "After " + a.depends_on.map(esc).join(" + ") : "Mission entry point"} · attempt ${a.attempts}</small></button>`).join("")}</div><div class="mission-layout"><div><section class="panel"><div class="panel-title"><h2>Decision brief</h2>${report ? badge(report.verdict) : '<span class="inline-count">Waiting for the writing agent</span>'}</div>${report ? `<div class="agent-summary">${esc(report.summary)}</div>${findings(report, m.evidence)}${report.risks.length ? `<h3>Risks and limitations</h3><ul class="risk-list">${report.risks.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : ""}${report.questions.length ? `<h3>Questions to resolve</h3><ul>${report.questions.map((q) => `<li>${esc(q)}</li>`).join("")}</ul>` : ""}` : empty("Your team’s deliverable will appear here", "The final writer combines specialist findings and review concerns.", "✧")}</section>${reviewer ? `<section class="panel"><div class="panel-title"><h2>Independent review</h2>${badge(reviewer.verdict)}</div><div class="agent-summary">${esc(reviewer.summary)}</div><ul class="risk-list">${reviewer.risks.map((r) => `<li>${esc(r)}</li>`).join("")}</ul></section>` : ""}<section class="panel"><div class="panel-title"><h2>Proposed actions</h2><span class="inline-count">${m.operations.length} work packages</span></div>${m.operations.length ? m.operations.map((o) => `<div class="operation-card"><div class="request-top"><h3>${esc(o.title)}</h3>${badge(o.status)}</div><p>${esc(o.arguments.description)}</p><div class="request-meta"><span>${esc(o.kind)}</span><span>${esc(o.department)}</span><span>Arguments ${short(o.arguments_hash)}</span></div>${o.status === "draft" ? `<button class="button secondary small" data-submit-operation="${esc(o.id)}">Review & submit for approval</button>` : ""}${Object.keys(o.result).length ? `<pre>${esc(JSON.stringify(o.result, null, 2))}</pre>` : ""}</div>`).join("") : empty("No proposed actions yet", "Agents draft; people review; approved tools execute.")}</section></div><aside><section class="panel"><div class="panel-title"><h2>Evidence ledger</h2></div>${m.evidence.length ? m.evidence.map((e) => `<div class="source-card"><span class="eyebrow">${esc(e.type)}</span><br><button class="text-button" data-evidence="${esc(e.id)}">${esc(e.title)} ↗</button>${e.profile ? `<div class="sub">${e.profile.row_count} rows · server-computed metrics</div>` : ""}</div>`).join("") : empty("No attached evidence", "The team must distinguish assumptions from facts.")}</section><section class="panel"><div class="panel-title"><h2>Execution timeline</h2></div><div class="timeline">${m.events
        .slice()
        .reverse()
        .map(
          (e) =>
            `<div class="timeline-item"><strong>${esc(e.event)}</strong><small>${esc(e.agent_id || e.detail)} · ${fmtDate(e.created)}</small></div>`,
        )
        .join(
          "",
        )}</div></section><p class="mission-runtime-note">Research and analysis can run concurrently. Every specialist output is persisted before dependants continue. A worker restart reuses completed checkpoints.</p></aside></div>`;
    if (m.can_complete && m.status !== "completed") {
      const close = document.createElement("button");
      close.className = "button small";
      close.id = "mission-complete";
      close.textContent = "Record outcome & close";
      $(".mission-top-actions").append(close);
      close.onclick = () => {
        dialog(
          `<h2>Record the operational outcome</h2><p>The report and tool receipts are separate from business success. Record what the organization actually changed or learned.</p><form id="mission-outcome-form"><label class="field">Observed outcome<textarea name="outcome" required minlength="15" maxlength="3000"></textarea></label><div class="form-actions">${submitButton("Close objective with outcome")}</div></form>`,
        );
        bindForm("#mission-outcome-form", async (v) => {
          await opPost("/missions/" + id + "/complete", v);
          $("#dialog").close();
          toast("Objective closed with an owner-recorded outcome");
          await showMission(id);
        });
      };
    }
    if (["ready", "review_required"].includes(m.status) && m.iteration < 2) {
      const refine = document.createElement("button");
      refine.className = "button secondary small";
      refine.textContent = "Refine with feedback";
      $(".mission-top-actions").append(refine);
      refine.onclick = () => {
        dialog(
          `<h2>Improve the plan with human feedback</h2><p>Research and analysis checkpoints are retained. The planner, reviewer and writer will run again. Old draft actions are withdrawn and artifact versions stay in history.</p><form id="mission-refinement-form"><label class="field">Required changes<textarea name="feedback" required minlength="15" maxlength="2000"></textarea></label><div class="form-actions">${submitButton("Queue revised plan")}</div></form>`,
        );
        bindForm("#mission-refinement-form", async (v) => {
          await opPost("/missions/" + id + "/refine", v);
          $("#dialog").close();
          await showMission(id);
          startMission(id);
        });
      };
    }
    const historyButton = document.createElement("button");
    historyButton.className = "text-button";
    historyButton.textContent = "Artifact history · round " + m.iteration;
    $(".agent-metrics").append(historyButton);
    historyButton.onclick = handle(async () => {
      const versions = await api("/ops/missions/" + id + "/artifacts");
      dialog(
        `<h2>Versioned agent artifacts</h2>${versions.map((v) => `<details class="request-card"><summary>${esc(v.agent_id)} · round ${v.iteration} · ${short(v.content_hash)}</summary><div class="detail-text">${esc(v.output.summary)}</div><small>${fmtDate(v.created)}</small></details>`).join("") || empty("No published artifacts yet", "Only validated agent results are checkpointed here.")}`,
      );
    });
    if (m.outcome) {
      const section = document.createElement("section");
      section.className = "panel";
      section.innerHTML = `<div class="eyebrow">Owner-recorded operational outcome</div><h2>What changed</h2><div class="detail-text">${esc(m.outcome)}</div>`;
      $("#main").append(section);
    }
    document.querySelectorAll(".operation-card").forEach((card, index) => {
      const o = m.operations[index];
      if (o) receiptButton(card, o, () => showMission(id));
      if (o && ["draft", "pending", "failed", "blocked"].includes(o.status)) {
        const button = document.createElement("button");
        button.className = "text-button";
        button.textContent = "Withdraw this proposal";
        button.onclick = handle(async () => {
          await opPost("/operations/" + o.id + "/withdraw");
          await showMission(id);
        });
        card.append(button);
      }
    });
    $("#mission-back").onclick = () => {
      ops.selected = null;
      pages.missions();
    };
    if (m.status === "waiting_provider" && m.retry_at) {
      const message = document.createElement("p");
      message.className = "note";
      message.textContent =
        "Provider quota backoff. Completed checkpoints are preserved; next eligible retry: " +
        fmtDate(m.retry_at);
      $(".agent-dag").before(message);
      if (m.retry_at <= Date.now() / 1000) startMission(id);
    }
    $("#mission-run")?.addEventListener("click", () => startMission(id));
    $("#mission-retry")?.addEventListener(
      "click",
      handle(async () => {
        await opPost("/missions/" + id + "/retry");
        await showMission(id);
        startMission(id);
      }),
    );
    $("#mission-cancel")?.addEventListener(
      "click",
      handle(async () => {
        await opPost("/missions/" + id + "/cancel");
        await showMission(id);
      }),
    );
    document.querySelectorAll("[data-agent]").forEach(
      (b) =>
        (b.onclick = () => {
          const a = m.agents.find((a) => a.id === b.dataset.agent);
          dialog(
            `<div class="eyebrow">${esc(a.role)} · ${esc(a.status)}</div><h2>${esc(a.name)}</h2>${a.output ? `<div class="agent-summary">${esc(a.output.summary)}</div>${findings(a.output, m.evidence)}<ul class="risk-list">${a.output.risks.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>` : empty("No published output", "Queued, failed or inaccessible output is not presented as a result.")}`,
          );
          evidenceButtons(m.evidence);
        }),
    );
    evidenceButtons(m.evidence);
    document.querySelectorAll("[data-submit-operation]").forEach(
      (b) =>
        (b.onclick = () => {
          const o = m.operations.find(
            (o) => o.id === b.dataset.submitOperation,
          );
          dialog(
            `<h2>Review the exact action</h2><h3>${esc(o.title)}</h3><div class="detail-text">${esc(o.arguments.description)}</div><p class="muted">Tool: ${esc(o.kind)} · Department: ${esc(o.department)}</p><p class="note">Submitting shares this exact action text with authorized approvers. Review source-sensitive content and the independent reviewer’s concerns first. No action executes at submission.</p><form id="submit-operation-form"><label><input type="checkbox" required> I reviewed the action and consent to sharing it with approvers.</label><div class="form-actions">${submitButton("Submit exact action")}</div></form>`,
          );
          bindForm("#submit-operation-form", async () => {
            await opPost("/missions/" + id + "/submit-actions", {
              operation_ids: [o.id],
              acknowledge_review: true,
            });
            $("#dialog").close();
            toast("Action submitted to a separate reviewer");
            await showMission(id);
          });
        }),
    );
    if (["queued", "running", "waiting_provider"].includes(m.status)) {
      const epoch = state.sessionEpoch;
      ops.poll = setTimeout(() => {
        if (
          state.me &&
          state.sessionEpoch === epoch &&
          state.page === "missions" &&
          ops.selected === id &&
          !$("#dialog").open
        )
          handle(() => showMission(id))();
      }, 1800);
    }
  }

  pages.agent_studio = async () => {
    const [teams, catalog] = await Promise.all([
      api("/ops/teams"),
      api("/ops/catalog"),
    ]);
    $("#main").innerHTML =
      heading(
        "Real specialist roles. Configurable coordination.",
        "Build the team for your objective.",
        "Define agent responsibilities and a validated dependency graph; the platform enforces permissions outside prompts.",
        userAdmin()
          ? '<button class="button" id="team-new">＋ Create agent team</button>'
          : "",
      ) +
      `<div class="model-state"><strong>${catalog.ai_ready ? "Company AI model configured" : "Company AI model not configured"}</strong><br>${esc(catalog.model.provider)} / ${esc(catalog.model.model || "none")} · ${catalog.ai_ready ? "Live missions make separate validated model calls for each specialist." : "Evidence mode remains available and is clearly labeled as deterministic."}</div>${teams.map((t) => `<section class="panel"><div class="panel-title"><div><h2>${esc(t.name)}</h2><p class="muted">${esc(t.description)}</p></div>${userAdmin() ? `<button class="text-button" data-team="${esc(t.id)}">${t.id === "default" ? "Customize a copy" : "Edit team"} ↗</button>` : ""}</div><div class="agent-dag">${t.definition.agents.map((a, i) => `<div class="agent-node"><div class="agent-node-head"><span class="agent-number">${i + 1} · ${esc(a.role)}</span></div><strong>${esc(a.name)}</strong><p class="muted">${esc(a.instructions)}</p><small>Depends on: ${a.depends_on.map(esc).join(", ") || "START"}</small></div>`).join("")}</div></section>`).join("")}${userAdmin() ? `<section class="panel"><div class="panel-title"><h2>Company model configuration</h2></div><p class="muted">Credentials are encrypted on the server and never included in agent prompts or returned by the API. Model changes are versioned; running missions will not silently switch models.</p><form id="model-form"><div class="form-grid"><label class="field">Provider<select name="provider"><option value="groq">Groq</option><option value="gemini">Gemini</option></select></label>${field("Model ID", "model", "Model available in your account", "text", 'required maxlength="100"')}${field("API key", "api_key", "", "password", 'required minlength="8" maxlength="2000" autocomplete="off"')}</div><div class="form-actions">${submitButton("Save encrypted model configuration")}</div></form></section>` : ""}<div class="note">The model can recommend and draft. Identity, source access, budgets, allowed destinations and approval rules are enforced in application code.</div>`;
    function editTeam(team) {
      dialog(
        `<h2>${team.id && team.id !== "default" ? "Edit agent team" : "Create an agent team"}</h2><form id="agent-team-form"><div class="fields">${field("Team name", "name", "", "text", `required minlength="2" maxlength="100" value="${esc(team.name)}"`)}${field("Description", "description", "", "text", `required minlength="5" maxlength="1000" value="${esc(team.description)}"`)}<label class="field agent-editor">Agent definitions (JSON)<textarea name="definition" required>${esc(JSON.stringify(team.definition, null, 2))}</textarea><small>3–8 agents; unique IDs; no dependency cycles; final writer must receive every agent’s output; reviewer must inspect every planner.</small></label></div><div class="form-actions">${submitButton("Save agent team")}</div></form>`,
      );
      bindForm("#agent-team-form", async (v) => {
        let definition;
        try {
          definition = JSON.parse(v.definition);
        } catch (_) {
          throw new Error("Agent definitions must be valid JSON");
        }
        const body = { name: v.name, description: v.description, definition };
        await api(
          "/ops/teams" +
            (team.id && team.id !== "default" ? "/" + team.id : ""),
          { method: team.id && team.id !== "default" ? "PUT" : "POST", body },
        );
        $("#dialog").close();
        toast("Validated agent team saved");
        await pages.agent_studio();
      });
    }
    $("#team-new")?.addEventListener("click", () =>
      editTeam({ ...catalog.default_team, name: "My operations team" }),
    );
    document
      .querySelectorAll("[data-team]")
      .forEach(
        (b) =>
          (b.onclick = () =>
            editTeam(teams.find((t) => t.id === b.dataset.team))),
      );
    bindForm("#model-form", async (v, f) => {
      await api("/ops/model", { method: "PUT", body: v });
      f.reset();
      toast("Encrypted company model configuration saved");
      state.me = await api("/me");
      state.csrf = state.me.csrf;
      await navigate("agent_studio");
    });
  };

  pages.business_data = async () => {
    const data = await api("/ops/datasets");
    $("#main").innerHTML =
      heading(
        "Quantitative tools, beyond conversation",
        "Make decisions from actual business data.",
        "Upload an operational CSV. Statistics and group breakdowns are computed by code, then interpreted by the agent team.",
        userAdmin()
          ? '<button class="button" id="dataset-new">＋ Upload dataset</button>'
          : "",
      ) +
      `<div class="cards">${data.map((d) => `<article class="card"><div class="card-icon">▥</div><h2>${esc(d.title)}</h2>${badge(d.visibility)}<div class="data-metrics"><div class="data-metric"><strong>${d.profile.row_count}</strong><small>rows</small></div><div class="data-metric"><strong>${Object.keys(d.profile.columns).length}</strong><small>columns</small></div><div class="data-metric"><strong>${Object.values(d.profile.columns).filter((c) => c.type === "numeric").length}</strong><small>numeric metrics</small></div></div><div class="card-footer"><button class="text-button" data-dataset="${esc(d.id)}">Explore computed profile ↗</button>${userAdmin() ? `<button class="text-button" data-delete-data="${esc(d.id)}">Delete</button>` : ""}</div></article>`).join("") || empty("Connect the numbers to the problem", "CSV examples: support queues, onboarding stages, service timings or operating costs.", "▥")}</div><p class="note">No model-generated SQL or Python executes. CSV values are data, not instructions. A mission’s group-by and metric selections are validated against the dataset schema.</p>`;
    $("#dataset-new")?.addEventListener("click", () => {
      dialog(
        `<h2>Add business data</h2><form id="dataset-form"><div class="fields">${field("Dataset title", "title", "Support queue · November", "text", 'required minlength="2" maxlength="150"')}<label class="field">CSV file<input name="file" type="file" accept=".csv" required><small>UTF-8 · maximum 2 MB / 10,000 rows / 60 columns</small></label><label class="field">Visibility<select name="visibility"><option value="organization">Organization</option><option value="department">Your department</option><option value="admin">Administrators</option></select></label></div><div class="form-actions">${submitButton("Upload and profile")}</div></form>`,
      );
      bindForm("#dataset-form", async (_, f) => {
        await api("/ops/datasets", { method: "POST", body: new FormData(f) });
        $("#dialog").close();
        toast("Dataset profiled");
        await pages.business_data();
      });
    });
    document.querySelectorAll("[data-dataset]").forEach(
      (b) =>
        (b.onclick = () => {
          const d = data.find((d) => d.id === b.dataset.dataset);
          dialog(
            `<div class="eyebrow">Server-computed analysis</div><h2>${esc(d.title)}</h2><p class="muted">${d.profile.row_count} rows · ${esc(d.department)}</p>${Object.entries(
              d.profile.columns,
            )
              .map(
                ([name, c]) =>
                  `<div class="column-profile"><strong>${esc(name)}</strong> ${badge(c.type)}<p>${c.unique} unique · ${c.missing} missing${c.type === "numeric" ? ` · total ${esc(c.total)} · mean ${esc(c.mean)} · range ${esc(c.min)}–${esc(c.max)}` : ""}</p>${c.categories ? `<div class="metric-bars">${c.categories.map((x) => `<div class="metric-bar"><span>${esc(x.label)}</span><progress aria-label="${esc(x.label)} row count" max="${d.profile.row_count}" value="${x.count}"></progress><span>${x.count}</span></div>`).join("")}</div>` : ""}</div>`,
              )
              .join("")}`,
          );
        }),
    );
    document.querySelectorAll("[data-delete-data]").forEach(
      (b) =>
        (b.onclick = () => {
          dialog(
            '<h2>Delete this dataset?</h2><p>Existing mission outputs that depend on it will become inaccessible.</p><button class="button danger" id="dataset-delete-confirm">Delete dataset</button>',
          );
          $("#dataset-delete-confirm").onclick = handle(async () => {
            await api("/ops/datasets/" + b.dataset.deleteData, {
              method: "DELETE",
            });
            $("#dialog").close();
            await pages.business_data();
          });
        }),
    );
  };

  pages.tool_connections = async () => {
    const connections = await api("/ops/connectors");
    $("#main").innerHTML =
      heading(
        "Connect company systems, keep scoped authority",
        "Tools the team can actually use.",
        "Read business context and execute approved actions against fixed destinations.",
        userAdmin()
          ? '<button class="button" id="connector-new">＋ Connect a tool</button>'
          : "",
      ) +
      `<div class="cards">${connections.map((c) => `<article class="card"><div class="card-icon">${c.kind === "github" ? "⌘" : "#"}</div><h2>${esc(c.name)}</h2><p>${esc(c.kind)} · ${esc(c.config.repository || c.config.channel)}</p>${badge(c.enabled ? "enabled" : "paused")}<p>Department: ${esc(c.department)} · revision ${c.revision}</p><div class="card-footer">${userAdmin() ? `<button class="text-button" data-connector-test="${esc(c.id)}">Check read/configuration</button><button class="text-button" data-connector-toggle="${esc(c.id)}">${c.enabled ? "Pause" : "Enable"}</button>` : ""}</div></article>`).join("") || empty("Bring the system of record into the workflow", "Connect GitHub issues or an approved Slack destination. Use signed incoming hooks for other business systems.", "⊞")}</div><section class="panel"><h2>Available execution capabilities</h2><div class="quick-grid"><div class="quick-card"><strong>Internal work items</strong><small>Approved work becomes a durable task with department, status and recorded outcome.</small></div><div class="quick-card"><strong>GitHub issues</strong><small>Read open issues from one configured repository; create approved issues with an operation correlation marker.</small></div><div class="quick-card"><strong>Slack messages</strong><small>Send approved text to one configured channel. No channel history is ingested.</small></div><div class="quick-card"><strong>Signed business events</strong><small>Existing applications trigger mission templates through HMAC-signed, replay-protected hooks.</small></div></div></section><p class="note">Credentials are encrypted at rest. A connector is department-scoped and never gives an agent an arbitrary URL. Uncertain delivery is recorded for reconciliation; the worker will not blindly resend it.</p>`;
    $("#connector-new")?.addEventListener("click", () => {
      dialog(
        `<h2>Connect a company tool</h2><form id="connector-form"><div class="fields">${field("Connection name", "name", "Engineering issue tracker", "text", 'required minlength="2" maxlength="100"')}<label class="field">Tool<select name="kind" id="connector-kind"><option value="github">GitHub repository</option><option value="slack">Slack channel</option></select></label>${field("Fixed target", "target", "owner/repository or Slack channel ID", "text", 'required maxlength="210"')}${field("Handling department", "department", "", "text", `required maxlength="60" value="${esc(state.me.user.department)}"`)}${field("Scoped access token", "token", "", "password", 'required minlength="8" maxlength="2000" autocomplete="off"')}</div><p class="mission-form-note">Use a token with access limited to the intended repository or channel. It is not shown again or sent to the language model.</p><div class="form-actions">${submitButton("Save encrypted connection")}</div></form>`,
      );
      bindForm("#connector-form", async (v) => {
        await opPost("/connectors", {
          name: v.name,
          kind: v.kind,
          department: v.department,
          config:
            v.kind === "github"
              ? { repository: v.target }
              : { channel: v.target },
          token: v.token,
        });
        $("#dialog").close();
        toast("Encrypted connection saved");
        await pages.tool_connections();
      });
    });
    document.querySelectorAll("[data-connector-test]").forEach(
      (b) =>
        (b.onclick = handle(async () => {
          const r = await opPost(
            "/connectors/" + b.dataset.connectorTest + "/test",
          );
          dialog(
            `<h2>${esc(r.status.replaceAll("_", " "))}</h2><pre>${esc(JSON.stringify(r.context, null, 2))}</pre>`,
          );
        })),
    );
    document.querySelectorAll("[data-connector-toggle]").forEach(
      (b) =>
        (b.onclick = handle(async () => {
          await opPost("/connectors/" + b.dataset.connectorToggle + "/toggle");
          await pages.tool_connections();
        })),
    );
  };

  pages.op_approvals = async () => {
    const operations = await api("/ops/approvals");
    $("#main").innerHTML =
      heading(
        "A boundary between recommendations and effects",
        "Approve the action, not a vague intention.",
        "Review immutable arguments, the target and handling department before execution.",
      ) +
      `<div class="note">The requester cannot approve their own action. Shared arguments are immutable. Permissions and connector revisions are checked again immediately before dispatch.</div><section class="panel"><div class="panel-title"><h2>Action inbox</h2><span class="inline-count">${operations.length} visible actions</span></div>${operations.map((o) => `<article class="operation-card"><div class="request-top"><h3>${esc(o.title)}</h3>${badge(o.status)}</div><p>${esc(o.arguments.description)}</p><div class="request-meta"><span>${esc(o.kind)}</span><span>${esc(o.department)}</span><span>${o.mine ? "Your submitted action" : "Review queue"}</span><span>Hash ${short(o.arguments_hash)}</span></div>${Object.keys(o.result).length ? `<pre>${esc(JSON.stringify(o.result, null, 2))}</pre>` : ""}<div class="request-bottom">${o.can_review ? `<button class="button small" data-operation="${esc(o.id)}" data-decision="approve">Approve & execute</button><button class="button secondary small" data-operation="${esc(o.id)}" data-decision="reject">Reject</button>` : ""}${o.status === "uncertain" ? '<span class="muted">Verify the target system; automatic resend is disabled.</span>' : ""}</div></article>`).join("") || empty("No shared actions to review", "Mission owners review and explicitly submit their draft actions first.", "✓")}</section>`;
    document.querySelectorAll("[data-operation]").forEach(
      (b) =>
        (b.onclick = () => {
          const o = operations.find((o) => o.id === b.dataset.operation);
          dialog(
            `<h2>${b.dataset.decision === "approve" ? "Approve these exact arguments?" : "Reject this action?"}</h2><pre>${esc(JSON.stringify(o.arguments, null, 2))}</pre><form id="operation-decision-form"><label class="field">Reviewer note<textarea name="note" maxlength="500"></textarea></label><div class="form-actions">${submitButton(b.dataset.decision === "approve" ? "Approve & execute exact action" : "Reject action")}</div></form>`,
          );
          bindForm("#operation-decision-form", async (v) => {
            const result = await opPost("/operations/" + o.id + "/decision", {
              decision: b.dataset.decision,
              note: v.note,
            });
            $("#dialog").close();
            toast("Action status: " + result.status);
            await pages.op_approvals();
          });
        }),
    );
    document
      .querySelectorAll(".operation-card")
      .forEach((card, index) =>
        receiptButton(card, operations[index], pages.op_approvals),
      );
  };

  pages.work_board = async () => {
    const items = await api("/ops/work-items");
    $("#main").innerHTML =
      heading(
        "Execution only counts when work moves",
        "Track the operational outcome.",
        "Approved internal work packages become durable tasks. Marking done requires a concrete outcome.",
      ) +
      `<div class="operations-board">${[
        "planned",
        "in_progress",
        "blocked",
        "done",
      ]
        .map(
          (status) =>
            `<section class="board-column"><h2>${status.replaceAll("_", " ")} <span>${items.filter((w) => w.status === status).length}</span></h2>${
              items
                .filter((w) => w.status === status)
                .map(
                  (w) =>
                    `<article class="work-card">${badge(w.department)}<h3>${esc(w.title)}</h3><p>${esc(w.description)}</p>${w.outcome ? `<p><strong>Outcome:</strong> ${esc(w.outcome)}</p>` : ""}<small class="muted">Updated ${fmtDate(w.updated)}</small>${w.can_update ? `<br><button class="text-button" data-work-item="${esc(w.id)}">Update status & outcome ↗</button>` : ""}</article>`,
                )
                .join("") || '<p class="muted">No work in this stage.</p>'
            }</section>`,
        )
        .join("")}</div>`;
    document.querySelectorAll("[data-work-item]").forEach(
      (b) =>
        (b.onclick = () => {
          const w = items.find((w) => w.id === b.dataset.workItem);
          dialog(
            `<h2>${esc(w.title)}</h2><form id="work-item-form"><div class="fields"><label class="field">Status<select name="status" aria-label="Status">${["planned", "in_progress", "blocked", "done"].map((s) => `<option value="${s}" ${s === w.status ? "selected" : ""}>${s.replaceAll("_", " ")}</option>`).join("")}</select></label><label class="field">Concrete outcome or blocker<textarea name="outcome" maxlength="2000">${esc(w.outcome)}</textarea><small>At least 10 characters are required to mark work done.</small></label></div><div class="form-actions">${submitButton("Record work update")}</div></form>`,
          );
          bindForm("#work-item-form", async (v) => {
            await api("/ops/work-items/" + w.id, { method: "PUT", body: v });
            $("#dialog").close();
            toast("Work outcome recorded");
            await pages.work_board();
          });
        }),
    );
  };

  pages.mission_triggers = async () => {
    const [schedules, hooks, missions] = await Promise.all([
      api("/ops/schedules"),
      api("/ops/hooks"),
      api("/ops/missions"),
    ]);
    $("#main").innerHTML =
      heading(
        "Make the useful workflow repeatable",
        "Missions that start when work happens.",
        "Run an agent team on a schedule or from a signed event in your existing system.",
        '<div class="mission-top-actions"><button class="button" id="schedule-new">＋ Schedule a mission</button><button class="button secondary" id="hook-new">＋ Create event hook</button></div>',
      ) +
      `<div class="grid-two"><section class="panel"><div class="panel-title"><h2>Recurring missions</h2></div>${schedules.map((s) => `<div class="request-card"><div class="request-top"><h3>${esc(s.name)}</h3>${badge(s.enabled ? "enabled" : "paused")}</div><p>Every ${s.interval_hours} hours · next ${fmtDate(s.next_run)}</p><button class="text-button" data-schedule-toggle="${esc(s.id)}">${s.enabled ? "Pause" : "Resume"}</button></div>`).join("") || empty("Schedule an established workflow", "A recurring run is a new mission under your current permissions.")}</section><section class="panel"><div class="panel-title"><h2>Incoming event hooks</h2></div>${hooks.map((h) => `<div class="request-card"><div class="request-top"><h3>${esc(h.name)}</h3>${badge(h.enabled ? "enabled" : "paused")}</div><pre>${esc(h.url)}</pre><small class="muted">HMAC signature + timestamp · stable external event ID</small></div>`).join("") || empty("Connect an existing business system", "Signed events can trigger an escalation, investigation or management review.")}</section></div><div class="note">Run the separate operations worker for unattended processing. Scheduled missions recheck current identity and source access. Invalid schedules pause rather than running with broader permissions. Event hooks reject unsigned, stale or tampered requests.</div>`;
    async function triggerDialog(kind) {
      if (!missions.length) {
        toast(
          "Create a mission first, then reuse its inputs as a trigger template.",
          true,
        );
        return;
      }
      dialog(
        `<h2>${kind === "schedule" ? "Schedule a mission" : "Create a signed event hook"}</h2><form id="trigger-form"><div class="fields">${field("Name", "name", "", "text", 'required minlength="2" maxlength="100"')}<label class="field">Use mission inputs<select name="mission_id">${missions
          .filter((m) => m.access_valid)
          .map((m) => `<option value="${esc(m.id)}">${esc(m.title)}</option>`)
          .join(
            "",
          )}</select></label>${kind === "schedule" ? field("Run every (hours)", "interval_hours", "24", "number", 'required value="24" min="1" max="720"') : ""}</div><div class="form-actions">${submitButton(kind === "schedule" ? "Create recurring mission" : "Create signed hook")}</div></form>`,
      );
      bindForm("#trigger-form", async (v) => {
        const m = await api("/ops/missions/" + v.mission_id);
        const data = m.evidence.filter((e) => e.type === "dataset");
        const connections = m.evidence.filter((e) => e.type === "connector");
        const teamAgent = await api("/ops/teams");
        const template = {
          title: m.title,
          objective: m.objective,
          team_id: m.team_id || teamAgent[0].id,
          mode: m.mode,
          request_key: crypto.randomUUID(),
          max_tokens: m.max_tokens,
          dataset_ids: data.map((d) => d.resource_id),
          connector_ids: connections.map((c) => c.resource_id),
          group_by: data[0]?.profile.group_by || "",
          metric: data[0]?.profile.metric || "",
        };
        const result = await opPost(
          kind === "schedule" ? "/schedules" : "/hooks",
          {
            name: v.name,
            template,
            ...(kind === "schedule"
              ? { interval_hours: Number(v.interval_hours) }
              : {}),
          },
        );
        $("#dialog").close();
        await pages.mission_triggers();
        if (result.secret)
          dialog(
            `<h2>Copy the signing secret now</h2><p>Store this in the sending system’s secret manager. It is not displayed again.</p><div class="result-secret">${esc(result.secret)}</div><pre>${esc(result.url)}</pre><p>Signature: HMAC-SHA256(secret, timestamp + "." + raw JSON body). Headers: X-Aivora-Timestamp and X-Aivora-Signature. Body: event_id and context.</p>`,
          );
        else toast("Recurring mission configured");
      });
    }
    $("#schedule-new").onclick = handle(() => triggerDialog("schedule"));
    $("#hook-new").onclick = handle(() => triggerDialog("hook"));
    document.querySelectorAll("[data-schedule-toggle]").forEach(
      (b) =>
        (b.onclick = handle(async () => {
          await opPost("/schedules/" + b.dataset.scheduleToggle + "/toggle");
          await pages.mission_triggers();
        })),
    );
  };
})();
