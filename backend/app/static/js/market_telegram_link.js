const telegramMarketLink = document.getElementById("telegramMarketLink");

const MARKET_TELEGRAM_URLS = {
    sok: "https://t.me/bitirmeshrinkflationsok",
    migros: "https://t.me/bitirmeshrinkflationmigros",
};

const MARKET_LABELS = {
    sok: "ŞOK",
    migros: "MİGROS",
};

const MARKET_SELECT_IDS = [
    "dashboardMarketFilter",
    "comparisonMarketFilter",
    "marketFilter",
];

function normalizeMarketValue(value) {
    const normalizedValue = String(value ?? "")
        .trim()
        .toLocaleLowerCase("tr-TR")
        .replaceAll("ş", "s")
        .replaceAll("ı", "i")
        .replaceAll("ğ", "g")
        .replaceAll("ü", "u")
        .replaceAll("ö", "o")
        .replaceAll("ç", "c");

    if (normalizedValue.startsWith("migros")) {
        return "migros";
    }

    if (normalizedValue.startsWith("sok")) {
        return "sok";
    }

    return "";
}

function findMarketFilterElement() {
    return MARKET_SELECT_IDS
        .map((id) => document.getElementById(id))
        .find((element) => element);
}

function getSelectedMarketValue() {
    const marketFilterElement = findMarketFilterElement();
    const filterValue = normalizeMarketValue(marketFilterElement?.value ?? "");
    if (filterValue) {
        return filterValue;
    }

    const initialParams = new URLSearchParams(window.location.search);
    return normalizeMarketValue(initialParams.get("market") ?? "");
}

function updateTelegramMarketLink() {
    if (!telegramMarketLink) {
        return;
    }

    const selectedMarket = getSelectedMarketValue();
    const marketUrl = MARKET_TELEGRAM_URLS[selectedMarket] ?? "";
    const isEnabled = Boolean(marketUrl);

    telegramMarketLink.href = marketUrl || "#";
    telegramMarketLink.classList.toggle("is-disabled", !isEnabled);
    telegramMarketLink.setAttribute("aria-disabled", String(!isEnabled));
    telegramMarketLink.tabIndex = isEnabled ? 0 : -1;
    telegramMarketLink.title = isEnabled
        ? `${MARKET_LABELS[selectedMarket]} Telegram grubunu aç`
        : "Telegram grubu için market seçin";
    telegramMarketLink.setAttribute("aria-label", telegramMarketLink.title);
}

function bindMarketFilterUpdates() {
    const marketFilterElement = findMarketFilterElement();
    if (!marketFilterElement) {
        updateTelegramMarketLink();
        return;
    }

    marketFilterElement.addEventListener("change", updateTelegramMarketLink);

    const observer = new MutationObserver(updateTelegramMarketLink);
    observer.observe(marketFilterElement, {
        childList: true,
        subtree: true,
        attributes: true,
    });

    updateTelegramMarketLink();
    window.setTimeout(updateTelegramMarketLink, 300);
    window.setTimeout(updateTelegramMarketLink, 1000);
}

telegramMarketLink?.addEventListener("click", (event) => {
    if (telegramMarketLink.classList.contains("is-disabled")) {
        event.preventDefault();
    }
});

bindMarketFilterUpdates();
