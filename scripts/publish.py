#!/usr/bin/env python3
"""queue/ の中から「今日（JST）投稿予定」のものを1件だけ投稿する。

使い方:
  python scripts/publish.py            # 今日の分
  python scripts/publish.py 2026-08-21 # 日付を指定
  DRY_RUN=1 python scripts/publish.py  # APIを叩かず、組み立てだけ確認
"""
import os, sys, json
from datetime import datetime, timezone, timedelta
import yaml
import ig

JST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DRY  = os.environ.get("DRY_RUN") == "1"

def media_url(rel):
    """media/ 配下のファイルを raw.githubusercontent.com の公開URLにする。
    Meta 側がこのURLを取りに来るため、リポジトリは public である必要がある。"""
    repo = os.environ["GITHUB_REPOSITORY"]          # owner/name
    ref  = os.environ.get("GITHUB_SHA") or "main"
    rel  = rel.lstrip("/")
    return f"https://raw.githubusercontent.com/{repo}/{ref}/{rel}"

def load_entry(date_str):
    p = os.path.join(ROOT, "queue", f"{date_str}.yml")
    if not os.path.exists(p):
        return None, None
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f), p

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else datetime.now(JST).strftime("%Y-%m-%d")
    entry, path = load_entry(date_str)
    if not entry:
        print(f"[skip] {date_str} の予定はありません")
        return 0

    # dry-run のときは Secrets 未設定でも動くようにする
    user_id = os.environ.get("IG_USER_ID", "")
    token   = os.environ.get("IG_ACCESS_TOKEN", "")
    if not DRY and not (user_id and token):
        print("[error] IG_USER_ID / IG_ACCESS_TOKEN が未設定です"); return 1
    kind    = entry.get("type", "carousel")
    caption = (entry.get("caption") or "").rstrip()
    media   = entry.get("media") or []
    first_c = (entry.get("first_comment") or "").strip()

    if not media:
        print(f"[error] {path}: media が空です"); return 1
    if kind == "carousel" and not (2 <= len(media) <= 10):
        print(f"[error] カルーセルは2〜10枚です（今: {len(media)}）"); return 1

    urls = [media_url(m) for m in media]
    print(f"[plan] {date_str} / {kind} / {len(urls)}点")
    for u in urls: print("   ", u)
    print(f"[plan] caption {len(caption)}文字 / first_comment {'あり' if first_c else 'なし'}")

    if DRY:
        print("[dry-run] ここで終了。APIは叩いていません。"); return 0

    q = ig.quota_used(user_id, token)
    if q: print("[quota]", json.dumps(q, ensure_ascii=False))

    if kind == "reel":
        cid = ig.create_reel_container(user_id, token, urls[0], caption=caption,
                                       cover_url=(media_url(entry["cover"]) if entry.get("cover") else None))
    elif kind == "image":
        cid = ig.create_image_container(user_id, token, urls[0], caption=caption)
    else:
        children = []
        for i, u in enumerate(urls, 1):
            ch = ig.create_image_container(user_id, token, u, is_carousel_item=True)
            print("   child:", ch)
            # 子コンテナも FINISHED を待つ。待たずに親を作ると公開時に 9007 で落ちる
            ig.wait_ready(ch, token, timeout_s=300, interval_s=5, label=f"child{i}")
            children.append(ch)
        cid = ig.create_carousel_container(user_id, token, children, caption=caption)

    print("[container]", cid)
    # 画像・カルーセル・リールいずれも、公開前に処理完了を待つ
    ig.wait_ready(cid, token, timeout_s=900, interval_s=5, label="container")

    media_id = ig.publish(user_id, token, cid)
    print("[published]", media_id)

    if first_c:
        try:
            print("[comment]", ig.comment(media_id, token, first_c))
        except Exception as e:
            print("[warn] 最初のコメントに失敗:", e)

    # 二重投稿を防ぐため published/ へ退避
    done_dir = os.path.join(ROOT, "published")
    os.makedirs(done_dir, exist_ok=True)
    os.rename(path, os.path.join(done_dir, f"{date_str}.yml"))
    with open(os.path.join(done_dir, f"{date_str}.result.json"), "w", encoding="utf-8") as f:
        json.dump({"date": date_str, "type": kind, "media_id": media_id,
                   "count": len(urls)}, f, ensure_ascii=False, indent=2)
    print("[done]")
    return 0

if __name__ == "__main__":
    sys.exit(main())
