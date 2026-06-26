const views = [
  ["corpus", "語料"],
  ["resources", "知識資源"],
  ["pipeline", "處理流程"],
  ["search", "檢索"],
  ["timeline", "時間軸"],
  ["charts", "統計圖"],
  ["exports", "導出"],
  ["settings", "設定"],
];

const state = {
  view: "corpus",
  stats: {},
  timelineFilters: {},
  timelineFocusId: "",
  aiResults: {},
};

const $ = (selector) => document.querySelector(selector);

function api(path, options = {}) {
  return fetch(path, {
    headers: options.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...options,
  }).then(async (response) => {
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(parseApiError(detail) || response.statusText);
    }
    return response.json();
  });
}

function parseApiError(detail) {
  try {
    const payload = JSON.parse(detail);
    if (typeof payload.detail === "string") return payload.detail;
    if (Array.isArray(payload.detail)) return payload.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
    return payload.message || detail;
  } catch {
    return detail;
  }
}

function reportError(error) {
  console.error(error);
  toast(error instanceof Error ? error.message : String(error));
}

function guarded(action) {
  return (...args) => Promise.resolve(action(...args)).catch(reportError);
}

function toast(message) {
  const template = $("#toastTemplate");
  const node = template.content.firstElementChild.cloneNode(true);
  node.textContent = message;
  $("#toasts").appendChild(node);
  setTimeout(() => node.remove(), 4200);
}

function escapeHtml(value = "") {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[char]);
}

function nl2br(value = "") {
  return escapeHtml(value).replace(/\n/g, "<br />");
}

function sum(items = []) {
  return items.reduce((total, item) => total + Number(item.count || 0), 0);
}

function splitCsv(value = "") {
  return String(value || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function renderNav() {
  $("#nav").innerHTML = views
    .map(([id, label], index) => `<button class="nav-item ${state.view === id ? "active" : ""}" data-view="${id}"><span>${label}</span><small>${index + 1}</small></button>`)
    .join("");
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      render();
    });
  });
}

async function loadStats() {
  const [corpus, charts] = await Promise.all([api("/api/corpus/stats"), api("/api/analytics/charts")]);
  state.stats = { corpus, charts };
  $("#stats").innerHTML = [
    ["段落", corpus.documents || 0],
    ["卷數", corpus.volumes || 0],
    ["字數", corpus.characters || 0],
    ["事件", sum(charts.by_event)],
  ]
    .map(([label, value]) => `<div class="stat-card"><strong>${escapeHtml(value)}</strong><span>${label}</span></div>`)
    .join("");
}

function render() {
  renderNav();
  const view = $("#view");
  if (state.view === "corpus") renderCorpus(view);
  if (state.view === "resources") renderResources(view);
  if (state.view === "pipeline") renderPipeline(view);
  if (state.view === "search") renderSearch(view);
  if (state.view === "timeline") renderTimeline(view);
  if (state.view === "charts") renderCharts(view);
  if (state.view === "exports") renderExports(view);
  if (state.view === "settings") renderSettings(view);
}

function renderCorpus(view) {
  view.innerHTML = `
    <div class="grid">
      <div class="card">
        <h3>上傳 txt</h3>
        <p class="muted">支援 UTF-8、GB18030、Big5 等常見中文文本編碼；系統會切分卷次與段落。</p>
        <input id="fileInput" type="file" accept=".txt" />
        <div class="toolbar">
          <label><input id="clearUpload" type="checkbox" /> 清空既有語料</label>
          <button id="uploadBtn">上傳並導入</button>
        </div>
      </div>
      <div class="card">
        <h3>貼上文本</h3>
        <textarea id="pasteText" placeholder="貼上一段或多段史料文本..."></textarea>
        <div class="toolbar">
          <button id="pasteBtn">導入文本</button>
          <button id="clearCorpus" class="secondary">清空語料</button>
        </div>
      </div>
    </div>
    <div class="card">
      <h3>語料預覽</h3>
      <div id="docPreview" class="results"></div>
    </div>`;
  $("#uploadBtn").addEventListener("click", guarded(uploadCorpus));
  $("#pasteBtn").addEventListener("click", guarded(importText));
  $("#clearCorpus").addEventListener("click", guarded(clearCorpus));
  guarded(loadDocuments)();
}

