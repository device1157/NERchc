import { api } from "./components/api.js";
import { SettingsView } from "./views/Settings.js";
import { CorpusView } from "./views/Corpus.js";
import { SchemaView } from "./views/Schema.js";
import { PromptView } from "./views/Prompt.js";
import { AnnotateView } from "./views/Annotate.js";
import { ReviewView } from "./views/Review.js";
import { DatasetView } from "./views/Dataset.js";
import { TrainView } from "./views/Train.js";
import { ResultsView } from "./views/Results.js";

const routes = [
  { id: "settings", label: "设置", step: "模型接入", view: SettingsView },
  { id: "corpus", label: "语料管理", step: "Step 1", view: CorpusView },
  { id: "schema", label: "实体定义", step: "Step 2", view: SchemaView },
  { id: "prompt", label: "Prompt设计", step: "Step 3", view: PromptView },
  { id: "annotate", label: "LLM批量标注", step: "Step 4", view: AnnotateView },
  { id: "review", label: "人工校对", step: "Step 5", view: ReviewView },
  { id: "dataset", label: "训练数据", step: "Step 6", view: DatasetView },
  { id: "train", label: "模型训练", step: "Step 7", view: TrainView },
  { id: "results", label: "结果展示", step: "Step 5/8", view: ResultsView },
];

const state = {
  route: currentRoute(),
  stats: null,
  toast: "",
};

function currentRoute() {
  return location.hash.replace("#/", "") || "settings";
}

function routeMeta() {
  return routes.find((route) => route.id === state.route) || routes[0];
}

function showToast(message) {
  state.toast = message;
  renderShell();
  setTimeout(() => {
    state.toast = "";
    renderShell();
  }, 4200);
}

async function refreshStats() {
  try {
    state.stats = await api("/api/corpus/stats");
  } catch {
    state.stats = null;
  }
}

function navHtml() {
  return routes
    .map(
      (route, index) => `
        <a class="nav-item ${route.id === state.route ? "active" : ""}" href="#/${route.id}">
          <span class="nav-index">${index + 1}</span>
          <span><strong>${route.label}</strong><br><small>${route.step}</small></span>
        </a>
      `,
    )
    .join("");
}

function statusHtml() {
  const done = [
    state.stats?.sentences > 0,
    true,
    true,
    false,
    state.stats?.reviewed > 0,
    false,
    false,
    false,
    false,
  ];
  return done.map((item) => `<span class="status-pill ${item ? "done" : ""}"></span>`).join("");
}

async function renderShell() {
  const meta = routeMeta();
  const root = document.querySelector("#app");
  root.innerHTML = `
    <div class="app-shell">
      <aside class="sidebar">
        <div class="brand-mark">
          <h1>明实录<br>NER 工作台</h1>
          <p>清洗、标注、校对、训练、导出的一体化本地流程。</p>
        </div>
        <nav class="nav-list">${navHtml()}</nav>
      </aside>
      <main class="main">
        <section class="topbar">
          <div>
            <h2>${meta.label}</h2>
            <div class="muted">项目：default · 句子 ${state.stats?.sentences ?? 0} · 抽样 ${state.stats?.sampled ?? 0} · 已校对 ${state.stats?.reviewed ?? 0}</div>
          </div>
          <div class="status-strip">${statusHtml()}</div>
        </section>
        <section class="view" id="view"></section>
      </main>
    </div>
    ${state.toast ? `<div class="toast">${state.toast}</div>` : ""}
  `;
  const view = meta.view({ api, showToast, refreshStats });
  document.querySelector("#view").innerHTML = await view.render();
  if (view.afterRender) {
    await view.afterRender(document.querySelector("#view"));
  }
}

window.addEventListener("hashchange", async () => {
  state.route = currentRoute();
  await refreshStats();
  await renderShell();
});

await refreshStats();
await renderShell();

