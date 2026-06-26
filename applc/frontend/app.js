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
  modelStatus: [],
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
  attachResourceImportPanel(view);
  guarded(loadTermTypes)();
  guarded(loadTerms)();
}

function attachResourceImportPanel(view) {
  view.querySelector(".grid")?.insertAdjacentHTML("beforeend", `
    <div class="card">
      <h3>Bulk Dictionary Import</h3>
      <p class="muted">Upload CSV or JSON terms from CBDB, CHGIS, or curated research dictionaries. Required columns: type, text. Optional: canonical_id, aliases, event_type, metadata.</p>
      <input id="resourceImportFile" type="file" accept=".csv,.json,.txt" />
      <label class="inline"><input id="skipImportDuplicates" type="checkbox" checked /> Skip duplicate terms</label>
      <div class="toolbar">
        <button id="importTerms">Import terms</button>
      </div>
      <div id="importTermsResult" class="result subtle">No import run yet.</div>
    </div>`);
  $("#importTerms")?.addEventListener("click", guarded(importTerms));
}

async function importTerms() {
  const file = $("#resourceImportFile").files[0];
  if (!file) return toast("Choose a CSV or JSON file first.");
  const form = new FormData();
  form.append("file", file);
  const skip = $("#skipImportDuplicates").checked;
  const result = await api(`/api/resources/import?skip_duplicates=${skip}`, { method: "POST", body: form });
  $("#importTermsResult").textContent = `Imported ${result.imported}, skipped ${result.skipped}${result.errors?.length ? `, errors: ${result.errors.join("; ")}` : ""}`;
  await loadTermTypes();
  await loadTerms();
  await loadStats();
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
  attachModelPanel(view);
  guarded(loadRuns)();
  guarded(loadModelStatus)();
}

function attachModelPanel(view) {
  view.insertAdjacentHTML("beforeend", `
    <div class="card">
      <h3>Research Models & Data</h3>
      <p class="muted">Models and datasets stay under data/models or data/imports. The pipeline keeps safe offline fallbacks when artifacts are missing.</p>
      <div class="toolbar">
        <button id="refreshModels" class="secondary">Refresh status</button>
      </div>
      <div id="modelStatus" class="results"></div>
    </div>`);
  $("#refreshModels")?.addEventListener("click", guarded(loadModelStatus));
}

async function loadModelStatus() {
  const result = await api("/api/models/status");
  state.modelStatus = result.items || [];
  const node = $("#modelStatus");
  if (!node) return;
  node.innerHTML = state.modelStatus.map(renderModelStatusItem).join("") || `<p class="muted">No artifacts configured.</p>`;
  document.querySelectorAll("[data-fetch-artifact]").forEach((button) => {
    button.addEventListener("click", guarded(() => fetchArtifact(button.dataset.fetchArtifact)));
  });
}

function renderModelStatusItem(item) {
  return `<article class="result">
    <strong>${escapeHtml(item.artifact_id)}</strong> <span class="muted">${escapeHtml(item.kind)} / ${escapeHtml(item.status)}</span>
    <p>${escapeHtml(item.license_note || "")}</p>
    <p class="muted">${escapeHtml(item.local_path || "")}</p>
    <div class="toolbar">
      <button data-fetch-artifact="${escapeHtml(item.artifact_id)}">Fetch / prepare</button>
      <a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer"><button class="secondary">Source</button></a>
    </div>
  </article>`;
}

