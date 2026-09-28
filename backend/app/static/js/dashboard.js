const totalProductsEl = document.getElementById("total-products");
const totalProductsLabelEl = document.getElementById("total-products-label");
const totalProductsLinkEl = document.getElementById("totalProductsLink");
const updatedRecordsEl = document.getElementById("updated-records");
const updatedRecordsLabelEl = document.getElementById("updated-records-label");
const updatedRecordsLinkEl = document.getElementById("updatedRecordsLink");
const topPriceChangesTitleEl = document.getElementById("topPriceChangesTitle");
const topPriceChangesEl = document.getElementById("top-price-changes");
const productComparisonsTitleEl = document.getElementById("productComparisonsTitle");
const riskyProductsEl = document.getElementById("risky-products");
const dashboardSeciliUrunlerTitleEl = document.getElementById("dashboardSeciliUrunlerTitle");
const dashboardRiskyProductsCountEl = document.getElementById("dashboardRiskyProductsCount");
const dashboardRiskyProductsLinkEl = document.getElementById("dashboardRiskyProductsLink");
const productComparisonChartsEl = document.getElementById("productComparisonCharts");
const productComparisonScrollbarShellEl = document.getElementById("productComparisonScrollbarShell");
const productComparisonScrollbarRangeEl = document.getElementById("productComparisonScrollbarRange");
const dashboardMarketFilter = document.getElementById("dashboardMarketFilter");
const dashboardCategoryFilterWrap = document.getElementById("dashboardCategoryFilterWrap");
const dashboardCategoryFilter = document.getElementById("dashboardCategoryFilter");
const dashboardDateStart = document.getElementById("dashboardDateStart");
const dashboardDateEnd = document.getElementById("dashboardDateEnd");
const dashboardUrunDurumuFilter = document.getElementById("dashboardUrunDurumuFilter");
const dashboardApplyFiltersButton = document.getElementById("dashboardApplyFiltersButton");
const dashboardTemaKoku = document.getElementById("dashboardTemaKoku");
const dashboardUrunDurumuGostergesiYazi = document.getElementById("dashboardUrunDurumuGostergesiYazi");

let productComparisonCharts = [];
let dashboardLoadRequestToken = 0;
let isSyncingProductComparisonScroll = false;
const initialParams = new URLSearchParams(window.location.search);
const availableDatesCache = new Map();
const categoriesResponseCache = new Map();
const initialCategoryFilterValue = initialParams.get("kategori") ?? "";
const SUPPORTED_MARKETS = {
    sok: "ŞOK",
    migros: "MİGROS",
};
const DEFAULT_URUN_DURUMU = "zamlanmis_urunler";
const URUN_DURUMU_SECENEKLERI = {
    zamlanmis_urunler: {
        etiket: "Zamlanmış Ürünler",
        sayiEtiketi: "Zamlanmış Ürün Sayısı",
        ilkBesBasligi: "Birim Fiyatı Artmış 5 Ürün",
        grafikBasligi: "Zamlanmış Ürün Karşılaştırmaları",
        bolumBasligi: "Zamlanmış Ürünler",
        ilkBesBosMesaji: "Seçili filtreler için zamlanmış ürün bulunamadı.",
        bolumBosMesaji: "Seçili filtreler için zamlanmış ürün bulunamadı.",
        temaSinifi: "tema-zamlanmis-urunler",
        grafikRenkleri: {
            oncekiDolgu: "rgba(98, 142, 214, 0.84)",
            oncekiCizgi: "rgba(98, 142, 214, 1)",
            sonrakiDolgu: "rgba(245, 145, 66, 0.9)",
            sonrakiCizgi: "rgba(223, 118, 32, 1)",
        },
    },
    indirimdeki_urunler: {
        etiket: "İndirimli Ürünler",
        sayiEtiketi: "İndirimdeki Ürün Sayısı",
        ilkBesBasligi: "Birim Fiyatı Azalmış 5 Ürün",
        grafikBasligi: "İndirimdeki Ürün Karşılaştırmaları",
        bolumBasligi: "İndirimdeki Ürünler",
        ilkBesBosMesaji: "Seçili filtreler için indirimdeki ürün bulunamadı.",
        bolumBosMesaji: "Seçili filtreler için indirimdeki ürün bulunamadı.",
        temaSinifi: "tema-indirimdeki-urunler",
        grafikRenkleri: {
            oncekiDolgu: "rgba(98, 142, 214, 0.84)",
            oncekiCizgi: "rgba(98, 142, 214, 1)",
            sonrakiDolgu: "rgba(43, 166, 113, 0.9)",
            sonrakiCizgi: "rgba(28, 135, 88, 1)",
        },
    },
    shrinkflation_riskli_urunler: {
        etiket: "Shrinkflation Riskli Ürünler",
        sayiEtiketi: "Shrinkflation Riskli Ürün Sayısı",
        ilkBesBasligi: "Shrinkflation Riskli 5 Ürün",
        grafikBasligi: "Shrinkflation Riskli Ürün Karşılaştırmaları",
        bolumBasligi: "Shrinkflation Riskli Ürünler",
        ilkBesBosMesaji: "Seçili filtreler için shrinkflation riskli ürün bulunamadı.",
        bolumBosMesaji: "Seçili filtreler için shrinkflation riskli ürün bulunamadı.",
        temaSinifi: "tema-shrinkflation-riskli-urunler",
        grafikRenkleri: {
            oncekiDolgu: "rgba(98, 142, 214, 0.84)",
            oncekiCizgi: "rgba(98, 142, 214, 1)",
            sonrakiDolgu: "rgba(216, 72, 72, 0.88)",
            sonrakiCizgi: "rgba(193, 45, 45, 1)",
        },
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
    if (!value) return "Bilinmiyor";
    return CATEGORY_LABELS[value] ?? value;
}

function normalizeCategoryOptionValue(value) {
    if (!value) return "";
    const trimmedValue = String(value).trim();
    if (!trimmedValue) return "";
    return formatCategory(trimmedValue);
}

function formatMarket(value) {
    if (!value) return "Market bilgisi yok";
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
        dashboardUrunDurumuFilter?.value ?? initialParams.get("urun_durumu") ?? DEFAULT_URUN_DURUMU,
    );
}

