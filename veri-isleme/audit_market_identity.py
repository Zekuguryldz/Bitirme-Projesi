import argparse

import csv

import json

import re

from collections import defaultdict

from pathlib import Path

from typing import Iterable





def argumanlari_ayristir() -> argparse.Namespace:

    komut_ayristirici = argparse.ArgumentParser(

        description="Birden fazla market output klasorunde kimlik carpisma riskini audit eder."

    )

    komut_ayristirici.add_argument("input_dirs", nargs="+", type=Path)

    komut_ayristirici.add_argument("--output-json", type=Path, required=True)

    komut_ayristirici.add_argument("--output-csv", type=Path, required=True)

    return komut_ayristirici.argumanlari_ayristir()





def read_csv(yol: Path) -> list[dict[str, str]]:

    with yol.open("r", encoding="utf-8-sig", newline="") as handle:

        return list(csv.DictReader(handle))





def squeeze_spaces(value: str) -> str:

    return re.sub(r"\s+", " ", value.strip())





def write_csv(yol: Path, satirlar: list[dict[str, object]]) -> None:

    alan_adlari = [

        "identity_field",

        "identity_value",

        "status",

        "months",

        "product_names",

        "product_urls",

    ]

    yol.parent.mkdir(parents=True, exist_ok=True)

    with yol.open("w", encoding="utf-8", newline="") as handle:

        yazici = csv.DictWriter(handle, fieldnames=alan_adlari)

        yazici.writeheader()

        if satirlar:

            yazici.writerows(satirlar)





def iter_rows(girdi_dizinleri: Iterable[Path]):

    for girdi_dizini in girdi_dizinleri:

        label = girdi_dizini.name

        for satir in read_csv(girdi_dizini / "urunler.csv"):

            yield label, satir





def build_groups(girdi_dizinleri: list[Path], identity_field: str):

    groups: dict[str, list[tuple[str, dict[str, str]]]] = defaultdict(list)

    for label, satir in iter_rows(girdi_dizinleri):

        value = (satir.get(identity_field) or "").strip()

        if value:

            groups[value].append((label, satir))

    return groups





def summarize_groups(groups, identity_field: str) -> tuple[list[dict[str, object]], dict[str, int]]:

    satirlar: list[dict[str, object]] = []

    counts = {

        "total_keys": 0,

        "single_snapshot_keys": 0,

        "stable_keys": 0,

        "name_variation_only": 0,

        "hard_conflicts": 0,

    }

    for identity_value, items in sorted(groups.items()):

        counts["total_keys"] += 1

        months = sorted({label for label, _ in items})

        urun_adlari = {squeeze_spaces(satir["urun_ad"]) for _, satir in items}

        urun_adresleri = {squeeze_spaces(satir["urun_url"]) for _, satir in items if satir.get("urun_url")}



        if len(items) == 1:

            counts["single_snapshot_keys"] += 1

            continue



        if len(urun_adlari) == 1 and len(urun_adresleri) <= 1:

            counts["stable_keys"] += 1

            continue



        status = "name_variation_only"

        if len(urun_adresleri) > 1:

            status = "hard_conflict"

            counts["hard_conflicts"] += 1

        else:

            counts["name_variation_only"] += 1



        satirlar.append(

            {

                "identity_field": identity_field,

                "identity_value": identity_value,

                "status": status,

                "months": " | ".join(months),

                "product_names": " | ".join(sorted(urun_adlari)),

                "product_urls": " | ".join(sorted(urun_adresleri)),

            }

        )

    return satirlar, counts





def main() -> None:

    args = argumanlari_ayristir()

    tum_satirlar: list[dict[str, object]] = []

    ozet: dict[str, dict[str, int]] = {}



    for identity_field in ["site_product_code", "url_key"]:

        groups = build_groups(args.girdi_dizinleri, identity_field)

        satirlar, counts = summarize_groups(groups, identity_field)

        ozet[identity_field] = counts

        tum_satirlar.extend(satirlar)



    args.output_json.parent.mkdir(parents=True, exist_ok=True)

    args.output_json.write_text(json.dumps(ozet, ensure_ascii=False, indent=2), encoding="utf-8")

    write_csv(args.cikti_csv, tum_satirlar)

    print(f"Summary JSON: {args.output_json}")

    print(f"Detail CSV: {args.output_csv}")





if __name__ == "__main__":

    main()

