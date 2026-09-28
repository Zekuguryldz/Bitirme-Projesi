const searchInput = document.getElementById("searchInput");
const categoryFilter = document.getElementById("categoryFilter");
const categoryFilterWrap = document.getElementById("categoryFilterWrap");
const marketFilter = document.getElementById("marketFilter");
const dateStartFilter = document.getElementById("dateStartFilter");
const dateEndFilter = document.getElementById("dateEndFilter");
const productsUrunDurumuFilter = document.getElementById("productsUrunDurumuFilter");
const filterButton = document.getElementById("filterButton");
const productsTableBody = document.getElementById("productsTableBody");
const productCount = document.getElementById("productCount");
const firstPageButton = document.getElementById("firstPageButton");
const prevPageButton = document.getElementById("prevPageButton");
const nextPageButton = document.getElementById("nextPageButton");
const lastPageButton = document.getElementById("lastPageButton");
const pageIndicator = document.getElementById("pageIndicator");
const pageNumberInput = document.getElementById("pageNumberInput");
const paginationSummary = document.getElementById("paginationSummary");
const productsTemaKoku = document.getElementById("productsTemaKoku");
const productsDurumLegend = document.getElementById("productsDurumLegend");

const PAGE_SIZE = 30;
let currentPage = 1;
let totalRecords = 0;
const initialParams = new URLSearchParams(window.location.search);
const productsResponseCache = new Map();
const categoriesResponseCache = new Map();
const availableDatesCache = new Map();
let hasPrefetchedMarketQueries = false;
let initialMarketFilterValue = "";
const initialCategoryFilterValue = initialParams.get("kategori") ?? "";
const DEFAULT_MARKETS = ["ŞOK", "MİGROS"];
const DEFAULT_URUN_DURUMU = "";
const URUN_DURUMU_SECENEKLERI = {
    "": {
        temaSinifi: "tema-sabit-urunler",
        satirSinifi: "comparison-row-sabit",
    },
    zamlanmis_urunler: {
        temaSinifi: "tema-zamlanmis-urunler",
        satirSinifi: "comparison-row-zam",
    },
    indirimdeki_urunler: {
        temaSinifi: "tema-indirimdeki-urunler",
        satirSinifi: "comparison-row-indirim",
    },
    shrinkflation_riskli_urunler: {
        temaSinifi: "tema-shrinkflation-riskli-urunler",
        satirSinifi: "comparison-row-shrinkflation",
    },
};
const DURUM_TEMA_SINIFLARI = [...new Set(
    Object.values(URUN_DURUMU_SECENEKLERI).map(({ temaSinifi }) => temaSinifi),
)];

const CATEGORY_LABELS = {
    Atistirmaliklar: "Atıştırmalıklar",
    Dondurma: "Dondurma",
    "Dondurulmus Urunler": "Dondurulmuş Ürünler",
    "Et Tavuk Sarkuteri": "Et Tavuk Şarküteri",
    Icecekler: "İçecekler",
    Kahvaltilik: "Kahvaltılık",
    Temizlik: "Temizlik",
    "Yemeklik Malzemeler": "Yemeklik Malzemeler",
};

function formatCategory(value) {
    if (!value) return "-";
    return CATEGORY_LABELS[value] ?? value;
}

function normalizeCategoryOptionValue(value) {
    if (!value) return "";
    const trimmedValue = String(value).trim();
    if (!trimmedValue) return "";
    return formatCategory(trimmedValue);
}

function normalizeMarketFilterValue(value) {
    if (!value) return "";
    const normalized = value
        .toLocaleLowerCase("tr-TR")
        .replaceAll("ş", "s")
        .replaceAll("ı", "i")
        .trim();
    if (normalized.startsWith("sok")) {
        return "ŞOK";
    }
    if (normalized.startsWith("migros")) {
        return "MİGROS";
    }
    return value;
}

function normalizeMarket(value) {
    return normalizeMarketFilterValue(value) || "-";
}