function getUrunDurumuAyarlari(urunDurumu = getSeciliUrunDurumu()) {
    return URUN_DURUMU_SECENEKLERI[urunDurumu] ?? URUN_DURUMU_SECENEKLERI[DEFAULT_URUN_DURUMU];
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

function buildProductContainerTags(url, className) {
    const normalizedUrl = normalizeProductUrl(url);
    if (!normalizedUrl) {
        return {
            openTag: `<article class="${className}">`,
            closeTag: "</article>",
        };
    }

    const safeUrl = escapeAttribute(normalizedUrl);
    return {
        openTag: `<a class="${className} product-link-shell" href="${safeUrl}" title="${safeUrl}">`,
        closeTag: "</a>",
    };
}

function resetDashboardCategoryFilter({ hide = true } = {}) {
    if (dashboardCategoryFilterWrap) {
        dashboardCategoryFilterWrap.hidden = hide;
    }

    if (!dashboardCategoryFilter) return;

    dashboardCategoryFilter.disabled = true;
    dashboardCategoryFilter.innerHTML = '<option value="">Tüm Kategoriler</option>';
    dashboardCategoryFilter.value = "";
}

function showDashboardCategoryFilterLoading() {
    if (dashboardCategoryFilterWrap) {
        dashboardCategoryFilterWrap.hidden = false;
    }

    if (!dashboardCategoryFilter) return;

    dashboardCategoryFilter.disabled = true;
    dashboardCategoryFilter.innerHTML = '<option value="">Kategoriler yükleniyor...</option>';
}

function populateDashboardCategoryFilter(items, selectedValue = "") {
    if (!dashboardCategoryFilter) return;

    const categories = [...new Map(
        items
            .filter(Boolean)
            .map((category) => {
                const normalizedCategory = normalizeCategoryOptionValue(category);
                return [normalizedCategory.toLocaleLowerCase("tr-TR"), normalizedCategory];
            }),
    ).values()].sort((a, b) => a.localeCompare(b, "tr"));
    const normalizedSelectedValue = normalizeCategoryOptionValue(selectedValue);

    if (dashboardCategoryFilterWrap) {
        dashboardCategoryFilterWrap.hidden = false;
    }

    dashboardCategoryFilter.disabled = false;
    dashboardCategoryFilter.innerHTML = '<option value="">Tüm Kategoriler</option>' +
        categories.map((category) => `<option value="${category}">${category}</option>`).join("");
    dashboardCategoryFilter.value = categories.includes(normalizedSelectedValue) ? normalizedSelectedValue : "";
}

async function loadDashboardCategoryOptions(
    marketValue,
    { selectedValue = "" } = {},
) {
    if (!dashboardCategoryFilter) return;
    if (!marketValue) {
        resetDashboardCategoryFilter();
        return;
    }

    showDashboardCategoryFilterLoading();

    try {
        if (!categoriesResponseCache.has(marketValue)) {
            const response = await fetch(`/products/categories?market=${encodeURIComponent(marketValue)}`);
            if (!response.ok) {
                throw new Error("dashboard categories fetch failed");
            }

            const data = await response.json();
            categoriesResponseCache.set(marketValue, data.items ?? []);
        }

        populateDashboardCategoryFilter(categoriesResponseCache.get(marketValue) ?? [], selectedValue);
    } catch (error) {
        if (dashboardCategoryFilterWrap) {
            dashboardCategoryFilterWrap.hidden = false;
        }
        dashboardCategoryFilter.disabled = false;
        dashboardCategoryFilter.innerHTML = '<option value="">Tüm Kategoriler</option>';
        dashboardCategoryFilter.value = "";
    }
}

function uygulaDashboardDurumTemasi(urunDurumu = getSeciliUrunDurumu()) {
    const durumAyarlari = getUrunDurumuAyarlari(urunDurumu);

    if (dashboardTemaKoku) {
        dashboardTemaKoku.classList.remove(...DURUM_TEMA_SINIFLARI);
        dashboardTemaKoku.classList.add(durumAyarlari.temaSinifi);
    }

    if (dashboardUrunDurumuGostergesiYazi) {
        dashboardUrunDurumuGostergesiYazi.textContent = durumAyarlari.etiket;
    }
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

function buildNormalizedDateValue(year, month, day) {
    const numericYear = Number(year);
    const numericMonth = Number(month);
    const numericDay = Number(day);
    const date = new Date(Date.UTC(numericYear, numericMonth - 1, numericDay));

    if (
        Number.isNaN(date.getTime())
        || date.getUTCFullYear() !== numericYear
        || (date.getUTCMonth() + 1) !== numericMonth
        || date.getUTCDate() !== numericDay
    ) {
        return "";
    }

    const pad = (part) => String(part).padStart(2, "0");
    return `${numericYear}-${pad(numericMonth)}-${pad(numericDay)}`;
}

function parseDateInputValue(value) {
    if (!value) return "";

    const trimmedValue = String(value).trim();
    if (!trimmedValue) return "";

    const isoMatch = trimmedValue.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (isoMatch) {
        const [, year, month, day] = isoMatch;
        return buildNormalizedDateValue(year, month, day);
    }

    const localeMatch = trimmedValue.match(/^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/);
    if (localeMatch) {
        const [, day, month, year] = localeMatch;
        return buildNormalizedDateValue(year, month, day);
    }

    const normalizedValue = formatDateInputValue(trimmedValue);
    if (!normalizedValue) {
        return "";
    }

    const normalizedMatch = normalizedValue.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!normalizedMatch) {
        return "";
    }

    const [, year, month, day] = normalizedMatch;
    return buildNormalizedDateValue(year, month, day);
}

function formatDateDisplayValue(value) {
    const normalizedValue = parseDateInputValue(value);
    if (!normalizedValue) return "";

    const [, year, month, day] = normalizedValue.match(/^(\d{4})-(\d{2})-(\d{2})$/) ?? [];
    if (!year || !month || !day) return "";

    return `${day}.${month}.${year}`;
}

function convertNormalizedDateValueToPickerDate(value) {
    const normalizedValue = parseDateInputValue(value);
    if (!normalizedValue) return null;

    const match = normalizedValue.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) return null;

    const [, year, month, day] = match;
    return new Date(Number(year), Number(month) - 1, Number(day), 12, 0, 0);
}

function setDashboardDateInputValidity(input, isValid) {
    if (!input) return;
    input.classList.toggle("is-invalid", !isValid);
}

