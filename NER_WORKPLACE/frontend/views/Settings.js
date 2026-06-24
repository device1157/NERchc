import { formData, pretty } from "../components/api.js";

export function SettingsView(ctx) {
  let settings = null;
  let testResult = null;

  return {
    async render() {
      settings = await ctx.api("/api/settings/llm");
      return `
        <div class="grid">
          <section class="card span-7">
            <h3>① 模型接入</h3>
            <form id="settings-form" class="form-grid">
              <div class="field"><label>base_url</label><input name="base_url" value="${settings.base_url ?? ""}"></div>
              <div class="field"><label>model_name</label><input name="model_name" value="${settings.model_name ?? ""}"></div>
              <div class="field"><label>api_key（留空表示不覆盖）</label><input name="api_key" type="password" placeholder="${settings.api_key || "未设置"}"></div>
              <div class="field"><label>temperature</label><input name="temperature" type="number" step="0.1" value="${settings.temperature ?? 0}"></div>
              <div class="field"><label>max_tokens</label><input name="max_tokens" type="number" value="${settings.max_tokens ?? 800}"></div>
              <div class="field"><label>请求超时（秒）</label><input name="timeout_seconds" type="number" value="${settings.timeout_seconds ?? 60}"></div>
              <div class="field"><label>并发数</label><input name="concurrency" type="number" value="${settings.concurrency ?? 2}"></div>
              <div class="field"><label>每秒请求上限</label><input name="rps" type="number" step="0.1" value="${settings.rps ?? 1}"></div>
            </form>
            <div class="actions">
              <button id="save-settings">保存设置</button>
              <button id="test-settings" class="secondary">测试连接</button>
            </div>
          </section>
          <section class="card span-5">
            <h3>连接状态</h3>
            <p class="muted">API key 只保存在本机 config/secrets.json，前端不会显示明文。</p>
            <pre id="settings-result">${pretty(testResult || settings)}</pre>
          </section>
        </div>
      `;
    },
    async afterRender(root) {
      const collect = () => {
        const data = formData(root.querySelector("#settings-form"));
        return {
          ...data,
          temperature: Number(data.temperature),
          max_tokens: Number(data.max_tokens),
          timeout_seconds: Number(data.timeout_seconds),
          concurrency: Number(data.concurrency),
          rps: Number(data.rps),
        };
      };
      root.querySelector("#save-settings").addEventListener("click", async () => {
        const saved = await ctx.api("/api/settings/llm", { method: "POST", body: collect() });
        root.querySelector("#settings-result").innerHTML = pretty(saved);
        ctx.showToast("模型接入设置已保存");
      });
      root.querySelector("#test-settings").addEventListener("click", async () => {
        root.querySelector("#settings-result").textContent = "测试中...";
        const result = await ctx.api("/api/settings/llm/test", { method: "POST", body: collect() });
        root.querySelector("#settings-result").innerHTML = pretty(result);
      });
    },
  };
}

