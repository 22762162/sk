/* Brain data stays in this page's memory, never in the offline cache. */
window.createSanjianBrain = ({ $, $$, esc, api, state, options }) => {
  let token = "", scopes = [], binding = null, preview = null, approval = null;
  let generation = 0, bindingGeneration = 0;
  let expiryTimer = null;
  const currentMonth = () => {
    const parts = new Intl.DateTimeFormat("en", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit" }).formatToParts(new Date());
    return `${parts.find(p => p.type === "year").value}-${parts.find(p => p.type === "month").value}`;
  };
  const target = () => `${$("#question-scene").value}/${$("#question-company").value}/${$("#question-project").value}/${currentMonth()}`;
  const displayTime = value => new Intl.DateTimeFormat("zh-CN", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
  const headers = () => token ? { "X-Sanjian-Brain-Access": token } : {};
  const request = (path, body) => api(`/api/app/brain/${path}`, {
    method: body ? "POST" : "GET", headers: headers(), cache: "no-store",
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  const notice = text => { $("#brain-status").textContent = text; };

  function reset() {
    clearTimeout(expiryTimer);
    generation += 1; preview = null; approval = null;
    $("#brain-items").replaceChildren();
    $("#brain-confirm-area").hidden = true;
    $("#brain-external-confirm").checked = false;
    $("#brain-preview-status").textContent = "可选：先读取本月资料，再逐条确认。未确认时不带大脑资料。";
    $("#question-brain").hidden = $("#question-scene").value !== "company";
    $("#brain-preview").disabled = !token || state.questionBusy;
    $("#question-scope-confirm").checked = false;
  }

  function lock() {
    token = ""; scopes = []; binding = null; bindingGeneration += 1;
    $("#brain-access").value = "";
    $("#brain-binding-area").hidden = true;
    notice("未解锁 · 只读出口需先由管理员安全配置。");
    reset();
  }

  async function loadBinding() {
    const serial = ++bindingGeneration;
    binding = null; $("#brain-bind").disabled = true;
    $("#brain-binding-status").textContent = "请选择公司及授权来源范围。";
    if (!token || !state.companyId) return;
    const companyId = state.companyId, projectId = $("#brain-project").value;
    try {
      const result = await request(`binding?company_id=${encodeURIComponent(companyId)}&project_id=${encodeURIComponent(projectId)}`);
      if (serial !== bindingGeneration) return;
      binding = result.binding;
      options($("#brain-scope"), scopes.map(s => ({ ...s, name: s.label })), "请选择明确授权的来源", binding?.scope_id || "");
      $("#brain-binding-status").textContent = binding ? `已绑定 · v${binding.version} · 改绑会撤销旧确认` : "此公司／项目尚未绑定。不会自动按名称匹配。";
      $("#brain-bind").disabled = false;
    } catch (error) { if (serial === bindingGeneration) $("#brain-binding-status").textContent = error.message; }
  }

  function companyChanged() {
    options($("#brain-project"), state.desk.projects.filter(p => p.company_id === state.companyId), "公司整体");
    reset(); loadBinding();
  }

  async function unlock() {
    const candidate = $("#brain-access").value;
    if (candidate.length < 32) { notice("请输入管理员提供的访问口令（至少 32 位），不是模型 API Key。"); return; }
    token = candidate; $("#brain-access").value = "";
    const serial = ++bindingGeneration;
    const button = $("#brain-unlock"); button.disabled = true;
    try {
      const result = await request("scopes");
      if (serial !== bindingGeneration) return;
      scopes = result.scopes;
      notice(`出口连接成功 · ${scopes.length} 个授权范围 · 口令仅在当前页面保留`);
      $("#brain-binding-area").hidden = false;
      companyChanged();
    } catch (error) { if (serial === bindingGeneration) { lock(); notice(error.message); } }
    finally { button.disabled = false; }
  }

  async function bind() {
    const companyId = state.companyId, projectId = $("#brain-project").value;
    if (!companyId || !$("#brain-scope").value) { $("#brain-binding-status").textContent = "请选择公司和授权来源范围。"; return; }
    const serial = bindingGeneration;
    $("#brain-bind").disabled = true; reset();
    try {
      const result = await request("binding", { company_id: companyId, project_id: projectId,
        scope_id: $("#brain-scope").value, expected_version: binding?.version || 0 });
      if (serial !== bindingGeneration) return;
      binding = result.binding;
      $("#brain-binding-status").textContent = `绑定已保存 · v${binding.version}。请到问事页预览资料。`;
    } catch (error) { if (serial === bindingGeneration) $("#brain-binding-status").textContent = error.message; }
    finally { if (serial === bindingGeneration) $("#brain-bind").disabled = false; }
  }

  async function readPreview() {
    reset();
    const serial = generation, key = target(), button = $("#brain-preview");
    if (!token || !$("#question-company").value) { $("#brain-preview-status").textContent = "请先选择公司，并在公司页解锁和绑定大脑范围。"; return; }
    button.disabled = true;
    $("#brain-preview-status").textContent = "正在读取已绑定范围…";
    try {
      const result = await request("preview", { company_id: $("#question-company").value,
        project_id: $("#question-project").value, period: currentMonth() });
      if (serial !== generation || key !== target()) return;
      preview = result.preview;
      expiryTimer = setTimeout(() => { reset(); $("#brain-preview-status").textContent = "预览已过期并清除；如需带入请重新读取。"; }, Math.max(0, Date.parse(preview.expires_at) - Date.now()));
      const c = preview.coverage;
      $("#brain-preview-status").textContent = `${preview.period} · 读取于 ${displayTime(preview.fetched_at)}（北京时间）· 10 分钟内有效。${c.knowledge_truncated ? "知识仅显示最新部分。" : ""}${c.revenue_complete ? "流水覆盖检查完整（不代表审计确认）。" : `流水缺少 ${c.revenue_missing_groups} 组，不展示部分总额，也不视为零。`}`;
      $("#brain-items").innerHTML = preview.items.map((item, index) => {
        const allowed = ["L1", "L2"].includes(item.level) && item.kind === "knowledge";
        return `<article class="brain-source"><div class="brain-source-meta"><strong>${esc(item.level)} · ${allowed ? "可整理摘要" : "仅在此查看"}</strong><span>${esc(item.source_system)}</span></div><p class="brain-source-text">${esc(item.text)}</p><small>来源记录时间：${esc(displayTime(item.known_at))}（北京时间） · ${item.kind === "revenue" ? "来源方报送，非审计报表，非个人收入" : "来源标记已确认，仍需本人核对"}</small>${allowed ? `<label class="check-line"><input type="checkbox" data-brain-select="${index}"><span>将本条去标识摘要用于这一次问事</span></label><label class="field">去标识摘要<textarea data-brain-summary="${index}" rows="2" maxlength="400" placeholder="只写必要事实，删除人名、联系方式、账号、精确地址及机密；不要直接粘贴整段原文"></textarea></label>` : "<p class=\"field-hint\">L3/L4 本期不允许发送给云端模型。</p>"}</article>`;
      }).join("") || '<p class="field-hint">此范围本月没有可用资料，不等于公司没有业务。</p>';
      $("#brain-confirm-area").hidden = !preview.items.some(i => ["L1", "L2"].includes(i.level) && i.kind === "knowledge");
    } catch (error) { if (serial === generation) $("#brain-preview-status").textContent = error.message; }
    finally { if (serial === generation) button.disabled = !token || state.questionBusy; }
  }

  async function confirm() {
    if (!preview) return;
    const summaries = {};
    $$("[data-brain-select]:checked").forEach(input => {
      const index = input.dataset.brainSelect;
      summaries[preview.items[Number(index)].id] = $(`[data-brain-summary="${index}"]`).value.trim();
    });
    if (!Object.keys(summaries).length || !$("#brain-external-confirm").checked) {
      $("#brain-preview-status").textContent = "请勾选至少一条来源、填写去标识摘要，并确认云端使用。"; return;
    }
    const serial = generation, key = target(), button = $("#brain-confirm"); button.disabled = true;
    try {
      const result = await request("confirm", { preview_id: preview.id, summaries, external_confirmed: true });
      if (serial !== generation || key !== target()) return;
      approval = { ...result.snapshot, key }; preview = null;
      $("#brain-items").replaceChildren(); $("#brain-confirm-area").hidden = true;
      $("#brain-preview-status").textContent = `已确认 ${approval.item_count} 条摘要，请尽快提交，仅用于下一条问事；有效至 ${displayTime(approval.expires_at)}（北京时间）。原始预览已从页面清除。`;
      $("#question-scope-confirm").checked = false;
    } catch (error) { if (serial === generation) $("#brain-preview-status").textContent = error.message; }
    finally { button.disabled = false; }
  }

  function forQuestion() {
    if (!approval) return {};
    if (!token || approval.key !== target() || Date.parse(approval.expires_at) <= Date.now()) {
      reset(); throw new Error("大脑确认已过期或范围变化，请重新预览确认，或不带大脑资料发问。");
    }
    return { brain_snapshot_id: approval.id };
  }

  $("#brain-unlock").addEventListener("click", unlock);
  $("#brain-lock").addEventListener("click", lock);
  $("#brain-project").addEventListener("change", () => { reset(); loadBinding(); });
  $("#brain-bind").addEventListener("click", bind);
  $("#brain-preview").addEventListener("click", readPreview);
  $("#brain-confirm").addEventListener("click", confirm);
  $("#brain-clear").addEventListener("click", reset);
  window.addEventListener("pagehide", lock);
  document.addEventListener("visibilitychange", () => { if (document.hidden) lock(); });
  window.addEventListener("offline", lock);
  lock();
  return { reset, companyChanged, headers, forQuestion, lock };
};
