(() => {
  "use strict";

  const bridge = window.AstrBotPluginPage;
  const $ = (selector) => document.querySelector(selector);
  const state = { subscriptions: [], selectedUmo: null, search: "", sessionSearch: "", upCache: new Map(), editing: null, returnFocus: null, confirmAction: null, logoFile: null, logoPreviewUrl: "" };
  const typeNames = {
    video: "过滤视频", draw: "过滤图文", article: "过滤专栏",
    forward: "过滤转发", lottery: "过滤抽奖", live: "过滤直播",
    live_end: "仅过滤下播", forward_lottery: "过滤转发抽奖"
  }; 

  const elements = {
    connection: $("#connection-state"), loading: $("#loading-state"), table: $("#table-wrap"), empty: $("#empty-state"),
    body: $("#subscription-body"), sessionList: $("#session-list"), sessionCount: $("#session-count"),
    resultCount: $("#result-count"), caption: $("#selected-session-caption"), deleteSession: $("#delete-session-button"),
    drawer: $("#subscription-drawer"), drawerBackdrop: $("#drawer-backdrop"), form: $("#subscription-form"), formMessage: $("#form-message"),
    drawerTitle: $("#drawer-title"), drawerKicker: $("#drawer-kicker"), upPreview: $("#up-preview"),
    logoPreview: $("#logo-preview"), logoStatus: $("#logo-status"), logoInput: $("#logo-file"), logoFileName: $("#logo-file-name"),
    chooseLogo: $("#choose-logo"), uploadLogo: $("#upload-logo"), resetLogo: $("#reset-logo"),
    confirm: $("#confirm-dialog"), confirmTitle: $("#confirm-title"), confirmDescription: $("#confirm-description")
  };

  function unwrap(response) {
    if (response && typeof response === "object" && "data" in response) return response.data;
    return response;
  }

  function apiGet(route) {
    if (!bridge || typeof bridge.apiGet !== "function") throw new Error("AstrBot Plugin Page bridge 不可用。");
    return bridge.apiGet(route);
  }

  function apiUpload(route, file) {
    if (!bridge || typeof bridge.upload !== "function") throw new Error("当前 AstrBot 版本不支持文件上传。");
    return bridge.upload(route, file);
  }

  function apiPost(route, payload) {
    if (!bridge || typeof bridge.apiPost !== "function") throw new Error("AstrBot Plugin Page bridge 不可用。");
    return bridge.apiPost(route, payload);
  }

  function setConnection(kind, text) {
    elements.connection.className = `connection-state ${kind || ""}`;
    elements.connection.innerHTML = "<i></i> ";
    elements.connection.append(document.createTextNode(text));
  }

  function text(value, fallback = "—") {
    return value === undefined || value === null || value === "" ? fallback : String(value);
  }

  function listOf(value) {
    if (Array.isArray(value)) return value;
    if (typeof value === "string") return value.split(",").map((item) => item.trim()).filter(Boolean);
    return [];
  }

  function readSubscriptions(payload) {
    const data = unwrap(payload);
    if (Array.isArray(data)) return data.map((item) => normalizeRecord(item));
    if (Array.isArray(data?.sessions)) {
      return data.sessions.flatMap((session) => {
        const rows = Array.isArray(session?.subscriptions) ? session.subscriptions : [];
        return rows.map((item) => normalizeRecord(item, session.umo));
      });
    }
    const source = data && (data.subscriptions || data.items || data.records);
    if (Array.isArray(source)) return source.map((item) => normalizeRecord(item));
    const sessions = source && typeof source === "object" ? source : (data && typeof data === "object" ? data : {});
    return Object.entries(sessions).flatMap(([umo, records]) => {
      const rows = Array.isArray(records) ? records : (records && (records.subscriptions || records.items)) || [];
      return Array.isArray(rows) ? rows.map((item) => normalizeRecord(item, umo)) : [];
    });
  }

  function normalizeRecord(record, fallbackUmo = "") {
    const row = record || {};
    return {
      umo: text(row.umo || row.sub_user || row.session || fallbackUmo, ""),
      uid: text(row.uid || row.up_uid || row.mid || row.user_id, ""),
      upName: row.up_name || row.name || row.uname || row.up?.name || "",
      filterTypes: listOf(row.filter_types || row.types || row.dynamic_types),
      filterRegex: Array.isArray(row.filter_regex) ? row.filter_regex.join("\n") : text(row.filter_regex || row.regex || row.filter, ""),
      atAll: Boolean(row.at_all),
      liveAtall: Boolean(row.live_atall),
      atSubUsers: listOf(row.at_sub_users),
      raw: row
    };
  }

  function getSessions() {
    const counts = new Map();
    state.subscriptions.forEach((row) => counts.set(row.umo, (counts.get(row.umo) || 0) + 1));
    return [...counts.entries()].map(([umo, count]) => ({ umo, count })).sort((a, b) => a.umo.localeCompare(b.umo, "zh-CN"));
  }

  function updateStats(statusPayload) {
    const status = unwrap(statusPayload) || {};
    const sessions = getSessions();
    const uniqueUps = new Set(state.subscriptions.map((row) => row.uid).filter(Boolean));
    const notifications = state.subscriptions.filter((row) => row.atAll || row.liveAtall || row.atSubUsers.length).length;
    const value = (keys, fallback) => keys.map((key) => status[key]).find((item) => Number.isFinite(Number(item))) ?? fallback;
    $("#stat-subscriptions").textContent = value(["subscription_count", "subscriptions", "total_subscriptions"], state.subscriptions.length);
    $("#stat-sessions").textContent = value(["session_count", "sessions", "active_sessions"], sessions.length);
    $("#stat-ups").textContent = value(["up_count", "ups", "upstream_count"], uniqueUps.size);
    $("#stat-notifications").textContent = value(["notification_count", "notifications"], notifications);
  }

  function renderSessions() {
    const sessions = getSessions();
    const query = state.sessionSearch.toLocaleLowerCase();
    const visible = sessions.filter((session) => session.umo.toLocaleLowerCase().includes(query));
    elements.sessionList.replaceChildren();
    elements.sessionCount.textContent = sessions.length;
    if (!sessions.length) {
      const empty = document.createElement("p"); empty.className = "field-hint"; empty.textContent = "暂无可管理的会话。"; elements.sessionList.append(empty); return;
    }
    visible.forEach((session) => {
      const option = document.createElement("button");
      option.type = "button"; option.className = "session-option"; option.role = "option";
      option.setAttribute("aria-selected", String(session.umo === state.selectedUmo)); option.dataset.umo = session.umo;
      const name = document.createElement("span"); name.textContent = session.umo;
      const count = document.createElement("small"); count.textContent = `${session.count} 条订阅`;
      option.append(name, count); elements.sessionList.append(option);
    });
    if (!visible.length) { const empty = document.createElement("p"); empty.className = "field-hint"; empty.textContent = "未找到会话。"; elements.sessionList.append(empty); }
  }

  function addChip(container, label, style) {
    const chip = document.createElement("span"); chip.className = `chip ${style || ""}`; chip.textContent = label; container.append(chip);
  }

  function renderTable() {
    const sessionRows = state.subscriptions.filter((row) => row.umo === state.selectedUmo);
    const query = state.search.toLocaleLowerCase();
    const rows = sessionRows.filter((row) => [row.uid, row.upName, row.filterRegex, ...row.filterTypes].join(" ").toLocaleLowerCase().includes(query));
    elements.caption.textContent = state.selectedUmo || "选择一个会话";
    elements.deleteSession.disabled = !state.selectedUmo || !sessionRows.length;
    elements.resultCount.textContent = state.selectedUmo ? `显示 ${rows.length} / ${sessionRows.length} 条` : "";
    elements.body.replaceChildren();
    elements.loading.hidden = true;
    elements.table.hidden = !rows.length;
    elements.empty.hidden = Boolean(rows.length) || !state.selectedUmo;
    if (!rows.length) {
      if (state.selectedUmo && query) { elements.empty.querySelector("h3").textContent = "没有匹配的订阅"; elements.empty.querySelector("p").textContent = "换个关键词，或新建一条规则。"; }
      else { elements.empty.querySelector("h3").textContent = "这里还没有订阅"; elements.empty.querySelector("p").textContent = "新建一条规则，开始接收 UP 主动态。"; }
      return;
    }
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      const up = document.createElement("td"); const upBox = document.createElement("div"); upBox.className = "up-cell";
      const avatar = document.createElement("span"); avatar.className = "avatar"; avatar.textContent = (row.upName || row.uid || "?").slice(0, 1).toUpperCase();
      const details = document.createElement("div"); const name = document.createElement("strong"); name.textContent = row.upName || "UP 主信息待加载";
      const uid = document.createElement("small"); uid.textContent = `UID ${row.uid || "未知"}`; details.append(name, uid); upBox.append(avatar, details); up.append(upBox);
      const types = document.createElement("td"); const typesBox = document.createElement("div"); typesBox.className = "chips";
      (row.filterTypes.length ? row.filterTypes : ["全部动态"]).forEach((type) => addChip(typesBox, typeNames[type] || type)); types.append(typesBox);
      const regex = document.createElement("td"); regex.className = "muted-cell"; regex.title = row.filterRegex || ""; regex.textContent = row.filterRegex || "未设置";
      const alerts = document.createElement("td"); const alertBox = document.createElement("div"); alertBox.className = "chips";
      if (row.atAll) addChip(alertBox, "@全体", "all"); if (row.liveAtall) addChip(alertBox, "开播 @全体", "live"); if (row.atSubUsers.length) addChip(alertBox, `@${row.atSubUsers.length} 人`); if (!alertBox.children.length) addChip(alertBox, "普通推送"); alerts.append(alertBox);
      const actions = document.createElement("td"); const actionBox = document.createElement("div"); actionBox.className = "row-actions";
      [["编辑", "edit"], ["删除", "delete"]].forEach(([label, action]) => { const button = document.createElement("button"); button.type = "button"; button.className = `row-action ${action}`; button.textContent = label; button.dataset.action = action; button.dataset.umo = row.umo; button.dataset.uid = row.uid; actionBox.append(button); }); actions.append(actionBox);
      tr.append(up, types, regex, alerts, actions); elements.body.append(tr);
    });
  }

  async function fetchUp(uid) {
    if (!uid) return null;
    if (state.upCache.has(uid)) return state.upCache.get(uid);
    const data = unwrap(await apiGet(`up/${encodeURIComponent(uid)}`)) || {};
    const name = data.name || data.uname || data.nickname || data.user?.name || "";
    state.upCache.set(uid, name);
    return name;
  }

  async function hydrateUpNames() {
    const pending = [...new Set(state.subscriptions
      .filter((row) => row.umo === state.selectedUmo && row.uid && !row.upName)
      .map((row) => row.uid))].slice(0, 25);
    await Promise.allSettled(pending.map(async (uid) => {
      const name = await fetchUp(uid);
      if (name) state.subscriptions.forEach((row) => { if (row.uid === uid) row.upName = name; });
    }));
  }

  function renderLogo(payload) {
    const data = unwrap(payload) || {};
    elements.logoStatus.className = "logo-status";
    if (data.data_url) elements.logoPreview.src = data.data_url;
    elements.resetLogo.disabled = !data.customized;
    elements.logoStatus.textContent = data.customized
      ? `已使用自定义图片${data.width && data.height ? `（${data.width}×${data.height}）` : ""}`
      : "当前使用插件默认图片";
  }

  async function loadLogo() {
    try {
      renderLogo(await apiGet("logo"));
    } catch (error) {
      elements.logoStatus.textContent = error.message || "无法读取当前图片";
      elements.logoStatus.className = "logo-status error-text";
    }
  }

  function handleLogoFile(event) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      elements.logoStatus.textContent = "图片不能超过 5 MB。";
      elements.logoStatus.className = "logo-status error-text";
      event.target.value = "";
      return;
    }
    if (state.logoPreviewUrl) URL.revokeObjectURL(state.logoPreviewUrl);
    state.logoFile = file;
    state.logoPreviewUrl = URL.createObjectURL(file);
    elements.logoPreview.src = state.logoPreviewUrl;
    elements.logoFileName.textContent = file.name;
    elements.uploadLogo.disabled = false;
    elements.logoStatus.className = "logo-status";
    elements.logoStatus.textContent = "已选择图片，点击上传并应用。";
  }

  async function uploadLogo() {
    if (!state.logoFile) return;
    elements.uploadLogo.disabled = true;
    elements.chooseLogo.disabled = true;
    elements.logoStatus.className = "logo-status";
    elements.logoStatus.textContent = "正在上传并处理…";
    try {
      renderLogo(await apiUpload("logo/upload", state.logoFile));
      elements.logoFileName.textContent = "未选择新图片";
      elements.logoInput.value = "";
      if (state.logoPreviewUrl) URL.revokeObjectURL(state.logoPreviewUrl);
      state.logoFile = null; state.logoPreviewUrl = "";
      toast("渲染头像已更新。");
    } catch (error) {
      elements.logoStatus.className = "logo-status error-text";
      elements.logoStatus.textContent = error.message || "上传失败，请稍后重试。";
    } finally {
      elements.chooseLogo.disabled = false;
      elements.uploadLogo.disabled = !state.logoFile;
    }
  }

  async function resetLogo() {
    try {
      renderLogo(await apiPost("logo/reset", {}));
      elements.logoFileName.textContent = "未选择新图片";
      elements.logoInput.value = "";
      if (state.logoPreviewUrl) URL.revokeObjectURL(state.logoPreviewUrl);
      state.logoFile = null; state.logoPreviewUrl = "";
      elements.uploadLogo.disabled = true;
      toast("已恢复默认渲染头像。");
    } catch (error) {
      toast(error.message || "恢复默认头像失败，请稍后重试。", true);
    }
  }

  async function load() {
    elements.loading.hidden = false; elements.table.hidden = true; elements.empty.hidden = true;
    setConnection("", "正在同步");
    try {
      const [subscriptions, status] = await Promise.all([apiGet("subscriptions"), apiGet("status")]);
      state.subscriptions = readSubscriptions(subscriptions).filter((row) => row.umo && row.uid);
      const sessions = getSessions();
      if (!sessions.some((item) => item.umo === state.selectedUmo)) state.selectedUmo = sessions[0]?.umo || null;
      updateStats(status); renderSessions(); renderTable(); setConnection("connected", "已同步");
      hydrateUpNames().then(() => { renderTable(); renderSessions(); }).catch(() => {});
    } catch (error) {
      console.error("无法读取订阅数据", error); setConnection("error", "连接失败");
      elements.loading.hidden = true; elements.empty.hidden = false;
      elements.empty.querySelector("h3").textContent = "无法读取订阅"; elements.empty.querySelector("p").textContent = error.message || "请确认插件页面 bridge 可用后重试。";
      toast("读取订阅失败，请稍后重试。", true);
    }
  }

  function openDrawer(record = null, trigger = document.activeElement) {
    state.editing = record; state.returnFocus = trigger; elements.form.reset(); elements.formMessage.hidden = true;
    elements.drawerTitle.textContent = record ? "编辑订阅" : "添加订阅"; $("#drawer-kicker").textContent = record ? "更新规则" : "新建规则";
    const umo = elements.form.elements.umo, uid = elements.form.elements.uid;
    umo.disabled = Boolean(record); uid.disabled = Boolean(record);
    if (record) {
      umo.value = record.umo; uid.value = record.uid; elements.form.elements.filter_regex.value = record.filterRegex;
      elements.form.elements.at_all.checked = record.atAll; elements.form.elements.live_atall.checked = record.liveAtall;
      elements.form.elements.at_sub_users.value = record.atSubUsers.join(", "); elements.upPreview.textContent = record.upName ? `已识别：${record.upName}` : `UID ${record.uid}`;
      [...elements.form.querySelectorAll("input[name=filter_types]")].forEach((input) => { input.checked = record.filterTypes.includes(input.value); });
    } else elements.upPreview.textContent = "输入 UID 后可查找 UP 主。";
    elements.drawer.hidden = false; elements.drawerBackdrop.hidden = false; document.body.style.overflow = "hidden";
    requestAnimationFrame(() => (record ? elements.form.elements.filter_regex : umo).focus());
  }

  function closeDrawer() {
    elements.drawer.hidden = true; elements.drawerBackdrop.hidden = true; document.body.style.overflow = ""; state.editing = null;
    if (state.returnFocus && typeof state.returnFocus.focus === "function") state.returnFocus.focus();
  }

  function showFormMessage(message) { elements.formMessage.textContent = message; elements.formMessage.hidden = false; }

  async function lookupUp() {
    const uid = elements.form.elements.uid.value.trim();
    if (!/^\d+$/.test(uid)) return showFormMessage("请输入仅包含数字的 UP 主 UID。");
    elements.formMessage.hidden = true; elements.upPreview.textContent = "正在查找…";
    try { const name = await fetchUp(uid); elements.upPreview.textContent = name ? `已识别：${name}` : "未返回 UP 主名称，但可继续保存。"; }
    catch (error) { elements.upPreview.textContent = "查找失败，请检查 UID 后重试。"; }
  }

  function payloadFromForm() {
    const form = elements.form.elements; const record = state.editing;
    return {
      umo: (record ? record.umo : form.umo.value).trim(), uid: (record ? record.uid : form.uid.value).trim(),
      filter_types: [...elements.form.querySelectorAll("input[name=filter_types]:checked")].map((input) => input.value),
      filter_regex: form.filter_regex.value.split("\n").map((value) => value.trim()).filter(Boolean), at_all: form.at_all.checked, live_atall: form.live_atall.checked,
      at_sub_users: form.at_sub_users.value.split(",").map((value) => value.trim()).filter(Boolean)
    };
  }

  async function saveSubscription(event) {
    event.preventDefault(); elements.formMessage.hidden = true;
    const payload = payloadFromForm();
    if (!payload.umo || !payload.uid) return showFormMessage("请填写会话 UMO 与 UP 主 UID。");
    if (!/^\d+$/.test(payload.uid)) return showFormMessage("UP 主 UID 只能包含数字。");
    const save = $("#save-subscription"); save.disabled = true; save.textContent = "正在保存…";
    try {
      await apiPost(state.editing ? "subscriptions/update" : "subscriptions/create", payload);
      toast(state.editing ? "订阅规则已更新。" : "订阅已创建。"); closeDrawer(); await load();
    } catch (error) { console.error("保存订阅失败", error); showFormMessage(error.message || "保存失败，请稍后重试。"); }
    finally { save.disabled = false; save.textContent = "保存订阅"; }
  }

  function confirm({ title, description, action, buttonText = "确认删除" }) {
    state.confirmAction = action; state.returnFocus = document.activeElement; elements.confirmTitle.textContent = title; elements.confirmDescription.textContent = description; $("#confirm-ok").textContent = buttonText; elements.confirm.hidden = false;
    requestAnimationFrame(() => $("#confirm-cancel").focus());
  }

  function closeConfirm() { elements.confirm.hidden = true; state.confirmAction = null; if (state.returnFocus?.focus) state.returnFocus.focus(); }

  async function deleteOne(umo, uid) {
    try { await apiPost("subscriptions/delete", { umo, uid }); toast("订阅已删除。"); await load(); }
    catch (error) { console.error("删除订阅失败", error); toast(error.message || "删除失败，请稍后重试。", true); }
  }

  async function deleteSession(umo) {
    try { await apiPost("sessions/delete-all", { umo }); toast("该会话的订阅已清空。"); await load(); }
    catch (error) { console.error("清空会话失败", error); toast(error.message || "清空失败，请稍后重试。", true); }
  }

  function toast(message, isError = false) { const item = document.createElement("div"); item.className = `toast${isError ? " error" : ""}`; item.textContent = message; $("#toast-region").append(item); window.setTimeout(() => item.remove(), 4200); }

  $("#create-button").addEventListener("click", (event) => openDrawer(null, event.currentTarget));
  document.querySelectorAll(".empty-create").forEach((button) => button.addEventListener("click", (event) => openDrawer(null, event.currentTarget)));
  $("#refresh-button").addEventListener("click", () => { load(); loadLogo(); });
  elements.chooseLogo.addEventListener("click", () => elements.logoInput.click());
  elements.logoInput.addEventListener("change", handleLogoFile);
  elements.uploadLogo.addEventListener("click", uploadLogo);
  elements.resetLogo.addEventListener("click", () => confirm({ title: "恢复默认渲染头像？", description: "将删除当前自定义图片，后续卡片恢复使用插件默认头像。", action: resetLogo, buttonText: "恢复默认" }));
  $("#session-filter").addEventListener("input", (event) => { state.sessionSearch = event.target.value; renderSessions(); });
  $("#subscription-search").addEventListener("input", (event) => { state.search = event.target.value; renderTable(); });
  elements.sessionList.addEventListener("click", (event) => { const option = event.target.closest("[data-umo]"); if (!option) return; state.selectedUmo = option.dataset.umo; state.search = ""; $("#subscription-search").value = ""; renderSessions(); renderTable(); hydrateUpNames().then(() => renderTable()).catch(() => {}); });
  elements.body.addEventListener("click", (event) => { const button = event.target.closest("button[data-action]"); if (!button) return; const row = state.subscriptions.find((item) => item.umo === button.dataset.umo && item.uid === button.dataset.uid); if (button.dataset.action === "edit" && row) openDrawer(row, button); if (button.dataset.action === "delete") confirm({ title: "删除这条订阅？", description: `将停止向当前会话推送 UID ${button.dataset.uid} 的动态，此操作无法撤销。`, action: () => deleteOne(button.dataset.umo, button.dataset.uid) }); });
  elements.deleteSession.addEventListener("click", () => { const count = state.subscriptions.filter((row) => row.umo === state.selectedUmo).length; confirm({ title: "清空此会话的订阅？", description: `将删除「${state.selectedUmo}」中的 ${count} 条订阅规则，此操作无法撤销。`, action: () => deleteSession(state.selectedUmo), buttonText: "清空会话" }); });
  $("#close-drawer").addEventListener("click", closeDrawer); $("#cancel-drawer").addEventListener("click", closeDrawer); elements.drawerBackdrop.addEventListener("click", closeDrawer); elements.form.addEventListener("submit", saveSubscription); $("#lookup-up").addEventListener("click", lookupUp);
  $("#confirm-cancel").addEventListener("click", closeConfirm); $("#confirm-ok").addEventListener("click", async () => { const action = state.confirmAction; closeConfirm(); if (action) await action(); });
  document.addEventListener("keydown", (event) => { if (event.key !== "Escape") return; if (!elements.confirm.hidden) closeConfirm(); else if (!elements.drawer.hidden) closeDrawer(); });

  async function initialize() {
    if (!bridge) {
      setConnection("error", "Bridge 不可用");
      return;
    }
    try {
      await bridge.ready();
      await Promise.all([load(), loadLogo()]);
    } catch (error) {
      console.error("Plugin Page 初始化失败", error);
      setConnection("error", "连接失败");
      elements.loading.hidden = true;
      elements.empty.hidden = false;
      elements.empty.querySelector("h3").textContent = "页面初始化失败";
      elements.empty.querySelector("p").textContent = error.message || "请刷新页面后重试。";
    }
  }

  initialize();
})();