async function fetchArtifact(artifactId) {
  const result = await api("/api/models/fetch", {
    method: "POST",
    body: JSON.stringify({ artifact_id: artifactId, force: false }),
  });
  toast(`${artifactId}: ${result.status}`);
  await loadModelStatus();
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

attachResourceImportPanel = function attachResourceImportAndCbdbPanelFinal(view) {
  view.querySelector(".grid")?.insertAdjacentHTML("beforeend", `
    <div class="card">
      <h3>Bulk Dictionary Import</h3>
      <p class="muted">Upload CSV or JSON terms. Required columns: type, text. Optional: canonical_id, aliases, event_type, metadata.</p>
      <input id="resourceImportFile" type="file" accept=".csv,.json,.txt" />
      <label class="inline"><input id="skipImportDuplicates" type="checkbox" checked /> Skip duplicate terms</label>
      <div class="toolbar"><button id="importTerms">Import terms</button></div>
      <div id="importTermsResult" class="result subtle">No import run yet.</div>
    </div>
    <div class="card">
      <h3>CBDB 人名更新</h3>
      <p class="muted">輸入人名或使用目前已抽取的人名，從 CBDB API 更新 person_name 知識資源。</p>
      <textarea id="cbdbNames" placeholder="每行一個人名，例如：夏原吉"></textarea>
      <label class="inline"><input id="cbdbUseExtracted" type="checkbox" checked /> 包含目前已抽取的人名</label>
      <label class="inline"><input id="cbdbUseTerms" type="checkbox" /> 包含既有 person_name 知識詞</label>
      <div class="toolbar"><button id="updateCbdb">更新 CBDB 人名</button></div>
      <div id="cbdbResult" class="result subtle">尚未更新。</div>
    </div>`);
  $("#importTerms")?.addEventListener("click", guarded(importTerms));
  $("#updateCbdb")?.addEventListener("click", guarded(updateCbdbPeople));
};

renderTimelineItem = function renderTimelineItemWithAiChatFinal(item) {
  const timelineId = item.timeline_id || `D${item.document_id}`;
  const entities = item.entities?.length ? item.entities : parseEntityRefs(item.entity_refs).map((entity) => ({
    ...entity,
    entity_type_label: entityLabel(entity.entity_type),
    color: entityColor(entity.entity_type),
    display_text: entity.entity_type === "PER" ? `人名|"${entity.text}"` : entity.text,
  }));
  const annotations = item.annotations || [];
  const savedAnalyses = item.ai_analysis_results || [];
  const chatMessages = item.ai_chat_messages || [];
  const targetOptions = [
    `<option value="event" data-kind="event" data-value="${escapeHtml(item.event_type)}">事件：${escapeHtml(item.event_type_label || eventLabel(item.event_type))}</option>`,
    ...entities.map((entity) => `<option value="entity:${escapeHtml(entity.id)}" data-kind="entity" data-value="${escapeHtml(entity.text)}" data-entity-id="${escapeHtml(entity.id)}">實體：${escapeHtml(displayEntityText(entity))}</option>`),
  ];
  const analysisKey = `${timelineId}:event:${item.event_type}`;
  const cached = state.aiResults[analysisKey];
  return `
    <article class="timeline-item ${state.timelineFocusId === timelineId ? "focused" : ""}" id="timeline-${escapeHtml(timelineId)}">
      <div class="timeline-head">
        <span class="node-id">${escapeHtml(timelineId)}</span>
        <strong>${escapeHtml(item.ce_year || "未知年份")} ｜ ${escapeHtml(item.event_type_label || eventLabel(item.event_type))}</strong>
        <span class="entity-chip">${escapeHtml(item.event_type)}</span>
      </div>
      <p>${highlightText(item.raw_text || "", state.timelineFilters.q || "")}</p>
      <p class="muted">日期：${escapeHtml(item.historical_dates || "未抽取")} ｜ 機率：${escapeHtml(item.probability)} ｜ 引文：${escapeHtml(item.citation || "")}</p>
      ${entities.length ? `<div class="chip-row">${entities.map(renderTimelineEntityChip).join("")}</div>` : ""}
      <div class="ai-toolbar">
        <select class="ai-target" data-timeline-id="${escapeHtml(timelineId)}">${targetOptions.join("")}</select>
        <button data-analyze="${escapeHtml(timelineId)}">AI 分析</button>
        <button class="secondary" data-export-md="${escapeHtml(timelineId)}">保存為 Markdown</button>
      </div>
      <div class="research-panel">
        ${annotations.length ? `<div class="chip-row">${annotations.map(renderAnnotationChip).join("")}</div>` : ""}
        <div class="correction-grid">
          <div>
            <label>修正事件類型</label>
            <input class="event-correction" data-document-id="${escapeHtml(item.document_id)}" value="${escapeHtml(item.event_type_label || eventLabel(item.event_type))}" />
          </div>
          <button data-add-event="${escapeHtml(item.document_id)}">儲存事件修正</button>
          <div>
            <label>補充漏掉的實體</label>
            <input class="entity-correction" data-document-id="${escapeHtml(item.document_id)}" placeholder="文字|類別，例如 夏原吉|人名 或 南京|LOC" />
          </div>
          <button data-add-entity="${escapeHtml(item.document_id)}">儲存實體</button>
        </div>
        ${savedAnalyses.length ? `<div class="saved-ai">${savedAnalyses.map(renderSavedAnalysis).join("")}</div>` : ""}
        <div class="ai-chat-panel">
          <label>追問 AI</label>
          <textarea class="ai-chat-input" data-timeline-id="${escapeHtml(timelineId)}" placeholder="針對此節點繼續提問..."></textarea>
          <div class="toolbar"><button data-ai-chat="${escapeHtml(timelineId)}">送出追問</button></div>
          <div class="ai-chat-history" id="chat-${escapeHtml(timelineId)}">${renderChatMessages(chatMessages)}</div>
        </div>
      </div>
      <div class="ai-result" id="analysis-${escapeHtml(timelineId)}">${cached ? nl2br(cached) : "尚未產生本節點的 AI 分析。"}</div>
    </article>`;
};

bindTimelineActions = function bindTimelineActionsWithAiChatFinal() {
  document.querySelectorAll("[data-analyze]").forEach((button) => {
    button.addEventListener("click", guarded(() => analyzeTimelineNode(button)));
  });
  document.querySelectorAll("[data-add-event]").forEach((button) => {
    button.addEventListener("click", guarded(() => saveEventCorrection(button.dataset.addEvent)));
  });
  document.querySelectorAll("[data-add-entity]").forEach((button) => {
    button.addEventListener("click", guarded(() => saveEntityCorrection(button.dataset.addEntity)));
  });
  document.querySelectorAll("[data-ai-chat]").forEach((button) => {
    button.addEventListener("click", guarded(() => sendAiChat(button.dataset.aiChat)));
  });
  document.querySelectorAll("[data-export-md]").forEach((button) => {
    button.addEventListener("click", guarded(() => exportAiMarkdown(button.dataset.exportMd)));
  });
};

render();
guarded(loadStats)();

const baseAttachResourceImportPanelForCbdb = attachResourceImportPanel;
attachResourceImportPanel = function attachResourceImportAndCbdbPanel(view) {
  baseAttachResourceImportPanelForCbdb(view);
  view.querySelector(".grid")?.insertAdjacentHTML("beforeend", `
    <div class="card">
      <h3>CBDB 人名更新</h3>
      <p class="muted">輸入人名或使用目前已抽取的人名，從 CBDB API 更新 person_name 知識資源。</p>
      <textarea id="cbdbNames" placeholder="每行一個人名，例如：夏原吉"></textarea>
      <label class="inline"><input id="cbdbUseExtracted" type="checkbox" checked /> 包含目前已抽取的人名</label>
      <label class="inline"><input id="cbdbUseTerms" type="checkbox" /> 包含既有 person_name 知識詞</label>
      <div class="toolbar">
        <button id="updateCbdb">更新 CBDB 人名</button>
      </div>
      <div id="cbdbResult" class="result subtle">尚未更新。</div>
    </div>`);
  $("#updateCbdb")?.addEventListener("click", guarded(updateCbdbPeople));
};

async function updateCbdbPeople() {
  const names = ($("#cbdbNames")?.value || "")
    .split(/\r?\n|,/)
    .map((item) => item.trim())
    .filter(Boolean);
  const result = await api("/api/resources/cbdb/update", {
    method: "POST",
    body: JSON.stringify({
      names,
      include_extracted: $("#cbdbUseExtracted")?.checked || false,
      include_terms: $("#cbdbUseTerms")?.checked || false,
    }),
  });
  $("#cbdbResult").textContent = `完成：請求 ${result.requested}，新增 ${result.imported}，略過 ${result.skipped}，無結果 ${result.no_results?.length || 0}，錯誤 ${result.errors?.length || 0}`;
  await loadTermTypes();
  await loadTerms();
}

function displayEntityText(entity) {
  return entity.display_text || (entity.entity_type === "PER" ? `人名|"${entity.text}"` : entity.text);
}

renderTimelineEntityChip = function renderTimelineEntityChipPersonAware(entity) {
  const color = entity.color || entityColor(entity.entity_type);
  const label = entity.entity_type_label || entityLabel(entity.entity_type);
  return `<span class="entity-chip colored-entity" style="--entity-color:${escapeHtml(color)}">${escapeHtml(displayEntityText(entity))}｜${escapeHtml(label)}</span>`;
};

renderTimelineItem = function renderTimelineItemWithAiChat(item) {
  const timelineId = item.timeline_id || `D${item.document_id}`;
  const entities = item.entities?.length ? item.entities : parseEntityRefs(item.entity_refs).map((entity) => ({
    ...entity,
    entity_type_label: entityLabel(entity.entity_type),
    color: entityColor(entity.entity_type),
    display_text: entity.entity_type === "PER" ? `人名|"${entity.text}"` : entity.text,
  }));
  const annotations = item.annotations || [];
  const savedAnalyses = item.ai_analysis_results || [];
  const targetOptions = [
    `<option value="event" data-kind="event" data-value="${escapeHtml(item.event_type)}">事件：${escapeHtml(item.event_type_label || eventLabel(item.event_type))}</option>`,
    ...entities.map((entity) => `<option value="entity:${escapeHtml(entity.id)}" data-kind="entity" data-value="${escapeHtml(entity.text)}" data-entity-id="${escapeHtml(entity.id)}">實體：${escapeHtml(displayEntityText(entity))}</option>`),
  ];
  const analysisKey = `${timelineId}:event:${item.event_type}`;
  const cached = state.aiResults[analysisKey];
  return `
    <article class="timeline-item ${state.timelineFocusId === timelineId ? "focused" : ""}" id="timeline-${escapeHtml(timelineId)}">
      <div class="timeline-head">
        <span class="node-id">${escapeHtml(timelineId)}</span>
        <strong>${escapeHtml(item.ce_year || "未知年份")} ｜ ${escapeHtml(item.event_type_label || eventLabel(item.event_type))}</strong>
        <span class="entity-chip">${escapeHtml(item.event_type)}</span>
      </div>
      <p>${highlightText(item.raw_text || "", state.timelineFilters.q || "")}</p>
      <p class="muted">日期：${escapeHtml(item.historical_dates || "未抽取")} ｜ 機率：${escapeHtml(item.probability)} ｜ 引文：${escapeHtml(item.citation || "")}</p>
      ${entities.length ? `<div class="chip-row">${entities.map(renderTimelineEntityChip).join("")}</div>` : ""}
      <div class="ai-toolbar">
        <select class="ai-target" data-timeline-id="${escapeHtml(timelineId)}">${targetOptions.join("")}</select>
        <button data-analyze="${escapeHtml(timelineId)}">AI 分析</button>
        <button class="secondary" data-export-md="${escapeHtml(timelineId)}">匯出 Markdown</button>
      </div>
      <div class="research-panel">
        ${annotations.length ? `<div class="chip-row">${annotations.map(renderAnnotationChip).join("")}</div>` : ""}
        <div class="correction-grid">
          <div>
            <label>修正事件類型</label>
            <input class="event-correction" data-document-id="${escapeHtml(item.document_id)}" value="${escapeHtml(item.event_type_label || eventLabel(item.event_type))}" />
          </div>
          <button data-add-event="${escapeHtml(item.document_id)}">儲存事件修正</button>
          <div>
            <label>補充漏掉的實體</label>
            <input class="entity-correction" data-document-id="${escapeHtml(item.document_id)}" placeholder="文字|類別，例如 夏原吉|人名 或 南京|LOC" />
          </div>
          <button data-add-entity="${escapeHtml(item.document_id)}">儲存實體</button>
        </div>
        ${savedAnalyses.length ? `<div class="saved-ai">${savedAnalyses.map(renderSavedAnalysis).join("")}</div>` : ""}
        <div class="ai-chat-panel">
          <label>追問 AI</label>
          <textarea class="ai-chat-input" data-timeline-id="${escapeHtml(timelineId)}" placeholder="針對此節點繼續提問..."></textarea>
          <div class="toolbar">
            <button data-ai-chat="${escapeHtml(timelineId)}">送出追問</button>
          </div>
          <div class="ai-chat-history" id="chat-${escapeHtml(timelineId)}"></div>
        </div>
      </div>
      <div class="ai-result" id="analysis-${escapeHtml(timelineId)}">${cached ? nl2br(cached) : "尚未產生本節點的 AI 分析。"}</div>
    </article>`;
};

const baseBindTimelineActionsForChat = bindTimelineActions;
bindTimelineActions = function bindTimelineActionsWithAiChat() {
  baseBindTimelineActionsForChat();
  document.querySelectorAll("[data-ai-chat]").forEach((button) => {
    button.addEventListener("click", guarded(() => sendAiChat(button.dataset.aiChat)));
  });
  document.querySelectorAll("[data-export-md]").forEach((button) => {
    button.addEventListener("click", guarded(() => exportAiMarkdown(button.dataset.exportMd)));
  });
};

async function sendAiChat(timelineId) {
  const input = document.querySelector(`.ai-chat-input[data-timeline-id="${timelineId}"]`);
  const message = input?.value.trim();
  if (!message) return toast("請先輸入追問內容。");
  const historyNode = document.getElementById(`chat-${timelineId}`);
  if (historyNode) historyNode.textContent = "AI 回答中...";
  const result = await api("/api/llm/chat", {
    method: "POST",
    body: JSON.stringify({ timeline_id: timelineId, message }),
  });
  if (input) input.value = "";
  if (historyNode) historyNode.innerHTML = renderChatMessages(result.saved_messages || []);
  toast("追問已保存。");
}

function renderChatMessages(messages) {
  return messages.map((item) => {
    const speaker = item.role === "user" ? "使用者" : "AI";
    return `<article class="result subtle"><strong>${escapeHtml(speaker)}</strong><p>${nl2br(item.content || "")}</p><p class="muted">${escapeHtml(item.created_at || "")}</p></article>`;
  }).join("");
}

async function exportAiMarkdown(timelineId) {
  const result = await api("/api/llm/export-markdown", {
    method: "POST",
    body: JSON.stringify({ timeline_id: timelineId }),
  });
  toast(`已匯出 Markdown：${result.filename}`);
}

const baseRenderTimelineItem = renderTimelineItem;
renderTimelineItem = function renderTimelineItemWithResearchTools(item) {
  const timelineId = item.timeline_id || `D${item.document_id}`;
  const annotations = item.annotations || [];
  const savedAnalyses = item.ai_analysis_results || [];
  const extra = `
    <div class="research-panel">
      <p class="muted">Citation: ${escapeHtml(item.citation || "")}${item.calendar_dates ? ` / Exact date: ${escapeHtml(item.calendar_dates)}` : ""}${item.date_precisions ? ` / Precision: ${escapeHtml(item.date_precisions)}` : ""}</p>
      ${annotations.length ? `<div class="chip-row">${annotations.map(renderAnnotationChip).join("")}</div>` : ""}
      <div class="correction-grid">
        <div>
          <label>Correct event type</label>
          <input class="event-correction" data-document-id="${escapeHtml(item.document_id)}" value="${escapeHtml(item.event_type || "")}" />
        </div>
        <button data-add-event="${escapeHtml(item.document_id)}">Save event correction</button>
        <div>
          <label>Add missed entity</label>
          <input class="entity-correction" data-document-id="${escapeHtml(item.document_id)}" placeholder="text|TYPE, e.g. 夏原吉|PER" />
        </div>
        <button data-add-entity="${escapeHtml(item.document_id)}">Save entity</button>
      </div>
      ${savedAnalyses.length ? `<div class="saved-ai">${savedAnalyses.map(renderSavedAnalysis).join("")}</div>` : ""}
    </div>`;
  return baseRenderTimelineItem(item).replace("</article>", `${extra}</article>`);
};

const baseBindTimelineActions = bindTimelineActions;
bindTimelineActions = function bindTimelineActionsWithResearchTools() {
  baseBindTimelineActions();
  document.querySelectorAll("[data-add-event]").forEach((button) => {
    button.addEventListener("click", guarded(() => saveEventCorrection(button.dataset.addEvent)));
  });
  document.querySelectorAll("[data-add-entity]").forEach((button) => {
    button.addEventListener("click", guarded(() => saveEntityCorrection(button.dataset.addEntity)));
  });
};

function renderAnnotationChip(annotation) {
  const label = annotation.annotation_type === "event"
    ? `${annotation.action}: ${annotation.event_type || ""}`
    : `${annotation.action}: ${annotation.text || ""} ${annotation.entity_type || ""}`;
  return `<span class="entity-chip annotation-chip">${escapeHtml(label)}</span>`;
}

function renderSavedAnalysis(item) {
  return `<article class="result subtle"><strong>Saved AI: ${escapeHtml(item.target_kind)} / ${escapeHtml(item.target_value)}</strong><p>${nl2br(item.summary || "")}</p><p class="muted">${escapeHtml(item.model || "")} ${escapeHtml(item.updated_at || "")}</p></article>`;
}

async function saveEventCorrection(documentId) {
  const input = document.querySelector(`.event-correction[data-document-id="${documentId}"]`);
  const eventType = input?.value.trim();
  if (!eventType) return toast("Enter an event type first.");
  await api("/api/annotations", {
    method: "POST",
    body: JSON.stringify({ document_id: Number(documentId), annotation_type: "event", action: "confirm", event_type: eventType }),
  });
  toast("Event correction saved. Re-run classification to apply it.");
  await loadTimeline();
}

async function saveEntityCorrection(documentId) {
  const input = document.querySelector(`.entity-correction[data-document-id="${documentId}"]`);
  const value = input?.value.trim() || "";
  const [text, entityType = "PER"] = value.split("|").map((item) => item.trim());
  if (!text) return toast("Enter entity text first.");
  await api("/api/annotations", {
    method: "POST",
    body: JSON.stringify({
      document_id: Number(documentId),
      annotation_type: "entity",
      action: "add",
      text,
      entity_type: entityType || "PER",
      start: 0,
      end: text.length,
    }),
  });
  toast("Entity correction saved. Re-run NER/linking to apply it.");
  await loadTimeline();
}

const EVENT_LABELS_ZH = {
  military: "軍事",
  appointment: "任官任命",
  tribute: "朝貢外交",
  punishment: "刑罰司法",
  disaster: "災異",
  finance: "財政賦役",
  uncategorized: "未分類",
};

const ENTITY_LABELS_ZH = {
  PER: "人物",
  LOC: "地點",
  OFF: "官位職官",
  TARGET: "研究對象",
};

const ENTITY_COLORS_DEFAULT = {
  PER: "#ad3f28",
  LOC: "#2f7d55",
  OFF: "#246b9f",
  TARGET: "#bc8b38",
};

state.displaySettings = {
  event_labels: EVENT_LABELS_ZH,
  entity_labels: ENTITY_LABELS_ZH,
  entity_colors: ENTITY_COLORS_DEFAULT,
};
state.timelineFacets = { events: [], entities: [] };

function eventLabel(code) {
  return state.displaySettings.event_labels?.[code] || EVENT_LABELS_ZH[code] || code || "未分類";
}

function entityLabel(code) {
  return state.displaySettings.entity_labels?.[code] || ENTITY_LABELS_ZH[code] || code || "未知類別";
}

function entityColor(code) {
  return state.displaySettings.entity_colors?.[code] || ENTITY_COLORS_DEFAULT[code] || "#756653";
}

async function loadDisplaySettings() {
  try {
    const settings = await api("/api/display/settings");
    state.displaySettings = {
      event_labels: { ...EVENT_LABELS_ZH, ...(settings.event_labels || {}) },
      entity_labels: { ...ENTITY_LABELS_ZH, ...(settings.entity_labels || {}) },
      entity_colors: { ...ENTITY_COLORS_DEFAULT, ...(settings.entity_colors || {}) },
    };
  } catch (error) {
    console.warn("Display settings fallback", error);
  }
}

const originalRenderTimeline = renderTimeline;
renderTimeline = function renderTimelineChinese(view) {
  view.innerHTML = `
    <div class="card">
      <h3>時間軸搜尋</h3>
      <p class="muted">可用原文、時間節點 ID、事件類型、中文事件名稱、實體名稱或實體類別搜尋。</p>
      <div class="timeline-search-grid">
        <input id="timelineTextSearch" placeholder="全文搜尋：例如 軍事、官位、地名、T0001 或原文片段" value="${escapeHtml(state.timelineFilters.q || "")}" />
        <input id="timelineId" placeholder="節點 ID：T0001" value="${escapeHtml(state.timelineFilters.timelineId || "")}" />
        <input id="timelineEvent" list="timelineEventList" placeholder="事件類型：軍事 / military" value="${escapeHtml(state.timelineFilters.eventType || "")}" />
        <input id="timelineEntity" list="timelineEntityList" placeholder="實體或類別：南京 / 官位 / OFF" value="${escapeHtml(state.timelineFilters.entity || "")}" />
      </div>
      <datalist id="timelineEventList">${(state.timelineFacets.events || []).map((item) => `<option value="${escapeHtml(item.event_type_label || item.event_type)}">${escapeHtml(item.event_type)} (${escapeHtml(item.count)})</option>`).join("")}</datalist>
      <datalist id="timelineEntityList">${(state.timelineFacets.entities || []).map((item) => `<option value="${escapeHtml(item.text)}">${escapeHtml(item.entity_type_label || item.entity_type)} (${escapeHtml(item.count)})</option>`).join("")}</datalist>
      <div class="toolbar">
        <button id="timelineBtn">搜尋時間軸</button>
        <button id="timelineReset" class="secondary">清除篩選</button>
      </div>
    </div>
    <div id="timelineItems" class="timeline"></div>`;
  $("#timelineBtn").addEventListener("click", guarded(loadTimeline));
  ["timelineTextSearch", "timelineId", "timelineEvent", "timelineEntity"].forEach((id) => {
    $(`#${id}`)?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") guarded(loadTimeline)();
    });
  });
  $("#timelineReset").addEventListener("click", () => {
    state.timelineFilters = {};
    state.timelineFocusId = "";
    renderTimeline($("#view"));
  });
  guarded(loadTimeline)();
};

