import { pretty } from "../components/api.js";

export function AnnotateView(ctx) {
  let estimate = {};
  let tasks = [];

  return {
    async render() {
      estimate = await ctx.api("/api/annotate/estimate");
      tasks = await ctx.api("/api/tasks");
      return `
        <div class="grid">
          <section class="card span-5">
            <h3>⑤ LLM 批量标注</h3>
            <div class="metric-row">
              <div class="metric">抽样句<strong>${estimate.sentences ?? 0}</strong></div>
              <div class="metric">类型数<strong>${estimate.entity_types ?? 0}</strong></div>
              <div class="metric">调用数<strong>${estimate.total_calls ?? 0}</strong></div>
              <div class="metric">剩余<strong>${estimate.remaining ?? 0}</strong></div>
            </div>
            <div class="actions">
              <button id="start-annotate">启动批量标注</button>
              <button id="refresh" class="secondary">刷新任务</button>
            </div>
            <p class="muted">断点单位为句子×实体类型。已 done 的 llm_calls 会自动跳过。</p>
          </section>
          <section class="card span-7">
            <h3>后台任务</h3>
            <table class="table">
              <thead><tr><th>ID</th><th>类型</th><th>状态</th><th>进度</th><th>消息</th><th>操作</th></tr></thead>
              <tbody>
                ${tasks
                  .map(
                    (item) => `<tr>
                      <td>${item.id}</td><td>${item.type}</td><td>${item.status}</td><td>${item.progress}/${item.total}</td><td>${item.message || ""}</td>
                      <td><button class="secondary pause" data-id="${item.id}">暂停</button> <button class="secondary resume" data-id="${item.id}">继续</button></td>
                    </tr>`,
                  )
                  .join("") || `<tr><td colspan="6" class="muted">暂无任务。</td></tr>`}
              </tbody>
            </table>
          </section>
        </div>
      `;
    },
    async afterRender(root) {
      root.querySelector("#start-annotate").addEventListener("click", async () => {
        const result = await ctx.api("/api/annotate/start", { method: "POST", body: {} });
        ctx.showToast(`标注任务已启动：#${result.task_id}`);
        setTimeout(() => location.reload(), 500);
      });
      root.querySelector("#refresh").addEventListener("click", () => location.reload());
      root.querySelectorAll(".pause").forEach((button) => {
        button.addEventListener("click", async () => {
          await ctx.api(`/api/tasks/${button.dataset.id}/pause`, { method: "POST", body: {} });
          location.reload();
        });
      });
      root.querySelectorAll(".resume").forEach((button) => {
        button.addEventListener("click", async () => {
          await ctx.api(`/api/tasks/${button.dataset.id}/resume`, { method: "POST", body: {} });
          location.reload();
        });
      });
    },
  };
}