async function uploadCorpus() {
  const file = $("#fileInput").files[0];
  if (!file) return toast("請先選擇 txt 檔案。");
  const form = new FormData();
  form.append("file", file);
  const clear = $("#clearUpload").checked;
  const result = await api(`/api/corpus/upload?clear_existing=${clear}`, { method: "POST", body: form });
  toast(`已導入 ${result.documents} 個段落。`);
  await loadStats();
  await loadDocuments();
}

async function importText() {
  const text = $("#pasteText").value.trim();
  if (!text) return toast("請先貼上文本。");
  const result = await api("/api/corpus/import-text", {
    method: "POST",
    body: JSON.stringify({ source_name: "manual.txt", text, clear_existing: false }),
  });
  toast(`已導入 ${result.documents} 個段落。`);
  await loadStats();
  await loadDocuments();
}

async function clearCorpus() {
  await api("/api/corpus/documents", { method: "DELETE" });
  toast("語料已清空。");
  await loadStats();
  await loadDocuments();
}

async function loadDocuments() {
  const result = await api("/api/corpus/documents?limit=8");
  $("#docPreview").innerHTML = result.items
    .map((doc) => `<article class="result"><strong>${escapeHtml(doc.volume || "未分卷")} #${escapeHtml(doc.seq)}</strong><p>${escapeHtml(doc.raw_text)}</p></article>`)
    .join("") || `<p class="muted">尚未導入語料。</p>`;
}

function renderResources(view) {
  view.innerHTML = `
    <div class="grid">
      <div class="card">
        <h3>新增知識項</h3>
        <select id="termType">
          <option value="location">地名</option>
          <option value="office">官職</option>
          <option value="target_entity">目標實體</option>
          <option value="variant">異體字</option>
          <option value="surname">姓氏</option>
          <option value="event_keyword">事件關鍵詞</option>
        </select>
        <input id="termText" placeholder="詞條文本" />
        <input id="termCanonical" placeholder="標準 ID（可選）" />
        <input id="termAliases" placeholder="別名，以逗號分隔" />
        <input id="termEventType" placeholder="事件類型或異體字標準形，如 military" />
        <button id="addTerm">新增</button>
      </div>
      <div class="card">
        <h3>資源列表</h3>
        <div class="toolbar">
          <select id="resourceFilter"><option value="">全部</option></select>
          <button id="reloadTerms" class="secondary">重新載入</button>
        </div>
        <div id="terms" class="results"></div>
      </div>
    </div>`;
  $("#addTerm").addEventListener("click", guarded(addTerm));
  $("#reloadTerms").addEventListener("click", guarded(loadTerms));
  $("#resourceFilter").addEventListener("change", guarded(loadTerms));
  guarded(loadTermTypes)();
  guarded(loadTerms)();
}

async function loadTermTypes() {
  const result = await api("/api/resources/types");
  $("#resourceFilter").innerHTML = `<option value="">全部</option>` + result.items.map((item) => `<option value="${escapeHtml(item.type)}">${escapeHtml(item.type)} (${escapeHtml(item.count)})</option>`).join("");
}

async function loadTerms() {
  const filter = $("#resourceFilter")?.value || "";
  const result = await api(`/api/resources/terms?limit=200${filter ? `&type=${encodeURIComponent(filter)}` : ""}`);
  $("#terms").innerHTML = result.items
    .map((term) => `<article class="result"><strong>${escapeHtml(term.text)}</strong> <span class="muted">${escapeHtml(term.type)}</span><p>${escapeHtml(term.canonical_id || "")} ${escapeHtml(term.aliases_json || "")}</p></article>`)
    .join("") || `<p class="muted">尚無資源。</p>`;
}