const originalLoadTimeline = loadTimeline;
loadTimeline = async function loadTimelineChinese() {
  const q = $("#timelineTextSearch")?.value.trim() || "";
  const timelineId = $("#timelineId")?.value.trim() || "";
  const entity = $("#timelineEntity")?.value.trim() || "";
  const eventType = $("#timelineEvent")?.value.trim() || "";
  state.timelineFilters = { q, timelineId, entity, eventType };
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (timelineId) params.set("timeline_id", timelineId);
  if (entity) params.set("entity", entity);
  if (eventType) params.set("event_type", eventType);
  const result = await api(`/api/analytics/timeline?${params.toString()}`);
  state.timelineFacets = result.facets || state.timelineFacets;
  if (result.display) {
    state.displaySettings = {
      event_labels: { ...EVENT_LABELS_ZH, ...(result.display.event_labels || {}) },
      entity_labels: { ...ENTITY_LABELS_ZH, ...(result.display.entity_labels || {}) },
      entity_colors: { ...ENTITY_COLORS_DEFAULT, ...(result.display.entity_colors || {}) },
    };
  }
  const items = result.items || [];
  $("#timelineItems").innerHTML = items.map(renderTimelineItem).join("") || `<p class="muted">沒有找到符合條件的時間節點。</p>`;
  bindTimelineActions();
  focusTimelineNode();
};

