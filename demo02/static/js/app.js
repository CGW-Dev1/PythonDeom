const state = {
  categories: [],
  activeCategoryId: null,
  items: [],
  config: null,
  metrics: null,
};

const dom = {
  adminToggle: document.getElementById("adminToggle"),
  adminPanel: document.getElementById("adminPanel"),
  categoryTabs: document.getElementById("categoryTabs"),
  categorySummary: document.getElementById("categorySummary"),
  activeCategoryTitle: document.getElementById("activeCategoryTitle"),
  activeCategoryMeta: document.getElementById("activeCategoryMeta"),
  urlInput: document.getElementById("urlInput"),
  collectBtn: document.getElementById("collectBtn"),
  refreshBtn: document.getElementById("refreshBtn"),
  clearBtn: document.getElementById("clearBtn"),
  statusBox: document.getElementById("statusBox"),
  resultBody: document.getElementById("resultBody"),
  resultCount: document.getElementById("resultCount"),
  newCategoryName: document.getElementById("newCategoryName"),
  addCategoryBtn: document.getElementById("addCategoryBtn"),
  categoryAdminList: document.getElementById("categoryAdminList"),
  timeoutInput: document.getElementById("timeoutInput"),
  batchInput: document.getElementById("batchInput"),
  platformSwitches: document.getElementById("platformSwitches"),
  saveConfigBtn: document.getElementById("saveConfigBtn"),
  metricsBar: document.getElementById("metricsBar"),
  logList: document.getElementById("logList"),
};

function refreshIcons() {
  if (window.lucide) {
    window.lucide.createIcons();
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const data = await response.json();
  if (!response.ok || !data.ok) {
    throw new Error(data.message || "请求失败");
  }
  return data;
}

function setStatus(message, type = "") {
  dom.statusBox.textContent = message || "";
  dom.statusBox.className = `status-box ${type}`.trim();
}

function setBusy(button, busy) {
  button.disabled = busy;
  button.dataset.originalText = button.dataset.originalText || button.textContent.trim();
  if (busy) {
    button.classList.add("is-busy");
  } else {
    button.classList.remove("is-busy");
  }
}

function activeCategory() {
  return state.categories.find((category) => category.id === state.activeCategoryId) || null;
}

async function loadCategories() {
  const data = await api("/api/categories");
  state.categories = data.categories;
  if (!state.activeCategoryId || !state.categories.some((item) => item.id === state.activeCategoryId)) {
    state.activeCategoryId = state.categories[0]?.id || null;
  }
}

async function loadItems() {
  if (!state.activeCategoryId) {
    state.items = [];
    return;
  }
  const data = await api(`/api/categories/${state.activeCategoryId}/items`);
  state.items = data.items;
}

async function loadConfig() {
  const data = await api("/api/config");
  state.config = data.config;
}

async function loadMetrics() {
  const data = await api("/api/metrics");
  state.metrics = data.metrics;
}

async function refreshAll() {
  await loadCategories();
  await loadItems();
  await loadConfig();
  await loadMetrics();
  render();
}

function render() {
  renderCategories();
  renderWorkspace();
  renderAdmin();
  renderMetrics();
  refreshIcons();
}

function renderCategories() {
  dom.categoryTabs.textContent = "";
  dom.categorySummary.textContent = `${state.categories.length} 个分类`;

  if (!state.categories.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "暂无分类";
    dom.categoryTabs.appendChild(empty);
    return;
  }

  state.categories.forEach((category) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `category-tab icon-btn ${category.id === state.activeCategoryId ? "active" : ""}`;
    button.addEventListener("click", async () => {
      state.activeCategoryId = category.id;
      setStatus("");
      await loadItems();
      render();
    });

    const name = document.createElement("span");
    name.textContent = category.name;
    const count = document.createElement("span");
    count.className = "count";
    count.textContent = category.count;

    button.append(name, count);
    dom.categoryTabs.appendChild(button);
  });
}

function renderWorkspace() {
  const category = activeCategory();
  dom.activeCategoryTitle.textContent = category ? `${category.name}比价区` : "比价区";
  dom.activeCategoryMeta.textContent = category ? "当前分类数据独立展示" : "请选择分类";
  dom.collectBtn.disabled = !category;
  dom.refreshBtn.disabled = !category || state.items.length === 0;
  dom.clearBtn.disabled = !category || state.items.length === 0;
  renderResults();
}

