# -*- coding: utf-8 -*-
"""
StreamDeck配置生成模块
负责生成StreamDeck的profile文件夹和manifest文件
"""

import json
import shutil
import uuid
import pathlib
from pathlib import Path

from config import (
    DEVICE_MODEL, DEVICE_UUID, OUTPUT_DIR, IMAGES_DIR,
    IMG_PREV, IMG_NEXT, IMG_HOTKEY, IMG_SWITCH,
    PREV_SLOT, NEXT_SLOT, USABLE
)
from uuid_manager import get_home_uuid, get_model_uuid
from utils import safe_filename, get_official_profiles_dir


def mk_btn(img, name, uuid_key, settings=None, show_title=True):
    """创建按钮配置"""
    st = {"Image": img}
    if show_title:
        st.update({"Title": name, "TitleAlignment": "middle", "FontSize": 14, "FontStyle": "Bold"})
    return {
        "ActionID": str(uuid.uuid4()),
        "Controller": "",
        "Name": name,
        "Settings": settings or {},
        "State": 0,
        "States": [st],
        "UUID": uuid_key
    }


def get_page_capacity(page_idx, total_pages):
    """计算模型页面每页容量"""
    if total_pages == 1:
        return 14
    elif page_idx == 0:
        return 14
    elif page_idx == total_pages - 1:
        return 14
    else:
        return 13


def get_home_page_capacity(page_idx, total_pages):
    """计算主页每页容量"""
    if total_pages == 1:
        return 15  # 单页可以使用所有15个按钮
    elif page_idx == 0:
        return 14  # 首页：14个按钮（无Previous按钮）
    elif page_idx == total_pages - 1:
        return 14  # 末页：14个按钮（无Next按钮）
    else:
        return 13  # 中间页：13个按钮（需要Previous和Next按钮）


