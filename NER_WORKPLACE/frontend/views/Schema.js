import { escapeHtml, formData } from "../components/api.js";

export function SchemaView(ctx) {
  let entityTypes = [];

  return {
    async render() {
      entityTypes = await ctx.api("/api/entity-types");
      const current = entityTypes[0] || {};
      return `
        <div class="grid">
          <section class="card span-7">
            <h3>③ 实体类型</h3>
            <div class="grid">
              ${entityTypes
                .map(
                  (item) => `
                <article class="card span-6" style="box-shadow:none">
                  <span class="tag" style="background:${item.color}">${item.tag}</span>
                  <h3>${escapeHtml(item.label)}</h3>
                  <p>${escapeHtml(item.definition)}</p>
                  <p class="muted">${escapeHtml(item.rules)}</p>
                  <button class="secondary edit-type" data-id="${item.id}">载入编辑</button>
                </article>
              `,
                )
                .join("")}
            </div>
          </section>
          <section class="card span-5">
            <h3>新增 / 编辑</h3>
            <form id="schema-form" class="form-grid">
              <input type="hidden" name="id" value="${current.id ?? ""}">
              <div class="field"><label>短标签</label><input name="tag" value="${current.tag ?? ""}"></div>
              <div class="field"><label>中文名</label><input name="label" value="${current.label ?? ""}"></div>
              <div class="field"><label>颜色</label><input name="color" type="color" value="${current.color ?? "#d97706"}"></div>
              <div class="field"><label>频率</label><input name="freq" type="number" step="0.01" value="${current.freq ?? ""}"></div>
              <div class="field" style="grid-column:1/-1"><label>定义</label><textarea name="definition">${current.definition ?? ""}</textarea></div>
              <div class="field" style="grid-column:1/-1"><label>边界规则</label><textarea name="rules">${current.rules ?? ""}</textarea></div>
              <div class="field"><label>正例（一行一个）</label><textarea name="positive_examples">${(current.positive_examples || []).join("\n")}</textarea></div>
              <div class="field"><label>反例（一行一个）</label><textarea name="negative_examples">${(current.negative_examples || []).join("\n")}</textarea></div>
            </form>
            <div class="actions">
              <button id="save-type">保存</button>
              <button id="new-type" class="secondary">清空新增</button>
            </div>
          </section>
        </div>
      `;
    },
    async afterRender(root) {
      const loadForm = (item = {}) => {
        const form = root.querySelector("#schema-form");
        const fields = form.elements;
        fields.id.value = item.id || "";
        fields.tag.value = item.tag || "";
        fields.label.value = item.label || "";
        fields.color.value = item.color || "#d97706";
        fields.freq.value = item.freq || "";
        fields.definition.value = item.definition || "";
        fields.rules.value = item.rules || "";
        fields.positive_examples.value = (item.positive_examples || []).join("\n");
        fields.negative_examples.value = (item.negative_examples || []).join("\n");
      };
      root.querySelectorAll(".edit-type").forEach((button) => {
        button.addEventListener("click", () => loadForm(entityTypes.find((item) => String(item.id) === button.dataset.id)));
      });
      root.querySelector("#new-type").addEventListener("click", () => loadForm());
      root.querySelector("#save-type").addEventListener("click", async () => {
        const form = root.querySelector("#schema-form");
        const data = formData(form);
        const body = {
          tag: data.tag,
          label: data.label,
          color: data.color,
          freq: data.freq ? Number(data.freq) : null,
          definition: data.definition,
          rules: data.rules,
          positive_examples: data.positive_examples.split(/\n+/).map((x) => x.trim()).filter(Boolean),
          negative_examples: data.negative_examples.split(/\n+/).map((x) => x.trim()).filter(Boolean),
        };
        const method = data.id ? "PUT" : "POST";
        const path = data.id ? `/api/entity-types/${data.id}` : "/api/entity-types";
        await ctx.api(path, { method, body });
        ctx.showToast("实体定义已保存");
        location.reload();
      });
    },
  };
}
