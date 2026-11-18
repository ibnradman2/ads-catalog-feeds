# -*- coding: utf-8 -*-
"""ناشر ملفات المنتجات: سجل المتاجر المصدَّر ci/data/stores.json (P-merchant-025).

STORES_DATA وSNAP_FEEDS وGOOGLE_SOURCES تتغيّر بعد export_stores، فتُقرأ من الوحدة (S.SNAP_FEEDS) لا بنسخها.
"""
import json, os, sys

from pf_common import DASH, R, die

# ===== سجل المتاجر المصدَّر (P-merchant-025): ci/data/stores.json، ولا معرّف حساب مكتوب في هذا الملف =====
STORES_FILE = os.path.join(DASH, "data", "stores.json")
# الحقول المطلوبة لكل قسم. المصدَّر من السجل وحده: النطاق ومعرّفات الحسابات العامة (لا مفتاح ولا توكن ولا اتصال).
# معرّفات الملفات (الكتالوج وملف سناب ومصدر Merchant) لا مصدر لها في السجل، فتبقى في stores.json كما هي.
SHAPE = {"stores": ("domain",), "snap_feeds": ("account_id", "catalog_id", "feed_id", "file"),
         "google_sources": ("store", "account_id", "data_source_id", "file")}


def shape_problems(data):
    bad = []
    for sec, keys in SHAPE.items():
        entries = data.get(sec)
        if not isinstance(entries, dict) or not entries:
            bad.append(f"القسم {sec} غائب أو فارغ")
            continue
        for k, v in entries.items():
            for key in keys:
                if not isinstance(v, dict) or not isinstance(v.get(key), str) or not v[key].strip():
                    bad.append(f"{sec}/{k}/{key}")
    if not isinstance(data.get("snap_repoint_default"), list):
        bad.append("snap_repoint_default")
    return bad


def load_stores():
    try:
        with open(STORES_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        die(f"تعذّرت قراءة {STORES_FILE}: {type(e).__name__}. صدّره بـ: python dashboard" + chr(92) + "publish_feeds.py --export-stores")
    bad = shape_problems(data)
    if bad:
        die("stores.json ناقص أو فاسد: " + " · ".join(bad[:8]))
    return data


def _snap_feeds(data):
    """المتجر ← (حساب الإعلانات، الكتالوج، الملف داخل سناب، الملف المنشور)."""
    return {k: (v["account_id"], v["catalog_id"], v["feed_id"], v["file"]) for k, v in data["snap_feeds"].items()}


def _google_sources(data):
    """المفتاح ← (حساب Merchant، مصدر البيانات، الملف المنشور)."""
    return {k: (v["account_id"], v["data_source_id"], v["file"]) for k, v in data["google_sources"].items()}


STORES_DATA = load_stores()
# كتالوجات سناب المقابلة لكل ملف منشور: المتجر → (حساب الإعلانات، الكتالوج، الملف داخل سناب، الملف المنشور)
SNAP_FEEDS = _snap_feeds(STORES_DATA)

# مصادر Merchant Center الأساسية التي تسحب ملفات جوجل المنشورة: المتجر → (الحساب، المصدر، الملف)
# جوجل لا يقبل جدولة سحب أقصر من يومية، فتطلب هذه المهمة الساعية سحبًا فوريًّا بعد كل نشر.
GOOGLE_SOURCES = _google_sources(STORES_DATA)


def export_stores(write=True):
    """يصدّر من سجل المتاجر النطاق ومعرّفات الحسابات العامة إلى stores.json. يعيد True إن اختلف الملف عن السجل
    (ويُكتب إن كان write). يرفع RuntimeError إن لم يوجد سجل أو نقص فيه شيء، فلا يُكتب ملف ناقص أبدًا."""
    global STORES_DATA, SNAP_FEEDS, GOOGLE_SOURCES
    if R is None:
        raise RuntimeError("لا سجل متاجر في هذه البيئة (التصدير محلي فقط)")
    cur = STORES_DATA
    new = json.loads(json.dumps(cur))
    try:
        for k, st in new["stores"].items():
            st["domain"] = R.domain(k)
        for k, v in new["snap_feeds"].items():
            v["account_id"] = R.account_id(k, "snap")
        for k, v in new["google_sources"].items():
            v["account_id"] = R.account_id(v["store"], "merchant_center")
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"السجل لا يحوي ما يلزم: {type(e).__name__}: {str(e)[:100]}") from e
    bad = shape_problems(new)
    if bad:
        raise RuntimeError("التصدير ناقص: " + " · ".join(bad[:8]))
    if new == cur:
        return False
    if write:
        tmp = STORES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            json.dump(new, f, ensure_ascii=False, indent=1)
            f.write("\n")
        os.replace(tmp, STORES_FILE)
        STORES_DATA = new
        SNAP_FEEDS, GOOGLE_SOURCES = _snap_feeds(new), _google_sources(new)
    return True


def stores_command(write):
    """--export-stores (يكتب) و--check-stores (يفحص ويخرج بالرمز 1 عند الاختلاف)."""
    try:
        changed = export_stores(write=write)
    except RuntimeError as e:
        die(str(e))
    if write:
        print("stores.json: " + ("حُدّث من السجل." if changed else "مطابق للسجل، لا تغيير."))
        return
    print("stores.json: " + ("يختلف عن السجل. شغّل --export-stores." if changed else "مطابق للسجل."))
    sys.exit(1 if changed else 0)
