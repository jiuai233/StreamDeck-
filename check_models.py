#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dump_models_and_hotkeys_with_icons_CONF.py
------------------------------------------
• 可通过 LIVE2D_ROOT / 环境变量 VTS_LIVE2D_ROOT 设置模型根目录
• 先用 modelFileName；若缺失，再按 modelName 匹配文件夹
• 仍保留调试输出
"""

import asyncio, json, uuid, os, re, shutil, hashlib
from pathlib import Path
try:
    from typing import Optional
except ImportError:
    # 对于较老的Python版本，定义一个简单的Optional替代
    def Optional(x):
        return x
import websockets

# ---------- 可调参数 ----------
VTS_API_URI       = "ws://localhost:8001"
PLUGIN_NAME       = "StreamDeck VTube Studio"
PLUGIN_DEVELOPER  = "Mirabox"
OUTPUT_JSON       = "models_hotkeys.json"
DELAY_AFTER_LOAD  = 3.0
DEFAULT_ICON      = "default.jpg"      # 脚本同目录放一张占位图
IMAGES_DIR        = Path("Images")     # StreamDeck Images 目录

# 模型根目录：优先环境变量，其次常量
LIVE2D_ROOT = Path(
    os.getenv(
        "VTS_LIVE2D_ROOT",
        r"C:\Program Files (x86)\Steam\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels"
    )
)
# --------------------------------


def folder_by_model_name(root, model_name):
    """
    在 root 下按 model_name 找文件夹：
      - 精准匹配
      - 去掉 '_vts' 后再匹配
      - 不区分大小写
    """
    for p in root.iterdir():
        if not p.is_dir():
            continue
        name_nosuffix = re.sub(r"_vts$", "", p.name, flags=re.I)
        if p.name.lower() == model_name.lower() or name_nosuffix.lower() == model_name.lower():
            return p
    return None


def copy_icon_to_images(icon_path, model_name):
    """复制图标到Images目录并返回新文件名"""
    IMAGES_DIR.mkdir(exist_ok=True)
    
    # 使用模型名和文件内容生成唯一文件名
    icon_file = Path(icon_path)
    if not icon_file.exists():
        return "default.png"
    
    # 生成唯一ID (使用模型名和文件大小的hash)
    content_hash = hashlib.md5(f"{model_name}_{icon_file.stat().st_size}".encode()).hexdigest()[:26].upper()
    new_filename = f"{content_hash}{icon_file.suffix}"
    
    target_path = IMAGES_DIR / new_filename
    
    # 如果目标文件不存在，复制过去
    if not target_path.exists():
        shutil.copy2(icon_file, target_path)
        print("  ✓ 复制图标: {} -> {}".format(icon_file.name, new_filename))
    else:
        print("  ✓ 图标已存在: {}".format(new_filename))
    
    return new_filename

def pick_icon_from_dir(model_dir, model_name):
    """给定模型文件夹，返回复制后的图标文件名"""
    exts = {".png", ".jpg", ".jpeg", ".webp"}

    for pattern in ("icon.*", "ico_*.*"):
        hits = list(model_dir.glob(pattern))
        if hits:
            print("  ✓ 使用 {}".format(hits[0].name))
            return copy_icon_to_images(hits[0], model_name)

    for p in model_dir.iterdir():
        if p.suffix.lower() in exts:
            print("  ✓ 使用 {}".format(p.name))
            return copy_icon_to_images(p, model_name)

    print("  ✗ 没找到图片 → 用默认图")
    return "default.png"


def find_icon(model_file_name, model_name):
    """综合 modelFileName / modelName 返回复制后的图标文件名"""
    # ① modelFileName 直接推算
    if model_file_name:
        direct_dir = LIVE2D_ROOT / Path(model_file_name).parent
        if direct_dir.exists():
            print("◇ 模型 [{}] 目录: {}  (来自 modelFileName)".format(model_name, direct_dir))
            return pick_icon_from_dir(direct_dir, model_name)

    # ② modelName 匹配文件夹
    guess_dir = folder_by_model_name(LIVE2D_ROOT, model_name)
    if guess_dir:
        print("◇ 模型 [{}] 目录: {}  (名称匹配)".format(model_name, guess_dir))
        return pick_icon_from_dir(guess_dir, model_name)

    # ③ all failed
    print("⚠ 未在 {} 找到 [{}] 对应文件夹 → 用默认图\n".format(LIVE2D_ROOT, model_name))
    return "default.png"


class VTSAPI:
    def __init__(self, uri):
        self.uri, self.ws, self.token, self.authed = uri, None, None, False

    async def _conn(self):
        self.ws = await websockets.connect(self.uri)
        print("✓ 已连接 {}".format(self.uri))

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

    async def authenticate(self):
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

    async def available_models(self):
        return (await self._req("AvailableModelsRequest"))["data"]["availableModels"]

    async def load_model(self, mid):
        # 添加重试机制
        max_retries = 3
        for attempt in range(max_retries):
            try:
                await self._req("ModelLoadRequest", {"modelID": mid})
                return
            except RuntimeError as e:
                if "Cannot currently change model" in str(e):
                    if attempt < max_retries - 1:
                        print("  ⚠️ 模型切换失败，{}秒后重试 ({}/{})".format(2, attempt + 1, max_retries))
                        await asyncio.sleep(2)
                        continue
                    else:
                        print("  ❌ 模型切换失败，跳过此模型: {}".format(e))
                        raise
                else:
                    raise

    async def current_model_info(self):
        return (await self._req("CurrentModelRequest"))["data"]

    async def current_model_hotkeys(self):
        return (await self._req("HotkeysInCurrentModelRequest")
                )["data"].get("availableHotkeys", [])

    async def close(self):
        if self.ws: await self.ws.close()


async def main():
    api = VTSAPI(VTS_API_URI)
    await api.authenticate()

    models = await api.available_models()
    print("发现 {} 个模型，开始遍历…".format(len(models)))

    out = {"models": []}
    for idx, m in enumerate(models):
        print("[{}/{}] 加载 {} …".format(idx+1, len(models), m['modelName']))
        try:
            await api.load_model(m["modelID"])
            await asyncio.sleep(DELAY_AFTER_LOAD)

            info     = await api.current_model_info()      # 取 modelFileName
            hotkeys  = await api.current_model_hotkeys()
            mfile    = info.get("modelFileName")

            print("  → 动作 {} 个".format(len(hotkeys)))
            icon     = find_icon(mfile, m["modelName"])

            out["models"].append({
                "modelName": m["modelName"],
                "modelID"  : m["modelID"],
                "icon"     : icon,
                "hotkeys"  : [
                    {"hotkeyID": hk.get("hotkeyID"),
                     "name": hk.get("name"),
                     "type": hk.get("type")}
                    for hk in hotkeys]
            })
        except Exception as e:
            print("  ❌ 处理模型 {} 时出错: {}".format(m['modelName'], e))
            print("  → 跳过此模型，继续处理下一个")
            continue

    Path(OUTPUT_JSON).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    print("\n✓ 完成，写入 {}".format(OUTPUT_JSON))
    await api.close()


if __name__ == "__main__":
    asyncio.run(main())
