from __future__ import annotations

import shutil
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
W = f"{{{W_NS}}}"

ET.register_namespace("w", W_NS)


PROJECT_TITLE = "SHRINKFLATION TESPİT VE TAKİP SİSTEMİ"
PROJECT_TITLE_EN = "SHRINKFLATION DETECTION AND MONITORING SYSTEM"
AUTHOR_NAME = "Zeki Uğur Yıldız"
APPROVAL_NAME = "Dr. Öğr. Üyesi [Danışman Adı]"
THESIS_DATE = "Mayıs 2026"


TURKISH_ABSTRACT = (
    "Bu çalışmada market ürünlerinde görülen fiyat, gramaj ve paket adedi değişimlerini izleyerek "
    "shrinkflation riskini ortaya koyan bir web uygulaması geliştirilmiştir. Çalışmanın çıkış noktası, "
    "etiket fiyatı sabit kalsa bile ürün miktarının azalması sonucunda tüketicinin fiilen daha yüksek "
    "birim fiyat ödemesidir. Geliştirilen sistem FastAPI tabanlı bir servis katmanı, SQLAlchemy ile "
    "veritabanı erişimi, Supabase PostgreSQL üzerinde tutulan ürün ve fiyat zaman serileri ile Jinja2 "
    "tabanlı bir gösterim arayüzünden oluşmaktadır. Uygulama; ürün, market ve fiyat zaman serisi "
    "tablolarını kullanarak tarih bazlı karşılaştırmalar yapar, ürün adlarından gramaj ve paket "
    "bilgilerini ayrıştırır, farklı ölçü birimlerini normalize eder ve ardışık kayıtları eşleştirerek "
    "birim fiyat bozulmalarını tespit eder. İçerik azalması ile birlikte birim fiyat artışı gözlenen "
    "durumlar shrinkflation riski olarak işaretlenmektedir. Dashboard katmanında market, kategori, tarih "
    "aralığı ve ürün durumu filtreleri sağlanmış; ayrıca haftalık özetlerin Telegram üzerinden otomatik "
    "iletilmesi için bildirim modülü eklenmiştir. Testler; fiyat karşılaştırma mantığı, tarih çözümleme, "
    "market filtreleme ve bildirim üretimi gibi kritik iş kurallarını doğrulamaktadır. Sonuç olarak proje, "
    "shrinkflation olgusunu yalnızca kavramsal olarak tartışmak yerine, açıklanabilir kurallarla çalışan ve "
    "karşılaştırmalı veri sunan uygulanabilir bir karar destek aracına dönüştürmektedir."
)


ENGLISH_ABSTRACT = (
    "This study presents a web application that monitors price, package size and pack-count changes in "
    "retail products in order to detect shrinkflation risk. The core motivation is that consumers may end "
    "up paying a higher unit price even when the shelf price appears unchanged. The implemented system "
    "combines a FastAPI-based service layer, SQLAlchemy for database access, Supabase PostgreSQL for "
    "product and price time-series storage, and a Jinja2-based dashboard interface. The application performs "
    "date-driven product comparisons, extracts quantity and pack information from product names, normalizes "
    "measurement units, and compares adjacent snapshots to identify unit-price deterioration. Cases where "
    "content decreases while unit price increases are marked as shrinkflation risks. The dashboard supports "
    "market, category, date-range and product-status filters, and the notification layer can deliver weekly "
    "summaries through Telegram. Automated tests validate the main business rules including price comparison, "
    "date resolution, market filtering and notification generation. As a result, the project turns "
    "shrinkflation from a purely conceptual discussion into a practical and explainable decision-support tool "
    "that can be used for comparative retail monitoring."
)


INTRO_PARAGRAPHS = [
    (
        "Enflasyonist dönemlerde fiyat artışları her zaman doğrudan etiket fiyatı üzerinden görülmemektedir. "
        "Bazı ürünlerde fiyat sabit kalırken paket boyutunun küçülmesi, adet sayısının azalması veya toplam "
        "içeriğin düşmesi sonucunda tüketici fark etmeden daha yüksek birim fiyat ödeyebilmektedir. Office for "
        "National Statistics, ürün ağırlığı düştüğünde fakat fiyat aynı kaldığında bunun fiilen ek maliyet "
        "yarattığını ve istatistiklerde dikkate alınmadığında enflasyonun eksik ölçülebileceğini göstermektedir "
        "[1]. Benzer biçimde birim fiyat bilgisinin ürün karşılaştırmasını kolaylaştırdığı ve tüketicinin daha "
        "doğru karar vermesine yardım ettiği vurgulanmaktadır [2], [5]."
    ),
    (
        "Bu bitirme projesinin amacı, market verilerinden hareketle fiyat ve içerik değişimlerini izleyen, "
        "shrinkflation riskini açıklanabilir kurallarla belirleyen ve sonuçları kullanıcıya karşılaştırmalı "
        "olarak sunan bir yazılım geliştirmektir. Çalışmanın devamında önce konuya ilişkin literatür ve benzer "
        "yaklaşımlar özetlenmiş, ardından sistem tasarımı ile tespit yöntemi açıklanmış, son olarak uygulamanın "
        "gerçeklenmesi, test yaklaşımı ve sınırlılıkları değerlendirilmiştir."
    ),
]