async function addTerm() {
  const metadata = {};
  const note = $("#termEventType").value.trim();
  if ($("#termType").value === "event_keyword" && note) metadata.event_type = note;
  if ($("#termType").value === "variant" && note) metadata.canonical = note;
  await api("/api/resources/terms", {
    method: "POST",
    body: JSON.stringify({
      type: $("#termType").value,
      text: $("#termText").value.trim(),
      canonical_id: $("#termCanonical").value.trim() || null,
      aliases: $("#termAliases").value.split(",").map((item) => item.trim()).filter(Boolean),
      metadata,
    }),
  });
  toast("已新增知識項。");
  await loadTermTypes();
  await loadTerms();
}

function renderPipeline(view) {
  const steps = [
    ["time", "時間抽取", "抽取年號、干支、月日並推定 CE 年份。"],
    ["ner", "實體識別", "使用知識資源與規則抽取人名、地名、官職、目標實體。"],
    ["link", "實體連結", "把實體連到標準詞條、別名與 canonical ID。"],
    ["embed", "段落向量", "建立段落向量，支援聚類與相似段落分析。"],
    ["cluster", "段落聚類", "用 K-means fallback 找出文本模板。"],
    ["classify", "事件分類", "依事件關鍵詞與權重產生事件類型。"],
  ];
  view.innerHTML = `
    <div class="toolbar">
      <button id="runAll">執行全流程</button>
      <button id="loadRuns" class="secondary">刷新執行記錄</button>
    </div>
    <div class="pipeline">${steps.map(([id, title, desc]) => `<div class="card step"><h3>${title}</h3><p class="muted">${desc}</p><button data-step="${id}">執行</button></div>`).join("")}</div>
    <div class="card"><h3>執行記錄</h3><div id="runs" class="results"></div></div>`;
  document.querySelectorAll("[data-step]").forEach((button) => button.addEventListener("click", guarded(() => runStep(button.dataset.step))));
  $("#runAll").addEventListener("click", guarded(runAll));
  $("#loadRuns").addEventListener("click", guarded(loadRuns));
  guarded(loadRuns)();
}

async function runStep(step) {
  const result = await api(`/api/pipeline/${step}`, { method: "POST", body: "{}" });
  toast(`${step} 完成：${JSON.stringify(result.result)}`);
  await loadStats();
  await loadRuns();
}

async function runAll() {
  const result = await api("/api/pipeline/all", { method: "POST", body: "{}" });
  toast(`全流程完成：${result.steps.length} 個步驟。`);
  await loadStats();
  await loadRuns();
}

async function loadRuns() {
  const result = await api("/api/runs");
  $("#runs").innerHTML = result.items
    .map((run) => `<article class="result"><strong>${escapeHtml(run.step)}</strong> ${escapeHtml(run.status)}<p>${escapeHtml(run.message)}</p></article>`)
    .join("") || `<p class="muted">尚無執行記錄。</p>`;
}

function renderSearch(view) {
  view.innerHTML = `
    <div class="toolbar">
      <select id="searchKind"><option value="paragraphs">段落</option><option value="entities">實體</option><option value="events">事件</option></select>
      <input id="searchQuery" placeholder="輸入關鍵詞、實體或事件類型" />
      <button id="searchBtn">檢索</button>
    </div>
    <div id="searchResults" class="results"></div>`;
  $("#searchBtn").addEventListener("click", guarded(doSearch));
}

async function doSearch() {
  const kind = $("#searchKind").value;
  const q = $("#searchQuery").value.trim();
  let url = `/api/search/${kind}`;
  if (kind === "entities" && q) url += `?q=${encodeURIComponent(q)}`;
  if (kind === "events" && q) url += `?event_type=${encodeURIComponent(q)}`;
  if (kind === "paragraphs" && q) url += `?q=${encodeURIComponent(q)}`;
  const result = await api(url);
  $("#searchResults").innerHTML = result.items.map(renderSearchItem).join("") || `<p class="muted">沒有找到結果。</p>`;
}

function renderSearchItem(item) {
  const text = item.raw_text || item.text || "";
  return `<article class="result"><strong>${escapeHtml(item.event_type || item.entity_type || item.volume || "段落")}</strong><p>${escapeHtml(text)}</p><p class="muted">CE ${escapeHtml(item.ce_year || "未定")} · ${escapeHtml(item.canonical_text || item.event_types || item.entities || "")}</p></article>`;
}

