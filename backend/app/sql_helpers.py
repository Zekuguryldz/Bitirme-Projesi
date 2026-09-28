MARKET_TRANSLATION_SOURCE = "CGIOSUcgiosuÇĞİIÖŞÜçğıöşü"
MARKET_TRANSLATION_TARGET = "cgiosucgiosucgiiosucgiosu"


def build_normalized_text_sql(column_name: str) -> str:
    return (
        f"lower(translate(coalesce({column_name}, ''), "
        f"'{MARKET_TRANSLATION_SOURCE}', '{MARKET_TRANSLATION_TARGET}'))"
    )


def build_canonical_product_identity_sql(url_column_name: str, name_column_name: str) -> str:
    # Scraper duplicates can produce the same product URL slug with a different trailing product code.
    cleaned_url_sql = (
        "regexp_replace("
        "regexp_replace("
        f"lower(trim(coalesce({url_column_name}, ''))), "
        "'[?#].*$', "
        "''"
        "), "
        "'/+$', "
        "''"
        ")"
    )
    canonical_url_sql = (
        "regexp_replace("
        f"{cleaned_url_sql}, "
        "'(-p-)[^/?#]+(?=$|[/?#])', "
        "''"
        ")"
    )
    normalized_name_sql = build_normalized_text_sql(name_column_name)
    return f"coalesce(nullif({canonical_url_sql}, ''), nullif({normalized_name_sql}, ''))"