LITERATURE_PARAGRAPHS = [
    (
        "Güncel literatür shrinkflation olgusunun istisnai değil, birçok kategoride gözlemlenebilen sistematik bir "
        "fiyatlama davranışı olduğunu göstermektedir. Janssen ve Kasinger, ABD perakende gıda verileri üzerinde "
        "yaptıkları çalışmada küçülmenin büyümeye kıyasla çok daha yaygın olduğunu, çoğu durumda nominal fiyatın "
        "eşzamanlı olarak düşmediğini ve tüketicilerin fiyat değişimlerine, paket boyutu değişimlerinden daha güçlü "
        "tepki verdiğini raporlamıştır [3]."
    ),
    (
        "Lee tarafından sunulan çalışma da benzer biçimde 56 ürün kategorisinde sistematik shrinkflation örnekleri "
        "tespit etmekte; medyan ürün boyutunun yaklaşık yüzde 11 küçüldüğünü ve buna bağlı birim fiyatın yaklaşık "
        "yüzde 9 arttığını belirtmektedir [4]. Aynı çalışma, zorunlu birim fiyat açıklamasının tüketici tepkisini "
        "bir miktar artırsa da tek başına güçlü bir caydırıcı mekanizma oluşturmadığını göstermektedir [4]."
    ),
    (
        "Politika ve uygulama tarafında NIST, birim fiyat etiketlerinin tutarlı ve karşılaştırılabilir biçimde "
        "sunulmasını iyi uygulama olarak tanımlamaktadır [2]. GOV.UK rehberleri de birim fiyatın farklı boyuttaki "
        "ürünlerin gerçek maliyetini karşılaştırmayı kolaylaştırdığını vurgular [5]. Bu proje, literatürdeki bu "
        "tespitleri yazılımsal bir iş akışına dönüştürerek ürün zaman serilerini, içerik çözümlemeyi ve açıklanabilir "
        "risk sınıflandırmasını aynı uygulama içinde birleştirmesi bakımından özgünleşmektedir."
    ),
]


DESIGN_PARAGRAPHS = [
    (
        "Sistem modüler bir mimariyle tasarlanmıştır. Uygulamanın giriş noktası olan FastAPI servisi; sayfa "
        "rotaları, ürün rotaları, dashboard rotaları ve bildirim rotalarını ayrı modüller halinde bir araya "
        "getirmektedir. FastAPI dokümantasyonunda önerildiği gibi çok dosyalı yapı, bağımlılık kullanımı ve "
        "şablon/static dosya desteği birlikte kullanılarak bakım kolaylığı yüksek bir servis katmanı kurulmuştur [6]."
    ),
    (
        "Veri katmanında `urunler`, `market` ve `fiyat_zaman_serisi` tabloları temel alınmıştır. Bu yapı sayesinde "
        "ürünün kimliği, ait olduğu market, kategori bilgisi ve farklı tarihlerdeki fiyat ile ölçü değerleri ayrı "
        "ama ilişkili olarak tutulmaktadır. SQLAlchemy oturumu veritabanı ile uygulama arasındaki tüm sorgu ve nesne "
        "yaşam döngüsünü yönetmekte, böylece router ve servis katmanlarında aynı erişim biçimi korunmaktadır [7]."
    ),
    (
        "Dashboard sorgularında ürünün en güncel ve bir önceki fiyat kaydını ayırmak için ortak tablo ifadeleri "
        "ve `row_number()` tabanlı pencere fonksiyonları kullanılmaktadır. PostgreSQL pencere fonksiyonları, aynı "
        "ürüne ait kayıtları sıralı biçimde ele alıp her satırın bağlamını koruyarak karşılaştırma yapmaya imkan "
        "verdiğinden bu problem için uygun bir çözüm sunmaktadır [8]."
    ),
    (
        "Arayüz tarafında Jinja2 şablonları, istemci tarafı JavaScript ve grafik bileşenleri ile özet kartlar, "
        "karşılaştırma listeleri ve filtre panelleri hazırlanmıştır. Böylece backend katmanında üretilen veriler "
        "yalnızca JSON olarak değil, son kullanıcı tarafından okunabilir bir karar destek paneli olarak da sunulmaktadır."
    ),
]


