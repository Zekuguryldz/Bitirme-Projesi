import argparse

import csv

import re

from collections import defaultdict

from dataclasses import dataclass

from pathlib import Path

from typing import Dict, Iterable, Optional



from product_identity import clean_optional_text, extract_url_key





PRODUCT_URL_RE = re.compile(r"-p-[A-Za-z0-9]+(?=$|[/?#])", re.IGNORECASE)

CATEGORY_URL_HINT_RE = re.compile(r"(-c-[A-Za-z0-9]+|[?&]page=\d+)", re.IGNORECASE)

NAME_TRANSLATION = str.maketrans(

    {

        "ç": "c",

        "Ç": "c",

        "ğ": "g",

        "Ğ": "g",

        "ı": "i",

        "İ": "i",

        "ö": "o",

        "Ö": "o",

        "ş": "s",

        "Ş": "s",

        "ü": "u",

        "Ü": "u",

    }

)

SAFE_DROP_TOKENS = {

    "adet",

    "cam",

    "kutu",

    "makarna",

    "paket",

    "paketi",

    "pet",

    "poset",

    "zipper",

}





@dataclass(frozen=True)

class ReferenceIndexes:

    exact_index: Dict[str, list[dict[str, str]]]

    normalize_indeks: Dict[str, list[dict[str, str]]]

    token_bag_index: Dict[str, list[dict[str, str]]]

    reduced_token_bag_index: Dict[str, list[dict[str, str]]]





def is_product_url(adres: object) -> bool:

    normalize_edilmis = clean_optional_text(adres)

    if not normalize_edilmis:

        return False

    return PRODUCT_URL_RE.search(normalize_edilmis) is not None





def needs_url_backfill(adres: object) -> bool:

    normalize_edilmis = clean_optional_text(adres)

    if not normalize_edilmis:

        return True

    if is_product_url(normalize_edilmis):

        return False

    if CATEGORY_URL_HINT_RE.search(normalize_edilmis) is not None:

        return True

    return True





def normalize_name_for_match(ad: object) -> Optional[str]:

    normalize_edilmis = clean_optional_text(ad)

    if not normalize_edilmis:

        return None

    normalize_edilmis = normalize_edilmis.translate(NAME_TRANSLATION).lower()

    normalize_edilmis = normalize_edilmis.replace("&", " ve ")

    normalize_edilmis = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", normalize_edilmis)

    normalize_edilmis = re.sub(r"(?<=\d)\s*[*xX]\s*(?=\d)", " x ", normalize_edilmis)

    normalize_edilmis = re.sub(r"\bgr\b", "g", normalize_edilmis)

    normalize_edilmis = re.sub(r"\blt\b", "l", normalize_edilmis)

    normalize_edilmis = re.sub(r"[^\w\s]", " ", normalize_edilmis)

    normalize_edilmis = re.sub(r"\s+", " ", normalize_edilmis).strip()

    return normalize_edilmis or None





def token_bag_key(ad: object, *, drop_safe_tokens: bool = False) -> Optional[str]:

    normalize_edilmis = normalize_name_for_match(ad)

    if not normalize_edilmis:

        return None



    tokens = normalize_edilmis.split()

    if drop_safe_tokens:

        tokens = [token for token in tokens if token not in SAFE_DROP_TOKENS]

    if not tokens:

        return None

    return " ".join(sorted(tokens))





def pick_first(satir: dict[str, str], *columns: str) -> Optional[str]:

    for column in columns:

        value = clean_optional_text(satir.get(column))

        if value is not None:

            return value

    return None





