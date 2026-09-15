"""Qwen Turbo bot for one local WeChat group.

Only a text message that explicitly mentions this account is sent to Qwen.
Historical messages are skipped when the listener starts.
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import json
import os
import re
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque
from pathlib import Path

import psutil

from wechatauto import WeChatDB
from wechatauto.db import Listener
from wechatauto.guia import quick_send


ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "bot_config.json"
SECRET_PATH = ROOT / "填写千问密钥.txt"
RUNTIME_DIR = ROOT / ".bot-data"
STATUS_PATH = RUNTIME_DIR / "status.json"
CLAIMS_PATH = RUNTIME_DIR / "claimed_messages.json"
OUTBOUND_PATH = RUNTIME_DIR / "sent_answer_fingerprints.json"
STATUS_LOCK = threading.Lock()
CLAIMS_LOCK = threading.Lock()


def acquire_instance_mutex():
    """Allow only one bot process, even while the PID file is being created."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    create_mutex = kernel32.CreateMutexW
    create_mutex.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
    create_mutex.restype = ctypes.c_void_p
    handle = create_mutex(None, False, "Local\\WeChatQwenGroupBot_f7b91d2c")
    if not handle or ctypes.get_last_error() == 183:
        if handle:
            kernel32.CloseHandle(ctypes.c_void_p(handle))
        return None
    return handle


def claim_message(group_id: str, message: dict) -> bool:
    """Persist a send claim before touching WeChat, preventing restart duplicates."""
    identity = "%s|%s|%s|%s" % (
        group_id,
        message.get("sender_username") or message.get("sender_id", ""),
        message.get("create_time", ""),
        text_value(message.get("content")),
    )
    key = hashlib.sha256(identity.encode("utf-8", errors="ignore")).hexdigest()
    with CLAIMS_LOCK:
        try:
            claimed = json.loads(CLAIMS_PATH.read_text(encoding="utf-8"))
            if not isinstance(claimed, list):
                claimed = []
        except (OSError, ValueError):
            claimed = []
        if key in claimed:
            return False
        claimed.append(key)
        claimed = claimed[-1000:]
        temp_path = CLAIMS_PATH.with_suffix(".tmp")
        temp_path.write_text(json.dumps(claimed, ensure_ascii=False), encoding="utf-8")
        os.replace(temp_path, CLAIMS_PATH)
        return True


def claim_outbound(group_id: str, answer: str, ttl_seconds: int = 300) -> bool:
    """Suppress the same generated answer in one group for a short safety window."""
    now = int(time.time())
    key = hashlib.sha256((group_id + "|" + answer).encode("utf-8", errors="ignore")).hexdigest()
    with CLAIMS_LOCK:
        try:
            records = json.loads(OUTBOUND_PATH.read_text(encoding="utf-8"))
            if not isinstance(records, dict):
                records = {}
        except (OSError, ValueError):
            records = {}
        records = {k: int(v) for k, v in records.items() if now - int(v) < ttl_seconds}
        if key in records:
            return False
        records[key] = now
        temp_path = OUTBOUND_PATH.with_suffix(".tmp")
        temp_path.write_text(json.dumps(records), encoding="utf-8")
        os.replace(temp_path, OUTBOUND_PATH)
        return True


def update_status(**changes) -> None:
    """Atomically update the dashboard status without storing chat text."""
    RUNTIME_DIR.mkdir(exist_ok=True)
    with STATUS_LOCK:
        try:
            current = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = {}
        current.update(changes)
        current["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        temp_path = STATUS_PATH.with_suffix(".tmp")
        temp_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, STATUS_PATH)


def bump_status(field: str, amount: int = 1, **changes) -> None:
    RUNTIME_DIR.mkdir(exist_ok=True)
    with STATUS_LOCK:
        try:
            current = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = {}
        current[field] = int(current.get(field, 0)) + amount
        current.update(changes)
        current["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        temp_path = STATUS_PATH.with_suffix(".tmp")
        temp_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp_path, STATUS_PATH)


def load_settings() -> dict:
    settings = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if SECRET_PATH.exists():
        for line in SECRET_PATH.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "DASHSCOPE_API_KEY" and value.strip():
                os.environ["DASHSCOPE_API_KEY"] = value.strip()
    return settings