REQUIREMENTS_PARAGRAPHS = [
    (
        "Problemin temel gereksinimi, aynı veya benzer ürüne ait farklı tarihlerdeki kayıtların güvenilir biçimde "
        "eşleştirilmesidir. Proje bu nedenle market adlarını Türkçe karakter farklarından bağımsız normalize etmekte, "
        "kategori değerlerini ortak anahtarlara dönüştürmekte ve tarih aralığına göre ürün karşılaştırmaları üretmektedir."
    ),
    (
        "Fonksiyonel açıdan sistem; ürün listeleme, kategori ve metin araması, market bazlı filtreleme, seçilen iki "
        "tarih arasında fiyat değişimi karşılaştırması, shrinkflation riski taşıyan ürünlerin listelenmesi ve haftalık "
        "özet bildirimlerinin hazırlanması ihtiyaçlarını karşılamaktadır. Fonksiyonel olmayan gereksinimler arasında "
        "ise modüler kod yapısı, açıklanabilir sonuç üretimi ve mevcut veritabanı yapısıyla uyum öne çıkmaktadır."
    ),
    (
        "Bu kapsam, projeyi yalnızca veri gösteren bir panel olmaktan çıkarıp iş kuralı çalışan bir analiz aracı "
        "haline getirmektedir. Kullanıcı tarafında amaç sadece hangi ürünün pahalılaştığını görmek değil, içerik "
        "azalması ile birim fiyat bozulmasının birlikte gerçekleşip gerçekleşmediğini anlayabilmektir."
    ),
]


DATA_MODEL_PARAGRAPHS = [
    (
        "Shrinkflation tespiti için ürün adı içinden gramaj, hacim ve çoklu paket ifadeleri düzenli ifadeler ile "
        "ayrıştırılmaktadır. `g`, `kg`, `ml`, `l` ve `adet` türleri ortak birimlere çevrilmekte; çoklu paket yapıları "
        "tekli ürün içeriği ve toplam içerik olarak yeniden hesaplanmaktadır. Böylece hem 500 g tek paket ürünler hem "
        "de 10x17,5 g gibi çoklu paketler karşılaştırılabilir hale gelmektedir."
    ),
    (
        "Servis katmanında eşik değerleri `DetectionThresholds` yapısı ile tanımlanmıştır. Varsayılan yaklaşımda içerik "
        "azalışı ve birim fiyat artışı için yüzde 3 eşiği kullanılmakta, yalnızca nominal fiyat değişimine bakılmamaktadır. "
        "Bu tercih, aynı fiyatla daha az içerik sunulan veya görünürde indirim yapılmasına rağmen birim fiyatı bozulan "
        "ürünlerin de riskli sayılmasını sağlar."
    ),
    (
        "Ürünler, doğrudan metin eşitliği ile değil aile benzerliği üzerinden eşleştirilmektedir. Ürün adlarından ölçü "
        "ifadeleri temizlenerek bir `family_key` üretilmekte, benzer isimli kayıtlar bu anahtar üzerinden gruplanmaktadır. "
        "Böylece ambalaj boyutu değişmiş fakat marka ve ürün ailesi aynı kalmış ürünlerin farklı snapshot'ları birbirine "
        "bağlanabilmektedir."
    ),
]


RULE_FLOW_PARAGRAPHS = [
    (
        "Kural tabanlı tespit akışı beş adımdan oluşur: ilgili markete ait snapshot kayıtlarını çekmek, her kaydın ölçü "
        "bilgisini çözümlemek, aynı ürün ailesine ait eski ve yeni kayıtları eşlemek, içerik ve fiyat yüzdelerini hesaplamak "
        "ve son olarak açıklanabilir bir risk etiketi üretmek. Çıktı nesnesi; eski ve yeni fiyat, içerik farkları, birim "
        "fiyat değişimi, risk oranı, yön ve gerekçe alanlarını birlikte taşımaktadır."
    ),
    (
        "Bu yaklaşımın önemli avantajı, model çıktısının denetlenebilir olmasıdır. Sistem bir ürünü riskli işaretlediğinde "
        "yalnızca sonuca değil, `toplam içerik azaldı`, `paket adedi düştü` veya `birim içerik küçüldü` gibi gerekçelere de "
        "ulaşılabilmektedir. Bitirme projesi ölçeğinde bu açıklanabilirlik, kara kutu bir tahmin modeline göre daha savunulabilir "
        "ve geliştirilebilir bir temel oluşturmaktadır."
    ),
]