const researchRenderTimelineItem = renderTimelineItem;
renderTimelineItem = function renderTimelineItemChinese(item) {
  const timelineId = item.timeline_id || `D${item.document_id}`;
  const entities = item.entities?.length ? item.entities : parseEntityRefs(item.entity_refs).map((entity) => ({
    ...entity,
    entity_type_label: entityLabel(entity.entity_type),
    color: entityColor(entity.entity_type),
  }));
  const annotations = item.annotations || [];
  const savedAnalyses = item.ai_analysis_results || [];
  const targetOptions = [
    `<option value="event" data-kind="event" data-value="${escapeHtml(item.event_type)}">事件：${escapeHtml(item.event_type_label || eventLabel(item.event_type))}</option>`,
    ...entities.map((entity) => `<option value="entity:${escapeHtml(entity.id)}" data-kind="entity" data-value="${escapeHtml(entity.text)}" data-entity-id="${escapeHtml(entity.id)}">實體：${escapeHtml(entity.text)} (${escapeHtml(entity.entity_type_label || entityLabel(entity.entity_type))})</option>`),
  ];
  const analysisKey = `${timelineId}:event:${item.event_type}`;
  const cached = state.aiResults[analysisKey];
  return `
    <article class="timeline-item ${state.timelineFocusId === timelineId ? "focused" : ""}" id="timeline-${escapeHtml(timelineId)}">
      <div class="timeline-head">
        <span class="node-id">${escapeHtml(timelineId)}</span>
        <strong>${escapeHtml(item.ce_year || "未知年份")} ｜ ${escapeHtml(item.event_type_label || eventLabel(item.event_type))}</strong>
        <span class="entity-chip">${escapeHtml(item.event_type)}</span>
      </div>
      <p>${highlightText(item.raw_text || "", state.timelineFilters.q || "")}</p>
      <p class="muted">日期：${escapeHtml(item.historical_dates || "未抽取")} ｜ 機率：${escapeHtml(item.probability)} ｜ 引文：${escapeHtml(item.citation || "")}</p>
      ${entities.length ? `<div class="chip-row">${entities.map(renderTimelineEntityChip).join("")}</div>` : ""}
      <div class="ai-toolbar">
        <select class="ai-target" data-timeline-id="${escapeHtml(timelineId)}">${targetOptions.join("")}</select>
        <button data-analyze="${escapeHtml(timelineId)}">AI 分析</button>
      </div>
      <div class="research-panel">
        ${annotations.length ? `<div class="chip-row">${annotations.map(renderAnnotationChip).join("")}</div>` : ""}
        <div class="correction-grid">
          <div>
            <label>修正事件類型</label>
            <input class="event-correction" data-document-id="${escapeHtml(item.document_id)}" value="${escapeHtml(item.event_type_label || eventLabel(item.event_type))}" />
          </div>
          <button data-add-event="${escapeHtml(item.document_id)}">儲存事件修正</button>
          <div>
            <label>補充漏掉的實體</label>
            <input class="entity-correction" data-document-id="${escapeHtml(item.document_id)}" placeholder="文字|類別，例如 南京|LOC 或 夏原吉|PER" />
          </div>
          <button data-add-entity="${escapeHtml(item.document_id)}">儲存實體</button>
        </div>
        ${savedAnalyses.length ? `<div class="saved-ai">${savedAnalyses.map(renderSavedAnalysis).join("")}</div>` : ""}
      </div>
      <div class="ai-result" id="analysis-${escapeHtml(timelineId)}">${cached ? nl2br(cached) : "尚未產生本節點的 AI 分析。"}</div>
    </article>`;
};

