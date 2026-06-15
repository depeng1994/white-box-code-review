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
const drilldownModal = document.querySelector("#drilldownModal");
const drilldownClose = document.querySelector("#drilldownClose");
const drilldownTitle = document.querySelector("#drilldownTitle");
const drilldownKicker = document.querySelector("#drilldownKicker");
const drilldownSummary = document.querySelector("#drilldownSummary");
const drilldownBody = document.querySelector("#drilldownTable tbody");
const themeToggle = document.querySelector("#themeToggle");
const themeIcon = themeToggle?.querySelector(".theme-icon");
const themeLabel = themeToggle?.querySelector(".theme-label");
const themeStorageKey = "reviewBoardTheme";
const assetVersion = document.documentElement.dataset.assetVersion || "local";

let dashboard = null;
let ranges = fallbackRanges;
let selectedPrId = null;
let staticBundle = null;
let selectedDrilldownPrId = null;
let prSort = { key: "id", direction: "desc" };
let contributorSort = { key: "submit_prs", direction: "desc" };
let activeDrilldownRows = [];

function preferredTheme() {
  const saved = localStorage.getItem(themeStorageKey);
  if (saved === "light" || saved === "dark") return saved;
  return document.documentElement.dataset.theme || "dark";
}

function applyTheme(theme) {
  const nextTheme = theme === "light" ? "light" : "dark";
  document.documentElement.dataset.theme = nextTheme;
  if (!themeToggle) return;
  const isLight = nextTheme === "light";
  themeToggle.setAttribute("aria-pressed", String(isLight));
  themeToggle.setAttribute("aria-label", isLight ? "切换深色主题" : "切换浅色主题");
  if (themeIcon) themeIcon.textContent = isLight ? "☀" : "☾";
  if (themeLabel) themeLabel.textContent = isLight ? "深色" : "浅色";
}

function toggleTheme() {
  const nextTheme = document.documentElement.dataset.theme === "light" ? "dark" : "light";
  localStorage.setItem(themeStorageKey, nextTheme);
  applyTheme(nextTheme);
}

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

function escapeAttr(value) {
  return String(value).replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");
}

function rate(numerator, denominator) {
  return denominator ? numerator / denominator : 0;
}

function sortDirection(current, key) {
  if (current.key !== key) return "desc";
  return current.direction === "desc" ? "asc" : "desc";
}

function numericValue(row, key) {
  if (key === "score") return row.score ?? -1;
  if (key === "poor_rate") return rate(row.poor_prs, row.rated_prs);
  if (key === "excellent_rate") return rate(row.excellent_prs, row.rated_prs);
  if (key === "scored_poor_rate") return rate(row.scored_poor, row.scored_prs);
  if (key === "scored_excellent_rate") return rate(row.scored_excellent, row.scored_prs);
  return Number(row[key] ?? 0);
}

function sortRows(rows, sortState) {
  const direction = sortState.direction === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => {
    const delta = numericValue(a, sortState.key) - numericValue(b, sortState.key);
    if (delta !== 0) return delta * direction;
    return String(a.title || a.name || a.id).localeCompare(String(b.title || b.name || b.id), "zh-CN");
  });
}

function prioritizeReviewDetails(details) {
  return [...details].sort((a, b) => {
    const aRank = a.type === "MR评价" ? 0 : 1;
    const bRank = b.type === "MR评价" ? 0 : 1;
    return aRank - bRank;
  });
}

function updateSortMarks() {
  document.querySelectorAll(".sort-button").forEach((button) => {
    const table = button.dataset.table;
    const state = table === "contributor" ? contributorSort : prSort;
    const active = button.dataset.sort === state.key;
    button.classList.toggle("active", active);
    const mark = button.querySelector(".sort-mark");
    mark.textContent = active ? (state.direction === "asc" ? "↑" : "↓") : "↕";
    button.title = active ? `当前${state.direction === "asc" ? "升序" : "降序"}，点击切换` : "点击排序";
  });
}

async function loadDashboard() {
  const params = new URLSearchParams({
    period: periodSelect.value,
    range: rangeSelect.value || "",
  });
  const controller = new AbortController();
  const timeout = window.setTimeout(() => controller.abort(), 1500);
  try {
    const response = await fetch(`/api/dashboard?${params.toString()}`, { signal: controller.signal });
    if (!response.ok) {
      const text = await response.text();
      throw new Error(text);
    }
    dashboard = await response.json();
  } catch (error) {
    dashboard = await loadStaticDashboard();
  } finally {
    window.clearTimeout(timeout);
  }
  ranges = dashboard.ranges || fallbackRanges;
  populateRanges(true);
  if (!selectedPrId && dashboard.prs?.length) selectedPrId = dashboard.prs[0].id;
  renderAll();
}