function renderTimeline(view) {
  view.innerHTML = `
    <div class="toolbar">
      <input id="timelineId" placeholder="時間軸 ID，如 T0001" value="${escapeHtml(state.timelineFilters.timelineId || "")}" />
      <input id="timelineEntity" placeholder="按實體過濾" value="${escapeHtml(state.timelineFilters.entity || "")}" />
      <input id="timelineEvent" placeholder="按事件類型過濾" value="${escapeHtml(state.timelineFilters.eventType || "")}" />
      <button id="timelineBtn">載入時間軸</button>
      <button id="timelineReset" class="secondary">清除過濾</button>
    </div>
    <p class="muted">每個節點都有固定 ID。可在節點內選擇「事件」或「實體」後按「AI 分析」。</p>
    <div id="timelineItems" class="timeline"></div>`;
  $("#timelineBtn").addEventListener("click", guarded(loadTimeline));
  $("#timelineReset").addEventListener("click", () => {
    state.timelineFilters = {};
    state.timelineFocusId = "";
    renderTimeline($("#view"));
  });
  guarded(loadTimeline)();
}

async function loadTimeline() {
  const timelineId = $("#timelineId")?.value.trim() || "";
  const entity = $("#timelineEntity")?.value.trim() || "";
  const eventType = $("#timelineEvent")?.value.trim() || "";
  state.timelineFilters = { timelineId, entity, eventType };
  const params = new URLSearchParams();
  if (timelineId) params.set("timeline_id", timelineId);
  if (entity) params.set("entity", entity);
  if (eventType) params.set("event_type", eventType);
  const result = await api(`/api/analytics/timeline?${params.toString()}`);
  $("#timelineItems").innerHTML = result.items.map(renderTimelineItem).join("") || `<p class="muted">尚無事件，請先執行處理流程。</p>`;
  bindTimelineActions();
  focusTimelineNode();
}

function renderTimelineItem(item) {
  const timelineId = item.timeline_id || `D${item.document_id}`;
  const entities = parseEntityRefs(item.entity_refs);
  const targetOptions = [
    `<option value="event" data-kind="event" data-value="${escapeHtml(item.event_type)}">事件：${escapeHtml(item.event_type)}</option>`,
    ...entities.map((entity) => `<option value="entity:${escapeHtml(entity.id)}" data-kind="entity" data-value="${escapeHtml(entity.text)}" data-entity-id="${escapeHtml(entity.id)}">實體：${escapeHtml(entity.text)} (${escapeHtml(entity.entity_type)})</option>`),
  ];
  const analysisKey = `${timelineId}:event:${item.event_type}`;
  const cached = state.aiResults[analysisKey];
  return `
    <article class="timeline-item ${state.timelineFocusId === timelineId ? "focused" : ""}" id="timeline-${escapeHtml(timelineId)}">
      <div class="timeline-head">
        <span class="node-id">${escapeHtml(timelineId)}</span>
        <strong>${escapeHtml(item.ce_year || "未定年")} · ${escapeHtml(item.event_type)}</strong>
      </div>
      <p>${escapeHtml(item.raw_text)}</p>
      <p class="muted">${escapeHtml(item.historical_dates || "無日期詞")} · P=${escapeHtml(item.probability)}</p>
      ${entities.length ? `<div class="chip-row">${entities.map((entity) => `<span class="entity-chip">${escapeHtml(entity.text)} · ${escapeHtml(entity.entity_type)}</span>`).join("")}</div>` : ""}
      <div class="ai-toolbar">
        <select class="ai-target" data-timeline-id="${escapeHtml(timelineId)}">${targetOptions.join("")}</select>
        <button data-analyze="${escapeHtml(timelineId)}">AI 分析</button>
      </div>
      <div class="ai-result" id="analysis-${escapeHtml(timelineId)}">${cached ? nl2br(cached) : "尚未分析。"}</div>
    </article>`;
}

function parseEntityRefs(refs) {
  return splitCsv(refs).map((ref) => {
    const parts = ref.split(":");
    const id = parts.shift() || "";
    const entityType = parts.pop() || "";
    return { id, text: parts.join(":"), entity_type: entityType };
  }).filter((entity) => entity.id && entity.text);
}

