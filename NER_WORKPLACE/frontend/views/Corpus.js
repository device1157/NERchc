import { pretty } from "../components/api.js";

export function CorpusView(ctx) {
  let stats = {};
  let preview = { sentences: [] };

  return {
    async render() {
      stats = await ctx.api("/api/corpus/stats");
      try {
        preview = await ctx.api("/api/corpus/preview");
      } catch {
        preview = { sentences: [] };
      }
      return `
        <div class="grid">
          <section class="card span-5">
            <h3>② 上传与预处理</h3>
            <div class="field"><label>明实录 txt 文件</label><input id="corpus-file" type="file" accept=".txt"></div>
            <div class="actions">
              <button id="upload">上传</button>
              <button id="run-preprocess" class="secondary">运行完整流水线</button>
            </div>
            <div class="form-grid" style="margin-top:.8rem">
              <div class="field"><label>抽样总句数</label><input id="sample-size" type="number" value="600"></div>
              <div class="field"><label>最长句长</label><input id="max-len" type="number" value="200"></div>
              <div class="field"><label>最短句长</label><input id="min-len" type="number" value="50"></div>
              <div class="field"><label>繁简转换</label><select id="convert"><option value="true">启用 s2t</option><option value="false">关闭</option></select></div>
            </div>
          </section>
          <section class="card span-7">
            <h3>语料统计</h3>
            <div class="metric-row">
              <div class="metric">条目<strong>${stats.documents ?? 0}</strong></div>
              <div class="metric">句子<strong>${stats.sentences ?? 0}</strong></div>
              <div class="metric">抽样<strong>${stats.sampled ?? 0}</strong></div>
              <div class="metric">已校对<strong>${stats.reviewed ?? 0}</strong></div>
            </div>
            <pre>${pretty(preview.stats || {})}</pre>
          </section>
          <section class="card">
            <h3>句读抽检</h3>
            <table class="table">
              <thead><tr><th>ID</th><th>句子</th><th>状态</th></tr></thead>
              <tbody>
                ${(preview.sentences || []).map((item) => `<tr><td>${item.id}</td><td>${item.text}</td><td>${item.status}</td></tr>`).join("") || `<tr><td colspan="3" class="muted">暂无句子，请先上传并预处理。</td></tr>`}
              </tbody>
            </table>
          </section>
        </div>
      `;
    },
    async afterRender(root) {
      root.querySelector("#upload").addEventListener("click", async () => {
        const input = root.querySelector("#corpus-file");
        if (!input.files.length) return ctx.showToast("请选择 txt 文件");
        const body = new FormData();
        body.append("file", input.files[0]);
        const result = await ctx.api("/api/corpus/upload", { method: "POST", body });
        ctx.showToast(`已上传 ${result.filename}`);
      });
      root.querySelector("#run-preprocess").addEventListener("click", async () => {
        const body = {
          step: "all",
          sample_size: Number(root.querySelector("#sample-size").value),
          max_sentence_len: Number(root.querySelector("#max-len").value),
          min_sentence_len: Number(root.querySelector("#min-len").value),
          convert_s2t: root.querySelector("#convert").value === "true",
          reset_existing: true,
        };
        const result = await ctx.api("/api/corpus/preprocess", { method: "POST", body });
        await ctx.refreshStats();
        ctx.showToast(`预处理完成：${result.documents} 条，${result.sentences} 句`);
        location.reload();
      });
    },
  };
}

