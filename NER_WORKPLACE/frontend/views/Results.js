import { renderHighlight } from "../components/HighlightText.js";
import { escapeHtml, pretty } from "../components/api.js";

export function ResultsView(ctx) {
  let rows = { items: [] };
  let types = [];
  let colors = {};
  let runs = [];

  return {
    async render() {
      rows = await ctx.api("/api/results/annotations?page_size=12");
      types = await ctx.api("/api/entity-types");
      colors = Object.fromEntries(types.map((type) => [type.tag, type.color]));
      runs = await ctx.api("/api/train/runs");
      return `
        <div class="grid">
          <section class="card span-7">
            <h3>⑨ 标注结果浏览</h3>
            ${rows.items
              .map(
                (item) => `
              <article class="card" style="box-shadow:none;margin-bottom:.8rem">
                <div class="muted">#${item.id} · ${item.volume || "未分卷"} · ${item.status}</div>
                ${renderHighlight(item.text, item.annotations, colors)}
              </article>
            `,
              )
              .join("") || `<p class="muted">暂无标注结果。</p>`}
          </section>
          <section class="card span-5">
            <h3>模型推理预览</h3>
            <textarea id="infer-text">占城國王遣其臣虎都蠻來朝貢詔中書省左丞相李善長宴勞之</textarea>
            <div class="actions"><button id="infer">预览推理</button><button id="export" class="secondary">导出结果</button></div>
            <div id="infer-result"></div>
            <h3>指标看板</h3>
            <pre>${pretty(runs[0]?.metrics || {})}</pre>
          </section>
        </div>
      `;
    },
    async afterRender(root) {
      root.querySelector("#infer").addEventListener("click", async () => {
        const result = await ctx.api("/api/results/infer", { method: "POST", body: { text: root.querySelector("#infer-text").value } });
        root.querySelector("#infer-result").innerHTML = renderHighlight(result.text, result.entities, colors);
      });
      root.querySelector("#export").addEventListener("click", async () => {
        const result = await ctx.api("/api/results/export");
        ctx.showToast(`导出路径：${result.annotations_jsonl}`);
      });
    },
  };
}

