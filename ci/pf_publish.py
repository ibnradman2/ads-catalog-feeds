# -*- coding: utf-8 -*-
"""ناشر ملفات المنتجات: التوليد، وشرط القبول، والنسخ إلى المستودع، والرفع، والتحقق من الروابط."""
import datetime as dt
import json, os, subprocess, sys, time

import requests

from pf_common import (BASE_URL, BUILD, DASH, FEEDS, IN_CI, LANG_FILE, MIN_LANG_RATIO, MIN_RATIO,
                       POLL_SECONDS, REPO, UA, VOLATILE, count_products, die, sh)


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
    rows, problems, hold = [], [], set()
    for name in published:
        if name.endswith("-reviews.xml"):
            continue   # ملف التقييمات (P-merchant-022) يولّده feed_reviews لا المولّد الوسيط
        old_n = count_products(os.path.join(REPO, name))
        f = fresh.get(name)
        if not f:
            msg = f"{name}: كان منشورًا ولم يُولَّد الآن (تعذّر تحميل ملف سلة المصدر)."
            if LANG_FILE.search(name):
                print("تحذير: " + msg + " تبقى النسخة المنشورة.")
            else:
                problems.append(msg)
            continue
        new_n = f.get("products") or 0
        if old_n and new_n < old_n * MIN_RATIO:
            msg = f"{name}: المنتجات {new_n} مقابل {old_n} منشورة — أقلّ من {int(MIN_RATIO*100)}%."
            if LANG_FILE.search(name):
                # الملف الإنجليزي يستبعد كل ترجمة قديمة عمدًا، فنقصه تحذير لا يوقف نشر الملفات العربية.
                print("تحذير: " + msg)
                if new_n < old_n * MIN_LANG_RATIO:
                    # انهيار لا استبعاد: ملف لغة بمنتج أو منتجين ينزل بعدد السلع النشطة في Merchant (2026-10-12)
                    print("   ← يُحجب هذا الملف وتبقى النسخة المنشورة.")
                    hold.add(name)
            else:
                problems.append(msg)
    if hold:
        alert_hold(hold)
    if problems:
        die("شرط القبول لم يتحقّق:\n  - " + "\n  - ".join(problems))

    for name, f in sorted(fresh.items()):
        if name in hold:
            continue
        src = os.path.join(FEEDS, name)
        if not os.path.exists(src):
            die(f"{name}: المولّد أعلن إنتاجه ولم يوجد في build" + chr(92) + "feeds.")
        rows.append({"file": name, "products": f.get("products"), "links": f.get("links"),
                     "bytes": os.path.getsize(src),
                     "previous_products": count_products(os.path.join(REPO, name))})
    return rows


def alert_hold(names):
    """ملف لغة حُجب لانهياره: يُسجَّل مشكلةً في ميزان الشغل (المادة 229) ليصلح سببه، ولا يمرّ صامتًا."""
    text = ("حُجب نشر ملفات لغة انهار عدد منتجاتها (بقيت النسخة المنشورة): " + "، ".join(sorted(names))
            + ". السبب في سجل النشر: ابحث عن «يُحجب» ثم أصلح المولّد (المادة 255).")
    board = os.path.join(os.path.dirname(REPO), "routines", "board.py")   # محليًّا C:ds-api؛ وعلى GitHub لا يوجد
    if os.path.exists(board):
        try:
            subprocess.run([sys.executable, board, "add", "--kind", "problem", "--text", text, "--scope", "feeds",
                            "--by", "publish_feeds"], timeout=60, capture_output=True)
        except Exception as e:  # noqa: BLE001
            print("تعذّر تسجيل التنبيه في ميزان الشغل: " + str(e)[:80])
    print("تنبيه: " + text)


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


def push_main():
    """يرفع main. إن رُفض لتقدّم الأصل (تشغيلان متداخلان) يعيد ربط commit المحلي فوقه مفضِّلًا ملفاتنا الأحدث ثم يرفع."""
    p = subprocess.run(["git", "push", "origin", "main"], cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode == 0:
        return
    sh(["git", "fetch", "-q", "origin", "main"])
    sh(["git", "rebase", "-X", "theirs", "origin/main"])
    sh(["git", "push", "origin", "main"])


def publish(changed):
    ensure_git_identity()
    if not changed:
        sha = sh(["git", "rev-parse", "HEAD"])
        if not IN_CI and sh(["git", "rev-list", "--count", "origin/main..HEAD"], check=False) not in ("", "0"):
            push_main()   # commits محلية سابقة لم تُرفع (بعد دمج التفرّع)
            print("لا تغيير جديد، ورُفعت commits سابقة لم تُرفع.")
            return sha, True
        print("لا تغيير في الملفات — لا حاجة إلى رفع جديد.")
        return sha, False
    msg = "تحديث ملفات المنتجات " + dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    sh(["git", "commit", "-q", "-m", msg])
    push_main()
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
