# -*- coding: utf-8 -*-
"""ناشر ملفات المنتجات: طلب سحب فوري من Merchant Center بعد النشر."""
import json, os, sys

import requests

import pf_stores as S
from pf_common import DASH, IN_CI


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
    for store, (acc, ds, fname) in S.GOOGLE_SOURCES.items():
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
    for store, (acc, ds, fname) in S.GOOGLE_SOURCES.items():
        if changed is not None and fname not in changed:
            continue
        try:
            client.call("datasources", f"accounts/{acc}/dataSources/{ds}:fetch", method="POST", body={})
            print(f"[{store}] طُلب من جوجل سحب {fname} الآن.")
        except m.ApiError as e:
            print(f"[{store}] تعذّر طلب السحب من جوجل: {e.status} {e.message[:120]}")
