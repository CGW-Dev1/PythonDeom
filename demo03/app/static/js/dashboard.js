const state = {
    page: 1,
    pageSize: 12,
    total: 0,
    options: null,
    charts: {},
};

const chartColors = ["#34d0b6", "#e7b957", "#ef6f83", "#9bd46a", "#72a7ff", "#d28cff", "#ff9d61"];

function byId(id) {
    return document.getElementById(id);
}

function money(value) {
    const number = Number(value || 0);
    if (number >= 10000) {
        return `${(number / 10000).toFixed(1)}万`;
    }
    return number.toLocaleString("zh-CN");
}

function percent(value) {
    const number = Number(value || 0);
    return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }
    return response.json();
}

function currentFilters() {
    const params = new URLSearchParams();
    const mappings = [
        ["city", "cityFilter"],
        ["district", "districtFilter"],
        ["layout", "layoutFilter"],
        ["status", "statusFilter"],
        ["price_min", "priceMin"],
        ["price_max", "priceMax"],
        ["area_min", "areaMin"],
        ["area_max", "areaMax"],
        ["start_date", "startDate"],
        ["end_date", "endDate"],
        ["keyword", "keywordFilter"],
    ];
    mappings.forEach(([key, id]) => {
        const value = byId(id)?.value?.trim();
        if (value) {
            params.set(key, value);
        }
    });
    return params;
}

function chart(id) {
    if (!state.charts[id]) {
        state.charts[id] = echarts.init(byId(id), null, { renderer: "canvas" });
    }
    return state.charts[id];
}

function setSelectOptions(select, items, labelKey, valueKey, placeholder) {
    const selected = select.value;
    select.innerHTML = `<option value="">${placeholder}</option>`;
    items.forEach((item) => {
        const option = document.createElement("option");
        option.value = valueKey ? item[valueKey] : item;
        option.textContent = labelKey ? item[labelKey] : item;
        select.appendChild(option);
    });
    if ([...select.options].some((option) => option.value === selected)) {
        select.value = selected;
    }
}

async function loadOptions() {
    state.options = await fetchJson("/api/options");
    setSelectOptions(byId("cityFilter"), state.options.cities, null, null, "全部城市");
    setSelectOptions(byId("layoutFilter"), state.options.layouts, null, null, "全部户型");
    setSelectOptions(byId("statusFilter"), state.options.statuses, null, null, "全部状态");
    updateDistrictOptions();
}

function updateDistrictOptions() {
    const city = byId("cityFilter").value;
    const districts = (state.options?.districts || []).filter((item) => !city || item.city === city);
    setSelectOptions(byId("districtFilter"), districts, "district", "district", "全部区域");
}

function renderMetrics(metrics) {
    const cards = [
        ["总房源量", metrics.total_listings, "套", ""],
        ["有效在售", metrics.active_listings, "套", ""],
        ["挂牌均价", money(metrics.avg_list_unit_price), "元/㎡", ""],
        ["成交均价", money(metrics.avg_deal_unit_price), "元/㎡", ""],
        ["近7天成交", metrics.deals_7d, "套", ""],
        ["近30天成交", metrics.deals_30d, "套", ""],
        ["成交周期均值", metrics.avg_transaction_cycle, "天", ""],
        ["市场热度指数", metrics.market_heat, "/100", `环比 <b class="${metrics.mom_trend}">${percent(metrics.avg_mom)}</b> · 同比 <b class="${metrics.yoy_trend}">${percent(metrics.avg_yoy)}</b>`],
    ];
    byId("metricsGrid").innerHTML = cards
        .map(([label, value, unit, sub]) => `
            <article class="metric-card">
                <span>${label}</span>
                <strong>${value}</strong>
                <em>${unit}${sub ? ` · ${sub}` : ""}</em>
            </article>
        `)
        .join("");
}

function renderDistrictChart(rows) {
    const data = rows.slice(0, 36).map((row) => ({
        name: row.name,
        city: row.city,
        district: row.district,
        value: [row.avg_price, row.listings, row.deals, row.active],
        symbolSize: Math.max(12, Math.min(54, Math.sqrt(row.listings) * 5)),
    }));
    const option = {
        color: chartColors,
        tooltip: {
            trigger: "item",
            formatter: (p) => {
                const d = p.data;
                return `${d.name}<br>挂牌均价：${money(d.value[0])} 元/㎡<br>房源：${d.value[1]} 套<br>成交：${d.value[2]} 套`;
            },
        },
        grid: { left: 64, right: 26, top: 34, bottom: 48 },
        xAxis: {
            name: "挂牌均价",
            axisLabel: { color: "#aaa797", formatter: (v) => `${Math.round(v / 10000)}万` },
            splitLine: { lineStyle: { color: "rgba(238,234,219,.08)" } },
        },
        yAxis: {
            name: "房源量",
            axisLabel: { color: "#aaa797" },
            splitLine: { lineStyle: { color: "rgba(238,234,219,.08)" } },
        },
        series: [
            {
                type: "scatter",
                data,
                encode: { x: 0, y: 1 },
                itemStyle: { opacity: 0.82 },
            },
        ],
    };
    const instance = chart("districtChart");
    instance.setOption(option, true);
    instance.off("click");
    instance.on("click", (params) => {
        if (!params.data) return;
        byId("cityFilter").value = params.data.city;
        updateDistrictOptions();
        byId("districtFilter").value = params.data.district;
        state.page = 1;
        refreshAll();
    });
}

