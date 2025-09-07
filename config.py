# -*- coding: utf-8 -*-
"""
配置文件 - StreamDeck VTS Generator
包含所有全局配置常量
"""

from pathlib import Path

# ---------- VTS API 配置 ----------
VTS_API_URI = "ws://localhost:8001"
PLUGIN_NAME = "StreamDeck VTube Studio"
PLUGIN_DEVELOPER = "Mirabox"
DELAY_AFTER_LOAD = 3.0

# ---------- StreamDeck 配置 ----------
DEVICE_MODEL = "20GBA9901"
DEVICE_UUID = "293V3"
COLUMNS, ROWS = 5, 3
OUTPUT_DIR = "StreamDeck_Profiles"
DEFAULT_ICON = "default.png"
IMAGES_DIR = Path("Images")

# 图像文件
IMG_PREV = "Images/btn_previousPage.png"
IMG_NEXT = "Images/btn_nextPage.png"
IMG_HOTKEY = "Images/vts_logo.png"
IMG_SWITCH = "Images/vts_logo.png"

# UUID 存储文件
UUID_FILE = "profile_uuids.json"

# 坐标与容量
def slot(col, row): 
    return f"{col},{row}"

ROWS_DESC = list(range(ROWS-1, -1, -1))
ALL_SLOTS = [slot(c, r) for r in ROWS_DESC for c in range(COLUMNS)]
PREV_SLOT = slot(0, 0)
NEXT_SLOT = slot(COLUMNS-1, 0)
USABLE = [s for s in ALL_SLOTS if s not in {PREV_SLOT, NEXT_SLOT}]