# -*- coding: utf-8 -*-
r"""يبني ملف منتجات وسيطًا يحمل معاملات التتبع لكل منتج — المتاجر الثلاثة.

لماذا: سناب لا يقبل معاملات الرابط لإعلانات الكتالوج إلا داخل حقل link لكل منتج في ملف
المنتجات نفسه قبل رفعه (لا حقل «معاملات» على الحملة ولا المجموعة ولا التصميم). وسلة لا تتيح
إضافة هذه المعاملات في مولّد الملف. فالحل: نقرأ ملف سلة كما هو، ونضيف المعاملات إلى رابط كل
منتج، ونكتب ملفًّا جديدًا تُوجَّه إليه المنصة بدل ملف سلة.

المعاملات بالمعرّفات فقط (لا أسماء). ماكروهات سناب المقبولة داخل حقل الرابط:
  {{campaign.id}} · {{adSet.id}} · {{ad.id}} · {{campaign.name}} · {{adSet.name}}
وميتا يستعمل {{campaign.id}} و{{adset.id}} و{{ad.id}} بالصيغة نفسها.

  python dashboard\catalog_feed_proxy.py            # يبني الملفات ويتحقّق منها
  python dashboard\catalog_feed_proxy.py --check    # فحص فقط بلا كتابة
"""
import json, sys, os, re, datetime as dt
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import xml.etree.ElementTree as ET
from defusedxml.ElementTree import fromstring as safe_fromstring  # ملف خارجي: تحصين ضد XXE
import requests

# مجلد النواتج. على GitHub Actions يُمرَّر مجلد مؤقت عبر FEEDS_BUILD_DIR؛ ومحليًّا يبقى كما كان.
BUILD = os.environ.get("FEEDS_BUILD_DIR") or r"C:\ads-api\dashboard\build"
OUT = os.path.join(BUILD, "feeds")
# على GitHub Actions تُقرأ مصادر سلة من السرّ CATALOG_FEEDS_JSON (محتوى catalog_feeds.json كاملًا).
IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# معاملات التتبع لكل منصة (بالمعرّفات فقط)
PARAMS = {
    "snap": "utm_source=snapchat&utm_medium=paid&utm_campaign={{campaign.id}}&utm_content={{adSet.id}}&utm_term={{ad.id}}",
    "meta": "utm_source={{site_source_name}}&utm_medium=paid&utm_campaign={{campaign.id}}&utm_content={{adset.id}}&utm_term={{ad.id}}",
    "google": "utm_source=google-ads&utm_medium=cpc&utm_campaign={campaignid}&utm_content={adgroupid}",
}
# مصادر ملفات سلة (تُقرأ من ملف الأسرار حتى لا يظهر المقطع السرّي في الكود)
SOURCES = os.path.join(BUILD, "catalog_feeds.json")

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
NS = {"g": "http://base.google.com/ns/1.0"}
ET.register_namespace("g", NS["g"])


def add_params(url, suffix):
    """يضيف المعاملات إلى الرابط بعد حذف أي utm قديم، ويبقي بقية المعاملات."""
    if not url:
        return url
    p = urlsplit(url)
    keep = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    query = urlencode(keep) + ("&" if keep else "") + suffix
    return urlunsplit((p.scheme, p.netloc, p.path, query, p.fragment))


