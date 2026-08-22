"""Instagram Content Publishing API の薄いラッパー。
Instagram API with Instagram Login（graph.instagram.com）を使う。
Facebookページ連携なしで、IGプロアカウント単体で動く経路。
"""
import os, time, requests

BASE = "https://graph.instagram.com"
API  = os.environ.get("IG_API_VERSION", "v23.0")

class IGError(RuntimeError):
    pass

def _url(path):
    return f"{BASE}/{API}/{path.lstrip('/')}"

def _post(path, token, **params):
    params["access_token"] = token
    r = requests.post(_url(path), data=params, timeout=120)
    if not r.ok:
        raise IGError(f"POST {path} -> {r.status_code} {r.text}")
    return r.json()

def _get(path, token, **params):
    params["access_token"] = token
    r = requests.get(_url(path), params=params, timeout=60)
    if not r.ok:
        raise IGError(f"GET {path} -> {r.status_code} {r.text}")
    return r.json()

def create_image_container(user_id, token, image_url, caption=None, is_carousel_item=False):
    p = {"image_url": image_url}
    if is_carousel_item:
        p["is_carousel_item"] = "true"
    elif caption is not None:
        p["caption"] = caption
    return _post(f"{user_id}/media", token, **p)["id"]

def create_reel_container(user_id, token, video_url, caption=None, cover_url=None, share_to_feed=True):
    p = {"media_type": "REELS", "video_url": video_url,
         "share_to_feed": "true" if share_to_feed else "false"}
    if caption is not None:
        p["caption"] = caption
    if cover_url:
        p["cover_url"] = cover_url
    return _post(f"{user_id}/media", token, **p)["id"]

def create_carousel_container(user_id, token, children, caption=None):
    p = {"media_type": "CAROUSEL", "children": ",".join(children)}
    if caption is not None:
        p["caption"] = caption
    return _post(f"{user_id}/media", token, **p)["id"]

def wait_ready(container_id, token, timeout_s=900, interval_s=5, label=""):
    """コンテナが FINISHED になるまで待つ。
    画像でもカルーセルでも、Instagram 側の処理が終わる前に publish すると
    code 9007「The media is not ready for publishing」で落ちる。
    """
    waited = 0
    last = None
    while waited < timeout_s:
        st = _get(container_id, token, fields="status_code,status")
        code = st.get("status_code")
        if code != last:
            print(f"   [{label or container_id}] {code}")
            last = code
        if code == "FINISHED":
            return
        if code == "ERROR":
            raise IGError(f"container {container_id} failed: {st}")
        time.sleep(interval_s)
        waited += interval_s
    raise IGError(f"container {container_id} not ready after {timeout_s}s (last={last})")

def publish(user_id, token, creation_id, retries=6, backoff_s=10):
    """9007（まだ準備中）は一時的なので、少し待って何度か試す。"""
    for i in range(retries):
        try:
            return _post(f"{user_id}/media_publish", token, creation_id=creation_id)["id"]
        except IGError as e:
            msg = str(e)
            transient = ("9007" in msg) or ("2207027" in msg) or ("not ready" in msg)
            if not transient or i == retries - 1:
                raise
            wait = backoff_s * (i + 1)
            print(f"   publish がまだ受け付けられません。{wait}秒待って再試行 ({i+1}/{retries-1})")
            time.sleep(wait)

def comment(media_id, token, message):
    return _post(f"{media_id}/comments", token, message=message)["id"]

def quota_used(user_id, token):
    try:
        return _get(f"{user_id}/content_publishing_limit", token,
                    fields="config,quota_usage")
    except IGError:
        return None