function normalizeUrunDurumuParamValue(value) {
    if (!value) return DEFAULT_URUN_DURUMU;

    const normalized = String(value)
        .trim()
        .toLocaleLowerCase("tr-TR")
        .replaceAll("ş", "s")
        .replaceAll("ı", "i")
        .replaceAll("ğ", "g")
        .replaceAll("ü", "u")
        .replaceAll("ö", "o")
        .replaceAll("ç", "c")
        .replaceAll("-", "_")
        .replaceAll(" ", "_");

    if ([
        "zamlanmis",
        "zamlanan",
        "zamlanan_urunler",
        "zamlanmis_urunler",
    ].includes(normalized)) {
        return "zamlanmis_urunler";
    }
    if ([
        "indirimdeki",
        "indirimli",
        "indirime_girmis",
        "indirimdeki_urunler",
        "indirimli_urunler",
    ].includes(normalized)) {
        return "indirimdeki_urunler";
    }
    if ([
        "shrinkflation",
        "shrinkflation_riskli",
        "shrinkflation_riskli_urunler",
    ].includes(normalized)) {
        return "shrinkflation_riskli_urunler";
    }
    return DEFAULT_URUN_DURUMU;
}

function getSelectedUrunDurumu() {
    return normalizeUrunDurumuParamValue(
        productsUrunDurumuFilter?.value ?? initialParams.get("urun_durumu") ?? DEFAULT_URUN_DURUMU,
    );
}

function getUrunDurumuAyarlari(urunDurumu = getSelectedUrunDurumu()) {
    return URUN_DURUMU_SECENEKLERI[urunDurumu] ?? URUN_DURUMU_SECENEKLERI[DEFAULT_URUN_DURUMU];
}

function updateProductsDurumLegend(urunDurumu = getSelectedUrunDurumu()) {
    if (!productsDurumLegend) return;

    productsDurumLegend
        .querySelectorAll(".products-durum-item")
        .forEach((element) => {
            element.classList.toggle("is-active", element.dataset.urunDurumu === urunDurumu);
        });
}

function applyProductsDurumTheme(urunDurumu = getSelectedUrunDurumu()) {
    const durumAyarlari = getUrunDurumuAyarlari(urunDurumu);

    if (productsTemaKoku) {
        productsTemaKoku.classList.remove(...DURUM_TEMA_SINIFLARI);
        productsTemaKoku.classList.add(durumAyarlari.temaSinifi);
    }

    updateProductsDurumLegend(urunDurumu);
}

function formatDate(value) {
    if (!value) return "-";

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "-";

    return new Intl.DateTimeFormat("tr-TR", {
        dateStyle: "short",
        timeStyle: "short",
    }).format(date);
}

function formatCurrency(value) {
    if (value === null || value === undefined) return "-";
    return new Intl.NumberFormat("tr-TR", {
        style: "currency",
        currency: "TRY",
        maximumFractionDigits: 2,
    }).format(Number(value));
}

function formatMeasure(value, unit) {
    if (value === null || value === undefined) return "-";
    const number = Number(value);
    const text = Number.isInteger(number) ? `${number}` : number.toFixed(2);
    return `${text} ${unit ?? ""}`.trim();
}

function getUnitPriceBasis(unit) {
    if (!unit) return "";

    const normalizedUnit = String(unit).trim().toLocaleLowerCase("tr-TR");
    if (normalizedUnit === "g" || normalizedUnit === "gr") {
        return "g";
    }
    if (normalizedUnit === "ml") {
        return "ml";
    }
    if (normalizedUnit === "adet" || normalizedUnit === "ad") {
        return "adet";
    }

    return normalizedUnit;
}

function formatUnitPriceAmount(value) {
    const number = Number(value);
    const useExtendedPrecision = Math.abs(number) < 1;
    return new Intl.NumberFormat("tr-TR", {
        style: "currency",
        currency: "TRY",
        minimumFractionDigits: 2,
        maximumFractionDigits: useExtendedPrecision ? 4 : 2,
    }).format(number);
}

function formatUnitPrice(value, unit) {
    if (value === null || value === undefined) return "-";

    const basis = getUnitPriceBasis(unit);
    const formattedValue = formatUnitPriceAmount(value);
    return basis ? `${formattedValue} / ${basis}` : formattedValue;
}