def load_sources():
    r"""روابط ملفات سلة الحقيقية. تُقرأ من build\catalog_feeds.json إن وُجد، وإلا تُجلب من سناب.

    تقارير التدقيق تُقنّع المقطع السرّي في الرابط، فلا تصلح مصدرًا هنا.
    الأولوية: متغيّر البيئة CATALOG_FEEDS_JSON ثم الملف المحلي ثم سناب (محليًّا فقط).
    """
    env_json = os.environ.get("CATALOG_FEEDS_JSON", "").strip()
    if env_json:
        try:
            return json.loads(env_json)
        except ValueError:
            print("متغيّر CATALOG_FEEDS_JSON ليس JSON صالحًا — لم يُقرأ منه شيء.")   # لا يُطبع المحتوى أبدًا
            return {}
    if IN_CI:
        return {}   # لا رجوع إلى واجهة سناب على الخادم: لا رموز سناب هناك
    if os.path.exists(SOURCES):
        return json.load(open(SOURCES, encoding="utf-8"))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import utm_snap as u
    toks = u.tokens()
    src = {}
    for key, (name, acc) in u.ACCOUNTS.items():
        tok = u.token_for(acc, toks)
        if not tok:
            continue
        sc0, j0 = u.get(f"/adaccounts/{acc}", tok)
        org = ((j0.get("adaccounts") or [{}])[0].get("adaccount") or {}).get("organization_id")
        if not org:
            continue
        sc, j = u.get(f"/organizations/{org}/catalogs", tok)   # الكتالوجات تحت المنظمة لا الحساب
        for c in (j.get("catalogs") or []):
            cat = c.get("catalog") or {}
            sc2, j2 = u.get(f"/catalogs/{cat.get('id')}/product_feeds", tok)
            for f in (j2.get("product_feeds") or []):
                pf = f.get("product_feed") or {}
                url = (pf.get("schedule") or {}).get("url") or ""   # الرابط يسكن في schedule.url
                if url.startswith("http"):
                    src.setdefault(key, []).append({"catalog_id": cat.get("id"), "name": cat.get("name"),
                                                    "feed_id": pf.get("id"), "feed": pf.get("name"),
                                                    "currency": pf.get("default_currency"), "url": url})
    if src:
        json.dump(src, open(SOURCES, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("كُتبت مصادر الملفات في build" + chr(92) + "catalog_feeds.json (محلي، يحوي المقطع السرّي)")
    return src


def fetch(url):
    r = requests.get(url, headers={"User-Agent": UA}, timeout=120)
    r.raise_for_status()
    return r.content


def safe_error(e):
    """وصف الخطأ بلا رابط: رسائل requests تحوي الرابط كاملًا بمقطعه السرّي،
    وسجلّات Actions في المستودع العام يراها أي أحد."""
    resp = getattr(e, "response", None)
    code = f" {resp.status_code}" if resp is not None else ""
    return type(e).__name__ + code


# ملفات تُنظَّف قبل النشر: الوصف فوق 5000 حرف يرفضه سناب، وسعر الخصم غير الأقل خصم وهمي
# (البند P-asal-snap-003). يضيف كل متجر نفسه من جلسته بعد اعتماد المالك.
CLEAN = {("asal", "snap"), ("asal", "google")}
DESC_MAX = 4900
G = "{http://base.google.com/ns/1.0}"


def _num(text):
    m = re.search(r"\d+(?:\.\d+)?", (text or "").replace(",", ""))
    return float(m.group()) if m else None


def clean_item(it):
    """ينظّف الوصف ويحذف سعر الخصم غير الصالح. يعيد (وصف قُصّ؟، خصم حُذف؟)."""
    cut = dropped = False
    d = it.find(G + "description")
    if d is None:
        d = it.find("description")
    if d is not None and d.text:
        t = re.sub(r"<[^>]+>", " ", d.text).replace("&nbsp;", " ").replace("\xa0", " ")
        t = re.sub(r"[ \t]+", " ", t)
        t = re.sub(r"\s*\n\s*", "\n", t).strip()
        if len(t) > DESC_MAX:
            head = t[:DESC_MAX]
            end = max(head.rfind(c) for c in (".", "!", "؟", "\n"))
            t = head[:end + 1] if end > DESC_MAX // 2 else head[:head.rfind(" ")]
            cut = True
        d.text = t.strip()
    for tag in (G + "sale_price", "sale_price"):
        sp = it.find(tag)
        if sp is None:
            continue
        pr = it.find(G + "price")
        if pr is None:
            pr = it.find("price")
        s, p = _num(sp.text), _num(pr.text if pr is not None else None)
        if s is not None and p is not None and s >= p:
            it.remove(sp)
            for extra in (G + "sale_price_effective_date", "sale_price_effective_date"):
                e = it.find(extra)
                if e is not None:
                    it.remove(e)
            dropped = True
    return cut, dropped


# منتجات رفضتها ميتا لادّعاءات علاجية في الوصف (البند P-asal-meta-004).
# تُحذف من وصفها الجمل التي فيها ادّعاء صحي، في ملف ميتا فقط، والمتجر بلا تغيير.
CLAIMS_IDS = {("asal", "meta"): {"1086532456", "1204991584", "1228632179", "1281597213",
                                 "1293030213", "1994787951", "453091196", "622456174",
                                 # عبوات طلح كبيرة غير مرفوضة، بالوصف نفسه (البند P-asal-meta-006)
                                 "1262276205", "797605987", "1571578210", "63390305"}}
# رفضها جوجل للسبب نفسه (personal_hardships)، فيأخذ ملف جوجل الوصف البديل ذاته (البند P-asal-merchant-003).
CLAIMS_IDS[("asal", "google")] = CLAIMS_IDS[("asal", "meta")]
CLAIM_RE = re.compile(r"علاج|دواء|دكتور|طبيب|صيدلي|شفاء|يشفي|مرض|التهاب|ألم(?!اني)|آلام|مناعة|سكري|سكرية"
                      r"|ضغط الدم|الكبد|المعدة|القولون|الباطنية|جرثوم|بكتير|فيروس|مضاد|مفاصل"
                      r"|يقوي|تقوية|يعالج|الكحة|الحلق|الجروح|الحروق|الوقاية"
                      r"|فقر الدم|الأنيميا|الدوخة|الأعصاب|الشيخوخة|آثار جانبية|نتائج فعالة|يعانون|يعاني|صحة|صحي|جروح|كحة|صدره|والصدر|أعصاب|الأرق|مهدئ|مرمم|يريحهم|يريحه")


# وصف بديل مكتوب لكل منتج من المنتجات أعلاه (البند P-asal-meta-005).
_OVR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "meta_desc_override.json")
DESC_OVERRIDE = json.load(open(_OVR, encoding="utf-8")).get("asal", {}) if os.path.exists(_OVR) else {}


def strip_claims(it):
    """يحذف من الوصف كل جملة فيها ادّعاء صحي. يعيد عدد الجمل المحذوفة."""
    d = it.find(G + "description")
    if d is None:
        d = it.find("description")
    if d is None or not d.text:
        return 0
    t = re.sub(r"<[^>]+>", " ", d.text).replace("&nbsp;", " ").replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    parts = re.split(r"(?<=[.!؟:\n·])", t)
    kept = [x for x in parts if not CLAIM_RE.search(x)]
    d.text = re.sub(r"\s*\n\s*", "\n", "".join(kept)).strip()
    return len(parts) - len(kept)


# إثراء ملف جوجل (البند P-asal-merchant-005، البنود M-06 وM-07 وM-08 من خطة Merchant Center):
# تصنيف جوجل، والتسميات المخصصة 0..3، وسعر الوحدة. الحقل الموجود في ملف سلة لا يُستبدل.
# العائلة تُعرف من العنوان ونوع المنتج معًا، وأول قاعدة تنطبق هي المعتمدة؛ ترتيبها مقصود.
FAMILIES = [
    ("هدايا", 136, r"بوكس|هدية|اهداء|إهداء|تشكيلة"),
    ("زعفران", 1529, r"زعفران"),
    ("هيل", 1529, r"هيل"),
    ("بن وقهوة", 1868, r"(?:^|\s)بن(?:\s|$)|قهوة|باشنفر|هرري"),
    ("مانوكا", 4947, r"مانوكا"),
    ("مشروب عسل", 4947, r"مشروب"),
    ("خلطات العسل", 4947, r"خلطة"),
    ("مجرى أبيض", 4947, r"مجرى|مرديسيا"),
    ("سدر", 4947, r"سدر"),
    ("طلح", 4947, r"طلح"),
    ("سمرة", 4947, r"سمرة"),
    ("زهور", 4947, r"(?:عسل|شمع).*(?:زهور|زهرة|برسيم)"),
    ("مشتقات النحل", 422, r"حبوب (?:ال)?لقاح|غذاء (?:ال)?ملكات|عكبر|طلع (?:ال)?نخ"),
    ("عناية بالبشرة", 567, r"كريم"),
    ("عسل آخر", 4947, r"عسل|شمع"),
    ("تمور", 6812, r"تمر|تمور|عجوة|ضميد|خلاص"),
    ("فواكه مجففة", 1755, r"زبيب|مجفف|مشمش|(?:^|\s)تين"),
    ("مكسرات وبذور", 433, r"مكسرات|لوز|كاجو|فستق|جوز|بندق|بذور|كتان|قطونة|(?:^|\s)شيا|حلبة"),
    ("سمن", 5827, r"سمن"),
    ("زيوت", 2126, r"زيت"),
    ("خل", 2140, r"(?:^|\s)خل(?:\s|$)"),
    ("طحينة", 4692, r"طحينة|طحينية"),
    ("دقيق", 2775, r"دقيق|تلبينة|شعير"),
    ("منقوعات", 2073, r"بابونج|كركديه|يانسون|مرمية|شاي|ماتشا"),
    ("بهارات وأعشاب", 1529, r"بهارات|كمون|فلفل|كركم|قرفة|قرنفل|زنجبيل|شمر|زعتر|نخوة|صمغ|اكليل|إكليل"
                            r"|(?:^|\s)(?:ال)?مُ?رة|أعشاب|عشبة|جنسنج|جنسج|حبة البركة|قسط|مشاط"),
]
FAMILIES = [(n, c, re.compile(p)) for n, c, p in FAMILIES]
SEASONS = [("اليوم الوطني", r"الوطني"), ("يوم التأسيس", r"التأسيس"), ("رمضان", r"رمضان"),
           ("العيد", r"(?:^|\s)(?:ال)?عيد"), ("الشتاء", r"الشتاء|شتوي")]
SEASONS = [(n, re.compile(p)) for n, p in SEASONS]
# شريحة الأداء من نقرات Merchant Center في 30 يومًا (يبنيها dashboard\feed_labels_build.py).
# الرموز محايدة لأن الملف منشور للعموم: أ = نصف النقرات الأول، ب = حتى 80%، ج = الباقي، د = بلا نقرات.
_LBL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "feed_labels.json")
PERF_TIERS = json.load(open(_LBL, encoding="utf-8")).get("stores", {}) if os.path.exists(_LBL) else {}
UNIT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(كيلوجرام|كيلو|كجم|كغ|غرام|جرام|جم|غ)(?![ء-ي])")
COUNT_RE = re.compile(r"\d+\s*(?:عبوات|عبوة|علب|علبة|حبات|أكياس|كيس|برطمانات|قطع)|عبوتان|عبوتين|[+×x]|مجان")


