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

وتوجيه سناب إلى الروابط المنشورة (عملية منفصلة، تُنفَّذ يدويًّا لا في المهمة اليوميّة):
  python dashboard\publish_feeds.py --snap-status              # قراءة فقط
  python dashboard\publish_feeds.py --repoint asal hayala      # توجيه مع نسخة احتياطية
  python dashboard\publish_feeds.py --restore build\feed_url_backup_<ts>.json
"""
import json, sys, os, re, subprocess, time, datetime as dt
import requests

DASH = os.path.dirname(os.path.abspath(__file__))
# على GitHub Actions يُمرَّر المجلدان عبر متغيّرات البيئة؛ ومحليًّا تبقى القيم كما كانت.
BUILD = os.environ.get("FEEDS_BUILD_DIR") or os.path.join(DASH, "build")
FEEDS = os.path.join(BUILD, "feeds")
REPO = os.environ.get("FEEDS_REPO_DIR") or r"C:\ads-api\feeds_repo"
IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"
BASE_URL = "https://ibnradman2.github.io/ads-catalog-feeds/"
REPORT = os.path.join(BUILD, "publish_feeds.json")
MIN_RATIO = 0.80          # حدّ القبول: نسبة منتجات الملف الجديد إلى المنشور
POLL_SECONDS = 420        # أقصى انتظار لظهور النسخة الجديدة على Pages
UA = "Mozilla/5.0 (compatible; ads-catalog-feeds/1.0)"

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def die(msg):
    print("\n[توقّف] " + msg)
    print("لم يُنشر شيء. الملفات المنشورة حاليًّا باقية كما هي.")
    sys.exit(1)


def sh(args, cwd=REPO, check=True):
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode != 0:
        die(f"فشل الأمر {' '.join(args[:3])} — {(p.stderr or p.stdout or '').strip()[:300]}")
    return (p.stdout or "").strip()


def count_products(path_or_bytes):
    """عدد عناصر <item> في ملف منتجات."""
    if isinstance(path_or_bytes, bytes):
        data = path_or_bytes
    else:
        if not os.path.exists(path_or_bytes):
            return None
        data = open(path_or_bytes, "rb").read()
    return len(re.findall(rb"<item[\s>]", data))


def build_feeds():
    """يشغّل مولّد الملفات الوسيطة داخل هذه العملية نفسها."""
    sys.path.insert(0, DASH)
    import catalog_feed_proxy as p
    argv = sys.argv
    sys.argv = [os.path.join(DASH, "catalog_feed_proxy.py")]      # حتى لا يرث --dry-run وغيره
    try:
        p.main()
    except Exception as e:
        die(f"فشل توليد الملفات الوسيطة — {type(e).__name__}: {str(e)[:200]}")
    finally:
        sys.argv = argv
    rep_path = os.path.join(BUILD, "catalog_feed_proxy.json")
    if not os.path.exists(rep_path):
        die("لم يُكتب build" + chr(92) + "catalog_feed_proxy.json — المولّد لم يكمل عمله.")
    return json.load(open(rep_path, encoding="utf-8"))


def gate(proxy_report):
    """يقارن الملفات الجديدة بالمنشور حاليًّا ويوقف النشر عند أي نقص.

    يعيد قائمة (اسم الملف، منتجات جديدة، روابط معدَّلة، منتجات منشورة سابقًا).
    """
    fresh = {f["file"]: f for f in proxy_report.get("files", []) if f.get("file")}
    if not fresh:
        die("المولّد لم ينتج أي ملف. تحقّق من اتصال الإنترنت ومن مصادر سلة.")

    published = sorted(n for n in os.listdir(REPO) if n.endswith(".xml"))
    rows, problems = [], []
    for name in published:
        old_n = count_products(os.path.join(REPO, name))
        f = fresh.get(name)
        if not f:
            problems.append(f"{name}: كان منشورًا ولم يُولَّد الآن (تعذّر تحميل ملف سلة المصدر).")
            continue
        new_n = f.get("products") or 0
        if old_n and new_n < old_n * MIN_RATIO:
            problems.append(f"{name}: المنتجات {new_n} مقابل {old_n} منشورة — أقلّ من {int(MIN_RATIO*100)}%.")
    if problems:
        die("شرط القبول لم يتحقّق:\n  - " + "\n  - ".join(problems))

    for name, f in sorted(fresh.items()):
        src = os.path.join(FEEDS, name)
        if not os.path.exists(src):
            die(f"{name}: المولّد أعلن إنتاجه ولم يوجد في build" + chr(92) + "feeds.")
        rows.append({"file": name, "products": f.get("products"), "links": f.get("links"),
                     "bytes": os.path.getsize(src),
                     "previous_products": count_products(os.path.join(REPO, name))})
    return rows


VOLATILE = re.compile(rb"<lastBuildDate>.*?</lastBuildDate>", re.S)


def copy_in(rows):
    """ينسخ الملفات إلى المستودع ويعيد أسماء ما تغيّر فعلًا.

    تاريخ البناء (lastBuildDate) يتغيّر في كل تحميل من سلة ولو لم يتغيّر منتج واحد،
    فيُستثنى من المقارنة حتى لا ينتفخ المستودع بنسخة يوميّة لا جديد فيها.
    """
    for r in rows:
        data = open(os.path.join(FEEDS, r["file"]), "rb").read()
        dst = os.path.join(REPO, r["file"])
        if os.path.exists(dst) and VOLATILE.sub(b"", open(dst, "rb").read()) == VOLATILE.sub(b"", data):
            r["changed"] = False
            continue
        open(dst, "wb").write(data)
        r["changed"] = True
    sh(["git", "add", "-A"])
    out = sh(["git", "status", "--porcelain"])
    return [l[3:].strip().strip('"') for l in out.splitlines() if l.strip()]


def ensure_git_identity():
    sh(["git", "config", "user.name", "ibnradman2"])
    sh(["git", "config", "user.email", "ibnradman2@users.noreply.github.com"])
    sh(["git", "config", "core.autocrlf", "false"])
    if IN_CI:
        return   # على Actions يتولّى actions/checkout صلاحية الرفع بـGITHUB_TOKEN
    # مساعد اعتماد غير تفاعلي، حتى لا تتوقّف المهمة المجدولة على نافذة تسجيل دخول
    sh(["git", "config", "--replace-all", "credential.helper", ""])
    sh(["git", "config", "--add", "credential.helper", "!gh auth git-credential"])


def publish(changed):
    ensure_git_identity()
    if not changed:
        sha = sh(["git", "rev-parse", "HEAD"])
        print("لا تغيير في الملفات — لا حاجة إلى رفع جديد.")
        return sha, False
    msg = "تحديث ملفات المنتجات " + dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    sh(["git", "commit", "-q", "-m", msg])
    sh(["git", "push", "origin", "main"])
    sha = sh(["git", "rev-parse", "HEAD"])
    print(f"رُفع {len(changed)} ملفًّا — commit {sha[:8]}")
    return sha, True


def verify(rows, pushed):
    """يتحقّق أن كل رابط يعيد 200 وبعدد المنتجات نفسه. ينتظر انتشار النسخة الجديدة."""
    deadline = time.time() + (POLL_SECONDS if pushed else 60)
    pending = {r["file"]: r for r in rows}
    while pending:
        for name in list(pending):
            r = pending[name]
            url = BASE_URL + name
            try:
                resp = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            except Exception as e:
                r["http_status"], r["served_products"] = 0, None
                r["note"] = type(e).__name__
                continue
            r["url"], r["http_status"] = url, resp.status_code
            r["content_type"] = resp.headers.get("Content-Type", "")
            r["served_products"] = count_products(resp.content) if resp.status_code == 200 else None
            if resp.status_code == 200 and r["served_products"] == r["products"]:
                r["note"] = "مطابق"
                del pending[name]
        if not pending or time.time() > deadline:
            break
        time.sleep(20)
    for r in rows:
        r.setdefault("url", BASE_URL + r["file"])
        if r.get("note") != "مطابق":
            r["note"] = "النسخة المنشورة لم تطابق بعدُ (قد يحتاج Pages دقائق إضافية)"
    return rows


# كتالوجات سناب المقابلة لكل ملف منشور: المتجر → (حساب الإعلانات، الكتالوج، الملف داخل سناب، الملف المنشور)
SNAP_FEEDS = {
    "asal":   ("dc254711-b3de-4f26-9484-364e2c91bdc5", "4bdcb0aa-7c90-4091-a7b1-0530c28dc418",
               "5f86e501-50bb-44c8-b6d2-9a76beab1683", "asal-2-snap.xml"),
    "hayala": ("f46b3709-d6c4-46b6-b144-e6dc8b18af23", "586237b2-9d83-46b7-a557-a8a0e34e27a9",
               "28123ee3-3446-4666-837d-5c0cf34fa9ea", "hayala-2-snap.xml"),
    "areesh": ("66d50fe5-5ca2-49b6-be7f-9b13989b95a1", "370e2192-af56-4f55-a09f-d5b95f7a80f9",
               "06bd5e11-6d75-437d-a0d2-8dd234fdc410", "areesh-1-snap.xml"),
}


def _snap():
    sys.path.insert(0, DASH)
    import utm_snap as u
    return u, u.tokens()


def _feed_object(u, tok, catalog_id, feed_id):
    sc, j = u.get(f"/catalogs/{catalog_id}/product_feeds", tok)
    if sc != 200:
        die(f"تعذّرت قراءة ملفات الكتالوج {catalog_id[:8]} من سناب (حالة {sc}).")
    for f in (j.get("product_feeds") or []):
        pf = f.get("product_feed") or {}
        if pf.get("id") == feed_id:
            return pf
    die(f"لم يوجد الملف {feed_id[:8]} داخل الكتالوج {catalog_id[:8]}.")


def _put_feed(u, tok, catalog_id, pf, new_url):
    body = {"product_feeds": [{
        "id": pf["id"], "name": pf.get("name"), "default_currency": pf.get("default_currency"),
        "feed_type": pf.get("feed_type"), "source": pf.get("source"),
        "schedule": {**(pf.get("schedule") or {}), "url": new_url},
    }]}
    return u.put(f"/catalogs/{catalog_id}/product_feeds", tok, body)


def repoint(stores):
    """يوجّه ملفات سناب إلى الروابط المنشورة، بعد حفظ الروابط السابقة."""
    u, toks = _snap()
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = os.path.join(BUILD, f"feed_url_backup_{ts}.json")
    backup, results = [], []
    for store in stores:
        if store not in SNAP_FEEDS:
            die(f"متجر غير معروف: {store}")
        acc, cat, fid, fname = SNAP_FEEDS[store]
        tok = u.token_for(acc, toks)
        if not tok:
            die(f"تعذّر الحصول على صلاحية لحساب {store}.")
        pf = _feed_object(u, tok, cat, fid)
        old = (pf.get("schedule") or {}).get("url") or ""
        backup.append({"store": store, "adaccount_id": acc, "catalog_id": cat, "feed_id": fid,
                       "name": pf.get("name"), "old_url": old,
                       "updated_at_before": pf.get("updated_at")})
    json.dump(backup, open(backup_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"حُفظت الروابط السابقة في {os.path.basename(backup_path)} (لا يُرفع: يحوي روابط سلة السرّية)")

    for b in backup:
        acc, cat, fid, fname = SNAP_FEEDS[b["store"]]
        tok = u.token_for(acc, toks)
        new_url = BASE_URL + fname
        if b["old_url"] == new_url:
            print(f"[{b['store']}] موجَّه أصلًا إلى الرابط المنشور — لا تغيير.")
            results.append({**b, "new_url": new_url, "status": "بلا تغيير"})
            continue
        pf = _feed_object(u, tok, cat, fid)
        sc, j = _put_feed(u, tok, cat, pf, new_url)
        sub = ((j.get("product_feeds") or [{}])[0]).get("sub_request_status")
        after = _feed_object(u, tok, cat, fid)
        now_url = (after.get("schedule") or {}).get("url")
        ok = (sc == 200 and now_url == new_url)
        print(f"[{b['store']}] حالة {sc} · {sub} · {'تمّ التوجيه' if ok else 'لم يتغيّر الرابط'}")
        results.append({**b, "new_url": new_url, "http_status": sc, "sub_status": sub,
                        "verified": ok, "updated_at_after": after.get("updated_at")})
    json.dump({"as_of": ts, "backup_file": backup_path, "results":
               [{k: v for k, v in r.items() if k != "old_url"} for r in results]},
              open(os.path.join(BUILD, "feed_repoint_snap.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("التقرير: build" + chr(92) + "feed_repoint_snap.json · النسخة الاحتياطية: " + backup_path)


def restore(path):
    """يعيد الروابط السابقة من ملف النسخة الاحتياطية."""
    if not os.path.exists(path):
        die(f"ملف النسخة الاحتياطية غير موجود: {path}")
    u, toks = _snap()
    for b in json.load(open(path, encoding="utf-8")):
        acc, cat, fid = b["adaccount_id"], b["catalog_id"], b["feed_id"]
        tok = u.token_for(acc, toks)
        if not tok:
            die(f"تعذّر الحصول على صلاحية لحساب {b['store']}.")
        pf = _feed_object(u, tok, cat, fid)
        sc, j = _put_feed(u, tok, cat, pf, b["old_url"])
        after = _feed_object(u, tok, cat, fid)
        ok = (after.get("schedule") or {}).get("url") == b["old_url"]
        print(f"[{b['store']}] استرجاع — حالة {sc} · {'تمّ' if ok else 'فشل'}")


def snap_status(stores=None):
    """يقرأ حالة الملفات في سناب: الرابط الحالي ووقت آخر تحديث (آخر سحب)."""
    u, toks = _snap()
    for store in (stores or SNAP_FEEDS):
        acc, cat, fid, fname = SNAP_FEEDS[store]
        tok = u.token_for(acc, toks)
        pf = _feed_object(u, tok, cat, fid)
        url = (pf.get("schedule") or {}).get("url") or ""
        where = "المنشور" if url.startswith(BASE_URL) else "سلة"
        print(f"[{store}] المصدر {where} · آخر تحديث {pf.get('updated_at')} · "
              f"جدولة {(pf.get('schedule') or {}).get('interval_type')}")


def snap_uploads(stores=None, wait=0):
    """حالة آخر عمليّات السحب في سناب لكل ملف: المصدر، الحالة، عدد المنتجات، الأخطاء.

    المنفذ الوحيد الذي يكشف ذلك هو /product_feeds/{id}/feed_uploads (لا يوجد
    product_feed_uploads ولا أي منفذ آخر؛ جُرّبت فأعادت 404).
    """
    u, toks = _snap()
    deadline = time.time() + wait
    out = []
    while True:
        out = []
        for store in (stores or SNAP_FEEDS):
            acc, cat, fid, fname = SNAP_FEEDS[store]
            tok = u.token_for(acc, toks)
            sc, j = u.get(f"/product_feeds/{fid}/feed_uploads", tok, limit=5)
            ups = [x.get("feed_upload") or {} for x in (j.get("feed_uploads") or [])]
            ups.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            last = ups[0] if ups else {}
            s = last.get("summary") or {}
            out.append({"store": store, "status": last.get("status"),
                        "source": "المنشور" if (last.get("url") or "").startswith(BASE_URL) else "سلة",
                        "total_items": s.get("total_items"), "items_modified": s.get("items_modified"),
                        "created_at": last.get("created_at"),
                        "issues": (s.get("issues_summary") or {}).get("errors") or {}})
        if time.time() >= deadline or all(r["status"] not in ("INITIALIZED", "IN_PROGRESS", "FETCHING", "PROCESSING", None) for r in out):
            break
        time.sleep(30)
    for r in out:
        print(f"[{r['store']}] مصدر {r['source']} · {r['status']} · منتجات {r['total_items']} · "
              f"أخطاء {r['issues'] or 'لا شيء'} · {r['created_at']}")
    json.dump(out, open(os.path.join(BUILD, "feed_uploads_snap.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return out


# مصادر Merchant Center الأساسية التي تسحب ملفات جوجل المنشورة: المتجر → (الحساب، المصدر، الملف)
# جوجل لا يقبل جدولة سحب أقصر من يومية، فتطلب هذه المهمة الساعية سحبًا فوريًّا بعد كل نشر.
GOOGLE_SOURCES = {
    "asal":   ("262993710", "204430403", "asal-2-google.xml"),
    "areesh": ("742634052", "10086822428", "areesh-1-google.xml"),
    "hayala": ("683146519", "10086393943", "hayala-2-google.xml"),
}


def _ci_google_fetch(changed):
    """نسخة Actions: لا يوجد merchant_radar هناك، فيُقرأ مفتاح حساب الخدمة من السرّ MERCHANT_SA_JSON.
    إن غاب السرّ يُتخطّى الطلب، ويسحب جوجل الملف في موعده اليومي المعتاد."""
    raw = os.environ.get("MERCHANT_SA_JSON", "").strip()
    if not raw:
        print("سحب جوجل الفوري: متخطّى (السرّ MERCHANT_SA_JSON غير موجود).")
        return
    try:
        from google.oauth2 import service_account
        from google.auth.transport.requests import Request
        creds = service_account.Credentials.from_service_account_info(
            json.loads(raw), scopes=["https://www.googleapis.com/auth/content"])
        creds.refresh(Request())
    except Exception as e:  # noqa: BLE001
        print("سحب جوجل الفوري: تعذّر الدخول — " + e.__class__.__name__)
        return
    for store, (acc, ds, fname) in GOOGLE_SOURCES.items():
        if changed is not None and fname not in changed:
            continue
        url = f"https://merchantapi.googleapis.com/datasources/v1/accounts/{acc}/dataSources/{ds}:fetch"
        try:
            r = requests.post(url, headers={"Authorization": "Bearer " + creds.token}, json={}, timeout=60)
            ok = r.status_code < 400
            print(f"[{store}] " + (f"طُلب من جوجل سحب {fname} الآن." if ok
                                   else f"تعذّر طلب السحب من جوجل: {r.status_code}"))
        except Exception as e:  # noqa: BLE001
            print(f"[{store}] تعذّر طلب السحب من جوجل: {e.__class__.__name__}")


def google_fetch(changed=None):
    """يطلب من Merchant Center سحب الملف الآن للمتاجر التي تغيّر ملف جوجل فيها (أو كلها إن لم يُحدَّد)."""
    if IN_CI:
        return _ci_google_fetch(changed)
    sys.path.insert(0, DASH)
    import merchant_radar as m
    try:
        client = m.Client()
    except Exception as e:  # noqa: BLE001
        print("سحب جوجل الفوري: تعذّر الدخول — " + e.__class__.__name__)
        return
    for store, (acc, ds, fname) in GOOGLE_SOURCES.items():
        if changed is not None and fname not in changed:
            continue
        try:
            client.call("datasources", f"accounts/{acc}/dataSources/{ds}:fetch", method="POST", body={})
            print(f"[{store}] طُلب من جوجل سحب {fname} الآن.")
        except m.ApiError as e:
            print(f"[{store}] تعذّر طلب السحب من جوجل: {e.status} {e.message[:120]}")


def main():
    dry = "--dry-run" in sys.argv
    if "--google-fetch" in sys.argv:
        return google_fetch()
    if "--snap-uploads" in sys.argv:
        i = sys.argv.index("--snap-uploads")
        w = int(sys.argv[i + 1]) if len(sys.argv) > i + 1 and sys.argv[i + 1].isdigit() else 0
        return snap_uploads(wait=w)
    if "--repoint" in sys.argv:
        i = sys.argv.index("--repoint")
        stores = [a for a in sys.argv[i + 1:] if not a.startswith("-")]
        return repoint(stores or ["asal", "hayala"])
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
    proxy_report = ({"files": [{"file": n, "products": count_products(os.path.join(FEEDS, n)), "links": None}
                               for n in sorted(os.listdir(FEEDS)) if n.endswith(".xml")]}
                    if "--no-build" in sys.argv else build_feeds())
    rows = gate(proxy_report)
    changed = copy_in(rows)
    if dry:
        print("تجربة فقط — لم يُرفع شيء. المتغيّر: " + (", ".join(changed) or "لا شيء"))
        sh(["git", "reset", "-q", "HEAD"], check=False)
        sh(["git", "checkout", "--", "."], check=False)
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
