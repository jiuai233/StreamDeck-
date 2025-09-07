# -*- coding: utf-8 -*-
"""
VTS API 客户端模块
处理与VTube Studio的WebSocket连接和API调用
"""

import asyncio
import json
import uuid
import websockets
from config import VTS_API_URI, PLUGIN_NAME, PLUGIN_DEVELOPER, DELAY_AFTER_LOAD


class VTSAPI:
    """VTube Studio API客户端"""
    
    def __init__(self, uri=None):
        self.uri = uri or VTS_API_URI
        self.ws = None
        self.token = None
        self.authed = False

    async def _conn(self):
        """建立WebSocket连接"""
        self.ws = await websockets.connect(self.uri)
        print(f"✓ 已连接 {self.uri}")

    def _payload(self, msg, data=None):
        """构建API请求载荷"""
        p = {
            "apiName": "VTubeStudioPublicAPI",
            "apiVersion": "1.0",
            "requestID": str(uuid.uuid4()),
            "messageType": msg,
            "data": data or {}
        }
        if self.authed:
            p["data"]["authenticationToken"] = self.token
        return p

    async def _req(self, msg, data=None):
        """发送API请求"""
        # 检查连接状态，如果断开则重连
        if not self.ws:
            print("  ⚠️ WebSocket连接断开，尝试重连...")
            await self._conn()
        
        try:
            await self.ws.send(json.dumps(self._payload(msg, data)))
            response = await self.ws.recv()
            r = json.loads(response)
            if r.get("messageType") == "APIError":
                raise RuntimeError(r["data"]["message"])
            return r
        except websockets.exceptions.ConnectionClosed:
            print("  ⚠️ 连接在请求过程中断开，尝试重连...")
            await self._conn()
            # 重试一次
            await self.ws.send(json.dumps(self._payload(msg, data)))
            response = await self.ws.recv()
            r = json.loads(response)
            if r.get("messageType") == "APIError":
                raise RuntimeError(r["data"]["message"])
            return r

    async def auth(self):
        """认证流程"""
        await self._conn()
        try:
            tok = await self._req("AuthenticationTokenRequest",
                                  {"pluginName": PLUGIN_NAME, "pluginDeveloper": PLUGIN_DEVELOPER})
            self.token = tok["data"]["authenticationToken"]
            print("✓ 获取到认证令牌，请在VTube Studio中点击'允许'")
        except RuntimeError as e:
            if "authentication is currently ongoing" in str(e):
                print("⚠ 认证窗口已打开，请在VTube Studio中点击'允许'，然后重新运行脚本")
                raise RuntimeError("请先在VTube Studio中确认认证，然后重新运行脚本")
            else:
                raise
        
        await self.ws.send(json.dumps(self._payload("AuthenticationRequest",
                     {"pluginName": PLUGIN_NAME, "pluginDeveloper": PLUGIN_DEVELOPER,
                      "authenticationToken": self.token})))
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
        # 添加重试机制和超时保护
        max_retries = 3
        timeout_seconds = 8
        
        # 在加载前检查VTS状态
        if not await self.check_vts_state():
            print("  ⚠️ VTS状态异常，跳过此模型")
            raise RuntimeError("VTS状态异常，可能有错误对话框阻塞")
        
        for attempt in range(max_retries):
            try:
                # 添加超时保护
                await asyncio.wait_for(
                    self._req("ModelLoadRequest", {"modelID": model_id}),
                    timeout=timeout_seconds
                )
                
                # 加载后验证状态
                await asyncio.sleep(DELAY_AFTER_LOAD)
                
                # 检查模型是否真的加载成功
                if not await self.force_clear_model_state():
                    if attempt < max_retries - 1:
                        print(f"  ⚠️ 模型加载后状态异常，2秒后重试 ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(3)  # 稍长等待时间让用户手动关闭对话框
                        continue
                    else:
                        raise RuntimeError("模型加载后检测到错误对话框")
                
                return
                
            except asyncio.TimeoutError:
                print(f"  ⚠️ 模型加载超时 ({attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    # 检查是否是对话框阻塞导致的超时
                    if not await self.check_vts_state():
                        print("  ⚠️ 检测到VTS可能被错误对话框阻塞，跳过此模型")
                        raise RuntimeError("VTS被错误对话框阻塞")
                    await asyncio.sleep(3)
                    continue
                else:
                    print(f"  ❌ 模型加载超时，跳过此模型")
                    raise RuntimeError("模型加载超时")
                    
            except RuntimeError as e:
                error_msg = str(e)
                if "Cannot currently change model" in error_msg or "model load cooldown" in error_msg:
                    if attempt < max_retries - 1:
                        print(f"  ⚠️ 模型切换失败，3秒后重试 ({attempt + 1}/{max_retries})")
                        await asyncio.sleep(3)
                        continue
                    else:
                        print(f"  ❌ 模型切换失败，跳过此模型: {e}")
                        raise
                elif "VTS状态异常" in error_msg or "错误对话框" in error_msg:
                    # 如果是对话框相关错误，直接跳过不重试
                    print(f"  ❌ {error_msg}，跳过此模型")
                    raise
                else:
                    raise
                    
            except Exception as e:
                print(f"  ❌ 模型加载出现未知错误: {e}")
                if attempt < max_retries - 1:
                    print(f"  ⚠️ 3秒后重试 ({attempt + 1}/{max_retries})")
                    await asyncio.sleep(3)
                    continue
                else:
                    raise

    async def current_model_info(self):
        """获取当前模型信息"""
        return (await self._req("CurrentModelRequest"))["data"]

    async def check_vts_state(self):
        """检查VTS状态，看是否有错误对话框阻塞"""
        try:
            # 尝试快速ping VTS API
            await asyncio.wait_for(
                self._req("APIStateRequest"), 
                timeout=3
            )
            return True
        except (asyncio.TimeoutError, Exception):
            return False

    async def force_clear_model_state(self):
        """尝试清除可能的错误状态"""
        try:
            # 尝试获取当前状态，如果失败说明可能有对话框阻塞
            current_info = await asyncio.wait_for(
                self.current_model_info(),
                timeout=2
            )
            return True
        except asyncio.TimeoutError:
            print("  ⚠️ 检测到VTS可能有错误对话框阻塞，尝试恢复...")
            return False
        except Exception as e:
            print(f"  ⚠️ VTS状态异常: {e}")
            return False

    async def close(self):
        """关闭连接"""
        if self.ws:
            await self.ws.close()