function renderTimelineEntityChip(entity) {
  const color = entity.color || entityColor(entity.entity_type);
  const label = entity.entity_type_label || entityLabel(entity.entity_type);
  return `<span class="entity-chip colored-entity" style="--entity-color:${escapeHtml(color)}">${escapeHtml(textWithLabel(entity.text, label))}</span>`;
}

function textWithLabel(text, label) {
  return `${text}｜${label}`;
}

function highlightText(text, query) {
  const safe = escapeHtml(text);
  if (!query) return safe;
  const escapedQuery = escapeHtml(query);
  return safe.replaceAll(escapedQuery, `<mark>${escapedQuery}</mark>`);
}

const originalLoadCharts = loadCharts;
loadCharts = async function loadChartsChinese() {
  const result = await api("/api/analytics/charts");
  if (result.display) {
    state.displaySettings = {
      event_labels: { ...EVENT_LABELS_ZH, ...(result.display.event_labels || {}) },
      entity_labels: { ...ENTITY_LABELS_ZH, ...(result.display.entity_labels || {}) },
      entity_colors: { ...ENTITY_COLORS_DEFAULT, ...(result.display.entity_colors || {}) },
    };
  }
  renderBars("#chartEvents", result.by_event, "event_type");
  renderBars("#chartEntities", result.by_entity_type, "entity_type", (item) => item.entity_names ? `實體：${item.entity_names}` : "");
  renderBars("#chartYears", result.by_year, "ce_year");
  renderBars("#chartVolumes", result.by_volume.slice(0, 16), "volume");
};