function getNormalizedDashboardDateValue(input) {
    const rawValue = input?.value?.trim() ?? "";
    if (!rawValue) {
        setDashboardDateInputValidity(input, true);
        return "";
    }

    const normalizedValue = parseDateInputValue(rawValue);
    setDashboardDateInputValidity(input, Boolean(normalizedValue));
    return normalizedValue;
}

function setDashboardDateInputValue(input, value) {
    if (!input) return;

    const normalizedValue = parseDateInputValue(value);
    const picker = input._flatpickr;
    const pickerDate = convertNormalizedDateValueToPickerDate(normalizedValue);

    if (!normalizedValue) {
        if (picker) {
            picker.clear();
        } else {
            input.value = "";
        }
        setDashboardDateInputValidity(input, true);
        return;
    }

    if (picker) {
        picker.setDate(pickerDate, true);
    } else {
        input.value = formatDateDisplayValue(normalizedValue);
    }

    setDashboardDateInputValidity(input, true);
}

function getDashboardDatePicker(input) {
    return input?._flatpickr ?? null;
}

function getDashboardDatePickerEnabledValues(availableDates = []) {
    return availableDates
        .map((value) => convertNormalizedDateValueToPickerDate(value))
        .filter(Boolean);
}

function updateDashboardDatePickerOptions(input, availableDates = []) {
    const picker = getDashboardDatePicker(input);
    if (!picker) return;

    picker.set("enable", getDashboardDatePickerEnabledValues(availableDates));
    picker.set("clickOpens", availableDates.length > 0);
}

function initializeDashboardDatePickers() {
    if (typeof window.flatpickr !== "function") {
        return;
    }

    const localeConfig = window.flatpickr.l10ns?.tr ?? "default";

    [dashboardDateStart, dashboardDateEnd].forEach((input) => {
        if (!input || getDashboardDatePicker(input)) {
            return;
        }

        window.flatpickr(input, {
            locale: localeConfig,
            dateFormat: "d.m.Y",
            disableMobile: true,
            allowInput: true,
            clickOpens: !input.disabled,
            onOpen() {
                setDashboardDateInputValidity(input, true);
            },
            onChange() {
                setDashboardDateInputValidity(input, true);
            },
        });
    });
}

function getNormalizedDashboardDateRange() {
    const startValue = getNormalizedDashboardDateValue(dashboardDateStart);
    const endValue = getNormalizedDashboardDateValue(dashboardDateEnd);
    const hasInvalidInput = (
        Boolean(dashboardDateStart?.value?.trim()) && !startValue
    ) || (
        Boolean(dashboardDateEnd?.value?.trim()) && !endValue
    );

    if (hasInvalidInput) {
        return {
            startValue: "",
            endValue: "",
            hasInvalidInput: true,
        };
    }

    if (startValue && !endValue) {
        return {
            startValue,
            endValue: startValue,
            hasInvalidInput: false,
        };
    }

    if (!startValue && endValue) {
        return {
            startValue: endValue,
            endValue,
            hasInvalidInput: false,
        };
    }

    if (!startValue || !endValue) {
        return {
            startValue,
            endValue,
            hasInvalidInput: false,
        };
    }

    if (startValue <= endValue) {
        return {
            startValue,
            endValue,
            hasInvalidInput: false,
        };
    }

    return {
        startValue: endValue,
        endValue: startValue,
        hasInvalidInput: false,
    };
}

function getDashboardFilters() {
    const market = normalizeMarketParamValue(
        dashboardMarketFilter?.value ?? initialParams.get("market") ?? "sok",
    ) || "sok";
    const category = market
        ? normalizeCategoryOptionValue(
            dashboardCategoryFilter?.value ?? initialParams.get("kategori") ?? "",
        )
        : "";
    const urunDurumu = getSeciliUrunDurumu();
    const { startValue, endValue, hasInvalidInput } = getNormalizedDashboardDateRange();
    if (startValue) setDashboardDateInputValidity(dashboardDateStart, true);
    if (endValue) setDashboardDateInputValidity(dashboardDateEnd, true);

    const hasFullDateRange = Boolean(startValue && endValue);

    return {
        market,
        marketLabel: SUPPORTED_MARKETS[market] ?? formatMarket(market),
        category,
        urunDurumu,
        startValue: hasFullDateRange ? startValue : "",
        endValue: hasFullDateRange ? endValue : "",
        hasInvalidInput,
    };
}

function buildDashboardParams(extraParams = {}) {
    const { market, category, urunDurumu, startValue, endValue } = getDashboardFilters();
    const params = new URLSearchParams({
        market,
        urun_durumu: urunDurumu,
    });

    if (market && category) {
        params.set("kategori", category);
    }

    if (startValue && endValue) {
        params.set("tarih_baslangic", startValue);
        params.set("tarih_bitis", endValue);
    }

    Object.entries(extraParams).forEach(([key, value]) => {
        if (value === null || value === undefined || value === "") {
            return;
        }
        params.set(key, String(value));
    });

    return params;
}

function buildUrl(path, extraParams = {}) {
    const query = buildDashboardParams(extraParams).toString();
    return query ? `${path}?${query}` : path;
}

function syncDashboardQueryState() {
    const nextQuery = buildDashboardParams().toString();
    const nextUrl = nextQuery
        ? `${window.location.pathname}?${nextQuery}`
        : window.location.pathname;
    window.history.replaceState({}, "", nextUrl);
}

function setDashboardApplyButtonState(isLoading) {
    if (!dashboardApplyFiltersButton) return;
    dashboardApplyFiltersButton.disabled = isLoading;
    dashboardApplyFiltersButton.textContent = isLoading ? "Listeleniyor..." : "Listele";
}

