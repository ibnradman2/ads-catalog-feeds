# -*- coding: utf-8 -*-
"""ناشر ملفات المنتجات: الثوابت والمسارات والأدوات المشتركة (die وsh وcount_products).

وحدة من تقسيم publish_feeds.py (حارس الأداء، المادة 467)، بلا تغيير في السلوك.
"""
import json, sys, os, re, subprocess, time, datetime as dt
import requests

try:   # محليًّا: سجل المتاجر الموحّد (P-onboarding-001) لتصدير ci/data/stores.json وحده. على GitHub لا سجل
    import stores_registry as R   # (المستودع عام)، فيقرأ كل شيء من stores.json المرفوع (P-merchant-025).
except Exception:  # noqa: BLE001
    R = None

DASH = os.path.dirname(os.path.abspath(__file__))
# على GitHub Actions يُمرَّر المجلدان عبر متغيّرات البيئة؛ ومحليًّا تبقى القيم كما كانت.
BUILD = os.environ.get("FEEDS_BUILD_DIR") or os.path.join(DASH, "build")
FEEDS = os.path.join(BUILD, "feeds")
REPO = os.environ.get("FEEDS_REPO_DIR") or r"C:\ads-api\feeds_repo"
IN_CI = os.environ.get("GITHUB_ACTIONS") == "true"
BASE_URL = "https://ibnradman2.github.io/ads-catalog-feeds/"
# الرابط الجديد على كلاودفلير (المادة 546). التوجيه (--repoint) إليه بتمرير FEEDS_REPOINT_BASE، والنشر نفسه يبقى على Pages
NEW_BASE = "https://catalog-feeds.ibnradman2.workers.dev/"
REPOINT_BASE = os.environ.get("FEEDS_REPOINT_BASE") or BASE_URL


def _ours(url):
    return (url or "").startswith((BASE_URL, NEW_BASE))
REPORT = os.path.join(BUILD, "publish_feeds.json")
MIN_RATIO = 0.80          # حدّ القبول: نسبة منتجات الملف الجديد إلى المنشور
POLL_SECONDS = 420        # أقصى انتظار لظهور النسخة الجديدة على Pages
UA = "Mozilla/5.0 (compatible; ads-catalog-feeds/1.0)"


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


MIN_LANG_RATIO = 0.8   # ملف لغة ينزل تحت 80% من المنشور يُحجب وتبقى نسخته المنشورة، كالملف العربي (حادثة 2026-10-12)
LANG_FILE = re.compile(r"-(google|meta|snap)-[a-z]{2,3}\.xml$")   # ملفات اللغات: نقصها تحذير لا يوقف العربي
VOLATILE = re.compile(rb"<lastBuildDate>.*?</lastBuildDate>", re.S)
