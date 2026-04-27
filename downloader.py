import os
import re
import time
import subprocess
import requests
import platform
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional
from api import get_audio_url

# 常量配置
DOWNLOAD_TIMEOUT = 30
FFMPEG_TIMEOUT = 300
MAX_RETRY = 3
MAX_WORKERS = 3

def get_ffmpeg_cmd(temp_audio: str, final_audio: str, bitrate: str = "320k", format: str = "MP3") -> str:
    system = platform.system()
    # 处理路径转义（跨平台）
    temp_audio = os.path.normpath(temp_audio)
    final_audio = os.path.normpath(final_audio)
    
    # 根据格式生成不同的命令
    if format == "MP3":
        codec = "libmp3lame"
        bitrate_param = f"-b:a {bitrate}"
    elif format == "WAV":
        codec = "pcm_s16le"
        bitrate_param = ""
    elif format == "FLAC":
        codec = "flac"
        bitrate_param = ""
    else:
        codec = "libmp3lame"
        bitrate_param = f"-b:a 320k"
    
    if system == "Windows":
        return f'ffmpeg -y -i "{temp_audio}" -acodec {codec} {bitrate_param} "{final_audio}" -v 0'
    else:
        # Linux/macOS 下无需双引号转义（避免shell解析问题）
        return f'ffmpeg -y -i {temp_audio} -acodec {codec} {bitrate_param} {final_audio} -v 0'

def clean_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|]', "", name)

def single_download(item: dict, save_path: str, sessdata: str, log_func: Callable[[str], None], 
                   progress_func: Callable[[int, str], None], quality: str = "320k", 
                   format: str = "MP3", main_window: Optional[object] = None) -> bool:
    title = item["title"]
    bvid = item["bvid"]
    log_func(f"\n—————— {title} ——————")
    ok = False
    for _ in range(MAX_RETRY):
        # 检查是否取消下载
        if main_window and main_window.download_cancel:
            log_func(f"❌ 已取消下载：{title}")
            return False
        # 检查是否暂停下载
        while main_window and main_window.download_pause:
            time.sleep(1)
            if main_window.download_cancel:
                log_func(f"❌ 已取消下载：{title}")
                return False
        url, msg = get_audio_url(bvid, sessdata)
        if url and download_and_convert(bvid, title, url, save_path, log_func, progress_func, 
                                       sessdata, quality, format, main_window):
            ok = True
            break
        time.sleep(1.5)
    if not ok:
        log_func(f"❌ 多次下载失败：{title}")
    return ok

def download_and_convert(bvid: str, title: str, url: str, save_path: str, 
                        log_func: Callable[[str], None], progress_func: Callable[[int, str], None], 
                        sessdata: str, quality: str = "320k", format: str = "MP3", 
                        main_window: Optional[object] = None) -> bool:
    title = clean_filename(title)
    temp_audio = os.path.join(save_path, f"{title}.m4a")
    final_audio = os.path.join(save_path, f"{title}.{format.lower()}")
    
    # 重复下载检测
    if os.path.exists(final_audio):
        log_func(f"⚠️ {title} 已存在，跳过下载")
        return True
    
    try:
        log_func(f"开始下载：{title}")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": f"https://www.bilibili.com/video/{bvid}/",
            "Cookie": f"SESSDATA={sessdata}"
        }
        with requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT) as r:
            r.raise_for_status()
            total_size = int(r.headers.get("content-length", 0))
            downloaded_size = 0
            with open(temp_audio, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024*1024):
                    # 检查是否取消下载
                    if main_window and main_window.download_cancel:
                        log_func(f"❌ 已取消下载：{title}")
                        if os.path.exists(temp_audio):
                            os.remove(temp_audio)
                        return False
                    # 检查是否暂停下载
                    while main_window and main_window.download_pause:
                        time.sleep(1)
                        if main_window.download_cancel:
                            log_func(f"❌ 已取消下载：{title}")
                            if os.path.exists(temp_audio):
                                os.remove(temp_audio)
                            return False
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            progress = int(downloaded_size / total_size * 100)
                            progress_func(progress, title)
        # 根据格式和音质生成跨平台兼容的ffmpeg命令
        cmd = get_ffmpeg_cmd(temp_audio, final_audio, quality, format)
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT
        )
        if result.returncode != 0:
            raise Exception(f"ffmpeg转换失败：{result.stderr[:100]}")
        if os.path.exists(temp_audio):
            os.remove(temp_audio)
        log_func(f"✅ 完成：{title}")
        return True
    except subprocess.TimeoutExpired:
        log_func("❌ 失败：ffmpeg转换超时")
        if os.path.exists(temp_audio):
            os.remove(temp_audio)
        return False
    except Exception as e:
        log_func(f"❌ 失败：{str(e)[:50]}")
        if os.path.exists(temp_audio):
            os.remove(temp_audio)
        return False

def download_audio_task(video_list: list, select_rows: list, save_path: str, sessdata: str, 
                       log_func: Callable[[str], None], progress_func: Callable[[int, str], None], 
                       quality: str = "320k", format: str = "MP3", 
                       main_window: Optional[object] = None) -> None:
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for row in select_rows:
            item = video_list[row]
            futures.append(executor.submit(
                single_download, item, save_path, sessdata, log_func, progress_func, 
                quality, format, main_window
            ))
        # 等待所有任务完成
        for future in futures:
            future.result()
    log_func("\n===== 全部任务结束 =====")
