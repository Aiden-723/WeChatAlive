"""Modern multi-page dashboard for the local WeChat AI bot."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import customtkinter as ctk
import psutil
from tkinter import messagebox


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "bot_config.json"
SECRET_PATH = ROOT / "填写API密钥.txt"
RUNTIME_DIR = ROOT / ".bot-data"
STATUS_PATH = RUNTIME_DIR / "status.json"
PID_PATH = RUNTIME_DIR / "bot.pid"
BOT_PATH = ROOT / "wechat_ai_bot.py"

BG, SIDEBAR, CARD = "#0B1220", "#0F172A", "#151F32"
BORDER, TEXT, MUTED = "#26354F", "#F3F7FC", "#8EA1B9"
GREEN, GREEN_HOVER = "#07C160", "#06A953"
BLUE, RED, AMBER, PURPLE = "#4F8CFF", "#FF6376", "#F5B942", "#B18CFF"


def read_json(path: Path, default: dict) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(default)


def current_pid() -> int:
    try:
        pid = int(PID_PATH.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        return 0
    return pid if psutil.pid_exists(pid) else 0


class Dashboard(ctk.CTk):
    def __init__(self):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=BG)
        self.title("微信 AI 机器人管理")
        self.geometry("1080x760")
        self.minsize(940, 680)
        self.config_data = read_json(CONFIG_PATH, {})
        self.model_var = ctk.StringVar(value=self.config_data.get("model", ""))
        self.base_url_var = ctk.StringVar(value=self.config_data.get("base_url", ""))
        self.temperature_var = ctk.DoubleVar(value=float(self.config_data.get("temperature", 0.7)))
        self.context_var = ctk.IntVar(value=int(self.config_data.get("context_rounds", 4)))
        self.max_chars_var = ctk.StringVar(value=str(self.config_data.get("max_reply_chars", 1500)))
        self.group_var = ctk.StringVar(value=self.config_data.get("group_name", "示例群聊"))
        self.scope_var = ctk.StringVar(value=(
            "所有微信群" if self.config_data.get("reply_scope") == "all_groups" else "指定群聊"))
        self.key_var = ctk.StringVar()
        self.notice_var = ctk.StringVar(value="设置已就绪")
        self.pages, self.nav_buttons, self.stat_values = {}, {}, {}
        self._build_shell()
        self.show_page("overview")
        self.after(250, self.refresh_status)

    def _build_shell(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self._build_sidebar()
        self.page_host = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.page_host.grid(row=0, column=1, sticky="nsew")
        self.page_host.grid_rowconfigure(0, weight=1)
        self.page_host.grid_columnconfigure(0, weight=1)
        self.pages["overview"] = self._overview_page()
        self.pages["model"] = self._model_page()
        self.pages["identity"] = self._identity_page()
        self.pages["connection"] = self._connection_page()
        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

    def _build_sidebar(self):
        side = ctk.CTkFrame(self, width=218, corner_radius=0, fg_color=SIDEBAR)
        side.grid(row=0, column=0, sticky="nsew")
        side.grid_propagate(False)
        side.grid_rowconfigure(8, weight=1)
        logo = ctk.CTkFrame(side, fg_color="transparent")
        logo.grid(row=0, column=0, sticky="ew", padx=20, pady=(28, 28))
        ctk.CTkLabel(logo, text="AI", width=46, height=46, corner_radius=14,
                     fg_color=GREEN, text_color="#04170C",
                     font=("Arial", 17, "bold")).pack(side="left")
        names = ctk.CTkFrame(logo, fg_color="transparent")
        names.pack(side="left", padx=(11, 0))
        ctk.CTkLabel(names, text="微信机器人", text_color=TEXT,
                     font=("Microsoft YaHei UI", 15, "bold")).pack(anchor="w")
        ctk.CTkLabel(names, text="LOCAL AI", text_color=GREEN,
                     font=("Arial", 9, "bold")).pack(anchor="w")

        items = (("overview", "◉", "运行概览"), ("model", "✦", "模型设置"),
                 ("identity", "◎", "身份设定"), ("connection", "⌁", "连接信息"))
        for row, (key, icon, label) in enumerate(items, start=1):
            button = ctk.CTkButton(
                side, text=f"  {icon}   {label}", anchor="w", height=44,
                corner_radius=11, fg_color="transparent", hover_color="#19283E",
                text_color=MUTED, font=("Microsoft YaHei UI", 12),
                command=lambda name=key: self.show_page(name))
            button.grid(row=row, column=0, sticky="ew", padx=12, pady=3)
            self.nav_buttons[key] = button

        privacy = ctk.CTkFrame(side, fg_color="#13243A", corner_radius=14,
                               border_width=1, border_color="#203A58")
        privacy.grid(row=9, column=0, sticky="sew", padx=14, pady=18)
        ctk.CTkLabel(privacy, text="隐私模式", text_color=BLUE,
                     font=("Microsoft YaHei UI", 11, "bold")).pack(anchor="w", padx=13, pady=(12, 3))
        ctk.CTkLabel(privacy, text="只把真正的 @ 消息\n发送给所选模型",
                     text_color=MUTED, justify="left",
                     font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=13, pady=(0, 12))

    def show_page(self, name):
        self.pages[name].tkraise()
        for key, button in self.nav_buttons.items():
            active = key == name
            button.configure(fg_color="#173229" if active else "transparent",
                             text_color=TEXT if active else MUTED,
                             font=("Microsoft YaHei UI", 12, "bold" if active else "normal"))

    def _page(self, title, subtitle):
        page = ctk.CTkFrame(self.page_host, fg_color=BG, corner_radius=0)
        page.grid_columnconfigure(0, weight=1)
        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=30, pady=(28, 20))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text=title, text_color=TEXT,
                     font=("Microsoft YaHei UI", 25, "bold")).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(head, text=subtitle, text_color=MUTED,
                     font=("Microsoft YaHei UI", 11)).grid(row=1, column=0, sticky="w", pady=(4, 0))
        return page, head

    def _status_badge(self, head):
        self.status_pill = ctk.CTkLabel(head, text="  ● 检查中  ", corner_radius=14,
                                       fg_color="#273449", text_color=MUTED,
                                       font=("Microsoft YaHei UI", 12, "bold"), height=30)
        self.status_pill.grid(row=0, column=1, rowspan=2, sticky="e")

    def _overview_page(self):
        page, head = self._page("运行概览", "实时查看机器人、AI 模型与群聊处理状态")
        self._status_badge(head)
        hero = self._card(page)
        hero.grid(row=1, column=0, sticky="ew", padx=30)
        hero.grid_columnconfigure(0, weight=1)
        self.hero_title = ctk.CTkLabel(hero, text=self.group_var.get(), text_color=TEXT,
                                       font=("Microsoft YaHei UI", 19, "bold"))
        self.hero_title.grid(row=0, column=0, sticky="w", padx=20, pady=(18, 2))
        self.hero_subtitle = ctk.CTkLabel(hero, text="仅原生 @ 触发  ·  未配置模型",
                                          text_color=MUTED, font=("Microsoft YaHei UI", 11))
        self.hero_subtitle.grid(row=1, column=0, sticky="w", padx=20, pady=(0, 18))
        controls = ctk.CTkFrame(hero, fg_color="transparent")
        controls.grid(row=0, column=1, rowspan=2, padx=18)
        self._action_button(controls, "启动", self.start_bot, GREEN, GREEN_HOVER, "#04170C").pack(side="left", padx=4)
        self._action_button(controls, "重启", self.restart_bot, "#26364F", "#334968").pack(side="left", padx=4)
        self._action_button(controls, "停止", self.stop_bot, "#3A2230", "#542B3C", "#FF9CAB").pack(side="left", padx=4)

        stats = ctk.CTkFrame(page, fg_color="transparent")
        stats.grid(row=2, column=0, sticky="ew", padx=24, pady=16)
        for col in range(4):
            stats.grid_columnconfigure(col, weight=1)
        for col, (title, key, color, hint) in enumerate((
            ("监听消息", "messages_seen", BLUE, "本次运行"),
            ("收到 @", "mentions_handled", GREEN, "有效触发"),
            ("成功回复", "replies_sent", PURPLE, "已送达"),
            ("错误", "errors", RED, "需要关注"))):
            card = self._card(stats, 15)
            card.grid(row=0, column=col, sticky="ew", padx=6)
            ctk.CTkLabel(card, text=title, text_color=MUTED,
                         font=("Microsoft YaHei UI", 10)).pack(anchor="w", padx=15, pady=(13, 0))
            value = ctk.CTkLabel(card, text="0", text_color=color, font=("Arial", 28, "bold"))
            value.pack(anchor="w", padx=15, pady=(2, 0))
            ctk.CTkLabel(card, text=hint, text_color="#61738D",
                         font=("Microsoft YaHei UI", 9)).pack(anchor="w", padx=15, pady=(0, 12))
            self.stat_values[key] = value

        detail = self._card(page)
        detail.grid(row=3, column=0, sticky="ew", padx=30)
        detail.grid_columnconfigure(1, weight=1)
        detail.grid_columnconfigure(3, weight=1)
        self.detail_labels = {}
        for idx, (label, key) in enumerate((
            ("API 状态", "api_status"), ("启动时间", "started_at"),
            ("最近活动", "last_activity"), ("最近错误", "last_error"))):
            row, col = divmod(idx, 2)
            ctk.CTkLabel(detail, text=label, text_color=MUTED,
                         font=("Microsoft YaHei UI", 10)).grid(row=row, column=col * 2, sticky="w", padx=(18, 8), pady=13)
            value = ctk.CTkLabel(detail, text="-", text_color=TEXT,
                                 font=("Microsoft YaHei UI", 10), anchor="w")
            value.grid(row=row, column=col * 2 + 1, sticky="ew", padx=(0, 18), pady=13)
            self.detail_labels[key] = value
        return page

    def _model_page(self):
        page, head = self._page("模型设置", "填写模型 ID，并调整回答风格和短期记忆")
        form = self._card(page)
        form.grid(row=1, column=0, sticky="new", padx=30)
        form.grid_columnconfigure(1, weight=1)
        self._form_title(form, "模型参数", "支持任意 OpenAI 兼容模型 ID")
        self._row_label(form, 1, "模型")
        ctk.CTkEntry(form, textvariable=self.model_var, height=40,
                     placeholder_text="例如：qwen3.5-flash / gpt-4.1-mini",
                     fg_color="#0E1727", border_color=BORDER).grid(
                         row=1, column=1, sticky="ew", padx=(12, 24), pady=9)

        self._row_label(form, 2, "创造性")
        temp_line = ctk.CTkFrame(form, fg_color="transparent")
        temp_line.grid(row=2, column=1, sticky="ew", padx=(12, 24), pady=9)
        temp_line.grid_columnconfigure(0, weight=1)
        self.temp_value = ctk.CTkLabel(temp_line, text=f"{self.temperature_var.get():.1f}", text_color=GREEN)
        ctk.CTkSlider(temp_line, from_=0, to=1.9, number_of_steps=19,
                      variable=self.temperature_var, button_color=GREEN,
                      progress_color=GREEN, command=lambda v: self.temp_value.configure(text=f"{v:.1f}")).grid(row=0, column=0, sticky="ew")
        self.temp_value.grid(row=0, column=1, padx=(12, 0))

        self._row_label(form, 3, "记忆轮数")
        ctx_line = ctk.CTkFrame(form, fg_color="transparent")
        ctx_line.grid(row=3, column=1, sticky="ew", padx=(12, 24), pady=9)
        ctx_line.grid_columnconfigure(0, weight=1)
        self.context_value = ctk.CTkLabel(ctx_line, text=str(self.context_var.get()), text_color=BLUE)
        ctk.CTkSlider(ctx_line, from_=0, to=20, number_of_steps=20,
                      variable=self.context_var, button_color=BLUE,
                      progress_color=BLUE, command=lambda v: self.context_value.configure(text=str(round(v)))).grid(row=0, column=0, sticky="ew")
        self.context_value.grid(row=0, column=1, padx=(12, 0))

        self._row_label(form, 4, "最长回复")
        ctk.CTkEntry(form, textvariable=self.max_chars_var, height=40,
                     fg_color="#0E1727", border_color=BORDER,
                     placeholder_text="100 – 4000").grid(row=4, column=1, sticky="ew", padx=(12, 24), pady=9)
        actions = ctk.CTkFrame(form, fg_color="transparent")
        actions.grid(row=5, column=1, sticky="e", padx=24, pady=(16, 24))
        self._action_button(actions, "保存", self.save_settings, "#26364F", "#334968").pack(side="left", padx=5)
        self._action_button(actions, "保存并重启", self.save_and_restart, GREEN, GREEN_HOVER, "#04170C", 112).pack(side="left", padx=5)
        return page

    def _identity_page(self):
        page, head = self._page("身份设定", "自定义机器人的角色、语气、知识边界和回答规则")
        card = self._card(page)
        card.grid(row=1, column=0, sticky="nsew", padx=30)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(2, weight=1)
        self._form_title(card, "系统身份提示词", "你可以直接用自然语言描述它应该成为谁")
        presets = ctk.CTkFrame(card, fg_color="transparent")
        presets.grid(row=1, column=0, columnspan=2, sticky="w", padx=22, pady=(2, 8))
        for name, prompt in (
            ("通用助手", "你是微信群里的AI助手。请用简洁、友好、准确的中文回答；不知道时坦诚说明，不要编造。"),
            ("幽默群友", "你是群里的幽默AI群友，回答自然、有趣但不过度玩梗。保持礼貌，不编造事实，重要问题要认真回答。"),
            ("技术顾问", "你是资深技术顾问。回答应准确、结构清晰、优先给出可执行方案；信息不足时先说明假设。")):
            ctk.CTkButton(presets, text=name, width=92, height=32, corner_radius=9,
                          fg_color="#26364F", hover_color="#334968",
                          command=lambda p=prompt: self.set_prompt(p)).pack(side="left", padx=(0, 8))
        self.prompt_text = ctk.CTkTextbox(card, height=390, corner_radius=12,
                                          fg_color="#0E1727", border_width=1,
                                          border_color=BORDER, text_color=TEXT,
                                          font=("Microsoft YaHei UI", 12), wrap="word")
        self.prompt_text.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=22, pady=(0, 14))
        self.prompt_text.insert("1.0", self.config_data.get("system_prompt", ""))
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=3, column=0, columnspan=2, sticky="e", padx=22, pady=(0, 20))
        self._action_button(actions, "保存身份", self.save_settings, "#26364F", "#334968", width=100).pack(side="left", padx=5)
        self._action_button(actions, "保存并重启", self.save_and_restart, GREEN, GREEN_HOVER, "#04170C", 112).pack(side="left", padx=5)
        return page

    def _connection_page(self):
        page, head = self._page("连接信息", "管理监听群聊、模型接口、API Key 与连接测试")
        card = self._card(page)
        card.grid(row=1, column=0, sticky="new", padx=30)
        card.grid_columnconfigure(1, weight=1)
        self._form_title(card, "微信与模型", "API Key 只保存在本机，不会显示在界面中")
        self._row_label(card, 1, "回复范围")
        ctk.CTkOptionMenu(card, variable=self.scope_var,
                          values=["所有微信群", "指定群聊"], height=40,
                          fg_color="#26364F", button_color="#314663",
                          button_hover_color="#3B5576").grid(row=1, column=1, sticky="ew", padx=(12, 24), pady=9)
        self._row_label(card, 2, "指定群名")
        ctk.CTkEntry(card, textvariable=self.group_var, height=40,
                     placeholder_text="仅在‘指定群聊’模式下使用",
                     fg_color="#0E1727", border_color=BORDER).grid(row=2, column=1, sticky="ew", padx=(12, 24), pady=9)
        self._row_label(card, 3, "模型接口")
        ctk.CTkEntry(card, textvariable=self.base_url_var, height=40,
                     placeholder_text="例如：https://.../v1",
                     fg_color="#0E1727", border_color=BORDER).grid(
                         row=3, column=1, sticky="ew", padx=(12, 24), pady=9)
        self._row_label(card, 4, "API Key")
        ctk.CTkEntry(card, textvariable=self.key_var, show="●", height=40,
                     placeholder_text="已配置；留空则不修改", fg_color="#0E1727",
                     border_color=BORDER).grid(row=4, column=1, sticky="ew", padx=(12, 24), pady=9)
        self.connection_status = ctk.CTkLabel(card, text="连接状态：等待检测",
                                              text_color=MUTED, anchor="w")
        self.connection_status.grid(row=5, column=1, sticky="ew", padx=(12, 24), pady=9)
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.grid(row=6, column=1, sticky="e", padx=24, pady=(14, 24))
        self._action_button(actions, "测试 API", self.test_api, "#26364F", "#334968", width=100).pack(side="left", padx=5)
        self._action_button(actions, "保存并重启", self.save_and_restart, GREEN, GREEN_HOVER, "#04170C", 112).pack(side="left", padx=5)

        note = ctk.CTkFrame(page, fg_color="#102033", corner_radius=14,
                            border_width=1, border_color="#1E3A56")
        note.grid(row=2, column=0, sticky="ew", padx=30, pady=16)
        ctk.CTkLabel(note, text="最小化与运行说明", text_color=BLUE,
                     font=("Microsoft YaHei UI", 12, "bold")).pack(anchor="w", padx=18, pady=(15, 4))
        ctk.CTkLabel(note, justify="left", text_color=MUTED,
                     text="• 最小化到任务栏：可以继续监听，回复时自动恢复微信\n"
                          "• 关闭到托盘：可能无法找到发送窗口，不建议\n"
                          "• Windows 锁屏：无法操作微信发送消息\n"
                          "• 回复时微信会短暂切到前台，这是当前自动化方案的限制").pack(anchor="w", padx=18, pady=(0, 15))
        return page

    def _card(self, parent, radius=18):
        return ctk.CTkFrame(parent, fg_color=CARD, corner_radius=radius,
                            border_width=1, border_color=BORDER)

    def _form_title(self, parent, title, subtitle):
        ctk.CTkLabel(parent, text=title, text_color=TEXT,
                     font=("Microsoft YaHei UI", 17, "bold")).grid(row=0, column=0, sticky="w", padx=22, pady=(20, 3))
        ctk.CTkLabel(parent, text=subtitle, text_color=MUTED,
                     font=("Microsoft YaHei UI", 10)).grid(row=0, column=1, sticky="e", padx=24, pady=(20, 3))

    def _row_label(self, parent, row, text):
        ctk.CTkLabel(parent, text=text, text_color=MUTED, width=90, anchor="w",
                     font=("Microsoft YaHei UI", 11)).grid(row=row, column=0, sticky="w", padx=(22, 0), pady=9)

    def _action_button(self, parent, text, command, color, hover, text_color=TEXT, width=86):
        return ctk.CTkButton(parent, text=text, command=command, width=width,
                             height=38, corner_radius=10, fg_color=color,
                             hover_color=hover, text_color=text_color,
                             font=("Microsoft YaHei UI", 11, "bold"))

    def set_prompt(self, prompt):
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", prompt)

    def refresh_status(self):
        data = read_json(STATUS_PATH, {})
        running = bool(current_pid())
        self.status_pill.configure(text="  ● 正在运行  " if running else "  ● 已停止  ",
                                   fg_color="#123B2B" if running else "#3A2230",
                                   text_color=GREEN if running else "#FF9CAB")
        for key, label in self.stat_values.items():
            label.configure(text=str(data.get(key, 0)))
        self.hero_title.configure(text=str(data.get("group_name", self.group_var.get())))
        model_text = data.get("model") or self.model_var.get() or "未配置模型"
        self.hero_subtitle.configure(text=f"仅原生 @ 触发  ·  {model_text}")
        for key, label in self.detail_labels.items():
            label.configure(text=str(data.get(key) or "-"))
        api_status = str(data.get("api_status") or "等待检测")
        self.connection_status.configure(text="连接状态：" + api_status,
                                         text_color=GREEN if "正常" in api_status else MUTED)
        self.after(1000, self.refresh_status)

    def _validated_config(self):
        temperature = round(float(self.temperature_var.get()), 1)
        context_rounds = int(round(self.context_var.get()))
        max_chars = int(self.max_chars_var.get())
        if not 0 <= temperature < 2 or not 0 <= context_rounds <= 20 or not 100 <= max_chars <= 4000:
            raise ValueError
        return temperature, context_rounds, max_chars

    def save_settings(self):
        try:
            temperature, context_rounds, max_chars = self._validated_config()
        except ValueError:
            messagebox.showerror("设置有误", "创造性范围 0–1.9，记忆轮数 0–20，回复字数 100–4000。")
            return False
        data = read_json(CONFIG_PATH, {})
        data.update(model=self.model_var.get().strip(),
                    base_url=self.base_url_var.get().strip(),
                    group_name=self.group_var.get().strip() or "示例群聊",
                    reply_scope="all_groups" if self.scope_var.get() == "所有微信群" else "selected_group",
                    temperature=temperature, context_rounds=context_rounds,
                    max_reply_chars=max_chars,
                    system_prompt=self.prompt_text.get("1.0", "end").strip())
        temp = CONFIG_PATH.with_suffix(".tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, CONFIG_PATH)
        self.config_data = data
        new_key = self.key_var.get().strip()
        if new_key:
            SECRET_PATH.write_text("API_KEY=" + new_key + "\n", encoding="utf-8")
            self.key_var.set("")
        self.notice_var.set("设置已保存")
        return True

    def save_and_restart(self):
        if self.save_settings():
            self.restart_bot()

    def start_bot(self):
        if current_pid():
            self.notice_var.set("机器人已经在运行")
            return
        RUNTIME_DIR.mkdir(exist_ok=True)
        out = open(RUNTIME_DIR / "bot.log", "a", encoding="utf-8")
        err = open(RUNTIME_DIR / "bot-error.log", "a", encoding="utf-8")
        subprocess.Popen([sys.executable, "-u", str(BOT_PATH)], cwd=ROOT,
                         stdout=out, stderr=err,
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.notice_var.set("正在启动……")

    def stop_bot(self):
        pid = current_pid()
        if not pid:
            self.notice_var.set("机器人已经停止")
            return
        try:
            process = psutil.Process(pid)
            process.terminate()
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()
        except psutil.Error:
            pass
        try:
            PID_PATH.unlink()
        except OSError:
            pass
        self.notice_var.set("已停止")

    def restart_bot(self):
        self.stop_bot()
        self.notice_var.set("正在重启……")
        self.after(850, self.start_bot)

    def test_api(self):
        self.notice_var.set("正在测试模型 API……")
        self.connection_status.configure(text="连接状态：正在测试……", text_color=AMBER)

        def worker():
            result = subprocess.run([sys.executable, str(BOT_PATH), "--test-api"],
                                    cwd=ROOT, capture_output=True, text=True,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            def finish():
                ok = result.returncode == 0
                text = "连接状态：模型连接正常" if ok else "连接状态：连接失败，请检查接口、模型和 API Key"
                self.connection_status.configure(text=text, text_color=GREEN if ok else RED)
                self.notice_var.set("模型连接正常" if ok else "模型连接失败")
            self.after(0, finish)
        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    Dashboard().mainloop()
