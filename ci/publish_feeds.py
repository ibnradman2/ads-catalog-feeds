# -*- coding: utf-8 -*-
r"""ينشر ملفات المنتجات الوسيطة على رابط https ثابت (GitHub Pages) ويحدّثها يوميًّا.

الخطوات: يعيد توليد الملفات بـcatalog_feed_proxy، ثم يقارنها بالمنشور حاليًّا، ثم يرفع
المتغيّر منها فقط إلى المستودع العام، ثم يتحقّق أن كل رابط يعيد 200 بالمحتوى الجديد.

شروط القبول (gate) قبل أي نشر:
  · كل ملف كان منشورًا من قبل يجب أن يُولَّد من جديد بنجاح، وإلا توقّف.
  · عدد منتجات الملف الجديد لا يقلّ عن 80% من عدد منتجات المنشور حاليًّا، وإلا توقّف.
الغرض: ألّا يُنشر كتالوج مبتور إذا تعطّل مصدر سلة أو عاد ناقصًا.

  python dashboard\publish_feeds.py             # توليد ونشر وتحقّق
  python dashboard\publish_feeds.py --dry-run   # توليد وفحص بلا رفع
  python dashboard\publish_feeds.py --no-build  # ينشر الملفات الموجودة كما هي
  python dashboard\publish_feeds.py --export-stores  # يحدّث ci\data\stores.json من سجل المتاجر (محليًّا)
  python dashboard\publish_feeds.py --check-stores   # يفحص أنه مطابق للسجل (الرمز 1 عند الاختلاف)

لا معرّف حساب مكتوب في الكود (P-merchant-025): النطاقات ومعرّفات الحسابات والملفات تُقرأ من ci\data\stores.json،
وهو تصدير غير سرّي من سجل المتاجر (adsops\config\stores.yaml) يُحدَّث تلقائيًّا في كل تشغيل محلي.

وتوجيه سناب إلى الروابط المنشورة (عملية منفصلة، تُنفَّذ يدويًّا لا في المهمة اليوميّة):
  python dashboard\publish_feeds.py --snap-status              # قراءة فقط
  python dashboard\publish_feeds.py --repoint asal hayala      # توجيه مع نسخة احتياطية
  python dashboard\publish_feeds.py --restore build\feed_url_backup_<ts>.json
"""
import datetime as dt
import json, os, sys

# الوحدات بجوار هذا الملف: الغلاف dashboard\publish_feeds.py يشغّله بـrunpy فلا يضيف مجلده إلى المسار.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pf_stores as S   # noqa: E402  (يقرأ stores.json عند الاستيراد، كما كان)
from pf_common import BASE_URL, DASH, FEEDS, IN_CI, R, REPO, REPORT, count_products, die, sh   # noqa: E402
from pf_google import google_fetch   # noqa: E402
from pf_publish import build_feeds, copy_in, gate, publish, verify   # noqa: E402
from pf_snap import repoint, restore, snap_status, snap_uploads   # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def main():
    dry = "--dry-run" in sys.argv
    if "--export-stores" in sys.argv:
        return S.stores_command(write=True)
    if "--check-stores" in sys.argv:
        return S.stores_command(write=False)
    if "--google-fetch" in sys.argv:
        return google_fetch()
    if "--snap-uploads" in sys.argv:
        i = sys.argv.index("--snap-uploads")
        w = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit() else 0
        return snap_uploads(wait=w)
    if "--repoint" in sys.argv:
        i = sys.argv.index("--repoint")
        stores = [a for a in sys.argv[i + 1:] if not a.startswith("-")]
        return repoint(stores or S.STORES_DATA["snap_repoint_default"])
    if "--restore" in sys.argv:
        return restore(sys.argv[sys.argv.index("--restore") + 1])
    if "--snap-status" in sys.argv:
        return snap_status()
    if not os.path.isdir(REPO):
        die(f"مجلّد المستودع غير موجود: {REPO}")
    print(f"=== نشر ملفات المنتجات — {dt.datetime.now():%Y-%m-%d %H:%M} ===")
    # جلب آخر نسخة أولًا: قد يكون الناشر الآخر (المهمة المحلية أو Actions) رفع قبلنا.
    # بلا check: إن فشل الجلب يكمل كما كان، والرفع نفسه يرفض إن كان المستودع متأخّرًا.
    sh(["git", "pull", "-q", "--ff-only", "origin", "main"], check=False)
    if not IN_CI and sh(["git", "rev-list", "--count", "HEAD..origin/main"], check=False) not in ("", "0"):
        # تفرّع الفرعان (رفع الناشر المحلي وActions في الوقت نفسه): يُدمج البعيد بلا أخذ ملفاته،
        # لأن الملفات المحلية تُولَّد الآن من سلة فهي الأحدث. بغير هذا توقّف النشر المحلي 101 ساعة (2026-10-15).
        sh(["git", "merge", "-q", "-s", "ours", "--no-edit", "origin/main"], check=False)
    if not IN_CI and R is not None:   # كل مزامنة محلية تحدّث التصدير من السجل، فيرفعه copy_in مع الملفات (P-merchant-025)
        try:
            drift = S.export_stores(write=not dry)
            if drift:
                print("stores.json: " + ("يختلف عن السجل (تجربة: لم يُكتب)." if dry else "حُدّث من السجل."))
        except RuntimeError as e:
            print("تحذير: تعذّر تصدير سجل المتاجر — " + str(e)[:150] + ". يبقى stores.json المرفوع.")
    proxy_report = ({"files": [{"file": n, "products": count_products(os.path.join(FEEDS, n)), "links": None}
                               for n in sorted(os.listdir(FEEDS)) if n.endswith(".xml")]}
                    if "--no-build" in sys.argv else build_feeds())
    rows = gate(proxy_report)
    if not IN_CI and not dry:
        try:   # ملفات التقييمات (عسل الجبال وعريش وهيالة): مرة يوميًّا، وفشلها لا يوقف النشر (P-merchant-022، خطة 2026-10-19)
            sys.path.insert(0, DASH)
            import feed_reviews
            feed_reviews.run_all()
        except Exception as e:  # noqa: BLE001
            print("ملف التقييمات: تعذّر — " + type(e).__name__ + ": " + str(e)[:150])
    changed = copy_in(rows)
    if dry:
        print("تجربة فقط — لم يُرفع شيء. المتغيّر: " + (", ".join(changed) or "لا شيء"))
        # يُرجع ملفات المنتجات وحدها، لا الكود: التعديل غير المرفوع في ci يبقى (M-32؛ كان يُمسح).
        sh(["git", "reset", "-q", "HEAD"], check=False)
        sh(["git", "checkout", "--", "*.xml"], check=False)
        return
    sha, pushed = publish(changed)
    verify(rows, pushed)
    if pushed:
        google_fetch(changed)
    ok =sum(1 for r in rows if r.get("http_status") == 200)
    report = {"as_of": dt.datetime.now().isoformat(timespec="seconds"), "base_url": BASE_URL,
              "commit": sha, "pushed": pushed, "changed_files": changed,
              "files_ok": ok, "files_total": len(rows), "files": rows}
    json.dump(report, open(REPORT, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    for r in rows:
        print(f"{r['file']:<22} منتجات {r['products']:<5} حالة {r.get('http_status')} · {r.get('note')}")
    print(f"\n{ok} من {len(rows)} ملفًّا تعيد 200. التقرير: build" + chr(92) + "publish_feeds.json")
    if ok != len(rows):
        sys.exit(2)


if __name__ == "__main__":
    main()
