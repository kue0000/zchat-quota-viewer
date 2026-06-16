import json
import os
import re
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


APP_NAME = "ZCHAT 额度查看"
BASE_URL = "https://www.zchat.tech"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZchatQuotaViewer")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")


def ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {"token": "", "refresh_seconds": 300}
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            "token": data.get("token", ""),
            "refresh_seconds": int(data.get("refresh_seconds", 300)),
        }
    except Exception:
        return {"token": "", "refresh_seconds": 300}


def save_config(config):
    ensure_config_dir()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def clean_token(value):
    value = value.strip().strip("'\"")
    if not value:
        return ""
    value = value.replace("\\x3D", "=").replace("\\x3B", ";")
    match = re.search(r"(?:^|[;\s])token=([^;\s'\"`]+)", value)
    if match:
        return match.group(1).strip().strip("'\"")
    if value.lower().startswith("bearer "):
        return value.split(None, 1)[1].strip().strip("'\"")
    return value


def unwrap_response(payload):
    if isinstance(payload, dict):
        if "data" in payload and isinstance(payload["data"], (dict, list)):
            return payload["data"]
        if "_rawValue" in payload:
            return unwrap_response(payload["_rawValue"])
    return payload


def api_post(path, token):
    url = f"{BASE_URL}/{path.lstrip('/')}"
    body = b"{}"
    request = Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/users/setting",
            "User-Agent": "ZchatQuotaViewer/1.0",
        },
    )
    with urlopen(request, timeout=20) as response:
        text = response.read().decode("utf-8", errors="replace")
    return json.loads(text)


def flatten_json(value, prefix=""):
    rows = []
    if isinstance(value, dict):
        for key, item in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            rows.extend(flatten_json(item, path))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            path = f"{prefix}[{index}]"
            rows.extend(flatten_json(item, path))
    else:
        rows.append((prefix, value))
    return rows


def pick_first(flat, patterns):
    for key, value in flat:
        low = key.lower()
        if all(pattern in low for pattern in patterns) and value not in (None, ""):
            return value
    return None


def field_name(path):
    path = re.sub(r"\[\d+\]", "", path)
    return path.split(".")[-1].lower()


def pick_field(flat, names):
    wanted = {name.lower() for name in names}
    for key, value in flat:
        if field_name(key) in wanted and value not in (None, ""):
            return value
    return None


def pick_path(flat, names):
    wanted = {name.lower() for name in names}
    for key, value in flat:
        normalized = key.lower().replace("_", "").replace("-", "")
        if normalized in wanted and value not in (None, ""):
            return value
    return None


def normalize_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    number = float(match.group(0))
    return int(number) if number.is_integer() else number


def parse_ratio(value):
    if not isinstance(value, str):
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", value)
    if not match:
        return None
    used = normalize_number(match.group(1))
    total = normalize_number(match.group(2))
    if total is None or used is None or total <= 0:
        return None
    return used, total


def iter_objects(value, path=""):
    if isinstance(value, dict):
        yield path, value
        for key, item in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            yield from iter_objects(item, child_path)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from iter_objects(item, f"{path}[{index}]")


def score_text(text, kind):
    text = text.lower()
    high_words = ("advanced", "advance", "high", "vip", "gpt", "premium", "plus", "高级")
    free_words = ("free", "normal", "basic", "trial", "gratis", "免费", "普通", "基础")
    score = 0
    if kind == "high":
        score += sum(8 for word in high_words if word in text)
        score -= sum(6 for word in free_words if word in text)
    else:
        score += sum(8 for word in free_words if word in text)
        score -= sum(6 for word in high_words if word in text and word not in ("basic",))
    score += sum(2 for word in ("day", "daily", "quota", "limit", "usage", "used", "count", "num", "times", "额度", "用量") if word in text)
    return score


def find_ratio_candidate(value, kind):
    best = None
    for key, item in flatten_json(value):
        ratio = parse_ratio(str(item)) if isinstance(item, str) else None
        if not ratio:
            continue
        used, total = ratio
        label = f"{key} {item}"
        score = score_text(label, kind)
        if total in (30, 100, 200, 300):
            score += 4
        if best is None or score > best[0]:
            best = (score, used, total, key)
    if best and best[0] > 0:
        return best[1], best[2]
    return None, None


