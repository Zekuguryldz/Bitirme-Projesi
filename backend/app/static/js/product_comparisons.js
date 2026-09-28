const productComparisonsTableBody = document.getElementById("productComparisonsTableBody");
const productComparisonsCount = document.getElementById("productComparisonsCount");
const productComparisonsFirstPageButton = document.getElementById("productComparisonsFirstPageButton");
const productComparisonsPrevPageButton = document.getElementById("productComparisonsPrevPageButton");
const productComparisonsNextPageButton = document.getElementById("productComparisonsNextPageButton");
const productComparisonsLastPageButton = document.getElementById("productComparisonsLastPageButton");
const productComparisonsPageIndicator = document.getElementById("productComparisonsPageIndicator");
const productComparisonsPageNumberInput = document.getElementById("productComparisonsPageNumberInput");
const productComparisonsSummary = document.getElementById("productComparisonsSummary");
const productComparisonsTitle = document.getElementById("productComparisonsTitle");
const comparisonMarketFilter = document.getElementById("comparisonMarketFilter");
const comparisonCategoryFilterWrap = document.getElementById("comparisonCategoryFilterWrap");
const comparisonCategoryFilter = document.getElementById("comparisonCategoryFilter");
const comparisonDateStart = document.getElementById("comparisonDateStart");
const comparisonDateEnd = document.getElementById("comparisonDateEnd");
const comparisonUrunDurumuFilter = document.getElementById("comparisonUrunDurumuFilter");
const comparisonFilterButton = document.getElementById("comparisonFilterButton");
const comparisonTemaKoku = document.getElementById("comparisonTemaKoku");
const comparisonUrunDurumuGostergesiYazi = document.getElementById("comparisonUrunDurumuGostergesiYazi");

const PAGE_SIZE = 10;
let currentPage = 1;
let totalComparisons = 0;
const initialParams = new URLSearchParams(window.location.search);
const availableDatesCache = new Map();
const categoriesResponseCache = new Map();
const initialCategoryFilterValue = initialParams.get("kategori") ?? "";
const DEFAULT_URUN_DURUMU = "zamlanmis_urunler";
const SUPPORTED_MARKETS = {
    sok: "ŞOK",
    migros: "MİGROS",
};
const URUN_DURUMU_SECENEKLERI = {
    zamlanmis_urunler: {
        baslik: "Zamlanmış Ürün Karşılaştırmaları",
        aciklama: "Birim fiyat arttı",
        bosMesaj: "Seçili filtreler için zamlanmış ürün bulunamadı.",
        etiket: "Zamlanmış Ürünler",
        temaSinifi: "tema-zamlanmis-urunler",
    },
    indirimdeki_urunler: {
        baslik: "İndirimdeki Ürün Karşılaştırmaları",
        aciklama: "Birim fiyat azaldı",
        bosMesaj: "Seçili filtreler için indirimdeki ürün bulunamadı.",
        etiket: "İndirimli Ürünler",
        temaSinifi: "tema-indirimdeki-urunler",
    },
    shrinkflation_riskli_urunler: {
        baslik: "Shrinkflation Riskli Ürün Karşılaştırmaları",
        aciklama: null,
        bosMesaj: "Seçili filtreler için shrinkflation riskli ürün bulunamadı.",
        etiket: "Shrinkflation Riskli Ürünler",
        temaSinifi: "tema-shrinkflation-riskli-urunler",
    },
};
const DURUM_TEMA_SINIFLARI = Object.values(URUN_DURUMU_SECENEKLERI).map(({ temaSinifi }) => temaSinifi);

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

