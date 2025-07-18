#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dump_models_and_hotkeys_with_icons_CONF.py
------------------------------------------
• 可通过 LIVE2D_ROOT / 环境变量 VTS_LIVE2D_ROOT 设置模型根目录
• 先用 modelFileName；若缺失，再按 modelName 匹配文件夹
• 仍保留调试输出
"""

import asyncio, json, uuid, os, re
from pathlib import Path
from typing import Optional
import websockets

# ---------- 可调参数 ----------
VTS_API_URI       = "ws://localhost:8001"
PLUGIN_NAME       = "StreamDeck VTube Studio"
PLUGIN_DEVELOPER  = "Mirabox"
OUTPUT_JSON       = "models_hotkeys.json"
DELAY_AFTER_LOAD  = 3.0
DEFAULT_ICON      = "default.jpg"      # 脚本同目录放一张占位图

# 模型根目录：优先环境变量，其次常量
LIVE2D_ROOT = Path(
    os.getenv(
        "VTS_LIVE2D_ROOT",
        r"C:\Program Files (x86)\Steam\steamapps\common\VTube Studio\VTube Studio_Data\StreamingAssets\Live2DModels"
    )
)
# --------------------------------


def folder_by_model_name(root: Path, model_name: str) -> Optional[Path]:
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


def pick_icon_from_dir(model_dir: Path, model_name: str) -> str:
    """给定模型文件夹，返回图标路径或 default"""
    exts = {".png", ".jpg", ".jpeg", ".webp"}

    for pattern in ("icon.*", "ico_*.*"):
        hits = list(model_dir.glob(pattern))
        if hits:
            print(f"  ✓ 使用 {hits[0].name}\n")
            return str(hits[0])

    for p in model_dir.iterdir():
        if p.suffix.lower() in exts:
            print(f"  ✓ 使用 {p.name}\n")
            return str(p)

    print("  ✗ 没找到图片 → 用默认图\n")
    return str(Path(DEFAULT_ICON).resolve())


def find_icon(model_file_name: Optional[str], model_name: str) -> str:
    """综合 modelFileName / modelName 返回缩略图路径"""
    # ① modelFileName 直接推算
    if model_file_name:
        direct_dir = LIVE2D_ROOT / Path(model_file_name).parent
        if direct_dir.exists():
            print(f"◇ 模型 [{model_name}] 目录: {direct_dir}  (来自 modelFileName)")
            return pick_icon_from_dir(direct_dir, model_name)

    # ② modelName 匹配文件夹
    guess_dir = folder_by_model_name(LIVE2D_ROOT, model_name)
    if guess_dir:
        print(f"◇ 模型 [{model_name}] 目录: {guess_dir}  (名称匹配)")
        return pick_icon_from_dir(guess_dir, model_name)

    # ③ all failed
    print(f"⚠ 未在 {LIVE2D_ROOT} 找到 [{model_name}] 对应文件夹 → 用默认图\n")
    return str(Path(DEFAULT_ICON).resolve())


class VTSAPI:
    def __init__(self, uri):
        self.uri, self.ws, self.token, self.authed = uri, None, None, False

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

    async def authenticate(self):
        await self._conn()
        tok = await self._req("AuthenticationTokenRequest",
                              {"pluginName":PLUGIN_NAME,"pluginDeveloper":PLUGIN_DEVELOPER})
        self.token = tok["data"]["authenticationToken"]
        await self.ws.send(json.dumps(self._payload("AuthenticationRequest",
                     {"pluginName":PLUGIN_NAME,"pluginDeveloper":PLUGIN_DEVELOPER,
                      "authenticationToken":self.token})))
        if not (await self.ws.recv()):
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
                        print(f"  ⚠️ 模型切换失败，{2}秒后重试 ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(2)
                        continue
                    else:
                        print(f"  ❌ 模型切换失败，跳过此模型: {e}")
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
    print(f"发现 {len(models)} 个模型，开始遍历…")

    out = {"models": []}
    for idx, m in enumerate(models):
        print(f"[{idx+1}/{len(models)}] 加载 {m['modelName']} …")
        try:
            await api.load_model(m["modelID"])
            await asyncio.sleep(DELAY_AFTER_LOAD)

            info     = await api.current_model_info()      # 取 modelFileName
            hotkeys  = await api.current_model_hotkeys()
            mfile    = info.get("modelFileName")

            print(f"  → 动作 {len(hotkeys)} 个")
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
            print(f"  ❌ 处理模型 {m['modelName']} 时出错: {e}")
            print(f"  → 跳过此模型，继续处理下一个")
            continue

    Path(OUTPUT_JSON).write_text(json.dumps(out, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    print(f"\n✓ 完成，写入 {OUTPUT_JSON}")
    await api.close()


if __name__ == "__main__":
    asyncio.run(main())
