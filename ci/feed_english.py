# -*- coding: utf-8 -*-
r"""ملف جوجل الإنجليزي لـMerchant Center (البند P-asal-merchant-008، أمر المالك 2026-09-27).

لماذا: ملف سلة للمنصات عربي فقط حتى برابط /en، والمالك يريد منتجات إنجليزية حقيقية في
Merchant Center 262993710. فنأخذ ملف جوجل العربي بعد معالجته (السعر والتوفر والصور وروابط
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
CACHE = os.path.join(REPO, "en_texts.json")
STORES = {"asal": "https://asalaljebal.sa"}
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MAX_FETCH = 140
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


def _now():
    return dt.datetime.now(dt.timezone.utc)


def load_cache():
    try:
        return json.load(open(CACHE, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    tmp = CACHE + ".tmp"
    json.dump(cache, open(tmp, "w", encoding="utf-8"), ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, CACHE)


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


def refresh(store, ids, cache):
    """يحدّث نصوص /en لما مضى عليه يوم أو لم يُجلب. يعيد (المحدَّث، سبب التوقف أو None)."""
    base = STORES[store]
    sc = cache.setdefault(store, {})
    limit = _now() - dt.timedelta(hours=FRESH_HOURS)

    def age(pid):
        at = (sc.get(pid) or {}).get("at")
        return dt.datetime.fromisoformat(at) if at else dt.datetime.min.replace(tzinfo=dt.timezone.utc)

    due = sorted((p for p in ids if age(p) < limit), key=age)[:MAX_FETCH]
    s = requests.Session()
    s.headers["User-Agent"] = UA
    done, stop = 0, None
    for pid in due:
        try:
            r = s.get(f"{base}/en/x/p{pid}", timeout=30)   # سلة تصل إلى المنتج بمعرّفه أيًّا كان المقطع قبله
        except requests.RequestException as e:
            stop = type(e).__name__
            break
        if r.status_code == 429 or (r.status_code == 200 and not r.url.rstrip("/").endswith(f"/p{pid}")):
            stop = f"{r.status_code} {r.url[:40]}"
            break
        if r.status_code in (404, 410):
            sc[pid] = {"gone": True, "at": _now().isoformat(timespec="seconds")}
        elif r.status_code == 200:
            title, body = parse_page(r.text)
            if title:
                sc[pid] = {"title": title, "desc": body, "at": _now().isoformat(timespec="seconds")}
        else:
            stop = str(r.status_code)
            break
        done += 1
        time.sleep(0.3)
    return done, stop


def _arabic_share(text):
    letters = LETTER.findall(text or "")
    return (len(AR.findall(text or "")) / len(letters)) if letters else 0.0


def _season(text):
    return next((name for name, rx in EN_SEASONS if rx.search(text or "")), None)


AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _numbers(text):
    return set(re.findall(r"\d+(?:\.\d+)?", (text or "").translate(AR_DIGITS)))


def clean_desc(body_html, title):
    """نص الوصف الإنجليزي بلا HTML، بلا جمل ترويجية أو ادّعاءات صحية، و40 عامًا بدل 36 أو 38."""
    t = re.sub(r"</(p|li|h\d|div)>|<br\s*/?>", "\n", body_html or "", flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\xa0", " ")
    parts = [re.sub(r"\s+", " ", p).strip(" -•") for p in re.split(r"\n|(?<=[.!?])\s+", t)]
    kept = [p for p in parts if len(re.sub(r"\W", "", p)) >= 3
            and not EN_PROMO_RE.search(p) and not EN_CLAIM_RE.search(p)]
    new = YEARS_RE.sub(r"40\1years", " ".join(kept)).strip()
    return new if len(new) >= 40 else title


def build(xml_bytes, store):
    """يعيد (xml الإنجليزي، عدد المنتجات، قائمة المستبعد [(المعرّف، السبب)], ملخص التحديث)."""
    cache = load_cache()
    root = safe_fromstring(xml_bytes)
    items = root.findall(".//item")
    ids = [(it.findtext(G + "id") or "").strip() for it in items]
    fetched, stop = refresh(store, [i for i in ids if i], cache)
    save_cache(cache)
    sc = cache.get(store, {})
    parent = {c: p for p in root.iter() for c in p}
    excluded, kept = [], 0
    for it, pid in zip(items, ids):
        e = sc.get(pid) or {}
        ar_title = (it.findtext(G + "title") or it.findtext("title") or "").strip()
        ar_season = (it.findtext(G + "custom_label_1") or "دائم").strip()
        title = (e.get("title") or "").strip()
        desc = clean_desc(e.get("desc"), title) if title else ""
        en_season = _season(title)
        if e.get("gone") or not title:
            why = "لا صفحة إنجليزية محفوظة بعد"
        elif AR.search(title):
            why = "العنوان بلا ترجمة"
        elif _arabic_share(desc) > 0.05:
            why = "الوصف بلا ترجمة"
        elif en_season and en_season != ar_season:
            why = f"موسم العنوان الإنجليزي ({en_season}) يخالف العربي ({ar_season})"
        elif _numbers(ar_title) - _numbers(title):
            why = "أرقام العنوان العربي غائبة عن الإنجليزي: " + " ".join(sorted(_numbers(ar_title) - _numbers(title)))
        else:
            why = None
        if why:
            excluded.append((pid, why))
            parent[it].remove(it)
            continue
        for tag, value in (("title", title[:150]), ("description", desc[:4900])):
            el = it.find(G + tag)
            if el is None:
                el = it.find(tag)
            if el is None:
                el = ET.SubElement(it, G + tag)
            el.text = value
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80] or "product"
        for tag in ("link", G + "link", "mobile_link", G + "mobile_link"):
            el = it.find(tag)
            if el is not None and el.text:
                # مقطع إنجليزي من العنوان بدل المقطع العربي؛ سلة تصل إلى المنتج بمعرّفه، وتبقى معاملات التتبع
                q = el.text.strip().partition("?")
                el.text = f"{STORES[store]}/en/{slug}/p{pid}" + (q[1] + q[2] if q[1] else "")
        kept += 1
    ch = root.find("./channel/link")                     # رابط القناة نفسها
    if ch is not None and ch.text:
        ch.text = re.sub(r"/ar/?$", "/en", ch.text.strip())
    info = {"fetched": fetched, "stopped": stop, "cached": len(sc)}
    return ET.tostring(root, encoding="utf-8", xml_declaration=True), kept, excluded, info
