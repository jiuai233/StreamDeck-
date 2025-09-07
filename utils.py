# -*- coding: utf-8 -*-
"""
工具函数模块
包含进程检测、文件处理、图标处理等工具函数
"""

import os
import re
import shutil
import hashlib
from pathlib import Path
from typing import Optional

try:
    import psutil
except ImportError:
    print("错误：需要安装 psutil")
    print("运行：pip install psutil")
    exit(1)

from config import IMAGES_DIR, DEFAULT_ICON


def find_vts_by_process():
    """通过运行进程检测VTube Studio路径"""
    try:
        for proc in psutil.process_iter(['pid', 'name', 'exe']):
            try:
                proc_info = proc.info
                if not proc_info['name']:
                    continue
                    
                if 'vtube' in proc_info['name'].lower() or 'vtubestudio' in proc_info['name'].lower():
                    exe_path = proc_info['exe']
                    if exe_path and Path(exe_path).exists():
                        print(f"检测到运行中的VTube Studio: {proc_info['name']}")
                        
                        vts_dir = Path(exe_path).parent
                        model_dir = vts_dir / "VTube Studio_Data" / "StreamingAssets" / "Live2DModels"
                        
                        if model_dir.exists():
                            model_count = len([p for p in model_dir.iterdir() if p.is_dir()])
                            print(f"自动找到模型目录: {model_dir} ({model_count}个模型)")
                            return model_dir
                            
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
                
        return None
        
    except Exception as e:
        print(f"进程检测时出错: {e}")
        return None


def find_live2d_root():
    """查找模型目录"""
    print("正在检测VTube Studio运行状态...")
    
    model_dir = find_vts_by_process()
    if model_dir:
        return model_dir
    
    print("错误：未检测到运行中的VTube Studio")
    print("请启动VTube Studio后重新运行程序")
    return None


def copy_icon_to_images(src_path, model_name):
    """复制图标到Images目录"""
    if not IMAGES_DIR.exists():
        IMAGES_DIR.mkdir()

    # 生成唯一ID (使用模型名和文件大小的hash)
    icon_file = Path(src_path)
    if not icon_file.exists():
        return "default.png"
    
    content_hash = hashlib.md5(f"{model_name}_{icon_file.stat().st_size}".encode()).hexdigest()[:26].upper()
    new_filename = f"{content_hash}{icon_file.suffix}"
    
    target_path = IMAGES_DIR / new_filename
    
    # 如果目标文件不存在，复制过去
    if not target_path.exists():
        shutil.copy2(icon_file, target_path)
        print(f"  ✓ 复制图标: {icon_file.name} -> {new_filename}")
    else:
        print(f"  ✓ 图标已存在: {new_filename}")
    
    return new_filename


def folder_by_model_name(root, model_name):
    """根据模型名称查找文件夹"""
    for p in root.iterdir():
        if not p.is_dir():
            continue
        name_nosuffix = re.sub(r"_vts$", "", p.name, flags=re.I)
        if p.name.lower() == model_name.lower() or name_nosuffix.lower() == model_name.lower():
            return p
    return None


def pick_icon_from_dir(model_dir, model_name):
    """从模型目录选择图标"""
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    
    for pattern in ("icon.*", "ico_*.*"):
        hits = list(model_dir.glob(pattern))
        if hits:
            print(f"  ✓ 使用 {hits[0].name}")
            return copy_icon_to_images(hits[0], model_name)

    for p in model_dir.iterdir():
        if p.suffix.lower() in exts:
            print(f"  ✓ 使用 {p.name}")
            return copy_icon_to_images(p, model_name)

    print("  ✗ 没找到图片 → 用默认图")
    return "default.png"


def find_icon(model_file_name, model_name):
    """查找模型图标"""
    live2d_root = find_live2d_root()
    if not live2d_root:
        return DEFAULT_ICON
        
    # ① modelFileName 直接推算
    if model_file_name:
        direct_dir = live2d_root / Path(model_file_name).parent
        if direct_dir.exists():
            print(f"◇ 模型 [{model_name}] 目录: {direct_dir}  (来自 modelFileName)")
            return pick_icon_from_dir(direct_dir, model_name)

    # ② modelName 匹配文件夹
    guess_dir = folder_by_model_name(live2d_root, model_name)
    if guess_dir:
        print(f"◇ 模型 [{model_name}] 目录: {guess_dir}  (名称匹配)")
        return pick_icon_from_dir(guess_dir, model_name)

    # ③ all failed
    print(f"⚠ 未在 {live2d_root} 找到 [{model_name}] 对应文件夹 → 用默认图\n")
    return DEFAULT_ICON


def safe_filename(name):
    """安全文件名"""
    return re.sub(r'[\\/:*?"<>| ]+', "_", name)


def wait_for_user_input(message):
    """等待用户按键继续"""
    try:
        input(f"{message}\n按 Enter 键继续...")
    except KeyboardInterrupt:
        print("\n用户中断程序")
        raise


def get_official_profiles_dir():
    """获取官方StreamDock profiles目录"""
    user_profile = os.path.expanduser("~")
    return os.path.join(user_profile, "AppData", "Roaming", "HotSpot", "StreamDock", "profiles")