def generate_model_profile_folder(model_data):
    """生成单个模型的 profile 文件夹"""
    model_name = model_data["modelName"]
    safe_name = safe_filename(model_name)
    
    print(f"\n=== Generating {model_name} profile folder ===")
    
    # 获取模型UUID
    model_uuid = get_model_uuid(model_name)
    
    # 创建模型 profile 文件夹
    profile_folder = pathlib.Path(OUTPUT_DIR) / f"{model_uuid}.sdProfile"
    if profile_folder.exists():
        shutil.rmtree(profile_folder)
    profile_folder.mkdir(parents=True, exist_ok=True)
    
    # 复制Images目录
    images_dst = profile_folder / "Images"
    images_src = pathlib.Path("Images")
    if images_src.exists():
        shutil.copytree(images_src, images_dst)
    else:
        images_dst.mkdir()
    
    # 创建子页面目录
    profiles_dir = profile_folder / "profiles"
    profiles_dir.mkdir(exist_ok=True)
    
    # 生成页面
    hotkeys = model_data["hotkeys"]
    page_ids = []
    
    # 计算分页
    rough_pages = max(1, (len(hotkeys) + 12) // 13)  # 粗略估算
    hk_chunks = []
    remaining_hotkeys = hotkeys[:]
    page_idx = 0
    
    if not remaining_hotkeys:
        hk_chunks.append([])
    else:
        while remaining_hotkeys:
            capacity = get_page_capacity(page_idx, rough_pages)
            if page_idx == 0:
                capacity -= 1  # 为切换模型按钮预留位置
            
            chunk = remaining_hotkeys[:capacity]
            remaining_hotkeys = remaining_hotkeys[capacity:]
            hk_chunks.append(chunk)
            page_idx += 1
    
    total_pages = len(hk_chunks)
    
    # 生成每个页面
    for page_idx, chunk in enumerate(hk_chunks):
        page_uuid = str(uuid.uuid4()).upper()
        page_folder = profiles_dir / f"{page_uuid}.sdProfile"
        page_folder.mkdir(parents=True, exist_ok=True)
        page_ids.append(f"{page_uuid}.sdProfile")
        
        # 为每个子页面创建Images文件夹并复制图标
        page_images_dst = page_folder / "Images"
        if images_src.exists():
            shutil.copytree(images_src, page_images_dst)
        else:
            page_images_dst.mkdir()
        
        # 页面动作
        acts = {}
        
        # 导航按钮
        if page_idx > 0:
            acts[PREV_SLOT] = mk_btn(IMG_PREV, "Previous", "com.hotspot.streamdock.page.previous", show_title=False)
        if page_idx < total_pages - 1:
            acts[NEXT_SLOT] = mk_btn(IMG_NEXT, "Next", "com.hotspot.streamdock.page.next", show_title=False)
        
        # 可用槽位
        current_usable = [s for s in USABLE]
        if page_idx == 0:
            current_usable = [PREV_SLOT] + current_usable
        if page_idx == total_pages - 1:
            current_usable = current_usable + [NEXT_SLOT]
        
        hk_slots_iter = iter(current_usable)
        
        # 第一页添加切换模型按钮
        if page_idx == 0:
            switch_slot = next(hk_slots_iter)
            model_icon = model_data.get("icon", IMG_SWITCH)
            acts[switch_slot] = mk_btn(
                model_icon, "切换模型",
                "com.mirabox.streamdock.VtubeStudio.action1",
                {
                    "ip": "127.0.0.1", "port": "8001",
                    "selectModelID": model_data["modelID"],
                    "showTitle": True
                })
            
            # 返回Home按钮
            home_slot = "0,2"
            acts[home_slot] = mk_btn(
                IMG_SWITCH, "Back to Home",
                "com.hotspot.streamdock.profile.rotate",
                {
                    "DeviceUUID": "",
                    "ProfileUUID": get_home_uuid()
                })
        
        # 填充动作
        for hk in chunk:
            try:
                sl = next(hk_slots_iter)
                if page_idx == 0 and sl == "0,2":  # 跳过被占用的位置
                    sl = next(hk_slots_iter)
                
                # 处理热键图标路径
                hotkey_icon = model_data.get("icon", IMG_HOTKEY)
                
                acts[sl] = mk_btn(
                    hotkey_icon, hk["name"] or hk["type"],
                    "com.mirabox.streamdock.VtubeStudio.action2",
                    {
                        "ip": "127.0.0.1", "port": "8001",
                        "selectModelID": model_data["modelID"],
                        "selectHotKeyID": hk["hotkeyID"],
                        "selectHotKeyName": hk["name"],
                        "showTitle": True
                    })
            except StopIteration:
                break
        
        # 写页面manifest
        page_manifest = {
            "DeviceModel": DEVICE_MODEL,
            "DeviceUUID": DEVICE_UUID,
            "Name": model_name,
            "Version": "1.0",
            "Actions": acts
        }
        
        with open(page_folder / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(page_manifest, f, indent=2, ensure_ascii=False)
        
        print(f"  Page {page_idx+1}: {len(acts)} actions")
    
    # 写根manifest
    root_manifest = {
        "DeviceModel": DEVICE_MODEL,
        "DeviceUUID": DEVICE_UUID,
        "Name": model_name,
        "Version": "1.0",
        "Actions": {},
        "Pages": {
            "Current": page_ids[0] if page_ids else "",
            "Pages": page_ids
        },
        "ProfileUUID": model_uuid
    }
    
    with open(profile_folder / "manifest.json", 'w', encoding='utf-8') as f:
        json.dump(root_manifest, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Generated: {profile_folder}")
    return profile_folder


def generate_home_profile_folder(models_data):
    """生成Home profile文件夹（支持分页）"""
    print(f"\n=== Generating Home profile folder with pagination ===")
    
    home_uuid = get_home_uuid()
    
    # 创建Home profile文件夹
    home_folder = pathlib.Path(OUTPUT_DIR) / f"{home_uuid}.sdProfile"
    if home_folder.exists():
        shutil.rmtree(home_folder)
    home_folder.mkdir(parents=True, exist_ok=True)
    
    # 复制Images目录
    images_dst = home_folder / "Images"
    images_src = pathlib.Path("Images")
    if images_src.exists():
        shutil.copytree(images_src, images_dst)
    else:
        images_dst.mkdir()
    
    # 创建子页面目录
    profiles_dir = home_folder / "profiles"
    profiles_dir.mkdir(exist_ok=True)
    
    # 计算分页
    total_models = len(models_data)
    rough_pages = max(1, (total_models + 12) // 13)  # 粗估页数
    
    # 分配模型到各页
    model_chunks = []
    remaining_models = models_data[:]
    page_idx = 0
    
    if not remaining_models:
        model_chunks.append([])
    else:
        while remaining_models:
            capacity = get_home_page_capacity(page_idx, rough_pages)
            chunk = remaining_models[:capacity]
            remaining_models = remaining_models[capacity:]
            model_chunks.append(chunk)
            page_idx += 1
    
    total_pages = len(model_chunks)
    page_uuids = []
    
    print(f"  总模型数: {total_models}, 分为 {total_pages} 页")
    
    # 生成每一页
    for page_idx, model_chunk in enumerate(model_chunks):
        page_uuid = str(uuid.uuid4()).upper()
        page_uuids.append(f"{page_uuid}.sdProfile")
        page_folder = profiles_dir / f"{page_uuid}.sdProfile"
        page_folder.mkdir(parents=True, exist_ok=True)
        
        # 为页面创建Images文件夹
        page_images_dst = page_folder / "Images"
        if images_src.exists():
            shutil.copytree(images_src, page_images_dst)
        else:
            page_images_dst.mkdir()
        
        acts = {}
        
        # 添加导航按钮
        if page_idx > 0:
            acts[PREV_SLOT] = mk_btn(IMG_PREV, "Previous", "com.hotspot.streamdock.page.previous", show_title=False)
        if page_idx < total_pages - 1:
            acts[NEXT_SLOT] = mk_btn(IMG_NEXT, "Next", "com.hotspot.streamdock.page.next", show_title=False)
        
        # 计算可用槽位
        current_usable = [s for s in USABLE]
        if page_idx == 0:
            current_usable = [PREV_SLOT] + current_usable  # 首页可以使用PREV_SLOT
        if page_idx == total_pages - 1:
            current_usable = current_usable + [NEXT_SLOT]  # 末页可以使用NEXT_SLOT
        
        # 为模型创建按钮
        for i, model_data in enumerate(model_chunk):
            if i >= len(current_usable):
                break
            
            slot_pos = current_usable[i]
            model_uuid = get_model_uuid(model_data["modelName"])
            
            # 处理图标路径
            home_icon = model_data.get("icon", IMG_SWITCH)
            
            acts[slot_pos] = mk_btn(
                home_icon, model_data["modelName"],
                "com.hotspot.streamdock.profile.rotate",
                {
                    "DeviceUUID": "",
                    "ProfileUUID": model_uuid
                })
            print(f"  页面 {page_idx + 1}: 添加模型按钮 {model_data['modelName']} -> {model_uuid}")
        
        # 写页面manifest
        page_manifest = {
            "DeviceModel": DEVICE_MODEL,
            "DeviceUUID": DEVICE_UUID,
            "Name": f"Home-{page_idx + 1}",
            "Version": "1.0",
            "Actions": acts
        }
        
        with open(page_folder / "manifest.json", 'w', encoding='utf-8') as f:
            json.dump(page_manifest, f, indent=2, ensure_ascii=False)
        
        print(f"  生成页面 {page_idx + 1}: {len(model_chunk)} 个模型")
    
    # 写Home根manifest
    home_root_manifest = {
        "DeviceModel": DEVICE_MODEL,
        "DeviceUUID": DEVICE_UUID,
        "Name": "Home",
        "Version": "1.0",
        "Actions": {},
        "Pages": {
            "Current": page_uuids[0],
            "Pages": page_uuids
        },
        "ProfileUUID": home_uuid
    }
    
    with open(home_folder / "manifest.json", 'w', encoding='utf-8') as f:
        json.dump(home_root_manifest, f, indent=2, ensure_ascii=False)
    
    print(f"[OK] Generated: {home_folder}")
    print(f"  包含 {total_models} 个模型，分布在 {total_pages} 页中")
    return home_folder


def copy_to_official_directory():
    """复制到官方目录"""
    output_path = pathlib.Path(OUTPUT_DIR)
    official_path = pathlib.Path(get_official_profiles_dir())
    
    if not output_path.exists():
        print("❌ 输出目录不存在，请先生成profile文件夹")
        return
    
    try:
        if not official_path.exists():
            official_path.mkdir(parents=True, exist_ok=True)
        
        print(f"\n=== 复制到官方目录 ===")
        
        for profile_folder in output_path.iterdir():
            if profile_folder.is_dir() and profile_folder.name.endswith('.sdProfile'):
                target = official_path / profile_folder.name
                
                # 如果目标已存在，先删除
                if target.exists():
                    shutil.rmtree(target)
                
                # 复制整个文件夹
                shutil.copytree(profile_folder, target)
                print(f"  ✅ 复制: {profile_folder.name}")
        
        print(f"\n🎉 所有profile已复制到官方目录!")
        
    except Exception as e:
        print(f"复制到官方目录失败: {e}")
        print(f"请手动复制 {output_path} 到 {official_path}")


def generate_streamdeck_profiles(models_data):
    """生成StreamDeck配置文件夹"""
    if not models_data:
        print("没有模型数据")
        return False
    
    print(f"开始生成StreamDeck配置...")
    
    # 清理输出目录
    output_path = Path(OUTPUT_DIR)
    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir()
    
    # 生成所有模型的profile文件夹
    for model_data in models_data:
        generate_model_profile_folder(model_data)
    
    # 生成Home profile文件夹
    generate_home_profile_folder(models_data)
    
    print(f"\n[OK] All profile folders generated to {OUTPUT_DIR} directory!")
    
    # 复制到官方目录
    copy_to_official_directory()
    
    return True