def _text(it, tag):
    e = it.find(G + tag)
    if e is None:
        e = it.find(tag)
    return (e.text or "").strip() if e is not None else ""


def _price_band(it):
    p, s = _num(_text(it, "price")), _num(_text(it, "sale_price"))
    v = s if s is not None and p is not None and s < p else p
    if v is None:
        return None
    return "أقل من 100" if v < 100 else "100 إلى 299" if v < 300 else "300 إلى 599" if v < 600 else "600 فأكثر"


def _unit_measure(title):
    """يعيد (الكمية، الأساس) إن كان في العنوان وزن واحد لعبوة واحدة، وإلا None."""
    found = UNIT_RE.findall(title)
    if len(found) != 1 or COUNT_RE.search(title):
        return None
    v, unit = float(found[0][0].replace(",", ".")), found[0][1]
    grams = v * 1000 if unit in ("كيلوجرام", "كيلو", "كجم", "كغ") else v
    if grams <= 0:
        return None
    measure = (f"{grams / 1000:g}kg" if grams >= 1000 else f"{grams:g}g")
    return measure, ("1kg" if grams >= 1000 else "100g")


def enrich_google(items, store):
    """يضيف الحقول الناقصة لكل منتج في ملف جوجل. يعيد عدّاد التغطية."""
    tiers = PERF_TIERS.get(store, {})
    n = {"category": 0, "label_0": 0, "label_1": 0, "label_2": 0, "label_3": 0, "unit_pricing": 0}

    def put(it, tag, value, key):
        if value and it.find(G + tag) is None and it.find(tag) is None:
            ET.SubElement(it, G + tag).text = str(value)
            n[key] += 1

    for it in items:
        text = _text(it, "title") + " " + _text(it, "product_type")
        fam = next(((name, cat) for name, cat, rx in FAMILIES if rx.search(text)), ("أخرى", None))
        season = next((name for name, rx in SEASONS if rx.search(text)), "دائم")
        put(it, "google_product_category", fam[1], "category")
        put(it, "custom_label_0", "أداء " + tiers.get(_text(it, "id"), "د"), "label_0")
        put(it, "custom_label_1", season, "label_1")
        put(it, "custom_label_2", _price_band(it), "label_2")
        put(it, "custom_label_3", fam[0], "label_3")
        um = _unit_measure(_text(it, "title"))
        if um and it.find(G + "unit_pricing_measure") is None:
            ET.SubElement(it, G + "unit_pricing_measure").text = um[0]
            ET.SubElement(it, G + "unit_pricing_base_measure").text = um[1]
            n["unit_pricing"] += 1
    return n


