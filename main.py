#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StreamDeck VTS Generator - 修正版
基于GitHub项目jiuai233/StreamDeck-的正确实现
"""

import asyncio, json, uuid, os, re, shutil, hashlib, pathlib, sys
from pathlib import Path
from typing import Dict, List, Optional
import websockets

# 检查依赖
try:
    import psutil
except ImportError:
    print("错误：需要安装 psutil")
    print("运行：pip install psutil")
    exit(1)

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
def slot(col, row): return f"{col},{row}"
ROWS_DESC = list(range(ROWS-1, -1, -1))
ALL_SLOTS = [slot(c, r) for r in ROWS_DESC for c in range(COLUMNS)]
PREV_SLOT = slot(0, 0)
NEXT_SLOT = slot(COLUMNS-1, 0)
USABLE = [s for s in ALL_SLOTS if s not in {PREV_SLOT, NEXT_SLOT}]

# ---------- 进程检测功能 ----------
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

# ---------- 图标处理功能 ----------
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

# ---------- VTS API 类 ----------
class VTSAPI:
    def __init__(self, uri):
        self.uri = uri
        self.ws = None
        self.token = None
        self.authed = False

    async def _conn(self):
        self.ws = await websockets.connect(self.uri)
        print(f"✓ 已连接 {self.uri}")

    def _payload(self, msg, data=None):
        p = {"apiName":"VTubeStudioPublicAPI","apiVersion":"1.0",
             "requestID":str(uuid.uuid4()),"messageType":msg,"data":data or {}}
        if self.authed:
            p["data"]["authenticationToken"] = self.token
        return p

    async def _req(self, msg, data=None):
        await self.ws.send(json.dumps(self._payload(msg, data)))
        r = json.loads(await self.ws.recv())
        if r.get("messageType") == "APIError":
            raise RuntimeError(r["data"]["message"])
        return r

    async def auth(self):
        """认证流程"""
        await self._conn()
        try:
            tok = await self._req("AuthenticationTokenRequest",
                                  {"pluginName":PLUGIN_NAME,"pluginDeveloper":PLUGIN_DEVELOPER})
            self.token = tok["data"]["authenticationToken"]
            print("✓ 获取到认证令牌，请在VTube Studio中点击'允许'")
        except RuntimeError as e:
            if "authentication is currently ongoing" in str(e):
                print("⚠ 认证窗口已打开，请在VTube Studio中点击'允许'，然后重新运行脚本")
                raise RuntimeError("请先在VTube Studio中确认认证，然后重新运行脚本")
            else:
                raise
        
        await self.ws.send(json.dumps(self._payload("AuthenticationRequest",
                     {"pluginName":PLUGIN_NAME,"pluginDeveloper":PLUGIN_DEVELOPER,
                      "authenticationToken":self.token})))
        response = await self.ws.recv()
        if not response:
            raise RuntimeError("Auth failed")
        self.authed = True
        print("✓ 认证成功\n")
        return True

    async def get_available_models(self):
        """获取可用模型列表"""
        resp = await self._req("AvailableModelsRequest")
        return resp["data"]["availableModels"]

    async def get_hotkeys_in_current_model(self):
        """获取当前模型热键"""
        resp = await self._req("HotkeysInCurrentModelRequest")
        return resp["data"].get("availableHotkeys", [])

    async def load_model(self, model_id):
        """加载模型"""
        # 添加重试机制
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self._req("ModelLoadRequest", {"modelID": model_id})
                await asyncio.sleep(DELAY_AFTER_LOAD)
                return
            except RuntimeError as e:
                if "Cannot currently change model" in str(e) or "model load cooldown" in str(e):
                    if attempt < max_retries - 1:
                        print(f"  ⚠️ 模型切换失败，2秒后重试 ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(2)
                        continue
                    else:
                        print(f"  ❌ 模型切换失败，跳过此模型: {e}")
                        raise
                else:
                    raise

    async def current_model_info(self):
        return (await self._req("CurrentModelRequest"))["data"]

    async def close(self):
        if self.ws:
            await self.ws.close()

# ---------- UUID管理 ----------
def load_or_generate_uuids():
    """加载或生成UUID映射"""
    uuid_file = pathlib.Path(UUID_FILE)
    if uuid_file.exists():
        try:
            with open(uuid_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # 检查是否是旧格式，如果是则转换为新格式
                if "home" not in data and "models" not in data:
                    # 旧格式转换
                    home_uuid = data.get("Home", str(uuid.uuid4()).upper())
                    models = {k: v for k, v in data.items() if k != "Home"}
                    return {
                        "home": home_uuid,
                        "models": models
                    }
                else:
                    # 新格式直接返回
                    return data
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

# ---------- 工具函数 ----------
def safe_filename(name):
    """安全文件名"""
    return re.sub(r'[\\/:*?"<>| ]+', "_", name)

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

# ---------- 主要检测功能 ----------
async def check_models_and_hotkeys():
    """检测模型和热键"""
    print("开始连接VTube Studio API...")
    
    # 确保模型目录存在
    live2d_root = find_live2d_root()
    if not live2d_root:
        return None
    
    api = VTSAPI(VTS_API_URI)
    
    try:
        if not await api.auth():
            print("API认证失败")
            return None
        
        models = await api.get_available_models()
        print(f"发现 {len(models)} 个模型，开始遍历…")
        
        results = []
        
        for idx, model in enumerate(models):
            model_name = model["modelName"]
            model_id = model["modelID"]
            
            print(f"[{idx+1}/{len(models)}] 加载 {model_name} …")
            
            try:
                await api.load_model(model_id)
                
                info = await api.current_model_info()      # 取 modelFileName
                hotkeys = await api.get_hotkeys_in_current_model()
                mfile = info.get("modelFileName")
                
                print(f"  → 动作 {len(hotkeys)} 个")
                icon = find_icon(mfile, model_name)
                
                results.append({
                    "modelName": model_name,
                    "modelID": model_id,
                    "icon": icon,
                    "hotkeys": [
                        {"hotkeyID": hk.get("hotkeyID"),
                         "name": hk.get("name"),
                         "type": hk.get("type")}
                        for hk in hotkeys]
                })
                
            except Exception as e:
                print(f"  ❌ 处理模型 {model_name} 时出错: {e}")
                print("  → 跳过此模型，继续处理下一个")
                continue
        
        await api.close()
        return results
        
    except Exception as e:
        print(f"API连接错误: {e}")
        await api.close()
        return None

# ---------- StreamDock 配置生成 ----------
def get_official_profiles_dir():
    """获取官方StreamDock profiles目录"""
    user_profile = os.path.expanduser("~")
    return os.path.join(user_profile, "AppData", "Roaming", "HotSpot", "StreamDock", "profiles")

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

# ---------- 主程序 ----------
async def main():
    """主程序"""
    print("=" * 50)
    print("StreamDeck VTS Generator")
    print("=" * 50)
    
    # 检测模型和热键
    models_data = await check_models_and_hotkeys()
    if not models_data:
        print("获取模型数据失败")
        return False
    
    print(f"\n成功获取 {len(models_data)} 个模型的数据")
    
    # 生成StreamDeck配置
    success = generate_streamdeck_profiles(models_data)
    
    if success:
        print("\n" + "=" * 50)
        print("配置生成完成！")
        print("=" * 50)
    else:
        print("配置生成失败")
    
    return success

if __name__ == "__main__":
    try:
        result = asyncio.run(main())
        input("\n按任意键退出...")
    except KeyboardInterrupt:
        print("\n程序被用户中断")
    except Exception as e:
        print(f"\n程序运行出错: {e}")
        input("\n按任意键退出...")