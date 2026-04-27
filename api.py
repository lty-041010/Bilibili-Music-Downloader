import requests
import requests.exceptions
from typing import Tuple, List, Optional

# 常量配置
API_FAV_LIST = "https://api.bilibili.com/x/v3/fav/resource/list"
API_VIDEO_INFO = "https://api.bilibili.com/x/web-interface/view"
API_PLAY_URL = "https://api.bilibili.com/x/player/playurl"
REQUEST_TIMEOUT = 10
MAX_RETRY = 3

def get_all_favorite(fid: str, sessdata: str, bili_jct: str) -> Tuple[List[dict], str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://space.bilibili.com/",
        "Cookie": f"SESSDATA={sessdata}; bili_jct={bili_jct}"
    }
    all_videos = []
    page = 1
    try:
        while True:
            params = {"media_id": fid, "pn": page, "ps": 20, "platform": "web"}
            resp = requests.get(API_FAV_LIST, headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            data = resp.json()
            if data["code"] == -101:
                return [], "Cookie过期（SESSDATA/bili_jct无效），请重新获取"
            if data["code"] != 0:
                return [], data["message"]
            medias = data["data"]["medias"]
            if not medias:
                break
            all_videos.extend(medias)
            page += 1
        return all_videos, "success"
    except requests.exceptions.Timeout:
        return [], "请求超时（请检查网络/重试）"
    except requests.exceptions.ConnectionError:
        return [], "网络连接失败（请检查网络）"
    except requests.exceptions.HTTPError as e:
        return [], f"HTTP错误：{e.response.status_code}"
    except Exception as e:
        return [], f"网络错误：{str(e)}"

def get_audio_url(bvid: str, sessdata: str, cid: Optional[str] = None) -> Tuple[Optional[str], str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": f"https://www.bilibili.com/video/{bvid}/",
        "Cookie": f"SESSDATA={sessdata}"
    }
    if not cid:
        info_resp = requests.get(API_VIDEO_INFO, headers=headers, params={"bvid": bvid}, timeout=REQUEST_TIMEOUT).json()
        if info_resp["code"] == -101:
            return None, "Cookie过期（SESSDATA无效），请重新获取"
        if info_resp["code"] != 0:
            return None, info_resp["message"]
        cid = info_resp["data"]["cid"]
    play_resp = requests.get(API_PLAY_URL, headers=headers, params={
        "bvid": bvid,
        "cid": cid,
        "qn": 0,
        "fnval": 16,
        "fnver": 0,
        "fourk": 0
    }, timeout=REQUEST_TIMEOUT).json()
    if play_resp["code"] == -101:
        return None, "Cookie过期（SESSDATA无效），请重新获取"
    if play_resp["code"] != 0:
        return None, play_resp["message"]
    dash = play_resp["data"].get("dash")
    if not dash or "audio" not in dash:
        return None, "无音频流/版权限制"
    audio_list = dash["audio"]
    audio_list.sort(key=lambda x: x["bandwidth"], reverse=True)
    return audio_list[0]["baseUrl"], "success"
