#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
StreamDock VTS Generator GUI (Tkinter)
- 连接 VTS，获取模型列表
- 勾选需要的模型，生成配置并复制到官方目录
- 检测到 VTS 弹窗/忙碌时暂停并提示，待确认后继续

说明：为保持打包体积小，仅使用 Tkinter 与现有依赖。
"""

import os
import asyncio
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Dict, Set

from vts_client import VTSAPI
from utils import find_icon
from profile_generator import generate_streamdeck_profiles

# GUI 环境标记，避免控制台 input 阻塞
os.environ["SD_GUI"] = "1"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("StreamDock VTS Generator")
        # 确保底部按钮可见
        self.geometry("900x720")
        self.minsize(820, 660)

        self.models = []
        self.model_vars: Dict[str, tk.BooleanVar] = {}

        self._build_ui()

    def _build_ui(self):
        self._setup_theme()

        root = ttk.Frame(self, padding=(16, 16))
        root.pack(fill=tk.BOTH, expand=True)

        # 标题
        header = ttk.Frame(root)
        header.pack(fill=tk.X, pady=(0, 12))
        ttk.Label(header, text="StreamDock VTS Generator", style="Title.TLabel").pack(side=tk.LEFT)

        # 操作
        actions = ttk.Frame(root)
        actions.pack(fill=tk.X)
        self.btn_fetch = ttk.Button(actions, text="连接并获取模型", style="Accent.TButton", command=self.on_fetch_models)
        self.btn_fetch.pack(side=tk.LEFT)

        # 固定提示
        hint = ttk.Frame(root, style="Hint.TFrame")
        hint.pack(fill=tk.X, pady=(10, 6))
        ttk.Label(
            hint,
            text="提示：如进度卡住，请切到 VTube Studio 点击“允许”，或关闭错误弹窗后返回本窗口。",
            style="Hint.TLabel",
            wraplength=760,
            justify=tk.LEFT,
        ).pack(anchor=tk.W)

        # 全选/全不选
        sel_bar = ttk.Frame(root)
        sel_bar.pack(fill=tk.X, pady=(8, 6))
        ttk.Button(sel_bar, text="全选", style="Soft.TButton", command=self.select_all).pack(side=tk.LEFT)
        ttk.Button(sel_bar, text="全不选", style="Soft.TButton", command=self.select_none).pack(side=tk.LEFT, padx=(8, 0))

        # 模型滚动列表（卡片容器）
        card = ttk.Frame(root, style="Card.TFrame", padding=(10, 10))
        card.pack(fill=tk.BOTH, expand=True)
        self.canvas = tk.Canvas(card, borderwidth=0, height=380, highlightthickness=0, bg="#ffffff")
        self.chk_frame = ttk.Frame(self.canvas, style="Card.TFrame")
        self.scroll_y = ttk.Scrollbar(card, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scroll_y.set)
        self.scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.canvas_frame = self.canvas.create_window((0, 0), window=self.chk_frame, anchor="nw")
        self.chk_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # 进度条 + 生成按钮
        prog_bar = ttk.Frame(root)
        prog_bar.pack(fill=tk.X, pady=(8, 0))
        self.progress = ttk.Progressbar(prog_bar, mode="indeterminate")
        self.progress.pack(fill=tk.X)

        self.btn_generate = ttk.Button(root, text="生成配置（选中）", style="Accent.TButton", command=self.on_generate)
        self.btn_generate.pack(fill=tk.X, pady=(8, 0))
        self.btn_generate.configure(state=tk.DISABLED)

        # 状态栏
        self.status = tk.StringVar(value="准备就绪")
        ttk.Label(root, textvariable=self.status, style="Subtle.TLabel").pack(anchor=tk.W, pady=(6, 0))

    def _setup_theme(self):
        style = ttk.Style()
        try:
            style.theme_use("vista")
        except Exception:
            pass
        # 配色
        colors = {
            "bg": "#f6f8fb",
            "card": "#ffffff",
            "text": "#1f2937",
            "subtle": "#6b7280",
            "primary": "#409eff",
            "primary_soft": "#e8f3ff",
            "primary_hover": "#d6e9ff",
            "primary_press": "#c0ddff",
        }
        self.configure(bg=colors["bg"])
        style.configure("TFrame", background=colors["bg"]) 
        style.configure("Card.TFrame", background=colors["card"], borderwidth=1, relief="solid")
        style.configure("Hint.TFrame", background=colors["primary_soft"]) 
        style.configure("TLabel", font=("Segoe UI", 10), foreground=colors["text"], background=colors["bg"]) 
        style.configure("Subtle.TLabel", font=("Segoe UI", 9), foreground=colors["subtle"], background=colors["bg"]) 
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), foreground=colors["text"], background=colors["bg"]) 
        style.configure("Hint.TLabel", font=("Segoe UI", 9), foreground="#0f172a", background=colors["primary_soft"]) 
        style.configure("TButton", font=("Segoe UI", 10), padding=(14, 8), relief="flat")
        style.configure("Soft.TButton", background=colors["bg"], foreground=colors["text"]) 
        style.configure("Accent.TButton", background=colors["primary_soft"], foreground="#0f172a") 
        style.map("Accent.TButton", background=[("active", colors["primary_hover"]), ("pressed", colors["primary_press"])])
        style.configure("TProgressbar", thickness=8)

    def _on_canvas_configure(self, event):
        # 保持内层 frame 宽度与 canvas 一致
        self.canvas.itemconfig(self.canvas_frame, width=event.width)

    def _set_busy(self, busy: bool):
        self.config(cursor="watch" if busy else "")
        self.btn_fetch.configure(state=tk.DISABLED if busy else tk.NORMAL)
        self.btn_generate.configure(state=tk.DISABLED if busy else tk.NORMAL)
        if busy:
            try:
                self.progress.configure(mode="indeterminate")
                self.progress.start(60)
            except Exception:
                pass
        else:
            try:
                self.progress.stop()
            except Exception:
                pass

    def select_all(self):
        for v in self.model_vars.values():
            v.set(True)
        self.update_generate_button_state()

    def select_none(self):
        for v in self.model_vars.values():
            v.set(False)
        self.update_generate_button_state()

    def on_fetch_models(self):
        def task():
            self._safe_set_status("正在连接 VTS 并获取模型...")
            try:
                # 授权提示（打包后可见）
                self._safe_messagebox("授权提示", "请切换到 VTube Studio 并点击‘允许’，然后返回本窗口继续。", kind="info")
                models = asyncio.run(self._fetch_models())
                self._safe_call(lambda: self._update_model_checks(models))
                self._safe_set_status(f"获取到 {len(models)} 个模型，勾选后点击生成")
                self._safe_call(lambda: self.btn_generate.configure(state=tk.NORMAL if models else tk.DISABLED))
            except Exception as e:
                self._safe_messagebox("获取模型失败", str(e), kind="error")
                self._safe_set_status("获取模型失败")
            finally:
                self._safe_call(lambda: self._set_busy(False))

        self._set_busy(True)
        threading.Thread(target=task, daemon=True).start()

    async def _fetch_models(self):
        api = VTSAPI()
        # 认证：如失败提示并重试一次
        for attempt in range(2):
            try:
                await api.auth()
                break
            except Exception:
                if attempt == 0:
                    self._wait_modal("VTS 可能弹出授权或错误窗口，请处理后点击继续")
                    continue
                else:
                    await api.close()
                    raise

        # 健康检查：如被弹窗阻塞，提示并等待
        if not await api.check_vts_state():
            self._wait_modal("检测到 VTS 可能有弹窗，请处理后点击继续")

        # 获取模型：如失败提示并重试一次
        for attempt in range(2):
            try:
                models = await api.get_available_models()
                await api.close()
                return [{"modelName": m.get("modelName"), "modelID": m.get("modelID")} for m in models]
            except Exception:
                if attempt == 0:
                    self._wait_modal("VTS 可能弹窗或正忙，请处理后点击继续")
                    continue
                else:
                    await api.close()
                    raise

    def on_generate(self):
        selected_ids = {mid for mid, v in self.model_vars.items() if v.get()}
        if not selected_ids:
            messagebox.showwarning("未选择", "请至少选择一个模型后再生成")
            return

        def task():
            try:
                self._safe_set_status("正在获取已选模型的热键与图标...")
                data = asyncio.run(self._collect_selected_models(selected_ids))
                if not data:
                    self._safe_set_status("未获取到任何模型数据")
                    return
                self._safe_set_status("正在生成 StreamDock 配置...")
                ok = generate_streamdeck_profiles(data)
                if ok:
                    self._safe_set_status("配置生成完成，已复制到官方目录")
                    self._safe_messagebox("完成", "配置生成完成！", kind="info")
                else:
                    self._safe_set_status("配置生成失败")
                    self._safe_messagebox("失败", "配置生成失败", kind="error")
            except Exception as e:
                self._safe_set_status("生成过程中出错")
                self._safe_messagebox("出错", str(e), kind="error")
            finally:
                self._safe_call(lambda: self._set_busy(False))

        self._set_busy(True)
        threading.Thread(target=task, daemon=True).start()

    def _update_model_checks(self, models):
        # 清空
        for child in list(self.chk_frame.children.values()):
            child.destroy()
        self.models = models
        self.model_vars.clear()
        for m in models:
            mid = m["modelID"]
            var = tk.BooleanVar(value=True)
            self.model_vars[mid] = var
            cb = ttk.Checkbutton(self.chk_frame, text=m["modelName"], variable=var, command=self.update_generate_button_state)
            cb.pack(anchor=tk.W, padx=4, pady=2)
        self.chk_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.update_generate_button_state()

    def update_generate_button_state(self):
        any_selected = any(v.get() for v in self.model_vars.values())
        self.btn_generate.configure(state=tk.NORMAL if any_selected else tk.DISABLED)

    def _safe_set_status(self, text: str):
        self._safe_call(lambda: self.status.set(text))

    def _safe_call(self, fn):
        try:
            self.after(0, fn)
        except Exception:
            pass

    def _safe_messagebox(self, title: str, msg: str, kind: str = "info"):
        def _show():
            if kind == "error":
                messagebox.showerror(title, msg)
            elif kind == "warning":
                messagebox.showwarning(title, msg)
            else:
                messagebox.showinfo(title, msg)
        self._safe_call(_show)

    # 暂停确认对话
    def _wait_modal(self, message: str):
        evt = threading.Event()

        def show_modal():
            win = tk.Toplevel(self)
            win.title("请处理 VTS 弹窗")
            win.transient(self)
            win.grab_set()
            ttk.Label(win, text=message, wraplength=420).pack(padx=16, pady=(16, 8))
            ttk.Button(win, text="我已处理，继续", style="Accent.TButton",
                       command=lambda: (win.grab_release(), win.destroy(), evt.set())).pack(pady=(0, 16))
            self._center_window(win, 460, 140)

        self._safe_call(show_modal)
        evt.wait()

    def _center_window(self, win, w, h):
        try:
            win.update_idletasks()
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            x = (sw - w) // 2
            y = (sh - h) // 3
            win.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    async def _collect_selected_models(self, selected_ids: Set[str]):
        self._safe_set_status("正在认证 VTS...")
        api = VTSAPI()
        await api.auth()

        models = await api.get_available_models()
        models = [m for m in models if m.get("modelID") in selected_ids]
        total = len(models)
        self._safe_set_status(f"将处理 {total} 个模型...")

        results = []
        failed = 0

        for idx, model in enumerate(models, start=1):
            name = model.get("modelName")
            mid = model.get("modelID")
            self._safe_set_status(f"[{idx}/{total}] 加载 {name} 中...")

            # 尝试直到成功加载
            while True:
                if not await api.check_vts_state():
                    self._wait_modal("检测到 VTS 可能有弹窗，请处理后点击继续")
                    continue
                try:
                    await api.load_model(mid)
                    break
                except Exception as e:
                    self._safe_set_status(f"{name}: 切换失败/正忙 {e}")
                    self._wait_modal("VTS 可能有弹窗或正忙，请在 VTS 处理后点击继续")
                    continue

            # 读取模型信息与热键（失败提示一次后再重试一次）
            try:
                info = await asyncio.wait_for(api.current_model_info(), timeout=5)
                hotkeys = await asyncio.wait_for(api.get_hotkeys_in_current_model(), timeout=5)
            except Exception:
                self._wait_modal("读取信息失败，可能有弹窗，请处理后点击继续再试")
                try:
                    info = await asyncio.wait_for(api.current_model_info(), timeout=5)
                    hotkeys = await asyncio.wait_for(api.get_hotkeys_in_current_model(), timeout=5)
                except Exception:
                    failed += 1
                    continue

            mfile = info.get("modelFileName")
            icon = find_icon(mfile, name)
            self._safe_set_status(f"{name}: 动作 {len(hotkeys)} 个")
            results.append({
                "modelName": name,
                "modelID": mid,
                "icon": icon,
                "hotkeys": [{
                    "hotkeyID": hk.get("hotkeyID"),
                    "name": hk.get("name"),
                    "type": hk.get("type"),
                } for hk in hotkeys],
            })

        await api.close()
        self._safe_set_status(f"完成：成功 {len(results)}，跳过 {failed}")
        return results


if __name__ == "__main__":
    app = App()
    app.mainloop()