function updateDashboardDateFilterState(availableDates = []) {
    if (!dashboardDateStart || !dashboardDateEnd) {
        return;
    }

    const hasDates = availableDates.length > 0;
    const firstDate = hasDates ? availableDates[0] : "";
    const lastDate = hasDates ? availableDates[availableDates.length - 1] : "";
    const dateHint = hasDates
        ? `Mevcut tarihler: ${availableDates.map((value) => formatDateDisplayValue(value)).join(", ")}`
        : "Bu market için tarih bulunamadı.";

    [dashboardDateStart, dashboardDateEnd].forEach((input) => {
        input.disabled = !hasDates;
        input.placeholder = hasDates ? "Tarih seç" : "Tarih yok";
        input.title = dateHint;
        input.readOnly = !hasDates;
        updateDashboardDatePickerOptions(input, availableDates);

        if (!hasDates) {
            input.value = "";
            setDashboardDateInputValidity(input, true);
            getDashboardDatePicker(input)?.clear();
            return;
        }
    });

    if (hasDates) {
        dashboardDateStart.dataset.firstAvailableDate = firstDate;
        dashboardDateEnd.dataset.lastAvailableDate = lastDate;
    } else {
        delete dashboardDateStart.dataset.firstAvailableDate;
        delete dashboardDateEnd.dataset.lastAvailableDate;
    }
}

function buildDashboardDateRangeLabel(startValue, endValue) {
    const normalizedStartValue = parseDateInputValue(startValue);
    const normalizedEndValue = parseDateInputValue(endValue);

    if (!normalizedStartValue && !normalizedEndValue) {
        return "";
    }
    if (!normalizedStartValue || normalizedStartValue === normalizedEndValue) {
        return formatDateDisplayValue(normalizedEndValue || normalizedStartValue);
    }
    return `${formatDateDisplayValue(normalizedStartValue)} - ${formatDateDisplayValue(normalizedEndValue)}`;
}

function buildSeciliIlkBesBasligi(urunDurumu, tarihAraligiEtiketi) {
    const ayarlar = getUrunDurumuAyarlari(urunDurumu);
    return tarihAraligiEtiketi
        ? `${tarihAraligiEtiketi} Arası ${ayarlar.ilkBesBasligi}`
        : `İki Tarih Arası ${ayarlar.ilkBesBasligi}`;
}

function buildSeciliGrafikBasligi(urunDurumu, tarihAraligiEtiketi) {
    const ayarlar = getUrunDurumuAyarlari(urunDurumu);
    return tarihAraligiEtiketi
        ? `${tarihAraligiEtiketi} Arası ${ayarlar.grafikBasligi}`
        : `İki Tarih Arası ${ayarlar.grafikBasligi}`;
}

function buildSeciliSayiBasligi(marketLabel, urunDurumu, tarihAraligiEtiketi) {
    const ayarlar = getUrunDurumuAyarlari(urunDurumu);
    return tarihAraligiEtiketi
        ? `${tarihAraligiEtiketi} arası ${marketLabel} ${ayarlar.sayiEtiketi}`
        : `${marketLabel} ${ayarlar.sayiEtiketi}`;
}

function appendCategoryLabel(text, category) {
    return category ? `${text} (${category})` : text;
}

async function loadAvailableDates(
    marketValue,
    { preserveSelectedDates = true, applyDefaultRange = false } = {},
) {
    if (!marketValue) {
        updateDashboardDateFilterState([]);
        return;
    }

    try {
        if (!availableDatesCache.has(marketValue)) {
            const response = await fetch(`/products/dates?market=${encodeURIComponent(marketValue)}`);
            if (!response.ok) {
                throw new Error("dashboard dates fetch failed");
            }
            const data = await response.json();
            const dates = (data.items ?? [])
                .map((value) => formatDateInputValue(value))
                .filter(Boolean)
                .sort((a, b) => a.localeCompare(b));
            availableDatesCache.set(marketValue, dates);
        }

        const availableDates = availableDatesCache.get(marketValue) ?? [];
        updateDashboardDateFilterState(availableDates);

        if (!dashboardDateStart || !dashboardDateEnd) {
            return;
        }

        const currentStart = getNormalizedDashboardDateValue(dashboardDateStart);
        const currentEnd = getNormalizedDashboardDateValue(dashboardDateEnd);
        const hasValidRange = currentStart && currentEnd;

        if (hasValidRange) {
            setDashboardDateInputValue(dashboardDateStart, currentStart);
            setDashboardDateInputValue(dashboardDateEnd, currentEnd);
            return;
        }

        if (!preserveSelectedDates) {
            if (currentStart) {
                setDashboardDateInputValue(dashboardDateStart, currentStart);
            }
            if (currentEnd) {
                setDashboardDateInputValue(dashboardDateEnd, currentEnd);
            }
        }

        if (!applyDefaultRange) {
            return;
        }

        if (availableDates.length >= 2) {
            setDashboardDateInputValue(dashboardDateStart, availableDates[0]);
            setDashboardDateInputValue(dashboardDateEnd, availableDates[availableDates.length - 1]);
            return;
        }

        if (availableDates.length === 1) {
            setDashboardDateInputValue(dashboardDateStart, availableDates[0]);
            setDashboardDateInputValue(dashboardDateEnd, availableDates[0]);
            return;
        }

        if (!preserveSelectedDates) {
            dashboardDateStart.value = "";
            dashboardDateEnd.value = "";
        }
    } catch (error) {
        updateDashboardDateFilterState([]);
    }
}