function normalizeMarket(value) {
    if (!value) return "-";
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

function formatCount(value) {
    if (value === null || value === undefined) return "-";
    const number = Number(value);
    if (Number.isInteger(number)) return `${number}`;
    return number.toFixed(2);
}

function formatContent(value, unit) {
    if (value === null || value === undefined) return "-";
    const number = Number(value);
    const text = Number.isInteger(number) ? `${number}` : number.toFixed(2);
    return `${text} ${unit ?? ""}`.trim();
}

function formatUnitPrice(value, unit) {
    if (value === null || value === undefined) return "-";
    const number = Number(value);
    const useExtendedPrecision = Math.abs(number) < 1;
    const formatted = new Intl.NumberFormat("tr-TR", {
        style: "currency",
        currency: "TRY",
        minimumFractionDigits: 2,
        maximumFractionDigits: useExtendedPrecision ? 4 : 2,
    }).format(number);
    if (!unit) return formatted;
    const normalizedUnit = String(unit).trim().toLocaleLowerCase("tr-TR");
    return `${formatted} / ${normalizedUnit === "gr" ? "g" : normalizedUnit}`;
}

function formatComparisonReason(value) {
    const labels = {
        total_content_reduced: "Toplam içerik azaldı",
        total_content_increased: "Toplam içerik arttı",
        pack_count_reduced: "Paket adedi azaldı",
        pack_count_increased: "Paket adedi arttı",
        unit_size_reduced: "Birim içerik azaldı",
        unit_size_increased: "Birim içerik arttı",
        pack_count_and_unit_size_reduced: "Adet ve birim içerik azaldı",
        pack_count_and_unit_size_increased: "Adet ve birim içerik arttı",
        content_unchanged: "İçerik sabit",
    };
    return labels[value] ?? "Karşılaştırma";
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

function normalizeMarketParamValue(value) {
    if (!value) return "";
    const normalized = String(value)
        .trim()
        .toLocaleLowerCase("tr-TR")
        .replaceAll("ş", "s")
        .replaceAll("ı", "i");
    if (normalized.startsWith("sok")) {
        return "sok";
    }
    if (normalized.startsWith("migros")) {
        return "migros";
    }
    return "";
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

function getSeciliUrunDurumu() {
    return normalizeUrunDurumuParamValue(
        comparisonUrunDurumuFilter?.value ?? initialParams.get("urun_durumu") ?? DEFAULT_URUN_DURUMU,
    );
}

function getUrunDurumuAyarlari(urunDurumu = getSeciliUrunDurumu()) {
    return URUN_DURUMU_SECENEKLERI[urunDurumu] ?? URUN_DURUMU_SECENEKLERI[DEFAULT_URUN_DURUMU];
}

function uygulaKarsilastirmaDurumTemasi(urunDurumu = getSeciliUrunDurumu()) {
    const durumAyarlari = getUrunDurumuAyarlari(urunDurumu);

    if (comparisonTemaKoku) {
        comparisonTemaKoku.classList.remove(...DURUM_TEMA_SINIFLARI);
        comparisonTemaKoku.classList.add(durumAyarlari.temaSinifi);
    }

    if (comparisonUrunDurumuGostergesiYazi) {
        comparisonUrunDurumuGostergesiYazi.textContent = durumAyarlari.etiket;
    }
}

function normalizeCategoryOptionValue(value) {
    if (!value) return "";
    return String(value).trim();
}

function formatDateInputValue(value) {
    if (!value) return "";
    const directMatch = String(value).match(/^(\d{4}-\d{2}-\d{2})/);
    if (directMatch) {
        return directMatch[1];
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";

    const pad = (part) => String(part).padStart(2, "0");
    return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function formatDateOptionLabel(value) {
    const normalizedValue = formatDateInputValue(value);
    if (!normalizedValue) return "";

    const [year, month, day] = normalizedValue.split("-");
    if (!year || !month || !day) return normalizedValue;
    return `${day}.${month}.${year}`;
}

function getNormalizedDateRange() {
    const startValue = comparisonDateStart?.value ?? "";
    const endValue = comparisonDateEnd?.value ?? "";

    if (!startValue || !endValue) {
        return { startValue, endValue };
    }

    if (startValue <= endValue) {
        return { startValue, endValue };
    }

    return {
        startValue: endValue,
        endValue: startValue,
    };
}

function getKarsilastirmaAciklamasi(item) {
    const seciliUrunDurumu = getSeciliUrunDurumu();
    const urunDurumuAyarlari = getUrunDurumuAyarlari();
    if (seciliUrunDurumu === "shrinkflation_riskli_urunler") {
        return formatComparisonReason(item?.reason);
    }
    return urunDurumuAyarlari.aciklama ?? formatComparisonReason(item?.reason);
}

function getComparisonRowStatus(item) {
    if (item?.is_shrinkflation) {
        return "comparison-row-shrinkflation";
    }

    const unitPriceChange = Number(item?.birim_fiyat_degisim_yuzdesi);
    if (Number.isFinite(unitPriceChange)) {
        if (unitPriceChange > 0) {
            return "comparison-row-zam";
        }
        if (unitPriceChange < 0) {
            return "comparison-row-indirim";
        }
    }

    return "comparison-row-sabit";
}

function updateProductComparisonsTitle() {
    if (!productComparisonsTitle) return;
    const durumAyarlari = getUrunDurumuAyarlari();
    productComparisonsTitle.textContent = durumAyarlari.baslik;
    uygulaKarsilastirmaDurumTemasi();
}

function resetComparisonCategoryFilter({ hide = true } = {}) {
    if (comparisonCategoryFilterWrap) {
        comparisonCategoryFilterWrap.hidden = hide;
    }

    if (!comparisonCategoryFilter) return;

    comparisonCategoryFilter.disabled = true;
    comparisonCategoryFilter.innerHTML = '<option value="">Tüm Kategoriler</option>';
    comparisonCategoryFilter.value = "";
}

function showComparisonCategoryFilterLoading() {
    if (comparisonCategoryFilterWrap) {
        comparisonCategoryFilterWrap.hidden = false;
    }

    if (!comparisonCategoryFilter) return;

    comparisonCategoryFilter.disabled = true;
    comparisonCategoryFilter.innerHTML = '<option value="">Kategoriler yükleniyor...</option>';
}

function populateComparisonCategoryFilter(items, selectedValue = "") {
    if (!comparisonCategoryFilter) return;

    const categories = [...new Map(
        items
            .filter(Boolean)
            .map((category) => {
                const normalizedCategory = normalizeCategoryOptionValue(category);
                return [normalizedCategory.toLocaleLowerCase("tr-TR"), normalizedCategory];
            }),
    ).values()].sort((a, b) => a.localeCompare(b, "tr"));
    const normalizedSelectedValue = normalizeCategoryOptionValue(selectedValue);

    if (comparisonCategoryFilterWrap) {
        comparisonCategoryFilterWrap.hidden = false;
    }

    comparisonCategoryFilter.disabled = false;
    comparisonCategoryFilter.innerHTML = '<option value="">Tüm Kategoriler</option>' +
        categories.map((category) => `<option value="${category}">${category}</option>`).join("");
    comparisonCategoryFilter.value = categories.includes(normalizedSelectedValue) ? normalizedSelectedValue : "";
}

async function loadCategoryOptions(
    marketValue,
    { selectedValue = "" } = {},
) {
    if (!comparisonCategoryFilter) return;
    if (!marketValue) {
        resetComparisonCategoryFilter();
        return;
    }

    showComparisonCategoryFilterLoading();

    try {
        if (!categoriesResponseCache.has(marketValue)) {
            const response = await fetch(`/products/categories?market=${encodeURIComponent(marketValue)}`);
            if (!response.ok) {
                throw new Error("comparison categories fetch failed");
            }

            const data = await response.json();
            categoriesResponseCache.set(marketValue, data.items ?? []);
        }

        populateComparisonCategoryFilter(categoriesResponseCache.get(marketValue) ?? [], selectedValue);
    } catch (error) {
        if (comparisonCategoryFilterWrap) {
            comparisonCategoryFilterWrap.hidden = false;
        }
        comparisonCategoryFilter.disabled = false;
        comparisonCategoryFilter.innerHTML = '<option value="">Tüm Kategoriler</option>';
        comparisonCategoryFilter.value = "";
    }
}

function syncComparisonQueryState() {
    const params = new URLSearchParams();
    const marketValue = comparisonMarketFilter?.value ?? "";
    const categoryValue = comparisonCategoryFilter?.value ?? "";
    const urunDurumu = getSeciliUrunDurumu();
    const { startValue, endValue } = getNormalizedDateRange();

    if (marketValue) {
        params.set("market", marketValue);
    }
    if (urunDurumu) {
        params.set("urun_durumu", urunDurumu);
    }
    if (marketValue && categoryValue) {
        params.set("kategori", categoryValue);
    }
    if (startValue) {
        params.set("tarih_baslangic", startValue);
    }
    if (endValue) {
        params.set("tarih_bitis", endValue);
    }
    if (currentPage > 1) {
        params.set("page", String(currentPage));
    }

    const nextQuery = params.toString();
    const nextUrl = nextQuery ? `${window.location.pathname}?${nextQuery}` : window.location.pathname;
    window.history.replaceState({}, "", nextUrl);
}

function updateDateFilterState(
    enabled,
    availableDates = [],
    { selectedStartValue = "", selectedEndValue = "" } = {},
) {
    const normalizedStartValue = formatDateInputValue(selectedStartValue);
    const normalizedEndValue = formatDateInputValue(selectedEndValue);
    const optionMarkup = '<option value="">Tüm Tarihler</option>' + availableDates
        .map((value) => {
            const normalizedValue = formatDateInputValue(value);
            return `<option value="${normalizedValue}">${formatDateOptionLabel(normalizedValue)}</option>`;
        })
        .join("");

    [comparisonDateStart, comparisonDateEnd].forEach((input) => {
        if (!input) return;
        input.disabled = !enabled;
        input.innerHTML = optionMarkup;
        if (!enabled) {
            input.value = "";
        }
    });

    if (!enabled) return;

    if (comparisonDateStart) {
        comparisonDateStart.value = availableDates.includes(normalizedStartValue) ? normalizedStartValue : "";
    }
    if (comparisonDateEnd) {
        comparisonDateEnd.value = availableDates.includes(normalizedEndValue) ? normalizedEndValue : "";
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
    if (!marketValue) {
        updateDateFilterState(false);
        return;
    }

    try {
        if (!availableDatesCache.has(marketValue)) {
            const response = await fetch(`/products/dates?market=${encodeURIComponent(marketValue)}`);
            if (!response.ok) {
                throw new Error("comparison dates fetch failed");
            }
            const data = await response.json();
            const dates = (data.items ?? [])
                .map((value) => formatDateInputValue(value))
                .filter(Boolean)
                .sort((a, b) => a.localeCompare(b));
            availableDatesCache.set(marketValue, dates);
        }

        const availableDates = availableDatesCache.get(marketValue) ?? [];
        const effectiveSelectedStartValue = preserveSelectedDates
            ? (selectedStartValue || (comparisonDateStart?.value ?? ""))
            : "";
        const effectiveSelectedEndValue = preserveSelectedDates
            ? (selectedEndValue || (comparisonDateEnd?.value ?? ""))
            : "";
        updateDateFilterState(true, availableDates, {
            selectedStartValue: effectiveSelectedStartValue,
            selectedEndValue: effectiveSelectedEndValue,
        });
    } catch (error) {
        updateDateFilterState(false);
    }
}

function buildComparisonsParams({ page = currentPage } = {}) {
    const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String((page - 1) * PAGE_SIZE),
    });
    const marketValue = comparisonMarketFilter?.value ?? "";
    const categoryValue = comparisonCategoryFilter?.value ?? "";
    const urunDurumu = getSeciliUrunDurumu();
    const { startValue, endValue } = getNormalizedDateRange();

    if (marketValue) {
        params.set("market", marketValue);
    }
    if (urunDurumu) {
        params.set("urun_durumu", urunDurumu);
    }
    if (marketValue && categoryValue) {
        params.set("kategori", categoryValue);
    }
    if (startValue) {
        params.set("tarih_baslangic", startValue);
    }
    if (endValue) {
        params.set("tarih_bitis", endValue);
    }

    return params;
}

function updatePagination(total) {
    totalComparisons = total;
    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
    const startRecord = total === 0 ? 0 : ((currentPage - 1) * PAGE_SIZE) + 1;
    const endRecord = total === 0 ? 0 : Math.min(currentPage * PAGE_SIZE, total);

    if (productComparisonsCount) {
        productComparisonsCount.textContent = `${total} karşılaştırma bulundu`;
    }

    if (productComparisonsPageIndicator) {
        productComparisonsPageIndicator.textContent = `/ ${totalPages}`;
    }

    if (productComparisonsPageNumberInput) {
        productComparisonsPageNumberInput.max = String(totalPages);
        productComparisonsPageNumberInput.value = String(currentPage);
    }

    if (productComparisonsSummary) {
        productComparisonsSummary.textContent = total === 0
            ? "Gösterilecek karşılaştırma bulunamadı."
            : `${startRecord}-${endRecord} arası karşılaştırmalar gösteriliyor.`;
    }

    if (productComparisonsFirstPageButton) {
        productComparisonsFirstPageButton.disabled = currentPage <= 1;
    }

    if (productComparisonsPrevPageButton) {
        productComparisonsPrevPageButton.disabled = currentPage <= 1;
    }

    if (productComparisonsNextPageButton) {
        productComparisonsNextPageButton.disabled = currentPage >= totalPages;
    }

    if (productComparisonsLastPageButton) {
        productComparisonsLastPageButton.disabled = currentPage >= totalPages;
    }

    syncComparisonQueryState();
}

function renderProductComparisons(items) {
    if (!productComparisonsTableBody) return;
    const urunDurumuAyarlari = getUrunDurumuAyarlari();

    if (!items.length) {
        productComparisonsTableBody.innerHTML = `
            <tr>
                <td colspan="10" class="text-center text-secondary py-4">${urunDurumuAyarlari.bosMesaj}</td>
            </tr>
        `;
        return;
    }

    productComparisonsTableBody.innerHTML = items.map((item) => `
        <tr
            class="${[
        getComparisonRowStatus(item),
        normalizeProductUrl(item.urun_url) ? "comparison-clickable-row" : "",
    ].filter(Boolean).join(" ")}"
            ${normalizeProductUrl(item.urun_url) ? `data-product-url="${escapeAttribute(normalizeProductUrl(item.urun_url))}" title="${escapeAttribute(normalizeProductUrl(item.urun_url))}"` : ""}
        >
            <td>
                ${normalizeProductUrl(item.urun_url)
        ? `<a class="table-product-link" href="${escapeAttribute(normalizeProductUrl(item.urun_url))}" title="${escapeAttribute(normalizeProductUrl(item.urun_url))}"><strong>${item.urun_ad ?? "-"}</strong></a>`
        : `<strong>${item.urun_ad ?? "-"}</strong>`}
            </td>
            <td>${normalizeMarket(item.market_adi)}</td>
            <td>${formatCategory(item.urun_kategori)}</td>
            <td>${formatCurrency(item.eski_fiyat)}</td>
            <td>${formatCurrency(item.yeni_fiyat)}</td>
            <td>${formatContent(item.eski_gramaj, item.gramaj_birimi)}<br><small>${item.eski_adet_sayisi ? `${formatCount(item.eski_adet_sayisi)} adet` : "-"}</small></td>
            <td>${formatContent(item.yeni_gramaj, item.gramaj_birimi)}<br><small>${item.yeni_adet_sayisi ? `${formatCount(item.yeni_adet_sayisi)} adet` : "-"}</small></td>
            <td>${formatUnitPrice(item.eski_birim_fiyat, item.gramaj_birimi)}</td>
            <td>${formatUnitPrice(item.yeni_birim_fiyat, item.gramaj_birimi)}</td>
            <td>${getKarsilastirmaAciklamasi(item)}<br><small>${formatDate(item.eski_tarih)} → ${formatDate(item.yeni_tarih)} • Birim fiyat değişimi: ${item.birim_fiyat_degisim_yuzdesi === null || item.birim_fiyat_degisim_yuzdesi === undefined ? "-" : `${item.birim_fiyat_degisim_yuzdesi > 0 ? "+" : ""}${Number(item.birim_fiyat_degisim_yuzdesi).toFixed(2)}%`}</small></td>
        </tr>
    `).join("");
}

productComparisonsTableBody?.addEventListener("click", (event) => {
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

async function loadProductComparisons({ resetPage = false } = {}) {
    if (!productComparisonsTableBody) return;
    updateProductComparisonsTitle();
    if (resetPage) {
        currentPage = 1;
    }

    productComparisonsTableBody.innerHTML = `
        <tr>
            <td colspan="10" class="text-center text-secondary py-4">Karşılaştırmalar yükleniyor...</td>
        </tr>
    `;
    const params = buildComparisonsParams();

    try {
        const response = await fetch(`/dashboard/product-price-comparisons?${params.toString()}`);
        if (!response.ok) {
            throw new Error("product comparisons fetch failed");
        }

        const data = await response.json();
        const total = data.total ?? 0;
        const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
        if (currentPage > totalPages) {
            currentPage = totalPages;
            loadProductComparisons();
            return;
        }

        renderProductComparisons(data.items ?? []);
        updatePagination(total);
    } catch (error) {
        if (productComparisonsCount) {
            productComparisonsCount.textContent = "0 karşılaştırma";
        }
        if (productComparisonsSummary) {
            productComparisonsSummary.textContent = "Sayfalama bilgisi alınamadı.";
        }
        if (productComparisonsPageIndicator) {
            productComparisonsPageIndicator.textContent = "-";
        }
        if (productComparisonsPageNumberInput) {
            productComparisonsPageNumberInput.value = "1";
        }
        if (productComparisonsFirstPageButton) {
            productComparisonsFirstPageButton.disabled = true;
        }
        if (productComparisonsPrevPageButton) {
            productComparisonsPrevPageButton.disabled = true;
        }
        if (productComparisonsNextPageButton) {
            productComparisonsNextPageButton.disabled = true;
        }
        if (productComparisonsLastPageButton) {
            productComparisonsLastPageButton.disabled = true;
        }
        productComparisonsTableBody.innerHTML = `
            <tr>
                <td colspan="10" class="text-center text-secondary py-4">Karşılaştırmalar alınırken bir sorun oluştu.</td>
            </tr>
        `;
        syncComparisonQueryState();
    }
}

function goToPage(page) {
    const totalPages = Math.max(1, Math.ceil(totalComparisons / PAGE_SIZE));
    const nextPage = Math.min(Math.max(page, 1), totalPages);
    if (nextPage === currentPage) {
        updatePagination(totalComparisons);
        return;
    }

    currentPage = nextPage;
    loadProductComparisons();
}

productComparisonsPageNumberInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        event.preventDefault();
        const requestedPage = Number(productComparisonsPageNumberInput.value);
        if (!Number.isFinite(requestedPage)) return;
        goToPage(requestedPage);
    }
});

productComparisonsPageNumberInput?.addEventListener("blur", () => {
    const requestedPage = Number(productComparisonsPageNumberInput.value);
    if (!Number.isFinite(requestedPage)) {
        productComparisonsPageNumberInput.value = String(currentPage);
        return;
    }
    goToPage(requestedPage);
});

productComparisonsFirstPageButton?.addEventListener("click", () => {
    goToPage(1);
});

productComparisonsPrevPageButton?.addEventListener("click", () => {
    if (currentPage <= 1) return;
    currentPage -= 1;
    loadProductComparisons();
});

productComparisonsNextPageButton?.addEventListener("click", () => {
    const totalPages = Math.max(1, Math.ceil(totalComparisons / PAGE_SIZE));
    if (currentPage >= totalPages) return;
    currentPage += 1;
    loadProductComparisons();
});

productComparisonsLastPageButton?.addEventListener("click", () => {
    const totalPages = Math.max(1, Math.ceil(totalComparisons / PAGE_SIZE));
    goToPage(totalPages);
});

comparisonMarketFilter?.addEventListener("change", async () => {
    const selectedMarket = comparisonMarketFilter.value;
    await loadAvailableDates(selectedMarket, { preserveSelectedDates: false });
    await loadCategoryOptions(selectedMarket, { selectedValue: "" });
    loadProductComparisons({ resetPage: true });
});

comparisonCategoryFilter?.addEventListener("change", () => {
    loadProductComparisons({ resetPage: true });
});

comparisonUrunDurumuFilter?.addEventListener("change", () => {
    updateProductComparisonsTitle();
    loadProductComparisons({ resetPage: true });
});

comparisonFilterButton?.addEventListener("click", () => {
    loadProductComparisons({ resetPage: true });
});

const initialPage = Number(initialParams.get("page"));
if (Number.isFinite(initialPage) && initialPage >= 1) {
    currentPage = Math.floor(initialPage);
}

async function initializePage() {
    const initialMarket = normalizeMarketParamValue(initialParams.get("market"));
    const initialUrunDurumu = normalizeUrunDurumuParamValue(initialParams.get("urun_durumu"));
    if (comparisonMarketFilter) {
        comparisonMarketFilter.value = initialMarket;
    }
    if (comparisonUrunDurumuFilter) {
        comparisonUrunDurumuFilter.value = initialUrunDurumu;
    }
    uygulaKarsilastirmaDurumTemasi(initialUrunDurumu);
    updateProductComparisonsTitle();

    if (initialMarket) {
        await loadCategoryOptions(initialMarket, { selectedValue: initialCategoryFilterValue });
        const initialDateStartValue = formatDateInputValue(initialParams.get("tarih_baslangic") ?? "");
        const initialDateEndValue = formatDateInputValue(initialParams.get("tarih_bitis") ?? "");
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
        await loadAvailableDates(initialMarket, {
            preserveSelectedDates: true,
            selectedStartValue: normalizedInitialRange.startValue,
            selectedEndValue: normalizedInitialRange.endValue,
        });
    } else {
        resetComparisonCategoryFilter();
        updateDateFilterState(false);
    }

    loadProductComparisons();
}

initializePage();