IMPLEMENTATION_PARAGRAPHS = [
    (
        "Gerçekleme aşamasında uygulama hem API hem de web sayfası olarak çalışacak şekilde tasarlanmıştır. `/health` uç noktası "
        "veritabanı bağlantısını doğrularken, `/products` ve `/dashboard/*` uç noktaları ürün listeleme, kategori dağılımı, en ucuz "
        "ve en pahalı ürünler, tarih bazlı fiyat değişimleri ve riskli ürünler gibi görünür çıktıları üretmektedir. `/`, `/urunler` "
        "ve `/urun-karsilastirmalari` sayfaları ise bu verileri kullanıcı arayüzüne taşımaktadır."
    ),
    (
        "Dashboard katmanında market, kategori, başlangıç tarihi, bitiş tarihi ve ürün durumu filtreleri birlikte çalışmaktadır. "
        "Bu sayede kullanıcı belirli bir markette yalnızca zamlanan ürünleri, yalnızca indirimde olanları veya yalnızca shrinkflation "
        "riskli kayıtları inceleyebilmektedir. Türkçe karakterlerin normalize edilmesi sayesinde `ŞOK`, `SOK Market` veya `MİGROS` "
        "gibi farklı yazımlar aynı mantıksal filtre altında toplanmaktadır."
    ),
    (
        "Bildirim tarafında Telegram Bot API kullanılarak market bazlı haftalık özetler gönderilmektedir. Resmi API'de yer alan "
        "`sendMessage` yöntemi basit HTTP çağrılarıyla metin mesajı iletmeye imkan verdiği için bu ihtiyaçla uyumludur [9]. Projede "
        "bildirim içeriği tek parçada taşınamayacak kadar uzunsa mesajlar bölünmekte; ayrıca seçilen tarih aralığına ait ilk beş "
        "ürün ve ilgili dashboard bağlantıları aynı özet içinde sunulmaktadır."
    ),
]


API_LAYER_PARAGRAPHS = [
    (
        "Uygulamanın sayfa katmanı ile servis katmanı birbirini destekleyecek biçimde tasarlanmıştır. Ürün listesi, karşılaştırma "
        "sayfası ve riskli ürün sayfası aynı veri modelini paylaşmakta; böylece kullanıcı önce özet panelden bir kategoriye inebilmekte, "
        "ardından ilgili ürün kartlarını ayrıntılı biçimde görüntüleyebilmektedir. Bu bütünleşik yapı, teknik olarak backend ağırlıklı olan "
        "projenin kullanıcı deneyimi açısından da işlevsel bir sonuç üretmesini sağlamaktadır."
    ),
    (
        "Bildirim modülü tek seferlik manuel çalıştırma ve sürekli izleme senaryolarını desteklemektedir. Ayrı script'ler yardımıyla "
        "belirli marketler için anlık bildirim denenebilmekte veya yeni veri geldiğinde otomatik rapor üretilebilmektedir. Bu özellik, "
        "projenin sadece akademik bir prototip değil, operasyonel akışlara bağlanabilecek bir çekirdek servis olarak da kurgulandığını "
        "göstermektedir."
    ),
]


TEST_PARAGRAPHS = [
    (
        "Doğrulama aşamasında router ve servis katmanları için birim testleri hazırlanmıştır. Testler; market adı normalizasyonu, kategori "
        "eşleştirme, tarih çözümleme, ürün karşılaştırma sonuçları ve bildirim mesajı üretimi gibi kritik davranışları kapsamaktadır. "
        "Özellikle 500 g'dan 450 g'a düşen ama fiyatı sabit kalan ürün, nominal fiyatı gerilerken birim fiyatı artan ürün ve paket adedi "
        "azalan çoklu paket senaryoları shrinkflation mantığının doğruluğunu sınamak için kullanılmıştır."
    ),
    (
        "Bununla birlikte mevcut değerlendirme daha çok iş kuralı doğrulamasına odaklanmaktadır. Üretim ortamına yönelik yük testi, gerçek "
        "zamanlı veri çekme süreleri veya çok yüksek hacimli market verisi altında gecikme ölçümleri bu repository kapsamı dışındadır. Bu durum, "
        "projenin işlevsel olarak güçlü fakat performans mühendisliği açısından geliştirilmeye açık olduğunu göstermektedir."
    ),
]