def build_reference_indexes(

    satirlar: Iterable[dict[str, str]],

) -> ReferenceIndexes:

    exact_index: Dict[str, list[dict[str, str]]] = defaultdict(list)

    normalize_indeks: Dict[str, list[dict[str, str]]] = defaultdict(list)

    token_bag_index: Dict[str, list[dict[str, str]]] = defaultdict(list)

    reduced_token_bag_index: Dict[str, list[dict[str, str]]] = defaultdict(list)



    for satir in satirlar:

        urun_adi = pick_first(satir, "product_name", "urun_ad", "product_name_from_listing")

        urun_adresi = pick_first(satir, "product_url", "urun_url")

        if not urun_adi or not urun_adresi:

            continue



        entry = {

            "product_name": urun_adi,

            "product_url": urun_adresi,

            "site_product_code": pick_first(satir, "product_code", "site_product_code"),

            "url_key": pick_first(satir, "url_key") or extract_url_key(urun_adresi),

            "item_count": pick_first(satir, "item_count"),

        }

        exact_index[urun_adi].append(entry)



        normalize_ad = normalize_name_for_match(urun_adi)

        if normalize_ad:

            normalize_indeks[normalize_ad].append(entry)



        bag_key = token_bag_key(urun_adi)

        if bag_key:

            token_bag_index[bag_key].append(entry)



        reduced_bag_key = token_bag_key(urun_adi, drop_safe_tokens=True)

        if reduced_bag_key:

            reduced_token_bag_index[reduced_bag_key].append(entry)



    return ReferenceIndexes(

        exact_index=exact_index,

        normalize_indeks=normalize_indeks,

        token_bag_index=token_bag_index,

        reduced_token_bag_index=reduced_token_bag_index,

    )





def resolve_unique_match(

    index: Dict[str, list[dict[str, str]]],

    key: Optional[str],

    tekil_eslesme_turu: str,

    belirsiz_eslesme_turu: str,

) -> tuple[Optional[dict[str, str]], str]:

    if not key:

        return None, "no_match"



    eslesmeler = index.get(key, [])

    if len(eslesmeler) == 1:

        return eslesmeler[0], tekil_eslesme_turu

    if len(eslesmeler) > 1:

        return None, belirsiz_eslesme_turu

    return None, "no_match"





def resolve_product_url(

    urun_adi: object,

    indexes: ReferenceIndexes,

) -> tuple[Optional[dict[str, str]], str]:

    exact_name = clean_optional_text(urun_adi)

    if exact_name:

        tam_eslesmeler = indexes.exact_index.get(exact_name, [])

        if len(tam_eslesmeler) == 1:

            return tam_eslesmeler[0], "exact_name"

        if len(tam_eslesmeler) > 1:

            return None, "ambiguous_exact_name"



    normalize_ad = normalize_name_for_match(urun_adi)

    eslesen_satir, eslesme_turu = resolve_unique_match(

        indexes.normalize_indeks,

        normalize_ad,

        "normalized_name",

        "ambiguous_normalized_name",

    )

    if eslesen_satir or eslesme_turu.startswith("ambiguous"):

        return eslesen_satir, eslesme_turu



    bag_key = token_bag_key(urun_adi)

    eslesen_satir, eslesme_turu = resolve_unique_match(

        indexes.token_bag_index,

        bag_key,

        "token_bag_name",

        "ambiguous_token_bag_name",

    )

    if eslesen_satir or eslesme_turu.startswith("ambiguous"):

        return eslesen_satir, eslesme_turu



    reduced_bag_key = token_bag_key(urun_adi, drop_safe_tokens=True)

    eslesen_satir, eslesme_turu = resolve_unique_match(

        indexes.reduced_token_bag_index,

        reduced_bag_key,

        "reduced_token_bag_name",

        "ambiguous_reduced_token_bag_name",

    )

    if eslesen_satir or eslesme_turu.startswith("ambiguous"):

        return eslesen_satir, eslesme_turu



    return None, "no_match"





def default_output_paths(eski_yol: Path) -> tuple[Path, Path]:

    guncellenen = eski_yol.with_name(f"{legacy_path.stem}_url_backfilled.csv")

    audit = eski_yol.with_name(f"{legacy_path.stem}_url_backfill_audit.csv")

    return guncellenen, audit





