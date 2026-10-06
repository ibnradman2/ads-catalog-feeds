# -*- coding: utf-8 -*-
r"""ملف جوجل الإنجليزي لـMerchant Center (البند P-asal-merchant-008، أمر المالك 2026-09-27).

لماذا: ملف سلة للمنصات عربي فقط حتى برابط /en، والمالك يريد منتجات إنجليزية حقيقية في
Merchant Center عسل الجبال. فنأخذ ملف جوجل العربي بعد معالجته (السعر والتوفر والصور وروابط
التتبع والتسميات كما هي)، ونضع مكان العنوان والوصف نصّ صفحة المنتج الإنجليزية /en في المتجر،
ونحوّل الرابط إلى /en. المصدر في Merchant له لغة en، فيبقى الملف العربي كما هو.

المنتج يُستبعد من الملف الإنجليزي إن كان عنوانه أو وصفه في صفحة /en عربيًّا (بلا ترجمة)،
أو كان في عنوانه الإنجليزي موسم يخالف موسم العنوان العربي (ترجمة قديمة)، أو كانت أرقام العنوان
العربي غائبة عن الإنجليزي (وزن أو عدد قديم). ويعود وحده متى أصلحت جلسة store-asal ترجمته.

نصوص /en تُحفظ في en_texts.json داخل مستودع الملفات، ويُحدَّث منها ما مضى عليه يوم، بحدّ
140 صفحة في كل تشغيل؛ لأن واجهة سلة تردّ 429 بعد نحو 300 طلب سريع. عند 429 يتوقف التحديث
ويبقى النص المحفوظ.
"""
import json, os, re, time, html, datetime as dt
import xml.etree.ElementTree as ET
from defusedxml.ElementTree import fromstring as safe_fromstring
import requests

G = "{http://base.google.com/ns/1.0}"
REPO = os.environ.get("FEEDS_REPO_DIR") or r"C:\ads-api\feeds_repo"
CACHE = os.path.join(REPO, "en_texts.json")          # كاش الإنجليزية (اسمه القديم باقٍ)