function updateDashboardContext(summary = null) {
    const { market, marketLabel, category, urunDurumu, startValue, endValue } = getDashboardFilters();
    const urunDurumuAyarlari = getUrunDurumuAyarlari(urunDurumu);
    const snapshotDate = parseDateInputValue(summary?.toplam_urun_tarihi ?? "");
    const comparisonStartDate = parseDateInputValue(
        summary?.karsilastirma_baslangic_tarihi ?? startValue,
    );
    const comparisonEndDate = parseDateInputValue(
        summary?.karsilastirma_bitis_tarihi ?? endValue,
    );
    const comparisonDateRangeLabel = buildDashboardDateRangeLabel(
        comparisonStartDate,
        comparisonEndDate,
    );
    const productsParams = new URLSearchParams({ market });
    if (snapshotDate) {
        productsParams.set("tarih", snapshotDate);
    } else if (startValue && endValue) {
        productsParams.set("tarih_baslangic", startValue);
        productsParams.set("tarih_bitis", endValue);
    }
    const productsUrl = `/urunler?${productsParams.toString()}`;
    const karsilastirmaUrl = buildUrl("/urun-karsilastirmalari");

    uygulaDashboardDurumTemasi(urunDurumu);

    if (totalProductsLabelEl) {
        if (snapshotDate) {
            totalProductsLabelEl.textContent = `${formatDateDisplayValue(snapshotDate)} tarihli ${marketLabel} Veri Sayısı`;
        } else if (startValue || endValue) {
            totalProductsLabelEl.textContent = `Seçilen Tarihte ${marketLabel} Veri Sayısı`;
        } else {
            totalProductsLabelEl.textContent = `Son Çekilen ${marketLabel} Veri Sayısı`;
        }
    }
    if (updatedRecordsLabelEl) {
        updatedRecordsLabelEl.textContent = appendCategoryLabel(
            buildSeciliSayiBasligi(
                marketLabel,
                urunDurumu,
                comparisonDateRangeLabel,
            ),
            category,
        );
    }
    if (topPriceChangesTitleEl) {
        topPriceChangesTitleEl.textContent = appendCategoryLabel(
            buildSeciliIlkBesBasligi(
                urunDurumu,
                comparisonDateRangeLabel,
            ),
            category,
        );
    }
    if (productComparisonsTitleEl) {
        productComparisonsTitleEl.textContent = appendCategoryLabel(
            buildSeciliGrafikBasligi(
                urunDurumu,
                comparisonDateRangeLabel,
            ),
            category,
        );
    }
    if (dashboardSeciliUrunlerTitleEl) {
        dashboardSeciliUrunlerTitleEl.textContent = appendCategoryLabel(
            urunDurumuAyarlari.bolumBasligi,
            category,
        );
    }
    if (totalProductsLinkEl) {
        totalProductsLinkEl.href = productsUrl;
        totalProductsLinkEl.setAttribute("aria-label", `${marketLabel} ürün listesi sayfasına git`);
    }
    if (updatedRecordsLinkEl) {
        updatedRecordsLinkEl.href = karsilastirmaUrl;
        updatedRecordsLinkEl.setAttribute("aria-label", `${marketLabel} ürün karşılaştırmaları sayfasına git`);
    }
    if (dashboardRiskyProductsLinkEl) {
        dashboardRiskyProductsLinkEl.href = karsilastirmaUrl;
    }
}

function initializeDashboardFilters() {
    const initialMarket = normalizeMarketParamValue(initialParams.get("market")) || "sok";
    const initialUrunDurumu = normalizeUrunDurumuParamValue(initialParams.get("urun_durumu"));
    if (dashboardMarketFilter) {
        dashboardMarketFilter.value = initialMarket;
    }
    if (dashboardUrunDurumuFilter) {
        dashboardUrunDurumuFilter.value = initialUrunDurumu;
    }
    if (dashboardDateStart && initialParams.get("tarih_baslangic")) {
        setDashboardDateInputValue(
            dashboardDateStart,
            initialParams.get("tarih_baslangic"),
        );
    }
    if (dashboardDateEnd && initialParams.get("tarih_bitis")) {
        setDashboardDateInputValue(
            dashboardDateEnd,
            initialParams.get("tarih_bitis"),
        );
    }
    uygulaDashboardDurumTemasi(initialUrunDurumu);
}

function formatCurrency(value) {
    if (value === null || value === undefined) return "-";
    return new Intl.NumberFormat("tr-TR", {
        style: "currency",
        currency: "TRY",
        maximumFractionDigits: 2,
    }).format(Number(value));
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

function formatPercent(value) {
    if (value === null || value === undefined) return "-";
    const number = Number(value);
    const sign = number > 0 ? "+" : "";
    return `${sign}${number.toFixed(2)}%`;
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

function formatChangeReason(value) {
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
    return labels[value] ?? "İçerik değişimi";
}

function getShrinkflationVurgusu(item) {
    if (!item) return null;
    if (item.reason === "pack_count_reduced" || item.reason === "pack_count_increased") {
        return item.adet_degisim_yuzdesi;
    }
    if (item.reason === "unit_size_reduced" || item.reason === "unit_size_increased") {
        return item.birim_icerik_degisim_yuzdesi;
    }
    if (
        item.reason === "pack_count_and_unit_size_reduced"
        || item.reason === "pack_count_and_unit_size_increased"
    ) {
        return item.adet_degisim_yuzdesi ?? item.birim_icerik_degisim_yuzdesi;
    }
    return item.gramaj_degisim_yuzdesi ?? item.adet_degisim_yuzdesi ?? item.birim_icerik_degisim_yuzdesi;
}

function getSeciliDegisimRozeti(item, urunDurumu = getSeciliUrunDurumu()) {
    if (urunDurumu === "shrinkflation_riskli_urunler") {
        return item?.shrinkflation_orani_yuzdesi
            ?? item?.birim_fiyat_degisim_yuzdesi
            ?? getShrinkflationVurgusu(item);
    }
    return item?.birim_fiyat_degisim_yuzdesi ?? item?.fiyat_degisim_yuzdesi ?? null;
}

function getUrunDurumuAciklamasi(item, urunDurumu = getSeciliUrunDurumu()) {
    if (urunDurumu === "zamlanmis_urunler") {
        return "Birim fiyat arttı";
    }
    if (urunDurumu === "indirimdeki_urunler") {
        return "Birim fiyat azaldı";
    }
    return formatChangeReason(item?.reason);
}

function getComparisonMetric(item, urunDurumu = getSeciliUrunDurumu()) {
    const hasContentValues = item?.eski_gramaj !== null && item?.eski_gramaj !== undefined
        && item?.yeni_gramaj !== null && item?.yeni_gramaj !== undefined;
    const hasCountValues = item?.eski_adet_sayisi !== null && item?.eski_adet_sayisi !== undefined
        && item?.yeni_adet_sayisi !== null && item?.yeni_adet_sayisi !== undefined;
    const hasUnitContentValues = item?.eski_birim_gramaj !== null && item?.eski_birim_gramaj !== undefined
        && item?.yeni_birim_gramaj !== null && item?.yeni_birim_gramaj !== undefined;
    const hasUnitPriceValues = item?.eski_birim_fiyat !== null && item?.eski_birim_fiyat !== undefined
        && item?.yeni_birim_fiyat !== null && item?.yeni_birim_fiyat !== undefined;
    const hasPriceValues = item?.eski_fiyat !== null && item?.eski_fiyat !== undefined
        && item?.yeni_fiyat !== null && item?.yeni_fiyat !== undefined;

    if (urunDurumu !== "shrinkflation_riskli_urunler") {
        if (hasUnitPriceValues) {
            return {
                label: "Birim Fiyat",
                previousValue: Number(item.eski_birim_fiyat),
                nextValue: Number(item.yeni_birim_fiyat),
                formatValue(value) {
                    return formatUnitPrice(value, item.gramaj_birimi);
                },
            };
        }

        if (hasPriceValues) {
            return {
                label: "Fiyat",
                previousValue: Number(item.eski_fiyat),
                nextValue: Number(item.yeni_fiyat),
                formatValue(value) {
                    return formatCurrency(value);
                },
            };
        }
    }

    if (hasContentValues && Number(item.eski_gramaj) !== Number(item.yeni_gramaj)) {
        return {
            label: "Toplam İçerik",
            previousValue: Number(item.eski_gramaj),
            nextValue: Number(item.yeni_gramaj),
            formatValue(value) {
                return formatContent(value, item.gramaj_birimi);
            },
        };
    }

    if (hasCountValues && Number(item.eski_adet_sayisi) !== Number(item.yeni_adet_sayisi)) {
        return {
            label: "Paket Adedi",
            previousValue: Number(item.eski_adet_sayisi),
            nextValue: Number(item.yeni_adet_sayisi),
            formatValue(value) {
                return `${formatCount(value)} adet`;
            },
        };
    }

    if (hasUnitContentValues && Number(item.eski_birim_gramaj) !== Number(item.yeni_birim_gramaj)) {
        return {
            label: "Birim İçerik",
            previousValue: Number(item.eski_birim_gramaj),
            nextValue: Number(item.yeni_birim_gramaj),
            formatValue(value) {
                return formatContent(value, item.gramaj_birimi);
            },
        };
    }

    if (hasUnitPriceValues) {
        return {
            label: "Birim Fiyat",
            previousValue: Number(item.eski_birim_fiyat),
            nextValue: Number(item.yeni_birim_fiyat),
            formatValue(value) {
                return formatUnitPrice(value, item.gramaj_birimi);
            },
        };
    }

    if (hasPriceValues) {
        return {
            label: "Fiyat",
            previousValue: Number(item.eski_fiyat),
            nextValue: Number(item.yeni_fiyat),
            formatValue(value) {
                return formatCurrency(value);
            },
        };
    }

    if (hasContentValues) {
        return {
            label: "Toplam İçerik",
            previousValue: Number(item.eski_gramaj),
            nextValue: Number(item.yeni_gramaj),
            formatValue(value) {
                return formatContent(value, item.gramaj_birimi);
            },
        };
    }

    return {
        label: "Değer",
        previousValue: 0,
        nextValue: 0,
        formatValue(value) {
            return formatCount(value);
        },
    };
}

function getProductInitials(value) {
    if (!value) return "Ü";
    return value
        .split(" ")
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0])
        .join("")
        .toUpperCase();
}