function bindTimelineActions() {
  document.querySelectorAll("[data-analyze]").forEach((button) => {
    button.addEventListener("click", guarded(() => analyzeTimelineNode(button)));
  });
}

async function analyzeTimelineNode(button) {
  const timelineId = button.dataset.analyze;
  const select = document.querySelector(`.ai-target[data-timeline-id="${timelineId}"]`);
  const option = select?.selectedOptions[0];
  if (!option) return toast("請先選擇分析對象。");
  const resultNode = document.getElementById(`analysis-${timelineId}`);
  const targetKind = option.dataset.kind || "event";
  const targetValue = option.dataset.value || "";
  const entityId = option.dataset.entityId ? Number(option.dataset.entityId) : null;
  const cacheKey = `${timelineId}:${targetKind}:${entityId || targetValue}`;
  button.disabled = true;
  button.textContent = "分析中...";
  if (resultNode) resultNode.textContent = "正在呼叫大模型分析，請稍候...";
  try {
    const result = await api("/api/llm/analyze", {
      method: "POST",
      body: JSON.stringify({ timeline_id: timelineId, target_kind: targetKind, target_value: targetValue, entity_id: entityId }),
    });
    state.aiResults[cacheKey] = result.summary || "模型沒有返回文字。";
    if (resultNode) resultNode.innerHTML = nl2br(state.aiResults[cacheKey]);
  } finally {
    button.disabled = false;
    button.textContent = "AI 分析";
  }
}

function focusTimelineNode() {
  const focusId = state.timelineFocusId || state.timelineFilters.timelineId;
  if (!focusId) return;
  const node = document.getElementById(`timeline-${focusId}`);
  if (node) {
    node.scrollIntoView({ behavior: "smooth", block: "center" });
    node.classList.add("focused");
  }
}

function renderCharts(view) {
  view.innerHTML = `
    <p class="muted">統計圖下方的 ID 是對應時間軸節點。點擊 ID 可跳到該節點，方便核對 appointment、military 等分類來自哪段史料。</p>
    <div class="grid">
      <div class="card"><h3>事件類型</h3><div id="chartEvents" class="bars"></div></div>
      <div class="card"><h3>實體類型</h3><div id="chartEntities" class="bars"></div></div>
      <div class="card"><h3>年份分布</h3><div id="chartYears" class="bars"></div></div>
      <div class="card"><h3>卷分布</h3><div id="chartVolumes" class="bars"></div></div>
    </div>`;
  guarded(loadCharts)();
}

async function loadCharts() {
  const result = await api("/api/analytics/charts");
  renderBars("#chartEvents", result.by_event, "event_type");
  renderBars("#chartEntities", result.by_entity_type, "entity_type", (item) => item.entity_names ? `實體：${item.entity_names}` : "");
  renderBars("#chartYears", result.by_year, "ce_year");
  renderBars("#chartVolumes", result.by_volume.slice(0, 16), "volume");
}

function renderBars(selector, items, key, extraText = () => "") {
  const max = Math.max(1, ...items.map((item) => item.count));
  $(selector).innerHTML = items.map((item) => {
    const ids = splitCsv(item.timeline_ids);
    const label = item[key] || "未分類";
    const extra = extraText(item);
    return `
      <div class="bar">
        <span>${escapeHtml(label)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${(item.count / max) * 100}%"></div></div>
        <strong>${escapeHtml(item.count)}</strong>
        <div class="bar-meta">
          ${ids.length ? `涉及節點：${ids.map((id) => `<button class="id-chip" data-timeline-id="${escapeHtml(id)}">${escapeHtml(id)}</button>`).join("")}` : "尚無對應時間軸節點"}
          ${extra ? `<small>${escapeHtml(extra)}</small>` : ""}
        </div>
      </div>`;
  }).join("") || `<p class="muted">沒有資料。</p>`;
  document.querySelectorAll(`${selector} .id-chip`).forEach((button) => {
    button.addEventListener("click", () => openTimelineId(button.dataset.timelineId));
  });
}

