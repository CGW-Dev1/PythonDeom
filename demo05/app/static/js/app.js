const currencyFormatter = new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 0
});

function formatCurrency(value) {
    return `${currencyFormatter.format(Number(value || 0))} 元`;
}

function formatUnitPrice(value) {
    return `${Number(value || 0).toFixed(2)} 元/㎡`;
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, {
        headers: {"Content-Type": "application/json"},
        ...options
    });
    if (!response.ok) {
        throw new Error(`请求失败：${response.status}`);
    }
    return response.json();
}

function showDashboardMessage(message, type = "success") {
    const box = document.querySelector("#dashboardMessage");
    if (!box) return;
    box.textContent = message;
    box.className = `inline-message ${type === "error" ? "error" : ""}`;
    box.hidden = false;
}

function renderSummary(summary) {
    const map = {
        total: summary.total,
        district_count: summary.district_count,
        avg_rent: formatCurrency(summary.avg_rent),
        avg_unit_price: formatUnitPrice(summary.avg_unit_price)
    };
    Object.entries(map).forEach(([key, value]) => {
        const node = document.querySelector(`[data-stat="${key}"]`);
        if (node) node.textContent = value;
    });
}

function renderRows(targetSelector, rows, columns) {
    const body = document.querySelector(targetSelector);
    if (!body) return;
    if (!rows.length) {
        body.innerHTML = `<tr><td colspan="${columns.length}">暂无数据</td></tr>`;
        return;
    }
    body.innerHTML = rows.map(row => {
        const cells = columns.map(column => `<td>${column.render(row)}</td>`).join("");
        return `<tr>${cells}</tr>`;
    }).join("");
}

async function loadStats() {
    const payload = await requestJson("/api/stats");
    renderSummary(payload.summary);
    renderRows("#districtStatsBody", payload.district_avg, [
        {render: row => row.district},
        {render: row => formatCurrency(row.avg_rent)},
        {render: row => formatUnitPrice(row.avg_unit_price)},
        {render: row => row.count}
    ]);
    renderRows("#houseTypeStatsBody", payload.house_type_avg, [
        {render: row => row.house_type},
        {render: row => formatCurrency(row.avg_rent)},
        {render: row => row.count}
    ]);
}

async function loadCharts() {
    const charts = await requestJson("/api/charts");
    const cacheBust = Date.now();
    Object.entries(charts).forEach(([key, url]) => {
        const image = document.querySelector(`[data-chart="${key}"]`);
        if (image) image.src = `${url}?v=${cacheBust}`;
    });
}

async function refreshDashboard() {
    if (!document.querySelector("#metricGrid")) return;
    await loadStats();
    await loadCharts();
}

function bindDashboardActions() {
    const seedButton = document.querySelector("#seedDataBtn");
    const crawlButton = document.querySelector("#crawlBtn");

    if (seedButton) {
        seedButton.addEventListener("click", async () => {
            seedButton.disabled = true;
            showDashboardMessage("正在导入演示数据...");
            try {
                const result = await requestJson("/api/crawl", {
                    method: "POST",
                    body: JSON.stringify({platform: "sample"})
                });
                showDashboardMessage(`导入完成：新增 ${result.inserted} 条，跳过 ${result.skipped} 条。`);
                await refreshDashboard();
            } catch (error) {
                showDashboardMessage(error.message, "error");
            } finally {
                seedButton.disabled = false;
            }
        });
    }

    if (crawlButton) {
        crawlButton.addEventListener("click", async () => {
            crawlButton.disabled = true;
            showDashboardMessage("采集任务执行中，页面可能需要等待一会儿...");
            try {
                const result = await requestJson("/api/crawl", {
                    method: "POST",
                    body: JSON.stringify({
                        platform: document.querySelector("#platformSelect").value,
                        city: document.querySelector("#citySelect").value,
                        max_pages: document.querySelector("#maxPagesInput").value
                    })
                });
                const errorText = result.errors && result.errors.length ? `；错误：${result.errors.join("；")}` : "";
                showDashboardMessage(`采集完成：新增 ${result.inserted} 条，跳过 ${result.skipped} 条${errorText}`);
                await refreshDashboard();
            } catch (error) {
                showDashboardMessage(error.message, "error");
            } finally {
                crawlButton.disabled = false;
            }
        });
    }
}

document.addEventListener("DOMContentLoaded", () => {
    bindDashboardActions();
    refreshDashboard().catch(error => showDashboardMessage(error.message, "error"));
});
