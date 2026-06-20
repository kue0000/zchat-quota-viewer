import json
import os
import re
import threading
import time
import tkinter as tk
import webbrowser
from tkinter import messagebox, scrolledtext, ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


APP_NAME = "ZCHAT Quota Viewer"
BASE_URL = "https://www.zchat.tech"
SETTINGS_URL = f"{BASE_URL}/users/setting"
CONFIG_DIR = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "ZchatQuotaViewer")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "token": "",
    "refresh_seconds": 300,
    "plan_mode": "manual",
    "current_vip_id": 7,
    "alert_high_remaining": 20,
    "alert_balance_below": 10.0,
    "alerts_enabled": True,
    "start_minimized": False,
    "show_mini_on_start": True,
    "mini_topmost": True,
}

VIP_IDS = {
    6: "zchat体验月卡",
    7: "zchat基础月卡",
    8: "zchat高级月卡",
    9: "zchat超级月卡",
    12: "zchat顶级周卡",
}


def ensure_config_dir():
    os.makedirs(CONFIG_DIR, exist_ok=True)


def load_config():
    config = dict(DEFAULT_CONFIG)
    if not os.path.exists(CONFIG_PATH):
        return config
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        config.update(data)
        config["refresh_seconds"] = int(config.get("refresh_seconds", DEFAULT_CONFIG["refresh_seconds"]))
        config["current_vip_id"] = int(config.get("current_vip_id", DEFAULT_CONFIG["current_vip_id"]))
        config["alert_high_remaining"] = int(config.get("alert_high_remaining", DEFAULT_CONFIG["alert_high_remaining"]))
        config["alert_balance_below"] = float(config.get("alert_balance_below", DEFAULT_CONFIG["alert_balance_below"]))
        config["alerts_enabled"] = bool(config.get("alerts_enabled", DEFAULT_CONFIG["alerts_enabled"]))
        config["start_minimized"] = bool(config.get("start_minimized", DEFAULT_CONFIG["start_minimized"]))
        config["show_mini_on_start"] = bool(config.get("show_mini_on_start", DEFAULT_CONFIG["show_mini_on_start"]))
        config["mini_topmost"] = bool(config.get("mini_topmost", DEFAULT_CONFIG["mini_topmost"]))
    except Exception:
        return dict(DEFAULT_CONFIG)
    return config


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


def unwrap_response(payload):
    if isinstance(payload, dict):
        if "data" in payload and isinstance(payload["data"], (dict, list)):
            return payload["data"]
        if "_rawValue" in payload:
            return unwrap_response(payload["_rawValue"])
    return payload


def api_post(path, token):
    request = Request(
        f"{BASE_URL}/{path.lstrip('/')}",
        data=b"{}",
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "Origin": BASE_URL,
            "Referer": SETTINGS_URL,
            "User-Agent": "ZchatQuotaViewer/2.0",
        },
    )
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def build_vip_rows(user, vip_levels):
    rows = []
    if not isinstance(vip_levels, list):
        return rows
    high_used = normalize_number(user.get("gpt4_send")) or 0
    free_used = normalize_number(user.get("gpt35_send")) or 0
    for plan in vip_levels:
        if not isinstance(plan, dict):
            continue
        high_total = normalize_number(plan.get("gpt4_send_limit")) or 0
        free_total = normalize_number(plan.get("gpt35_send_limit")) or 0
        rows.append({
            "id": plan.get("id"),
            "title": str(plan.get("title", VIP_IDS.get(plan.get("id"), "未知套餐"))),
            "price": str(plan.get("pay_amount", "")),
            "days": normalize_number(plan.get("end_time")) or 0,
            "level": normalize_number(plan.get("level")) or 0,
            "description": str(plan.get("description", "")),
            "high_used": high_used,
            "high_total": high_total,
            "free_used": free_used,
            "free_total": free_total,
        })
    return rows


def infer_plan_id_from_user(user):
    for key in ("vip_id", "vip_type", "v_id", "vip_level_id", "level_id"):
        if key in user and user[key] not in (None, ""):
            return normalize_number(user[key])
    title = str(user.get("vip_title") or user.get("vip_name") or user.get("level_name") or "")
    if title:
        for vip_id, name in VIP_IDS.items():
            if title in name or name in title:
                return vip_id
    return None


