import { pretty } from "../components/api.js";

export function DatasetView(ctx) {
  let stats = {};
  let sample = { items: [] };

  return {
    async render() {
      stats = await ctx.api("/api/dataset/stats");
      sample = await ctx.api("/api/dataset/sample");
      return `
        <div class="grid">
          <section class="card span-5">
            <h3>⑦ 训练数据构建</h3>
            <div class="form-grid">
              <div class="field"><label>数据集名称</label><input id="dataset-name" value="reviewed_dataset"></div>
              <div class="field"><label>正负比</label><input id="pn-ratio" type="number" step="0.1" value="2"></div>
              <div class="field"><label>包含未人工确认 LLM 数据</label><select id="include-llm"><option value="false">否</option><option value="true">是，仅调试</option></select></div>
            </div>
            <div class="actions">
              <button id="build">构建数据集</button>
              <button id="export" class="secondary">导出路径</button>
            </div>
          </section>
          <section class="card span-7">
            <h3>统计看板</h3>
            <pre id="dataset-stats">${pretty(stats)}</pre>
          </section>
          <section class="card">
            <h3>BIOES 抽样检视</h3>
            <pre>${pretty(sample.items || [])}</pre>
          </section>
        </div>
      `;
    },
    async afterRender(root) {
      root.querySelector("#build").addEventListener("click", async () => {
        const result = await ctx.api("/api/dataset/build", {
          method: "POST",
          body: {
            name: root.querySelector("#dataset-name").value,
            positive_negative_ratio: Number(root.querySelector("#pn-ratio").value),
            include_llm_only: root.querySelector("#include-llm").value === "true",
          },
        });
        root.querySelector("#dataset-stats").innerHTML = pretty(result);
        ctx.showToast("训练数据集已构建");
      });
      root.querySelector("#export").addEventListener("click", async () => {
        const result = await ctx.api("/api/dataset/export");
        ctx.showToast(`导出文件：${result.path}`);
      });
    },
  };
}