def find_numeric_pair(value, kind):
    best = None
    used_tokens = ("used", "use", "usage", "consume", "consumed", "cost", "spent", "current", "已用", "使用")
    total_tokens = ("limit", "total", "quota", "amount", "max", "times", "frequency", "count", "num", "每日", "额度", "总")
    for path, obj in iter_objects(value):
        numeric = []
        for key, item in obj.items():
            if isinstance(item, (dict, list)):
                continue
            number = normalize_number(item)
            if number is not None:
                numeric.append((str(key), number))
        for used_key, used in numeric:
            for total_key, total in numeric:
                if used_key == total_key or total <= 0 or used > total:
                    continue
                used_name = used_key.lower()
                total_name = total_key.lower()
                used_score = any(token in used_name for token in used_tokens)
                total_score = any(token in total_name for token in total_tokens)
                if not used_score and not total_score:
                    continue
                text = f"{path}.{used_key}.{total_key}"
                score = score_text(text, kind)
                if used_score:
                    score += 3
                if total_score:
                    score += 3
                if total in (30, 100, 200, 300):
                    score += 4
                if best is None or score > best[0]:
                    best = (score, used, total, text)
    if best and best[0] > 0:
        return best[1], best[2]
    return None, None


def discover_quota(value, kind):
    used, total = find_ratio_candidate(value, kind)
    if used is not None and total is not None:
        return used, total
    return find_numeric_pair(value, kind)


def find_quota_lines(user_data):
    flat = flatten_json(user_data)
    interesting = []
    needles = (
        "quota",
        "limit",
        "usage",
        "used",
        "remain",
        "free",
        "vip",
        "gpt",
        "高级",
        "免费",
        "额度",
        "用量",
        "余额",
        "balance",
        "money",
    )
    for key, value in flat:
        text = key.lower()
        if any(needle in text for needle in needles):
            if isinstance(value, (str, int, float, bool)) or value is None:
                interesting.append((key, value))
    return interesting[:40]


def find_plan(user_data, vip_data):
    user_flat = flatten_json(user_data)
    vip_id = pick_field(user_flat, ["vip_id", "vip_type", "v_id", "vip_level_id", "level_id"])
    vip_title = pick_field(user_flat, ["vip_title", "vip_name", "vip_level", "level_name"])
    rows = vip_data if isinstance(vip_data, list) else vip_data.get("data", []) if isinstance(vip_data, dict) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_flat = flatten_json(row)
        row_id = pick_field(row_flat, ["id", "vip_id", "v_id"])
        row_title = pick_field(row_flat, ["title", "name", "vip_title", "vip_name"])
        if vip_id is not None and str(row_id) == str(vip_id):
            return row
        if vip_title and row_title and str(vip_title) in str(row_title):
            return row
    return None


def pick_quota_pair(flat, prefixes):
    used_names = []
    total_names = []
    for prefix in prefixes:
        used_names.extend([
            f"{prefix}_used",
            f"{prefix}_use",
            f"{prefix}_usage",
            f"{prefix}_num",
            f"{prefix}_count",
            f"used_{prefix}",
            f"use_{prefix}",
        ])
        total_names.extend([
            f"{prefix}_limit",
            f"{prefix}_total",
            f"{prefix}_quota",
            f"{prefix}_times",
            f"{prefix}_amount",
            f"limit_{prefix}",
            f"total_{prefix}",
        ])
    used = normalize_number(pick_field(flat, used_names))
    total = normalize_number(pick_field(flat, total_names))
    return used, total


def quota_from_plan(plan, prefixes):
    if not plan:
        return None
    flat = flatten_json(plan)
    total_names = []
    for prefix in prefixes:
        total_names.extend([
            f"{prefix}_limit",
            f"{prefix}_total",
            f"{prefix}_quota",
            f"{prefix}_times",
            f"{prefix}_amount",
            f"limit_{prefix}",
            f"total_{prefix}",
        ])
    return normalize_number(pick_field(flat, total_names))