function renderResults() {
  dom.resultBody.textContent = "";
  dom.resultCount.textContent = `${state.items.length} 条记录`;

  if (!state.items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.className = "empty-state";
    cell.textContent = "当前分类暂无比价记录";
    row.appendChild(cell);
    dom.resultBody.appendChild(row);
    return;
  }

  state.items.forEach((item, index) => {
    const row = document.createElement("tr");

    const rankCell = document.createElement("td");
    const rankBadge = document.createElement("span");
    rankBadge.className = `rank-badge ${index === 0 ? "top" : ""}`;
    rankBadge.textContent = String(index + 1);
    rankCell.appendChild(rankBadge);

    const priceCell = document.createElement("td");
    priceCell.className = `price-cell ${index === 0 ? "lowest" : ""}`;
    priceCell.textContent = `¥${item.price_display}`;

    const platformCell = document.createElement("td");
    platformCell.textContent = item.platform;

    const urlCell = document.createElement("td");
    const link = document.createElement("a");
    link.href = item.url;
    link.target = "_blank";
    link.rel = "noreferrer";
    link.className = "product-link";
    link.textContent = item.url;
    urlCell.appendChild(link);
    if (item.title) {
      const title = document.createElement("div");
      title.className = "product-title";
      title.textContent = item.title;
      urlCell.appendChild(title);
    }

    const timeCell = document.createElement("td");
    timeCell.textContent = item.collected_at;

    const statusCell = document.createElement("td");
    statusCell.textContent = item.last_error ? item.last_error : "采集完成";
    statusCell.className = item.last_error ? "text-danger" : "text-success";

    row.append(rankCell, priceCell, platformCell, urlCell, timeCell, statusCell);
    dom.resultBody.appendChild(row);
  });
}

function renderAdmin() {
  dom.categoryAdminList.textContent = "";
  state.categories.forEach((category) => {
    const row = document.createElement("div");
    row.className = "admin-row";

    const name = document.createElement("strong");
    name.textContent = `${category.name}（${category.count}）`;

    const actions = document.createElement("div");
    actions.className = "btn-group btn-group-sm";

    const editBtn = document.createElement("button");
    editBtn.className = "btn btn-outline-primary";
    editBtn.type = "button";
    editBtn.textContent = "编辑";
    editBtn.addEventListener("click", () => editCategory(category));

    const deleteBtn = document.createElement("button");
    deleteBtn.className = "btn btn-outline-danger";
    deleteBtn.type = "button";
    deleteBtn.textContent = "删除";
    deleteBtn.addEventListener("click", () => deleteCategory(category));

    actions.append(editBtn, deleteBtn);
    row.append(name, actions);
    dom.categoryAdminList.appendChild(row);
  });

  if (state.config) {
    dom.timeoutInput.value = state.config.timeout_seconds;
    dom.batchInput.value = state.config.max_batch_size;
    dom.platformSwitches.textContent = "";

    Object.entries(state.config.enabled_platforms).forEach(([platform, enabled]) => {
      const id = `platform-${platform}`;
      const wrapper = document.createElement("label");
      wrapper.className = "form-check form-switch";

      const input = document.createElement("input");
      input.className = "form-check-input";
      input.type = "checkbox";
      input.id = id;
      input.checked = enabled;
      input.dataset.platform = platform;

      const label = document.createElement("span");
      label.className = "form-check-label";
      label.textContent = platform;

      wrapper.append(input, label);
      dom.platformSwitches.appendChild(wrapper);
    });
  }
}

function renderMetrics() {
  if (!state.metrics) {
    return;
  }

  const metricItems = [
    ["总采集", state.metrics.total],
    ["成功率", `${state.metrics.success_rate}%`],
    ["成功", state.metrics.success],
    ["平均耗时", `${state.metrics.avg_latency_ms}ms`],
  ];

  dom.metricsBar.textContent = "";
  metricItems.forEach(([label, value]) => {
    const box = document.createElement("div");
    box.className = "metric";
    const span = document.createElement("span");
    span.textContent = label;
    const strong = document.createElement("strong");
    strong.textContent = value;
    box.append(span, strong);
    dom.metricsBar.appendChild(box);
  });

  dom.logList.textContent = "";
  if (!state.metrics.logs.length) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.textContent = "暂无采集日志";
    dom.logList.appendChild(empty);
    return;
  }

  state.metrics.logs.slice(0, 12).forEach((log) => {
    const row = document.createElement("div");
    row.className = `log-row ${log.level === "成功" ? "success" : "failure"}`;
    const message = document.createElement("div");
    message.className = "log-message";

    const strong = document.createElement("strong");
    strong.textContent = `${log.level}：${log.message}`;

    const meta = document.createElement("div");
    meta.className = "log-meta";
    meta.textContent = `${log.time} · ${log.latency_ms}ms`;

    const url = document.createElement("div");
    url.className = "log-url";
    url.textContent = log.url || "";

    message.append(strong, meta, url);
    row.appendChild(message);
    dom.logList.appendChild(row);
  });
}