CONCLUSION_PARAGRAPHS = [
    (
        "Bu çalışmada geliştirilen sistem, shrinkflation problemini tüketici açısından görünür hale getiren uygulanabilir bir yazılım altyapısı "
        "sunmuştur. Ürünlerin yalnızca etiket fiyatına değil, toplam içerik ve birim fiyat değişimine göre değerlendirilmesi sayesinde daha anlamlı "
        "bir karşılaştırma zemini oluşturulmuştur. Proje; veri modeli, iş kuralları, dashboard katmanı ve bildirim altyapısı ile birlikte ele "
        "alındığında bitirme projesi düzeyinde bütünlüklü bir çözüm üretmektedir."
    ),
    (
        "Teknik açıdan en önemli katkı, ürün adlarından ölçü bilgisi çıkarımı ile açıklanabilir karşılaştırma mantığının aynı servis içinde "
        "birleştirilmesidir. Böylece sistem yalnızca veri sunmamakta, aynı zamanda neden riskli görüldüğünü açıklayan sonuçlar da üretmektedir. "
        "Bu yönüyle proje, fiyat şeffaflığı ve tüketici farkındalığı açısından bilişim tabanlı bir destek aracı niteliği taşımaktadır."
    ),
    (
        "Çalışmanın başlıca sınırlılığı, veri çekme ve ham veri temizleme katmanının bu repository içinde tam olarak yer almamasıdır. Ayrıca bazı "
        "tarihsel kayıtlar için eski dönem paket bilgisinin ayrı snapshot alanlarında tutulmaması, karşılaştırmalarda ek veri desteği gerektirebilmektedir. "
        "Gelecek çalışmalarda scraper katmanının doğrudan bütünleştirilmesi, çok marketli çapraz fiyat karşılaştırmalarının genişletilmesi, kullanıcı "
        "oturumları ve rol bazlı yetkilendirme eklenmesi ve risk puanlamasının istatistiksel yöntemlerle desteklenmesi önerilmektedir."
    ),
]


REFERENCES = [
    "[1] Office for National Statistics. The impact of Shrinkflation on CPIH, UK: January 2012 to June 2017. 24 July 2017. "
    "https://www.ons.gov.uk/economy/inflationandpriceindices/articles/theimpactofshrinkflationoncpihuk/january2012tojune2017",
    "[2] Sefcik, D. NIST SP 1181: Unit pricing guide: a best practice approach to unit pricing. National Institute of Standards and Technology, 2014. "
    "https://doi.org/10.6028/NIST.SP.1181",
    "[3] Janssen, A., Kasinger, J. Shrinkflation and Consumer Demand. Marketing Science, 45(1), 142-158, 2025. "
    "https://doi.org/10.1287/mksc.2024.0948",
    "[4] Lee, Y. Shrinkflation: Evidence on Product Downsizing and Consumer Response. SSRN / Kilts Center at Chicago Booth Marketing Data Center Paper, 2024. "
    "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5053745",
    "[5] GOV.UK. Unit pricing: information for consumers. 2015. "
    "https://www.gov.uk/government/publications/unit-pricing-information-for-consumers/unit-pricing-information-for-consumers",
    "[6] FastAPI Documentation. Tutorial - User Guide. Erişim: 15 Mayıs 2026. "
    "https://fastapi.tiangolo.com/tutorial/",
    "[7] SQLAlchemy Documentation. Session Basics. Erişim: 15 Mayıs 2026. "
    "https://docs.sqlalchemy.org/en/20/orm/session_basics.html",
    "[8] PostgreSQL Documentation. Window Functions. Erişim: 15 Mayıs 2026. "
    "https://www.postgresql.org/docs/current/functions-window.html",
    "[9] Telegram. Bot API. Erişim: 15 Mayıs 2026. "
    "https://core.telegram.org/bots/api",
]


APPENDIX_1 = (
    "Başlıca uç noktalar: `GET /health`, `GET /products`, `GET /dashboard/summary`, "
    "`GET /dashboard/top-price-changes`, `GET /dashboard/product-price-comparisons`, "
    "`GET /dashboard/risky-products` ve `POST /notifications/telegram/shrinkflation`. "
    "Bu uç noktalar ürün listeleme, tarih bazlı karşılaştırma, riskli ürün raporlama ve bildirim tetikleme amaçlarıyla kullanılmaktadır."
)


APPENDIX_2 = (
    "Temel kural akışı özetle şöyledir: ürün adı ve metadata içinden ölçü bilgisini ayıkla; ölçüleri ortak birimlere dönüştür; "
    "aynı ürün ailesine ait eski ve yeni kayıtları eşleştir; içerik, adet ve birim fiyat yüzdelerini hesapla; içerik azalışı ile "
    "birim fiyat artışı aynı anda görülüyorsa ürünü shrinkflation riskli olarak işaretle; sonucu gerekçe, şiddet ve tarih bilgisi "
    "ile birlikte kullanıcıya veya bildirim kanalına gönder."
)