def summarize(user_data, vip_data):
    flat = flatten_json(user_data)
    plan = find_plan(user_data, vip_data)
    plan_flat = flatten_json(plan) if plan else []
    name = pick_field(flat, ["nickname", "name", "username"]) or pick_field(flat, ["email"]) or "ZCHAT"
    email = pick_field(flat, ["email"]) or ""
    vip_name = (
        pick_field(flat, ["vip_title", "vip_name", "vip_level", "level_name"])
        or pick_field(plan_flat, ["title", "name", "vip_title", "vip_name"])
        or "未识别"
    )
    expire = (
        pick_field(flat, ["vip_expire_time", "vip_end_time", "expire_time", "expired_at", "expires_at", "end_time"])
        or pick_field(flat, ["vip_expire", "vip_end", "expiration", "expire"])
        or "未知"
    )
    balance = (
        pick_field(flat, ["balance", "money", "wallet", "amount", "credit"])
        or "未知"
    )

    combined = {"user": user_data, "matched_plan": plan, "vip_levels": vip_data}
    high_used, high_total = pick_quota_pair(flat, ["advanced", "advance", "high", "vip", "gpt", "premium"])
    free_used, free_total = pick_quota_pair(flat, ["free", "normal", "basic"])
    found_high_used, found_high_total = discover_quota(combined, "high")
    found_free_used, found_free_total = discover_quota(combined, "free")
    high_used = high_used if high_used is not None else found_high_used
    high_total = high_total if high_total is not None else found_high_total
    free_used = free_used if free_used is not None else found_free_used
    free_total = free_total if free_total is not None else found_free_total
    high_total = high_total or quota_from_plan(plan, ["advanced", "advance", "high", "vip", "gpt", "premium"])
    free_total = free_total or quota_from_plan(plan, ["free", "normal", "basic"])

    return {
        "name": str(name),
        "email": str(email),
        "vip_name": str(vip_name),
        "expire": str(expire),
        "balance": str(balance),
        "high_used": high_used,
        "high_total": high_total,
        "free_used": free_used,
        "free_total": free_total,
        "quota_lines": find_quota_lines(combined),
        "raw_user": user_data,
        "raw_vip": vip_data,
    }


class QuotaApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("560x680")
        self.minsize(480, 560)
        self.configure(bg="#f5f7fb")
        self.config_data = load_config()
        self.loading = False
        self.last_payload = None
        self.after_id = None
        self.create_widgets()
        self.refresh()
        self.schedule_next()

    def create_widgets(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TButton", padding=8)
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Title.TLabel", background="#f5f7fb", foreground="#1f2937", font=("Microsoft YaHei UI", 18, "bold"))
        style.configure("Sub.TLabel", background="#f5f7fb", foreground="#64748b", font=("Microsoft YaHei UI", 10))
        style.configure("CardTitle.TLabel", background="#ffffff", foreground="#475569", font=("Microsoft YaHei UI", 10, "bold"))
        style.configure("Value.TLabel", background="#ffffff", foreground="#111827", font=("Microsoft YaHei UI", 20, "bold"))
        style.configure("Small.TLabel", background="#ffffff", foreground="#64748b", font=("Microsoft YaHei UI", 9))

        header = ttk.Frame(self, padding=(18, 18, 18, 8))
        header.configure(style="Card.TFrame")
        header.pack(fill="x", padx=16, pady=(16, 10))

        title_row = ttk.Frame(header, style="Card.TFrame")
        title_row.pack(fill="x")
        ttk.Label(title_row, text="ZCHAT 额度", style="Value.TLabel").pack(side="left")
        ttk.Button(title_row, text="刷新", command=self.refresh).pack(side="right", padx=(8, 0))
        ttk.Button(title_row, text="设置", command=self.open_settings).pack(side="right")
        ttk.Button(title_row, text="复制数据", command=self.copy_raw).pack(side="right", padx=(0, 8))

        self.user_label = ttk.Label(header, text="等待刷新", style="Small.TLabel")
        self.user_label.pack(anchor="w", pady=(8, 0))
        self.status_label = ttk.Label(header, text="", style="Small.TLabel")
        self.status_label.pack(anchor="w", pady=(2, 0))

        self.high_card = self.create_quota_card("高级额度 每日用量")
        self.free_card = self.create_quota_card("免费额度 每日用量")

        info = ttk.Frame(self, padding=16, style="Card.TFrame")
        info.pack(fill="x", padx=16, pady=10)
        ttk.Label(info, text="账户信息", style="CardTitle.TLabel").grid(row=0, column=0, sticky="w", columnspan=2)
        self.vip_label = ttk.Label(info, text="套餐：未知", style="Small.TLabel")
        self.vip_label.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.expire_label = ttk.Label(info, text="到期：未知", style="Small.TLabel")
        self.expire_label.grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.balance_label = ttk.Label(info, text="余额：未知", style="Small.TLabel")
        self.balance_label.grid(row=3, column=0, sticky="w", pady=(6, 0))
        info.columnconfigure(0, weight=1)

        details = ttk.Frame(self, padding=16, style="Card.TFrame")
        details.pack(fill="both", expand=True, padx=16, pady=(10, 16))
        detail_row = ttk.Frame(details, style="Card.TFrame")
        detail_row.pack(fill="x")
        ttk.Label(detail_row, text="接口返回的额度相关字段", style="CardTitle.TLabel").pack(side="left")
        ttk.Button(detail_row, text="复制原始数据", command=self.copy_raw).pack(side="right")
        self.detail_text = scrolledtext.ScrolledText(details, height=10, wrap="word", font=("Consolas", 9), bg="#f8fafc", relief="flat")
        self.detail_text.pack(fill="both", expand=True, pady=(10, 0))
        self.detail_text.insert("1.0", "刷新后这里会列出额度、余额、用量相关字段。")
        self.detail_text.configure(state="disabled")

    def create_quota_card(self, title):
        frame = ttk.Frame(self, padding=16, style="Card.TFrame")
        frame.pack(fill="x", padx=16, pady=10)
        ttk.Label(frame, text=title, style="CardTitle.TLabel").pack(anchor="w")
        value = ttk.Label(frame, text="-- / --", style="Value.TLabel")
        value.pack(anchor="w", pady=(8, 8))
        bar = ttk.Progressbar(frame, maximum=100)
        bar.pack(fill="x")
        remain = ttk.Label(frame, text="剩余未知", style="Small.TLabel")
        remain.pack(anchor="w", pady=(8, 0))
        frame.value_label = value
        frame.progress = bar
        frame.remain_label = remain
        return frame

    def schedule_next(self):
        if self.after_id:
            self.after_cancel(self.after_id)
        seconds = max(30, int(self.config_data.get("refresh_seconds", 300)))
        self.after_id = self.after(seconds * 1000, self.refresh_and_reschedule)

    def refresh_and_reschedule(self):
        self.refresh()
        self.schedule_next()

    def refresh(self):
        if self.loading:
            return
        token = clean_token(self.config_data.get("token", ""))
        if not token:
            self.status_label.configure(text="请先点击“设置”，粘贴 zchat 的 token。")
            self.open_settings()
            return
        self.loading = True
        self.status_label.configure(text="正在刷新...")
        threading.Thread(target=self.fetch_worker, args=(token,), daemon=True).start()

    def fetch_worker(self, token):
        try:
            user_payload = api_post("api/get_user", token)
            vip_payload = api_post("api/get_vip_level", token)
            user_data = unwrap_response(user_payload)
            vip_data = unwrap_response(vip_payload)
            result = summarize(user_data, vip_data)
            self.after(0, lambda: self.apply_result(result))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            text = f"HTTP {exc.code}: {detail[:200]}"
            self.after(0, lambda text=text: self.show_error(text))
        except (URLError, TimeoutError) as exc:
            text = f"网络错误：{exc}"
            self.after(0, lambda text=text: self.show_error(text))
        except Exception as exc:
            text = f"刷新失败：{exc}"
            self.after(0, lambda text=text: self.show_error(text))

    def apply_result(self, result):
        self.loading = False
        self.last_payload = result
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        user_text = result["name"]
        if result["email"]:
            user_text += f" · {result['email']}"
        self.user_label.configure(text=user_text)
        self.status_label.configure(text=f"最后刷新：{now}")
        self.vip_label.configure(text=f"套餐：{result['vip_name']}")
        self.expire_label.configure(text=f"到期：{result['expire']}")
        self.balance_label.configure(text=f"余额：{result['balance']}")
        self.update_quota_card(self.high_card, result["high_used"], result["high_total"])
        self.update_quota_card(self.free_card, result["free_used"], result["free_total"])
        self.render_details(result["quota_lines"])

    def update_quota_card(self, card, used, total):
        if total is not None and used is None:
            card.value_label.configure(text=f"-- / {total} 次")
            card.progress.configure(value=0)
            card.remain_label.configure(text="已识别每日总额度；已用次数字段待适配。")
            return
        if used is None or total is None or total == 0:
            card.value_label.configure(text="-- / --")
            card.progress.configure(value=0)
            card.remain_label.configure(text="接口字段未自动识别，请看下方字段列表。")
            return
        percent = max(0, min(100, (float(used) / float(total)) * 100))
        remain = max(0, total - used)
        card.value_label.configure(text=f"{used} / {total} 次")
        card.progress.configure(value=percent)
        card.remain_label.configure(text=f"剩余 {remain} 次 · 已用 {percent:.0f}%")

    def render_details(self, rows):
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        if not rows:
            self.detail_text.insert("1.0", "没有发现明显的额度字段。可以点“复制原始数据”发给 Codex 继续适配字段名。")
        else:
            lines = [f"{key}: {value}" for key, value in rows]
            self.detail_text.insert("1.0", "\n".join(lines))
        self.detail_text.configure(state="disabled")

    def show_error(self, text):
        self.loading = False
        self.status_label.configure(text=text)
        if "401" in text or "403" in text:
            messagebox.showwarning("登录失效", "token 可能已过期，请重新登录 zchat 后更新 token。")

    def open_settings(self):
        dialog = tk.Toplevel(self)
        dialog.title("设置")
        dialog.geometry("520x360")
        dialog.transient(self)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="粘贴 token 或包含 token=... 的 document.cookie：").pack(anchor="w")
        token_text = scrolledtext.ScrolledText(frame, height=5, wrap="word")
        token_text.pack(fill="x", pady=(8, 12))
        token_text.insert("1.0", self.config_data.get("token", ""))

        ttk.Label(frame, text="刷新间隔（秒，最低 30）：").pack(anchor="w")
        interval_var = tk.StringVar(value=str(self.config_data.get("refresh_seconds", 300)))
        ttk.Entry(frame, textvariable=interval_var).pack(fill="x", pady=(8, 12))

        help_text = (
            "获取 token 的一种方式：登录 zchat 后，在该网页按 F12，Console 输入 "
            "document.cookie，然后复制 token= 后面的值。程序只把 token 保存在本机。"
        )
        ttk.Label(frame, text=help_text, wraplength=470, foreground="#64748b").pack(anchor="w", pady=(0, 12))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")

        def save_and_close():
            token = clean_token(token_text.get("1.0", "end"))
            try:
                seconds = max(30, int(interval_var.get().strip()))
            except ValueError:
                messagebox.showerror("设置错误", "刷新间隔必须是数字。")
                return
            self.config_data = {"token": token, "refresh_seconds": seconds}
            save_config(self.config_data)
            dialog.destroy()
            self.refresh()
            self.schedule_next()

        ttk.Button(buttons, text="保存并刷新", command=save_and_close).pack(side="right")
        ttk.Button(buttons, text="取消", command=dialog.destroy).pack(side="right", padx=(0, 8))

    def copy_raw(self):
        if not self.last_payload:
            self.status_label.configure(text="还没有可复制的数据，请先刷新一次。")
            return
        data = {
            "user": self.last_payload["raw_user"],
            "vip": self.last_payload["raw_vip"],
        }
        self.clipboard_clear()
        self.clipboard_append(json.dumps(data, ensure_ascii=False, indent=2))
        self.status_label.configure(text="原始数据已复制到剪贴板。")


if __name__ == "__main__":
    app = QuotaApp()
    app.mainloop()