const originalRenderBars = renderBars;
renderBars = function renderBarsWithIdList(selector, items, key, extraText = () => "") {
  const max = Math.max(1, ...items.map((item) => item.count));
  $(selector).innerHTML = items.map((item, index) => {
    const ids = splitCsv(item.timeline_ids);
    const preview = item.timeline_id_preview || ids.slice(0, 8);
    const label = item.label || (key === "event_type" ? eventLabel(item[key]) : key === "entity_type" ? entityLabel(item[key]) : item[key] || "未知");
    const extra = extraText(item);
    const detailId = `${selector.replace("#", "")}-${index}`;
    return `
      <div class="bar">
        <span>${escapeHtml(label)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${(item.count / max) * 100}%"></div></div>
        <strong>${escapeHtml(item.count)}</strong>
        <div class="bar-meta">
          ${ids.length ? `<span>節點 ${escapeHtml(ids.length)} 筆：</span>${preview.map((id) => `<button class="id-chip" data-timeline-id="${escapeHtml(id)}">${escapeHtml(id)}</button>`).join("")}` : "沒有對應時間節點"}
          ${ids.length > preview.length ? `<button class="id-list-toggle secondary" data-id-list="${escapeHtml(detailId)}">展開全部</button>` : ""}
          ${extra ? `<small>${escapeHtml(extra)}</small>` : ""}
          ${ids.length > preview.length ? `<div class="id-list" id="${escapeHtml(detailId)}" hidden>${ids.map((id) => `<button class="id-chip" data-timeline-id="${escapeHtml(id)}">${escapeHtml(id)}</button>`).join("")}</div>` : ""}
        </div>
      </div>`;
  }).join("") || `<p class="muted">沒有統計資料。</p>`;
  document.querySelectorAll(`${selector} .id-chip`).forEach((button) => {
    button.addEventListener("click", () => openTimelineId(button.dataset.timelineId));
  });
  document.querySelectorAll(`${selector} .id-list-toggle`).forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.idList);
      if (!target) return;
      target.hidden = !target.hidden;
      button.textContent = target.hidden ? "展開全部" : "收合清單";
    });
  });
};

const originalOpenTimelineId = openTimelineId;
openTimelineId = function openTimelineIdWithSearch(timelineId) {
  state.view = "timeline";
  state.timelineFocusId = timelineId;
  state.timelineFilters = { timelineId, q: "", entity: "", eventType: "" };
  render();
};

const originalRenderSettings = renderSettings;
renderSettings = function renderSettingsWithDisplay(view) {
  originalRenderSettings(view);
  attachDisplaySettingsPanel(view);
};

function attachDisplaySettingsPanel(view) {
  view.querySelector(".grid")?.insertAdjacentHTML("beforeend", `
    <div class="card">
      <h3>顯示與顏色設定</h3>
      <p class="muted">可調整事件與實體的中文顯示名稱，也可設定時間軸實體標記顏色。</p>
      <label>事件類型中文名稱（JSON）</label>
      <textarea id="eventLabelsJson" class="settings-json"></textarea>
      <label>實體類別中文名稱（JSON）</label>
      <textarea id="entityLabelsJson" class="settings-json"></textarea>
      <label>實體顏色（JSON，HEX 色碼）</label>
      <textarea id="entityColorsJson" class="settings-json"></textarea>
      <div class="toolbar">
        <button id="saveDisplaySettings">儲存顯示設定</button>
        <button id="resetDisplaySettings" class="secondary">填入預設值</button>
      </div>
      <div id="displaySettingsResult" class="result subtle">尚未儲存。</div>
    </div>`);
  fillDisplaySettingsForms();
  $("#saveDisplaySettings")?.addEventListener("click", guarded(saveDisplaySettings));
  $("#resetDisplaySettings")?.addEventListener("click", () => {
    state.displaySettings = {
      event_labels: EVENT_LABELS_ZH,
      entity_labels: ENTITY_LABELS_ZH,
      entity_colors: ENTITY_COLORS_DEFAULT,
    };
    fillDisplaySettingsForms();
  });
}

function fillDisplaySettingsForms() {
  if ($("#eventLabelsJson")) $("#eventLabelsJson").value = JSON.stringify(state.displaySettings.event_labels || EVENT_LABELS_ZH, null, 2);
  if ($("#entityLabelsJson")) $("#entityLabelsJson").value = JSON.stringify(state.displaySettings.entity_labels || ENTITY_LABELS_ZH, null, 2);
  if ($("#entityColorsJson")) $("#entityColorsJson").value = JSON.stringify(state.displaySettings.entity_colors || ENTITY_COLORS_DEFAULT, null, 2);
}

