const fallbackRanges = {
  week: ["2026年第25周"],
  month: ["2026-06"],
  quarter: ["2026 Q2"],
  half: ["2026 H1"],
  year: ["2026 全年"],
};

const periodSelect = document.querySelector("#periodSelect");
const rangeSelect = document.querySelector("#rangeSelect");
const searchInput = document.querySelector("#searchInput");
const prBody = document.querySelector("#prTable tbody");
const contributorBody = document.querySelector("#contributorTable tbody");
const detailPanel = document.querySelector("#detailPanel");

let dashboard = null;
let ranges = fallbackRanges;
let selectedPrId = null;
let staticBundle = null;

function formatNumber(value) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Math.round(Number(value)).toLocaleString("zh-CN");
}

function formatScore(value) {
  if (value === null || value === undefined) return "-";
  return Number(value).toFixed(Number.isInteger(Number(value)) ? 0 : 2);
}

function percent(value, total) {
  if (!total) return "-";
  return `${((value / total) * 100).toFixed(1)}%`;
}

function normalizeTime(value) {
  if (!value) return "";
  return value.replace("T", " ").replace("+08:00", "").slice(0, 16);
}

function level(score) {
  if (score === null || score === undefined) return ["未评分", "ok"];
  if (score < 3) return ["待改进", "poor"];
  if (score > 3) return ["优秀", "excellent"];
  return ["达标", "ok"];
}

function populateRanges(keepValue = true) {
  const current = keepValue ? rangeSelect.value : "";
  const options = ranges[periodSelect.value] || fallbackRanges[periodSelect.value] || [];
  rangeSelect.innerHTML = "";
  for (const range of options) {
    const option = document.createElement("option");
    option.value = range;
    option.textContent = range;
    rangeSelect.appendChild(option);
  }
  if (current && options.includes(current)) {
    rangeSelect.value = current;
  }
}

function matchesSearch(row) {
  const keyword = searchInput.value.trim().toLowerCase();
  if (!keyword) return true;
  return JSON.stringify(row).toLowerCase().includes(keyword);
}

async function loadDashboard() {
  const params = new URLSearchParams({
    period: periodSelect.value,
    range: rangeSelect.value || "",
  });
  try {
    const response = await fetch(`/api/dashboard?${params.toString()}`);
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text);
    }
    dashboard = await response.json();
  } catch (error) {
    dashboard = await loadStaticDashboard();
  }
  ranges = dashboard.ranges || fallbackRanges;
  populateRanges(true);
  if (!selectedPrId && dashboard.prs?.length) selectedPrId = dashboard.prs[0].id;
  renderAll();
}

async function loadStaticDashboard() {
  if (!staticBundle) {
    const response = await fetch("./dashboard-static.json");
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text || `静态数据加载失败：${response.status}`);
    }
    staticBundle = await response.json();
  }

  ranges = staticBundle.ranges || fallbackRanges;
  populateRanges(true);
  const period = periodSelect.value;
  const labels = ranges[period] || [];
  const label = rangeSelect.value || labels[0];
  const snapshot = staticBundle.dashboards?.[period]?.[label];
  if (!snapshot) {
    throw new Error(`静态数据不存在：${period} ${label || ""}`.trim());
  }
  return snapshot;
}

function renderMetrics() {
  const metrics = dashboard?.metrics || {};
  document.querySelector("#metricPr").textContent = formatNumber(metrics.mergedPrs);
  document.querySelector("#metricLines").textContent = formatNumber(metrics.lines);
  document.querySelector("#metricReviews").textContent = formatNumber(metrics.reviewComments);
  document.querySelector("#metricScore").textContent = formatScore(metrics.averageScore);
  document.querySelector("#metricPoor").textContent = formatNumber(metrics.poorPrs);
  document.querySelector("#metricExcellent").textContent = formatNumber(metrics.excellentPrs);

  const sync = dashboard?.lastSync;
  const syncTime = document.querySelector(".sync-time");
  const syncNote = document.querySelector(".sync-note");
  if (sync) {
    syncTime.textContent = normalizeTime(sync.finished_at || sync.started_at);
    syncNote.textContent = `${sync.status} · ${sync.pr_count} 个 PR · ${normalizeTime(sync.window_start)} 至 ${normalizeTime(sync.window_end)}`;
  }
}