async function loadStaticDashboard() {
  if (!staticBundle) {
    const response = await fetch(`./dashboard-static.json?v=${encodeURIComponent(assetVersion)}`);
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
  const rows = sortRows((dashboard?.prs || []).filter(matchesSearch), prSort);
  prBody.innerHTML = "";

  for (const row of rows) {
    prBody.appendChild(createPrMainRow(row, selectedPrId, (id) => {
      selectedPrId = selectedPrId === id ? null : id;
      renderPrTable();
    }));

    if (row.id === selectedPrId) {
      prBody.appendChild(createPrDetailRow(row));
    }
  }

  if (!rows.length) {
    prBody.innerHTML = `<tr><td colspan="9" class="title-cell">当前筛选条件下暂无 PR 数据。</td></tr>`;
  }
}

function createPrMainRow(row, selectedId, onSelect) {
  const [label, cls] = level(row.score);
    const tr = document.createElement("tr");
  tr.className = row.id === selectedId ? "selected" : "";
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
    onSelect(row.id);
    });
  return tr;
}

function createPrDetailRow(row) {
      const detailRow = document.createElement("tr");
      detailRow.className = "pr-detail-row";
      detailRow.innerHTML = `<td colspan="9">${renderPrDetail(row)}</td>`;
  return detailRow;
}

function renderPrDetail(row) {
  const [label, cls] = level(row.score);
  const details = prioritizeReviewDetails(row.detail || []);
  return `
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
  const rows = sortRows((dashboard?.contributors || []).filter(matchesSearch), contributorSort);
  contributorBody.innerHTML = "";

  for (const row of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.name}</td>
      <td class="submit-metric">${metricLink(row, "submit_prs", formatNumber(row.submit_prs))}</td>
      <td class="submit-metric">${metricLink(row, "submit_lines", formatNumber(row.submit_lines))}</td>
      <td class="submit-metric">${metricLink(row, "received_reviews", formatNumber(row.received_reviews))}</td>
      <td class="submit-metric">${metricLink(row, "rated_prs", formatNumber(row.rated_prs))}</td>
      <td class="submit-metric negative">${metricLink(row, "poor_prs", formatNumber(row.poor_prs))}</td>
      <td class="submit-metric">${metricLink(row, "poor_rate", percent(row.poor_prs, row.rated_prs))}</td>
      <td class="submit-metric positive">${metricLink(row, "excellent_prs", formatNumber(row.excellent_prs))}</td>
      <td class="submit-metric">${metricLink(row, "excellent_rate", percent(row.excellent_prs, row.rated_prs))}</td>
      <td class="review-metric review-start">${metricLink(row, "review_comments", formatNumber(row.review_comments))}</td>
      <td class="review-metric">${metricLink(row, "review_prs", formatNumber(row.review_prs))}</td>
      <td class="review-metric">${metricLink(row, "scored_prs", formatNumber(row.scored_prs))}</td>
      <td class="review-metric negative">${metricLink(row, "scored_poor", formatNumber(row.scored_poor))}</td>
      <td class="review-metric">${metricLink(row, "scored_poor_rate", percent(row.scored_poor, row.scored_prs))}</td>
      <td class="review-metric positive">${metricLink(row, "scored_excellent", formatNumber(row.scored_excellent))}</td>
      <td class="review-metric">${metricLink(row, "scored_excellent_rate", percent(row.scored_excellent, row.scored_prs))}</td>
    `;
    contributorBody.appendChild(tr);
  }

  if (!rows.length) {
    contributorBody.innerHTML = `<tr><td colspan="16">当前筛选条件下暂无贡献者数据。</td></tr>`;
  }
}

function metricLink(row, metric, label) {
  return `<button class="metric-link" type="button" data-contributor="${escapeAttr(row.name)}" data-metric="${metric}">${label}</button>`;
}

function prHasReviewFrom(pr, contributor) {
  return (pr.detail || []).some((item) => item.type === "检视意见" && item.author === contributor);
}

function prHasScoreFrom(pr, contributor) {
  return pr.reviewer === contributor && pr.score !== null && pr.score !== undefined;
}

function metricTitle(metric) {
  return {
    submit_prs: "提交 PR",
    submit_lines: "提交代码行数",
    received_reviews: "被检视意见",
    rated_prs: "已评分 PR",
    poor_prs: "待改进 PR",
    poor_rate: "待改进占比",
    excellent_prs: "优秀 PR",
    excellent_rate: "优秀占比",
    review_comments: "提交检视意见",
    review_prs: "检视涉及 PR",
    scored_prs: "打分 PR",
    scored_poor: "打分待改进",
    scored_poor_rate: "打分待改进占比",
    scored_excellent: "打分优秀",
    scored_excellent_rate: "打分优秀占比",
  }[metric] || metric;
}

