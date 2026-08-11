(() => {
  "use strict";

  const CACHE_KEY = "sanjian.pwa.private-cache.v2";
  const ROUTES = new Set(["home", "question", "records", "profile"]);
  const OUTCOMES = { hit: "命中", partial: "部分命中", miss: "未命中", unclear: "无法判断" };
  const TENDENCIES = { favorable: "偏顺", caution: "留意", neutral: "中性" };
  const state = {
    profiles: [], activeProfile: null, predictions: [], stats: null, today: null,
    route: "home", filter: "", offline: !navigator.onLine, deferredInstall: null,
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

  async function api(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: options.body ? { "Content-Type": "application/json", ...(options.headers || {}) } : options.headers,
    });
    let data;
    try { data = await response.json(); } catch (_) { data = { ok: false, error: "服务返回了无法解析的内容" }; }
    if (!response.ok || !data.ok) throw new Error(data.error || `请求失败（${response.status}）`);
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
    loadTodayReading();
  }

  function updateNetwork() {
    state.offline = state.offline || !navigator.onLine;
    $("#network-banner").hidden = !state.offline;
    $("#question-submit").disabled = state.offline || !state.activeProfile;
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
    $("#profile-chip-label").textContent = state.activeProfile?.name || "未建基本盘";
    $("#question-no-profile").hidden = !!state.activeProfile;
    $("#question-form").hidden = !state.activeProfile;
    renderQuestionResearch();
    renderToday();
    renderHomeReviews();
    renderRecords();
    renderProfiles();
    renderStats();
  }

  function renderQuestionResearch() {
    const box = $("#question-research-status");
    const profile = state.activeProfile;
    if (!profile) { box.hidden = true; return; }
    box.hidden = false;
    const linked = Boolean(String(profile.research_context || "").trim());
    box.innerHTML = linked
      ? `<strong>已关联高级研究资料 · v${esc(profile.research_version || 1)}</strong><br>本次问事会结合已确认事实；大运、神煞与流年将重新计算。`
      : `<strong>尚未关联高级研究资料</strong><br>本次仍会使用基本盘与流运；可到“我的 → 编辑”确认事实资料。`;
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
      <div id="today-reading" class="muted"></div>`;
  }

  async function loadTodayReading() {
    const slot = document.getElementById("today-reading");
    if (!slot || !state.activeProfile || !navigator.onLine) return;
    slot.textContent = "今日解读生成中…";
    try {
      const d = await api(`/api/app/today-reading?profile_id=${encodeURIComponent(state.activeProfile.id)}`);
      const t = { favorable: "#3f7d55", caution: "#b5762a", neutral: "#6b6459" }[d.tendency] || "#6b6459";
      slot.innerHTML = `<div style="border-left:3px solid ${t};padding:6px 10px;border-radius:6px;background:rgba(125,90,60,0.06);margin-top:8px;">
        <div>${esc(d.reading || "")}</div>
        <div style="margin-top:4px;"><b>宜</b> ${esc(d.do || "")} ｜ <b>忌</b> ${esc(d.avoid || "")}</div>
        <div style="font-size:11px;opacity:.7;margin-top:3px;">${esc(d.day_ganzhi || "")}日 · ${esc(d.jianchu || "")}日 · 传统日课参考</div></div>`;
    } catch (error) {
      slot.textContent = "";
    }
  }

  const duePredictions = () => {
    const today = new Date().toISOString().slice(0, 10);
    return state.predictions.filter(p => !p.review && String(p.period_end || "") <= today);
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
    const natal = basis.natal_computed_facts || {};
    const transit = basis.transit_computed_facts || {};
    return `<article class="prediction-card card">
      <div class="prediction-head">
        <div class="prediction-meta"><span>${esc(s.category_label || prediction.category)} · ${s.period === "day" ? "今天" : "本月"} · ${esc(fmtDate(s.asked_at || prediction.asked_at))}</span><span class="lock-badge">🔒 原始预测已锁定</span></div>
        <div class="prediction-question">${esc(s.question || prediction.question)}</div>
        <p class="prediction-conclusion">${esc(s.conclusion || "")}</p>
      </div>
      <div class="prediction-body">
        <div class="confidence-row" aria-label="${esc(confidenceLabel(s))}，${pct}%"><strong>${esc(confidenceLabel(s))}</strong><div class="confidence-track"><span style="width:${Math.max(0, Math.min(pct, 100))}%"></span></div><small>${pct}%</small></div>
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
    return `<article class="record-card card">
      <div class="record-summary">
        <div class="record-top"><span class="record-category">${esc(s.category_label || p.category || "问事")}</span><span class="record-date">${esc(fmtDate(p.locked_at))}</span></div>
        <div class="record-question">${esc(s.question || p.question)}</div>
        <p class="record-conclusion">${esc(s.conclusion || "")}</p>
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
      <div class="profile-main"><strong>${esc(p.name)}${p.is_active ? " · 当前" : ""}</strong><small>${esc(p.birth)} · ${p.gender === "male" ? "男" : "女"} · ${esc(p.place || "未填出生地")} · ${p.research_context ? `研究资料 v${esc(p.research_version)}` : "未关联研究资料"} · 基本盘 v${esc(p.version)}</small></div>
      <div class="profile-row-actions">${p.is_active ? "" : `<button type="button" class="profile-activate" data-id="${esc(p.id)}">切换</button>`}<button type="button" class="profile-edit" data-id="${esc(p.id)}">编辑</button></div>
    </div>`).join("");
    $$(".profile-activate", box).forEach(button => button.addEventListener("click", () => activateProfile(button.dataset.id)));
    $$(".profile-edit", box).forEach(button => button.addEventListener("click", () => openProfileForm(button.dataset.id)));
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
    box.innerHTML = `<div class="stats-overview"><div class="stats-copy"><strong>${esc(headline)}</strong><p>${esc(copy)}<br>${esc(state.stats.policy || "")}</p></div><div class="sample-ring" aria-label="${esc(headline)}">${n}/${min}</div></div>${groups}`;
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
        toast("高级研究中还没有本人录入的事实记录");
        return;
      }
      $("#profile-research").value = data.candidate_context || "";
      $("#profile-research-source").value = data.source || "advanced_dossier_reviewed";
      $("#profile-research-status").textContent = `待确认 · ${data.facts.length} 条`;
      toast(`已载入 ${data.facts.length} 条事实；检查后保存才会生效`);
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
    if (!navigator.onLine) { setError("#question-error", "当前离线，不能生成预测；已缓存记录仍可查看。"); return; }
    if (!state.activeProfile) { setError("#question-error", "请先创建基本盘"); return; }
    if (!form.reportValidity()) return;
    const body = {
      profile_id: state.activeProfile.id,
      period: $("input[name=period]:checked", form).value,
      category: $("#question-category").value,
      question: $("#question-text").value.trim(),
      background: $("#question-background").value.trim(),
    };
    const button = $("#question-submit");
    const progress = $("#question-progress");
    const progressText = $("#question-progress-text");
    button.disabled = true;
    progress.hidden = false;
    $("#prediction-result").innerHTML = "";
    const started = Date.now();
    try {
      const start = await api("/api/app/questions/start", { method: "POST", body: JSON.stringify(body) });
      let final = null;
      for (let i = 0; i < 100; i += 1) {
        await new Promise(resolve => setTimeout(resolve, 3000));
        const elapsed = Math.round((Date.now() - started) / 1000);
        progressText.textContent = `原问题已锁定，推演进行中 · ${elapsed} 秒`;
        const job = await api(`/api/consult/result?job_id=${encodeURIComponent(start.job_id)}`);
        if (job.status !== "running") { final = job; break; }
      }
      if (!final || final.status !== "done" || !final.result?.prediction) {
        throw new Error(final?.result?.error || "生成超时；服务端若仍在运行，可稍后到记录页刷新查看");
      }
      const prediction = final.result.prediction;
      state.predictions = [prediction, ...state.predictions.filter(p => p.id !== prediction.id)];
      persistCache();
      $("#prediction-result").innerHTML = snapshotCard(prediction);
      renderHomeReviews();
      renderRecords();
      form.reset();
      toast("预测已锁定，可在记录页随时查看");
      $("#prediction-result").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) { setError("#question-error", error.message); }
    finally { button.disabled = state.offline || !state.activeProfile; progress.hidden = true; }
  }

  function openReview(id) {
    if (state.offline) { toast("离线时只能查看，联网后再提交复盘"); return; }
    const prediction = state.predictions.find(p => p.id === id);
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
      state.stats = data.stats;
      persistCache();
      $("#review-dialog").close();
      renderAll();
      toast("复盘已锁定，历史预测保持不变");
    } catch (error) { setError("#review-error", error.message); }
    finally { button.disabled = false; }
  }

  function wireEvents() {
    document.addEventListener("click", event => {
      const routeButton = event.target.closest("[data-route]");
      if (routeButton) routeTo(routeButton.dataset.route);
    });
    $$(".quick-card").forEach(button => button.addEventListener("click", () => {
      $("#question-category").value = button.dataset.category;
      routeTo("question");
      $("#question-text").focus();
    }));
    $$(".filter").forEach(button => button.addEventListener("click", () => {
      state.filter = button.dataset.filter;
      renderRecords();
    }));
    $("#question-form").addEventListener("submit", submitQuestion);
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