function renderPrTable() {
  const rows = (dashboard?.prs || []).filter(matchesSearch);
  prBody.innerHTML = "";

  for (const row of rows) {
    const [label, cls] = level(row.score);
    const tr = document.createElement("tr");
    tr.className = row.id === selectedPrId ? "selected" : "";
    tr.dataset.id = row.id;
    tr.innerHTML = `
      <td>#${row.id}</td>
      <td class="title-cell">${row.title}</td>
      <td>${row.author}</td>
      <td>${normalizeTime(row.mergedAt)}</td>
      <td>${formatNumber(row.lines)}</td>
      <td>${formatNumber(row.reviews)}</td>
      <td>${formatScore(row.score)}</td>
      <td>${row.reviewer || "-"}</td>
      <td><span class="badge ${cls}">${label}</span></td>
    `;
    tr.addEventListener("click", () => {
      selectedPrId = row.id;
      renderPrTable();
      renderDetail();
    });
    prBody.appendChild(tr);
  }

  if (!rows.length) {
    prBody.innerHTML = `<tr><td colspan="9" class="title-cell">当前筛选条件下暂无 PR 数据。</td></tr>`;
  }
}

function renderDetail() {
  const row = (dashboard?.prs || []).find((item) => item.id === selectedPrId);
  if (!row) {
    detailPanel.innerHTML = `<div class="detail-empty">选择一条 PR 查看检视意见与 MR 评价。</div>`;
    return;
  }

  const [label, cls] = level(row.score);
  const details = row.detail || [];
  detailPanel.innerHTML = `
    <div class="detail-header">
      <div>
        <div class="detail-title">#${row.id} ${row.title}</div>
        <div class="detail-meta">${row.author} · ${normalizeTime(row.mergedAt)} · ${formatNumber(row.lines)} 行代码 · ${formatNumber(row.reviews)} 条检视意见</div>
      </div>
      <span class="badge ${cls}">${label}</span>
    </div>
    <div class="review-list">
      ${
        details.length
          ? details
              .map(
                (item) => `
                  <div class="review-item">
                    <div class="review-top">
                      <span>${item.type} · ${item.author} · ${normalizeTime(item.createdAt)}</span>
                      <span>${item.path || "-"}</span>
                    </div>
                    <div class="review-body">${item.body}</div>
                  </div>
                `,
              )
              .join("")
          : `<div class="review-item"><div class="review-body">该 PR 暂无人工检视意见或 MR 评价。</div></div>`
      }
    </div>
  `;
}

function renderContributorTable() {
  const rows = (dashboard?.contributors || []).filter(matchesSearch);
  contributorBody.innerHTML = "";

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.name}</td>
      <td>${formatNumber(row.submit_prs)}</td>
      <td>${formatNumber(row.submit_lines)}</td>
      <td>${formatNumber(row.received_reviews)}</td>
      <td>${formatNumber(row.rated_prs)}</td>
      <td class="negative">${formatNumber(row.poor_prs)}</td>
      <td>${percent(row.poor_prs, row.rated_prs)}</td>
      <td class="positive">${formatNumber(row.excellent_prs)}</td>
      <td>${percent(row.excellent_prs, row.rated_prs)}</td>
      <td>${formatNumber(row.review_comments)}</td>
      <td>${formatNumber(row.review_prs)}</td>
      <td>${formatNumber(row.scored_prs)}</td>
      <td class="negative">${formatNumber(row.scored_poor)}</td>
      <td class="positive">${formatNumber(row.scored_excellent)}</td>
      <td>${percent(row.scored_excellent, row.scored_prs)}</td>
    `;
    contributorBody.appendChild(tr);
  }

  if (!rows.length) {
    contributorBody.innerHTML = `<tr><td colspan="15">当前筛选条件下暂无贡献者数据。</td></tr>`;
  }
}

function renderAll() {
  renderMetrics();
  renderPrTable();
  renderDetail();
  renderContributorTable();
}

document.querySelectorAll(".view-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".view-tab").forEach((item) => item.classList.remove("active"));
    document.querySelectorAll(".view-panel").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`#${tab.dataset.view}View`).classList.add("active");
  });
});

periodSelect.addEventListener("change", async () => {
  populateRanges(false);
  selectedPrId = null;
  await loadDashboard();
});
rangeSelect.addEventListener("change", async () => {
  selectedPrId = null;
  await loadDashboard();
});
searchInput.addEventListener("input", renderAll);

populateRanges(false);
loadDashboard().catch((error) => {
  console.error(error);
  document.querySelector(".content").insertAdjacentHTML(
    "afterbegin",
    `<div class="table-card" style="padding:16px;margin-bottom:16px;color:#ffabab">数据加载失败：${error.message}</div>`,
  );
});
