import { pretty } from "../components/api.js";

export function TrainView(ctx) {
  let runs = [];
  let tasks = [];

  return {
    async render() {
      runs = await ctx.api("/api/train/runs");
      tasks = (await ctx.api("/api/tasks")).filter((task) => task.type === "train");
      return `
        <div class="grid">
          <section class="card span-5">
            <h3>⑧ 模型训练</h3>
            <div class="form-grid">
              <div class="field"><label>编码器</label><input id="encoder" value="hsc748NLP/GujiRoBERTa_jian_fan"></div>
              <div class="field"><label>epochs</label><input id="epochs" type="number" value="3"></div>
              <div class="field"><label>batch</label><input id="batch" type="number" value="8"></div>
              <div class="field"><label>learning rate</label><input id="lr" type="number" step="0.000001" value="0.000005"></div>
              <div class="field"><label>CRF</label><select id="crf"><option value="false">关闭</option><option value="true">启用</option></select></div>
            </div>
            <div class="actions"><button id="start-train">开始训练</button><button id="refresh" class="secondary">刷新</button></div>
            <p class="muted">当前实现默认模拟训练任务，确保端到端流程可验证；安装 transformers/torch 后可替换 trainer。</p>
          </section>
          <section class="card span-7">
            <h3>训练任务</h3>
            <pre>${pretty(tasks)}</pre>
          </section>
          <section class="card">
            <h3>训练运行</h3>
            <table class="table">
              <thead><tr><th>ID</th><th>状态</th><th>checkpoint</th><th>progress</th><th>metrics</th></tr></thead>
              <tbody>
                ${runs.map((run) => `<tr><td>${run.id}</td><td>${run.status}</td><td>${run.checkpoint_path || ""}</td><td><pre>${pretty(run.progress)}</pre></td><td><pre>${pretty(run.metrics)}</pre></td></tr>`).join("") || `<tr><td colspan="5" class="muted">暂无训练运行。</td></tr>`}
              </tbody>
            </table>
          </section>
        </div>
      `;
    },
    async afterRender(root) {
      root.querySelector("#start-train").addEventListener("click", async () => {
        const result = await ctx.api("/api/train/start", {
          method: "POST",
          body: {
            encoder: root.querySelector("#encoder").value,
            epochs: Number(root.querySelector("#epochs").value),
            batch_size: Number(root.querySelector("#batch").value),
            learning_rate: Number(root.querySelector("#lr").value),
            use_crf: root.querySelector("#crf").value === "true",
            simulate: true,
          },
        });
        ctx.showToast(`训练任务已启动：#${result.task_id}`);
        setTimeout(() => location.reload(), 500);
      });
      root.querySelector("#refresh").addEventListener("click", () => location.reload());
    },
  };
}

