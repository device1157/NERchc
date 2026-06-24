import { escapeHtml } from "./api.js";

export function renderHighlight(text, annotations = [], colors = {}) {
  const safe = String(text ?? "");
  const sorted = [...annotations]
    .filter((item) => Number.isFinite(Number(item.start)) && Number.isFinite(Number(item.end)))
    .sort((a, b) => a.start - b.start || b.end - a.end);
  let cursor = 0;
  let html = "";
  for (const item of sorted) {
    const start = Math.max(0, Math.min(safe.length, Number(item.start)));
    const end = Math.max(start, Math.min(safe.length, Number(item.end)));
    if (start < cursor) continue;
    html += escapeHtml(safe.slice(cursor, start));
    const color = colors[item.entity_type_tag || item.type] || "#8b3a21";
    html += `<span class="entity-mark" style="background:${color}" title="${escapeHtml(item.entity_type_tag || item.type)} [${start},${end})">${escapeHtml(safe.slice(start, end))}</span>`;
    cursor = end;
  }
  html += escapeHtml(safe.slice(cursor));
  return `<div class="highlight-text">${html}</div>`;
}

