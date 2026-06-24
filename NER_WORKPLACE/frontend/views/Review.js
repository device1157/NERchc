import { renderHighlight } from "../components/HighlightText.js";
import { escapeHtml } from "../components/api.js";

export function ReviewView(ctx) {
  let item = null;
  let types = [];
  let colors = {};

  return {
    async render() {
      item = await ctx.api("/api/review/next");
      types = await ctx.api("/api/entity-types");
      colors = Object.fromEntries(types.map((type) => [type.tag, type.color]));
      if (!item) {
        return `<section class="card"><h3>⑥ 人工校对</h3><p class="muted">没有待校对句子。请先预处理、抽样或运行 LLM 标注。</p></section>`;
      }
      return `
        <div class="grid">
          <section class="card span-7">
            <h3>逐句审校：#${item.id}</h3>
            ${renderHighlight(item.text, item.annotations, colors)}
            <p class="muted">拖选后可手动复制起止位置填写；MVP 当前提供表单式增删改，后续可增强为直接拖选。</p>
            <div class="actions">
              <button id="confirm">确认本句并下一句</button>
              <button id="refresh" class="secondary">刷新</button>
            </div>
          </section>
          <section class="card span-5">
            <h3>新增实体</h3>
            <form id="ann-form" class="form-grid">
              <div class="field"><label>类型</label><select name="entity_type_tag">${types.map((type) => `<option value="${type.tag}">${type.label}（${type.tag}）</option>`).join("")}</select></div>
              <div class="field"><label>start</label><input name="start" type="number" value="0"></div>
              <div class="field"><label>end</label><input name="end" type="number" value="1"></div>
              <div class="field"><label>文本</label><input name="text" placeholder="留空则按 span 截取"></div>
            </form>
            <div class="actions"><button id="add-ann">添加实体</button></div>
          </section>
          <section class="card">
            <h3>实体列表</h3>
            <table class="table">
              <thead><tr><th>ID</th><th>类型</th><th>span</th><th>文本</th><th>来源</th><th>状态</th><th>操作</th></tr></thead>
              <tbody>
                ${item.annotations
                  .map(
                    (ann) => `<tr>
                      <td>${ann.id}</td><td>${ann.entity_type_tag}</td><td>[${ann.start},${ann.end})</td><td>${escapeHtml(ann.text)}</td><td>${ann.source}</td><td>${ann.status}</td>
                      <td><button class="secondary accept" data-id="${ann.id}">确认</button> <button class="danger reject" data-id="${ann.id}">删除</button></td>
                    </tr>`,
                  )
                  .join("") || `<tr><td colspan="7" class="muted">本句暂无实体。</td></tr>`}
              </tbody>
            </table>
          </section>
        </div>
      `;
    },
    async afterRender(root) {
      if (!item) return;
      root.querySelector("#confirm").addEventListener("click", async () => {
        await ctx.api("/api/review/confirm", { method: "POST", body: { sentence_id: item.id } });
        await ctx.refreshStats();
        location.reload();
      });
      root.querySelector("#refresh").addEventListener("click", () => location.reload());
      root.querySelector("#add-ann").addEventListener("click", async () => {
        const form = root.querySelector("#ann-form");
        const body = {
          sentence_id: item.id,
          entity_type_tag: form.entity_type_tag.value,
          start: Number(form.start.value),
          end: Number(form.end.value),
          text: form.text.value || null,
          source: "human",
          status: "added",
        };
        await ctx.api("/api/annotations", { method: "POST", body });
        location.reload();
      });
      root.querySelectorAll(".accept").forEach((button) =>
        button.addEventListener("click", async () => {
          await ctx.api(`/api/annotations/${button.dataset.id}`, { method: "PUT", body: { id: Number(button.dataset.id), status: "confirmed" } });
          location.reload();
        }),
      );
      root.querySelectorAll(".reject").forEach((button) =>
        button.addEventListener("click", async () => {
          await ctx.api(`/api/annotations/${button.dataset.id}`, { method: "DELETE" });
          location.reload();
        }),
      );
    },
  };
}