function syncProductComparisonScroll(source, target) {
    if (!source || !target || isSyncingProductComparisonScroll) {
        return;
    }

    isSyncingProductComparisonScroll = true;
    target.scrollLeft = source.scrollLeft;
    window.requestAnimationFrame(() => {
        isSyncingProductComparisonScroll = false;
    });
}

function updateProductComparisonScrollbar() {
    if (
        !productComparisonChartsEl
        || !productComparisonScrollbarShellEl
        || !productComparisonScrollbarRangeEl
    ) {
        return;
    }

    const maxScroll = Math.max(
        0,
        Math.round(productComparisonChartsEl.scrollWidth - productComparisonChartsEl.clientWidth),
    );
    const hasOverflow = maxScroll > 4;
    productComparisonScrollbarShellEl.hidden = !hasOverflow;

    if (!hasOverflow) {
        productComparisonScrollbarRangeEl.max = "0";
        productComparisonScrollbarRangeEl.value = "0";
        return;
    }

    const visibleRatio = productComparisonChartsEl.clientWidth / productComparisonChartsEl.scrollWidth;
    const thumbWidth = Math.max(56, Math.round(productComparisonChartsEl.clientWidth * visibleRatio));
    productComparisonScrollbarRangeEl.max = String(maxScroll);
    productComparisonScrollbarRangeEl.value = String(
        Math.min(maxScroll, Math.round(productComparisonChartsEl.scrollLeft)),
    );
    productComparisonScrollbarRangeEl.style.setProperty(
        "--comparison-scroll-thumb-width",
        `${thumbWidth}px`,
    );
}

function renderTopPriceChanges(items) {
    if (!topPriceChangesEl) return;
    const urunDurumuAyarlari = getUrunDurumuAyarlari();
    if (!items.length) {
        topPriceChangesEl.textContent = urunDurumuAyarlari.ilkBesBosMesaji;
        return;
    }

    topPriceChangesEl.innerHTML = `
        <div class="price-move-list">
            ${items.map((item) => {
                const oncekiDeger = item.eski_birim_fiyat === null || item.eski_birim_fiyat === undefined
                    ? formatCurrency(item.eski_fiyat)
                    : formatUnitPrice(item.eski_birim_fiyat, item.gramaj_birimi);
                const yeniDeger = item.yeni_birim_fiyat === null || item.yeni_birim_fiyat === undefined
                    ? formatCurrency(item.yeni_fiyat)
                    : formatUnitPrice(item.yeni_birim_fiyat, item.gramaj_birimi);
                const productContainerTags = buildProductContainerTags(item.urun_url, "price-move-row");
                return `
                    ${productContainerTags.openTag}
                        <div class="price-move-main">
                            <div class="price-move-thumb">${getProductInitials(item.urun_ad)}</div>
                            <div class="price-move-copy">
                                <h3>${item.urun_ad ?? "-"}</h3>
                                <p>${formatCategory(item.urun_kategori)} • ${formatMarket(item.market_adi)} • ${getUrunDurumuAciklamasi(item)}</p>
                                <div class="price-move-old">${oncekiDeger}</div>
                            </div>
                        </div>
                        <div class="price-move-side">
                            <span class="price-move-badge">${formatPercent(getSeciliDegisimRozeti(item))}</span>
                            <strong>${yeniDeger}</strong>
                        </div>
                    ${productContainerTags.closeTag}
                `;
            }).join("")}
        </div>
    `;
}

