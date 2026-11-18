# -*- coding: utf-8 -*-
"""ناشر ملفات المنتجات: توجيه ملفات سناب إلى الروابط المنشورة، والاسترجاع، وقراءة الحالة والسحب."""
import datetime as dt
import json, os, sys, time

import pf_stores as S
from pf_common import BUILD, DASH, REPOINT_BASE, _ours, die


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
        if store not in S.SNAP_FEEDS:
            die(f"متجر غير معروف: {store}")
        acc, cat, fid, fname = S.SNAP_FEEDS[store]
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
        acc, cat, fid, fname = S.SNAP_FEEDS[b["store"]]
        tok = u.token_for(acc, toks)
        new_url = REPOINT_BASE + fname
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
    for store in (stores or S.SNAP_FEEDS):
        acc, cat, fid, fname = S.SNAP_FEEDS[store]
        tok = u.token_for(acc, toks)
        pf = _feed_object(u, tok, cat, fid)
        url = (pf.get("schedule") or {}).get("url") or ""
        where = "المنشور" if _ours(url) else "سلة"
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
        for store in (stores or S.SNAP_FEEDS):
            acc, cat, fid, fname = S.SNAP_FEEDS[store]
            tok = u.token_for(acc, toks)
            sc, j = u.get(f"/product_feeds/{fid}/feed_uploads", tok, limit=5)
            ups = [x.get("feed_upload") or {} for x in (j.get("feed_uploads") or [])]
            ups.sort(key=lambda x: x.get("created_at") or "", reverse=True)
            last = ups[0] if ups else {}
            s = last.get("summary") or {}
            out.append({"store": store, "status": last.get("status"),
                        "source": "المنشور" if _ours(last.get("url")) else "سلة",
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