function renderPie(id, rows, title) {
    chart(id).setOption(
        {
            color: chartColors,
            tooltip: { trigger: "item" },
            legend: { bottom: 8, textStyle: { color: "#aaa797" }, type: "scroll" },
            series: [
                {
                    name: title,
                    type: "pie",
                    radius: ["46%", "70%"],
                    center: ["50%", "43%"],
                    data: rows.map((row) => ({ name: row.name, value: row.value })),
                    label: { color: "#f4f1e8", formatter: "{b}\n{d}%" },
                },
            ],
        },
        true
    );
}

function renderBar(id, rows, valueName) {
    chart(id).setOption(
        {
            color: [chartColors[0]],
            tooltip: { trigger: "axis" },
            grid: { left: 42, right: 18, top: 26, bottom: 62 },
            xAxis: {
                type: "category",
                data: rows.map((row) => row.name),
                axisLabel: { color: "#aaa797", interval: 0, rotate: 25 },
            },
            yAxis: {
                type: "value",
                axisLabel: { color: "#aaa797" },
                splitLine: { lineStyle: { color: "rgba(238,234,219,.08)" } },
            },
            series: [{ name: valueName, type: "bar", data: rows.map((row) => row.value), barMaxWidth: 34 }],
        },
        true
    );
}

function renderPriceTrend(trend) {
    chart("priceTrendChart").setOption(
        {
            color: [chartColors[0], chartColors[2], chartColors[1]],
            tooltip: { trigger: "axis" },
            legend: { top: 8, textStyle: { color: "#aaa797" } },
            grid: { left: 56, right: 28, top: 48, bottom: 42 },
            xAxis: { type: "category", data: trend.months, axisLabel: { color: "#aaa797" } },
            yAxis: {
                type: "value",
                axisLabel: { color: "#aaa797", formatter: (v) => `${Math.round(v / 10000)}万` },
                splitLine: { lineStyle: { color: "rgba(238,234,219,.08)" } },
            },
            series: [
                { name: "挂牌均价", type: "line", smooth: true, data: trend.list_avg, connectNulls: true },
                { name: "成交均价", type: "line", smooth: true, data: trend.deal_avg, connectNulls: true },
                { name: "调价幅度", type: "line", smooth: true, data: trend.adjust_amount, yAxisIndex: 0 },
            ],
        },
        true
    );
}

function renderSupplyTrend(trend) {
    chart("supplyTrendChart").setOption(
        {
            color: [chartColors[4], chartColors[1], chartColors[2]],
            tooltip: { trigger: "axis" },
            legend: { top: 8, textStyle: { color: "#aaa797" } },
            grid: { left: 46, right: 28, top: 48, bottom: 42 },
            xAxis: { type: "category", data: trend.months, axisLabel: { color: "#aaa797" } },
            yAxis: {
                type: "value",
                axisLabel: { color: "#aaa797" },
                splitLine: { lineStyle: { color: "rgba(238,234,219,.08)" } },
            },
            series: [
                { name: "新增供应", type: "bar", data: trend.supply, barMaxWidth: 18 },
                { name: "成交量", type: "bar", data: trend.deals, barMaxWidth: 18 },
                { name: "调价次数", type: "line", smooth: true, data: trend.adjust_count },
            ],
        },
        true
    );
}

function renderSupport(rows) {
    chart("supportChart").setOption(
        {
            color: [chartColors[3], chartColors[2]],
            tooltip: { trigger: "axis" },
            grid: { left: 52, right: 18, top: 30, bottom: 46 },
            xAxis: { type: "category", data: rows.map((row) => row.name), axisLabel: { color: "#aaa797" } },
            yAxis: {
                type: "value",
                axisLabel: { color: "#aaa797", formatter: "{value}%" },
                splitLine: { lineStyle: { color: "rgba(238,234,219,.08)" } },
            },
            series: [{ name: "溢价率", type: "bar", data: rows.map((row) => row.premium), barMaxWidth: 34 }],
        },
        true
    );
}

