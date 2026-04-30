let currentPage = 1;
let totalPages = 1;

async function loadOptions(endpoint, selector, defaultLabel) {
    const select = document.querySelector(selector);
    if (!select) return;
    const values = await requestJson(endpoint);
    select.innerHTML = `<option value="">${defaultLabel}</option>` + values
        .map(value => `<option value="${value}">${value}</option>`)
        .join("");
}

function getFilters() {
    const params = new URLSearchParams();
    const district = document.querySelector("#districtFilter").value;
    const houseType = document.querySelector("#houseTypeFilter").value;
    const minPrice = document.querySelector("#minPriceFilter").value;
    const maxPrice = document.querySelector("#maxPriceFilter").value;
    params.set("page", currentPage);
    if (district) params.set("district", district);
    if (houseType) params.set("house_type", houseType);
    if (minPrice) params.set("min_price", minPrice);
    if (maxPrice) params.set("max_price", maxPrice);
    return params;
}

function renderListings(payload) {
    totalPages = Math.max(payload.pages || 1, 1);
    const body = document.querySelector("#listingBody");
    const total = document.querySelector("#listingTotal");
    const pageInfo = document.querySelector("#pageInfo");
    const prevButton = document.querySelector("#prevPageBtn");
    const nextButton = document.querySelector("#nextPageBtn");

    total.textContent = `共 ${payload.total} 条`;
    pageInfo.textContent = `第 ${payload.page} / ${totalPages} 页`;
    prevButton.disabled = payload.page <= 1;
    nextButton.disabled = payload.page >= totalPages;

    if (!payload.items.length) {
        body.innerHTML = `<tr><td colspan="9">暂无匹配房源</td></tr>`;
        return;
    }

    body.innerHTML = payload.items.map(item => `
        <tr>
            <td>${item.district}</td>
            <td>${item.community}</td>
            <td>${formatCurrency(item.rent_price)}</td>
            <td>${item.area}㎡</td>
            <td>${item.house_type}</td>
            <td>${item.orientation || "-"}</td>
            <td>${item.floor || "-"}</td>
            <td>${item.tags || "-"}</td>
            <td>${item.publish_time || "-"}</td>
        </tr>
    `).join("");
}

async function loadListings() {
    const payload = await requestJson(`/api/listings?${getFilters().toString()}`);
    renderListings(payload);
}

function bindListingActions() {
    document.querySelector("#searchBtn").addEventListener("click", () => {
        currentPage = 1;
        loadListings();
    });
    document.querySelector("#resetBtn").addEventListener("click", () => {
        document.querySelector("#districtFilter").value = "";
        document.querySelector("#houseTypeFilter").value = "";
        document.querySelector("#minPriceFilter").value = "";
        document.querySelector("#maxPriceFilter").value = "";
        currentPage = 1;
        loadListings();
    });
    document.querySelector("#prevPageBtn").addEventListener("click", () => {
        if (currentPage > 1) {
            currentPage -= 1;
            loadListings();
        }
    });
    document.querySelector("#nextPageBtn").addEventListener("click", () => {
        if (currentPage < totalPages) {
            currentPage += 1;
            loadListings();
        }
    });
}

document.addEventListener("DOMContentLoaded", async () => {
    await Promise.all([
        loadOptions("/api/districts", "#districtFilter", "全部区域"),
        loadOptions("/api/house-types", "#houseTypeFilter", "全部户型")
    ]);
    bindListingActions();
    await loadListings();
});
