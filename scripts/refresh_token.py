#!/usr/bin/env python3
"""長期アクセストークン（60日）を延長し、新しい値を stdout に出す。
延長条件: トークンが発行から24時間以上経っていて、まだ失効していないこと。
失効させると再取得（手動）になるので、月1回まわして常に余裕を持たせる。"""
import os, sys, requests

r = requests.get("https://graph.instagram.com/refresh_access_token",
                 params={"grant_type": "ig_refresh_token",
                         "access_token": os.environ["IG_ACCESS_TOKEN"]},
                 timeout=60)
if not r.ok:
    print(f"[error] {r.status_code} {r.text}", file=sys.stderr); sys.exit(1)
d = r.json()
print(f"[ok] 残り {d.get('expires_in')} 秒（約{int(d.get('expires_in',0))//86400}日）", file=sys.stderr)
print(d["access_token"])