async function collectPrices() {
  const category = activeCategory();
  if (!category) {
    return;
  }

  const urls = dom.urlInput.value.trim();
  if (!urls) {
    setStatus("请先输入商品网址", "error");
    return;
  }

  setBusy(dom.collectBtn, true);
  setStatus("加载中，正在采集价格...");
  try {
    const data = await api(`/api/categories/${category.id}/collect`, {
      method: "POST",
      body: JSON.stringify({ urls }),
    });
    state.items = data.items;
    state.categories = data.categories;
    await loadMetrics();
    render();

    const failText = data.failures.length ? `，失败 ${data.failures.length} 个` : "";
    setStatus(`采集完成：成功 ${data.added.length} 个${failText}`, data.failures.length ? "error" : "success");
    if (data.added.length) {
      dom.urlInput.value = "";
    }
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(dom.collectBtn, false);
  }
}

async function refreshPrices() {
  const category = activeCategory();
  if (!category) {
    return;
  }

  setBusy(dom.refreshBtn, true);
  setStatus("加载中，正在刷新当前分类价格...");
  try {
    const data = await api(`/api/categories/${category.id}/refresh`, { method: "POST" });
    state.items = data.items;
    await loadMetrics();
    render();
    const failText = data.failures.length ? `，失败 ${data.failures.length} 个` : "";
    setStatus(`刷新完成：更新 ${data.updated.length} 个${failText}`, data.failures.length ? "error" : "success");
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    setBusy(dom.refreshBtn, false);
  }
}

async function clearItems() {
  const category = activeCategory();
  if (!category) {
    return;
  }
  if (!window.confirm(`清空「${category.name}」下的所有采集记录？`)) {
    return;
  }

  setStatus("正在清空记录...");
  try {
    const data = await api(`/api/categories/${category.id}/items`, { method: "DELETE" });
    state.items = data.items;
    state.categories = data.categories;
    render();
    setStatus(`已清空 ${data.cleared} 条记录`, "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function addCategory() {
  const name = dom.newCategoryName.value.trim();
  if (!name) {
    setStatus("分类名称不能为空", "error");
    return;
  }

  try {
    const data = await api("/api/categories", {
      method: "POST",
      body: JSON.stringify({ name }),
    });
    state.categories = data.categories;
    state.activeCategoryId = data.category.id;
    dom.newCategoryName.value = "";
    await loadItems();
    render();
    setStatus("分类新增成功", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function editCategory(category) {
  const name = window.prompt("请输入新的分类名称", category.name);
  if (name === null) {
    return;
  }

  try {
    const data = await api(`/api/categories/${category.id}`, {
      method: "PUT",
      body: JSON.stringify({ name }),
    });
    state.categories = data.categories;
    render();
    setStatus("分类更新成功", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function deleteCategory(category) {
  if (!window.confirm(`删除分类「${category.name}」？该分类下的当前记录也会清空。`)) {
    return;
  }

  try {
    const data = await api(`/api/categories/${category.id}`, { method: "DELETE" });
    state.categories = data.categories;
    if (state.activeCategoryId === category.id) {
      state.activeCategoryId = state.categories[0]?.id || null;
    }
    await loadItems();
    render();
    setStatus("分类删除成功", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function saveConfig() {
  const enabledPlatforms = {};
  dom.platformSwitches.querySelectorAll("input[type='checkbox']").forEach((input) => {
    enabledPlatforms[input.dataset.platform] = input.checked;
  });

  try {
    const data = await api("/api/config", {
      method: "PUT",
      body: JSON.stringify({
        timeout_seconds: Number(dom.timeoutInput.value),
        max_batch_size: Number(dom.batchInput.value),
        enabled_platforms: enabledPlatforms,
      }),
    });
    state.config = data.config;
    render();
    setStatus("爬虫配置已保存", "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

dom.adminToggle.addEventListener("click", () => {
  dom.adminPanel.classList.toggle("d-none");
});
dom.collectBtn.addEventListener("click", collectPrices);
dom.refreshBtn.addEventListener("click", refreshPrices);
dom.clearBtn.addEventListener("click", clearItems);
dom.addCategoryBtn.addEventListener("click", addCategory);
dom.saveConfigBtn.addEventListener("click", saveConfig);
dom.newCategoryName.addEventListener("keydown", (event) => {
  if (event.key === "Enter") {
    addCategory();
  }
});

refreshAll().catch((error) => {
  setStatus(error.message, "error");
  refreshIcons();
});