function escapeAttribute(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll('"', "&quot;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
}

function normalizeProductUrl(value) {
    const normalizedValue = String(value ?? "").trim();
    return normalizedValue || "";
}

function getProductRowStatus(item) {
    const urunDurumu = normalizeUrunDurumuParamValue(item?.urun_durumu ?? "");
    return getUrunDurumuAyarlari(urunDurumu).satirSinifi;
}

function formatDateFilterValue(value) {
    if (!value) return "";

    const directMatch = String(value).match(/^(\d{4}-\d{2}-\d{2})/);
    if (directMatch) {
        return directMatch[1];
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";

    const pad = (part) => String(part).padStart(2, "0");
    const year = date.getFullYear();
    const month = pad(date.getMonth() + 1);
    const day = pad(date.getDate());

    return `${year}-${month}-${day}`;
}

function formatDateFilterOptionLabel(value) {
    const normalizedValue = formatDateFilterValue(value);
    if (!normalizedValue) return "";

    const [year, month, day] = normalizedValue.split("-");
    if (!year || !month || !day) return normalizedValue;
    return `${day}.${month}.${year}`;
}

function serializeDateFilterValue(value) {
    if (!value) return "";
    return value;
}

function getNormalizedDateRange() {
    const startValue = dateStartFilter?.value ?? "";
    const endValue = dateEndFilter?.value ?? "";

    if (!startValue || !endValue) {
        return {
            startValue,
            endValue,
        };
    }

    if (startValue <= endValue) {
        return {
            startValue,
            endValue,
        };
    }

    return {
        startValue: endValue,
        endValue: startValue,
    };
}

function resetCategoryFilter({ hide = true } = {}) {
    if (categoryFilterWrap) {
        categoryFilterWrap.hidden = hide;
    }

    if (!categoryFilter) return;

    categoryFilter.disabled = true;
    categoryFilter.innerHTML = '<option value="">Tüm Kategoriler</option>';
    categoryFilter.value = "";
}

function showCategoryFilterLoading() {
    if (categoryFilterWrap) {
        categoryFilterWrap.hidden = false;
    }

    if (!categoryFilter) return;

    categoryFilter.disabled = true;
    categoryFilter.innerHTML = '<option value="">Kategoriler yükleniyor...</option>';
}

function updateDateFilterOptions(
    availableDates = [],
    { selectedStartValue = "", selectedEndValue = "" } = {},
) {
    const normalizedStartValue = formatDateFilterValue(selectedStartValue);
    const normalizedEndValue = formatDateFilterValue(selectedEndValue);
    const hasDates = availableDates.length > 0;
    const optionMarkup = '<option value="">Tüm Tarihler</option>' + availableDates
        .map((value) => {
            const normalizedValue = formatDateFilterValue(value);
            return `<option value="${normalizedValue}">${formatDateFilterOptionLabel(normalizedValue)}</option>`;
        })
        .join("");

    [dateStartFilter, dateEndFilter].forEach((input) => {
        if (!input) return;
        input.disabled = !hasDates;
        input.innerHTML = optionMarkup;
    });

    if (dateStartFilter) {
        dateStartFilter.value = availableDates.includes(normalizedStartValue) ? normalizedStartValue : "";
    }
    if (dateEndFilter) {
        dateEndFilter.value = availableDates.includes(normalizedEndValue) ? normalizedEndValue : "";
    }
}

async function loadAvailableDates(
    marketValue,
    {
        preserveSelectedDates = false,
        selectedStartValue = "",
        selectedEndValue = "",
    } = {},
) {
    const cacheKey = marketValue || "__all__";

    try {
        if (!availableDatesCache.has(cacheKey)) {
            const marketQuery = marketValue
                ? `?market=${encodeURIComponent(marketValue)}`
                : "";
            const response = await fetch(`/products/dates${marketQuery}`);
            if (!response.ok) {
                throw new Error("dates fetch failed");
            }

            const data = await response.json();
            const dates = (data.items ?? [])
                .map((value) => formatDateFilterValue(value))
                .filter(Boolean)
                .sort((a, b) => a.localeCompare(b));
            availableDatesCache.set(cacheKey, dates);
        }

        const availableDates = availableDatesCache.get(cacheKey) ?? [];
        const effectiveSelectedStartValue = preserveSelectedDates
            ? (selectedStartValue || (dateStartFilter?.value ?? ""))
            : "";
        const effectiveSelectedEndValue = preserveSelectedDates
            ? (selectedEndValue || (dateEndFilter?.value ?? ""))
            : "";
        updateDateFilterOptions(availableDates, {
            selectedStartValue: effectiveSelectedStartValue,
            selectedEndValue: effectiveSelectedEndValue,
        });
    } catch (error) {
        updateDateFilterOptions([]);
    }
}

function renderProducts(items) {
    if (!items.length) {
        productsTableBody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center text-secondary py-4">Gösterilecek kayıt bulunamadı.</td>
            </tr>
        `;
        return;
    }

    productsTableBody.innerHTML = items.map((item) => {
        const productUrl = normalizeProductUrl(item.urun_url);
        const rowClasses = [getProductRowStatus(item)];
        if (productUrl) {
            rowClasses.push("comparison-clickable-row");
        }

        return `
            <tr
                class="${rowClasses.join(" ")}"
                ${productUrl ? `data-product-url="${escapeAttribute(productUrl)}" title="${escapeAttribute(productUrl)}"` : ""}
            >
                <td>
                    ${productUrl
        ? `<a class="table-product-link" href="${escapeAttribute(productUrl)}" title="${escapeAttribute(productUrl)}">${item.urun_ad ?? "-"}</a>`
        : `${item.urun_ad ?? "-"}`}
                </td>
                <td>${formatCategory(item.urun_kategori)}</td>
                <td>${normalizeMarket(item.market_adi)}</td>
                <td>${formatCurrency(item.urun_fiyat)}</td>
                <td>${formatMeasure(item.gramaj_degeri, item.gramaj_birimi)}</td>
                <td>${formatUnitPrice(item.birim_fiyat, item.gramaj_birimi)}</td>
                <td>${item.urun_marka ?? "-"}</td>
                <td>${formatDate(item.eklenme_tarihi)}</td>
            </tr>
        `;
    }).join("");
}

productsTableBody?.addEventListener("click", (event) => {
    if (event.target instanceof HTMLElement && event.target.closest("a")) {
        return;
    }

    const tableRow = event.target instanceof HTMLElement
        ? event.target.closest("tr[data-product-url]")
        : null;
    const productUrl = tableRow?.dataset?.productUrl ?? "";
    if (!productUrl) {
        return;
    }

    window.location.assign(productUrl);
});

function populateCategoryFilter(items, selectedValue = "") {
    if (!categoryFilter) return;

    const categories = [...new Map(
        items
            .filter(Boolean)
            .map((category) => {
                const normalizedCategory = normalizeCategoryOptionValue(category);
                return [normalizedCategory.toLocaleLowerCase("tr-TR"), normalizedCategory];
            }),
    ).values()].sort((a, b) => a.localeCompare(b, "tr"));
    const normalizedSelectedValue = normalizeCategoryOptionValue(selectedValue);
    if (categoryFilterWrap) {
        categoryFilterWrap.hidden = false;
    }
    categoryFilter.disabled = false;
    categoryFilter.innerHTML = '<option value="">Tüm Kategoriler</option>' +
        categories.map((category) => `<option value="${category}">${category}</option>`).join("");
    categoryFilter.value = categories.includes(normalizedSelectedValue) ? normalizedSelectedValue : "";
}

function populateMarketFilter(items) {
    const markets = [...new Set([
        ...DEFAULT_MARKETS,
        ...items.map((item) => normalizeMarket(item.market_adi)).filter(Boolean),
    ])].sort((a, b) => a.localeCompare(b, "tr"));
    const selectedValue = marketFilter.value || initialMarketFilterValue;
    marketFilter.disabled = false;
    marketFilter.innerHTML = '<option value="">Tüm Marketler</option>' +
        markets.map((market) => `<option value="${market}">${market}</option>`).join("");
    marketFilter.value = markets.includes(selectedValue) || selectedValue === "" ? selectedValue : "";
    initialMarketFilterValue = "";
}

function updatePagination(total) {
    totalRecords = total;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const startRecord = total === 0 ? 0 : ((currentPage - 1) * PAGE_SIZE) + 1;
    const endRecord = total === 0 ? 0 : Math.min(currentPage * PAGE_SIZE, total);

    if (pageIndicator) {
        pageIndicator.textContent = `/ ${totalPages}`;
    }

    if (pageNumberInput) {
        pageNumberInput.max = String(totalPages);
        pageNumberInput.value = String(currentPage);
    }

    if (paginationSummary) {
        paginationSummary.textContent = total === 0
            ? "Gösterilecek kayıt bulunamadı."
            : `${startRecord}-${endRecord} arası kayıtlar gösteriliyor.`;
    }

    if (firstPageButton) {
        firstPageButton.disabled = currentPage <= 1;
    }

    if (prevPageButton) {
        prevPageButton.disabled = currentPage <= 1;
    }

    if (nextPageButton) {
        nextPageButton.disabled = currentPage >= totalPages;
    }

    if (lastPageButton) {
        lastPageButton.disabled = currentPage >= totalPages;
    }
}

async function loadCategoryOptions(
    marketValue,
    { selectedValue = "" } = {},
) {
    if (!categoryFilter) return;
    if (!marketValue) {
        resetCategoryFilter();
        return;
    }

    showCategoryFilterLoading();

    const cacheKey = String(marketValue);

    try {
        if (!categoriesResponseCache.has(cacheKey)) {
            const response = await fetch(`/products/categories?market=${encodeURIComponent(marketValue)}`);
            if (!response.ok) {
                throw new Error("categories fetch failed");
            }

            const data = await response.json();
            categoriesResponseCache.set(cacheKey, data.items ?? []);
        }

        populateCategoryFilter(categoriesResponseCache.get(cacheKey), selectedValue);
    } catch (error) {
        if (categoryFilterWrap) {
            categoryFilterWrap.hidden = false;
        }
        categoryFilter.disabled = false;
        categoryFilter.innerHTML = '<option value="">Tüm Kategoriler</option>';
        categoryFilter.value = "";
    }
}

function buildProductsParams({
    page = currentPage,
    searchValue = searchInput?.value.trim() ?? "",
    categoryValue = categoryFilter?.value ?? "",
    marketValue = marketFilter?.value || initialMarketFilterValue,
    dateStartValue = dateStartFilter?.value ?? "",
    dateEndValue = dateEndFilter?.value ?? "",
    urunDurumu = getSelectedUrunDurumu(),
} = {}) {
    const effectiveMarketValue = marketValue ?? "";
    const effectiveCategoryValue = effectiveMarketValue ? categoryValue : "";
    const normalizedDateRange = getNormalizedDateRange();
    const effectiveDateStartValue = dateStartValue || normalizedDateRange.startValue;
    const effectiveDateEndValue = dateEndValue || normalizedDateRange.endValue;
    const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String((page - 1) * PAGE_SIZE),
    });

    if (searchValue) {
        params.set("search", searchValue);
    }

    if (effectiveCategoryValue) {
        params.set("kategori", effectiveCategoryValue);
    }

    if (effectiveMarketValue) {
        params.set("market", effectiveMarketValue);
    }

    if (urunDurumu) {
        params.set("urun_durumu", urunDurumu);
    }

    const serializedDateStartValue = serializeDateFilterValue(effectiveDateStartValue);
    if (serializedDateStartValue) {
        params.set("tarih_baslangic", serializedDateStartValue);
    }

    const serializedDateEndValue = serializeDateFilterValue(effectiveDateEndValue);
    if (serializedDateEndValue) {
        params.set("tarih_bitis", serializedDateEndValue);
    }

    return params;
}

function applyProductsResponse(data) {
    renderProducts(data.items ?? []);
    populateMarketFilter(data.items ?? []);
    productCount.textContent = `${data.total ?? 0} kayıt listeleniyor`;
    updatePagination(data.total ?? 0);
}

async function fetchProductsData(params) {
    const cacheKey = params.toString();
    if (productsResponseCache.has(cacheKey)) {
        return productsResponseCache.get(cacheKey);
    }

    const response = await fetch(`/products?${cacheKey}`);
    if (!response.ok) {
        throw new Error("products fetch failed");
    }

    const data = await response.json();
    productsResponseCache.set(cacheKey, data);
    return data;
}

async function prefetchMarketQueries() {
    if (hasPrefetchedMarketQueries) return;
    if (!marketFilter || currentPage !== 1) return;
    if (searchInput?.value.trim() || categoryFilter?.value || dateStartFilter?.value || dateEndFilter?.value || getSelectedUrunDurumu()) return;

    const marketValues = [...marketFilter.options]
        .map((option) => option.value)
        .filter((value) => value && value !== (marketFilter.value ?? ""));

    if (!marketValues.length) return;

    hasPrefetchedMarketQueries = true;
    await Promise.allSettled(
        marketValues.map((marketValue) => fetchProductsData(buildProductsParams({ page: 1, marketValue })))
    );
}

async function loadProducts({ resetPage = false } = {}) {
    if (!productsTableBody || !productCount) return;

    if (resetPage) {
        currentPage = 1;
    }

    productsTableBody.innerHTML = `
        <tr>
            <td colspan="8" class="text-center text-secondary py-4">Veri yükleniyor...</td>
        </tr>
    `;

    const params = buildProductsParams();

    try {
        const data = await fetchProductsData(params);
        applyProductsResponse(data);
        prefetchMarketQueries();
    } catch (error) {
        productsTableBody.innerHTML = `
            <tr>
                <td colspan="8" class="text-center text-secondary py-4">Veriler alınırken bir sorun oluştu.</td>
            </tr>
        `;
        productCount.textContent = "Veri alınamadı";

        if (paginationSummary) {
            paginationSummary.textContent = "Sayfalama bilgisi alınamadı.";
        }
        if (pageIndicator) {
            pageIndicator.textContent = "-";
        }
        if (pageNumberInput) {
            pageNumberInput.value = "1";
        }
        if (firstPageButton) {
            firstPageButton.disabled = true;
        }
        if (prevPageButton) {
            prevPageButton.disabled = true;
        }
        if (nextPageButton) {
            nextPageButton.disabled = true;
        }
        if (lastPageButton) {
            lastPageButton.disabled = true;
        }
    }
}

function goToPage(page) {
    const totalPages = Math.max(1, Math.ceil(totalRecords / PAGE_SIZE));
    const nextPage = Math.min(Math.max(page, 1), totalPages);
    if (nextPage === currentPage) {
        updatePagination(totalRecords);
        return;
    }

    currentPage = nextPage;
    loadProducts();
}

filterButton?.addEventListener("click", () => loadProducts({ resetPage: true }));
marketFilter?.addEventListener("change", async () => {
    await loadCategoryOptions(marketFilter.value, { selectedValue: "" });
    await loadAvailableDates(marketFilter.value, { preserveSelectedDates: false });
    loadProducts({ resetPage: true });
});
productsUrunDurumuFilter?.addEventListener("change", () => {
    applyProductsDurumTheme();
    loadProducts({ resetPage: true });
});

searchInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        event.preventDefault();
        loadProducts({ resetPage: true });
    }
});

pageNumberInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        event.preventDefault();
        const requestedPage = Number(pageNumberInput.value);
        if (!Number.isFinite(requestedPage)) return;
        goToPage(requestedPage);
    }
});

pageNumberInput?.addEventListener("blur", () => {
    const requestedPage = Number(pageNumberInput.value);
    if (!Number.isFinite(requestedPage)) {
        pageNumberInput.value = String(currentPage);
        return;
    }
    goToPage(requestedPage);
});

firstPageButton?.addEventListener("click", () => {
    goToPage(1);
});

prevPageButton?.addEventListener("click", () => {
    if (currentPage <= 1) return;
    currentPage -= 1;
    loadProducts();
});

nextPageButton?.addEventListener("click", () => {
    const totalPages = Math.max(1, Math.ceil(totalRecords / PAGE_SIZE));
    if (currentPage >= totalPages) return;
    currentPage += 1;
    loadProducts();
});

lastPageButton?.addEventListener("click", () => {
    const totalPages = Math.max(1, Math.ceil(totalRecords / PAGE_SIZE));
    goToPage(totalPages);
});

async function initializePage() {
    if (searchInput && initialParams.get("search")) {
        searchInput.value = initialParams.get("search");
    }

    const initialUrunDurumuValue = normalizeUrunDurumuParamValue(initialParams.get("urun_durumu") ?? "");
    if (productsUrunDurumuFilter) {
        productsUrunDurumuFilter.value = initialUrunDurumuValue;
    }
    applyProductsDurumTheme(initialUrunDurumuValue);

    const initialMarketValue = normalizeMarketFilterValue(initialParams.get("market") ?? "");
    initialMarketFilterValue = initialMarketValue;
    populateMarketFilter([]);

    await loadCategoryOptions(initialMarketValue, { selectedValue: initialCategoryFilterValue });

    const initialDateStartValue = formatDateFilterValue(
        initialParams.get("tarih_baslangic") ?? initialParams.get("tarih") ?? "",
    );
    const initialDateEndValue = formatDateFilterValue(
        initialParams.get("tarih_bitis") ?? initialParams.get("tarih") ?? "",
    );
    const normalizedInitialRange = (
        initialDateStartValue && initialDateEndValue && initialDateStartValue > initialDateEndValue
    )
        ? {
            startValue: initialDateEndValue,
            endValue: initialDateStartValue,
        }
        : {
            startValue: initialDateStartValue,
            endValue: initialDateEndValue,
        };

    await loadAvailableDates(initialMarketValue, {
        preserveSelectedDates: true,
        selectedStartValue: normalizedInitialRange.startValue,
        selectedEndValue: normalizedInitialRange.endValue,
    });

    loadProducts({ resetPage: true });
}

initializePage();
