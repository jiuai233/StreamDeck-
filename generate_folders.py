#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接生成 Stream Deck 文件夹结构，而不是 ZIP 文件
"""

import json, uuid, pathlib, shutil, hashlib
from typing import Dict, List

# 常量
DEVICE_MODEL = "20GBA9901"
DEVICE_UUID = "293V3"
COLUMNS, ROWS = 5, 3
OUTPUT_DIR = "StreamDeck_Profiles"  # 输出目录
OFFICIAL_PROFILES_DIR = r"C:\Users\jiuai233\AppData\Roaming\HotSpot\StreamDock\profiles"

# UUID 存储文件
UUID_FILE = "profile_uuids.json"

# 图像文件
IMG_PREV = "Images/btn_previousPage.png"
IMG_NEXT = "Images/btn_nextPage.png"
IMG_HOTKEY = "Images/vts_logo.png"
IMG_SWITCH = "Images/vts_logo.png"

# 坐标与容量
def slot(col, row): return f"{col},{row}"
ROWS_DESC = list(range(ROWS-1, -1, -1))
ALL_SLOTS = [slot(c, r) for r in ROWS_DESC for c in range(COLUMNS)]
PREV_SLOT = slot(0, 0)
NEXT_SLOT = slot(COLUMNS-1, 0)
USABLE = [s for s in ALL_SLOTS if s not in {PREV_SLOT, NEXT_SLOT}]

def uid(): return str(uuid.uuid4())

def mk_btn(img, name, uuid_key, settings=None, show_title=True):
    """创建按钮配置"""
    st = {"Image": img}
    if show_title:
        st.update({"Title": name, "TitleAlignment": "bottom", "FontSize": "10"})
    return {
        "ActionID": uid(),
        "Controller": "",
        "Name": name,
        "Settings": settings or {},
        "State": 0,
        "States": [st],
        "UUID": uuid_key
    }

def load_or_generate_uuids():
    """加载或生成UUID映射"""
    uuid_file = pathlib.Path(UUID_FILE)
    if uuid_file.exists():
        try:
            with open(uuid_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    
    # 生成新的UUID映射
    uuids = {
        "home": str(uuid.uuid4()).upper(),
        "models": {}
    }
    
    # 保存UUID映射
    with open(uuid_file, 'w', encoding='utf-8') as f:
        json.dump(uuids, f, indent=2, ensure_ascii=False)
    
    return uuids

def get_home_uuid():
    """获取Home UUID"""
    uuids = load_or_generate_uuids()
    return uuids["home"]

def get_model_uuid(model_name):
    """获取模型UUID"""
    uuids = load_or_generate_uuids()
    if model_name not in uuids["models"]:
        uuids["models"][model_name] = str(uuid.uuid4()).upper()
        # 保存更新的映射
        with open(UUID_FILE, 'w', encoding='utf-8') as f:
            json.dump(uuids, f, indent=2, ensure_ascii=False)
    return uuids["models"][model_name]

def safe_filename(name):
    """安全文件名"""
    import re
    return re.sub(r'[\\/:*?"<>| ]+', "_", name)

def generate_model_profile_folder(model_data):
    """生成单个模型的 profile 文件夹"""
    model_name = model_data["modelName"]
    safe_name = safe_filename(model_name)
    
    print(f"\n=== 生成 {model_name} profile 文件夹 ===")
    
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
    
    # 动态分页
    def get_page_capacity(page_idx, total_pages):
        if total_pages == 1:
            return 14
        elif page_idx == 0:
            return 14
        elif page_idx == total_pages - 1:
            return 14
        else:
            return 13
    
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
        
        # 页面动作
        acts = {}
        
        # 导航按钮
        if page_idx > 0:
            acts[PREV_SLOT] = mk_btn(IMG_PREV, "上一页", "com.hotspot.streamdock.page.previous", show_title=False)
        if page_idx < total_pages - 1:
            acts[NEXT_SLOT] = mk_btn(IMG_NEXT, "下一页", "com.hotspot.streamdock.page.next", show_title=False)
        
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
            acts[switch_slot] = mk_btn(
                IMG_SWITCH, "切换模型",
                "com.mirabox.streamdock.VtubeStudio.action1",
                {
                    "ip": "127.0.0.1", "port": "8001",
                    "selectModelID": model_data["modelID"],
                    "showTitle": True
                })
            
            # 返回Home按钮
            home_slot = "0,2"
            acts[home_slot] = mk_btn(
                IMG_SWITCH, "返回Home",
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
                acts[sl] = mk_btn(
                    IMG_HOTKEY, hk["name"] or hk["type"],
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
        
        print(f"  · 页面 {page_idx+1}: {len(acts)} 个动作")
    
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
    
    print(f"✅ 生成完成: {profile_folder}")
    return profile_folder

def generate_home_profile_folder(model_names):
    """生成Home profile文件夹"""
    print(f"\n=== 生成 Home profile 文件夹 ===")
    
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
    
    # 生成Home页面
    home_page_uuid = str(uuid.uuid4()).upper()
    home_page_folder = profiles_dir / f"{home_page_uuid}.sdProfile"
    home_page_folder.mkdir(parents=True, exist_ok=True)
    
    # Home页面动作
    home_acts = {}
    available_slots = [s for s in ALL_SLOTS if s not in {PREV_SLOT, NEXT_SLOT}]
    
    # 为每个模型创建跳转按钮
    button_count = 0
    for model_name in model_names:
        if button_count >= len(available_slots):
            break
        
        slot_pos = available_slots[button_count]
        model_uuid = get_model_uuid(model_name)
        home_acts[slot_pos] = mk_btn(
            IMG_SWITCH, model_name,
            "com.hotspot.streamdock.profile.rotate",
            {
                "DeviceUUID": "",
                "ProfileUUID": model_uuid
            })
        button_count += 1
        print(f"  添加模型按钮: {model_name} -> {model_uuid}")
    
    # 写Home页面manifest
    home_page_manifest = {
        "DeviceModel": DEVICE_MODEL,
        "DeviceUUID": DEVICE_UUID,
        "Name": "Home",
        "Version": "1.0",
        "Actions": home_acts
    }
    
    with open(home_page_folder / "manifest.json", 'w', encoding='utf-8') as f:
        json.dump(home_page_manifest, f, indent=2, ensure_ascii=False)
    
    # 写Home根manifest
    home_root_manifest = {
        "DeviceModel": DEVICE_MODEL,
        "DeviceUUID": DEVICE_UUID,
        "Name": "Home",
        "Version": "1.0",
        "Actions": {},
        "Pages": {
            "Current": f"{home_page_uuid}.sdProfile",
            "Pages": [f"{home_page_uuid}.sdProfile"]
        },
        "ProfileUUID": home_uuid
    }
    
    with open(home_folder / "manifest.json", 'w', encoding='utf-8') as f:
        json.dump(home_root_manifest, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 生成完成: {home_folder}")
    print(f"  包含 {len(home_acts)} 个模型跳转按钮")
    return home_folder

def copy_to_official_directory():
    """复制到官方目录"""
    output_path = pathlib.Path(OUTPUT_DIR)
    official_path = pathlib.Path(OFFICIAL_PROFILES_DIR)
    
    if not output_path.exists():
        print("❌ 输出目录不存在，请先生成profile文件夹")
        return
    
    if not official_path.exists():
        print(f"❌ 官方目录不存在: {official_path}")
        return
    
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

def main():
    print("Stream Deck 文件夹生成器")
    print("=" * 50)
    
    # 创建输出目录
    output_dir = pathlib.Path(OUTPUT_DIR)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 读取模型数据
    try:
        with open("models_hotkeys.json", 'r', encoding='utf-8') as f:
            models_data = json.load(f)["models"]
        model_names = [m["modelName"] for m in models_data]
        print(f"找到 {len(model_names)} 个模型")
    except Exception as e:
        print(f"读取模型数据失败: {e}")
        return
    
    # 生成所有模型的profile文件夹
    for model_data in models_data:
        generate_model_profile_folder(model_data)
    
    # 生成Home profile文件夹
    generate_home_profile_folder(model_names)
    
    print(f"\n🎉 所有profile文件夹已生成到 {OUTPUT_DIR} 目录!")
    
    # 询问是否复制到官方目录
    choice = input("\n是否复制到官方 Stream Deck 目录? (y/n): ").strip().lower()
    if choice == 'y':
        copy_to_official_directory()
    else:
        print(f"\n请手动复制 {OUTPUT_DIR} 中的文件夹到:")
        print(f"  {OFFICIAL_PROFILES_DIR}")

if __name__ == "__main__":
    main()