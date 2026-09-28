const riskyProductsTableBody = document.getElementById("riskyProductsTableBody");
const riskyProductsCountEl = document.getElementById("riskyProductsCount");
const initialParams = new URLSearchParams(window.location.search);
const initialMarket = initialParams.get("market")?.toLocaleLowerCase("tr-TR");
const initialDateStart = formatDateInputValue(initialParams.get("tarih_baslangic"));
const initialDateEnd = formatDateInputValue(initialParams.get("tarih_bitis"));
const SUPPORTED_MARKETS = {
    sok: "ŞOK",
    migros: "MİGROS",
};

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

function getSelectedMarketLabel() {
    return SUPPORTED_MARKETS[initialMarket] ?? null;
}

function getSelectedDateRangeLabel() {
    if (!initialDateStart || !initialDateEnd) return "";
    return `${initialDateStart} - ${initialDateEnd}`;
}

function buildRiskyProductsUrl() {
    if (!SUPPORTED_MARKETS[initialMarket]) {
        return "/dashboard/risky-products";
    }

    const params = new URLSearchParams({
        market: initialMarket,
    });
    if (initialDateStart) {
        params.set("tarih_baslangic", initialDateStart);
    }
    if (initialDateEnd) {
        params.set("tarih_bitis", initialDateEnd);
    }
    return `/dashboard/risky-products?${params.toString()}`;
}

function formatCount(value) {
    if (value === null || value === undefined) return "-";
    const number = Number(value);
    if (Number.isInteger(number)) return `${number}`;
    return number.toFixed(2);
}

function formatSize(value, unit) {
    if (value === null || value === undefined) return "-";
    return `${value} ${unit ?? ""}`.trim();
}

function formatChangeReason(value) {
    const labels = {
        total_content_reduced: "Toplam içerik azaldı",
        pack_count_reduced: "Paket adedi azaldı",
        unit_size_reduced: "Birim içerik azaldı",
        pack_count_and_unit_size_reduced: "Adet ve birim içerik azaldı",
    };
    return labels[value] ?? "Shrinkflation riski";
}

function getPrimaryRiskChange(item) {
    if (!item) return null;
    if (item.reason === "pack_count_reduced") {
        return item.adet_degisim_yuzdesi;
    }
    if (item.reason === "unit_size_reduced") {
        return item.birim_icerik_degisim_yuzdesi;
    }
    if (item.reason === "pack_count_and_unit_size_reduced") {
        return item.adet_degisim_yuzdesi ?? item.birim_icerik_degisim_yuzdesi;
    }
    return item.gramaj_degisim_yuzdesi ?? item.adet_degisim_yuzdesi ?? item.birim_icerik_degisim_yuzdesi;
}

async function loadRiskyProducts() {
    if (!riskyProductsTableBody) return;
    const marketLabel = getSelectedMarketLabel();

    try {
        const response = await fetch(buildRiskyProductsUrl());
        if (!response.ok) {
            throw new Error("risky products fetch failed");
        }

        const data = await response.json();
        const items = data.items ?? [];
        const total = Number(data.total ?? items.length ?? 0);

        if (riskyProductsCountEl) {
            riskyProductsCountEl.textContent = `${total} tespit`;
        }

        if (!items.length) {
            riskyProductsTableBody.innerHTML = `
                <tr>
                    <td colspan="10" class="text-center text-secondary py-4">${marketLabel ? `${marketLabel} için ` : ""}${getSelectedDateRangeLabel() ? `${getSelectedDateRangeLabel()} arasında ` : ""}shrinkflation riski taşıyan ürün bulunamadı.</td>
                </tr>
            `;
            return;
        }

        riskyProductsTableBody.innerHTML = items.map((item) => `
            <tr>
                <td>${item.urun_ad ?? "-"}</td>
                <td>${formatCurrency(item.eski_fiyat)}</td>
                <td>${formatCurrency(item.yeni_fiyat)}</td>
                <td>${formatSize(item.eski_gramaj, item.gramaj_birimi)}<br><small>${item.eski_adet_sayisi ? `${formatCount(item.eski_adet_sayisi)} adet` : "-"}</small></td>
                <td>${formatSize(item.yeni_gramaj, item.gramaj_birimi)}<br><small>${item.yeni_adet_sayisi ? `${formatCount(item.yeni_adet_sayisi)} adet` : "-"}</small></td>
                <td>${formatUnitPrice(item.eski_birim_fiyat, item.gramaj_birimi)}</td>
                <td>${formatUnitPrice(item.yeni_birim_fiyat, item.gramaj_birimi)}</td>
                <td>${formatChangeReason(item.reason)}<br><small>Ana değişim: ${formatPercent(getPrimaryRiskChange(item))} • Birim fiyat: ${formatPercent(item.birim_fiyat_degisim_yuzdesi)}</small></td>
                <td>${formatDate(item.eski_tarih)}</td>
                <td>${formatDate(item.yeni_tarih ?? item.kazima_tarihi)}</td>
            </tr>
        `).join("");
    } catch (error) {
        if (riskyProductsCountEl) {
            riskyProductsCountEl.textContent = "0 tespit";
        }
        riskyProductsTableBody.innerHTML = `
            <tr>
                <td colspan="10" class="text-center text-secondary py-4">Veriler alınırken bir sorun oluştu.</td>
            </tr>
        `;
    }
}

document.addEventListener("DOMContentLoaded", loadRiskyProducts);