async function saveDisplaySettings() {
  const payload = {
    event_labels: JSON.parse($("#eventLabelsJson").value || "{}"),
    entity_labels: JSON.parse($("#entityLabelsJson").value || "{}"),
    entity_colors: JSON.parse($("#entityColorsJson").value || "{}"),
  };
  const result = await api("/api/display/settings", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  state.displaySettings = result;
  $("#displaySettingsResult").textContent = "顯示設定已儲存。時間軸與統計圖重新載入後會套用。";
}

loadDisplaySettings();

const NAV_LABELS_ZH = {
  corpus: "語料庫",
  resources: "知識資源",
  pipeline: "處理流程",
  search: "搜尋",
  timeline: "時間軸",
  charts: "統計圖",
  exports: "匯出",
  settings: "設定",
};

renderNav = function renderNavChinese() {
  $("#nav").innerHTML = views
    .map(([id], index) => `<button class="nav-item ${state.view === id ? "active" : ""}" data-view="${id}"><span>${NAV_LABELS_ZH[id] || id}</span><small>${index + 1}</small></button>`)
    .join("");
  document.querySelectorAll(".nav-item").forEach((button) => {
    button.addEventListener("click", () => {
      state.view = button.dataset.view;
      render();
    });
  });
};

loadStats = async function loadStatsChinese() {
  const [corpus, charts] = await Promise.all([api("/api/corpus/stats"), api("/api/analytics/charts")]);
  state.stats = { corpus, charts };
  $("#stats").innerHTML = [
    ["段落數", corpus.documents || 0],
    ["卷數", corpus.volumes || 0],
    ["字數", corpus.characters || 0],
    ["事件數", sum(charts.by_event)],
  ]
    .map(([label, value]) => `<div class="stat-card"><strong>${escapeHtml(value)}</strong><span>${label}</span></div>`)
    .join("");
};

attachModelPanel = function attachModelPanelChinese(view) {
  view.insertAdjacentHTML("beforeend", `
    <div class="card">
      <h3>研究模型與外部資料</h3>
      <p class="muted">模型與資料會保存在 data/models 或 data/imports。缺少模型時，系統仍會使用安全的本機 fallback。</p>
      <div class="toolbar">
        <button id="refreshModels" class="secondary">重新整理狀態</button>
      </div>
      <div id="modelStatus" class="results"></div>
    </div>`);
  $("#refreshModels")?.addEventListener("click", guarded(loadModelStatus));
};

renderModelStatusItem = function renderModelStatusItemChinese(item) {
  return `<article class="result">
    <strong>${escapeHtml(item.artifact_id)}</strong> <span class="muted">${escapeHtml(item.kind)} / ${escapeHtml(item.status)}</span>
    <p>${escapeHtml(item.license_note || "")}</p>
    <p class="muted">${escapeHtml(item.local_path || "")}</p>
    <div class="toolbar">
      <button data-fetch-artifact="${escapeHtml(item.artifact_id)}">下載或準備</button>
      <a href="${escapeHtml(item.source_url)}" target="_blank" rel="noreferrer"><button class="secondary">來源</button></a>
    </div>
  </article>`;
};

renderTimelineItem = function renderTimelineItemChineseClean(item) {
  const timelineId = item.timeline_id || `D${item.document_id}`;
  const entities = item.entities?.length ? item.entities : parseEntityRefs(item.entity_refs).map((entity) => ({
    ...entity,
    entity_type_label: entityLabel(entity.entity_type),
    color: entityColor(entity.entity_type),
    display_text: entity.entity_type === "PER" ? `人名|"${entity.text}"` : entity.text,
  }));
  const annotations = item.annotations || [];
  const savedAnalyses = item.ai_analysis_results || [];
  const chatMessages = item.ai_chat_messages || [];
  const targetOptions = [
    `<option value="event" data-kind="event" data-value="${escapeHtml(item.event_type)}">事件：${escapeHtml(item.event_type_label || eventLabel(item.event_type))}</option>`,
    ...entities.map((entity) => `<option value="entity:${escapeHtml(entity.id)}" data-kind="entity" data-value="${escapeHtml(entity.text)}" data-entity-id="${escapeHtml(entity.id)}">實體：${escapeHtml(displayEntityText(entity))}</option>`),
  ];
  const analysisKey = `${timelineId}:event:${item.event_type}`;
  const cached = state.aiResults[analysisKey];
  return `
    <article class="timeline-item ${state.timelineFocusId === timelineId ? "focused" : ""}" id="timeline-${escapeHtml(timelineId)}">
      <div class="timeline-head">
        <span class="node-id">${escapeHtml(timelineId)}</span>
        <strong>${escapeHtml(item.ce_year || "未知年份")} ｜ ${escapeHtml(item.event_type_label || eventLabel(item.event_type))}</strong>
        <span class="entity-chip">${escapeHtml(item.event_type)}</span>
      </div>
      <p class="timeline-text">${renderTimelineText(item.raw_text || "", state.timelineFilters.q || "", entities)}</p>
      <p class="muted">日期：${escapeHtml(item.historical_dates || "未抽取")} ｜ 機率：${escapeHtml(item.probability)} ｜ 引文：${escapeHtml(item.citation || "")}</p>
      ${entities.length ? `<div class="chip-row">${entities.map(renderTimelineEntityChip).join("")}</div>` : ""}
      <div class="ai-toolbar">
        <select class="ai-target" data-timeline-id="${escapeHtml(timelineId)}">${targetOptions.join("")}</select>
        <button data-analyze="${escapeHtml(timelineId)}">AI 分析</button>
        <button class="secondary" data-export-md="${escapeHtml(timelineId)}">匯出 Markdown</button>
      </div>
      <div class="research-panel">
        ${annotations.length ? `<div class="chip-row">${annotations.map(renderAnnotationChip).join("")}</div>` : ""}
        <div class="correction-grid">
          <div>
            <label>修正事件類型</label>
            <input class="event-correction" data-document-id="${escapeHtml(item.document_id)}" value="${escapeHtml(item.event_type_label || eventLabel(item.event_type))}" />
          </div>
          <button data-add-event="${escapeHtml(item.document_id)}">儲存事件修正</button>
          <div>
            <label>補充漏掉的實體</label>
            <input class="entity-correction" data-document-id="${escapeHtml(item.document_id)}" placeholder="文字|類別，例如 南京|LOC 或 夏原吉|PER" />
          </div>
          <button data-add-entity="${escapeHtml(item.document_id)}">儲存實體</button>
        </div>
        ${savedAnalyses.length ? `<div class="saved-ai">${savedAnalyses.map(renderSavedAnalysis).join("")}</div>` : ""}
        <div class="ai-chat-panel">
          <label>追問 AI</label>
          <textarea class="ai-chat-input" data-timeline-id="${escapeHtml(timelineId)}" placeholder="針對此節點繼續提問..."></textarea>
          <div class="toolbar">
            <button data-ai-chat="${escapeHtml(timelineId)}">送出追問</button>
          </div>
          <div class="ai-chat-history" id="chat-${escapeHtml(timelineId)}">${renderChatMessages(chatMessages)}</div>
        </div>
      </div>
      <div class="ai-result" id="analysis-${escapeHtml(timelineId)}">${cached ? nl2br(cached) : "尚未產生本節點的 AI 分析。"}</div>
    </article>`;
};

renderTimelineEntityChip = function renderTimelineEntityChipChinese(entity) {
  const color = entity.color || entityColor(entity.entity_type);
  const label = entity.entity_type_label || entityLabel(entity.entity_type);
  const typeClass = entityTypeClass(entity.entity_type);
  return `<span class="entity-chip colored-entity ${typeClass}" style="--entity-color:${escapeHtml(color)}">${escapeHtml(textWithLabel(displayEntityText(entity), label))}</span>`;
};

textWithLabel = function textWithLabelChinese(text, label) {
  return `${text}｜${label}`;
};

function renderTimelineText(text, query, entities = []) {
  const ranges = entities
    .filter((entity) => Number.isInteger(Number(entity.start)) && Number.isInteger(Number(entity.end)) && Number(entity.end) > Number(entity.start))
    .map((entity) => ({ ...entity, start: Number(entity.start), end: Number(entity.end) }))
    .sort((left, right) => left.start - right.start || right.end - left.end);
  let cursor = 0;
  let html = "";
  for (const entity of ranges) {
    if (entity.start < cursor || entity.start < 0 || entity.end > text.length) continue;
    html += renderTextSegment(text.slice(cursor, entity.start), query);
    html += `<mark class="entity-inline ${entityTypeClass(entity.entity_type)}" title="${escapeHtml(entity.entity_type_label || entityLabel(entity.entity_type))}">${escapeHtml(text.slice(entity.start, entity.end))}</mark>`;
    cursor = entity.end;
  }
  html += renderTextSegment(text.slice(cursor), query);
  return html;
}

function renderTextSegment(text, query) {
  const safe = escapeHtml(text);
  if (!query) return safe;
  const safeQuery = escapeHtml(query);
  return safe.replaceAll(safeQuery, `<mark class="text-hit">${safeQuery}</mark>`);
}

function entityTypeClass(entityType) {
  if (entityType === "PER") return "person-entity";
  const safeType = String(entityType || "unknown").toLowerCase().replace(/[^a-z0-9_-]/g, "-");
  return `entity-${safeType}`;
}

renderSavedAnalysis = function renderSavedAnalysisChinese(item) {
  return `<article class="result subtle"><strong>已儲存 AI 分析：${escapeHtml(item.target_kind)} / ${escapeHtml(item.target_value)}</strong><p>${nl2br(item.summary || "")}</p><p class="muted">${escapeHtml(item.model || "")} ${escapeHtml(item.updated_at || "")}</p></article>`;
};

renderBars = function renderBarsWithChineseIdList(selector, items, key, extraText = () => "") {
  const max = Math.max(1, ...items.map((item) => item.count));
  $(selector).innerHTML = items.map((item, index) => {
    const ids = splitCsv(item.timeline_ids);
    const preview = item.timeline_id_preview || ids.slice(0, 8);
    const label = item.label || (key === "event_type" ? eventLabel(item[key]) : key === "entity_type" ? entityLabel(item[key]) : item[key] || "未知");
    const extra = extraText(item);
    const detailId = `${selector.replace("#", "")}-${index}`;
    return `
      <div class="bar">
        <span>${escapeHtml(label)}</span>
        <div class="bar-track"><div class="bar-fill" style="width:${(item.count / max) * 100}%"></div></div>
        <strong>${escapeHtml(item.count)}</strong>
        <div class="bar-meta">
          ${ids.length ? `<span>節點 ${escapeHtml(ids.length)} 筆：</span>${preview.map((id) => `<button class="id-chip" data-timeline-id="${escapeHtml(id)}">${escapeHtml(id)}</button>`).join("")}` : "沒有對應時間節點"}
          ${ids.length > preview.length ? `<button class="id-list-toggle secondary" data-id-list="${escapeHtml(detailId)}">展開全部</button>` : ""}
          ${extra ? `<small>${escapeHtml(extra)}</small>` : ""}
          ${ids.length > preview.length ? `<div class="id-list" id="${escapeHtml(detailId)}" hidden>${ids.map((id) => `<button class="id-chip" data-timeline-id="${escapeHtml(id)}">${escapeHtml(id)}</button>`).join("")}</div>` : ""}
        </div>
      </div>`;
  }).join("") || `<p class="muted">沒有統計資料。</p>`;
  document.querySelectorAll(`${selector} .id-chip`).forEach((button) => {
    button.addEventListener("click", () => openTimelineId(button.dataset.timelineId));
  });
  document.querySelectorAll(`${selector} .id-list-toggle`).forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.idList);
      if (!target) return;
      target.hidden = !target.hidden;
      button.textContent = target.hidden ? "展開全部" : "收合清單";
    });
  });
};