def paragraph_text(paragraph: ET.Element) -> str:
    return "".join(node.text or "" for node in paragraph.findall(f".//{W}t")).strip()


def keep_only_ppr(paragraph: ET.Element) -> None:
    for child in list(paragraph):
        if child.tag != f"{W}pPr":
            paragraph.remove(child)


def set_paragraph_text(paragraph: ET.Element, text: str) -> None:
    keep_only_ppr(paragraph)
    if not text:
        return
    run = ET.Element(f"{W}r")
    text_node = ET.SubElement(run, f"{W}t")
    if text.startswith(" ") or text.endswith(" ") or "  " in text:
        text_node.set(f"{{{XML_NS}}}space", "preserve")
    text_node.text = text
    paragraph.append(run)


def clone_paragraph_like(paragraph: ET.Element, text: str) -> ET.Element:
    new_paragraph = deepcopy(paragraph)
    set_paragraph_text(new_paragraph, text)
    return new_paragraph


def insert_after(body: ET.Element, anchor: ET.Element, paragraphs: list[ET.Element]) -> None:
    index = list(body).index(anchor)
    for offset, paragraph in enumerate(paragraphs, start=1):
        body.insert(index + offset, paragraph)


def remove_paragraph(paragraph: ET.Element) -> None:
    parent = paragraph.getparent() if hasattr(paragraph, "getparent") else None
    if parent is not None:
        parent.remove(paragraph)


def direct_body_paragraphs(body: ET.Element) -> list[ET.Element]:
    return [child for child in list(body) if child.tag == f"{W}p"]


def set_table_cell_text(cell: ET.Element, text: str) -> None:
    paragraphs = cell.findall(f"./{W}p")
    if not paragraphs:
        paragraph = ET.SubElement(cell, f"{W}p")
        set_paragraph_text(paragraph, text)
        return
    set_paragraph_text(paragraphs[0], text)
    for extra in paragraphs[1:]:
        cell.remove(extra)


def update_table_rows(table: ET.Element, rows: list[list[str]]) -> None:
    table_rows = table.findall(f"./{W}tr")
    if not table_rows:
        return
    template_row = table_rows[-1]
    while len(table_rows) < len(rows):
        table.append(deepcopy(template_row))
        table_rows = table.findall(f"./{W}tr")
    while len(table_rows) > len(rows):
        table.remove(table_rows[-1])
        table_rows = table.findall(f"./{W}tr")
    for row_element, row_values in zip(table_rows, rows):
        cells = row_element.findall(f"./{W}tc")
        for cell, value in zip(cells, row_values):
            set_table_cell_text(cell, value)


def remove_targeted_paragraphs(body: ET.Element, paragraphs: list[ET.Element], indexes: list[int]) -> None:
    for index in sorted(indexes, reverse=True):
        paragraph = paragraphs[index]
        if paragraph in list(body):
            body.remove(paragraph)