def text_value(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value if isinstance(value, str) else ""


def strip_group_sender_prefix(text: str) -> str:
    return re.sub(r"^(?:wxid_[0-9A-Za-z_-]+|[^:\r\n]+@chatroom):\s*", "", text, count=1)


def mentioned_me(db: WeChatDB, group_id: str, message: dict, self_info: dict) -> tuple[bool, str]:
    content = strip_group_sender_prefix(text_value(message.get("content"))).strip()
    if not content:
        return False, ""

    nickname = str(self_info.get("nick_name") or "")
    # Native WeChat @ mentions are followed by U+2005. Requiring that marker
    # prevents ordinary text that merely types "@昵称" from triggering the bot.
    # Do not reopen the message database here: callbacks run on worker threads,
    # and concurrent cache refreshes can corrupt the temporary SQLite snapshot.
    visible_mentions_me = bool(nickname and ("@" + nickname + "\u2005") in content)
    if not visible_mentions_me:
        return False, ""

    prompt = content
    if nickname:
        prompt = prompt.replace("@" + nickname, "", 1)
    prompt = prompt.lstrip(" \t\u2005,:：，")
    return bool(prompt), prompt


class AllGroupListener(Listener):
    """Discover groups from contacts, sessions and message tables, serially."""

    def __init__(self, db: WeChatDB, callback: callable, group_names: dict[str, str], **kwargs):
        super().__init__(db, **kwargs)
        self._group_callback = callback
        self._group_names = group_names
        self._next_discovery = 0.0

    def discover_groups(self) -> None:
        candidates: dict[str, str] = {}
        readers = (
            lambda: self.db.get_groups(),
            lambda: self.db.get_sessions(limit=500),
            lambda: self.db.list_message_chats(),
        )
        for read in readers:
            try:
                rows = read()
            except Exception:
                continue
            for row in rows:
                username = str(row.get("username") or "")
                if not username.endswith("@chatroom"):
                    continue
                name = str(row.get("name") or "")
                candidates[username] = name or candidates.get(username, "")

        for username, name in candidates.items():
            if name and not name.endswith("@chatroom"):
                self._group_names[username] = name
            if username in self._callbacks:
                continue
            try:
                self.add_listener(username, self._group_callback)
            except Exception:
                # add_listener records the callback before reading the initial
                # watermark. Roll it back so the next discovery can retry.
                self.remove_listener(username, self._group_callback)
        update_status(listening_groups=len(self._callbacks))

    def _poll_once(self) -> None:
        now = time.monotonic()
        if now >= self._next_discovery:
            self._next_discovery = now + 5.0
            self.discover_groups()
        super()._poll_once()


def ask_qwen(settings: dict, api_key: str, history: deque, prompt: str) -> str:
    url = settings["base_url"].rstrip("/") + "/chat/completions"
    messages = [{"role": "system", "content": settings["system_prompt"]}]
    messages.extend(history)
    messages.append({"role": "user", "content": prompt})
    body = json.dumps({
        "model": settings["model"],
        "messages": messages,
        "temperature": float(settings.get("temperature", 0.7)),
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(
            request, timeout=float(settings["request_timeout_seconds"])
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"千问接口返回 HTTP {exc.code}: {detail}") from exc
    answer = payload["choices"][0]["message"]["content"].strip()
    return answer[: int(settings["max_reply_chars"])]


def build_db() -> WeChatDB:
    RUNTIME_DIR.mkdir(exist_ok=True)
    key_dir = RUNTIME_DIR / "keys"
    key_dir.mkdir(exist_ok=True)
    os.environ["WECHATAUTO_KEYS_DIR"] = str(key_dir)
    return WeChatDB(
        workdir=str(RUNTIME_DIR / "db-cache"),
        keys_file=str(RUNTIME_DIR / "db-cache" / "keys.json"),
    )


def check_only(settings: dict) -> int:
    db = build_db()
    all_groups = settings.get("reply_scope") == "all_groups"
    group_id = db.group_name_to_id(settings["group_name"]) if not all_groups else None
    info = db.get_self_info()
    report = {
        "account_ready": bool(info.get("username") and info.get("nick_name")),
        "target_group_found": bool(db.get_groups()) if all_groups else bool(group_id),
        "reply_scope": "all_groups" if all_groups else "selected_group",
        "model": settings["model"],
        "api_key_configured": bool(os.getenv("DASHSCOPE_API_KEY")),
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["account_ready"] and report["target_group_found"] else 1


def run_bot(settings: dict) -> int:
    api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        update_status(running=False, api_status="未配置", last_error="尚未配置千问 API Key")
        print("请先打开‘填写千问密钥.txt’，在等号后粘贴百炼 API Key。")
        return 2

    instance_mutex = acquire_instance_mutex()
    if instance_mutex is None:
        print("机器人已经在运行。")
        return 0

    pid_path = RUNTIME_DIR / "bot.pid"
    if pid_path.exists():
        try:
            old_pid = int(pid_path.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            old_pid = 0
        if old_pid and psutil.pid_exists(old_pid):
            print("机器人已经在运行。")
            return 0
    RUNTIME_DIR.mkdir(exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="ascii")

    db = build_db()
    group_name = settings["group_name"]
    all_groups = settings.get("reply_scope") == "all_groups"
    group_id = None if all_groups else db.group_name_to_id(group_name)
    if not all_groups and not group_id:
        update_status(running=False, last_error=f"没有找到群聊：{group_name}")
        print(f"没有找到群聊：{group_name}")
        return 3
    self_info = db.get_self_info()
    history_items = max(0, int(settings.get("context_rounds", 4))) * 2
    histories: dict[str, deque] = defaultdict(lambda: deque(maxlen=history_items or 1))
    send_lock = threading.Lock()
    group_names: dict[str, str] = {}

    def on_message(message: dict, _listener: Listener) -> None:
        current_group_id = str(message.get("username") or group_id or "")
        if not current_group_id.endswith("@chatroom"):
            return
        bump_status("messages_seen", last_activity="收到一条新群消息")
        if message.get("type") != "文本" or message.get("sender_id") == 2:
            return
        is_mention, prompt = mentioned_me(db, current_group_id, message, self_info)
        if not is_mention:
            return
        bump_status("mentions_handled", last_activity="收到 @，正在调用千问", last_error="")
        try:
            sender = current_group_id + ":" + str(message.get("sender_username") or message.get("sender_id") or "群成员")
            print("收到一条 @ 消息，正在调用千问……", flush=True)
            answer = ask_qwen(settings, api_key, histories[sender], prompt)
            if not claim_message(current_group_id, message):
                update_status(last_activity="已拦截一条重复消息")
                print("已拦截重复消息。", flush=True)
                return
            if not claim_outbound(current_group_id, answer):
                update_status(last_activity="已拦截一条重复回答")
                print("已拦截重复回答。", flush=True)
                return
            update_status(api_status="连接正常", last_activity="千问已生成回答")
            target_group_name = group_names.get(current_group_id) or current_group_id
            with send_lock:
                # WeChat 4.x can write the sent message to its database late.
                # Treat the completed UI send as final; database verification can
                # falsely fail after the message is already visible and cause a retry.
                sent = quick_send(answer, target_group_name, verify=False)
            if not sent.is_success:
                raise RuntimeError("微信回复失败：" + str(sent["message"]))
            if history_items:
                histories[sender].append({"role": "user", "content": prompt})
                histories[sender].append({"role": "assistant", "content": answer})
            bump_status("replies_sent", last_activity="最近一次回复成功", last_error="")
            print("回复成功。", flush=True)
        except Exception as exc:
            bump_status("errors", last_activity="最近一次处理失败", last_error=str(exc)[:300])
            raise

    if all_groups:
        listener = AllGroupListener(
            db,
            on_message,
            group_names,
            interval=1.0,
            watermark_file=str(RUNTIME_DIR / "listener_watermark.json"),
            max_retries=0,
        )
        listener.discover_groups()
    else:
        listener = Listener(
            db,
            interval=1.0,
            watermark_file=str(RUNTIME_DIR / "listener_watermark.json"),
            max_retries=0,
        )
        group_names[group_id] = group_name
        listener.add_listener(group_id, on_message)
    stop_event = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    try:
        update_status(
            running=True,
            pid=os.getpid(),
            started_at=time.strftime("%Y-%m-%d %H:%M:%S"),
            group_name="所有微信群" if all_groups else group_name,
            model=settings["model"],
            reply_mode="仅明确 @ 时回复",
            api_status="已配置，等待调用",
            messages_seen=0,
            mentions_handled=0,
            replies_sent=0,
            errors=0,
            last_activity="监听已启动",
            last_error="",
        )
        listener.start()
        scope_text = "所有微信群" if all_groups else f"群聊“{group_name}”"
        print(f"机器人已启动：监听{scope_text}，只有被 @ 才会调用千问。", flush=True)
        while not stop_event.wait(1.0):
            pass
    finally:
        listener.stop()
        update_status(running=False, pid=0, last_activity="机器人已停止")
        try:
            pid_path.unlink()
        except OSError:
            pass
        ctypes.windll.kernel32.CloseHandle(ctypes.c_void_p(instance_mutex))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--test-api", action="store_true")
    args = parser.parse_args()
    settings = load_settings()
    if args.check:
        return check_only(settings)
    if args.test_api:
        api_key = os.getenv("DASHSCOPE_API_KEY", "").strip()
        if not api_key:
            print("api_ok=false")
            return 2
        ask_qwen(settings, api_key, deque(), "只回复两个字：正常")
        print("api_ok=true")
        return 0
    return run_bot(settings)


if __name__ == "__main__":
    sys.exit(main())
