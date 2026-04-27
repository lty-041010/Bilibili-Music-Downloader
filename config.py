import os
import json
from typing import Dict, Any

# 常量配置
CONFIG_FILE = "config.json"

# 默认配置
DEFAULT_CONFIG = {
    "fid": "",
    "sessdata": "",
    "bili_jct": "",
    "save_path": ""
}

def load_config() -> Dict[str, Any]:
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except json.JSONDecodeError:
            print("配置文件格式错误，使用默认配置")
            return DEFAULT_CONFIG.copy()
        except PermissionError:
            print("无配置文件读写权限，使用默认配置")
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()

def save_config(cfg: Dict[str, Any]) -> None:
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