function renderSeciliUrunler(items, total = null) {
    if (!riskyProductsEl) return;
    const urunDurumu = getSeciliUrunDurumu();
    const urunDurumuAyarlari = getUrunDurumuAyarlari(urunDurumu);
    if (dashboardRiskyProductsCountEl) {
        dashboardRiskyProductsCountEl.textContent = `${total ?? items.length} ürün`;
    }
    if (!items.length) {
        riskyProductsEl.textContent = urunDurumuAyarlari.bolumBosMesaji;
        return;
    }

    riskyProductsEl.innerHTML = `
        <div class="stack-list">
            ${items.map((item) => {
                const metric = getComparisonMetric(item, urunDurumu);
                const productContainerTags = buildProductContainerTags(item.urun_url, "list-row");
                return `
                    ${productContainerTags.openTag}
                        <div>
                            <h3>${item.urun_ad ?? "-"}</h3>
                            <p>${formatCategory(item.urun_kategori)} • ${formatMarket(item.market_adi)} • ${getUrunDurumuAciklamasi(item, urunDurumu)}</p>
                        </div>
                        <div class="text-end">
                            <strong>${formatPercent(getSeciliDegisimRozeti(item, urunDurumu))}</strong>
                            <span>${metric.label}: ${metric.formatValue(metric.previousValue)} → ${metric.formatValue(metric.nextValue)}</span>
                            <span>Etiket fiyatı: ${formatCurrency(item.eski_fiyat)} → ${formatCurrency(item.yeni_fiyat)}</span>
                        </div>
                    ${productContainerTags.closeTag}
                `;
            }).join("")}
        </div>
    `;
}

function renderProductComparisonCharts(items) {
    if (!productComparisonChartsEl) return;
    const urunDurumu = getSeciliUrunDurumu();
    const urunDurumuAyarlari = getUrunDurumuAyarlari(urunDurumu);
    const grafikRenkleri = urunDurumuAyarlari.grafikRenkleri;

    productComparisonCharts.forEach((chart) => chart.destroy());
    productComparisonCharts = [];

    if (!items.length) {
        productComparisonChartsEl.innerHTML = `
            <div class="placeholder-state">
                ${urunDurumuAyarlari.bolumBosMesaji}
            </div>
        `;
        updateProductComparisonScrollbar();
        return;
    }

    productComparisonChartsEl.innerHTML = items.map((item, index) => {
        const metric = getComparisonMetric(item, urunDurumu);
        const productContainerTags = buildProductContainerTags(item.urun_url, "comparison-card");
        return `
            ${productContainerTags.openTag}
                <div class="comparison-card-head">
                    <div class="comparison-card-copy">
                        <h3>${item.urun_ad ?? "-"}</h3>
                        <p>${formatCategory(item.urun_kategori)} • ${formatMarket(item.market_adi)} • ${getUrunDurumuAciklamasi(item, urunDurumu)}</p>
                    </div>
                    <span class="comparison-badge">${formatPercent(getSeciliDegisimRozeti(item, urunDurumu))}</span>
                </div>
                <div class="comparison-stats">
                    <div class="comparison-stat">
                        <span class="comparison-stat-label">Önceki ${metric.label}</span>
                        <strong>${metric.formatValue(metric.previousValue)}</strong>
                    </div>
                    <div class="comparison-stat comparison-stat-accent">
                        <span class="comparison-stat-label">Sonraki ${metric.label}</span>
                        <strong>${metric.formatValue(metric.nextValue)}</strong>
                    </div>
                </div>
                <div class="chart-shell comparison-chart-shell">
                    <canvas id="productComparisonChart${index}" aria-label="${item.urun_ad ?? "Ürün"} önceki ve sonraki ${metric.label.toLocaleLowerCase("tr-TR")} karşılaştırma grafiği"></canvas>
                </div>
                <div class="comparison-meta">
                    <span class="comparison-meta-item">
                        <small class="comparison-meta-label">${metric.label}</small>
                        <strong class="comparison-meta-value">${metric.formatValue(metric.previousValue)} → ${metric.formatValue(metric.nextValue)}</strong>
                    </span>
                    <span class="comparison-meta-item">
                        <small class="comparison-meta-label">Etiket fiyatı</small>
                        <strong class="comparison-meta-value">${formatCurrency(item.eski_fiyat)} → ${formatCurrency(item.yeni_fiyat)}</strong>
                    </span>
                    <span class="comparison-meta-item">
                        <small class="comparison-meta-label">Birim fiyat</small>
                        <strong class="comparison-meta-value">${formatUnitPrice(item.eski_birim_fiyat, item.gramaj_birimi)} → ${formatUnitPrice(item.yeni_birim_fiyat, item.gramaj_birimi)}</strong>
                    </span>
                    <span class="comparison-meta-item">
                        <small class="comparison-meta-label">Önceki kayıt</small>
                        <strong class="comparison-meta-value">${formatDate(item.eski_tarih)}</strong>
                    </span>
                    <span class="comparison-meta-item">
                        <small class="comparison-meta-label">Sonraki kayıt</small>
                        <strong class="comparison-meta-value">${formatDate(item.yeni_tarih)}</strong>
                    </span>
                </div>
            ${productContainerTags.closeTag}
        `;
    }).join("");

    items.forEach((item, index) => {
        const canvas = document.getElementById(`productComparisonChart${index}`);
        if (!canvas) return;

        const metric = getComparisonMetric(item, urunDurumu);
        const values = [metric.previousValue, metric.nextValue];
        const chart = new Chart(canvas, {
            type: "bar",
            data: {
                labels: ["Önceki", "Sonraki"],
                datasets: [
                    {
                        label: metric.label,
                        data: values,
                        barThickness: 34,
                        maxBarThickness: 38,
                        backgroundColor: [
                            grafikRenkleri.oncekiDolgu,
                            grafikRenkleri.sonrakiDolgu,
                        ],
                        borderColor: [
                            grafikRenkleri.oncekiCizgi,
                            grafikRenkleri.sonrakiCizgi,
                        ],
                        borderWidth: 1.5,
                        borderRadius: 10,
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        callbacks: {
                            label(context) {
                                return metric.formatValue(context.raw);
                            },
                        },
                    },
                },
                scales: {
                    x: {
                        ticks: {
                            color: "#66737c",
                        },
                        grid: {
                            display: false,
                        },
                    },
                    y: {
                        ticks: {
                            color: "#66737c",
                            callback(value) {
                                return metric.formatValue(value);
                            },
                        },
                        grid: {
                            color: "rgba(24, 33, 38, 0.08)",
                        },
                    },
                },
            },
        });

        productComparisonCharts.push(chart);
    });

    updateProductComparisonScrollbar();
}