function renderFloor(data) {
    const rows = [
        ...(data.floor || []).map((row) => ({ ...row, group: "楼层" })),
        ...(data.orientation || []).map((row) => ({ ...row, group: "朝向" })),
    ];
    chart("floorChart").setOption(
        {
            color: [chartColors[5]],
            tooltip: { trigger: "axis" },
            grid: { left: 56, right: 18, top: 30, bottom: 62 },
            xAxis: {
                type: "category",
                data: rows.map((row) => row.name),
                axisLabel: { color: "#aaa797", interval: 0, rotate: 25 },
            },
            yAxis: {
                type: "value",
                axisLabel: { color: "#aaa797", formatter: (v) => `${Math.round(v / 10000)}万` },
                splitLine: { lineStyle: { color: "rgba(238,234,219,.08)" } },
            },
            series: [{ name: "挂牌均价", type: "bar", data: rows.map((row) => row.avg_price), barMaxWidth: 30 }],
        },
        true
    );
}

function renderHotCommunities(rows) {
    byId("hotCommunityBody").innerHTML = rows
        .map(
            (row) => `
            <tr>
                <td title="${row.community}">${row.community}</td>
                <td>${row.city}-${row.district}</td>
                <td>${money(row.avg_price)}</td>
                <td>${row.deals}</td>
                <td>${row.heat}</td>
            </tr>
        `
        )
        .join("");
}

function renderQuality(quality) {
    byId("qualityText").textContent = `缺失率 ${quality.missing_rate}% · 错误率 ${quality.error_rate}% · ${quality.total} 条`;
}

async function loadDashboard() {
    const params = currentFilters();
    const data = await fetchJson(`/api/dashboard?${params.toString()}`);
    renderMetrics(data.metrics);
    renderQuality(data.quality);
    renderDistrictChart(data.districts);
    renderPie("layoutChart", data.layout, "户型");
    renderBar("priceChart", data.price_ranges, "房源数量");
    renderBar("areaChart", data.area_ranges, "房源数量");
    renderBar("decorationChart", data.decoration, "房源数量");
    renderPriceTrend(data.trend);
    renderSupplyTrend(data.trend);
    renderSupport(data.support_value);
    renderFloor(data.floor_orientation);
    renderHotCommunities(data.hot_communities);
}

async function loadListings() {
    const params = currentFilters();
    params.set("page", state.page);
    params.set("page_size", state.pageSize);
    const data = await fetchJson(`/api/listings?${params.toString()}`);
    state.total = data.total;
    byId("listingBody").innerHTML = data.items
        .map(
            (row) => `
            <tr>
                <td>${row.city}</td>
                <td>${row.district}</td>
                <td title="${row.community}">${row.community}</td>
                <td>${row.layout || ""}</td>
                <td>${Number(row.area || 0).toFixed(1)}㎡</td>
                <td>${Number(row.list_total_price || 0).toFixed(1)}万</td>
                <td>${money(row.list_unit_price)}</td>
                <td>${row.status}</td>
                <td>${row.deal_date || row.listing_date || ""}</td>
            </tr>
        `
        )
        .join("");
    const pages = Math.max(1, Math.ceil(data.total / state.pageSize));
    byId("pageInfo").textContent = `${state.page} / ${pages} · ${data.total} 条`;
    byId("prevPage").disabled = state.page <= 1;
    byId("nextPage").disabled = state.page >= pages;
}

async function refreshAll() {
    await Promise.all([loadDashboard(), loadListings()]);
}

function exportUrl(format) {
    const params = currentFilters();
    params.set("format", format);
    return `/api/export/listings?${params.toString()}`;
}

function bindEvents() {
    byId("cityFilter").addEventListener("change", () => {
        updateDistrictOptions();
        byId("districtFilter").value = "";
    });
    byId("applyFilters").addEventListener("click", () => {
        state.page = 1;
        refreshAll();
    });
    byId("resetFilters").addEventListener("click", () => {
        document.querySelectorAll(".filter-strip input, .filter-strip select").forEach((el) => {
            el.value = "";
        });
        updateDistrictOptions();
        state.page = 1;
        refreshAll();
    });
    byId("refreshBtn").addEventListener("click", refreshAll);
    byId("prevPage").addEventListener("click", () => {
        if (state.page > 1) {
            state.page -= 1;
            loadListings();
        }
    });
    byId("nextPage").addEventListener("click", () => {
        const pages = Math.max(1, Math.ceil(state.total / state.pageSize));
        if (state.page < pages) {
            state.page += 1;
            loadListings();
        }
    });
    byId("exportCsv").addEventListener("click", () => {
        window.location.href = exportUrl("csv");
    });
    byId("exportExcel").addEventListener("click", () => {
        window.location.href = exportUrl("xlsx");
    });
    byId("fullscreenBtn").addEventListener("click", () => {
        if (!document.fullscreenElement) {
            document.documentElement.requestFullscreen();
        } else {
            document.exitFullscreen();
        }
    });
    window.addEventListener("resize", () => {
        Object.values(state.charts).forEach((item) => item.resize());
    });
}

async function bootstrap() {
    bindEvents();
    await loadOptions();
    await refreshAll();
    setInterval(refreshAll, 60 * 1000);
}

bootstrap().catch((error) => {
    console.error(error);
    byId("metricsGrid").innerHTML = `<div class="notice error">大屏数据加载失败：${error.message}</div>`;
});