def _load_stores():
    """نطاقات المتاجر بترتيب البناء، من ci/data/stores.json (تصدير غير سرّي من سجل المتاجر، P-merchant-025).
    لا معرّف مكتوبًا في الكود. وغيابه أو فساده يوقف التشغيل قبل أي توليد أو نشر."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "stores.json")
    try:
        stores = json.load(open(path, encoding="utf-8"))["stores"]
        return {k: "https://" + v["domain"] for k, v in stores.items()}
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise RuntimeError(f"تعذّرت قراءة {path}: {type(e).__name__}. صدّره بـ: python dashboard/publish_feeds.py --export-stores") from e


STORES = _load_stores()   # المتجر ← رابطه؛ ترتيب المفاتيح = ترتيب بناء الملفات
# اللغات بترتيب المادة 61 البند 3: (رمز سلة في الرابط، رمز Merchant في اسم الملف ولغة المحتوى، النظام الكتابي)
LANGS = [("en", "en", "latin"), ("ur", "ur", "arabic"), ("hi", "hi", "devanagari"), ("tl", "tl", "latin"),
         ("ind", "id", "latin"), ("fr", "fr", "latin"), ("tr", "tr", "latin"), ("zh", "zh", "cjk")]
SCRIPT_RE = {"latin": re.compile(r"[A-Za-zÀ-ɏ]"), "arabic": re.compile(r"[؀-ۿ]"),
             "devanagari": re.compile(r"[ऀ-ॿ]"), "cjk": re.compile(r"[一-鿿]")}
UNTRANSLATED_RECHECK_HOURS = 48   # صفحة لغة لم تُترجم بعد (نصها = العربي) لا تُجلب أكثر من مرة كل يومين
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MAX_FETCH = 140   # حد طلبات واحد لكل تشغيل موزّع على كل المتاجر واللغات (سلة تردّ 429 بعد نحو 300)
FRESH_HOURS = 24
AR = re.compile(r"[\u0600-\u06FF]")
LETTER = re.compile(r"[A-Za-z\u0600-\u06FF]")

# المواسم بالإنجليزية، بأسماء تسمية custom_label_1 العربية في catalog_feed_proxy.SEASONS
EN_SEASONS = [("اليوم الوطني", re.compile(r"national\s+day", re.I)),
              ("يوم التأسيس", re.compile(r"found(?:ation|ing)\s+day", re.I)),
              ("رمضان", re.compile(r"ramadan", re.I)),
              ("العيد", re.compile(r"\beid\b", re.I)),
              ("الشتاء", re.compile(r"winter", re.I))]

# جمل غير منتجية في الوصف الإنجليزي، مقابل PROMO_RE العربي (البند M-13): الشحن والدفع والفروع
# والسجل التجاري ودعوات الشراء واسم الشركة والتنبيه. وجمل الادّعاء الصحي (البند P-asal-merchant-003).
EN_PROMO_RE = re.compile(
    r"riyadh|cities|shipping|delivery|deliver|receipt|whatsapp|customer service|cash|payment|pay |"
    r"tabby|tamara|mada|apple pay|installment|credit card|branch|commercial registration|tax number|"
    r"who are we|about us|rawdat|our experience|years in the honey|return within|right to return|"
    r"guarantee|hurry|stock runs out|quantity is limited|add to cart|click|order it now|order now|"
    r"examination certificate|examined in the laboratory|alert|food and drug|medical benefits|"
    r"research its benefits|why buy|mall|street|location link", re.I)
EN_CLAIM_RE = re.compile(
    r"\btreat|\bcure|heal|disease|immun|doctor|medic|inflamm|\bpain|diabet|cough|throat|wound|burn|"
    r"infection|bacteri|virus|antibiot|blood pressure|liver|stomach|colon|joint|anemia|nerve|insomnia|"
    r"strengthen|boost|prevent|symptom|patient|therap|health", re.I)
YEARS_RE = re.compile(r"\b3[68](\s*)years", re.I)   # عسل الجبال منذ 40 عامًا (أمر المالك 2026-09-24)

# العلامة الإنجليزية الموحدة بدل القيم العربية الثلاث (قرار المالك 2026-09-28، البند P-merchant-011)
EN_BRAND = {"asal": "Asal Aljebal", "areesh": "Areesh", "hayala": "Hayala"}
# نوع المنتج بالإنجليزية. القيمة الجديدة غير المترجمة يُحذف حقلها من الملف الإنجليزي وتُذكر في
# ملخص التشغيل، حتى لا يصل نص عربي إلى المصدر الإنجليزي.
EN_PRODUCT_TYPE = {
    "أعسال بالوزن": "Honey by Weight", "أصناف العسل": "Honey Varieties",
    "منتجات طبيعية": "Natural Products", "أعسال بلدية محلية": "Local Saudi Honey",
    "ربع كيلو": "Quarter Kilo (250 g)", "نصف كيلو": "Half Kilo (500 g)",
    "1 كيلو": "1 kg", "2 كيلو": "2 kg", "5 كيلو": "5 kg", "7 كيلو": "7 kg", "10 كيلو": "10 kg",
    "عسل سدر كشميري": "Kashmiri Sidr Honey", "عسل سدر حضرمي": "Hadrami Sidr Honey",
    "عسل سدر ملكي": "Royal Sidr Honey", "عسل سدر جبلي": "Mountain Sidr Honey",
    "عسل سدر بيشاوري": "Peshawari Sidr Honey", "عسل سدر طبيعي": "Natural Sidr Honey",
    "عسل سدر بالزنجبيل والليمون والكركم": "Sidr Honey with Ginger, Lemon and Turmeric",
    "أعسال بالشمع": "Honeycomb Honey", "أعسال بالجملة": "Wholesale Honey",
    "غذاء ملكات النحل": "Royal Jelly", "حبوب اللقاح": "Bee Pollen", "مشتقات النحل": "Bee Products",
    "عكبر": "Propolis", "كريم سم النحل": "Bee Venom Cream", "جنسنج": "Ginseng",
    "عسل حبة البركة السوداء": "Black Seed Honey", "عسل اليانسون": "Anise Honey",
    "عسل شوكة سمرة جنوبي": "Southern Samra Thorn Honey", "عسل الغابة السوداء": "Black Forest Honey",
    "عسل أبو فروة الكستناء": "Chestnut Honey", "عسل البردقوش": "Marjoram Honey",
    "عسل طلح جنوبي وحائلي": "Southern and Hail Talh Honey", "عسل الصبار المر": "Bitter Aloe Vera Honey",
    "عسل المجرى الأبيض": "White Majra Honey", "عسل زهور برية بلدي": "Local Wildflower Honey",
    "عسل زهور البرسيم": "Clover Flower Honey", "عسل المورينجا": "Moringa Honey",
    "عسل الأثل": "Athal (Tamarisk) Honey", "خلطة الجبال": "Aljebal Mountain Mix",
    "عروض اليوم الوطني 96": "Saudi National Day 96 Offers", "ملاعق عسل": "Honey Spoons",
    "تمر عجوة عالية المدينة": "Ajwa Alia Al-Madina Dates", "تمر سكري القصيم": "Qassim Sukkari Dates",
    "تلبينة نبوية": "Nabawi Talbinah", "سمن بلدي": "Local Ghee", "زبيب أحمر": "Red Raisins",
    "زبيب أسود": "Black Raisins", "مكسرات مشكلة": "Mixed Nuts", "لوز يمني": "Yemeni Almonds",
    "قهوة الشاذلية": "Shazliya Coffee", "العسل الاسباني": "Spanish Honey",
    "عسل مانوكا نيوزلندي": "New Zealand Manuka Honey", "تمر خلاص القصيم": "Qassim Khalas Dates",
    "عروض حصرية لمدة 48 ساعة": "48-Hour Exclusive Offers",
}


def en_product_type(value):
    """يترجم نوع المنتج جزءًا جزءًا (الفاصل ‹>›). يعيد None إن بقي جزء بلا ترجمة."""
    parts = [" ".join(p.split()) for p in (value or "").split(">") if p.strip()]
    out = [p if not AR.search(p) else EN_PRODUCT_TYPE.get(p) for p in parts]
    return None if not out or None in out else " > ".join(out)


def _now():
    return dt.datetime.now(dt.timezone.utc)


def cache_path(lang):
    """كاش مستقل لكل لغة: en_texts.json للإنجليزية، وtexts_<لغة>.json لغيرها."""
    return CACHE if lang == "en" else os.path.join(REPO, f"texts_{lang}.json")


def load_cache(lang="en"):
    try:
        return json.load(open(cache_path(lang), encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_cache(cache, lang="en"):
    path = cache_path(lang)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    json.dump(cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, path)


def parse_page(text):
    """يعيد (العنوان، وصف HTML) من صفحة المنتج الإنجليزية."""
    title = ""
    for m in re.findall(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', text, re.S):
        try:
            j = json.loads(m)
        except ValueError:
            continue
        for node in j.get("@graph", [j]) if isinstance(j, dict) else []:
            if isinstance(node, dict) and node.get("@type") == "Product" and node.get("name"):
                title = node["name"]
                break
        if title:
            break
    if not title:
        og = re.search(r'<meta property="og:title" content="([^"]*)"', text)
        title = html.unescape(og.group(1)).split(" | ")[0] if og else ""
    body = re.search(r'<article[^>]*id="more-content"[^>]*>(.*?)</article>', text, re.S)
    return html.unescape(title).strip(), (body.group(1) if body else "")


class Budget:
    """حد طلبات مشترك بين المتاجر واللغات في التشغيل الواحد، وتوقف مشترك عند أول 429."""
    def __init__(self, n=MAX_FETCH):
        self.left, self.stop = n, None


def refresh(store, ids, cache, lang="en", budget=None, ar_titles=None):
    """يحدّث نصوص صفحات اللغة لما مضى عليه يوم أو لم يُجلب. يعيد (المحدَّث، سبب التوقف أو None).
    صفحة لغة نصها هو العربي نفسه (لم تُترجم) تُعاد بعد 48 ساعة لا يوميًّا، توفيرًا للحد."""
    budget = budget or Budget()
    if budget.stop:
        return 0, budget.stop
    base = STORES[store]
    sc = cache.setdefault(store, {})
    now = _now()
    ar_titles = ar_titles or {}

    def age(pid):
        at = (sc.get(pid) or {}).get("at")
        return dt.datetime.fromisoformat(at) if at else dt.datetime.min.replace(tzinfo=dt.timezone.utc)

    def hours(pid):
        e = sc.get(pid) or {}
        same = bool(e.get("title")) and lang != "en" and e["title"].strip() == (ar_titles.get(pid) or "").strip()
        return UNTRANSLATED_RECHECK_HOURS if same else FRESH_HOURS

    due = sorted((p for p in ids if age(p) < now - dt.timedelta(hours=hours(p))), key=age)[:budget.left]
    s = requests.Session()
    s.headers["User-Agent"] = UA
    done = 0
    for pid in due:
        try:
            r = s.get(f"{base}/{lang}/x/p{pid}", timeout=30)   # سلة تصل إلى المنتج بمعرّفه أيًّا كان المقطع قبله
        except requests.RequestException as e:
            budget.stop = type(e).__name__
            break
        if r.status_code == 429 or (r.status_code == 200 and not r.url.rstrip("/").endswith(f"/p{pid}")):
            budget.stop = f"{r.status_code} {r.url[:40]}"
            break
        if r.status_code in (404, 410):
            sc[pid] = {"gone": True, "at": _now().isoformat(timespec="seconds")}
        elif r.status_code == 200:
            r.encoding = "utf-8"
            title, body = parse_page(r.text)
            if title:
                sc[pid] = {"title": title, "desc": body, "at": _now().isoformat(timespec="seconds")}
        else:
            budget.stop = str(r.status_code)
            break
        done += 1
        budget.left -= 1
        time.sleep(0.3)
    return done, budget.stop


def _arabic_share(text):
    letters = LETTER.findall(text or "")
    return (len(AR.findall(text or "")) / len(letters)) if letters else 0.0


def _same_text(a, b):
    """الأردية تكتب بالحرف العربي، فنص صفحة /ur الذي يطابق العربي (أو يكاد) لم يُترجم بعد (2026-10-06)."""
    import difflib
    return difflib.SequenceMatcher(None, " ".join((a or "").split()), " ".join((b or "").split())).ratio() >= 0.6


def _season(text):
    return next((name for name, rx in EN_SEASONS if rx.search(text or "")), None)


AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹०१२३४५६७८९", "0123456789" * 3)


EN_NUMBER_WORDS = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
                   "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
EN_NUMBER_WORD_RE = re.compile(r"\b(" + "|".join(EN_NUMBER_WORDS) + r")\b", re.I)


def _numbers(text):
    # العدد المكتوب بالكلمات في الإنجليزية (Three jars) يُعدّ رقمًا حتى لا يُستبعد المنتج خطأً
    text = EN_NUMBER_WORD_RE.sub(lambda m: EN_NUMBER_WORDS[m.group(1).lower()], text or "")
    # نسبة الخصم (37%) ترويج لا هوية منتج: عنوان الإنجليزية النظيف بلا خصم صحيح، فلا تُعدّ رقمًا ناقصًا
    text = re.sub(r"\d+(?:\.\d+)?\s*[%٪]", " ", text.translate(AR_DIGITS))
    return set(re.findall(r"\d+(?:\.\d+)?", text))


def clean_desc(body_html, title):
    """نص الوصف الإنجليزي بلا HTML، بلا جمل ترويجية أو ادّعاءات صحية، و40 عامًا بدل 36 أو 38."""
    t = re.sub(r"</(p|li|h\d|div)>|<br\s*/?>", "\n", body_html or "", flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ")
    parts = [re.sub(r"\s+", " ", p).strip(" -•") for p in re.split(r"\n|(?<=[.!?])\s+", t)]
    kept = [p for p in parts if len(re.sub(r"\W", "", p)) >= 3
            and not EN_PROMO_RE.search(p) and not EN_CLAIM_RE.search(p)]
    new = YEARS_RE.sub(r"40\1years", " ".join(kept)).strip()
    return new if len(new) >= 40 else title


# عبارات ترويجية في العنوان يرفضها جوجل بالرمز non_product_data (37 منتجًا في أول سحب 2026-09-27):
# الشحن المجاني ونسبة الخصم والدفع عند الاستلام وبادئة «عرض/عروض ...:».
TITLE_PROMO = [re.compile(p, re.I) for p in (
    r"\(\s*free\s+shipping\s*\)", r"\bwith\s+free\s+shipping\b", r"\bfree\s+shipping\b",
    r"\b(?:at|with)\s+an?\s+\d+(?:\.\d+)?\s*%\s*discount\b", r"\b\d+(?:\.\d+)?\s*%\s*(?:discount|off)\b",
    r"\b(?:and\s+)?pay(?:ment)?\s+(?:on|upon)\s+(?:delivery|receipt)\b", r"\bcash\s+on\s+delivery\b",
    r"^[^:]{0,40}\boffers?\s*:\s*", r"\s+offers?\b(?=\s*,)", r"^(?:an?\s+)?offer\s+(?:of\s+)?")]


def clean_title(title):
    """العنوان بلا عبارات ترويجية؛ يعود العنوان كما هو إن صار أقصر من 10 أحرف."""
    t = title
    for rx in TITLE_PROMO:
        t = rx.sub(" ", t)
    t = re.sub(r"\(\s*\)", " ", t)
    t = re.sub(r"\s*\+\s*(?=\+|$)", " ", t)
    t = re.sub(r"\s+([,)])", r"\1", re.sub(r"\s+", " ", t)).strip(" ,-+:")
    return t[:1].upper() + t[1:] if len(t) >= 10 else title


def _script_ok(lang_script, text):
    """النص مكتوب بنظام اللغة المطلوبة (لا عربي في لغة لاتينية، ولا لاتيني خالص في الهندية والصينية)."""
    if lang_script == "latin":
        return _arabic_share(text) <= 0.05
    letters = re.findall(r"[^\W\d_]", text or "")
    return bool(letters) and len(SCRIPT_RE[lang_script].findall(text or "")) / len(letters) >= 0.3


def build(xml_bytes, store, lang="en", budget=None, mlang=None, script="latin"):
    """يعيد (xml اللغة، عدد المنتجات، قائمة المستبعد [(المعرّف، السبب)], ملخص التحديث).
    en: السلوك الأصلي كما هو. وغير الإنجليزية: وصف المنتج = عنوانه المترجم (فلا تمرّ ادّعاءات الشحن والصحة
    بلا فاحص للغة، حتى يُبنى فاحص كل لغة)، والمنتج يُستبعد إن لم يُترجم عنوانه."""
    cache = load_cache(lang)
    root = safe_fromstring(xml_bytes)
    items = root.findall(".//item")
    ids = [(it.findtext(G + "id") or "").strip() for it in items]
    ar_t = {pid: (it.findtext(G + "title") or it.findtext("title") or "").strip() for it, pid in zip(items, ids)}
    fetched, stop = refresh(store, [i for i in ids if i], cache, lang, budget, ar_t)
    save_cache(cache, lang)
    sc = cache.get(store, {})
    parent = {c: p for p in root.iter() for c in p}
    excluded, kept, untranslated = [], 0, set()
    for it, pid in zip(items, ids):
        e = sc.get(pid) or {}
        ar_title = ar_t[pid]
        ar_season = (it.findtext(G + "custom_label_1") or "دائم").strip()
        title = (e.get("title") or "").strip()
        if lang == "en":
            desc = clean_desc(e.get("desc"), title) if title else ""
        else:
            desc = title
        en_season = _season(title) if lang == "en" else None
        if e.get("gone") or not title:
            why = "لا صفحة محفوظة بعد للغة " + lang
        elif title == ar_title or (lang != "ur" and AR.search(title) and lang != "ar")                 or (lang == "ur" and _same_text(title, ar_title)):
            why = "العنوان بلا ترجمة"
        elif not _script_ok(script, title):
            why = "العنوان بغير نظام اللغة"
        elif lang == "en" and _arabic_share(desc) > 0.05:
            why = "الوصف بلا ترجمة"
        elif en_season and en_season != ar_season:
            why = f"موسم العنوان الإنجليزي ({en_season}) يخالف العربي ({ar_season})"
        elif _numbers(ar_title) - _numbers(title):
            why = "أرقام العنوان العربي غائبة عن الترجمة: " + " ".join(sorted(_numbers(ar_title) - _numbers(title)))
        else:
            why = None
        if why:
            excluded.append((pid, why))
            parent[it].remove(it)
            continue
        if lang == "en":
            title = clean_title(title)
        for tag, value in (("title", title[:150]), ("description", desc[:4900])):
            el = it.find(G + tag)
            if el is None:
                el = it.find(tag)
            if el is None:
                el = ET.SubElement(it, G + tag)
            el.text = value
        brand = it.find(G + "brand")
        if brand is None:
            brand = ET.SubElement(it, G + "brand")
        brand.text = EN_BRAND[store]
        for pt in it.findall(G + "product_type"):
            en = en_product_type(pt.text) if lang == "en" else None
            if en:
                pt.text = en
            else:
                untranslated.add((pt.text or "").strip())
                it.remove(pt)
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80] or "product"
        for tag in ("link", G + "link", "mobile_link", G + "mobile_link"):
            el = it.find(tag)
            if el is not None and el.text:
                # مقطع لاتيني من العنوان بدل المقطع العربي؛ سلة تصل إلى المنتج بمعرّفه، وتبقى معاملات التتبع
                q = el.text.strip().partition("?")
                el.text = f"{STORES[store]}/{lang}/{slug}/p{pid}" + (q[1] + q[2] if q[1] else "")
        kept += 1
    ch = root.find("./channel/link")                     # رابط القناة نفسها
    if ch is not None and ch.text:
        ch.text = re.sub(r"/ar/?$", "/" + lang, ch.text.strip())
    info = {"fetched": fetched, "stopped": stop, "cached": len(sc),
            "untranslated_product_types": sorted(untranslated)}
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), kept, excluded, info


def build_all(google_xml):
    """google_xml: {المتجر: ملف جوجل العربي بايتات}. يبني ملف كل متجر ولغة بحد طلبات واحد مشترك.
    الترتيب: الإنجليزية لكل المتاجر (عسل الجبال ← هيالة ← عريش)، ثم باقي اللغات بترتيب المادة 61.
    يعيد قائمة {store, lang, mlang, xml, kept, excluded, info}؛ لغة بلا منتج مترجم واحد لا ملف لها."""
    budget = Budget()
    order = [s for s in STORES if s in google_xml]
    out = []
    for lang, mlang, script in LANGS:
        for store in order:
            try:
                xml, kept, excluded, info = build(google_xml[store], store, lang, budget, mlang, script)
            except Exception as e:  # noqa: BLE001
                out.append({"store": store, "lang": lang, "mlang": mlang, "error": f"{type(e).__name__}: {str(e)[:80]}"})
                continue
            out.append({"store": store, "lang": lang, "mlang": mlang, "xml": xml, "kept": kept,
                        "excluded": excluded, "info": info})
    return out
