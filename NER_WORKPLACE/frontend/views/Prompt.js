import { escapeHtml, formData, pretty } from "../components/api.js";

export function PromptView(ctx) {
  let prompts = [];
  let types = [];
  let sentences = { items: [] };

  return {
    async render() {
      prompts = await ctx.api("/api/prompts");
      types = await ctx.api("/api/entity-types");
      sentences = await ctx.api("/api/sentences?page_size=5&sampled=true");
      const active = prompts.find((item) => item.is_active) || prompts[0] || {};
      return `
        <div class="grid">
          <section class="card span-6">
            <h3>④ Prompt 构建器</h3>
            <form id="prompt-form">
              <div class="field"><label>模板名</label><input name="name" value="${escapeHtml(active.name || "")}"></div>
              <div class="field"><label>System prompt</label><textarea name="system_prompt" style="min-height:14rem">${escapeHtml(active.system_prompt || "")}</textarea></div>
              <div class="field"><label>User 模板</label><textarea name="user_template">${escapeHtml(active.user_template || "")}</textarea></div>
            </form>
            <div class="actions">
              <button id="save-prompt">保存为 active</button>
              <button id="sync-schema" class="secondary">同步实体定义</button>
            </div>
          </section>
          <section class="card span-6">
            <h3>实时预览 / 试运行</h3>
            <div class="field"><label>样例句</label><textarea id="preview-sentence">${escapeHtml(sentences.items?.[0]?.text || "占城國王遣其臣虎都蠻來朝貢詔中書省左丞相李善長宴勞之")}</textarea></div>
            <div class="field"><label>实体类型</label><select id="preview-type">${types.map((item) => `<option value="${item.tag}">${item.label}（${item.tag}）</option>`).join("")}</select></div>
            <div class="actions">
              <button id="preview">渲染 messages</button>
              <button id="dry-run" class="secondary">试调 LLM</button>
            </div>
            <pre id="prompt-result"></pre>
          </section>
        </div>
      `;
    },
    async afterRender(root) {
      root.querySelector("#save-prompt").addEventListener("click", async () => {
        const data = formData(root.querySelector("#prompt-form"));
        await ctx.api("/api/prompts", { method: "POST", body: { ...data, is_active: true } });
        ctx.showToast("Prompt 模板已保存并启用");
      });
      root.querySelector("#sync-schema").addEventListener("click", async () => {
        const result = await ctx.api("/api/prompts/sync-schema", { method: "POST", body: {} });
        root.querySelector("[name=system_prompt]").value = result.system_prompt;
      });
      const payload = () => ({
        sentence: root.querySelector("#preview-sentence").value,
        type_tag: root.querySelector("#preview-type").value,
      });
      root.querySelector("#preview").addEventListener("click", async () => {
        const result = await ctx.api("/api/prompts/preview", { method: "POST", body: payload() });
        root.querySelector("#prompt-result").innerHTML = pretty(result);
      });
      root.querySelector("#dry-run").addEventListener("click", async () => {
        root.querySelector("#prompt-result").textContent = "调用中...";
        const result = await ctx.api("/api/prompts/dry-run", { method: "POST", body: payload() });
        root.querySelector("#prompt-result").innerHTML = pretty(result);
      });
    },
  };
}

