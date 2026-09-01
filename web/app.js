(() => {
  "use strict";

  const CACHE_KEY = "sanjian.pwa.private-cache.v2";
  const ROUTES = new Set(["home", "question", "records", "profile", "company", "settings"]);
  const OUTCOMES = { hit: "命中", partial: "部分命中", miss: "未命中", unclear: "无法判断" };
  const TENDENCIES = { favorable: "偏顺", caution: "留意", neutral: "中性" };
  const FEATURE_PRESETS = {
    daily: {
      period: "day", category: "general",
      question: "请三方分别判断我今天最需要关注的机会、风险和可验证信号。",
    },
    month: {
      period: "month", category: "general",
      question: "请三方分别判断我本月的关键节点、主要风险和适合推进的行动窗口。",
    },
    zeri: {
      period: "month", category: "general",
      question: "请三方结合我要办的具体事情，判断本月更适合推进的时间窗口、避开条件和验证信号。",
      background: "请补充：具体事项、最早与最晚日期、不可调整的现实条件。",
    },
    hehun: {
      period: "month", category: "relationship",
      question: "请三方分别判断这段关系本月的互动走向、主要分歧和可验证信号。",
      background: "请补充：对方情况、当前关系阶段、你真正想确认的一件事。",
    },
  };
  const state = {
    profiles: [], activeProfile: null, predictions: [], stats: null, today: null,
    route: "home", filter: "", offline: !navigator.onLine, deferredInstall: null,
    desk: { companies: [], projects: [], memberships: [] }, companyId: "",
    companyPredictions: [], workspaceId: "", workspaceRequest: 0, questionBusy: false,
  };

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;",
  })[c]);
  const fmtDate = value => {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value).slice(0, 16) :
      new Intl.DateTimeFormat("zh-CN", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
  };
  const shortDate = value => String(value || "").replace("T", " ").slice(0, 16);
  const brain = window.createSanjianBrain({ $, $$, esc, api, state, options });

  function toast(message) {
    const el = $("#toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { el.hidden = true; }, 2800);
  }

  function setError(id, message = "") {
    const el = $(id);
    el.textContent = message;
    el.hidden = !message;
  }

  function renderQuestionDiscussion(events = []) {
    const stream = $("#question-discussion");
    if (!stream) return;
    const priorCount = Number(stream.dataset.count || 0);
    const items = Array.isArray(events) ? events : [];
    if (!items.length) {
      stream.innerHTML = `<article class="discussion-event" data-status="active">
        <div class="discussion-event-head"><strong>正在建立讨论</strong><span>系统</span></div>
        <p>原问题锁定后，三方的公开观点会依次出现在这里。</p>
      </article>`;
      stream.dataset.count = "0";
      return;
    }
    if (items.length === priorCount) return;
    const start = priorCount > items.length ? 0 : priorCount;
    if (start === 0) stream.innerHTML = "";
    const additions = items.slice(start).map((event, offset) => {
      const index = start + offset;
      const status = ["active", "done", "retry", "error"].includes(event.status)
        ? event.status : "active";
      const label = event.provider ? (event.provider_label || event.provider) :
        (String(event.type || "").startsWith("judge") ? "盲评" : "系统");
      return `<article class="discussion-event" data-status="${esc(status)}" data-seq="${esc(event.seq || index + 1)}">
        <div class="discussion-event-head"><strong>${esc(event.title || "分析进行中")}</strong><span>${esc(label)}</span></div>
        ${event.message ? `<p>${esc(event.message)}</p>` : ""}
      </article>`;
    }).join("");
    stream.insertAdjacentHTML("beforeend", additions);
    stream.dataset.count = String(items.length);
    if (items.length > priorCount) stream.scrollTop = stream.scrollHeight;
  }

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: options.body ? { "Content-Type": "application/json", ...(options.headers || {}) } : options.headers,
    });
    let data;
    try { data = await response.json(); } catch (_) { data = { ok: false, error: "服务返回了无法解析的内容" }; }
    if (!response.ok || !data.ok) throw new Error(data.error || (typeof data.detail === "string" ? data.detail : "") || `请求失败（${response.status}），请检查必填项`);
    return data;
  }

  function persistCache() {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify({
        cached_at: new Date().toISOString(), profiles: state.profiles,
        active_profile: state.activeProfile, predictions: state.predictions,
        stats: state.stats, today: state.today,
      }));
    } catch (_) { /* 私密浏览或空间不足时不阻断在线使用 */ }
  }

  function loadCache() {
    try { return JSON.parse(localStorage.getItem(CACHE_KEY) || "null"); } catch (_) { return null; }
  }

  function applyBootstrap(data) {
    state.profiles = data.profiles || [];
    state.activeProfile = data.active_profile || null;
    state.predictions = data.predictions || [];
    state.stats = data.stats || null;
    persistCache();
    renderAll();
  }

  async function bootstrap({ quiet = false } = {}) {
    if (!navigator.onLine) {
      const cached = loadCache();
      if (cached) {
        state.profiles = cached.profiles || [];
        state.activeProfile = cached.active_profile || null;
        state.predictions = cached.predictions || [];
        state.stats = cached.stats || null;
        state.today = cached.today || null;
      }
      state.offline = true;
      renderAll();
      return;
    }
    try {
      const data = await api("/api/app/bootstrap");
      state.offline = false;
      applyBootstrap(data);
      await loadToday();
      await loadDesk();
      const personal = await api("/api/app/predictions?scene=personal");
      state.predictions = personal.predictions || [];
      persistCache(); renderHomeReviews(); renderRecords();
    } catch (error) {
      state.offline = true;
      const cached = loadCache();
      if (cached) {
        state.profiles = cached.profiles || [];
        state.activeProfile = cached.active_profile || null;
        state.predictions = cached.predictions || [];
        state.stats = cached.stats || null;
        state.today = cached.today || null;
      }
      renderAll();
      if (!quiet) toast(`已切换到离线缓存：${error.message}`);
    }
  }

  async function loadToday() {
    if (!state.activeProfile || !navigator.onLine) { renderToday(); return; }
    try {
      const data = await api(`/api/app/today?profile_id=${encodeURIComponent(state.activeProfile.id)}`);
      state.today = data;
      persistCache();
    } catch (error) {
      state.today = { error: error.message };
    }
    renderToday();
  }

  function updateNetwork() {
    state.offline = state.offline || !navigator.onLine;
    $("#network-banner").hidden = !state.offline;
    $("#question-submit").disabled = state.questionBusy || state.offline || !state.activeProfile;
  }

  function routeTo(route, focus = true) {
    const next = ROUTES.has(route) ? route : "home";
    state.route = next;
    $$(".app-view").forEach(view => {
      const active = view.dataset.view === next;
      view.hidden = !active;
      view.classList.toggle("is-active", active);
    });
    $$(".nav-item").forEach(item => item.classList.toggle("is-active", item.dataset.route === next));
    if (location.hash !== `#${next}`) history.replaceState(null, "", `#${next}`);
    if (next === "records") renderRecords();
    if (next === "profile") renderProfiles();
    if (next === "company") { renderCompany(); loadCompanyRecords(); }
    if (focus) {
      window.scrollTo({ top: 0, behavior: "smooth" });
      const heading = $(`#view-${next} h1`);
      if (heading) { heading.setAttribute("tabindex", "-1"); heading.focus({ preventScroll: true }); }
    }
  }

  function renderAll() {
    updateNetwork();
    const now = new Date();
    $("#today-label").textContent = new Intl.DateTimeFormat("zh-CN", {
      month: "long", day: "numeric", weekday: "long",
    }).format(now);
    $("#profile-chip-label").textContent = state.activeProfile ? `默认 · ${state.activeProfile.name}` : "未建基本盘";
    $("#question-no-profile").hidden = !!state.activeProfile;
    $("#question-form").hidden = !state.activeProfile;
    renderScope();
    renderToday();
    renderHomeReviews();
    renderRecords();
    renderProfiles();
    renderStats();
  }

  function renderQuestionResearch() {
    const box = $("#question-research-status");
    const profile = state.profiles.find(p => p.id === $("#question-subject").value);
    if (!profile) { box.hidden = true; return; }
    box.hidden = false;
    if ($("#question-scene").value === "company") {
      box.innerHTML = "<strong>公司事项独立资料范围</strong><br>使用勾选人员的命盘与公司、项目背景，不自动带入个人大事记和个人旧研究。大脑资料仅在上方逐条确认后带入本次问事。";
      return;
    }
    const linked = Boolean(String(profile.research_context || "").trim());
    box.innerHTML = linked
      ? `<strong>已关联高级研究资料 · v${esc(profile.research_version || 1)}</strong><br>本次问事会结合已确认事实或本人点选的历史参考；大运、神煞与流年将重新计算。`
      : `<strong>使用所选主体的基本盘、流运与大事记</strong><br>可到“看盘 → 查看”核对事实；不会带入其他主体资料。`;
  }

  function renderToday() {
    const box = $("#today-card");
    box.setAttribute("aria-busy", "false");
    if (!state.activeProfile) {
      box.innerHTML = `<div class="card-kicker">今日流运</div><div class="empty-state">创建基本盘后，这里会显示本命与今日年、月、日柱。</div>`;
      return;
    }
    if (!state.today) {
      box.innerHTML = `<div class="card-kicker">今日流运 · 计算事实</div><div class="skeleton-row" aria-hidden="true"><span></span><span></span><span></span></div><p class="muted">正在读取今日年、月、日柱…</p>`;
      return;
    }
    if (state.today.error) {
      box.innerHTML = `<div class="card-kicker">今日流运</div><div class="empty-state">${esc(state.today.error)}${state.offline ? "；当前展示依赖上次缓存。" : ""}</div>`;
      return;
    }
    const transit = state.today.transit || {};
    box.innerHTML = `<div class="card-kicker">今日流运 · ${esc(state.activeProfile.name)} · ${esc(fmtDate(state.today.as_of))}</div>
      <div class="transit-row">
        <div class="transit-pillar"><small>年柱</small><strong>${esc(transit.year || "—")}</strong></div>
        <div class="transit-pillar"><small>月柱</small><strong>${esc(transit.month || "—")}</strong></div>
        <div class="transit-pillar"><small>日柱</small><strong>${esc(transit.day || "—")}</strong></div>
      </div><p class="today-note">${esc(state.today.note || "")}${state.offline ? " 当前为离线缓存。" : ""}</p>
      <button type="button" class="small-action today-consult" data-home-feature="daily">发起今日三方研判</button>`;
  }

  const duePredictions = () => {
    const today = new Date().toISOString().slice(0, 10);
    return state.predictions.filter(p => p.profile_id === state.activeProfile?.id && !p.review && String(p.period_end || "") <= today);
  };

  function renderHomeReviews() {
    const due = duePredictions();
    const box = $("#home-review-list");
    const badge = $("#review-badge");
    badge.hidden = !due.length;
    badge.textContent = String(Math.min(due.length, 99));
    if (!due.length) {
      box.innerHTML = `<div class="empty-state">暂无到期预测。问一件具体的事，等时间窗结束后回来核对。</div>`;
      return;
    }
    box.innerHTML = due.slice(0, 3).map(p => recordCard(p, true)).join("");
    wireRecordActions(box);
  }

  function confidenceLabel(snapshot) {
    const c = snapshot?.confidence || {};
    return c.label === "medium" ? "中等置信" : "低置信";
  }

  function snapshotCard(prediction) {
    const s = prediction.snapshot || {};
    const c = s.confidence || {};
    const pct = Math.round(Number(c.score || prediction.confidence || 0) * 100);
    const list = values => (values || []).map(v => `<li>${esc(v)}</li>`).join("") || "<li>本次未形成额外条件</li>";
    const basis = s.rule_basis || {};
    const research = s.research_context || {};
    const scope = s.decision_scope || {};
    const brainEvidence = s.decision_material?.brain_evidence;
    const brainReceipt = brainEvidence ? `<details class="snapshot-details"><summary>本次大脑依据 · ${brainEvidence.items?.length || 0} 条已确认摘要</summary><p>${esc(brainEvidence.period)} · 读取于 ${esc(fmtDate(brainEvidence.fetched_at))}。来源标记不等于审计确认，未外发敏感原文。</p>${(brainEvidence.items || []).map(item => `<div class="brain-source"><strong>${esc(item.level)} · ${esc(fmtDate(item.known_at))}</strong><p>${esc(item.summary)}</p><small>原来源散列：${esc(item.source_hash)}</small></div>`).join("")}<p class="field-hint">冻结摘要散列：${esc(brainEvidence.content_hash)}</p></details>` : "";
    const natal = basis.natal_computed_facts || {};
    const transit = basis.transit_computed_facts || {};
    const metrics = s.computed_metrics || {};
    const metricNumber = value => Number.isFinite(Number(value))
      ? Number(value).toLocaleString("zh-CN", { maximumFractionDigits: 2 }) : "—";
    const metricsBlock = metrics.kind === "business_target"
      ? `<section class="business-metrics" aria-label="经营目标确定性计算">
          <div class="business-metrics-heading"><h3>先算清任务缺口</h3><span>确定性算术 · 非 AI 猜测</span></div>
          <div class="business-metrics-grid">
            <div><small>当前完成率</small><strong>${esc(metricNumber(metrics.completion_pct))}%</strong></div>
            <div><small>距离目标</small><strong>${esc(metricNumber(metrics.gap))} 万元</strong></div>
            <div><small>剩余日均要求</small><strong>${esc(metricNumber(metrics.required_daily))} 万元</strong></div>
            <div><small>较前期需提升</small><strong>${metrics.required_lift_pct == null ? "数据不足" : `${esc(metricNumber(metrics.required_lift_pct))}%`}</strong></div>
          </div>
        </section>` : "";
    const roles = Array.isArray(s.three_role_analysis) ? s.three_role_analysis : [];
    const protocol = s.three_role_protocol || {};
    const shownConclusion = s.source === "sanjian_d3j_consultation" && !protocol.direct_question
      ? "这条旧结果没有直接回答原问题，已标记为不可用于行动判断；请用新版重新发起。"
      : (s.conclusion || "");
    const roleCards = roles.map(role => `<div class="role-analysis-card">
      <strong>${esc(role.provider_label || role.provider || "独立模型")}</strong>
      <small>${esc(role.school_name || role.school || "独立视角")}</small>
      <ul>${(role.findings || []).map(finding => `<li>${esc(finding.claim || "")}${finding.basis ? `<small>依据 / 验证：${esc(finding.basis)}</small>` : ""}</li>`).join("") || "<li>未保存观点</li>"}</ul>
    </div>`).join("");
    const arbitration = s.arbitration || {};
    const roleBlock = protocol.complete && protocol.direct_question && roles.length === 3
      ? `<section class="role-analysis">
          <div class="role-analysis-heading"><h3>三方独立判断</h3><span>3/3 完整 · 缺一不出结论</span></div>
          <div class="role-analysis-grid">${roleCards}</div>
          ${arbitration.summary ? `<p class="arbitration-note"><strong>盲评汇总：</strong>${esc(arbitration.summary)}${arbitration.unresolved ? ` · 保留 ${esc(arbitration.unresolved)} 项未决分歧` : ""}</p>` : ""}
        </section>`
      : `<div class="protocol-warning"><strong>这条旧记录没有“三方直接回答原问题”的证据。</strong><br>它可保留作问题记录，但不应拿来指导行动或作为新版准确率样本；新版问事会在答非所问、基础十神矛盾或任一方缺席时停止保存。</div>`;
    return `<article class="prediction-card card">
      <div class="prediction-head">
        <div class="prediction-meta"><span>${esc(s.category_label || prediction.category)} · ${s.period === "day" ? "今天" : "本月"} · ${esc(fmtDate(s.asked_at || prediction.asked_at))}</span><span class="lock-badge">🔒 原始预测已锁定</span></div>
        <div class="prediction-question">${esc(s.question || prediction.question)}</div>
        <p class="prediction-conclusion">${esc(shownConclusion)}</p>
      </div>
      <div class="prediction-body">
        <div class="scope-receipt"><strong>${scope.scene === "company" ? "公司事项" : "个人事项"} · ${esc(scope.subject?.name || "旧记录未锁定主体名称")}</strong><p>${esc(scope.company?.name || "仅当前主体")}${scope.project ? ` / ${esc(scope.project.name)}` : ""}${scope.participants?.length ? ` · ${scope.participants.map(p => esc(`${p.name}（${p.role}）`)).join("、")}` : ""}</p><small>资料范围以提交时快照为准；之后编辑档案不会改写此处。</small></div>
        <div class="confidence-row" aria-label="${esc(confidenceLabel(s))}，${pct}%"><strong>${esc(confidenceLabel(s))}</strong><div class="confidence-track"><span style="width:${Math.max(0, Math.min(pct, 100))}%"></span></div><small>${pct}%</small></div>
        ${metricsBlock}
        ${roleBlock}
        ${brainReceipt}
        <div class="snapshot-grid">
          <section class="snapshot-panel"><h3>有利触发条件</h3><ul>${list(s.favorable_triggers)}</ul></section>
          <section class="snapshot-panel"><h3>不利触发条件</h3><ul>${list(s.unfavorable_triggers)}</ul></section>
          <section class="snapshot-panel"><h3>行动建议</h3><ul>${list(s.action_suggestions)}</ul></section>
          <section class="snapshot-panel"><h3>可验证事件</h3><ul>${list(s.verifiable_events)}</ul></section>
        </div>
        <details class="snapshot-details"><summary>查看时间窗、版本与依据</summary><dl>
          <dt>时间窗</dt><dd>${esc(prediction.period_start)} — ${esc(prediction.period_end)}</dd>
          <dt>本命</dt><dd>${esc(Object.values(natal).join(" ") || "未保存")}</dd>
          <dt>流运</dt><dd>${esc(Object.values(transit).join(" ") || "未保存")}</dd>
          <dt>算法</dt><dd>${esc(prediction.algorithm_version || s.algorithm_version)}</dd>
          <dt>模型</dt><dd>${esc(prediction.model_version || s.model_version)}</dd>
          <dt>规则依据</dt><dd>${esc(basis.evidence_note || prediction.rule_version || "")}</dd>
          <dt>研究资料</dt><dd>${research.included ? `已引用本人确认资料 v${esc(research.profile_research_version)} · ${esc(research.content_hash || "")}` : "未引用"}</dd>
          <dt>校准</dt><dd>${esc(prediction.calibration_version || s.calibration_version)}</dd>
          <dt>快照哈希</dt><dd>${esc(prediction.content_hash || "")}</dd>
        </dl></details>
        <p class="today-note">${esc(s.disclaimer || "")}</p>
      </div>
    </article>`;
  }

  function recordCard(p, compact = false) {
    const s = p.snapshot || {};
    const review = p.review;
    const shownConclusion = s.source === "sanjian_d3j_consultation" && !s.three_role_protocol?.direct_question
      ? "旧结果未直接回答原问题，已标记为不可用于行动判断。"
      : (s.conclusion || "");
    return `<article class="record-card card">
      <div class="record-summary">
        <div class="record-top"><span class="record-category">${esc(s.decision_scope?.subject?.name || state.profiles.find(profile => profile.id === p.profile_id)?.name || "旧记录")} · ${esc(s.category_label || p.category || "问事")}</span><span class="record-date">${esc(fmtDate(p.locked_at))}</span></div>
        <div class="record-question">${esc(s.question || p.question)}</div>
        <p class="record-conclusion">${esc(shownConclusion)}</p>
        <div class="record-actions">
          ${review ? `<span class="review-outcome">复盘：${esc(OUTCOMES[review.outcome] || review.outcome)}</span>` : `<button type="button" class="small-action review-open" data-id="${esc(p.id)}">结果复盘</button>`}
          <button type="button" class="text-button snapshot-open" data-id="${esc(p.id)}">${compact ? "查看" : "完整快照"}</button>
        </div>
      </div>
      <div class="record-snapshot" data-snapshot="${esc(p.id)}" hidden>${snapshotCard(p)}</div>
    </article>`;
  }

  function wireRecordActions(root = document) {
    $$(".review-open", root).forEach(button => button.addEventListener("click", () => openReview(button.dataset.id)));
    $$(".snapshot-open", root).forEach(button => button.addEventListener("click", () => {
      const panel = root.querySelector(`[data-snapshot="${CSS.escape(button.dataset.id)}"]`);
      if (!panel) return;
      panel.hidden = !panel.hidden;
      button.textContent = panel.hidden ? "完整快照" : "收起快照";
    }));
  }

  function renderRecords() {
    const box = $("#records-list");
    const records = state.predictions.filter(p => {
      if ($("#records-subject").value && p.profile_id !== $("#records-subject").value) return false;
      if (state.filter === "pending") return !p.review;
      if (state.filter === "reviewed") return !!p.review;
      return true;
    });
    $$(".filter").forEach(button => button.classList.toggle("is-active", button.dataset.filter === state.filter));
    if (!records.length) {
      box.innerHTML = `<div class="empty-state">${state.activeProfile ? "这个筛选下还没有记录。" : "先创建基本盘并完成一次问事。"}</div>`;
      return;
    }
    box.innerHTML = records.map(p => recordCard(p)).join("");
    wireRecordActions(box);
  }

  function renderProfiles() {
    const box = $("#profile-list");
    if (!state.profiles.length) {
      box.innerHTML = `<div class="empty-state">还没有基本盘。创建后可保存、编辑和切换。</div>`;
      return;
    }
    box.innerHTML = state.profiles.map(p => `<div class="profile-row ${p.is_active ? "is-active" : ""}">
      <div class="profile-main"><strong>${esc(p.name)}${p.is_active ? " · 默认" : ""}</strong><small>${esc(p.birth)} · ${p.gender === "male" ? "男" : "女"} · ${esc(p.place || "未填出生地")} · ${p.research_context ? `研究资料 v${esc(p.research_version)}` : "未关联研究资料"} · 基本盘 v${esc(p.version)}</small></div>
      <div class="profile-row-actions"><button type="button" class="profile-view" data-id="${esc(p.id)}">查看</button>${p.is_active ? "" : `<button type="button" class="profile-activate" data-id="${esc(p.id)}">设为默认</button>`}<button type="button" class="profile-edit" data-id="${esc(p.id)}">编辑</button></div>
    </div>`).join("");
    $$(".profile-activate", box).forEach(button => button.addEventListener("click", () => activateProfile(button.dataset.id)));
    $$(".profile-edit", box).forEach(button => button.addEventListener("click", () => openProfileForm(button.dataset.id)));
    $$(".profile-view", box).forEach(button => button.addEventListener("click", () => loadWorkspace(button.dataset.id)));
  }

  function renderStats() {
    const box = $("#stats-card");
    const overall = state.stats?.overall;
    if (!state.activeProfile || !overall) {
      box.innerHTML = `<div class="empty-state">创建基本盘后，复盘数据会按类别、周期与版本汇总。</div>`;
      return;
    }
    const n = Number(overall.sample_size || 0);
    const min = Number(overall.minimum_sample_size || 8);
    const headline = overall.sufficient_sample ? `个人命中 ${Math.round(overall.hit_rate * 100)}%` : `样本 ${n} / ${min}`;
    const copy = overall.sufficient_sample ? `校准误差 ${Math.round(overall.calibration_error * 100)}%；只影响以后输出。` : `还差 ${Math.max(0, min - n)} 条可判断复盘。小样本不展示准确率。`;
    const groupBlock = (title, values) => {
      if (!(values || []).length) return "";
      const rows = values.map(g => `<div class="stat-row"><span>${esc(g.key)}</span><span>${g.sufficient_sample ? `${Math.round(g.hit_rate * 100)}% · n=${g.sample_size}` : `n=${g.sample_size} · 样本不足`}</span></div>`).join("");
      return `<details class="stat-detail"><summary>${esc(title)}</summary><div class="stat-groups">${rows}</div></details>`;
    };
    const groups = [
      groupBlock("按事情类别", state.stats.by_category),
      groupBlock("按预测周期", state.stats.by_period),
      groupBlock("按算法版本", state.stats.by_algorithm_version),
      groupBlock("按模型版本", state.stats.by_model_version),
      groupBlock("按规则版本", state.stats.by_rule_version),
    ].join("");
    box.innerHTML = `<div class="eyebrow">${esc(state.activeProfile.name)} · 个人事项</div><div class="stats-overview"><div class="stats-copy"><strong>${esc(headline)}</strong><p>${esc(copy)}<br>${esc(state.stats.policy || "")}</p></div><div class="sample-ring" aria-label="${esc(headline)}">${n}/${min}</div></div>${groups}`;
  }

  function openProfileForm(profileId = "") {
    if (state.offline) { toast("离线时只能查看基本盘"); return; }
    const profile = state.profiles.find(p => p.id === profileId);
    const form = $("#profile-form");
    form.reset();
    $("#profile-id").value = profile?.id || "";
    $("#profile-version").value = profile?.version || "";
    $("#profile-form-title").textContent = profile ? "编辑基本盘" : "新建基本盘";
    $("#profile-name").value = profile?.name || "";
    $("#profile-birth").value = String(profile?.birth || "").slice(0, 16);
    $("#profile-gender").value = profile?.gender || "male";
    $("#profile-place").value = profile?.place || "";
    $("#profile-longitude").value = profile?.longitude ?? "";
    $("#profile-timezone").value = profile?.timezone || "Asia/Shanghai";
    $("#profile-zi").value = profile?.zi_hour_mode || "split";
    $("#profile-industry").value = profile?.industry || "";
    $("#profile-occupation").value = profile?.occupation || "";
    $("#profile-situation").value = profile?.situation || "";
    $("#profile-research").value = profile?.research_context || "";
    $("#profile-research-source").value = profile?.research_source || "manual";
    const researchLinked = Boolean(profile?.research_context);
    $("#profile-research-status").textContent = researchLinked ? `已绑定 · v${profile.research_version}` : "未绑定";
    $("#profile-research-import").disabled = !profile;
    setError("#profile-error");
    form.hidden = false;
    form.scrollIntoView({ behavior: "smooth", block: "start" });
    $("#profile-name").focus();
  }

  async function saveProfile(event) {
    event.preventDefault();
    if (!navigator.onLine) { setError("#profile-error", "离线时不能保存基本盘"); return; }
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const id = $("#profile-id").value;
    const longitudeText = $("#profile-longitude").value.trim();
    const body = {
      name: $("#profile-name").value.trim(), birth: $("#profile-birth").value,
      gender: $("#profile-gender").value, place: $("#profile-place").value.trim(),
      longitude: longitudeText ? Number(longitudeText) : null,
      timezone: $("#profile-timezone").value, zi_hour_mode: $("#profile-zi").value,
      industry: $("#profile-industry").value.trim(), occupation: $("#profile-occupation").value.trim(),
      situation: $("#profile-situation").value.trim(),
      research_context: $("#profile-research").value.trim(),
      research_source: $("#profile-research").value.trim() ? ($("#profile-research-source").value || "manual") : "",
      is_active: !state.activeProfile,
    };
    if (id) body.expected_version = Number($("#profile-version").value);
    const submit = $("button[type=submit]", form);
    submit.disabled = true;
    setError("#profile-error");
    try {
      await api(id ? `/api/app/profiles/${encodeURIComponent(id)}` : "/api/app/profiles", {
        method: id ? "PUT" : "POST", body: JSON.stringify(body),
      });
      form.hidden = true;
      await bootstrap({ quiet: true });
      toast(id ? "基本盘已更新" : "基本盘已创建");
    } catch (error) { setError("#profile-error", error.message); }
    finally { submit.disabled = false; }
  }

  async function importResearchCandidates() {
    const profileId = $("#profile-id").value;
    if (!profileId) { toast("请先保存基本盘，再从高级研究载入"); return; }
    const button = $("#profile-research-import");
    button.disabled = true;
    try {
      const data = await api(`/api/app/profiles/${encodeURIComponent(profileId)}/research-candidates`);
      if (!data.facts?.length) {
        await loadWorkspace(profileId);
        toast(data.records?.length ? "可绑定记录已在看盘页列出，请核对后点选" : "还没有可绑定的事实或同生日历史记录");
        return;
      }
      const existing = $("#profile-research").value || "";
      const markerAt = existing.indexOf("【历史高级研究参考");
      const historyReference = markerAt >= 0 ? existing.slice(markerAt).trim() : "";
      const importedFacts = historyReference
        ? String(data.candidate_context || "").slice(0, 650).trim()
        : String(data.candidate_context || "").trim();
      $("#profile-research").value = [importedFacts, historyReference.slice(0, 540)]
        .filter(Boolean).join("\n\n").slice(0, 1200);
      $("#profile-research-source").value = historyReference
        ? "advanced_record_reviewed"
        : (data.source || "advanced_dossier_reviewed");
      $("#profile-research-status").textContent = `待确认 · ${data.facts.length} 条`;
      const recordHint = data.records?.length ? `；另有 ${data.records.length} 条历史记录可在看盘页绑定` : "";
      toast(`已载入 ${data.facts.length} 条事实；检查后保存才会生效${recordHint}`);
    } catch (error) { setError("#profile-error", error.message); }
    finally { button.disabled = false; }
  }

  async function activateProfile(id) {
    if (!navigator.onLine) { toast("离线时不能切换服务端基本盘"); return; }
    try {
      await api(`/api/app/profiles/${encodeURIComponent(id)}/activate`, { method: "POST" });
      state.today = null;
      await bootstrap({ quiet: true });
      toast("已切换基本盘");
    } catch (error) { toast(error.message); }
  }

  async function submitQuestion(event) {
    event.preventDefault();
    const form = event.currentTarget;
    setError("#question-error");
    if (state.questionBusy) return;
    if (!navigator.onLine) { setError("#question-error", "当前离线，不能生成预测；已缓存记录仍可查看。"); return; }
    if (!state.activeProfile) { setError("#question-error", "请先创建基本盘"); return; }
    if (!form.reportValidity()) return;
    const body = {
      profile_id: $("#question-subject").value,
      scene: $("#question-scene").value,
      scope_confirmed: $("#question-scope-confirm").checked,
      expected_profile_version: state.profiles.find(p => p.id === $("#question-subject").value)?.version,
      period: $("input[name=period]:checked", form).value,
      category: $("#question-category").value,
      question: $("#question-text").value.trim(),
      background: $("#question-background").value.trim(),
    };
    if (body.scene === "company") {
      body.company_id = $("#question-company").value;
      body.project_id = $("#question-project").value;
      body.membership_ids = $$("#question-members input:checked").map(input => input.value);
      body.expected_company_version = state.desk.companies.find(c => c.id === body.company_id)?.version;
      body.expected_project_version = state.desk.projects.find(p => p.id === body.project_id)?.version;
      body.expected_memberships = Object.fromEntries(body.membership_ids.map(id => {
        const member = state.desk.memberships.find(m => m.id === id);
        return [id, { version: member?.version, profile_version: member?.profile_version }];
      }));
      if (!body.company_id || !body.membership_ids.length) { setError("#question-error", "请选择公司及本次相关人员"); return; }
    }
    try { Object.assign(body, brain.forQuestion()); }
    catch (error) { setError("#question-error", error.message); return; }
    const button = $("#question-submit");
    const progress = $("#question-progress");
    const progressText = $("#question-progress-text");
    state.questionBusy = true;
    const controls = $$("input,select,textarea,button", form).map(el => ({ el, disabled: el.disabled }));
    controls.forEach(({ el }) => { el.disabled = true; });
    progress.hidden = false;
    progress.classList.remove("is-complete", "is-failed");
    renderQuestionDiscussion([]);
    $("#prediction-result").innerHTML = "";
    const started = Date.now();
    try {
      const start = await api("/api/app/questions/start", { method: "POST", body: JSON.stringify(body),
        headers: body.brain_snapshot_id ? brain.headers() : {}, cache: "no-store" });
      brain.reset();
      let final = null;
      for (let i = 0; i < 720; i += 1) {
        const elapsed = Math.round((Date.now() - started) / 1000);
        progressText.textContent = `原问题已锁定，三方命盘分析、原问题直答与盲评进行中 · ${elapsed} 秒`;
        const job = await api(`/api/consult/result?job_id=${encodeURIComponent(start.job_id)}`);
        renderQuestionDiscussion(job.events);
        if (job.status !== "running") { final = job; break; }
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      if (!final || final.status !== "done" || !final.result?.prediction) {
        progress.classList.add("is-failed");
        throw new Error(final?.result?.error || "生成超时；服务端若仍在运行，可稍后到记录页刷新查看");
      }
      const prediction = final.result.prediction;
      if (body.scene === "company") {
        if (body.company_id === state.companyId) {
          state.companyPredictions = [prediction, ...state.companyPredictions.filter(p => p.id !== prediction.id)];
          renderCompanyRecords();
        }
      }
      else state.predictions = [prediction, ...state.predictions.filter(p => p.id !== prediction.id)];
      persistCache();
      $("#prediction-result").innerHTML = snapshotCard(prediction);
      renderHomeReviews();
      renderRecords();
      form.reset();
      renderScope();
      progress.classList.add("is-complete");
      progressText.textContent = "三方公开观点、重试记录与匿名盲评已全部完成。";
      toast("预测已锁定，可在记录页随时查看");
      $("#prediction-result").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) { setError("#question-error", error.message); }
    finally {
      state.questionBusy = false;
      controls.forEach(({ el, disabled }) => { el.disabled = disabled; });
      button.disabled = state.offline || !state.activeProfile;
      renderScope();
    }
  }

  function openReview(id) {
    if (state.offline) { toast("离线时只能查看，联网后再提交复盘"); return; }
    const prediction = [...state.predictions, ...state.companyPredictions].find(p => p.id === id);
    if (!prediction || prediction.review) return;
    const dialog = $("#review-dialog");
    $("#review-form").reset();
    $("#review-prediction-id").value = id;
    setError("#review-error");
    dialog.showModal();
  }

  async function submitReview(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (!form.reportValidity()) return;
    const id = $("#review-prediction-id").value;
    const outcome = $("input[name=outcome]:checked", form)?.value;
    if (!outcome) { setError("#review-error", "请选择复盘结果"); return; }
    const body = {
      outcome,
      actual_at: $("#review-actual-at").value || null,
      result: $("#review-result").value.trim(),
      note: $("#review-note").value.trim(),
    };
    const button = $("button[type=submit]", form);
    button.disabled = true;
    try {
      const data = await api(`/api/app/predictions/${encodeURIComponent(id)}/review`, {
        method: "POST", body: JSON.stringify(body),
      });
      state.predictions = state.predictions.map(p => p.id === id ? data.prediction : p);
      state.companyPredictions = state.companyPredictions.map(p => p.id === id ? data.prediction : p);
      if (data.prediction.profile_id === state.activeProfile?.id) state.stats = data.stats;
      persistCache();
      $("#review-dialog").close();
      renderAll();
      renderCompanyRecords();
      toast("复盘已锁定，历史预测保持不变");
    } catch (error) { setError("#review-error", error.message); }
    finally { button.disabled = false; }
  }

  function openHomeFeature(feature) {
    if (feature === "accuracy") {
      routeTo("settings");
      window.setTimeout(() => $("#stats-card")?.scrollIntoView({ behavior: "smooth", block: "center" }), 180);
      return;
    }
    if (feature === "backup") {
      toast("主机每天自动备份到“文稿/三鉴备份”，保留最近 14 份");
      return;
    }
    const preset = FEATURE_PRESETS[feature];
    if (!preset) return;
    if (!state.activeProfile) {
      routeTo("profile");
      toast("先创建或选择基本盘，再发起三方会诊");
      return;
    }
    if (state.questionBusy) { toast("已有问事正在进行，请等待完成"); return; }
    clearQuestionDraft();
    $("#question-scene").value = "personal";
    $("#question-subject").value = state.activeProfile.id;
    renderScope();
    const period = $(`input[name=period][value="${preset.period}"]`);
    if (period) period.checked = true;
    $("#question-category").value = preset.category;
    $("#question-text").value = preset.question;
    $("#question-background").value = preset.background || "";
    routeTo("question");
    window.setTimeout(() => (preset.background ? $("#question-background") : $("#question-text"))?.focus(), 180);
    toast("已准备三方会诊问题，请补充现实背景后提交");
  }

  function options(select, rows, placeholder, preferred = "") {
    const previous = preferred || select.value;
    select.innerHTML = (placeholder == null ? "" : `<option value="">${esc(placeholder)}</option>`) + rows.map(row => `<option value="${esc(row.id)}">${esc(row.name)}</option>`).join("");
    if (rows.some(row => row.id === previous)) select.value = previous;
  }

  function clearQuestionDraft() {
    $("#question-text").value = ""; $("#question-background").value = "";
    $("#prediction-result").innerHTML = ""; setError("#question-error");
    $("#question-scope-confirm").checked = false;
  }

  function renderScope() {
    brain.reset();
    const subject = $("#question-subject");
    options(subject, state.profiles, null, subject.value || state.activeProfile?.id);
    options($("#records-subject"), state.profiles, "全部个人档案");
    const isCompany = $("#question-scene").value === "company";
    $("#question-company-fields").hidden = !isCompany;
    $("#question-company").required = isCompany;
    options($("#question-company"), state.desk.companies, "请选择公司");
    const companyId = $("#question-company").value;
    options($("#question-project"), state.desk.projects.filter(p => p.company_id === companyId), "公司整体（非单个项目）");
    const projectId = $("#question-project").value;
    const selected = new Set($$("#question-members input:checked").map(input => input.value));
    const members = state.desk.memberships.filter(m => m.company_id === companyId && (!m.project_id || m.project_id === projectId));
    $("#question-members").innerHTML = members.map(m => `<label class="check-line"><input type="checkbox" value="${esc(m.id)}" ${selected.has(m.id) ? "checked" : ""} ${m.consent_confirmed ? "" : "disabled"}><span>${esc(m.profile_name)} · ${esc(m.role)}${m.consent_confirmed ? "" : " · 未授权"}${m.ends_on ? ` · 至 ${esc(m.ends_on)}` : ""}</span></label>`).join("") || '<p class="field-hint">还没有适用关联，请先在公司页添加。</p>';
    $("#question-scope-summary").textContent = isCompany
      ? "只使用本次勾选的人员与所选公司、项目背景；不自动汇入个人私事。任职有效期会在提交时复核。"
      : `只分析「${state.profiles.find(p => p.id === subject.value)?.name || "未选择"}」：本命、流运、已确认事实与显式绑定参考。不包含公司、合伙人或其他档案。`;
    $("#question-scope-confirm").checked = false;
    renderQuestionResearch();
  }

  async function loadDesk() {
    try {
      state.desk = await api("/api/app/desk");
      if (!state.desk.companies.some(c => c.id === state.companyId)) state.companyId = state.desk.companies[0]?.id || "";
      renderCompany(); renderScope();
    } catch (error) { setError("#company-error", error.message); }
  }

  function renderCompany() {
    brain.companyChanged();
    options($("#company-select"), state.desk.companies, "请选择公司", state.companyId);
    const company = state.desk.companies.find(c => c.id === state.companyId);
    const box = $("#company-detail");
    if (!company) { box.innerHTML = '<div class="empty-state">先建立公司，再关联项目和相关人员。</div>'; return; }
    const projects = state.desk.projects.filter(p => p.company_id === company.id);
    const members = state.desk.memberships.filter(m => m.company_id === company.id);
    box.innerHTML = `<article class="desk-card card"><span class="eyebrow">手动录入 · v${esc(company.version)} · ${esc(fmtDate(company.updated_at))}</span><h2>${esc(company.name)}</h2><p>${esc(company.context || "尚未填写发展情况")}</p><div class="settings-actions"><button type="button" class="small-action" data-edit-company="${esc(company.id)}">编辑</button><button type="button" class="primary-action" id="company-ask">发起公司问事</button></div></article>
      <div class="section-heading"><h3>项目</h3><button class="text-button" type="button" data-edit-project="">＋ 添加项目</button></div>
      <div class="compact-list">${projects.map(p => `<article class="desk-row"><div><strong>${esc(p.name)}</strong><p>${esc(p.context || "尚未填背景")}</p></div><button class="text-button" type="button" data-edit-project="${esc(p.id)}">编辑</button></article>`).join("") || '<p class="field-hint">暂无项目，公司整体问事不要求项目。</p>'}</div>
      <div class="section-heading"><h3>相关人员与授权</h3><button class="text-button" type="button" data-edit-member="">＋ 关联人员</button></div>
      <div class="compact-list">${members.map(m => `<article class="desk-row"><div><strong>${esc(m.profile_name)} · ${esc(m.role)}</strong><p>${esc(projects.find(p => p.id === m.project_id)?.name || "公司整体")} · ${m.consent_confirmed ? "已确认授权" : "未授权 / 已撤回"} · ${esc(m.starts_on || "开始不限")} — ${esc(m.ends_on || "结束不限")}</p></div><button class="text-button" type="button" data-edit-member="${esc(m.id)}">编辑</button></article>`).join("") || '<p class="field-hint">每次问事仍需手动勾选，不会自动把全部人员送入分析。</p>'}</div>`;
  }

  function openDeskForm(kind, id = "") {
    if (state.offline) { toast("离线时不能编辑公司资料"); return; }
    if (kind !== "company" && !state.companyId) return;
    setError("#company-error");
    ["company", "project", "member"].forEach(name => { $(`#${name}-form`).hidden = name !== kind; });
    const form = $(`#${kind}-form`); form.reset();
    if (kind === "company") {
      const row = state.desk.companies.find(c => c.id === id);
      $("#company-id").value = row?.id || ""; $("#company-version").value = row?.version || 0;
      ["name", "industry", "context"].forEach(key => { $(`#company-${key}`).value = row?.[key] || ""; });
    } else if (kind === "project") {
      const row = state.desk.projects.find(p => p.id === id);
      $("#project-company").value = state.companyId;
      $("#project-id").value = row?.id || ""; $("#project-version").value = row?.version || 0;
      $("#project-name").value = row?.name || ""; $("#project-context").value = row?.context || "";
    } else {
      const row = state.desk.memberships.find(m => m.id === id);
      $("#member-company").value = state.companyId;
      $("#member-version").value = row?.version || 0;
      options($("#member-profile"), state.profiles, "请选择基本盘", row?.profile_id);
      options($("#member-project"), state.desk.projects.filter(p => p.company_id === state.companyId), "公司整体", row?.project_id);
      $("#member-profile").disabled = !!row; $("#member-project").disabled = !!row;
      $("#member-role").value = row?.role || ""; $("#member-consent").checked = !!row?.consent_confirmed;
      $("#member-start").value = row?.starts_on || ""; $("#member-end").value = row?.ends_on || "";
    }
    form.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  async function saveDeskForm(event, kind) {
    event.preventDefault();
    const form = event.currentTarget;
    if (state.offline || !form.reportValidity()) return;
    const button = $("button[type=submit]", form); button.disabled = true;
    let body, url, method = "POST";
    if (kind === "company") {
      const id = $("#company-id").value;
      url = `/api/app/companies${id ? `/${encodeURIComponent(id)}` : ""}`; if (id) method = "PUT";
      body = { name: $("#company-name").value.trim(), industry: $("#company-industry").value.trim(), context: $("#company-context").value.trim(), expected_version: Number($("#company-version").value) };
    } else if (kind === "project") {
      const id = $("#project-id").value;
      url = `/api/app/companies/${encodeURIComponent($("#project-company").value)}/projects${id ? `/${encodeURIComponent(id)}` : ""}`; if (id) method = "PUT";
      body = { name: $("#project-name").value.trim(), context: $("#project-context").value.trim(), expected_version: Number($("#project-version").value) };
    } else {
      url = `/api/app/companies/${encodeURIComponent($("#member-company").value)}/memberships`;
      body = { profile_id: $("#member-profile").value, project_id: $("#member-project").value, role: $("#member-role").value.trim(), consent_confirmed: $("#member-consent").checked, starts_on: $("#member-start").value, ends_on: $("#member-end").value, expected_version: Number($("#member-version").value) };
    }
    try {
      const result = await api(url, { method, body: JSON.stringify(body) });
      if (result.company) state.companyId = result.company.id;
      form.hidden = true; await loadDesk(); toast("已保存；之后问事会冻结新版本资料");
    } catch (error) { setError("#company-error", error.message); }
    finally { button.disabled = false; }
  }

  function renderCompanyRecords() {
    const box = $("#company-records");
    box.innerHTML = state.companyPredictions.map(p => recordCard(p)).join("") || '<div class="empty-state">当前公司暂无已锁定事项。公司复盘不混入个人校准。</div>';
    wireRecordActions(box);
  }

  async function loadCompanyRecords() {
    const companyId = state.companyId;
    state.companyPredictions = []; renderCompanyRecords();
    if (!companyId || state.offline) return;
    try {
      const data = await api(`/api/app/predictions?scene=company&company_id=${encodeURIComponent(companyId)}`);
      if (companyId !== state.companyId) return;
      state.companyPredictions = data.predictions || []; renderCompanyRecords();
    } catch (error) { setError("#company-error", error.message); }
  }

  async function loadWorkspace(id) {
    if (!id || state.offline) { toast("查看最新计算资料需要联网"); return; }
    const token = ++state.workspaceRequest;
    state.workspaceId = id;
    $("#event-form").hidden = true;
    const box = $("#chart-workspace"); box.innerHTML = '<div class="empty-state">正在读取该主体的计算资料…</div>';
    try {
      const data = await api(`/api/app/profiles/${encodeURIComponent(id)}/workspace`);
      if (token !== state.workspaceRequest) return;
      const profile = state.profiles.find(p => p.id === id);
      const pillars = data.computed?.pillars || {};
      const candidates = data.legacy_candidates?.records || [];
      box.innerHTML = `<article class="desk-card card"><span class="eyebrow">计算资料 · 基本盘 v${esc(data.profile_version)}</span><h2>${esc(profile?.name)}</h2><div class="chart-pillars">${["year", "month", "day", "hour"].map((key, i) => `<div><small>${["年柱", "月柱", "日柱", "时柱"][i]}</small><strong>${esc(pillars[key])}</strong></div>`).join("")}</div><p>${esc(data.note)}</p><button type="button" class="primary-action" id="workspace-ask">问这位的事情</button><details class="computed-detail"><summary>大运与神煞 · 计算明细（待独立对拍）</summary><pre>${esc(JSON.stringify({ dayun: data.computed.dayun, shensha: data.computed.shensha }, null, 2))}</pre></details></article>
        <article class="desk-card card"><span class="eyebrow">本人确认 · 非模型猜测</span><h3>现实背景与大事记</h3><p>${esc(data.confirmed_context || "未填写长期事实资料")}</p>${data.events.map(e => `<div class="event-row"><strong>${esc(e.occurred_on)}</strong><p>${esc(e.content)}</p><small>录入 ${esc(fmtDate(e.known_at))}</small></div>`).join("") || '<p class="field-hint">暂无追加事实。</p>'}</article>
        <article class="desk-card card"><span class="eyebrow">非事实参考 · 不计入验证证据</span><h3>历史研究</h3><p>${esc(data.historical_reference || "尚未绑定历史模型研究")}</p><p class="field-hint">同生日只用于寻找候选，不能证明是同一个人。请确认记录确属该主体再绑定。</p>${candidates.map(r => `<div class="desk-row"><div><strong>${esc(fmtDate(r.saved_at))}</strong><p>${esc(r.chart_line)}</p></div><button type="button" class="text-button" data-bind-reference="${esc(r.id)}">预览并绑定</button></div>`).join("") || '<p class="field-hint">没有匹配的旧记录。</p>'}</article>`;
      $("#event-form").hidden = false; $("#event-form").reset();
      $("#event-date").max = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Shanghai" });
      box.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) { if (token === state.workspaceRequest) box.innerHTML = `<div class="notice warning">${esc(error.message)}</div>`; }
  }

  async function bindReference(recordId) {
    const id = state.workspaceId;
    const profile = state.profiles.find(p => p.id === id);
    if (!profile) return;
    try {
      const preview = await api(`/api/app/profiles/${encodeURIComponent(id)}/research-record-preview?record_id=${encodeURIComponent(recordId)}`);
      if (!window.confirm(`确认这条记录属于「${profile.name}」？绑定后仅作历史参考，不是事实。\n\n${preview.reference}`)) return;
      await api(`/api/app/profiles/${encodeURIComponent(id)}/research-record-bind`, { method: "POST", body: JSON.stringify({ record_id: recordId, expected_version: profile.version }) });
      await bootstrap({ quiet: true }); await loadWorkspace(id);
      // Do not leave a pre-binding version in an open profile editor.
      if ($("#profile-id").value === id) $("#profile-form").hidden = true;
      toast("已绑定为非事实参考");
    } catch (error) { toast(error.message); }
  }

  async function saveEvent(event) {
    event.preventDefault();
    const form = event.currentTarget;
    if (state.offline || !form.reportValidity()) return;
    const id = state.workspaceId, button = $("button[type=submit]", form);
    button.disabled = true; setError("#event-error");
    try {
      await api(`/api/app/profiles/${encodeURIComponent(id)}/events`, { method: "POST", body: JSON.stringify({ occurred_on: $("#event-date").value, content: $("#event-content").value.trim(), confirmed: $("#event-confirm").checked }) });
      if (state.workspaceId === id) await loadWorkspace(id);
      toast("事实已追加；已有预测保持原样");
    } catch (error) { setError("#event-error", error.message); }
    finally { button.disabled = false; }
  }

  function wireEvents() {
    document.addEventListener("click", event => {
      for (const kind of ["company", "project", "member"]) {
        const edit = event.target.closest(`[data-edit-${kind}]`);
        if (edit) { openDeskForm(kind, edit.getAttribute(`data-edit-${kind}`)); return; }
      }
      const close = event.target.closest("[data-close-form]");
      if (close) { document.getElementById(close.dataset.closeForm).hidden = true; return; }
      const bind = event.target.closest("[data-bind-reference]");
      if (bind) { bindReference(bind.dataset.bindReference); return; }
      if (event.target.closest("#workspace-ask")) {
        if (state.questionBusy) { toast("已有问事正在进行"); return; }
        clearQuestionDraft();
        $("#question-scene").value = "personal"; $("#question-subject").value = state.workspaceId;
        renderScope(); routeTo("question"); return;
      }
      if (event.target.closest("#company-ask")) {
        if (state.questionBusy) { toast("已有问事正在进行"); return; }
        clearQuestionDraft();
        $("#question-scene").value = "company"; $("#question-company").value = state.companyId;
        renderScope(); routeTo("question"); return;
      }
      const featureButton = event.target.closest("[data-home-feature]");
      if (featureButton) { openHomeFeature(featureButton.dataset.homeFeature); return; }
      const routeButton = event.target.closest("[data-route]");
      if (routeButton) routeTo(routeButton.dataset.route);
    });
    $$(".quick-card").forEach(button => button.addEventListener("click", () => {
      if (state.questionBusy) { toast("已有问事正在进行"); return; }
      clearQuestionDraft();
      $("#question-scene").value = "personal";
      $("#question-subject").value = state.activeProfile?.id || "";
      renderScope();
      $("#question-category").value = button.dataset.category;
      routeTo("question");
      $("#question-text").focus();
    }));
    $$(".filter").forEach(button => button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      renderRecords();
    }));
    $("#question-form").addEventListener("submit", submitQuestion);
    ["scene", "subject", "company", "project"].forEach(key => $("#question-" + key).addEventListener("change", () => { clearQuestionDraft(); renderScope(); }));
    $("#question-form").addEventListener("input", event => { if (event.target.id !== "question-scope-confirm") $("#question-scope-confirm").checked = false; });
    $("#records-subject").addEventListener("change", renderRecords);
    $("#company-select").addEventListener("change", () => {
      state.companyId = $("#company-select").value;
      ["company", "project", "member"].forEach(kind => { $(`#${kind}-form`).hidden = true; });
      renderCompany(); loadCompanyRecords();
    });
    $("#company-new").addEventListener("click", () => openDeskForm("company"));
    ["company", "project", "member"].forEach(kind => $(`#${kind}-form`).addEventListener("submit", event => saveDeskForm(event, kind)));
    $("#company-refresh-records").addEventListener("click", loadCompanyRecords);
    $("#event-form").addEventListener("submit", saveEvent);
    $("#profile-research-open").addEventListener("click", () => loadWorkspace($("#profile-id").value));
    $("#profile-form").addEventListener("submit", saveProfile);
    $("#new-profile-button").addEventListener("click", () => openProfileForm());
    $("#profile-form-close").addEventListener("click", () => { $("#profile-form").hidden = true; });
    $("#profile-research-import").addEventListener("click", importResearchCandidates);
    $("#review-form").addEventListener("submit", submitReview);
    $("#review-close").addEventListener("click", () => $("#review-dialog").close());
    $("#clear-offline").addEventListener("click", () => {
      localStorage.removeItem(CACHE_KEY);
      toast("浏览器离线缓存已清除；服务端私有数据未删除");
    });
    $("#show-install-help").addEventListener("click", showInstallDialog);
    $("#install-button").addEventListener("click", showInstallDialog);
    $("#install-close").addEventListener("click", () => $("#install-dialog").close());
    $("#install-confirm").addEventListener("click", installApp);
    window.addEventListener("hashchange", () => routeTo(location.hash.slice(1), false));
    window.addEventListener("online", () => bootstrap({ quiet: true }));
    window.addEventListener("offline", () => { state.offline = true; updateNetwork(); toast("已离线：预测生成暂停"); });
  }

  function showInstallDialog() {
    $("#install-confirm").hidden = !state.deferredInstall;
    $("#install-dialog").showModal();
  }

  async function installApp() {
    if (!state.deferredInstall) return;
    state.deferredInstall.prompt();
    await state.deferredInstall.userChoice;
    state.deferredInstall = null;
    $("#install-dialog").close();
    $("#install-button").hidden = true;
  }

  window.addEventListener("beforeinstallprompt", event => {
    event.preventDefault();
    state.deferredInstall = event;
    $("#install-button").hidden = false;
  });
  window.addEventListener("appinstalled", () => { $("#install-button").hidden = true; toast("三鉴已安装"); });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => navigator.serviceWorker.register("/sw.js").catch(() => {}));
  }

  wireEvents();
  routeTo(location.hash.slice(1), false);
  bootstrap();
})();
