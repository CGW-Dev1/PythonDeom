function byId(id) {
    return document.getElementById(id);
}

async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.ok === false) {
        throw new Error(data.message || `HTTP ${response.status}`);
    }
    return data;
}

function showResult(id, message) {
    byId(id).textContent = message;
}

async function loadSources() {
    const rows = await fetchJson("/api/data-sources");
    byId("sourceBody").innerHTML = rows
        .map(
            (row) => `
            <tr>
                <td>${row.name}</td>
                <td>${row.source_type}</td>
                <td title="${row.url || ""}">${row.url || ""}</td>
                <td title="${row.compliance_note || ""}">${row.compliance_note || ""}</td>
                <td><button class="ghost-button small" data-delete-source="${row.id}">删除</button></td>
            </tr>
        `
        )
        .join("");
}

async function loadLogs() {
    const data = await fetchJson("/api/logs");
    byId("importLogs").innerHTML = data.import_logs
        .map(
            (row) => `
            <div class="log-item">
                <strong>${row.source_name || "未知来源"} · ${row.status}</strong><br>
                总数 ${row.rows_total}，新增 ${row.rows_inserted}，更新 ${row.rows_updated}，异常 ${row.rows_error}<br>
                ${row.message || ""}<br>${row.finished_at || row.started_at}
            </div>
        `
        )
        .join("");
    byId("operationLogs").innerHTML = data.operation_logs
        .map(
            (row) => `
            <div class="log-item">
                <strong>${row.username || "system"} · ${row.action}</strong><br>
                ${row.detail || ""}<br>${row.created_at}
            </div>
        `
        )
        .join("");
}

async function loadAdminListings() {
    const params = new URLSearchParams();
    const keyword = byId("adminKeyword").value.trim();
    if (keyword) params.set("keyword", keyword);
    params.set("page_size", 20);
    const data = await fetchJson(`/api/listings?${params.toString()}`);
    byId("adminListingBody").innerHTML = data.items
        .map(
            (row) => `
            <tr data-id="${row.id}">
                <td>${row.city}</td>
                <td>${row.district}</td>
                <td title="${row.community}">${row.community}</td>
                <td>${row.layout || ""}</td>
                <td><input class="mini-input" data-field="list_total_price" type="number" value="${Number(row.list_total_price || 0).toFixed(1)}"></td>
                <td>
                    <select class="mini-input" data-field="status">
                        ${["在售", "已成交", "下架", "暂停"].map((status) => `<option value="${status}" ${status === row.status ? "selected" : ""}>${status}</option>`).join("")}
                    </select>
                </td>
                <td>
                    <button class="ghost-button small" data-save="${row.id}">保存</button>
                    <button class="ghost-button small" data-delete="${row.id}">删除</button>
                </td>
            </tr>
        `
        )
        .join("");
}

function bindForms() {
    byId("importForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        showResult("importResult", "正在导入...");
        try {
            const data = await fetchJson("/api/import", { method: "POST", body: new FormData(event.target) });
            showResult("importResult", `导入完成：新增 ${data.rows_inserted}，更新 ${data.rows_updated}，异常 ${data.rows_error}`);
            event.target.reset();
            await Promise.all([loadLogs(), loadAdminListings()]);
        } catch (error) {
            showResult("importResult", `导入失败：${error.message}`);
        }
    });

    byId("seedForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = new FormData(event.target);
        try {
            const data = await fetchJson("/api/seed-demo", { method: "POST", body: formData });
            showResult("importResult", data.message);
            await Promise.all([loadLogs(), loadAdminListings()]);
        } catch (error) {
            showResult("importResult", `生成失败：${error.message}`);
        }
    });

    byId("sourceForm").addEventListener("submit", async (event) => {
        event.preventDefault();
        const formData = new FormData(event.target);
        const payload = Object.fromEntries(formData.entries());
        try {
            await fetchJson("/api/data-sources", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            event.target.reset();
            await loadSources();
        } catch (error) {
            alert(error.message);
        }
    });

    byId("adminSearch").addEventListener("click", loadAdminListings);
    byId("adminKeyword").addEventListener("keydown", (event) => {
        if (event.key === "Enter") loadAdminListings();
    });
}

function bindTableActions() {
    document.addEventListener("click", async (event) => {
        const deleteSource = event.target.dataset.deleteSource;
        if (deleteSource) {
            if (!confirm("确认删除该数据源配置？")) return;
            await fetchJson(`/api/data-sources/${deleteSource}`, { method: "DELETE" });
            await loadSources();
            return;
        }

        const deleteId = event.target.dataset.delete;
        if (deleteId) {
            if (!confirm("确认删除该房源？")) return;
            await fetchJson(`/api/listings/${deleteId}`, { method: "DELETE" });
            await loadAdminListings();
            await loadLogs();
            return;
        }

        const saveId = event.target.dataset.save;
        if (saveId) {
            const row = event.target.closest("tr");
            const payload = {};
            row.querySelectorAll("[data-field]").forEach((field) => {
                payload[field.dataset.field] = field.value;
            });
            await fetchJson(`/api/listings/${saveId}`, {
                method: "PATCH",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            });
            event.target.textContent = "已保存";
            setTimeout(() => {
                event.target.textContent = "保存";
            }, 1200);
            await loadLogs();
        }
    });
}

async function bootstrap() {
    bindForms();
    bindTableActions();
    await Promise.all([loadSources(), loadLogs(), loadAdminListings()]);
}

bootstrap().catch((error) => {
    console.error(error);
    alert(`后台加载失败：${error.message}`);
});