def fill_document(source_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, output_path)

    with zipfile.ZipFile(output_path, "r") as archive:
        file_map = {name: archive.read(name) for name in archive.namelist()}
        xml_bytes = file_map["word/document.xml"]
        root = ET.fromstring(xml_bytes)
        body = root.find(f"./{W}body")
        if body is None:
            raise RuntimeError("word/document.xml içinde body bulunamadi.")

        paragraphs = direct_body_paragraphs(body)
        tables = [child for child in list(body) if child.tag == f"{W}tbl"]

        set_paragraph_text(paragraphs[10], PROJECT_TITLE)
        set_paragraph_text(paragraphs[19], AUTHOR_NAME)
        set_paragraph_text(paragraphs[25], THESIS_DATE)
        set_paragraph_text(paragraphs[34], PROJECT_TITLE)
        set_paragraph_text(paragraphs[41], AUTHOR_NAME)
        set_paragraph_text(paragraphs[48], APPROVAL_NAME)
        set_paragraph_text(paragraphs[51], THESIS_DATE)

        set_paragraph_text(
            paragraphs[53],
            "Başlıklar proje içeriğine göre güncellenmiştir. Sayfa numaralarının doğru görünmesi için Word içinde içindekiler tablosu alanı güncellenmelidir.",
        )
        toc_lines = {
            55: "ŞEKİLLER LİSTESİ",
            56: "TABLOLAR LİSTESİ",
            57: "KISALTMALAR LİSTESİ",
            58: "ÖZET",
            59: "ABSTRACT",
            60: "TEŞEKKÜR",
            61: "1. GİRİŞ",
            62: "2. LİTERATÜR ARAŞTIRMASI",
            63: "3. SİSTEM TASARIMI VE YÖNTEM",
            64: "3.1. Problem Tanımı ve Gereksinimler",
            65: "3.1.1. Veri Modeli ve Shrinkflation Kuralları",
            66: "3.1.1.1. Kural Tabanlı Tespit Akışı",
            67: "4. GERÇEKLEME, TEST VE DEĞERLENDİRME",
            68: "4.1. API, Dashboard ve Bildirim Katmanı",
            69: "4.1.1. Testler ve Performans Değerlendirmesi",
            70: "5. SONUÇ ve TARTIŞMA",
            71: "KAYNAKÇA",
            72: "EKLER",
            74: "Not: Bu bölümdeki sayfa numaraları Word içinde alan güncellemesi yapıldığında otomatik olarak yenilenmelidir.",
        }
        for index, text in toc_lines.items():
            set_paragraph_text(paragraphs[index], text)

        set_paragraph_text(paragraphs[78], "Bu çalışmada ayrı bir şekil listesi kullanılmamıştır.")
        set_paragraph_text(paragraphs[79], "")
        set_paragraph_text(paragraphs[81], "Çalışma metin, tablo ve arayüz çıktıları üzerine kurulduğu için zorunlu bir şekil listesi oluşturulmamıştır.")
        set_paragraph_text(paragraphs[83], "")

        set_paragraph_text(paragraphs[89], "Tablo 3.1 Sistemde Kullanılan Temel Teknolojiler ve Görevleri")
        set_paragraph_text(paragraphs[92], "Belgede tek tablo olarak proje mimarisinde kullanılan temel teknolojiler ve görevleri verilmiştir.")
        set_paragraph_text(paragraphs[94], "")

        set_paragraph_text(paragraphs[98], "Çalışmada kullanılan temel kısaltmalar aşağıda verilmiştir.")

        set_paragraph_text(paragraphs[103], TURKISH_ABSTRACT)
        set_paragraph_text(
            paragraphs[104],
            "Anahtar Kelimeler: shrinkflation, birim fiyat, FastAPI, fiyat izleme, veri analitiği",
        )
        set_paragraph_text(paragraphs[108], PROJECT_TITLE_EN)
        set_paragraph_text(paragraphs[109], ENGLISH_ABSTRACT)
        set_paragraph_text(
            paragraphs[110],
            "Keywords: shrinkflation, unit price, FastAPI, price monitoring, data analytics",
        )

        set_paragraph_text(
            paragraphs[114],
            "Bu çalışmanın geliştirilme sürecinde teknik geri bildirimleriyle katkı sağlayan danışmanıma, aileme ve çalışma boyunca destek olan herkese teşekkür ederim.",
        )

        set_paragraph_text(paragraphs[118], INTRO_PARAGRAPHS[0])
        set_paragraph_text(paragraphs[119], INTRO_PARAGRAPHS[1])

        set_paragraph_text(paragraphs[122], LITERATURE_PARAGRAPHS[0])
        set_paragraph_text(paragraphs[123], LITERATURE_PARAGRAPHS[1])
        insert_after(body, paragraphs[123], [clone_paragraph_like(paragraphs[123], LITERATURE_PARAGRAPHS[2])])

        set_paragraph_text(paragraphs[125], "SİSTEM TASARIMI VE YÖNTEM")
        design_slots = [126, 127, 128, 129]
        for slot, text in zip(design_slots, DESIGN_PARAGRAPHS):
            set_paragraph_text(paragraphs[slot], text)
        for slot in range(130, 147):
            set_paragraph_text(paragraphs[slot], "")

        set_paragraph_text(paragraphs[147], "Problem Tanımı ve Gereksinimler")
        requirement_slots = [148, 149, 151]
        for slot, text in zip(requirement_slots, REQUIREMENTS_PARAGRAPHS):
            set_paragraph_text(paragraphs[slot], text)

        set_paragraph_text(paragraphs[150], "")
        set_paragraph_text(paragraphs[152], "")
        for slot in range(153, 159):
            set_paragraph_text(paragraphs[slot], "")

        set_paragraph_text(paragraphs[159], "Veri Modeli ve Shrinkflation Kuralları")
        data_model_slots = [160, 161, 163]
        for slot, text in zip(data_model_slots, DATA_MODEL_PARAGRAPHS):
            set_paragraph_text(paragraphs[slot], text)
        for slot in range(164, 168):
            set_paragraph_text(paragraphs[slot], "")

        set_paragraph_text(paragraphs[162], "Tablo 3.1 Sistemde Kullanılan Temel Teknolojiler ve Görevleri")

        set_paragraph_text(paragraphs[168], "Kural Tabanlı Tespit Akışı")
        set_paragraph_text(paragraphs[169], RULE_FLOW_PARAGRAPHS[0])
        set_paragraph_text(paragraphs[170], RULE_FLOW_PARAGRAPHS[1])

        set_paragraph_text(paragraphs[172], "GERÇEKLEME, TEST VE DEĞERLENDİRME")
        set_paragraph_text(paragraphs[173], IMPLEMENTATION_PARAGRAPHS[0])
        set_paragraph_text(paragraphs[174], IMPLEMENTATION_PARAGRAPHS[1])
        set_paragraph_text(paragraphs[175], IMPLEMENTATION_PARAGRAPHS[2])
        set_paragraph_text(paragraphs[176], "API, Dashboard ve Bildirim Katmanı")
        set_paragraph_text(paragraphs[177], API_LAYER_PARAGRAPHS[0])
        set_paragraph_text(paragraphs[178], "Testler ve Performans Değerlendirmesi")
        set_paragraph_text(paragraphs[179], TEST_PARAGRAPHS[0])
        set_paragraph_text(paragraphs[180], TEST_PARAGRAPHS[1])

        set_paragraph_text(paragraphs[183], CONCLUSION_PARAGRAPHS[0])
        set_paragraph_text(paragraphs[184], CONCLUSION_PARAGRAPHS[1])
        set_paragraph_text(paragraphs[185], CONCLUSION_PARAGRAPHS[2])
        set_paragraph_text(paragraphs[186], "")

        reference_slots = [189, 190, 191, 192, 193, 194]
        for slot, text in zip(reference_slots, REFERENCES[:6]):
            set_paragraph_text(paragraphs[slot], text)
        extra_refs = [clone_paragraph_like(paragraphs[194], text) for text in REFERENCES[6:]]
        insert_after(body, paragraphs[194], extra_refs)

        set_paragraph_text(
            paragraphs[197],
            "Bu bölümde uygulamanın başlıca uç noktaları ve shrinkflation tespit akışının kısa özeti verilmiştir.",
        )
        set_paragraph_text(paragraphs[198], "")
        set_paragraph_text(paragraphs[199], "EK-1: BAŞLICA API UÇ NOKTALARI")
        set_paragraph_text(paragraphs[200], APPENDIX_1)
        set_paragraph_text(paragraphs[201], "EK-2: SHRINKFLATION TESPİTİNDE KULLANILAN TEMEL KURALLAR")
        set_paragraph_text(paragraphs[202], APPENDIX_2)

        if len(tables) >= 2:
            update_table_rows(
                tables[0],
                [
                    ["API", "Application Programming Interface"],
                    ["ORM", "Object Relational Mapping"],
                    ["JSON", "JavaScript Object Notation"],
                ],
            )
            update_table_rows(
                tables[1],
                [
                    ["Teknoloji", "Amaç", "Projedeki Kullanımı"],
                    ["FastAPI", "Servis katmanı", "Ürün, dashboard ve bildirim uç noktaları"],
                    ["SQLAlchemy", "Veritabanı erişimi", "Oturum yönetimi, model ve sorgu işlemleri"],
                    ["PostgreSQL / Supabase", "Kalıcı veri saklama", "Ürün, market ve fiyat zaman serisi kayıtları"],
                ],
            )

        remove_targeted_paragraphs(
            body,
            paragraphs,
            [
                79,
                83,
                94,
                130,
                131,
                132,
                133,
                134,
                135,
                136,
                137,
                138,
                139,
                140,
                141,
                142,
                143,
                144,
                145,
                146,
                150,
                152,
                153,
                154,
                155,
                156,
                157,
                158,
                164,
                165,
                166,
                167,
                186,
                198,
            ],
        )

        file_map["word/document.xml"] = ET.tostring(root, encoding="utf-8", xml_declaration=True)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as temp_file:
        temp_path = Path(temp_file.name)

    try:
        with zipfile.ZipFile(temp_path, "w") as archive:
            for name, data in file_map.items():
                archive.writestr(name, data)
        shutil.move(temp_path, output_path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def main() -> None:
    source_path = Path("/Users/uguryildiz/Desktop/bitirme tezi/319bitime-projesi-sablon-08042025.docx")
    output_path = Path("/Users/uguryildiz/Desktop/pythoncalismalari/backend/outputs/319bitirme-projesi-doldurulmus.docx")
    fill_document(source_path, output_path)
    print(output_path)


if __name__ == "__main__":
    main()
