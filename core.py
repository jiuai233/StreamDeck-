# -*- coding: utf-8 -*-
"""
核心业务逻辑模块
处理模型检测和热键获取的主要业务流程
"""

import asyncio
from typing import List, Dict, Optional

from vts_client import VTSAPI
from utils import find_icon, wait_for_user_input


async def check_models_and_hotkeys(selected_ids: Optional[set] = None, interactive: bool = True) -> Optional[List[Dict]]:
    """检测模型和热键
    selected_ids: 仅处理这些 modelID（None 则处理全部）
    """
    print("开始连接VTube Studio API...")
    
    # 确保模型目录存在
    from utils import find_live2d_root
    live2d_root = find_live2d_root()
    if not live2d_root:
        return None
    
    api = VTSAPI()
    
    try:
        if not await api.auth():
            print("API认证失败")
            return None
        
        # 启动前健康检查
        print("🔍 检查VTS初始状态...")
        if not await api.check_vts_state():
            print("⚠️  警告：检测到VTS可能有错误对话框或异常状态")
            print("💡 建议：请检查VTS界面，关闭任何错误对话框后继续")
            print("⏳ 等待3秒...")
            await asyncio.sleep(3)
        
        models = await api.get_available_models()
        if selected_ids is not None:
            models = [m for m in models if m.get("modelID") in selected_ids]
        print(f"发现 {len(models)} 个模型，开始遍历…")
        print("\n" + "="*50)
        print("💡 重要提示：")
        print("   • 脚本会自动逐个测试加载每个模型")
        print("   • 如果遇到错误，脚本会暂停并提示您处理")
        print("   • 请保持关注VTS界面，及时关闭错误对话框")
        print("   • 处理完错误后按 Enter 键继续")
        print("   • 无法修复的模型会被自动跳过")
        print("="*50 + "\n")
        
        results = []
        failed_models = 0
        
        for idx, model in enumerate(models):
            model_name = model["modelName"]
            model_id = model["modelID"]
            
            print(f"[{idx+1}/{len(models)}] 加载 {model_name} …")
            
            # 每5个模型检查一次VTS整体状态
            if idx % 5 == 0 and idx > 0:
                print(f"  🔍 定期检查VTS整体状态...")
                if not await api.check_vts_state():
                    print("  ⚠️ 检测到VTS状态异常")
                    print("  💡 请检查VTS界面是否有错误对话框需要关闭")
                    if interactive:
                        wait_for_user_input("  ⏸️  请处理VTS状态后")
                    else:
                        print("  ⏭️ 非交互模式：自动跳过等待")
            
            try:
                await api.load_model(model_id)
                
                # 验证模型是否真的加载成功
                info = await asyncio.wait_for(
                    api.current_model_info(), 
                    timeout=5
                )
                hotkeys = await asyncio.wait_for(
                    api.get_hotkeys_in_current_model(), 
                    timeout=5
                )
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
                
            except asyncio.TimeoutError:
                print(f"  ❌ 模型 {model_name} 信息获取超时")
                print("  ⚠️ 可能原因：")
                print("     - VTS有错误对话框需要关闭")
                print("     - 模型文件损坏或过大")
                print("     - VTS程序响应缓慢")
                print("  💡 建议检查VTS界面是否有对话框或错误提示")
                
                if interactive:
                    wait_for_user_input("  ⏸️  请检查VTS状态后")
                else:
                    print("  ⏭️ 非交互模式：自动跳过等待")
                
                failed_models += 1
                # 添加错误模型占位符，避免完全丢失
                from config import DEFAULT_ICON
                results.append({
                    "modelName": f"{model_name} (跳过)",
                    "modelID": model_id,
                    "icon": DEFAULT_ICON,
                    "hotkeys": []
                })
                print("  → 跳过此模型，继续处理下一个\n")
                continue
            except Exception as e:
                error_msg = str(e)
                print(f"  ❌ 处理模型 {model_name} 时出错: {e}")
                
                if "错误对话框" in error_msg or "VTS状态异常" in error_msg:
                    print("  🔍 检测到VTS可能有错误对话框阻塞")
                    print("  💡 请检查VTS界面：")
                    print("     - 查看是否有错误对话框弹出")
                    print("     - 如有对话框请点击确定或关闭")
                    print("     - 确保VTS界面正常响应")
                    
                    wait_for_user_input("  ⏸️  请处理完VTS错误后")
                    
                    # 重新检查VTS状态
                    print("  🔍 重新检查VTS状态...")
                    if await api.check_vts_state():
                        print("  ✅ VTS状态已恢复")
                    else:
                        print("  ⚠️ VTS状态仍异常，将跳过此模型")
                elif "already loading" in error_msg.lower() or "cannot currently change" in error_msg.lower():
                    print("  ⚠️ VTS正在加载其他模型或处理中")
                    print("  💡 请检查VTS界面：")
                    print("     - 查看是否有模型正在加载")
                    print("     - 查看是否有加载失败的提示框")
                    print("     - 等待当前操作完成或关闭错误提示")
                    
                    if interactive:
                        wait_for_user_input("  ⏸️  请等待VTS操作完成或处理错误后")
                    else:
                        print("  ⏭️ 非交互模式：自动跳过等待")
                    
                else:
                    print("  ⚠️ 遇到未知错误")
                    print("  💡 建议检查VTS状态：")
                    print("     - 确认VTS程序正常运行")
                    print("     - 查看是否有任何错误对话框")
                    print("     - 检查模型文件是否损坏")
                    
                    if interactive:
                        wait_for_user_input("  ⏸️  请检查VTS状态后")
                    else:
                        print("  ⏭️ 非交互模式：自动跳过等待")
                
                print("  → 跳过此模型，继续处理下一个\n")
                failed_models += 1
                continue
        
        await api.close()
        
        # 输出统计信息
        successful_models = len(results) - failed_models
        print(f"\n模型处理完成统计:")
        print(f"  ✅ 成功处理: {successful_models} 个模型")
        print(f"  ❌ 跳过失败: {failed_models} 个模型")
        print(f"  📊 总计: {len(models)} 个模型")
        
        return results
        
    except Exception as e:
        print(f"API连接错误: {e}")
        await api.close()
        return None
