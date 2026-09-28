import re

from dataclasses import dataclass

from typing import Iterator, Optional

from urllib.parse import urlparse





PRODUCT_SEGMENT_RE = re.compile(r"(?P<segment>[^/]+-p-(?P<suffix>[A-Za-z0-9]+))$", re.IGNORECASE)





def clean_optional_text(value: object) -> Optional[str]:

    if value is None:

        return None



    text = str(value).strip()

    if not text or text.lower() == "nan":

        return None

    return text





def extract_url_key(adres: object) -> Optional[str]:

    normalize_adres = clean_optional_text(adres)

    if not normalize_adres:

        return None



    ayristirilmis = urlparse(normalize_adres)

    segment = ayristirilmis.path.rstrip("/").split("/")[-1]

    eslesme = PRODUCT_SEGMENT_RE.fullmatch(segment)

    if not eslesme:

        return None



    host = ayristirilmis.netloc.lower()

    suffix = eslesme.group("suffix")

    if host.endswith("sokmarket.com.tr") and suffix.isdigit():

        return suffix

    return eslesme.group("segment")





@dataclass(frozen=True)

class ProductIdentity:

    site_urun_kodu: Optional[str]

    adres_anahtari: Optional[str]

    urun_url: Optional[str]



    def adaylar(self) -> Iterator[tuple[str, str]]:

        if self.site_urun_kodu:

            yield "site_product_code", self.site_urun_kodu

        if self.adres_anahtari:

            yield "url_key", self.adres_anahtari

        if self.urun_url:

            yield "urun_url", self.urun_url





def build_product_identity(site_urun_kodu: object = None, urun_url: object = None) -> ProductIdentity:

    normalize_adres = clean_optional_text(urun_url)

    return ProductIdentity(

        site_urun_kodu=clean_optional_text(site_urun_kodu),

        adres_anahtari=extract_url_key(normalize_adres),

        urun_url=normalize_adres,

    )