def rewrite(xml_bytes, suffix, clean=False, claims_ids=(), enrich=None):
    """يعيد (xml جديد، عدد المنتجات، عدد الروابط المعدَّلة). enrich = مفتاح المتجر لإثراء ملف جوجل."""
    root = safe_fromstring(xml_bytes)
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    # المنتج بلا صورة ترفضه المنصات كلها، فيُستبعد من الملف الوسيط (القرار P-hayala-google-003).
    parent = {c: p for p in root.iter() for c in p}
    kept = []
    for it in items:
        img = it.find("{http://base.google.com/ns/1.0}image_link")
        if img is None:
            img = it.find("image_link")
        # صور خادم النظام المحاسبي fgateit.com ترجع خطأ 500، فترفضها المنصات (البند P-asal-merchant-003).
        if img is None or not (img.text or "").strip().startswith("http") or "fgateit.com" in img.text:
            parent[it].remove(it)
        else:
            kept.append(it)
    items = kept
    changed = 0
    for it in items:
        for tag in ("link", "{http://base.google.com/ns/1.0}link", "mobile_link",
                    "{http://base.google.com/ns/1.0}mobile_link"):
            el = it.find(tag)
            if el is not None and (el.text or "").startswith("http"):
                el.text = add_params(el.text.strip(), suffix)
                changed += 1
    if claims_ids:
        n = m = 0
        for it in items:
            gid = it.find(G + "id")
            pid = (gid.text or "").strip() if gid is not None else ""
            if pid not in claims_ids:
                continue
            new = DESC_OVERRIDE.get(pid)
            d = it.find(G + "description")
            if new and d is not None:
                d.text = new           # وصف مكتوب بلا ادّعاءات (البند P-asal-meta-005)
                m += 1
            else:
                n += strip_claims(it)
        print(f"   وصف بديل: {m} منتج · ادّعاءات صحية حُذفت: {n} جملة")
    if clean:
        res = [clean_item(it) for it in items]
        print(f"   تنظيف: وصف قُصّ {sum(c for c, _ in res)} · خصم غير صالح حُذف {sum(x for _, x in res)}")
    if enrich:
        n = enrich_google(items, enrich)
        print("   إثراء: " + " · ".join(f"{k} {v}" for k, v in n.items()))
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), len(items), changed