function openTimelineId(timelineId) {
  state.view = "timeline";
  state.timelineFocusId = timelineId;
  state.timelineFilters = { timelineId };
  render();
}

function renderSettings(view) {
  view.innerHTML = `
    <div class="grid">
      <div class="card">
        <h3>大模型 API 設定</h3>
        <p class="muted">支援 OpenAI-compatible Chat Completions API。Base link 可填如 https://api.openai.com/v1、https://www.juaiapi.com/v1；若只填 root 網址，系統會自動嘗試 /v1/chat/completions。</p>
        <label>API base link</label>
        <input id="llmBaseUrl" placeholder="https://api.openai.com/v1" />
        <label>Model</label>
        <input id="llmModel" placeholder="gpt-4o-mini" />
        <label>API Key</label>
        <input id="llmApiKey" type="password" placeholder="留空表示保留已保存的 key" />
        <label class="inline"><input id="llmClearKey" type="checkbox" /> 清除已保存的 API Key</label>
        <div id="llmKeyState" class="muted"></div>
        <div class="toolbar">
          <button id="saveLlmSettings">保存設定</button>
          <button id="testLlmSettings" class="secondary">測試連接</button>
        </div>
        <div id="llmTestResult" class="result subtle">尚未測試。</div>
      </div>
      <div class="card">
        <h3>AI 分析 Prompt</h3>
        <p class="muted">可使用變數：{timeline_id}、{target_kind}、{target_value}、{event_type}、{ce_year}、{entities}、{text}</p>
        <textarea id="llmPrompt" class="prompt-box"></textarea>
      </div>
    </div>`;
  $("#saveLlmSettings").addEventListener("click", guarded(saveLlmSettings));
  $("#testLlmSettings").addEventListener("click", guarded(testLlmSettings));
  guarded(loadLlmSettings)();
}

async function loadLlmSettings() {
  const settings = await api("/api/llm/settings");
  $("#llmBaseUrl").value = settings.base_url || "";
  $("#llmModel").value = settings.model || "";
  $("#llmPrompt").value = settings.prompt_template || "";
  $("#llmKeyState").textContent = settings.has_api_key ? `已保存 API Key（${settings.api_key_preview}）` : "尚未保存 API Key。";
}

function collectLlmSettings() {
  return {
    base_url: $("#llmBaseUrl").value.trim(),
    model: $("#llmModel").value.trim(),
    api_key: $("#llmApiKey").value.trim() || null,
    clear_api_key: $("#llmClearKey").checked,
    prompt_template: $("#llmPrompt").value.trim(),
  };
}

async function saveLlmSettings() {
  const settings = await api("/api/llm/settings", {
    method: "PUT",
    body: JSON.stringify(collectLlmSettings()),
  });
  $("#llmApiKey").value = "";
  $("#llmClearKey").checked = false;
  $("#llmKeyState").textContent = settings.has_api_key ? `已保存 API Key（${settings.api_key_preview}）` : "尚未保存 API Key。";
  toast("大模型設定已保存。");
}

async function testLlmSettings() {
  const resultNode = $("#llmTestResult");
  resultNode.textContent = "正在測試連接...";
  const settings = collectLlmSettings();
  const result = await api("/api/llm/test", {
    method: "POST",
    body: JSON.stringify({
      base_url: settings.base_url,
      model: settings.model,
      api_key: settings.api_key,
    }),
  });
  resultNode.textContent = `連接成功：${result.model} 透過 ${result.endpoint || "chat/completions"} 回覆「${result.message}」`;
}

function renderExports(view) {
  view.innerHTML = `
    <div class="grid">
      <div class="card"><h3>JSONL</h3><p class="muted">導出段落、時間、實體、連結與事件資料，方便下游分析。</p><a href="/api/exports/jsonl"><button>下載 JSONL</button></a></div>
      <div class="card"><h3>CSV</h3><p class="muted">導出表格格式，方便在 Excel 或統計工具中使用。</p><a href="/api/exports/csv"><button>下載 CSV</button></a></div>
    </div>`;
}

$("#refreshStats").addEventListener("click", guarded(loadStats));
render();
guarded(loadStats)();