function filterPrsForMetric(contributor, metric) {
  const prs = dashboard?.prs || [];
  const ownPr = (pr) => pr.author === contributor;
  const rated = (pr) => pr.score !== null && pr.score !== undefined;
  const poor = (pr) => rated(pr) && pr.score < 3;
  const excellent = (pr) => rated(pr) && pr.score > 3;

  if (["submit_prs", "submit_lines", "received_reviews"].includes(metric)) {
    return prs.filter(ownPr);
  }
  if (metric === "rated_prs") return prs.filter((pr) => ownPr(pr) && rated(pr));
  if (["poor_prs", "poor_rate"].includes(metric)) return prs.filter((pr) => ownPr(pr) && poor(pr));
  if (["excellent_prs", "excellent_rate"].includes(metric)) {
    return prs.filter((pr) => ownPr(pr) && excellent(pr));
  }
  if (["review_comments", "review_prs"].includes(metric)) {
    return prs.filter((pr) => prHasReviewFrom(pr, contributor));
  }
  if (metric === "scored_prs") return prs.filter((pr) => prHasScoreFrom(pr, contributor));
  if (["scored_poor", "scored_poor_rate"].includes(metric)) {
    return prs.filter((pr) => prHasScoreFrom(pr, contributor) && poor(pr));
  }
  if (["scored_excellent", "scored_excellent_rate"].includes(metric)) {
    return prs.filter((pr) => prHasScoreFrom(pr, contributor) && excellent(pr));
  }
  return [];
}

function openDrilldown(contributor, metric) {
  const rows = sortRows(filterPrsForMetric(contributor, metric), prSort);
  activeDrilldownRows = rows;
  selectedDrilldownPrId = rows[0]?.id || null;
  drilldownKicker.textContent = `${contributor} · ${dashboard?.range || ""}`;
  drilldownTitle.textContent = metricTitle(metric);
  drilldownSummary.textContent = `${rows.length} 个相关 PR`;
  renderDrilldownRows(rows);
  drilldownModal.hidden = false;
}

function renderDrilldownRows(rows) {
  drilldownBody.innerHTML = "";
  const sortedRows = sortRows(rows, prSort);
  activeDrilldownRows = sortedRows;
  for (const row of sortedRows) {
    drilldownBody.appendChild(createPrMainRow(row, selectedDrilldownPrId, (id) => {
      selectedDrilldownPrId = selectedDrilldownPrId === id ? null : id;
      renderDrilldownRows(sortedRows);
    }));
    if (row.id === selectedDrilldownPrId) {
      drilldownBody.appendChild(createPrDetailRow(row));
    }
  }
  if (!rows.length) {
    drilldownBody.innerHTML = `<tr><td colspan="9" class="title-cell">当前指标没有可展示的 PR 明细。</td></tr>`;
  }
}

function closeDrilldown() {
  drilldownModal.hidden = true;
  selectedDrilldownPrId = null;
  activeDrilldownRows = [];
}

function renderAll() {
  renderMetrics();
  renderPrTable();
  renderContributorTable();
  updateSortMarks();
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
document.addEventListener("click", (event) => {
  const button = event.target.closest(".sort-button");
  if (!button) return;
  event.stopPropagation();
  if (button.dataset.table === "contributor") {
    contributorSort = {
      key: button.dataset.sort,
      direction: sortDirection(contributorSort, button.dataset.sort),
    };
    renderContributorTable();
  } else {
    prSort = {
      key: button.dataset.sort,
      direction: sortDirection(prSort, button.dataset.sort),
    };
    renderPrTable();
    if (!drilldownModal.hidden) renderDrilldownRows(activeDrilldownRows);
  }
  updateSortMarks();
});
contributorBody.addEventListener("click", (event) => {
  const button = event.target.closest(".metric-link");
  if (!button) return;
  event.stopPropagation();
  openDrilldown(button.dataset.contributor, button.dataset.metric);
});
drilldownClose.addEventListener("click", closeDrilldown);
drilldownModal.addEventListener("click", (event) => {
  if (event.target === drilldownModal) closeDrilldown();
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !drilldownModal.hidden) closeDrilldown();
});
themeToggle?.addEventListener("click", toggleTheme);

applyTheme(preferredTheme());
populateRanges(false);
loadDashboard().catch((error) => {
  console.error(error);
  document.querySelector(".content").insertAdjacentHTML(
    "afterbegin",
    `<div class="table-card" style="padding:16px;margin-bottom:16px;color:#ffabab">数据加载失败：${error.message}</div>`,
  );
});