def main():
    check = "--check" in sys.argv
    os.makedirs(OUT, exist_ok=True)
    sources = load_sources()
    if not sources:
        print("لا مصادر ملفات معروفة — شغّل catalog_audit_snap_meta.py أولًا أو اكتب build\\catalog_feeds.json")
        return
    report = {"as_of": dt.date.today().isoformat(), "params": PARAMS, "files": []}
    for store, feeds in sources.items():
        for i, f in enumerate(feeds):
            if f.get("retired"):  # مصدر متقاعد: يُتخطّى ويبقى ترقيم الملفات كما هو
                continue
            try:
                raw = fetch(f["url"])
            except Exception as e:
                print(f"[{store}] {f.get('name')}: تعذّر التحميل — {safe_error(e)}")
                report["files"].append({"store": store, "name": f.get("name"), "error": safe_error(e)})
                continue
            for platform, suffix in PARAMS.items():
                try:
                    out_xml, n_items, n_links = rewrite(raw, suffix, (store, platform) in CLEAN,
                                                        CLAIMS_IDS.get((store, platform), ()),
                                                        store if platform == "google" else None)
                except Exception as e:
                    print(f"[{store}] {f.get('name')}: ملف غير صالح — {str(e)[:80]}")
                    break
                name = f"{store}-{i+1}-{platform}.xml"
                if not check:
                    open(os.path.join(OUT, name), "wb").write(out_xml)
                print(f"[{store}] {platform:<7} منتجات {n_items} · روابط معدَّلة {n_links} → build\\feeds\\{name}")
                report["files"].append({"store": store, "platform": platform, "file": name,
                                        "products": n_items, "links": n_links,
                                        "size_kb": round(len(out_xml) / 1024)})
    json.dump(report, open(os.path.join(BUILD, "catalog_feed_proxy.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("\nالملفات جاهزة في build\\feeds. تبقّى نشرها على رابط https ثابت وتوجيه المنصة إليه.")
    print("كُتب: build\\catalog_feed_proxy.json")


if __name__ == "__main__":
    main()