def choose_active_row(rows, user, config):
    mode = config.get("plan_mode", "manual")
    plan_id = infer_plan_id_from_user(user) if mode == "auto" else None
    if plan_id is None:
        plan_id = config.get("current_vip_id", 7)
    for row in rows:
        if str(row["id"]) == str(plan_id):
            return row, "auto" if mode == "auto" and infer_plan_id_from_user(user) is not None else "manual"
    return (rows[0], "fallback") if rows else (None, "none")


def quota_percent(used, total):
    if total in (None, 0):
        return 0
    return max(0, min(100, float(used) / float(total) * 100))


class QuotaRing(tk.Canvas):
    def __init__(self, parent, size=132, **kwargs):
        super().__init__(parent, width=size, height=size, bg=kwargs.get("bg", "#ffffff"), highlightthickness=0)
        self.size = size
        self.percent = 0
        self.text = "--"
        self.draw()

    def set_value(self, remaining, total):
        if total:
            self.percent = max(0, min(100, float(remaining) / float(total) * 100))
        else:
            self.percent = 0
        self.text = str(remaining) if remaining is not None else "--"
        self.draw()

    def draw(self):
        self.delete("all")
        pad = 10
        extent = max(0, min(359.9, self.percent / 100 * 360))
        self.create_oval(pad, pad, self.size - pad, self.size - pad, outline="#e5e7eb", width=12)
        self.create_arc(pad, pad, self.size - pad, self.size - pad, start=90, extent=-extent, outline="#2563eb", width=12, style="arc")
        self.create_text(self.size / 2, self.size / 2 - 5, text=self.text, fill="#0f172a", font=("Microsoft YaHei UI", 26, "bold"))
        self.create_text(self.size / 2, self.size / 2 + 26, text="剩余", fill="#64748b", font=("Microsoft YaHei UI", 9))


def quota_summary(user, vip_levels, config):
    rows = build_vip_rows(user, vip_levels)
    active, source = choose_active_row(rows, user, config)
    balance = normalize_number(user.get("money"))
    result = {
        "name": str(user.get("name") or "ZCHAT"),
        "email": str(user.get("email") or ""),
        "balance": balance,
        "updated_at": str(user.get("updated_at") or ""),
        "active": active,
        "plan_source": source,
        "rows": rows,
        "raw_user": user,
        "raw_vip": vip_levels,
    }
    if active:
        result["high_remaining"] = max(0, active["high_total"] - active["high_used"])
        result["free_remaining"] = max(0, active["free_total"] - active["free_used"])
    else:
        result["high_remaining"] = None
        result["free_remaining"] = None
    return result


class MiniWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("ZCHAT Mini")
        self.geometry("300x168")
        self.resizable(False, False)
        self.configure(bg="#111827")
        self.attributes("-topmost", parent.config_data.get("mini_topmost", True))
        self.protocol("WM_DELETE_WINDOW", self.withdraw)
        frame = tk.Frame(self, bg="#111827", padx=16, pady=14)
        frame.pack(fill="both", expand=True)
        self.title_label = tk.Label(frame, text="ZCHAT", fg="#e5e7eb", bg="#111827", font=("Microsoft YaHei UI", 12, "bold"))
        self.title_label.pack(anchor="w")
        self.high_label = tk.Label(frame, text="-- 次剩余", fg="#ffffff", bg="#111827", font=("Microsoft YaHei UI", 24, "bold"))
        self.high_label.pack(anchor="w", pady=(6, 0))
        self.detail_label = tk.Label(frame, text="高级额度 -- / --", fg="#93c5fd", bg="#111827", font=("Microsoft YaHei UI", 10))
        self.detail_label.pack(anchor="w")
        self.free_label = tk.Label(frame, text="免费额度 -- / --", fg="#cbd5e1", bg="#111827", font=("Microsoft YaHei UI", 9))
        self.free_label.pack(anchor="w", pady=(8, 0))
        self.balance_label = tk.Label(frame, text="余额 --", fg="#cbd5e1", bg="#111827", font=("Microsoft YaHei UI", 9))
        self.balance_label.pack(anchor="w")
        self.position_near_corner()
        self.withdraw()

    def position_near_corner(self):
        self.update_idletasks()
        width = self.winfo_width() or 300
        height = self.winfo_height() or 168
        x = max(0, self.winfo_screenwidth() - width - 28)
        y = 72
        self.geometry(f"{width}x{height}+{x}+{y}")

    def update_data(self, data):
        active = data.get("active")
        if not active:
            return
        self.title_label.configure(text=active["title"])
        self.high_label.configure(text=f"{data['high_remaining']} 次剩余")
        self.detail_label.configure(text=f"高级额度 {active['high_used']} / {active['high_total']} 次")
        self.free_label.configure(text=f"免费额度 {active['free_used']} / {active['free_total']} 次")
        self.balance_label.configure(text=f"余额 {data['balance'] if data['balance'] is not None else '--'}")


class QuotaApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("760x800")
        self.minsize(680, 680)
        self.configure(bg="#f3f6fb")
        self.config_data = load_config()
        self.loading = False
        self.after_id = None
        self.last_payload = None
        self.last_alert_key = None
        self.mini = None
        self.create_widgets()
        if self.config_data.get("show_mini_on_start", True):
            self.after(300, self.show_mini)
        if self.config_data.get("start_minimized"):
            self.after(200, self.withdraw)
        self.refresh()
        self.schedule_next()

    def create_widgets(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f6fb")
        style.configure("Card.TFrame", background="#ffffff", relief="flat")
        style.configure("Hero.TFrame", background="#ffffff", relief="flat")
        style.configure("TButton", padding=(12, 8), font=("Microsoft YaHei UI", 9))
        style.configure("Title.TLabel", background="#ffffff", foreground="#0f172a", font=("Microsoft YaHei UI", 24, "bold"))
        style.configure("Muted.TLabel", background="#ffffff", foreground="#64748b", font=("Microsoft YaHei UI", 9))
        style.configure("Section.TLabel", background="#ffffff", foreground="#334155", font=("Microsoft YaHei UI", 11, "bold"))
        style.configure("Metric.TLabel", background="#ffffff", foreground="#0f172a", font=("Microsoft YaHei UI", 34, "bold"))
        style.configure("SubMetric.TLabel", background="#ffffff", foreground="#475569", font=("Microsoft YaHei UI", 11))
        style.configure("Pill.TLabel", background="#dbeafe", foreground="#1d4ed8", font=("Microsoft YaHei UI", 9, "bold"), padding=(10, 4))

        shell = ttk.Frame(self, padding=18)
        shell.pack(fill="both", expand=True)

        header = ttk.Frame(shell, padding=18, style="Card.TFrame")
        header.pack(fill="x")
        left = ttk.Frame(header, style="Card.TFrame")
        left.pack(side="left", fill="x", expand=True)
        ttk.Label(left, text="ZCHAT 额度", style="Title.TLabel").pack(anchor="w")
        self.user_label = ttk.Label(left, text="等待刷新", style="Muted.TLabel")
        self.user_label.pack(anchor="w", pady=(8, 0))
        self.status_label = ttk.Label(left, text="", style="Muted.TLabel")
        self.status_label.pack(anchor="w", pady=(3, 0))
        actions = ttk.Frame(header, style="Card.TFrame")
        actions.pack(side="right")
        ttk.Button(actions, text="刷新", command=self.refresh).grid(row=0, column=0, padx=4, pady=3)
        ttk.Button(actions, text="迷你窗", command=self.toggle_mini).grid(row=0, column=1, padx=4, pady=3)
        ttk.Button(actions, text="设置", command=self.open_settings).grid(row=1, column=0, padx=4, pady=3)
        ttk.Button(actions, text="复制数据", command=self.copy_raw).grid(row=1, column=1, padx=4, pady=3)

        self.plan_card = ttk.Frame(shell, padding=22, style="Hero.TFrame")
        self.plan_card.pack(fill="x", pady=(14, 0))
        hero_left = ttk.Frame(self.plan_card, style="Hero.TFrame")
        hero_left.pack(side="left", fill="both", expand=True)
        self.plan_label = ttk.Label(hero_left, text="当前套餐 --", style="Section.TLabel")
        self.plan_label.pack(anchor="w")
        self.high_value = ttk.Label(hero_left, text="-- 次", style="Metric.TLabel")
        self.high_value.pack(anchor="w", pady=(8, 0))
        self.high_detail = ttk.Label(hero_left, text="高级额度等待刷新", style="SubMetric.TLabel")
        self.high_detail.pack(anchor="w", pady=(4, 0))
        self.free_detail = ttk.Label(hero_left, text="免费额度等待刷新", style="Muted.TLabel")
        self.free_detail.pack(anchor="w", pady=(10, 0))
        self.status_pill = ttk.Label(hero_left, text="等待刷新", style="Pill.TLabel")
        self.status_pill.pack(anchor="w", pady=(14, 0))
        hero_right = ttk.Frame(self.plan_card, style="Hero.TFrame")
        hero_right.pack(side="right", padx=(18, 0))
        self.quota_ring = QuotaRing(hero_right, size=142)
        self.quota_ring.pack()

        info = ttk.Frame(shell, padding=18, style="Card.TFrame")
        info.pack(fill="x", pady=(14, 0))
        ttk.Label(info, text="账户状态", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky="w")
        self.balance_label = ttk.Label(info, text="余额：--", style="SubMetric.TLabel")
        self.balance_label.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.source_label = ttk.Label(info, text="套餐识别：--", style="SubMetric.TLabel")
        self.source_label.grid(row=1, column=1, sticky="w", padx=(24, 0), pady=(10, 0))
        self.alert_label = ttk.Label(info, text="告警：--", style="SubMetric.TLabel")
        self.alert_label.grid(row=1, column=2, sticky="w", padx=(24, 0), pady=(10, 0))

        table_card = ttk.Frame(shell, padding=18, style="Card.TFrame")
        table_card.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(table_card, text="VIP 额度表", style="Section.TLabel").pack(anchor="w")
        columns = ("id", "title", "price", "high", "free")
        self.vip_tree = ttk.Treeview(table_card, columns=columns, show="headings", height=8)
        headings = {"id": "ID", "title": "套餐", "price": "价格", "high": "高级额度", "free": "免费额度"}
        widths = {"id": 50, "title": 180, "price": 70, "high": 130, "free": 130}
        for col in columns:
            self.vip_tree.heading(col, text=headings[col])
            self.vip_tree.column(col, width=widths[col], anchor="center" if col != "title" else "w")
        self.vip_tree.tag_configure("active", background="#dff0ff")
        self.vip_tree.tag_configure("warning", background="#fff7ed")
        self.vip_tree.pack(fill="both", expand=True, pady=(10, 0))

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
            self.status_label.configure(text="请先设置 token。")
            self.open_settings()
            return
        self.loading = True
        self.status_label.configure(text="正在刷新...")
        threading.Thread(target=self.fetch_worker, args=(token,), daemon=True).start()

    def fetch_worker(self, token):
        try:
            user = unwrap_response(api_post("api/get_user", token))
            vip = unwrap_response(api_post("api/get_vip_level", token))
            result = quota_summary(user, vip, self.config_data)
            self.after(0, lambda: self.apply_result(result))
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            self.after(0, lambda text=f"HTTP {exc.code}: {detail[:220]}": self.show_error(text))
        except (URLError, TimeoutError) as exc:
            self.after(0, lambda text=f"网络错误：{exc}": self.show_error(text))
        except Exception as exc:
            self.after(0, lambda text=f"刷新失败：{exc}": self.show_error(text))

    def apply_result(self, data):
        self.loading = False
        self.last_payload = data
        active = data.get("active")
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        user_text = data["name"] + (f" · {data['email']}" if data["email"] else "")
        self.user_label.configure(text=user_text)
        self.status_label.configure(text=f"最后刷新：{now}")
        if active:
            high_percent = quota_percent(active["high_used"], active["high_total"])
            high_remaining = data["high_remaining"]
            free_remaining = data["free_remaining"]
            self.plan_label.configure(text=f"当前套餐：{active['title']} (ID {active['id']})")
            self.high_value.configure(text=f"{high_remaining} 次")
            self.quota_ring.set_value(high_remaining, active["high_total"])
            self.high_detail.configure(text=f"高级额度 {active['high_used']} / {active['high_total']} 次 · 已用 {high_percent:.0f}%")
            self.free_detail.configure(text=f"免费额度 {active['free_used']} / {active['free_total']} 次 · 剩余 {free_remaining} 次")
            if high_remaining <= self.config_data.get("alert_high_remaining", 20):
                self.status_pill.configure(text="额度偏低")
            else:
                self.status_pill.configure(text="额度充足")
        self.balance_label.configure(text=f"余额：{data['balance'] if data['balance'] is not None else '--'}")
        source_text = {"auto": "接口自动", "manual": "手动 ID", "fallback": "回退首项", "none": "未识别"}.get(data["plan_source"], data["plan_source"])
        self.source_label.configure(text=f"套餐识别：{source_text}")
        self.render_rows(data)
        self.check_alerts(data)
        if self.mini:
            self.mini.update_data(data)

    def render_rows(self, data):
        active = data.get("active") or {}
        self.vip_tree.delete(*self.vip_tree.get_children())
        for row in data.get("rows", []):
            tags = ()
            if row["id"] == active.get("id"):
                tags = ("active",)
            self.vip_tree.insert(
                "",
                "end",
                values=(
                    row["id"],
                    row["title"],
                    row["price"],
                    f"{row['high_used']} / {row['high_total']} 次",
                    f"{row['free_used']} / {row['free_total']} 次",
                ),
                tags=tags,
            )

    def check_alerts(self, data):
        if not self.config_data.get("alerts_enabled", True):
            self.alert_label.configure(text="告警：关闭")
            return
        active = data.get("active")
        messages = []
        if active:
            remaining = data["high_remaining"]
            threshold = self.config_data.get("alert_high_remaining", 20)
            if remaining is not None and remaining <= threshold:
                messages.append(f"高级额度剩余 {remaining} 次")
        balance = data.get("balance")
        balance_threshold = self.config_data.get("alert_balance_below", 10.0)
        if balance is not None and balance <= balance_threshold:
            messages.append(f"余额 {balance}")
        if not messages:
            self.alert_label.configure(text="告警：正常")
            return
        text = "；".join(messages)
        self.alert_label.configure(text=f"告警：{text}")
        key = f"{time.strftime('%Y-%m-%d')}|{text}"
        if key != self.last_alert_key:
            self.last_alert_key = key
            messagebox.showwarning("ZCHAT 额度提醒", text)

    def show_error(self, text):
        self.loading = False
        self.status_label.configure(text=text)
        if "401" in text or "403" in text:
            messagebox.showwarning("登录失效", "token 可能已过期，请重新登录 zchat 后更新 token。")

    def toggle_mini(self):
        if self.mini is None or not self.mini.winfo_exists():
            self.mini = MiniWindow(self)
        if self.mini.state() == "withdrawn":
            self.show_mini()
        else:
            self.mini.withdraw()

    def show_mini(self):
        if self.mini is None or not self.mini.winfo_exists():
            self.mini = MiniWindow(self)
        self.mini.attributes("-topmost", self.config_data.get("mini_topmost", True))
        self.mini.position_near_corner()
        self.mini.deiconify()
        self.mini.lift()
        if self.last_payload:
            self.mini.update_data(self.last_payload)

    def open_settings(self):
        dialog = tk.Toplevel(self)
        dialog.title("设置")
        dialog.geometry("560x620")
        dialog.transient(self)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="token 或 document.cookie：").pack(anchor="w")
        token_text = scrolledtext.ScrolledText(frame, height=5, wrap="word")
        token_text.pack(fill="x", pady=(6, 12))
        token_text.insert("1.0", self.config_data.get("token", ""))

        ttk.Button(frame, text="打开 ZCHAT 设置页", command=lambda: webbrowser.open(SETTINGS_URL)).pack(anchor="w", pady=(0, 12))

        ttk.Label(frame, text="套餐识别模式：").pack(anchor="w")
        plan_mode = tk.StringVar(value=self.config_data.get("plan_mode", "manual"))
        mode_row = ttk.Frame(frame)
        mode_row.pack(fill="x", pady=(6, 12))
        ttk.Radiobutton(mode_row, text="自动优先", variable=plan_mode, value="auto").pack(side="left")
        ttk.Radiobutton(mode_row, text="手动套餐 ID", variable=plan_mode, value="manual").pack(side="left", padx=(16, 0))

        ttk.Label(frame, text="当前套餐 ID：6体验 / 7基础 / 8高级 / 9超级 / 12顶级周卡").pack(anchor="w")
        vip_var = tk.StringVar(value=str(self.config_data.get("current_vip_id", 7)))
        ttk.Entry(frame, textvariable=vip_var).pack(fill="x", pady=(6, 12))

        ttk.Label(frame, text="刷新间隔（秒，最低 30）：").pack(anchor="w")
        interval_var = tk.StringVar(value=str(self.config_data.get("refresh_seconds", 300)))
        ttk.Entry(frame, textvariable=interval_var).pack(fill="x", pady=(6, 12))

        ttk.Label(frame, text="高级额度剩余告警阈值：").pack(anchor="w")
        high_alert_var = tk.StringVar(value=str(self.config_data.get("alert_high_remaining", 20)))
        ttk.Entry(frame, textvariable=high_alert_var).pack(fill="x", pady=(6, 12))

        ttk.Label(frame, text="余额低于多少元告警：").pack(anchor="w")
        balance_alert_var = tk.StringVar(value=str(self.config_data.get("alert_balance_below", 10.0)))
        ttk.Entry(frame, textvariable=balance_alert_var).pack(fill="x", pady=(6, 12))

        alerts_var = tk.BooleanVar(value=self.config_data.get("alerts_enabled", True))
        ttk.Checkbutton(frame, text="启用告警", variable=alerts_var).pack(anchor="w")
        start_var = tk.BooleanVar(value=self.config_data.get("start_minimized", False))
        ttk.Checkbutton(frame, text="启动后隐藏主窗口", variable=start_var).pack(anchor="w", pady=(6, 0))
        mini_start_var = tk.BooleanVar(value=self.config_data.get("show_mini_on_start", True))
        ttk.Checkbutton(frame, text="启动后显示迷你窗", variable=mini_start_var).pack(anchor="w", pady=(6, 0))
        mini_top_var = tk.BooleanVar(value=self.config_data.get("mini_topmost", True))
        ttk.Checkbutton(frame, text="迷你窗置顶", variable=mini_top_var).pack(anchor="w", pady=(6, 0))

        help_text = "提示：登录 zchat 后按 F12，在 Console 输入 document.cookie，复制整段内容粘贴即可。"
        ttk.Label(frame, text=help_text, wraplength=520, foreground="#64748b").pack(anchor="w", pady=(14, 12))

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")

        def save_and_close():
            try:
                next_config = dict(self.config_data)
                next_config.update({
                    "token": clean_token(token_text.get("1.0", "end")),
                    "plan_mode": plan_mode.get(),
                    "current_vip_id": int(vip_var.get().strip()),
                    "refresh_seconds": max(30, int(interval_var.get().strip())),
                    "alert_high_remaining": int(high_alert_var.get().strip()),
                    "alert_balance_below": float(balance_alert_var.get().strip()),
                    "alerts_enabled": bool(alerts_var.get()),
                    "start_minimized": bool(start_var.get()),
                    "show_mini_on_start": bool(mini_start_var.get()),
                    "mini_topmost": bool(mini_top_var.get()),
                })
            except ValueError:
                messagebox.showerror("设置错误", "套餐 ID、刷新间隔和告警阈值必须是数字。")
                return
            self.config_data = next_config
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
            "config": {k: v for k, v in self.config_data.items() if k != "token"},
        }
        self.clipboard_clear()
        self.clipboard_append(json.dumps(data, ensure_ascii=False, indent=2))
        self.status_label.configure(text="原始数据已复制到剪贴板。")


if __name__ == "__main__":
    app = QuotaApp()
    app.mainloop()