async function fetchJson(url) {
    const response = await fetch(url);
    if (!response.ok) {
        throw new Error(`request failed: ${url}`);
    }
    return response.json();
}

async function loadDashboard({ syncQuery = false } = {}) {
    const requestToken = ++dashboardLoadRequestToken;

    updateDashboardContext();
    if (syncQuery) {
        syncDashboardQueryState();
    }

    try {
        const [summary, topChanges, productComparisons, seciliUrunler] = await Promise.all([
            fetchJson(buildUrl("/dashboard/summary")),
            fetchJson(buildUrl("/dashboard/top-price-changes")),
            fetchJson(buildUrl("/dashboard/product-price-comparisons")),
            fetchJson(buildUrl("/dashboard/product-price-comparisons", { limit: 1 })),
        ]);

        if (requestToken !== dashboardLoadRequestToken) {
            return;
        }

        updateDashboardContext(summary);

        if (totalProductsEl) {
            totalProductsEl.textContent = summary.toplam_urun ?? "-";
        }
        if (updatedRecordsEl) {
            updatedRecordsEl.textContent = getDashboardFilters().category
                ? (productComparisons.total ?? (productComparisons.items ?? []).length ?? "-")
                : (summary.bugun_guncellenen_kayit ?? "-");
        }

        renderTopPriceChanges(
            getDashboardFilters().category
                ? (productComparisons.items ?? []).slice(0, 5)
                : (topChanges.items ?? []),
        );
        renderProductComparisonCharts(productComparisons.items ?? []);
        renderSeciliUrunler(seciliUrunler.items ?? [], seciliUrunler.total ?? null);
    } catch (error) {
        if (requestToken !== dashboardLoadRequestToken) {
            return;
        }

        if (totalProductsEl) totalProductsEl.textContent = "-";
        if (updatedRecordsEl) updatedRecordsEl.textContent = "-";
        if (topPriceChangesEl) topPriceChangesEl.textContent = "Veriler alınırken bir sorun oluştu.";
        if (productComparisonChartsEl) {
            productComparisonChartsEl.innerHTML = `
                <div class="placeholder-state">
                    Grafik verileri alınırken bir sorun oluştu.
                </div>
            `;
        }
        updateProductComparisonScrollbar();
        if (dashboardRiskyProductsCountEl) dashboardRiskyProductsCountEl.textContent = "0 ürün";
        if (riskyProductsEl) riskyProductsEl.textContent = "Veriler alınırken bir sorun oluştu.";
    }
}

function normalizeDashboardDateInputs() {
    [dashboardDateStart, dashboardDateEnd].forEach((input) => {
        if (!input) return;
        const normalizedValue = getNormalizedDashboardDateValue(input);
        if (!input.value.trim()) {
            setDashboardDateInputValidity(input, true);
            return;
        }
        if (normalizedValue) {
            input.value = formatDateDisplayValue(normalizedValue);
        }
    });
}

async function applyDashboardFilters() {
    normalizeDashboardDateInputs();
    const { hasInvalidInput } = getDashboardFilters();
    if (hasInvalidInput) {
        return;
    }

    updateDashboardContext();
    setDashboardApplyButtonState(true);
    try {
        await loadDashboard({ syncQuery: true });
    } finally {
        setDashboardApplyButtonState(false);
    }
}

initializeDashboardFilters();
initializeDashboardDatePickers();
updateDashboardContext();

dashboardApplyFiltersButton?.addEventListener("click", async () => {
    await applyDashboardFilters();
});

dashboardMarketFilter?.addEventListener("change", async () => {
    const market = normalizeMarketParamValue(dashboardMarketFilter?.value ?? "") || "sok";
    await Promise.all([
        loadDashboardCategoryOptions(market, { selectedValue: "" }),
        loadAvailableDates(market, {
            preserveSelectedDates: false,
            applyDefaultRange: false,
        }),
    ]);
    updateDashboardContext();
});

dashboardCategoryFilter?.addEventListener("change", () => {
    updateDashboardContext();
});

dashboardUrunDurumuFilter?.addEventListener("change", () => {
    updateDashboardContext();
});

productComparisonChartsEl?.addEventListener("scroll", () => {
    if (!productComparisonScrollbarRangeEl || isSyncingProductComparisonScroll) {
        return;
    }

    isSyncingProductComparisonScroll = true;
    productComparisonScrollbarRangeEl.value = String(Math.round(productComparisonChartsEl.scrollLeft));
    window.requestAnimationFrame(() => {
        isSyncingProductComparisonScroll = false;
    });
});

productComparisonScrollbarRangeEl?.addEventListener("input", () => {
    if (!productComparisonChartsEl || isSyncingProductComparisonScroll) {
        return;
    }

    isSyncingProductComparisonScroll = true;
    productComparisonChartsEl.scrollLeft = Number(productComparisonScrollbarRangeEl.value || 0);
    window.requestAnimationFrame(() => {
        isSyncingProductComparisonScroll = false;
    });
});

[dashboardDateStart, dashboardDateEnd].forEach((input) => {
    input?.addEventListener("blur", () => {
        normalizeDashboardDateInputs();
    });
});

window.addEventListener("resize", updateProductComparisonScrollbar);
window.addEventListener("load", updateProductComparisonScrollbar);


async function bootstrapDashboard() {
    const market = normalizeMarketParamValue(
        dashboardMarketFilter?.value ?? initialParams.get("market") ?? "sok",
    ) || "sok";
    await Promise.all([
        loadDashboardCategoryOptions(market, {
            selectedValue: initialCategoryFilterValue,
        }),
        loadAvailableDates(market, {
            preserveSelectedDates: Boolean(
                initialParams.get("tarih_baslangic") && initialParams.get("tarih_bitis"),
            ),
            applyDefaultRange: !Boolean(
                initialParams.get("tarih_baslangic") && initialParams.get("tarih_bitis"),
            ),
        }),
    ]);
    updateDashboardContext();
    await loadDashboard({ syncQuery: true });
}

bootstrapDashboard();