attachDisplaySettingsPanel = function attachDisplaySettingsPanelChinese(view) {
  view.querySelector(".grid")?.insertAdjacentHTML("beforeend", `
    <div class="card">
      <h3>顯示與顏色設定</h3>
      <p class="muted">調整事件與實體的中文名稱，並設定時間軸上不同實體類別的標記顏色。</p>
      <label>事件類型中文名稱（JSON）</label>
      <textarea id="eventLabelsJson" class="settings-json"></textarea>
      <label>實體類別中文名稱（JSON）</label>
      <textarea id="entityLabelsJson" class="settings-json"></textarea>
      <label>實體顏色（JSON，HEX 色碼）</label>
      <textarea id="entityColorsJson" class="settings-json"></textarea>
      <div class="toolbar">
        <button id="saveDisplaySettings">儲存顯示設定</button>
        <button id="resetDisplaySettings" class="secondary">填入預設值</button>
      </div>
      <div id="displaySettingsResult" class="result subtle">尚未儲存。</div>
    </div>`);
  fillDisplaySettingsForms();
  $("#saveDisplaySettings")?.addEventListener("click", guarded(saveDisplaySettings));
  $("#resetDisplaySettings")?.addEventListener("click", () => {
    state.displaySettings = {
      event_labels: EVENT_LABELS_ZH,
      entity_labels: ENTITY_LABELS_ZH,
      entity_colors: ENTITY_COLORS_DEFAULT,
    };
    fillDisplaySettingsForms();
  });
};

saveEventCorrection = async function saveEventCorrectionChinese(documentId) {
  const input = document.querySelector(`.event-correction[data-document-id="${documentId}"]`);
  const eventType = input?.value.trim();
  if (!eventType) return toast("請先輸入事件類型。");
  await api("/api/annotations", {
    method: "POST",
    body: JSON.stringify({ document_id: Number(documentId), annotation_type: "event", action: "confirm", event_type: eventType }),
  });
  toast("事件修正已儲存。重新執行分類後會套用。");
  await loadTimeline();
};

saveEntityCorrection = async function saveEntityCorrectionChinese(documentId) {
  const input = document.querySelector(`.entity-correction[data-document-id="${documentId}"]`);
  const value = input?.value.trim() || "";
  const [text, entityType = "PER"] = value.split("|").map((item) => item.trim());
  if (!text) return toast("請先輸入實體文字。");
  await api("/api/annotations", {
    method: "POST",
    body: JSON.stringify({
      document_id: Number(documentId),
      annotation_type: "entity",
      action: "add",
      text,
      entity_type: entityType || "PER",
      start: 0,
      end: text.length,
    }),
  });
  toast("實體修正已儲存。重新執行 NER/Linking 後會套用。");
  await loadTimeline();
};

render();
guarded(loadStats)();