def backfill_rows(

    eski_satirlar: list[dict[str, str]],

    indexes: ReferenceIndexes,

) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, int]]:

    guncellenen_satirlar: list[dict[str, str]] = []

    denetim_satirlari: list[dict[str, str]] = []

    stats = {

        "total": 0,

        "updated": 0,

        "already_product_url": 0,

        "no_match": 0,

        "ambiguous": 0,

    }



    for satir in eski_satirlar:

        stats["total"] += 1

        guncellenen_satir = dict(satir)

        urun_adi = pick_first(satir, "urun_ad", "product_name")

        guncel_adres = pick_first(satir, "urun_url", "product_url")



        status = "unchanged"

        eslesme_turu = ""

        cozulen_adres = guncel_adres or ""

        cozulen_kod = ""

        cozulen_adres_anahtari = ""



        if not needs_url_backfill(guncel_adres):

            stats["already_product_url"] += 1

            status = "already_product_url"

        else:

            eslesen_satir, eslesme_turu = resolve_product_url(urun_adi, indexes)

            if eslesen_satir:

                cozulen_adres = eslesen_satir["product_url"]

                cozulen_kod = eslesen_satir.get("site_product_code") or ""

                cozulen_adres_anahtari = eslesen_satir.get("url_key") or ""

                status = "backfilled"

                stats["updated"] += 1



                if "urun_url" in guncellenen_satir:

                    guncellenen_satir["urun_url"] = cozulen_adres

                if "product_url" in guncellenen_satir:

                    guncellenen_satir["product_url"] = cozulen_adres

                if "site_product_code" in guncellenen_satir and cozulen_kod:

                    guncellenen_satir["site_product_code"] = cozulen_kod

                if "url_key" in guncellenen_satir and cozulen_adres_anahtari:

                    guncellenen_satir["url_key"] = cozulen_adres_anahtari

            else:

                if eslesme_turu.startswith("ambiguous"):

                    stats["ambiguous"] += 1

                else:

                    stats["no_match"] += 1

                status = "unresolved"



        guncellenen_satirlar.append(guncellenen_satir)

        denetim_satirlari.append(

            {

                "row_id": pick_first(satir, "id", "urun_id", "kayit_id") or "",

                "product_name": urun_adi or "",

                "old_url": guncel_adres or "",

                "new_url": cozulen_adres,

                "status": status,

                "match_type": eslesme_turu,

                "reference_site_product_code": cozulen_kod,

                "reference_url_key": cozulen_adres_anahtari,

            }

        )



    return guncellenen_satirlar, denetim_satirlari, stats





def write_csv(yol: Path, satirlar: list[dict[str, str]]) -> None:

    if not satirlar:

        return

    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=list(satirlar[0].keys()))

        yazici.writeheader()

        yazici.writerows(satirlar)





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Eski kategori URL'lerini guncel urun URL'leri ile urun adi uzerinden geri doldurur."

    )

    komut_ayristirici.add_argument("legacy_csv", type=Path)

    komut_ayristirici.add_argument("reference_csv", type=Path)

    komut_ayristirici.add_argument("--output-csv", type=Path, default=None)

    komut_ayristirici.add_argument("--audit-csv", type=Path, default=None)

    return komut_ayristirici.argumanlari_ayristir()





def main() -> None:

    args = argumanlari_ayristir()

    cikti_csv, denetim_csv = default_output_paths(args.legacy_csv)

    if args.cikti_csv is not None:

        cikti_csv = args.cikti_csv

    if args.denetim_csv is not None:

        denetim_csv = args.denetim_csv



    with args.legacy_csv.open("r", encoding="utf-8-sig", newline="") as handle:

        eski_satirlar = list(csv.DictReader(handle))



    with args.reference_csv.open("r", encoding="utf-8-sig", newline="") as handle:

        referans_satirlar = list(csv.DictReader(handle))



    indexes = build_reference_indexes(referans_satirlar)

    guncellenen_satirlar, denetim_satirlari, stats = backfill_rows(eski_satirlar, indexes)



    write_csv(cikti_csv, guncellenen_satirlar)

    write_csv(denetim_csv, denetim_satirlari)



    print(f"Updated CSV: {output_csv}")

    print(f"Audit CSV: {audit_csv}")

    print(f"Toplam satir: {stats['total']}")

    print(f"Geri doldurulan URL: {stats['updated']}")

    print(f"Zaten dogru urun URL'si olan: {stats['already_product_url']}")

    print(f"Eslesmeyen: {stats['no_match']}")

    print(f"Belirsiz eslesme: {stats['ambiguous']}")





if __name__ == "__main__":

    main()

