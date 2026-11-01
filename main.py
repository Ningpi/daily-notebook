# -*- coding: utf-8 -*-
"""
每日记事本 —— 主程序（Tkinter，零第三方依赖）
"""
import os
import sys
import re
import json
import time
import socket
import random
import threading
import subprocess
import datetime as dt
import tkinter as tk
import tkinter.ttk as ttk
from tkinter import font as tkfont

import parser as core
import parser_en as core_en
import quotes as quotebox
import themes as palette
import holidays as cn_holidays
import i18n
from i18n import t as tr

APP_NAME = "每日记事本"
APP_NAME_EN = "Daily Note"
VERSION = "1.9.9.13"


# ----------------------------------------------------------------- 配色
class _Tokens(object):
    """把颜色常量代理到「当前主题」，换肤后所有引用自动跟随"""

    def __init__(self, theme):
        self._t = theme

    def set_theme(self, theme):
        self._t = theme

    @classmethod
    def set_darken(cls, k):
        """字体深浅：文字色向黑色加深（手动 0~100%；自动推导时上限较小）"""
        cls._darken = max(0.0, min(1.0, k))

    _darken = 0.0

    def __getattr__(self, name):
        t = self.__dict__.get("_t") or palette.THEMES[0]
        dk = type(self)._darken
        mapping = {
            "BG": "bg", "HEAD": "head", "LINE": "line", "TEXT": "text",
            "SUB": "sub", "ACCENT": "accent", "ROW2": "row2", "BUBBLE": "bubble",
        }
        if name in mapping:
            c = t[mapping[name]]
            if dk > 0 and name in ("TEXT", "SUB"):
                return _mix(c, "#000000", dk)
            return c
        # 由主题派生的颜色
        if name == "SPLIT":          # 对话框/任务列表分割线：比背景明显加深（v1.9.3）
            return _mix(t["line"], t["text"], 0.45)
        if name == "DONE":            # 已完成文字：主题色掺灰
            return _mix(t["sub"], "#FFFFFF", 0.45)
        if name == "INPUT_BG":
            return _mix(t["bg"], "#FFFFFF", 0.65)
        if name == "INPUT_LINE":
            return _mix(t["line"], "#FFFFFF", 0.15)
        if name == "BOT_BUBBLE":
            return _mix(t["bg"], "#FFFFFF", 0.72)
        if name == "BAR_BG":
            return _mix(t["line"], "#FFFFFF", 0.25)
        raise AttributeError(name)


def _hex(c):
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _mix(a, b, k):
    """a 与 b 按 k 比例混合（k=0 取 a，k=1 取 b）"""
    ra, ga, ba = _hex(a)
    rb, gb, bb = _hex(b)
    return "#%02X%02X%02X" % (
        int(round(ra + (rb - ra) * k)),
        int(round(ga + (gb - ga) * k)),
        int(round(ba + (bb - ba) * k)),
    )


C = _Tokens(palette.THEMES[0])

# 进度条配色（低=灰蓝，过半=橙，全完成=绿）—— 与便签主题无关，保持不变
C_BAR_LOW = "#7C95AB"
C_BAR_MID = "#E8942F"
C_BAR_FULL = "#4CAF6E"

TIPS = [
    "把任务直接说给我，我来帮你排优先级。",
    "试试：「9点开会，下午3点交周报，顺便买瓶酱油」",
    "带时间的任务会自动往前排。",
    "勾掉的任务会沉到底部，晚上回看很有成就感。",
    "点右上角的图钉按钮，可以让便签一直浮在最上层。",
]

ENCOURAGE = [
    "全部搞定，今天你赢了。",
    "收工！这一天很扎实。",
    "件件清零，睡个好觉。",
    "全清空，给自己鼓个掌。",
]


# ----------------------------------------------------------------- 数据
def data_dir():
    """数据目录：优先程序同级 data/（绿色便携），不可写时退回用户目录。

    ⚠ 打包后若装在 C:\\Program Files，同级目录通常没有写权限，
    以前会静默失败（界面正常、重启全丢）。这里用真实写测试判定。
    """
    cands = []
    if getattr(sys, "frozen", False):
        cands.append(os.path.join(os.path.dirname(sys.executable), "data"))
    else:
        cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "data"))
    # 用户目录兜底（各平台统一放在 home 下，避免 APPDATA 权限差异）
    cands.append(os.path.join(os.path.expanduser("~"), ".daily_note"))
    for d in cands:
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".wtest")
            with open(probe, "w") as f:
                f.write("1")
            os.remove(probe)
            return d
        except Exception:
            continue
    return os.path.join(os.path.expanduser("~"), ".daily_note")


class Store(object):
    _save_error = None        # 最近一次写盘错误（None 表示正常）

    def __init__(self):
        self.path = os.path.join(data_dir(), "tasks.json")
        self.hist_path = os.path.join(data_dir(), "history.json")
        self.tasks = []
        self.messages = []
        self.today = self._today()
        self.topmost = True
        self.history = {}          # {"YYYY-MM-DD": [ {title, hhmm, score, done, done_at}, ... ]}
        self.theme = palette.DEFAULT_ID
        self.lang = "zh"
        self.clock_geom = None
        self.alpha = 0.88          # 便签透明度（底栏滑块可调，0.40~1.00）
        self.bell_mode = "chime"
        self.user_name = ""        # 用户昵称（首次启动问出来）
        self.bot_name = ""         # 助手自己的名字
        self.setup_stage = 0       # 0=没问过 1=已问昵称 2=都问好了
        self.bubble_enabled = True # 右下角「未完成任务」气泡开关
        self.bubble_w = 84         # 气泡宽度（拖拽缩放，60~160）
        self.font_scale = 1.0      # 字体缩放（0.8~1.3）
        self.text_darken = None    # 手动字体深浅；None=按透明度自动推导
        self.notes = []
        self.note_pos = None
        self.note_geom = None
        self.chat_h = None
        self.quotes = {"zh": {"last": "", "recent": []},
                       "en": {"last": "", "recent": []}}   # 中英各一套
        self.load()
        self.load_history()
        self.sync_history()

    @staticmethod
    def _today():
        return dt.date.today().isoformat()

    def load(self):
        if not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            self.tasks = obj.get("tasks", [])
            self.messages = obj.get("messages", [])[-60:]
            self.topmost = bool(obj.get("topmost", True))
            self.theme = obj.get("theme", palette.DEFAULT_ID)
            self.lang = obj.get("lang", "zh")
            self.quotes = obj.get("quotes") or {
                "zh": {"last": obj.get("quote_last", ""),
                       "recent": obj.get("quote_recent", [])[-60:]},
                "en": {"last": "", "recent": []},
            }
            self.clock_geom = obj.get("clock_geom")
            self.bell_mode = obj.get("bell_mode", "chime")
            self.notes = obj.get("notes", [])
            self.note_pos = obj.get("note_pos")
            self.note_geom = obj.get("note_geom")
            self.chat_h = obj.get("chat_h")
            self.alpha = float(obj.get("alpha", 0.88))
            self.user_name = (obj.get("user_name") or "").strip()
            self.bot_name = (obj.get("bot_name") or "").strip()
            self.setup_stage = int(obj.get("setup_stage", 0))
            self.bubble_enabled = bool(obj.get("bubble_enabled", True))
            self.bubble_w = max(60, min(160, int(obj.get("bubble_w", 84) or 84)))
            self.font_scale = max(0.8, min(1.3, float(obj.get("font_scale", 1.0) or 1.0)))
            td = obj.get("text_darken")
            if td is not None:
                # 存的是 0~1.0 的浮点；旧版本可能存 0~45 的百分数
                td = float(td)
                if td > 1.0:
                    td = td / 100.0
                self.text_darken = max(0.0, min(1.0, td))
            # v1.8.1 起不再问助手名：停留在旧阶段 2 的直接视为完成
            if self.setup_stage >= 2:
                self.setup_stage = 3
            for k in ("zh", "en"):
                self.quotes.setdefault(k, {"last": "", "recent": []})
            saved_day = obj.get("date", self._today())
            if saved_day != self.today:
                # 跨天（关着软件过了零点）：与运行时 tick 保持同一套规则，
                # 不要把「昨天没做完的事」一律改写成今天 —— 那会让历史失真。
                #
                # v1.9.9 修复：之前先改 self.today 再归档，导致昨天的任务被
                # 记到今天名下（历史里「昨天」永远是空的）。现在先把任务按
                # 原始日期 saved_day 归档，再切到今天。
                today = self._today()
                try:
                    self.sync_history(day=saved_day)
                except Exception:
                    pass
                for t in self.tasks:
                    if t.get("repeat"):
                        # 周期任务：到点才复活，不到点压到已完成区
                        try:
                            t["done"] = not core.repeat_due_today(t["repeat"])
                        except Exception:
                            pass
                        if t["done"]:
                            t["done_at"] = None
                        t["reminded"] = False
                        t["reminded_day"] = None
                        continue
                    dd = t.get("due_date")
                    if dd:
                        # 有明确截止日：还没到就保留时刻，过期才清
                        if dd < today and not t.get("done"):
                            t["hhmm"] = None
                    elif not t.get("done"):
                        t["hhmm"] = None
                    t["reminded"] = False
                    t["reminded_day"] = None
                    # day 保留原始创建日（历史按天归集要用它）
                self.today = today
                self.messages = []
        except Exception:
            pass

    def q_state(self, lang):
        return self.quotes.setdefault("en" if lang == "en" else "zh",
                                      {"last": "", "recent": []})

    def save(self):
        for st in self.quotes.values():
            st["recent"] = st.get("recent", [])[-60:]
        obj = {
            "date": self.today,
            "topmost": self.topmost,
            "theme": self.theme,
            "lang": self.lang,
            "quotes": self.quotes,
            "tasks": self.tasks,
            "messages": self.messages[-60:],
            "clock_geom": getattr(self, "clock_geom", None),
            "bell_mode": getattr(self, "bell_mode", "chime"),
            "notes": getattr(self, "notes", []),
            "note_pos": getattr(self, "note_pos", None),
            "note_geom": getattr(self, "note_geom", None),
            "chat_h": getattr(self, "chat_h", None),
            "alpha": round(float(getattr(self, "alpha", 0.88)), 2),
            "user_name": getattr(self, "user_name", ""),
            "bot_name": getattr(self, "bot_name", ""),
            "setup_stage": int(getattr(self, "setup_stage", 0)),
            "bubble_enabled": bool(getattr(self, "bubble_enabled", True)),
            "bubble_w": int(getattr(self, "bubble_w", 84)),
            "font_scale": round(float(getattr(self, "font_scale", 1.0) or 1.0), 2),
            "text_darken": getattr(self, "text_darken", None),
        }
        self._atomic(self.path, obj)

    # ---------------- 历史归档
    def load_history(self):
        if not os.path.exists(self.hist_path):
            return
        try:
            with open(self.hist_path, "r", encoding="utf-8") as f:
                obj = json.load(f)
            days = obj.get("days", {})
            if isinstance(days, dict):
                self.history = {k: v for k, v in days.items() if isinstance(v, list)}
        except Exception:
            pass

    def save_history(self):
        self._atomic(self.hist_path, {"days": self.history})

    def purge_history(self, titles):
        """从历史（所有天）里移除指定标题的条目（v1.9.8：
        手动删除的任务不再留在历史记录里，数据同步）"""
        if not titles:
            return
        try:
            changed = False
            for day in list(self.history.keys()):
                rows = self.history.get(day) or []
                kept = [r for r in rows if r.get("title", "") not in titles]
                if len(kept) != len(rows):
                    self.history[day] = kept
                    changed = True
            if changed:
                self.save_history()
        except Exception:
            pass

    @staticmethod
    def _atomic(path, obj):
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=1)
            os.replace(tmp, path)
            Store._save_error = None
        except Exception as e:
            # 不能静默：写盘失败要留痕，界面据此提示用户（否则重启即丢数据）
            Store._save_error = "%s: %s" % (type(e).__name__, e)
            try:
                with open(os.path.join(data_dir(), "save_error.log"), "a",
                          encoding="utf-8") as lf:
                    lf.write("%s  %s  %s\n" % (
                        dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), path,
                        Store._save_error))
            except Exception:
                pass

    @staticmethod
    def _hist_sig(rows):
        """当日历史的轻量签名：任何字段变了才算真的变了"""
        return tuple((r.get("title", ""), r.get("hhmm"), r.get("score"),
                      bool(r.get("done")), r.get("done_at", "")) for r in rows)

    def sync_history(self, day=None):
        """把当日任务快照写进历史（按标题合并；内容没变就不写盘）

        day 可显式指定归档到哪一天（跨天启动时用于把昨天的任务归到昨天）。
        """
        day = day or self.today
        snap = self.history.get(day, [])
        by_title = {}
        for r in snap:
            by_title[r.get("title", "")] = r
        changed = False
        for t in self.tasks:
            title = t.get("title", "")
            if not title:
                continue
            old = by_title.get(title)
            if old is None:
                old = {
                    "title": title,
                    "hhmm": t.get("hhmm"),
                    "score": t.get("score", 30),
                    "done": bool(t.get("done")),
                    "done_at": t.get("done_at", "") if t.get("done") else "",
                }
                snap.append(old)
                by_title[title] = old
                changed = True
            else:
                old["score"] = max(old.get("score", 0), t.get("score", 0))
                if t.get("hhmm") and not old.get("hhmm"):
                    old["hhmm"] = t.get("hhmm")
                if t.get("done"):
                    old["done"] = True
                    if not old.get("done_at") and t.get("done_at"):
                        old["done_at"] = t.get("done_at")
                elif old.get("done"):
                    # 取消打勾要同步回历史（此前只单向写 True，
                    # 取消勾选后当天记录还是「已完成」）
                    old["done"] = False
                    old["done_at"] = ""
                    changed = True
        self.history[day] = snap
        # 脏检查：签名没变就不写磁盘（此前每次重绘都全量写盘，是卡顿主因之一）
        sig = self._hist_sig(snap)
        if changed or sig != getattr(self, "_hist_last_sig", None):
            self._hist_last_sig = sig
            self.save_history()

    def history_stats(self, day):
        rows = self.history.get(day, [])
        total = len(rows)
        done = sum(1 for r in rows if r.get("done"))
        return done, total

    def history_days(self):
        return sorted(self.history.keys(), reverse=True)


# ----------------------------------------------------------------- 自绘部件
class Canvas(tk.Canvas):
    def __init__(self, master, **kw):
        kw.setdefault("bg", C.BG)
        kw.setdefault("highlightthickness", 0)
        kw.setdefault("bd", 0)
        super().__init__(master, **kw)


def round_rect(cv, x1, y1, x2, y2, r=8, **kw):
    r = max(1, min(r, (x2 - x1) // 2, (y2 - y1) // 2))
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, splinesteps=12, **kw)


# ----------------------------------------------------------------- 主题图标
# 「给助手起名」：你叫X / 我希望你叫X / 你就叫X / 以后就叫你X
# 不匹配「你以后叫我…」（那是在说自己昵称）
_BOT_NAME_RE = re.compile(
    r"(?:你|您)(?:以后|就|都|要|希望|得)?(?:就)?叫(?!我|自己|什么|啥)([^，,。.!！?？\s]{1,8})")


class IconCache(object):
    """assets/icons/<主题>/<图标>_<深浅>.png 的懒加载缓存。

    图标由设计稿 SVG 预渲染（每套主题 × text/sub/accent 三档），
    运行时零依赖；找不到文件时返回 None，调用方退回自绘/文本。
    """
    _cache = {}
    _base = None

    @classmethod
    def base_dir(cls):
        if cls._base is None:
            base = getattr(sys, "_MEIPASS", None)  # PyInstaller 单文件解包目录
            if not base:
                base = os.path.dirname(os.path.abspath(__file__))
            cls._base = os.path.join(base, "assets", "icons")
        return cls._base

    @classmethod
    def get(cls, name, shade="text", theme=None, owner=None):
        if not theme:
            return None       # 主题必须由调用方传入（store.theme）
        # PhotoImage 绑定在创建时的 root（解释器）上：多 App / 主题重建 /
        # 旧 root 销毁后，跨实例复用同一缓存会变成 "pyimage 不存在"。
        # 因此缓存 key 必须带上归属解释器（owner root），各实例互不串用。
        own_tk = None
        if owner is not None:
            try:
                own_tk = owner.tk
            except Exception:
                own_tk = None
        key = (name, shade, theme, id(own_tk) if own_tk is not None else 0)
        img = cls._cache.get(key)
        if img is not None:
            try:
                # 校验图片仍归属于当前解释器（root 销毁后 tk 属性会失效）
                if own_tk is None:
                    if str(img.tk) == str(tk._get_default_root().tk):
                        return img
                else:
                    if img.tk is own_tk or str(img.tk) == str(own_tk):
                        return img
            except Exception:
                pass
            cls._cache.pop(key, None)
        path = os.path.join(cls.base_dir(), key[2], "%s_%s.png" % (name, shade))
        if not os.path.exists(path) and shade == "faint":
            # 「更淡」档（v1.9.5 置顶/未置顶区分）：预渲染的 45% 透明副本；
            # 老的图标包没有 faint 图时退回 sub，保证不空着
            path = os.path.join(cls.base_dir(), key[2], "%s_faint.png" % name)
            if not os.path.exists(path):
                path = os.path.join(cls.base_dir(), key[2], "%s_sub.png" % name)
        if not os.path.exists(path):
            return None
        try:
            img = tk.PhotoImage(file=path)
        except Exception:
            return None
        cls._cache[key] = img
        return img


# ----------------------------------------------------------------- 右下角提醒小窗
class DueCard(object):
    """截止提醒卡片：默认贴在屏幕右下角，可拖动，点卡片进详情，可关闭。

    多个任务同时到点时会沿着右下角往上叠，不会互相盖住。
    """

    W, H = 268, 116

    def __init__(self, app, task):
        self.app = app
        self.tid = task.get("id")
        self.title = task.get("title", "")
        self.hhmm = task.get("hhmm")
        self.slot = len([c for c in getattr(app, "_due_cards", []) if c.alive()])
        win = tk.Toplevel(app.root)
        self.win = win
        try:
            win.overrideredirect(True)     # 无标题栏的小卡片，更像系统通知
        except Exception:
            pass
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.97)
        except Exception:
            pass
        win.configure(bg=C.LINE)
        outer = tk.Frame(win, bg=C.BG)
        outer.pack(fill="both", expand=True, padx=1, pady=1)
        # 左侧强调竖条
        bar = tk.Frame(outer, bg=C.ACCENT, width=4)
        bar.pack(side="left", fill="y")
        body = tk.Frame(outer, bg=C.BG)
        body.pack(side="left", fill="both", expand=True, padx=10, pady=8)

        self.lbl_name = tk.Label(body, text="", bg=C.BG, fg=C.TEXT,
                                 font=(app.f_ui, 10, "bold"), anchor="w",
                                 justify="left", wraplength=self.W - 46)
        self.lbl_name.pack(fill="x")
        self.lbl_left = tk.Label(body, text="", bg=C.BG, fg="#D97036",
                                 font=app.f_small, anchor="w")
        self.lbl_left.pack(fill="x", pady=(2, 0))
        self.lbl_at = tk.Label(body, text="", bg=C.BG, fg=C.SUB,
                               font=app.f_tiny, anchor="w")
        self.lbl_at.pack(fill="x")
        btns = tk.Frame(body, bg=C.BG)
        btns.pack(fill="x", pady=(6, 0))
        for txt, fn in (("due_ignore", self.close), ("due_detail", self.open_detail)):
            b = tk.Button(btns, text=tr(txt), bg=C.ROW2, fg=C.TEXT, relief="flat",
                          font=app.f_tiny, padx=8,
                          activebackground=C.ACCENT, activeforeground="white",
                          command=fn)
            b.pack(side="right", padx=(6, 0))
        # 关闭小叉（右上）
        self.x_btn = tk.Label(outer, text="×", bg=C.BG, fg=C.SUB,
                              font=(app.f_ui, 11), cursor="hand2")
        self.x_btn.place(relx=1.0, x=-9, y=3, anchor="ne")
        self.x_btn.bind("<Button-1>", lambda e: self.close())

        self.refresh()
        self._place()
        # 拖动整个卡片
        st = {"x": 0, "y": 0, "moved": False}

        def press(e):
            st["x"], st["y"] = e.x_root - win.winfo_x(), e.y_root - win.winfo_y()
            st["moved"] = False

        def drag(e):
            st["moved"] = True
            win.geometry("+%d+%d" % (e.x_root - st["x"], e.y_root - st["y"]))

        def click(e):
            # 拖动过就不算点击，避免「一拖就跳详情」
            if not st["moved"]:
                self.open_detail()

        for w in (outer, body, self.lbl_name, self.lbl_left, self.lbl_at, bar):
            w.bind("<Button-1>", press)
            w.bind("<B1-Motion>", drag)
            w.bind("<ButtonRelease-1>", click)
        self._drag_state = st
        self._tick()

    # ---- 基础
    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    def _place(self):
        win = self.win
        try:
            win.update_idletasks()
            sw = win.winfo_screenwidth()
            sh = win.winfo_screenheight()
            gap = 10
            x = sw - self.W - gap - 6
            y = sh - self.H - gap - 52 - self.slot * (self.H + gap)
            win.geometry("%dx%d+%d+%d" % (self.W, self.H, max(0, x), max(0, y)))
        except Exception:
            pass

    def _left_text(self):
        if not self.hhmm or len(self.hhmm) != 5:
            return tr("due_left_soon"), "#D97036"
        try:
            h, m = self.hhmm.split(":")
            now = dt.datetime.now()
            due = now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
        except Exception:
            return tr("due_left_soon"), "#D97036"
        diff = (due - now).total_seconds()
        if diff < -60:
            # v1.9.9.5：超过 1 小时的用「x小时y分钟」，不再全是干巴巴的分钟数
            mins = int(abs(diff) // 60)
            if mins >= 60:
                return tr("due_over", t=tr("over_hm",
                                           h=mins // 60, m=mins % 60)), "#E2434B"
            return tr("due_over", t=tr("over_min", m=mins)), "#E2434B"
        if diff <= 60:
            return tr("due_left_soon"), "#E2434B"
        mins = int(diff // 60)
        if mins >= 60:
            return tr("due_left_hm", h="%d:%02d" % (mins // 60, mins % 60)), "#D97036"
        return tr("due_left_min", m=mins), "#D97036"

    def refresh(self):
        try:
            self.lbl_name.config(text=self.title)
            txt, col = self._left_text()
            self.lbl_left.config(text="⏳ " + txt, fg=col)
            self.lbl_at.config(text=tr("due_at", d=self.hhmm) if self.hhmm else "")
            self.win.configure(bg=C.LINE)
            self.win.lift()
        except Exception:
            pass

    def _tick(self):
        """自己每秒刷一次剩余时间，到点状态变了就换个颜色"""
        if not self.alive():
            return
        try:
            self.refresh()
        except Exception:
            pass
        try:
            self.win.after(30000, self._tick)     # 30 秒够用，别拿 1 秒去刷
        except Exception:
            pass

    def open_detail(self):
        self.app.open_task_detail(self.tid)
        self.close()

    def close(self):
        try:
            if self.alive():
                self.win.destroy()
        except Exception:
            pass
        try:
            if self in self.app._due_cards:
                self.app._due_cards.remove(self)
        except Exception:
            pass


# ----------------------------------------------------------------- 未完成任务气泡
class Bubble(object):
    """屏幕右下角「未完成任务」气泡（系统时钟上方）。

    平时只显示一个小气泡（图标 + 数量）；点一下在它上方展开
    每个未完成任务的条状气泡（点任务名进详情页），再点合并收回。
    透明度跟随主便签；可在主便签底栏开关。
    """
    W, H = 84, 40

    def __init__(self, app):
        self.app = app
        self.expanded = False
        self._rows = []
        # 大小可拖拽调节（记在 store.bubble_w，60~160px，高度等比）
        self.W = int(getattr(app.store, "bubble_w", 84) or 84)
        self.W = max(60, min(220, self.W))
        self.H = max(28, round(self.W * 40 / 84))
        win = tk.Toplevel(app.root)
        self.win = win
        try:
            win.overrideredirect(True)
        except Exception:
            pass
        win.attributes("-topmost", True)
        win.configure(bg=C.LINE)
        self._apply_alpha()
        self.main = tk.Frame(win, bg=C.BG, highlightthickness=1,
                             highlightbackground=C.LINE)
        self.main.pack(fill="both", expand=True)
        fs_n, fs_t = self._fonts()
        img = app.icon("bubble", "accent")
        self.count_lbl = tk.Label(self.main, text="0", bg=C.BG, fg=C.ACCENT,
                                  font=(app.f_ui, fs_n, "bold"))
        self.count_lbl.pack(side="left", padx=(8, 3), pady=4)
        self.txt_lbl = tk.Label(self.main, text=tr("bubble_left"), bg=C.BG, fg=C.TEXT,
                                font=(app.f_ui, fs_t))
        self.txt_lbl.pack(side="left", padx=(0, 6))
        # 右缘缩放把手：按住左右拖动改变气泡大小
        self.grip = tk.Frame(self.main, bg=C.BG, width=6,
                             cursor="sb_h_double_arrow")
        self.grip.pack(side="right", fill="y")
        self.grip.bind("<Button-1>", self._grip_press)
        self.grip.bind("<B1-Motion>", self._grip_drag)
        self.grip.bind("<ButtonRelease-1>", self._grip_release)
        for w in (self.main, self.count_lbl, self.txt_lbl):
            w.bind("<Button-1>", lambda e: self.toggle())
            w.bind("<Enter>", lambda e: self.main.configure(highlightbackground=C.ACCENT))
            w.bind("<Leave>", lambda e: self.main.configure(highlightbackground=C.LINE))
        if img is not None:
            self.ic_lbl = tk.Label(self.main, image=img, bg=C.BG)
            self.ic_lbl.image = img
            self.ic_lbl.pack(side="right", padx=(0, 4))
            self.ic_lbl.bind("<Button-1>", lambda e: self.toggle())
        self._place()
        self.refresh()

    # ---- 拖拽缩放
    def _grip_press(self, e):
        self._gw = [e.x_root, self.W]

    def _grip_drag(self, e):
        if not getattr(self, "_gw", None):
            return
        dx = e.x_root - self._gw[0]
        self.W = max(60, min(220, self._gw[1] + dx))
        self.H = max(28, round(self.W * 40 / 84))
        self._place()
        if self.expanded:
            self._expand()

    def _grip_release(self, e):
        if getattr(self, "_gw", None):
            self._gw = None
            try:
                self.app.store.bubble_w = int(self.W)
                self.app.store.save()
            except Exception:
                pass

    # ---- 基础
    def alive(self):
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    def _apply_alpha(self):
        try:
            self.win.attributes("-alpha", getattr(self.app.store, "alpha", 0.88))
        except Exception:
            pass

    def _place(self):
        try:
            sw = self.win.winfo_screenwidth()
            sh = self.win.winfo_screenheight()
            x = sw - self.W - 14
            y = sh - self.H - 64          # 系统时钟（任务栏）上方
            self.win.geometry("%dx%d+%d+%d" % (self.W, self.H, max(0, x), max(0, y)))
        except Exception:
            pass

    def _undone(self):
        return [t for t in self.app.store.tasks if not t.get("done")]

    def _ordered(self):
        """气泡展开顺序（v1.9.9）：紧急度优先，同优先级里截止早的在前。

        与主列表的差异：主列表只看时刻（hhmm），气泡是「扫一眼就知道
        先干什么」的提醒工具，所以同分时把带日期且更早到期的排前面；
        完全没有截止信息的压到最后。
        """
        today = self.app.store._today()

        def _key(it):
            i, t = it
            has_dl = bool(t.get("hhmm") or t.get("due_date"))
            dd = t.get("due_date") or (today if t.get("hhmm") else "9999")
            return (-t.get("score", 0), 0 if has_dl else 1,
                    dd, t.get("hhmm") or "99:99", i)

        return [t for _, t in sorted(enumerate(self._undone()), key=_key)]

    def _dl_text(self, t):
        """任务条右侧的截止小字：「M/D HH:MM」；只有日期给「M/D」"""
        hhmm = t.get("hhmm")
        if hhmm:
            try:
                return self.app._tshow(t, hhmm)
            except Exception:
                return hhmm
        dd = t.get("due_date")
        if dd:
            try:
                _y, _m, _d = [int(x) for x in dd.split("-")]
                return "%d/%d" % (_m, _d)
            except Exception:
                return dd
        return ""

    # ---- 尺寸自适应：文本永远显示全（v1.9.3）
    def _fonts(self):
        """气泡字号：跟随「字体大小」滑块"""
        fsc = float(getattr(self.app.store, "font_scale", 1.0) or 1.0)
        return (max(9, round(11 * fsc)), max(7, round(8 * fsc)))

    def _fit(self):
        """按内容计算气泡大小：宽度取「手动拖拽值」与「内容所需」的较大者，
        文本不再截断；高度按字号行高。上限 220px 防止遮屏。
        测宽对象是「当前显示的文本」（v1.9.3 用固定文案，空态长句被截断）"""
        try:
            from tkinter import font as tkfont
            fn, ft = self._fonts()
            f_num = tkfont.Font(font=(self.app.f_ui, fn, "bold"))
            f_txt = tkfont.Font(font=(self.app.f_ui, ft))
            cur = self.txt_lbl.cget("text") or tr("bubble_left")
            num = self.count_lbl.cget("text") or ""
            need = (f_num.measure(num or "0") + f_txt.measure(cur)
                    + 56)          # 边距 + 缩放把手 + 图标位（留余量防字体差异）
            base = int(getattr(self.app.store, "bubble_w", 84) or 84)
            self.W = max(60, min(240, max(base, need)))
            self.H = max(28, f_txt.metrics("linespace") + 12)
        except Exception:
            self.W = max(60, min(220, self.W))
            self.H = max(28, round(self.W * 40 / 84))
        self._place()

    def refresh(self):
        """未完成数量变化后更新主气泡；展开态重建任务条"""
        if not self.alive():
            return
        try:
            fn, ft = self._fonts()
            self.count_lbl.config(font=(self.app.f_ui, fn, "bold"))
            self.txt_lbl.config(font=(self.app.f_ui, ft))
        except Exception:
            pass
        undone = self._undone()
        try:
            # 先定文本，再测宽 —— v1.9.4 顺序反了，测的还是上一次的文案，
            # 空态（长句）因此按旧文本算宽度被截断（v1.9.5 修复）
            if undone:
                self.count_lbl.config(text=str(len(undone)))
                if not self.count_lbl.winfo_ismapped():
                    self.count_lbl.pack(side="left", padx=(8, 3), pady=4,
                                        before=self.txt_lbl)
                self.txt_lbl.config(text=tr("bubble_left"))
            else:
                self.count_lbl.pack_forget()      # 空态不显示「0」
                self.txt_lbl.config(text=tr("bubble_none"))
            self._apply_alpha()
        except Exception:
            pass
        self._fit()       # 文本就位后再按实际内容算宽度
        if self.expanded:
            self._expand()
        else:
            self._collapse()

    def toggle(self):
        self.expanded = not self.expanded
        if self.expanded:
            self._expand()
        else:
            self._collapse()

    def _collapse(self):
        for r in self._rows:
            try:
                if r.winfo_exists():
                    r.destroy()
            except Exception:
                pass
        self._rows = []

    def _expand(self):
        self._collapse()
        undone = self._ordered()      # v1.9.9：紧急优先、同分先到期在前
        if not undone:
            return
        # 任务条：放在主气泡上方逐个排列（宽度按字号实测，文本不截断）
        base_x = self.win.winfo_x()
        base_y = self.win.winfo_y()
        fsc = float(getattr(self.app.store, "font_scale", 1.0) or 1.0)
        f_row = None
        try:
            from tkinter import font as tkfont
            # v1.9.9.7：字体对象缓存复用——之前每次展开都新建 tkfont.Font，
            # 关闭时成堆的 Tcl 字体对象销毁是「alloc: invalid block」的诱因之一
            key = max(8, round(9 * fsc))
            f_row = getattr(self, "_row_font", None)
            if f_row is None or getattr(self, "_row_font_size", None) != key:
                f_row = self._row_font = tkfont.Font(
                    font=(self.app.f_ui, key))
                self._row_font_size = key
        except Exception:
            f_row = None

        def _need(t):
            """v1.9.9.13：单行「内容净宽」= 色条3 + 标题padx16 + 标题宽
            + (间隔·+时间宽) —— 不再带 56px 基线和 20px 富余，
            中缝压缩到固定 8px。"""
            dl = self._dl_text(t)
            if f_row is not None:
                extra = (f_row.measure("· " + dl) + 8) if dl else 0
                tw = f_row.measure(t["title"])
            else:
                extra = (len(dl) * round(7 * fsc) + 8) if dl else 0
                tw = len(t["title"]) * round(13 * fsc)
            return 27 + tw + extra

        # v1.9.9.13：先对全部行预计算，取最大值作为统一宽度——
        # 所有行左右边缘对齐；最长行超 460 时截它的标题，其余行跟随
        rows_data = undone[:8]      # 最多铺 8 条，多了显示省略
        needs = [_need(t) for t in rows_data]
        uni_w = max(needs) if needs else 120
        _capped = uni_w > 460
        uni_w = max(120, min(460, uni_w))
        for i, t in enumerate(rows_data):
            disp = t["title"]
            try:
                if _capped and f_row is not None \
                        and needs[i] > 460:
                    _cap = 460 - 27 - (needs[i] - 27
                                       - (f_row.measure(t["title"])
                                          if f_row is not None else 0))
                    disp = self.app.ellipsize(disp, f_row, max(40, _cap))
            except Exception:
                pass
            h = max(26, round(30 * fsc))
            y = base_y - (i + 1) * (h + 6) - 6
            row = tk.Toplevel(self.app.root)
            try:
                row.overrideredirect(True)
                row.attributes("-topmost", True)
                row.attributes("-alpha", getattr(self.app.store, "alpha", 0.88))
            except Exception:
                pass
            row.configure(bg=C.LINE)
            inner = tk.Frame(row, bg=C.ROW2, highlightthickness=1,
                             highlightbackground=C.LINE)
            inner.pack(fill="both", expand=True, padx=1, pady=1)
            # v1.9.9：色条跟主列表同一套优先级色（紧急红/重要橙/一般蓝/不急灰）
            _plabel, pcolor = core.priority_label(t.get("score", 0))
            dot = tk.Frame(inner, bg=pcolor, width=3)
            dot.pack(side="left", fill="y")
            lbl = tk.Label(inner, text=disp, bg=C.ROW2, fg=C.TEXT,
                           font=self.app.f_small, anchor="w", padx=8)
            lbl.pack(side="left", fill="x", expand=True)
            # 截止时间小字（右侧，弱色）：没有截止信息的任务不显示；
            # 已过期的用红色提醒（v1.9.9）
            dl = self._dl_text(t)
            if dl:
                expired = False
                try:
                    expired = bool(self.app._is_expired(t.get("hhmm"),
                                                        t.get("due_date")))
                except Exception:
                    expired = False
                dlc_lbl = tk.Label(inner, text="· " + dl, bg=C.ROW2,
                                   fg="#E2434B" if expired else C.SUB,
                                   font=self.app.f_small, anchor="e",
                                   padx=2)
                dlc_lbl.pack(side="right", padx=(0, 8))
                dlc_lbl.bind("<Button-1>",
                             lambda e, tid=t["id"]: self._open(tid))
            for ww in (inner, lbl):
                ww.bind("<Button-1>", lambda e, tid=t["id"]: self._open(tid))
            try:
                # v1.9.9.7：任务条右对齐气泡右缘，并夹在屏幕内——
                # 之前以气泡左缘为起点向右铺，条一宽右半截就出屏了
                # v1.9.9.13：rw 用统一宽度 uni_w（预计算好的最宽行），
                # 不再逐行独立；+6 为外框余量
                rw = uni_w + 6
                _sw = row.winfo_screenwidth()
                rx = base_x + self.win.winfo_width() - rw
                rx = max(8, min(rx, _sw - rw - 8))
                row.geometry("%dx%d+%d+%d" % (rw, h, rx, max(0, y)))
            except Exception:
                pass
            self._rows.append(row)
        try:
            self.win.attributes("-topmost", True)
            self.win.lift()
        except Exception:
            pass

    def _open(self, tid):
        self.expanded = False
        self._collapse()
        self.app.open_task_detail(tid)

    def close(self):
        self._collapse()
        try:
            if self.alive():
                self.win.destroy()
        except Exception:
            pass


# ----------------------------------------------------------------- 主窗口
class NoteApp(object):

    def __init__(self, root):
        self.root = root
        self.store = Store()
        self.overlay = False
        self._drag = None
        self._resizing = None
        self._edit_id = None
        self._compose_placeholder = True
        self._hist_win = None
        self._bar_tip = ""
        self._theme_win = None
        self._alpha_panel = None
        self._unbind_alpha_away = lambda: None
        self._due_cards = []       # 右下角截止提醒卡片
        self._edit_entry = None    # 当前正在编辑标题的 Entry
        self._bubble = None        # 右下角「未完成任务」气泡
        self._undo_last = None     # 最近一次可撤回的操作（v1.9.5）
        self._pending_q = None     # 当前在等回答的是哪个追问（v1.9.5）
        self._font_cache = {}
        self._width_cache = {}
        self._charw_cache = {}
        self._avg_cache = {}

        # 语言与主题先就位，后面所有控件才用对文案和颜色
        i18n.set_lang(self.store.lang)
        C.set_theme(palette.get(self.store.theme))
        self.decks = quotebox.DeckSet()
        for lang in ("zh", "en"):
            st = self.store.q_state(lang)
            self.decks.seed_recent(lang, st.get("recent", [])[-20:])

        self.setup_window()
        self.setup_fonts()
        self.build_ui()
        self.refresh_tasks(scroll_top=True)
        self.render_messages()
        self.restore_quote()

        if self.store.topmost:
            self.root.attributes("-topmost", True)

        self.placeholder_tick()
        # 启动后把键盘焦点直接给输入框：用户打开便签就能打字，
        # 不用先点一下（无边框窗口默认不抢焦点，这点很容易被当成「打不了字」）
        self.root.after(60, self._grab_focus)
        self.root.after(240, self._first_hello)
        # 右下角「未完成任务」气泡（可在底栏开关）
        if getattr(self.store, "bubble_enabled", True):
            self.root.after(600, self._ensure_bubble)
        # 编辑标题时的全局点击兜底（收起悬空的编辑框）——走常驻路由器，
        # 避免被其他面板的 unbind_all 误杀
        self._hook_click("edit_outside", self._global_edit_click)

    def _ensure_bubble(self):
        """确保右下角气泡存在（开关打开且窗口还在）"""
        if not getattr(self.store, "bubble_enabled", True):
            return
        b = getattr(self, "_bubble", None)
        if b is not None and b.alive():
            try:
                b.refresh()
            except Exception:
                pass
            return
        try:
            self._bubble = Bubble(self)
        except Exception:
            self._bubble = None

    def toggle_bubble(self):
        self.store.bubble_enabled = not getattr(self.store, "bubble_enabled", True)
        self.store.save()
        if self.store.bubble_enabled:
            self._ensure_bubble()
            self.flash(tr("bubble_on"))
        else:
            b = getattr(self, "_bubble", None)
            if b is not None:
                b.close()
                self._bubble = None
            self.flash(tr("bubble_off"))

    def _first_hello(self):
        """开场白：首次启动只问称呼；之后每天一句轮换问候（不重复、循环）"""
        try:
            # 数据目录不可写时明确告知（否则重启后任务全丢，用户毫无头绪）
            if getattr(Store, "_save_error", None):
                self.push_tr("bot", "save_warn")
            stage = int(getattr(self.store, "setup_stage", 0) or 0)
            nm = getattr(self.store, "user_name", "")
            if stage == 0:
                # 第一次见面：只问称呼，不带「新的一天」——那句留给以后每天开场
                self.push_tr("bot", "ask_user_name")
                self.store.setup_stage = 1
                self.store.save()
            elif stage >= 3 and nm:
                # 每日问候：按「今天的序号」取池子里一句 → 同一天不换，
                # 跨天换下一句，10 句一轮不重样
                cur, dual = self._daily_greet_dual()
                self.push("bot", cur, dual=dual)
        except Exception:
            pass

    def icon(self, name, shade="text"):
        """取当前主题下的 SVG 图标 PhotoImage（预渲染 PNG）"""
        return IconCache.get(name, shade, theme=self.store.theme, owner=self.root)

    def _grab_focus(self):
        try:
            self.root.focus_force()
            self.entry.focus_set()
            self._activate_window()
            self.diag("启动取焦点完成 focus=%s" % self.root.focus_get())
        except Exception:
            pass
        # 记录运行环境，便于诊断 Windows 上的问题
        self.diag("== 启动 v%s | 目录=%s | 可写=%s ==" % (
            VERSION, data_dir(),
            os.access(data_dir(), os.W_OK)))

    def _activate_window(self, focus_entry=True):
        """Windows：无边框窗口拿不到系统级键盘焦点 → 光标不显示、退格失效。
        用 Win32 API 直接把窗口带到前台并设为活动窗口。
        focus_entry=False 时不抢主输入框焦点（行内编辑标题时用，v1.9.7：
        之前编辑框刚拿到焦点就被这里 focus_force 抢走，打的字一半进了
        编辑框一半漏进发送框）。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.SetFocus(hwnd)
            self.root.lift()
            if focus_entry:
                self.entry.focus_force()
        except Exception:
            pass

    def _fix_win11_corner(self):
        """Windows 11：无边框窗口被系统强制圆角（Win11 的 DWM 对所有窗口生效），
        圆角裁掉直角的标题栏后，两角会露出底色浅块（用户反馈的「左右两个小方块」）。
        用 DwmSetWindowAttribute 把圆角偏好设为 DONOTROUND(1)，两角即可正常填充。"""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            from ctypes import wintypes

            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id())
            if not hwnd:
                hwnd = self.root.winfo_id()
            # DWMWA_WINDOW_CORNER_PREFERENCE = 33
            #   0=系统默认 1=不圆角 2=圆角 3=小圆角
            pref = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass

    def _key_fallback(self, e):
        """焦点不在输入框时，把打字/编辑键转交过去（解决无边框窗口吃键盘焦点的问题）。
        路由后立即把焦点真正交给输入框——这样光标会出现，后续按键走原生路径，
        可以正常点击定位、选择、退格。"""
        w = self.root.focus_get()
        # v1.9.9.2 修复：行内编辑待办/便签时打字被劫进发送框。
        # 旧判断 str(w).endswith("entry") 只救得了路径恰好叫 entry 的输入框；
        # 行内编辑框是第 N 个 Entry，路径是 !entry2/!entry3…，判断失效后
        # 每个按键都被这里转交发送框并 focus_force 抢走焦点。
        # 现在凡是原生就能处理键盘的控件（Entry/Text/Spinbox/Combobox）一律放行。
        if w is not None and isinstance(
                w, (tk.Entry, tk.Text, tk.Spinbox, ttk.Combobox)):
            return
        if w is self.entry:
            return
        ch = getattr(e, "char", "") or ""
        ks = getattr(e, "keysym", "") or ""
        if self._compose_placeholder and (ch.isprintable() and ch.strip()):
            self.clear_placeholder()
        try:
            if ks == "BackSpace":
                n = len(self.entry.get())
                self.entry.delete(n - 1, "end") if n else None
            elif ks == "Delete":
                i = self.entry.index("insert")
                self.entry.delete(i, min(i + 1, len(self.entry.get()))) \
                    if i < len(self.entry.get()) else None
            elif ks == "Return" or ks == "KP_Enter":
                self.on_send()
            elif ks == "Home":
                self.entry.icursor(0)
            elif ks == "End":
                self.entry.icursor("end")
            elif ks == "Left":
                self.entry.icursor(max(0, self.entry.index("insert") - 1))
            elif ks == "Right":
                self.entry.icursor(min(len(self.entry.get()), self.entry.index("insert") + 1))
            elif ch and ch.isprintable():
                self.entry.insert("insert", ch)
            else:
                return
            # 关键：把焦点真正交给输入框，光标从此显示，后续按键走原生处理
            self.entry.focus_force()
            self.diag("按键兜底路由 %s" % ks)
        except Exception:
            pass
        return "break"

    # ---------------- 窗口
    def setup_window(self):
        r = self.root
        r.title(self.app_name() + "  v" + VERSION)
        r.configure(bg=C.BG)
        r.overrideredirect(True)          # 无边框，像便签
        r.attributes("-alpha", getattr(self.store, "alpha", 0.88))  # 半透明：可调
        # 文字加深：手动滑块优先；没动过就按透明度推导
        C.set_darken(self._effective_darken())
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        w = int(sw / 6)
        h = int(sh / 3)
        w = max(250, min(w, 460))
        h = max(150, min(h, 340))
        x = sw - w - int(sw * 0.012)
        y = int(sh * 0.055)
        # 恢复上次关闭前的位置和大小
        saved = getattr(self.store, "note_geom", None) or (
            "%d,%d" % (x, y) if getattr(self.store, "note_pos", None) is None
            else self.store.note_pos)
        try:
            parts = str(saved).replace("x", "+").split("+")
            if len(parts) == 4:
                sw_, sh_, sx, sy = [int(v) for v in parts]
                w = max(250, min(sw_, sw - 40))
                h = max(150, min(sh_, sh - 60))
                if -sw < sx < sw and -sh < sy < sh:
                    x, y = sx, sy
            else:
                sx, sy = [int(v) for v in parts[:2]]
                if -sw < sx < sw and -sh < sy < sh:
                    x, y = sx, sy
        except Exception:
            pass
        # v1.9.9.7：窗口整体夹回屏幕内——之前位置可以漂到右缘外，
        # 底栏最右侧的时钟按钮会被屏幕边缘切掉
        x = max(8, min(x, sw - w - 8))
        y = max(8, min(y, sh - h - 40))
        r.geometry("%dx%d+%d+%d" % (w, h, x, y))
        r.minsize(250, 150)
        r.protocol("WM_DELETE_WINDOW", self.quit)
        # v1.9.9.3：源码运行时窗口/任务栏分组也用新图标
        # （打包版的 exe 图标由 PyInstaller 编进 exe，见 每日记事本.spec）
        try:
            _icp = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "assets", "icon.png")
            if os.path.exists(_icp):
                self._icon_img = tk.PhotoImage(file=_icp)
                r.iconphoto(True, self._icon_img)
        except Exception:
            pass
        # v1.9.9.8：Windows 下用 ico 再设一次——任务栏分组图标以它为准
        # （打包版的 exe 图标由 PyInstaller 编进 exe，见 每日记事本.spec）
        if os.name == "nt":
            try:
                _ici = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "assets", "icon.ico")
                if os.path.exists(_ici):
                    r.iconbitmap(_ici)
            except Exception:
                pass
        # （按用户要求恢复旧形式：不在任务栏单独显示）
        # Win11 会把无边框窗口也裁成圆角，露出标题栏两角的浅色块 → 关掉圆角
        r.update_idletasks()
        self._fix_win11_corner()

    def _save_note_pos(self):
        """记住主窗口的位置 + 大小"""
        try:
            self.store.note_geom = "%dx%d+%d+%d" % (
                self.root.winfo_width(), self.root.winfo_height(),
                self.root.winfo_x(), self.root.winfo_y())
            self.store.save()
        except Exception:
            pass

    def setup_fonts(self):
        fams = set(tkfont.families())

        def pick(cands, default):
            for c in cands:
                if c in fams:
                    return c
            return default

        self.f_ui = pick(["微软雅黑", "Microsoft YaHei", "Noto Sans CJK SC",
                          "Source Han Sans SC", "PingFang SC", "WenQuanYi Micro Hei"],
                         "TkDefaultFont")
        self._build_fonts()

    def _build_fonts(self):
        """按 store.font_scale（0.8~1.3）构建各处字号；字体大小滑块实时调用"""
        sc = float(getattr(self.store, "font_scale", 1.0) or 1.0)
        self.f_task = (self.f_ui, max(8, round(10 * sc)))
        self.f_small = (self.f_ui, max(7, round(8 * sc)))
        self.f_tiny = (self.f_ui, max(6, round(7 * sc)))
        self.f_chat = (self.f_ui, max(8, round(9 * sc)))

    # ---------------- 骨架
    def build_ui(self):
        r = self.root
        # 哲言行（最底一行：日期靠左 + 哲言靠右，同一行 v1.9.3）
        self.quote_row = tk.Frame(r, bg=C.BG, height=18)
        self.quote_row.pack(side="bottom", fill="x", padx=10, pady=(0, 1))
        self.f_note = tk.Label(self.quote_row, text=self.today_text(),
                               bg=C.BG, fg=C.SUB, font=self.f_tiny, anchor="w")
        self.f_note.pack(side="left")
        self.quote_lbl = tk.Label(self.quote_row, text="", bg=C.BG, fg=C.SUB,
                                  font=(self.f_ui, 8), anchor="e", justify="right",
                                  wraplength=300)
        self.quote_lbl.pack(side="right", fill="x", expand=True)
        self.quote_row.bind("<Button-1>", lambda e: self.roll_quote(manual=True))
        self.quote_lbl.bind("<Button-1>", lambda e: self.roll_quote(manual=True))
        self.quote_lbl.bind("<Enter>", lambda e: self.quote_lbl.config(fg=C.ACCENT))
        self.quote_lbl.bind("<Leave>", lambda e: self.quote_lbl.config(fg=C.SUB))

        # 托盘按钮（纯功能键，不再放日期）
        self.foot = tk.Frame(r, bg=C.BG, height=16)
        self.foot.pack(side="bottom", fill="x", padx=8, pady=(0, 2))
        # 互动提示：悬浮在功能栏上方（place 浮层，不占功能栏的空间）
        self.f_hint = tk.Label(r, text="", bg=C.HEAD, fg=C.TEXT, font=self.f_tiny,
                               padx=6, pady=1)
        self.f_hint.place(relx=1.0, rely=1.0, x=-6, y=-40, anchor="se")
        self.f_hint.lift()
        self.clock_btn = tk.Label(self.foot, text=tr("clock_btn"), bg=C.BG, fg=C.SUB,
                                  font=self.f_tiny, cursor="hand2", padx=4)
        self.clock_btn.pack(side="right")
        self.clock_btn.bind("<Button-1>", lambda e: self.open_clock())
        self.clock_btn.bind("<Enter>", lambda e: self.clock_btn.config(fg=C.ACCENT))
        self.clock_btn.bind("<Leave>", lambda e: self.clock_btn.config(fg=C.SUB))
        # 底栏纯文本按钮（按需求去掉图标）
        self.cal_btn = tk.Label(self.foot, text=tr("cal_btn"), bg=C.BG, fg=C.SUB,
                                font=self.f_tiny, cursor="hand2", padx=4)
        self.cal_btn.pack(side="right", padx=(0, 10))
        self.cal_btn.bind("<Button-1>", lambda e: self.open_calendar_view())
        self.cal_btn.bind("<Enter>", lambda e: self.cal_btn.config(fg=C.ACCENT))
        self.cal_btn.bind("<Leave>", lambda e: self.cal_btn.config(fg=C.SUB))
        self.hist_btn = tk.Label(self.foot, text=tr("history_btn"), bg=C.BG, fg=C.SUB,
                                 font=self.f_tiny, cursor="hand2", padx=4)
        self.hist_btn.pack(side="right", padx=(0, 8))
        self.hist_btn.bind("<Button-1>", lambda e: self.open_history())
        self.hist_btn.bind("<Enter>", lambda e: self.hist_btn.config(fg=C.ACCENT))
        self.hist_btn.bind("<Leave>", lambda e: self.hist_btn.config(fg=C.SUB))
        self.alpha_btn = tk.Label(self.foot, text=tr("alpha_btn"), bg=C.BG, fg=C.SUB,
                                  font=self.f_tiny, cursor="hand2", padx=4)
        self.alpha_btn.pack(side="right", padx=(0, 6))
        self.alpha_btn.bind("<Button-1>", lambda e: self.toggle_alpha_panel())
        self.alpha_btn.bind("<Enter>", lambda e: self.alpha_btn.config(fg=C.ACCENT))
        self.alpha_btn.bind("<Leave>", lambda e: self.alpha_btn.config(fg=C.SUB))
        self.bubble_btn = tk.Label(self.foot, text=tr("bubble_btn"), bg=C.BG,
                                   fg=C.ACCENT if getattr(self.store, "bubble_enabled", True) else C.SUB,
                                   font=self.f_tiny, cursor="hand2", padx=4)
        self.bubble_btn.pack(side="right", padx=(0, 8))
        self.bubble_btn.bind("<Button-1>", lambda e: self.toggle_bubble())
        self.bubble_btn.bind("<Enter>", lambda e: self.bubble_btn.config(fg=C.ACCENT))
        self.bubble_btn.bind("<Leave>", lambda e: self.bubble_btn.config(
            fg=C.ACCENT if getattr(self.store, "bubble_enabled", True) else C.SUB))

        # 标题栏
        self.head = Canvas(r, height=28)
        self.head.pack(side="top", fill="x")
        self.head.bind("<Configure>", lambda e: self.debounce("head", self.draw_head))
        # 启动时立即画一次：之前只靠 <Configure> 的 debounce，而事件循环起来后
        # Configure 往往不再触发，标题栏一直是空画布（v1.9.6 发现）
        self.head.after(30, self.draw_head)
        self.head.bind("<Button-1>", self.on_head_press)
        self.head.bind("<B1-Motion>", self.on_drag)
        self.head.bind("<ButtonRelease-1>", lambda e: setattr(self, "_drag", None))
        # v1.9.4：删除「双击标题栏收起便签」手势 —— 双击会与连点其他按钮
        # （如中英转换）叠加误触收起功能，用户要求功能独立

        # 进度条（标题栏正下方，最顶部）
        self.bar = Canvas(r, height=26)
        self.bar.pack(side="top", fill="x")
        self.bar.bind("<Configure>", lambda e: self.debounce("bar", self.draw_bar))
        self.bar.bind("<Button-1>", lambda e: self.flash(self._bar_tip))

        # 四边 + 四角缩放：v1.9.7 起改用「坐标判断」而不是热区 Frame。
        # 之前 10px 热区浮在最上层，顶热区盖掉标题栏文字上半、底热区盖掉
        # 日期行、右热区吃掉勾选框的点击 —— 就是「内容显示不全」「方框点不动」
        # 的根因。坐标法不遮挡任何内容，四边四角照样能拉。
        # 原理：按下时看坐标落在不在边缘 10px / 角 18px 内，是则进入缩放。
        self.grip = tk.Frame(r, bg=C.BG, height=1)
        self.grip.pack(side="bottom", fill="x")   # 保留占位，避免历史代码报错
        self._edges = []                          # 兼容旧引用（不再创建浮层）
        r.bind("<Button-1>", self._edge_probe, add="+")
        r.bind("<B1-Motion>", self._edge_motion, add="+")
        r.bind("<ButtonRelease-1>", self._edge_up, add="+")
        r.bind("<Motion>", self._edge_cursor, add="+")

        # 聊天区（顶部）
        self.chat_wrap = tk.Frame(r, bg=C.BG)
        self.chat_wrap.pack(side="top", fill="x")
        self.list_mode = "task"          # task=待办 / note=便签
        self.chat_h = int(getattr(self.store, "chat_h", None) or 96)
        self.chat_cv = Canvas(self.chat_wrap, height=self.chat_h)
        self.chat_cv.pack(side="top", fill="both")
        self.chat_cv.bind("<Configure>", lambda e: self.debounce("chat", self.render_messages))
        self.chat_cv.bind("<MouseWheel>", self.on_chat_wheel)
        self.chat_cv.bind("<Button-4>", lambda e: self.on_chat_wheel(e, -1))
        self.chat_cv.bind("<Button-5>", lambda e: self.on_chat_wheel(e, 1))

        # 输入行
        self.input_row = tk.Frame(r, bg=C.BG)
        self.input_row.pack(side="top", fill="x", padx=6, pady=(2, 4))
        self.entry = tk.Entry(self.input_row, relief="flat", bd=0, bg=C.INPUT_BG,
                              fg=C.TEXT, insertbackground=C.TEXT, font=self.f_chat,
                              highlightthickness=1, highlightbackground=C.INPUT_LINE,
                              highlightcolor=C.ACCENT)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry.bind("<Return>", lambda e: self.on_send())
        self.entry.bind("<KP_Enter>", lambda e: self.on_send())
        self.entry.bind("<FocusIn>", self.clear_placeholder)
        self.entry.bind("<FocusOut>", self.restore_placeholder)
        # 无边框窗口下点击不一定把键盘焦点交给输入框，这里显式要一次
        self.entry.bind("<Button-1>", lambda e: (self.diag("entry 点击取焦点"),
                                                 self._activate_window()))
        # Windows 兜底：只要焦点不在输入框，任何可见字符都转交给输入框
        self.root.bind("<Key>", self._key_fallback)
        self.entry.bind("<Escape>", lambda e: self.root.focus_set())
        self.send_btn = tk.Label(self.input_row, text=tr("send"), bg=C.ACCENT, fg="white",
                                 font=self.f_small, padx=7, pady=3, cursor="hand2")
        self.send_btn.pack(side="left", padx=(4, 0))
        self.send_btn.bind("<Button-1>", lambda e: self.on_send())

        # 可拖动分隔条：上下拖动调整聊天区高度
        self.splitter = tk.Frame(r, bg=C.SPLIT, height=4,
                                 cursor="sb_v_double_arrow")
        self.splitter.pack(side="top", fill="x")
        self.splitter.bind("<Button-1>", self.on_split_press)
        self.splitter.bind("<B1-Motion>", self.on_split_drag)
        self.splitter.bind("<ButtonRelease-1>", self.on_split_release)

        # 任务区标题
        self.list_head = tk.Frame(r, bg=C.BG, height=18)
        self.list_head.pack(side="top", fill="x", padx=8)
        self.tab_todo = tk.Label(self.list_head, text=tr("tab_todo"), bg=C.BG,
                                 fg=C.ACCENT, font=self.f_tiny, cursor="hand2")
        self.tab_todo.pack(side="left")
        self.tab_note = tk.Label(self.list_head, text=tr("tab_note"), bg=C.BG,
                                 fg=C.SUB, font=self.f_tiny, cursor="hand2")
        self.tab_note.pack(side="left", padx=(8, 0))
        self.tab_todo.bind("<Button-1>", lambda e: self.switch_mode("task"))
        self.tab_note.bind("<Button-1>", lambda e: self.switch_mode("note"))
        self.counter = tk.Label(self.list_head, text="", bg=C.BG, fg=C.SUB,
                                font=self.f_tiny, anchor="w")
        self.counter.pack(side="left", padx=(10, 0))
        self.clear_btn = tk.Label(self.list_head, text=tr("clear_done"), bg=C.BG, fg=C.SUB,
                                  font=self.f_tiny, cursor="hand2")
        self.clear_btn.pack(side="right")
        self.clear_btn.bind("<Button-1>", lambda e: self.clear_done())

        # 任务列表（Canvas + 滚轮）
        self.list_wrap = tk.Frame(r, bg=C.BG)
        self.list_wrap.pack(side="top", fill="both", expand=True)
        self.list_cv = Canvas(self.list_wrap)
        self.list_cv.pack(side="top", fill="both", expand=True)
        self.list_cv.bind("<Configure>", lambda e: self.debounce("list", self.refresh_tasks))
        self.list_cv.bind("<MouseWheel>", self.on_list_wheel)
        self.list_cv.bind("<Button-4>", lambda e: self.on_list_wheel(e, -1))
        self.list_cv.bind("<Button-5>", lambda e: self.on_list_wheel(e, 1))

        # v1.9.9.2 关键修复：这里必须 add="+"。之前直接覆盖，把上面刚注册的
        # _edge_probe/_edge_motion/_edge_up/_edge_cursor 四个缩放绑定全部抹掉，
        # 表现就是「主窗口怎么都拉不动」。lambda 里顺手放过边缘命中：正在
        # 缩放时不用再抢焦点。
        for w in (r, self.chat_wrap):
            w.bind("<Button-1>", lambda e: None if getattr(self, "_edge", None)
                   else self.root.focus_set(), add="+")
        # v1.9.9.7：底栏宽度不够时自动换短标签（英文 Clock/Calendar/… 很长，
        # 窄窗口或调大字体时 Clock 会被截成「Clou」）
        self.foot.bind("<Configure>",
                       lambda e: self.debounce("foot", self._fit_foot))

    # ---------------- 标题栏绘制
    def _fit_foot(self):
        """底栏放不下完整按钮文字时，自动降级为短标签"""
        w = self.foot.winfo_width()
        if w < 40:
            return
        pairs = [
            (self.clock_btn, "clock_btn", "clock_btn"),   # Clock 已是最短
            (self.cal_btn, "cal_btn", "cal_btn_s"),
            (self.hist_btn, "history_btn", "hist_btn_s"),
            (self.alpha_btn, "alpha_btn", "alpha_btn_s"),
            (self.bubble_btn, "bubble_btn", "bubble_btn_s"),
        ]

        def total(full):
            s = 46.0                       # 各 padx 间距 + 框架边距
            for _lbl, k, ks in pairs:
                s += self.text_width(tr(k if full else ks), self.f_tiny) + 8
            return s

        short = total(True) > w - 8
        for lbl, k, ks in pairs:
            want = tr(ks if short else k)
            try:
                if lbl.cget("text") != want:
                    lbl.config(text=want)
            except Exception:
                pass

    def draw_head(self):
        cv = self.head
        cv.delete("all")
        w = max(cv.winfo_width(), 10)
        h = 28
        cv.create_rectangle(0, 0, w, h, fill=C.HEAD, outline="")
        # 品牌：纯文字，顶格靠左（v1.9.3 按需求去掉图标）
        cv.create_text(8, h // 2, text=self.app_name(), anchor="w",
                       font=(self.f_ui, 9, "bold"), fill=C.TEXT)
        # 右侧按钮（从右往左）
        bx = w - 14
        self._btn_close(bx, h // 2, self.quit, "#B4463C")
        bx -= 22
        self._btn_line(bx, h // 2, self.minimize, C.TEXT)
        bx -= 22
        self._btn_pin(bx, h // 2, self.store.topmost, self.toggle_top, C.TEXT)
        bx -= 22
        self._btn_panel(bx, h // 2, self.overlay, self.toggle_overlay, C.TEXT)
        bx -= 22
        self._btn_palette(bx, h // 2, self.open_palette, C.TEXT)
        bx -= 24
        self._btn_lang(bx, h // 2, C.TEXT)

    def _btn_lang(self, x, y, color):
        """语言按钮：显示当前语言可切换到的目标（中 / EN）"""
        cv = self.head
        label = "EN" if not i18n.is_en() else "中"
        txt = cv.create_text(x, y, text=label, anchor="center",
                             font=(self.f_ui, 8, "bold"), fill=color)
        box = cv.create_rectangle(x - 9, y - 7, x + 9, y + 7,
                                  outline=color, width=1, fill=C.HEAD)
        cv.tag_lower(box, txt)           # 框垫在文字下：不透明挡穿透、不遮字
        cv.tag_bind(txt, "<Button-1>", lambda e: self.toggle_lang())
        cv.tag_bind(box, "<Button-1>", lambda e: self.toggle_lang())
        cv.tag_bind(box, "<Enter>", lambda e: [cv.itemconfigure(box, outline=C.ACCENT),
                                               cv.itemconfigure(txt, fill=C.ACCENT)])
        cv.tag_bind(box, "<Leave>", lambda e: [cv.itemconfigure(box, outline=color),
                                               cv.itemconfigure(txt, fill=color)])

    def _logo(self, cv, x, y):
        """便签小图标：SVG 记事本图标；无图标退回自绘"""
        img = self.icon("note", "text")
        if img is not None:
            cv.create_image(x + 6, y, image=img)
            return
        cv.create_polygon(x - 5, y - 5, x + 5, y - 5, x + 5, y + 2, x + 2, y + 5,
                          x - 5, y + 5, fill=C.BG, outline=C.TEXT, width=1)
        cv.create_line(x + 5, y + 2, x + 2, y + 5, fill=C.TEXT, width=1)
        cv.create_line(x - 2.5, y - 1, x + 2.5, y - 1, fill=C.SUB, width=1)

    def _hot(self, items, cmd):
        """给一组画布元素挂上点击"""
        cv = self.head
        for it in items:
            cv.tag_bind(it, "<Button-1>", lambda e, c=cmd: c())

    def _btn_close(self, x, y, cmd, color):
        cv = self.head
        a = 4
        l1 = cv.create_line(x - a, y - a, x + a, y + a, fill=color, width=1.5)
        l2 = cv.create_line(x + a, y - a, x - a, y + a, fill=color, width=1.5)
        hit = cv.create_rectangle(x - 8, y - 8, x + 8, y + 8, outline="", fill=C.HEAD)
        cv.tag_lower(hit, l1)            # 热区垫在图形下面：既挡穿透又不遮图形
        self._hot([l1, l2, hit], cmd)
        cv.tag_bind(hit, "<Enter>", lambda e: [cv.itemconfigure(l1, fill=C.ACCENT),
                                               cv.itemconfigure(l2, fill=C.ACCENT)])
        cv.tag_bind(hit, "<Leave>", lambda e: [cv.itemconfigure(l1, fill=color),
                                               cv.itemconfigure(l2, fill=color)])

    def _btn_line(self, x, y, cmd, color):
        cv = self.head
        ln = cv.create_line(x - 4, y, x + 4, y, fill=color, width=1.5)
        hit = cv.create_rectangle(x - 8, y - 8, x + 8, y + 8, outline="", fill=C.HEAD)
        cv.tag_lower(hit, ln)
        cv.tag_bind(ln, "<Button-1>", lambda e, c=cmd: c())
        cv.tag_bind(hit, "<Button-1>", lambda e, c=cmd: c())
        cv.tag_bind(hit, "<Enter>", lambda e: cv.itemconfigure(ln, fill=C.ACCENT))
        cv.tag_bind(hit, "<Leave>", lambda e: cv.itemconfigure(ln, fill=color))

    def _btn_pin(self, x, y, pinned, cmd, color):
        """图钉：置顶=深色实心；未置顶=更浅的淡色（v1.9.5 拉开区分度）"""
        cv = self.head
        if pinned:
            img = self.icon("pin", "text")
        else:
            img = self.icon("pin", "faint") or self.icon("pin", "sub")
        if img is not None:
            hit = cv.create_image(x, y, image=img)
            self._hot([hit], cmd)
            cv.tag_bind(hit, "<Enter>", lambda e: self._head_img(
                hit, "pin", "accent"))
            cv.tag_bind(hit, "<Leave>", lambda e: self._head_img(
                hit, "pin", "text" if pinned else "faint"))
            return
        items = []
        if pinned:
            # 实心图钉：圆头 + 针尖
            items.append(cv.create_oval(x - 4, y - 5, x + 4, y + 1, fill=color, outline=color))
            items.append(cv.create_polygon(x - 1.5, y + 1, x + 1.5, y + 1, x, y + 6,
                                           fill=color, outline=color))
        else:
            items.append(cv.create_oval(x - 4, y - 5, x + 4, y + 1, fill="", outline=color, width=1.2))
            items.append(cv.create_line(x, y + 1, x, y + 6, fill=color, width=1.2))
        hit = cv.create_rectangle(x - 8, y - 8, x + 8, y + 8, outline="", fill=C.HEAD)
        cv.tag_lower(hit, items[0])
        self._hot(items + [hit], cmd)
        cv.tag_bind(hit, "<Enter>", lambda e: self._tint(items, C.ACCENT))
        cv.tag_bind(hit, "<Leave>", lambda e: self._tint(items, color, pinned))

    def _head_img(self, item, name, shade):
        """Canvas 上的图片按钮换图（hover/状态切换）"""
        img = self.icon(name, shade)
        if img is not None:
            self.head.itemconfigure(item, image=img)

    def _tint(self, items, color, filled=False):
        cv = self.head
        for i in items:
            k = cv.type(i)
            if k == "oval":
                cv.itemconfigure(i, outline=color)
                cv.itemconfigure(i, fill=color if filled else "")
            elif k == "polygon":
                cv.itemconfigure(i, outline=color, fill=color if filled else "")
            else:
                cv.itemconfigure(i, fill=color)

    def _btn_panel(self, x, y, collapsed, cmd, color):
        """收起/展开：实心方块=已收起，空心=展开中"""
        cv = self.head
        if collapsed:
            body = cv.create_rectangle(x - 4, y - 4, x + 4, y + 4, fill=color, outline=color)
        else:
            body = cv.create_rectangle(x - 4, y - 4, x + 4, y + 4, fill="", outline=color, width=1.2)
            cv.create_line(x - 4, y - 1, x + 4, y - 1, fill=color, width=1)
        hit = cv.create_rectangle(x - 8, y - 8, x + 8, y + 8, outline="", fill=C.HEAD)
        cv.tag_lower(hit, body)
        cv.tag_bind(body, "<Button-1>", lambda e, c=cmd: c())
        cv.tag_bind(hit, "<Button-1>", lambda e, c=cmd: c())
        cv.tag_bind(hit, "<Enter>", lambda e: cv.itemconfigure(body, outline=C.ACCENT))
        cv.tag_bind(hit, "<Leave>", lambda e: cv.itemconfigure(body, outline=color))

    def _btn_palette(self, x, y, cmd, color):
        """调色盘：SVG 色板图标；无图标退回自绘"""
        cv = self.head
        img = self.icon("palette", "text")
        if img is not None:
            hit = cv.create_image(x, y, image=img)
            self._hot([hit], cmd)
            cv.tag_bind(hit, "<Enter>", lambda e: self._head_img(hit, "palette", "accent"))
            cv.tag_bind(hit, "<Leave>", lambda e: self._head_img(hit, "palette", "text"))
            return
        disk = cv.create_oval(x - 5, y - 5, x + 5, y + 5, fill="", outline=color, width=1.3)
        dots = [cv.create_oval(x - 3.2 + i * 2.6, y - 2.6, x - 1.6 + i * 2.6, y - 1.0,
                               fill=color, outline="") for i in range(3)]
        hole = cv.create_oval(x + 0.6, y + 1.2, x + 3.0, y + 3.6, fill="", outline=color, width=1)
        hit = cv.create_rectangle(x - 8, y - 8, x + 8, y + 8, outline="", fill=C.HEAD)
        cv.tag_lower(hit, disk)
        cv.tag_bind(hit, "<Button-1>", lambda e, c=cmd: c())
        cv.tag_bind(disk, "<Button-1>", lambda e, c=cmd: c())

        def tint(col):
            cv.itemconfigure(disk, outline=col)
            cv.itemconfigure(hole, outline=col)
            for d in dots:
                cv.itemconfigure(d, fill=col)
        cv.tag_bind(hit, "<Enter>", lambda e: tint(C.ACCENT))
        cv.tag_bind(hit, "<Leave>", lambda e: tint(color))

    # ---------------- 进度条
    def progress_state(self):
        """返回 (已完成, 总数, 进度0~1)"""
        total = len(self.store.tasks)
        done = sum(1 for t in self.store.tasks if t.get("done"))
        return done, total, (done / total if total else 0.0)

    def bar_color(self, ratio):
        if ratio >= 1.0:
            return C_BAR_FULL
        if ratio >= 0.5:
            return C_BAR_MID
        return C_BAR_LOW

    def draw_bar(self):
        cv = self.bar
        cv.delete("all")
        w = max(cv.winfo_width(), 40)
        h = 26
        cv.create_rectangle(0, 0, w, h, fill=C.BG, outline="")
        done, total, ratio = self.progress_state()
        color = self.bar_color(ratio)

        pad = 8
        tx = pad
        # 左侧文字：已完成 / 总数
        if total == 0:
            head_txt = tr("no_task")
            t = cv.create_text(tx, h / 2, text=head_txt, anchor="w",
                               font=self.f_tiny, fill=C.SUB)
            bbox = cv.bbox(t) or (tx, 0, tx + 60, h)
            self._bar_track(cv, min(bbox[2] + 8, w - pad - 30), w - pad, h)
            self._bar_tip = tr("no_task_tip")
            return

        head_txt = "%d / %d" % (done, total)
        t = cv.create_text(tx, h / 2, text=head_txt, anchor="w",
                           font=(self.f_ui, 8, "bold"), fill=color)
        bbox = cv.bbox(t) or (tx, 0, tx + 30, h)
        tx = bbox[2] + 6

        # 右侧文字：百分比 或 鼓励语
        full = done >= total
        if full:
            right_txt = self.encourage(total)
            right_color = C_BAR_FULL
            right_font = (self.f_ui, 8, "bold")
        else:
            right_txt = "%d%%" % int(round(ratio * 100))
            right_color = C.SUB
            right_font = (self.f_ui, 8, "bold")
        rt = cv.create_text(w - pad, h / 2, text=right_txt, anchor="e",
                            font=right_font, fill=right_color, tags=("pct",))
        rbox = cv.bbox(rt) or (w - 40, 0, w - pad, h)

        bar_x2 = rbox[0] - 8
        bar_x1 = tx
        if bar_x2 - bar_x1 < 34:          # 太窄就把左侧计数省掉，只留条
            bar_x1 = pad
            cv.delete(t)
        self._bar_track(cv, bar_x1, bar_x2, h, ratio, color, full)

        left = total - done
        self._bar_tip = (
            tr("bar_tip_full", n=total) if full else
            tr("bar_tip_left", done=done, total=total, left=left, pct=int(round(ratio * 100)))
        )

    def _bar_track(self, cv, x1, x2, h, ratio=0.0, color=None, full=False):
        """画进度槽 + 填充"""
        if x2 - x1 < 6:
            return
        y1, y2 = h / 2 - 4, h / 2 + 4
        round_rect(cv, x1, y1, x2, y2, 4, fill=C.BAR_BG, outline="")
        if ratio <= 0:
            return
        fill_x2 = x1 + max(4, (x2 - x1) * min(ratio, 1.0))
        round_rect(cv, x1, y1, fill_x2, y2, 4, fill=color or C_BAR_LOW, outline="")
        # 全完成时在条上叠一层细高光，更醒目
        if full:
            cv.create_line(x1 + 5, y1 + 2, fill_x2 - 5, y1 + 2,
                           fill="#8FD3A6", width=1)

    # ---------------- 重绘去抖
    def debounce(self, key, fn, delay=40):
        """同一来源的 <Configure> 风暴只保留最后一次（避免拖动窗口时每帧全量重绘）"""
        pend = getattr(self, "_debounce_ids", None)
        if pend is None:
            pend = self._debounce_ids = {}
        old = pend.get(key)
        if old is not None:
            try:
                self.root.after_cancel(old)
            except Exception:
                pass
        pend[key] = self.root.after(delay, lambda: (pend.pop(key, None), fn()))

    # ---------------- 黑匣子日志（v1.3.5：改为后台线程异步写）
    # 此前每次 diag 都重新 open 文件——Windows 上杀毒软件扫描时会锁住文件，
    # open() 永久阻塞 → UI 线程卡死 →「未响应」。log 证实卡死都发生在
    # 回调第一行 diag 处，就是它。现在 UI 线程只往队列里放，磁盘完全交给后台线程。
    def diag(self, msg):
        try:
            if getattr(self, "_diag_q", None) is None:
                import queue as _q, threading as _th
                self._diag_q = _q.Queue()
                self._diag_path = os.path.join(data_dir(), "log.txt")
                self._diag_th = _th.Thread(target=self._diag_worker, daemon=True)
                self._diag_th.start()
            self._diag_q.put_nowait("%s %s" % (
                dt.datetime.now().strftime("%H:%M:%S.%f")[:-3], msg))
        except Exception:
            pass

    def _diag_worker(self):
        fh = None
        while True:
            try:
                line = self._diag_q.get(timeout=2.0)
            except Exception:
                continue
            if line is None:        # 退出哨兵
                break
            for attempt in range(3):
                try:
                    if fh is None:
                        fh = open(self._diag_path, "a", encoding="utf-8")
                    fh.write(line + "\n")
                    fh.flush()
                    break
                except Exception:
                    try:
                        fh.close()
                    except Exception:
                        pass
                    fh = None
                    time.sleep(0.5)
            self._diag_q.task_done()

    def timed(self, label, fn):
        t0 = time.time()
        fn()
        self.diag("  %-22s %5d ms" % (label, int((time.time() - t0) * 1000)))

    # ---------------- 换肤
    def apply_theme(self, theme_id, announce=True):
        self.diag("== apply_theme %s ==" % theme_id)
        try:
            self.timed("set_theme+save", lambda: (C.set_theme(palette.get(theme_id)),
                                                  setattr(self.store, "theme", theme_id),
                                                  self.store.save()))
            # Tk 控件（非 Canvas）要显式刷色
            self.timed("tk控件刷色", lambda: self._recolor_widgets())
            # Canvas 重绘
            self.timed("draw_head", self.draw_head)
            self.timed("draw_bar", self.draw_bar)
            self.timed("render_messages", self.render_messages)
            self.timed("refresh_tasks", self.refresh_tasks)
            if self._hist_win is not None and self._hist_win.winfo_exists():
                self._hist_win.configure(bg=C.BG)
                self._render_history()
            if self._theme_win is not None and self._theme_win.winfo_exists():
                self.timed("repaint_palette", self._repaint_palette)
            cw = getattr(self, "_clock_win", None)
            if cw is not None and cw.winfo_exists():
                self.timed("recolor_clock", self._recolor_clock)
            self.timed("recolor_cal", self._recolor_calendar)
            # 气泡是独立 Toplevel，递归刷色覆盖不到 → 直接重建
            if getattr(self.store, "bubble_enabled", True):
                b = getattr(self, "_bubble", None)
                if b is not None:
                    b.close()
                self._bubble = None
                self.root.after(80, self._ensure_bubble)
            if announce:
                self.flash(tr("theme_changed", name=self.theme_label(palette.get(theme_id)["id"])))
            self.diag("== apply_theme 完成 ==")
        except Exception:
            import traceback as _tb
            self.diag("!! 异常:\n" + _tb.format_exc())

    def _recolor_widgets(self):
        self.root.configure(bg=C.BG)
        self.grip.configure(bg=C.BG)
        # 缩放热区：顶部/上角=标题栏色，其余=背景色（见创建处，v1.9.6）
        for f in getattr(self, "_edges", []):
            f.configure(bg=getattr(f, "_edge_col", C.BG))
        self.chat_wrap.configure(bg=C.BG)
        self.input_row.configure(bg=C.BG)
        self.list_head.configure(bg=C.BG)
        self.list_wrap.configure(bg=C.BG)
        self.foot.configure(bg=C.BG)
        self.quote_row.configure(bg=C.BG)
        self.chat_cv.configure(bg=C.BG)
        self.list_cv.configure(bg=C.BG)
        self.splitter.configure(bg=C.SPLIT)
        self.head.configure(bg=C.BG)
        self.bar.configure(bg=C.BG)
        self.counter.configure(bg=C.BG, fg=C.SUB)
        self.clear_btn.configure(bg=C.BG, fg=C.SUB)
        self.f_note.configure(bg=C.BG, fg=C.SUB)
        self.f_hint.configure(bg=C.BG, fg=C.SUB)
        self.hist_btn.configure(bg=C.BG, fg=C.SUB)
        self.quote_lbl.configure(bg=C.BG, fg=C.SUB)
        self.entry.configure(bg=C.INPUT_BG, fg=C.TEXT, insertbackground=C.TEXT,
                             highlightbackground=C.INPUT_LINE, highlightcolor=C.ACCENT)
        self.send_btn.configure(bg=C.ACCENT)
        # 兜底：递归刷所有没显式列出的控件（tab、透明度按钮、弹层残留等），
        # 之前换主题后个别组件颜色不更新，就是漏在这类「后来加的控件」上。
        skip = {id(self.entry), id(self.send_btn), id(self.splitter)} \
            | {id(f) for f in getattr(self, "_edges", [])}   # 热区颜色单独管
        seen = set()

        def _walk(w):
            if id(w) in seen:
                return
            seen.add(id(w))
            for ch in w.winfo_children():
                if id(ch) in skip:
                    _walk(ch)
                    continue
                cls = ch.winfo_class()
                try:
                    if cls in ("Frame", "TFrame", "Label", "Canvas", "Listbox",
                               "Spinbox", "Scale", "Checkbutton", "Radiobutton"):
                        ch.configure(bg=C.BG)
                    if cls in ("Label", "Button", "Checkbutton", "Radiobutton",
                               "Listbox") and id(ch) != id(self.send_btn):
                        # Button 保持自己的 ACCENT 底 + 浅色字
                        if cls == "Button":
                            ch.configure(bg=C.ROW2, fg=C.TEXT,
                                         activebackground=C.ROW2,
                                         activeforeground=C.TEXT)
                        else:
                            ch.configure(fg=C.SUB)
                    if cls == "Entry":
                        ch.configure(bg=C.INPUT_BG, fg=C.TEXT,
                                     insertbackground=C.TEXT)
                except Exception:
                    pass
                _walk(ch)

        _walk(self.root)

    def _repaint_palette(self):
        """就地把调色盘刷新到当前主题（控件版，不重建）"""
        win = self._theme_win
        if win is None or not win.winfo_exists():
            return
        try:
            win.configure(bg=C.BG, highlightbackground=C.LINE, highlightcolor=C.LINE)
            for ch in win.winfo_children():
                try:
                    ch.configure(bg=C.BG)
                except Exception:
                    pass
                for gc in ch.winfo_children():
                    try:
                        gc.configure(bg=C.BG)
                    except Exception:
                        pass
            for tid, (sw, nm, t) in getattr(self, "_palette_cells", {}).items():
                cur = (tid == self.store.theme)
                sw.configure(highlightbackground=C.ACCENT if cur else t["line"])
                nm.configure(fg=C.TEXT if cur else C.SUB)
        except Exception:
            pass

    def open_palette(self):
        # v1.3.6：改用普通 Tk 控件（按钮网格）。此前 Canvas 图元点击在
        # Windows 上存在事件分发死锁（回调从未执行，log 已证实），
        # 普通 widget 的事件路径与 Canvas 完全不同，绕开该问题。
        if self._theme_win is not None:
            self._close_palette()
            return
        self.diag("打开调色盘（内嵌面板 v2）")
        panel = tk.Frame(self.root, bg=C.BG, highlightthickness=1,
                         highlightbackground=C.LINE, highlightcolor=C.LINE)
        self._theme_win = panel
        self._palette_cells = {}
        panel.pack(side="top", fill="x", after=self.bar, before=self.chat_wrap)

        head = tk.Frame(panel, bg=C.BG)
        head.pack(side="top", fill="x", padx=10, pady=(6, 0))
        tk.Label(head, text=tr("palette_title"), bg=C.BG, fg=C.SUB,
                 font=(self.f_ui, 8, "bold")).pack(side="left")
        xb = tk.Label(head, text="×", bg=C.BG, fg=C.SUB,
                      font=(self.f_ui, 11, "bold"), cursor="hand2")
        xb.pack(side="right")
        xb.bind("<Button-1>", lambda e: self._close_palette())

        grid = tk.Frame(panel, bg=C.BG)
        grid.pack(side="top", fill="x", padx=4, pady=(2, 8))
        cols = 4
        for i, t in enumerate(palette.THEMES):
            r, c = divmod(i, cols)
            cell = tk.Frame(grid, bg=C.BG)
            cell.grid(row=r, column=c, padx=2, pady=3)
            cur = (t["id"] == self.store.theme)
            sw = tk.Label(cell, text="", bg=t["bg"], width=5, height=1,
                          relief="solid", bd=1, highlightthickness=2,
                          highlightbackground=C.ACCENT if cur else t["line"])
            sw.pack()
            nm = tk.Label(cell, text=self.theme_label(t["id"]), bg=C.BG,
                          fg=C.TEXT if cur else C.SUB, font=self.f_tiny)
            nm.pack()
            self._palette_cells[t["id"]] = (sw, nm, t)
            for wgt in (sw, nm):
                wgt.bind("<Button-1>", lambda e, tid=t["id"]: self._pick_theme(tid))
                wgt.bind("<Enter>", lambda e, w=sw: w.configure(highlightbackground=C.ACCENT))
                wgt.bind("<Leave>", lambda e, w=sw, tl=t:
                         w.configure(highlightbackground=C.ACCENT
                                     if tl["id"] == self.store.theme else tl["line"]))

    def _pick_theme(self, tid):
        self.diag("点击色块 %s" % tid)
        self.apply_theme(tid)

    def _close_palette(self):
        p = self._theme_win
        self._theme_win = None
        self._palette_cv = None
        if p is not None:
            try:
                p.destroy()
            except Exception:
                pass

    # ---------------- 哲言
    def lang_code(self):
        return "en" if i18n.is_en() else "zh"

    def draw_quote(self):
        """从当前语言的那副牌里抽一句，并记进该语言的状态"""
        code = self.lang_code()
        q = self.decks.draw(code)
        st = self.store.q_state(code)
        st["last"] = q
        st["recent"] = (st.get("recent", []) + [q])[-60:]
        self.store.save()
        return q

    def fmt_quote(self, q):
        """哲言气泡统一加标记，与普通回复区分开"""
        return tr("quote_wrap", q=q) if q else q

    def show_quote(self, q):
        self.quote_lbl.config(text="\u201c" + q + "\u201d" if q else "")

    def restore_quote(self):
        st = self.store.q_state(self.lang_code())
        q = st.get("last") or self.draw_quote()
        st["last"] = q
        self.store.save()
        self.show_quote(q)

    def roll_quote(self, manual=False):
        q = self.draw_quote()
        if not q:
            return
        self.show_quote(q)
        if manual:
            self.flash(q, 3600)

    def quote_on_complete(self, task, left):
        """勾掉一项后：只报「任务完成」。哲言不再刷屏，只留在底部哲言栏。"""
        def _mk(lang):
            s = i18n.render("task_done_push", dict(title=task["title"]), lang)
            if left <= 0:
                s += " " + i18n.render("task_done_all", dict(n=len(self.store.tasks)), lang)
            return s
        self.push_dual("bot", _mk(i18n.get_lang()), _mk(
            "en" if i18n.get_lang() == "zh" else "zh"))
        return None

    # ---------------- 拖拽 / 缩放
    def on_head_press(self, e):
        self._drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())

    def on_drag(self, e):
        if not self._drag:
            return
        # 拖动时暂时取消置顶重设，避免闪烁
        x = e.x_root - self._drag[0]
        y = e.y_root - self._drag[1]
        self.root.geometry("+%d+%d" % (x, y))
        self.debounce("notepos", self._save_note_pos, 500)

    def on_split_press(self, e):
        self._split = (e.y_root, self.chat_cv.winfo_height())
        # 分割线只有 5px 高，同样需要抓取事件流才能拖得动
        try:
            e.widget.grab_set()
        except Exception:
            pass

    def on_split_drag(self, e):
        if not self._split:
            return
        y0, h0 = self._split
        new_h = int(max(40, min(h0 + (e.y_root - y0),
                                self.root.winfo_height() - 170)))
        self.chat_h = new_h
        self.chat_cv.configure(height=new_h)

    def on_split_release(self, e):
        if getattr(self, "_split", None):
            self._split = None
            try:
                e.widget.grab_release()
            except Exception:
                pass
            try:
                self.store.chat_h = self.chat_h
                self.store.save()
            except Exception:
                pass

    def on_grip_press(self, e):
        self._resizing = [e.x_root, e.y_root, self.root.winfo_width(),
                          self.root.winfo_height(), dt.datetime.now()]
        self.grip.bind("<B1-Motion>", self.on_resize)
        self.grip.bind("<ButtonRelease-1>", self.on_resize_end)

    def on_resize(self, e):
        if not self._resizing:
            return
        # 节流：Motion 事件比刷新率高时挤队会卡
        if (dt.datetime.now() - self._resizing[4]).total_seconds() < 0.03:
            return
        self._resizing[4] = dt.datetime.now()
        x0, y0, w0, h0 = self._resizing[:4]
        w = max(250, w0 + (e.x_root - x0))
        h = max(150, h0 + (e.y_root - y0))
        self.root.geometry("%dx%d" % (w, h))

    def on_resize_end(self, e):
        self._resizing = None
        self._save_note_pos()
        self.grip.unbind("<B1-Motion>")
        self.grip.unbind("<ButtonRelease-1>")

    # ---- 边框拖拽缩放（四边 + 四角，坐标法 v1.9.7）----
    EDGE_PX = 10        # 边缘命中厚度
    CORNER_PX = 18      # 角部命中边长

    def _edge_zone(self, x, y):
        """坐标 → 缩放方位；不在边缘返回 None"""
        w = self.root.winfo_width()
        h = self.root.winfo_height()
        # 标题栏右侧按钮区（关闭/最小化/置顶等）不参与缩放命中，
        # 否则点按钮会被当成拉右上角（v1.9.7）
        if y < 28 and x >= w - 130:
            return None
        C_ = self.CORNER_PX
        if x < C_ and y < C_:
            return "corner-tl"
        if x >= w - C_ and y < C_:
            return "corner-tr"
        if x < C_ and y >= h - C_:
            return "corner-bl"
        if x >= w - C_ and y >= h - C_:
            return "corner-br"
        E = self.EDGE_PX
        if y < E:
            return "top"
        if y >= h - E:
            return "bottom"
        if x < E:
            return "left"
        if x >= w - E:
            return "right"
        return None

    _EDGE_CURSORS = {
        "top": "top_side", "bottom": "bottom_side",
        "left": "left_side", "right": "right_side",
        "corner-tl": "top_left_corner", "corner-tr": "top_right_corner",
        "corner-bl": "bottom_left_corner", "corner-br": "bottom_right_corner",
    }

    def _edge_xy(self, e):
        """把事件坐标换算成「相对主窗口」的坐标（v1.9.8 关键修复）。

        事件从任务条/输入框等内部控件冒泡到主窗口绑定时，e.x/e.y 是
        相对那个控件的，不是相对窗口的——之前直接拿来做边缘判定，
        结果就是「拉不动窗口」+「光标在任务条中间也变成缩放样式」。
        """
        try:
            return (e.x_root - self.root.winfo_rootx(),
                    e.y_root - self.root.winfo_rooty())
        except Exception:
            return (getattr(e, "x", 0), getattr(e, "y", 0))

    def _edge_cursor(self, e):
        """悬停在边缘 → 显示缩放光标（节流：值没变不刷）"""
        if getattr(self, "_edge", None):
            return
        try:
            zone = self._edge_zone(*self._edge_xy(e))
        except Exception:
            return
        cur = self._EDGE_CURSORS.get(zone, "")
        if self.root.cget("cursor") != cur:
            self.root.config(cursor=cur)

    def _edge_probe(self, e):
        """按下：落在边缘则进入缩放模式（控件自己的 handler 照常执行）"""
        zone = self._edge_zone(*self._edge_xy(e))
        if not zone:
            return
        r = self.root
        self._edge = {"side": zone,
                      "mx": e.x_root, "my": e.y_root,
                      "x": r.winfo_x(), "y": r.winfo_y(),
                      "w": r.winfo_width(), "h": r.winfo_height(),
                      "t": dt.datetime.min}
        self._drag = None           # 别让标题栏拖动同时生效

    def _edge_motion(self, e):
        st = getattr(self, "_edge", None)
        if not st:
            return
        # 节流：Motion 事件可能比刷新率高，挤队会卡（~33fps 足够顺滑）
        now = dt.datetime.now()
        if (now - st.get("t", now)).total_seconds() < 0.03:
            return
        st["t"] = now
        dx, dy = e.x_root - st["mx"], e.y_root - st["my"]
        side, x, y, w, h = st["side"], st["x"], st["y"], st["w"], st["h"]
        MIN_W, MIN_H = 240, 160
        if side in ("left", "corner-tl", "corner-bl"):
            w = max(MIN_W, st["w"] - dx)
            x = st["x"] + (st["w"] - w)
        if side in ("right", "corner-tr", "corner-br"):
            w = max(MIN_W, st["w"] + dx)
        if side in ("bottom", "corner-bl", "corner-br"):
            h = max(MIN_H, st["h"] + dy)
        if side in ("top", "corner-tl", "corner-tr"):
            h = max(MIN_H, st["h"] - dy)
            y = st["y"] + (st["h"] - h)
        self.root.geometry("%dx%d+%d+%d" % (w, h, x, y))

    def _edge_up(self, e):
        if getattr(self, "_edge", None):
            self._edge = None
            self.root.config(cursor="")
            self._save_note_pos()

    # ---- 旧版热区接口（保留兼容：测试/历史调用） ----
    def on_edge_press(self, e, side):
        r = self.root
        self._edge = {"side": side,
                      "mx": e.x_root, "my": e.y_root,
                      "x": r.winfo_x(), "y": r.winfo_y(),
                      "w": r.winfo_width(), "h": r.winfo_height(),
                      "t": dt.datetime.min,
                      "wgt": getattr(e, "widget", None)}
        try:
            e.widget.grab_set()
        except Exception:
            pass

    def on_edge_drag(self, e):
        self._edge_motion(e)

    def on_edge_release(self):
        st = getattr(self, "_edge", None)
        if st:
            try:
                w = st.get("wgt")
                if w is not None:
                    w.grab_release()
            except Exception:
                pass
            self._edge = None
            self._save_note_pos()


    # ---------------- 窗口动作
    def toggle_top(self):
        self.store.topmost = not self.store.topmost
        self.root.attributes("-topmost", self.store.topmost)
        self.store.save()
        self.draw_head()
        self.flash(tr("pinned_on") if self.store.topmost else tr("pinned_off"))

    def toggle_overlay(self):
        """收起「虚拟屏占 1/18」的便签形态"""
        self.overlay = not self.overlay
        r = self.root
        if self.overlay:
            r.overrideredirect(True)
            r.attributes("-alpha", max(0.35, getattr(self.store, "alpha", 0.88) - 0.08))
            self.chat_wrap.pack_forget()
            self.input_row.pack_forget()
        else:
            r.attributes("-alpha", getattr(self.store, "alpha", 0.88))  # 半透明：可调
            self.chat_wrap.pack(side="top", fill="x", after=self.bar)
            self.input_row.pack(side="top", fill="x", padx=6, pady=(2, 4),
                                after=self.chat_wrap)
            self.render_messages()
        self.draw_head()
        self.refresh_tasks()

    def minimize(self):
        self.root.overrideredirect(False)
        # 先解旧绑定再挂新的：反复最小化不至于叠出多个 <Map> 回调
        try:
            self.root.unbind("<Map>")
        except Exception:
            pass
        self.root.iconify()
        self.root.after(120, self._after_min)

    def _after_min(self):
        try:
            self.root.unbind("<Map>")
            self.root.bind("<Map>", self._on_map)
        except Exception:
            pass

    def _on_map(self, e=None):
        try:
            self.root.unbind("<Map>")
        except Exception:
            pass
        try:
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", self.store.topmost)
        except Exception:
            pass
        self.draw_head()

    def quit(self):
        # v1.9.9.7：优雅退出——之前直接 destroy，挂着的 after 定时回调
        # （跨天轮询/倒计时心跳/防抖等）和运行期动态创建的 Tcl 字体对象
        # 会在解释器销毁时被清到一半，Windows 上偶发
        # 「Fatal Error: alloc: invalid block」弹窗。
        self._closing = True
        # 先把窗口藏起来：点关闭立刻视觉响应，后台安静收尾
        try:
            self.root.withdraw()
        except Exception:
            pass
        try:
            for aid in self.root.tk.call("after", "info"):
                try:
                    self.root.after_cancel(aid)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            getattr(self, "_diag_q", None) and self._diag_q.put_nowait(None)
        except Exception:
            pass
        self._save_note_pos()
        self._close_clock()
        b = getattr(self, "_bubble", None)
        if b is not None:
            b.close()
        for c in list(getattr(self, "_due_cards", [])):
            c.close()
        self.store.sync_history()
        self._save_note_pos()
        self.store.save()
        self.close_history()
        try:
            self.root.update_idletasks()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        # v1.9.9.9b：「alloc: invalid block」仍会在 Windows 上于 Tcl 解释器
        # 收尾阶段弹出（残留的 Tcl 字体/图片对象被 GC 时清到坏块）。
        # 此时数据已全部落盘、窗口已销毁，直接硬退出进程，
        # 彻底跳过 Tcl/Python 收尾，杜绝该崩溃。
        # 测试环境例外：pytest 进程还要继续跑。
        if "pytest" not in sys.modules:
            os._exit(0)

    def flash(self, text, ms=1600):
        self.f_hint.config(text=text)
        self.root.after(ms, lambda: self.f_hint.config(text=""))

    # ---------------- 聊天区
    def bubble_texts(self):
        """把消息排成 (role, text) 列表（按当前语言取双语消息）"""
        lang = i18n.get_lang()
        out = []
        for m in self.store.messages:
            out.append((m.get("role", "bot"),
                        m.get(lang) or m.get("text", "")))
        return out

    def render_messages(self, offset=None):
        cv = self.chat_cv
        cv.delete("all")
        w = max(cv.winfo_width(), 40)
        h = max(cv.winfo_height(), 40)
        texts = self.bubble_texts()
        if not texts:
            texts = [("bot", tr("hello_first"))]
        line_h = 15
        max_bubble_w = int(w * 0.82)
        items = []
        for role, text in reversed(texts):
            # 宽度优先贴合文本（v1.9.5）：先按「不换行」量真实宽度，
            # 只有超过上限才折行，避免短句被塞进一个过大的框
            one = " ".join((text or "").split("\n"))
            natural = self.text_width(one, self.f_chat) + 16
            if natural <= max_bubble_w:
                wrapped = text or ""
            else:
                wrapped = self.wrap_text(text, self.f_chat, max_bubble_w - 16)
            lines = wrapped.split("\n")
            bh = len(lines) * line_h + 8
            bw = max([self.text_width(l, self.f_chat) for l in lines] or [30]) + 16
            bw = min(max(bw, 36), max_bubble_w)
            items.append((role, lines, bw, bh))
        items.reverse()                      # 回到时间正序

        total = sum(i[3] + 5 for i in items) + 6
        if offset is None:
            offset = min(0, h - total)       # 默认贴底显示最新
        self._chat_offset = offset
        self._chat_total = total
        self._chat_min = min(0, h - total)   # 滚动下限：到最旧一条为止
        y = offset + 4
        for role, lines, bw, bh in items:
            if y + bh < -4 or y > h + 4:
                y += bh + 5
                continue
            if role == "user":
                x1 = w - 6 - bw
                color = C.BUBBLE
            else:
                x1 = 6
                color = C.BOT_BUBBLE
            round_rect(cv, x1, y, x1 + bw, y + bh, 8, fill=color, outline="#EDE0AE")
            ty = y + 4
            for ln in lines:
                cv.create_text(x1 + 8, ty, text=ln, anchor="nw", font=self.f_chat, fill=C.TEXT)
                ty += line_h
            y += bh + 5

    def real_font(self, spec):
        """带缓存的 Font 获取：同一 spec 只创建一次（此前每次新建导致严重卡顿）"""
        cache = getattr(self, "_font_cache", None)
        if cache is None:
            cache = self._font_cache = {}
        key = str(spec)
        f = cache.get(key)
        if f is None:
            try:
                f = tkfont.Font(font=spec)
            except Exception:
                f = tkfont.nametofont("TkDefaultFont")
            cache[key] = f
        return f

    def text_width(self, s, spec):
        try:
            return self.real_font(spec).measure(s)
        except Exception:
            return len(s) * 9

    # ---------------- 量宽加速
    # font.measure() 每次调用都有固定的 Tk 往返开销（实测约 0.5ms，与文字长短几乎无关），
    # 几十条任务一次重绘要调几百次，就会累计成几百毫秒的卡顿。
    # 对策：① 结果缓存 ② 平均字宽预估（只在放不下时才真正去量）③ 一次性批量测量。
    AVG_UNSAFE = set("mwMW@%“”…—【】（）：；，。！？、")

    def _avg_key(self, spec):
        return "avg|" + str(spec)

    def avg_char_w(self, spec):
        """该字体下「典型中文/字母」的平均字宽，用于快速预估"""
        key = self._avg_key(spec)
        w = self._avg_cache.get(key)
        if w is not None:
            return w
        f = self.real_font(spec)
        try:
            w = f.measure("国国国国国国国国") / 8.0
        except Exception:
            w = 9.0
        if not w or w <= 0:
            w = 9.0
        self._avg_cache[key] = w
        return w

    def est_width(self, s, spec):
        """估算不超宽（宁可估大一点，超宽时再精量）"""
        n = len(s)
        if n == 0:
            return 0
        spec_key = str(spec)
        charw = self._charw_cache.get(spec_key, {})
        known = 0
        tot = 0
        unknown = 0
        for ch in s:
            cw = charw.get(ch)
            if cw is None:
                unknown += 1
            else:
                known += 1
                tot += cw
        if unknown:
            tot += unknown * self.avg_char_w(spec) * 1.04
        return tot

    def fits(self, s, spec, maxw):
        """先估算，估得下就用缓存值；估不下才去问 Tk（结果回填缓存）"""
        spec_key = str(spec)
        key = "w|" + spec_key + "|" + str(s)
        hit = self._width_cache.get(key)
        if hit is not None and hit[0] <= maxw:
            return True
        if self.est_width(s, spec) <= maxw * 0.96:
            return True
        return self.text_width(s, spec) <= maxw

    def measure_many(self, strings, spec, maxw):
        """一次性量一批短文本的宽度，返回 True/False 列表（是否放得下）。
        maxw 可以是数字，也可以是逐行的宽度列表（v1.9.7：带时间/用时多的行
        可用宽度更小，统一 maxw 会高估 fits，导致标题溢出或过度截断）。"""
        strings = list(strings)
        if isinstance(maxw, (list, tuple)):
            maxws = list(maxw) + [maxw[-1] if maxw else 0] * (len(strings) - len(maxw))
        else:
            maxws = [maxw] * len(strings)
        res = [None] * len(strings)
        spec_key = str(spec)
        need = []
        for i, s in enumerate(strings):
            key = "w|" + spec_key + "|" + str(s)
            hit = self._width_cache.get(key)
            if hit is not None:
                res[i] = hit[0] <= maxws[i]
            elif self.est_width(s, spec) <= maxws[i] * 0.96:
                res[i] = True
            else:
                need.append(i)
        if need:
            # 用 \x1f 拼接，一次 measure 拿回总宽，再按差分还原每段宽度
            parts = [str(strings[i]) for i in need]
            sep = "\x1f"
            f = self.real_font(spec)
            widths = []
            prev = 0
            acc = ""
            for j, part in enumerate(parts):
                acc = acc + part if j == 0 else acc + sep + part
                cur = f.measure(acc)
                widths.append(cur - prev)
                prev = cur
            for i, w in zip(need, widths):
                self._width_cache["w|" + spec_key + "|" + str(strings[i])] = (w,)
                res[i] = w <= maxws[i]
        return res

    def _char_w(self, ch, spec_key, font):
        """字符宽度缓存：同一字符在同一字体下宽度恒定"""
        cache = self._charw_cache.setdefault(spec_key, {})
        w = cache.get(ch)
        if w is None:
            w = None
            try:
                w = font.measure(ch)
            except Exception:
                w = None
            if not w:
                # 量不出来（异常/零宽）就用平均字宽兜底，绝不写 9 之类的假值
                w = self.avg_char_w(spec_key)
            cache[ch] = w
        return w

    def wrap_text(self, text, spec, maxw):
        """中英文混排按像素宽度折行（先整句估算，能塞下就不逐字走）"""
        whole = str(text)
        if "\n" not in whole and self.fits(whole, spec, maxw):
            return whole
        if not hasattr(self, "_charw_cache"):
            self._charw_cache = {}
        f = self.real_font(spec)
        skey = str(spec)
        out_lines = []
        for raw in whole.split("\n"):
            cur = ""
            cur_w = 0
            for ch in raw:
                cw = self._char_w(ch, skey, f)
                if cur and cur_w + cw > maxw:
                    out_lines.append(cur)
                    cur, cur_w = ch, cw
                else:
                    cur += ch
                    cur_w += cw
            out_lines.append(cur)
        return "\n".join(out_lines)

    def ellipsize(self, title, spec, avail):
        """把过长标题截断加省略号。
        关键：从「刚好可能放不下的长度」开始往上试，通常 1~2 次就命中，
        避免原先「逐字删 + 每次 measure」的 O(n^2) 往返开销。"""
        key = "e|" + str(spec) + "|" + str(avail) + "|" + str(title)
        hit = self._width_cache.get(key)
        if hit is not None:
            return hit[0]
        n = len(title)
        avg = self.avg_char_w(spec) or 9.0
        # 估算最多能放几个字（留出省略号的位置），从这里开始往下退
        guess = int(avail / avg) if avg > 0 else n
        start = min(n, max(1, guess))
        out = "…" if n else ""
        for k in range(start, 0, -1):
            cand = title[:k] + "…"
            if self.text_width(cand, spec) <= avail:
                out = cand
                break
        self._width_cache[key] = (out,)
        return out

    def on_chat_wheel(self, e, direction=None):
        # 向下滑 = 看最新（offset 往 0 靠）；向上滑 = 翻旧消息
        if direction is None:
            direction = 1 if getattr(e, "delta", 0) > 0 else -1
        cur = getattr(self, "_chat_offset", 0)
        lo = getattr(self, "_chat_min", 0)          # 最旧消息处，不许再往上
        new = max(lo, min(4, cur + direction * 14))
        self.render_messages(offset=new)

    # ---------------- 输入
    def placeholder_tick(self):
        if not self.store.messages:
            self.entry.insert(0, tr("input_ph"))
            self.entry.config(fg=C.SUB)
            self._compose_placeholder = True

    def clear_placeholder(self, e=None):
        if self._compose_placeholder:
            self.entry.delete(0, "end")
            self.entry.config(fg=C.TEXT)
            self._compose_placeholder = False

    def restore_placeholder(self, e=None):
        """输入框空着且失去焦点时，把提示语放回去（原来只在启动时设一次）"""
        if not self._compose_placeholder and not self.entry.get().strip():
            self.entry.delete(0, "end")
            self.entry.insert(0, tr("input_ph"))
            self.entry.config(fg=C.SUB)
            self._compose_placeholder = True

    def on_send(self):
        if self._compose_placeholder:
            return "break"
        text = self.entry.get().strip()
        if not text:
            return "break"
        self.entry.delete(0, "end")
        if self.list_mode == "note":
            self.add_note(text)
            return "break"
        self.handle_user_text(text)
        return "break"

    # ---------------- 消息流
    def push(self, role, text, dual=None):
        msg = {"role": role, "text": text,
               "t": dt.datetime.now().strftime("%H:%M")}
        if dual:
            # 双语回放：切语言时历史消息跟着换（zh, en)
            msg["zh"], msg["en"] = dual[0], dual[1]
        self.store.messages.append(msg)
        self.store.messages = self.store.messages[-60:]
        self.store.save()
        self.render_messages()

    def push_dual(self, role, cur, oth):
        """以「当前语言 + 另一语言」推送；cur/oth 由调用方按语言分别渲染"""
        lang = i18n.get_lang()
        self.push(role, cur, dual=(cur, oth) if lang == "zh" else (oth, cur))

    def push_tr(self, role, key, **kw):
        """直接以模板推送一条双语消息（respond 流程之外的开场白等）"""
        lang = i18n.get_lang()
        other = "en" if lang == "zh" else "zh"
        cur = i18n.render(key, kw, lang)
        oth = i18n.render(key, kw, other)
        self.push(role, cur, dual=(cur, oth) if lang == "zh" else (oth, cur))

    def _daily_greet_dual(self):
        """每日问候：按天取池子索引，返回 (当前语言文本, (zh, en))"""
        idx = dt.date.today().toordinal() % 10
        nm = getattr(self.store, "user_name", "")

        def _of(lang):
            if nm:
                pool = i18n.render_list("daily_greet", lang)
                return pool[idx % len(pool)].format(name=nm)
            return i18n.render("new_day", {}, lang)
        cur = _of(i18n.get_lang())
        return cur, (_of("zh"), _of("en"))

    def _dual_of(self, reply, specs):
        """用记录到的 (key, kw, 渲染文本) 尝试重建另一语言版本。
        成功返回 (zh, en)；拼接复杂对不上时返回 None（保留原文）。"""
        if not reply or not specs:
            return None
        lang = i18n.get_lang()
        other = "en" if lang == "zh" else "zh"
        remaining = reply
        other_text = reply
        # 长模板先替换：短模板（如称呼前缀）常被长模板包含，
        # 若先替换短模板会把长模板的匹配打断
        for key, kw, cur in sorted(specs, key=lambda s: -len(s[2] or "")):
            if not cur or cur not in remaining:
                continue        # 被更长的模板包含，跳过
            oth = i18n.render(key, kw, other)
            remaining = remaining.replace(cur, "\x00", 1)
            other_text = other_text.replace(cur, oth, 1)
        # 没被模板覆盖的只剩分隔符/空白才算成功
        if re.sub(r"[\s，,。.：:;；!！?？·…\-—_~～\"'“”‘’、\x00]", "", remaining):
            return None
        return (reply, other_text) if lang == "zh" else (other_text, reply)

    def greeting(self):
        """按时段的招呼：5-11 早上 / 11-14 中午 / 14-18 下午 / 其余晚上"""
        h = dt.datetime.now().hour
        if 5 <= h < 11:
            key = "greet_morning"
        elif 11 <= h < 14:
            key = "greet_noon"
        elif 14 <= h < 18:
            key = "greet_noon"
        else:
            key = "greet_evening"
        return i18n.pick(random, key)

    def handle_user_text(self, text):
        self.push("user", text)
        # 记录模式：respond 期间所有 tr() 调用会被记录，
        # 用于给这条回复生成双语版本（切语言时历史消息跟着换）
        i18n.record_start()
        try:
            reply = self.respond(text)
        finally:
            specs = i18n.record_drain()
        if reply:
            self.push("bot", reply, dual=self._dual_of(reply, specs))
        self.refresh_tasks(scroll_top=True)

    @staticmethod
    def _is_tell_phrase(seg):
        """「天气预报说有雨」这类转述/背景说明，不是任务本身"""
        import re as _re
        return bool(_re.search(r"(天气预报|说是有|听说|据说是|好像说)", seg or ""))

    @staticmethod
    def _same_title(a, b):
        """标题是否指同一件事（去空格、小写后互为子串或相等）"""
        a = (a or "").replace(" ", "").lower()
        b = (b or "").replace(" ", "").lower()
        if not a or not b:
            return False
        return a == b or a in b or b in a

    def _find_similar(self, title):
        """找已存在的相似任务标题；没有则 None。完全相同的优先返回。"""
        for t in self.store.tasks:
            if t["title"] == title:
                return t["title"]
        for t in self.store.tasks:
            if self._same_title(t["title"], title) and not t.get("done"):
                return t["title"]
        return None

    @staticmethod
    def _dup_ok_re():
        import re as _re
        return _re.compile(
            r"^\s*(就这个|就这样|就它|是的?|好吧?|好的|确认|可以|行|嗯+|ok|okay|yes|same)\s*[。.！!～~]*\s*$",
            _re.I)

    # ---------------- 过期截止时间确认（v1.9.4） ----------------
    def _is_expired(self, hhmm, due_iso):
        """截止时间是否已过：日期早于今天，或今天但时刻已过"""
        today = self.store._today()
        d = due_iso or today
        if d < today:
            return True
        if d > today or not hhmm:
            return False
        now = dt.datetime.now().strftime("%H:%M")
        return hhmm < now

    def _remind_now(self, task):
        """立即提醒一次：右下角悬浮卡片 + 聊天播报 + 铃声"""
        task["reminded"] = False
        task["reminded_day"] = None
        try:
            self.show_due_card(task)
        except Exception:
            pass
        lg = i18n.get_lang()
        ol = "en" if lg == "zh" else "zh"

        def _rn(l, _t=task):
            return i18n.render("remind_now", dict(
                t=_t["title"],
                h=(_t.get("deadline_txt") or _t.get("hhmm")
                   or _t.get("remind_at"))), l)
        self.push_dual("bot", _rn(lg), _rn(ol))
        self._ring_bell(self.root)
        self.refresh_tasks()

    def _resolve_expired(self, text):
        """用户对「已过截止时间，确认加入吗」的回答"""
        pe = getattr(self, "_pending_expired", None)
        self._pending_expired = None
        if not pe:
            return None
        # 长句/带动作的输入像一条新任务，不是对确认的回答（v1.9.7：
        # 之前「九点半背课文」没确认完就输「下午三点交作业」，被确认吃掉）
        _s = (text or "").strip()
        if len(_s) > 12 or (len(_s) > 6 and
                            re.search(r"(做好|做完|完成|写|交|准备|整理|发|去|买|做|开|打|看|读)", _s)):
            self._pending_q = None
            self._pending_task = None
            return None                      # respond 继续按新输入解析
        low = (text or "").strip().lower()
        ok = bool(self._dup_ok_re().search(text or "")) \
            or re.search(r"(确认|加入|要|加上|好呀|嗯+|yes|ok)", low)
        no = bool(re.search(r"(不用|不要|取消|算了|不加|拒绝|no\b|cancel)", low))
        # v1.9.9：确认环节里顺手答了 A/B/C/D（优先级）也视为「要加入」，
        # 并把优先级一并记下——之前这种回答被判成「没听懂」而无限重复提问
        _lv = re.match(r"^\s*([ABCD])\s*$", (text or "").strip(), re.I)
        if _lv:
            ok = True
        _lv_score = {"A": 95, "B": 75, "C": 55, "D": 30}.get(
            _lv.group(1).upper()) if _lv else None
        # 队列里还有别的过期任务待确认 → 交回 respond 前先决定
        _queue = (pe or {}).get("queue") or []

        def _next_ask():
            """当前这条处理完，若队列还有，继续问下一条；否则清空状态"""
            nonlocal pe
            if _queue:
                nxt = _queue.pop(0)
                nxt.setdefault("mode", "new")
                nxt["queue"] = _queue
                self._pending_expired = nxt
                self._pending_q = "expired"
                _t = (nxt.get("task") or {}).get("title", "")
                _m = tr("dl_expired", t=_t)
                if _queue:
                    _m += tr("dl_expired_more", n=len(_queue) + 1)
                return _m
            self._pending_q = None
            self._pending_expired = None
            return None

        if pe["mode"] == "new":
            d = pe["task"]
            if ok and no:
                no = False
            if ok:
                if _lv_score is not None:
                    d["score"] = _lv_score
                    d["manual"] = True
                self.store.tasks.append(d)
                self.store.save()
                self.refresh_tasks(scroll_top=True)
                self._remind_now(d)
                # v1.9.9.3：确认加入后立刻说「撤回」要能撤掉这条任务
                self._push_undo({"kind": "task", "id": d["id"]})
                _nxt = _next_ask()
                if _nxt:
                    return tr("dl_expired_added", t=d["title"]) + "\n" + _nxt
                return tr("dl_expired_added", t=d["title"])
            if no:
                _nxt = _next_ask()
                if _nxt:
                    return tr("dl_expired_skip", t=d["title"]) + "\n" + _nxt
                return tr("dl_expired_skip", t=d["title"])
            self._pending_expired = pe
            return tr("dl_expired", t=d["title"])
        # mode == "dl"：追问环节设的过期截止时间。
        # 注意：此时任务已经在待办里了，「不用」只是不设这个时间，不是删任务（v1.9.5）
        task = None
        for t in self.store.tasks:
            if t["id"] == pe["id"]:
                task = t
                break
        if task is None:
            return None
        if no:
            task["hhmm"] = None
            task["due_date"] = None
            task["deadline_txt"] = None
            task.pop("remind_before", None)
            self.store.save()
            self.refresh_tasks(scroll_top=True)
            self._pending_task = None
            self._pending_q = None
            # v1.9.9.3：这里必须记成 kind="task"。之前记成 kind="deadline"
            # 且 hhmm/due 全空，被 _match_undo 的「没时间别装撤过」防谎话
            # 分支判成「无可撤回」——用户明明刚被承诺「说撤回可以撤销」。
            # 此时时间本来就没设上，唯一有意义的撤销就是撤掉这个刚建的任务。
            self._push_undo({"kind": "task", "id": task["id"]})
            return tr("dl_expired_task_kept", t=task["title"])
        if ok:
            task["hhmm"] = pe["hhmm"]
            task["due_date"] = pe["due"]
            self.store.save()
            self.refresh_tasks(scroll_top=True)
            self._remind_now(task)
            self._pending_task = None
            # v1.9.9.3：确认把时间设上后，说「撤回」= 清掉这个时间
            # （与「刚设过时间就撤回」的全局语义一致）；注意不能记 hhmm=None，
            # 否则会被「没时间别装撤过」防谎话分支判成无可撤回
            self._push_undo({"kind": "deadline", "id": task["id"]})
            return tr("dl_expired_added", t=task["title"])
        # 没听懂：再问一遍
        self._pending_expired = pe
        return tr("dl_expired", t=task["title"])


    def _add_single(self, title, hhmm, score, dur, override=None):
        self.store.tasks.append({
            "id": "%d%03d" % (int(time.time() * 1000), random.randint(0, 999)),
            "title": override or title,
            "hhmm": hhmm,
            "dur": dur,
            "score": score,
            "manual": False,
            "done": False,
            "created": dt.datetime.now().strftime("%H:%M"),
            "day": self.store._today(),
        })
        self.store.save()
        self.refresh_tasks(scroll_top=True)

    # ---- 优先级 / 截止时间 问答 ----
    PRI_RE = None
    DL_TIME_RE = None
    DL_NO_RE = None

    def _pri_re(self):
        import re as _re
        if self.PRI_RE is None:
            self.PRI_RE = _re.compile(
                r"(?<![A-Za-z])([ABCD])(?![A-Za-z])|紧急|很急|非常重要|重要|一般|不急|不赶|"
                r"urgent|important|normal|low priority", _re.I)
        return self.PRI_RE

    def _dl_time_re(self):
        import re as _re
        if self.DL_TIME_RE is None:
            self.DL_TIME_RE = _re.compile(
                r"(明天|后天|今天|今晚|明早|下午|晚上|中午|早上|上午)?\s*"
                r"(\d{1,2})[点时:：](\d{1,2})?分?半?|"
                r"\b(\d{1,2})(:\d{2})?\s*(am|pm)\b", _re.I)
        return self.DL_TIME_RE

    @staticmethod
    def _dl_no_re():
        import re as _re
        return _re.compile(r"^\s*(没有|无|不用|不设|不用了|没有截止|no|none|nope|no deadline)\s*[。.！!～~]*\s*$", _re.I)

    def _smart_meridiem(self, text, eng):
        """无时段词的钟点：自动挑「还没过去的那个解释」（v1.9.5）

        用户 13:45 回「两点」时，引擎默认给 02:00（凌晨），必然已过 →
        于是弹「已过截止时间」，实际用户想说的是 14:00。
        规则：原样按引擎（凌晨）算；若已过且「+12 小时」（下午）还没过 → 取下午；
        两个都过了就保持原样，交给过期确认流程。
        只在原文完全没写时段词时介入，用户写了「凌晨/晚上」就尊重原意。
        """
        if not eng or not eng.get("hhmm"):
            return eng
        t = text or ""
        if re.search(r"(凌晨|半夜|深夜|早上|早晨|上午|中午|下午|傍晚|晚上|今晚|明晚|夜里|晚些|稍晚)", t):
            return eng
        # raw 可能是中文数字（「十点」），所以小时直接从已经解析好的 hhmm 里取
        hhmm = eng["hhmm"]
        try:
            h = int(str(hhmm).split(":")[0])
        except Exception:
            return eng
        if h > 12 or h == 12:
            return eng                     # 用户已经说了 12 小时制以外的时刻
        due = eng.get("due")
        if due and due != self.store._today():
            return eng                     # 明确是别的日期，不猜时段
        if not self._is_expired(hhmm, due):     # 凌晨那个解释还没过，就用它
            return eng
        h24 = (h + 12) % 24
        alt = "%02d:%s" % (h24, hhmm.split(":")[1] if ":" in hhmm else "00")
        if not self._is_expired(alt, due):      # 下午那个解释还没过 → 取下午
            eng = dict(eng)
            eng["hhmm"] = alt
            if eng.get("raw"):
                eng["raw"] = eng["raw"] + "（下午）"
        return eng

    @staticmethod
    def _is_pure_time_reply(text):
        """这句话是不是「纯粹在报一个时间」（可以当作截止时间回答）

        判据：去掉时间词和常见连接/语气词后基本不剩东西。
        「明天下午三点」「下午3点」「八点半吧」→ True
        「晚上八点提醒我做20个俯卧撑」→ False（还有动作和宾语，是新任务）
        """
        import re as _re
        t = (text or "").strip()
        if not t:
            return False
        # 带明显动作词的一律当新任务
        if _re.search(r"(提醒|做|写|交|发|去|买|准备|整理|完成|开|打|看|读|练|跑|洗|收拾|约)", t):
            return False
        # 时间词之外只允许剩这些
        rest = _re.sub(
            r"(明天|后天|大后天|今天|今晚|明晚|上午|中午|下午|傍晚|晚上|凌晨|半夜|深夜|早上|早晨|"
            r"下周[一二三四五六日天]?|这周[一二三四五六日天]?|周[一二三四五六日天]|"
            r"\d{1,2}|[一二三四五六七八九十]{1,3}|点半|点|时|分|"
            r"月|日|号|:|：|am|pm|AM|PM|"
            r"吧|啊|呀|呢|哈|就|是|在|到|为|好|可以|行|嗯|"
            r"[，,。.、！!？?~～\s])", "", t)
        return len(rest) <= 1

    def _apply_pri_answer(self, text):
        """把用户对优先级/截止时间的回答应用到待确认任务上。
        返回 (是否匹配回答, 回复文本, 剩余文本)"""
        pt = getattr(self, "_pending_task", None)
        if not pt:
            return False, None, text
        task = None
        for t in self.store.tasks:
            if t["id"] == pt["id"]:
                task = t
                break
        if task is None or task.get("done"):
            self._pending_task = None
            return False, None, text

        need_pri = pt.get("need_pri")
        need_dl = pt.get("need_dl")
        m = self._pri_re().search(text)
        time_m = self._dl_time_re().search(text)
        no_dl = bool(self._dl_no_re().search(text))
        # v1.9.4：优先用 parser 引擎解析回答（支持中文数字「八点」「八点半」
        # 「一刻」、相对天「明天/大后天/3天后」、月日「10月30日」、下周一…）；
        # 中文回答才走引擎，英文回答退回旧正则（am/pm 由它兜底）
        eng_time = None
        if re.search(r"[\u4e00-\u9fff]", text or ""):
            _t = (core.find_times(text or "") or [None])[0]
            if _t:
                _d = core.find_deadline_date(text or "")
                eng_time = {"hhmm": _t[0], "raw": _t[2],
                            "due": (_d[0].isoformat() if _d and _d[0] else None),
                            "off": _t[3] if len(_t) > 3 else 0}
                eng_time = self._smart_meridiem(text, eng_time)
        # 完全不像回答（没字母没时间也没说没有）→ 当普通输入处理。
        # 引擎解析出的时间也算「时间」（「明天下午三点」旧正则接不住，v1.9.5），
        # 但必须防住「晚上八点提醒我做20个俯卧撑」这种带动作的整句新任务：
        # 只有「整句就是时间」才算回答，否则交给新任务解析。
        if eng_time and not m and not time_m and not no_dl:
            if not self._is_pure_time_reply(text):
                return False, None, text
        if not m and not time_m and not no_dl and not eng_time:
            return False, None, text

        replies = []
        if m and need_pri:
            letter = (m.group(1) or m.group(0)).strip().upper()
            table = {"A": "pri_a", "B": "pri_b", "C": "pri_c", "D": "pri_d"}
            if letter not in table:
                low = m.group(0).lower()
                if "urgent" in low or "紧急" in low or "很急" in low:
                    letter = "A"
                elif "important" in low or "重要" in low:
                    letter = "B"
                elif "normal" in low or "一般" in low:
                    letter = "C"
                else:
                    letter = "D"
            scores = {"A": 95, "B": 75, "C": 55, "D": 30}
            task["score"] = scores[letter]
            task["manual"] = True
            replies.append(tr("pri_set", t=task["title"], p=tr(table[letter])))
            need_pri = False
        elif need_pri and (time_m or no_dl):
            # 只回答了时间：优先级保持默认，不再追问
            need_pri = False

        if eng_time and need_dl:
            # v1.9.4：parser 引擎结果优先（中文数字 / 半 / 一刻 / 月日 / 相对天全支持）
            hhmm = eng_time["hhmm"]
            due_iso = eng_time["due"]
            if not due_iso and eng_time["off"]:
                due_iso = (dt.date.today() +
                           dt.timedelta(days=eng_time["off"])).isoformat()
            # 回答里没带日期时不覆盖原句带入的 due_date（如「明天交推文」+「B 晚上8点」）
            due_iso = due_iso or task.get("due_date")
            new_dl = hhmm
            if due_iso:
                y2, m2, d2 = due_iso.split("-")
                new_dl = "%s月%s日 %s" % (int(m2), int(d2), hhmm)
            task["hhmm"] = hhmm
            task["due_date"] = due_iso
            task["deadline_txt"] = new_dl
            task["_from_raw"] = False
            self._push_undo({"kind": "deadline", "id": task["id"]})
            replies.append(tr("dl_set", t=task["title"], d=new_dl))
            need_dl = False
            # 过期检测：日期早于今天，或今天但时刻已过 → 走确认对话
            if self._is_expired(hhmm, due_iso):
                self._pending_expired = {"mode": "dl", "id": task["id"],
                                         "hhmm": hhmm, "due": due_iso}
                self._pending_q = "expired"
                task["hhmm"] = None
                task["due_date"] = None
                self.store.save()
                self.refresh_tasks(scroll_top=True)
                return True, tr("dl_expired", t=task["title"]), ""
        elif time_m and need_dl:
            # 旧正则兜底（引擎没命中时，主要覆盖英文 am/pm 形式）
            hh, mm = time_m.group(2), time_m.group(3)
            prefix_w = time_m.group(1) or ""
            day_off = {"明天": 1, "后天": 2}.get(prefix_w, 0)
            if day_off:
                task["due_date"] = (dt.date.today() +
                                    dt.timedelta(days=day_off)).isoformat()
            if time_m.group(4):   # 8pm 形式
                hh = time_m.group(4)
                mm = (time_m.group(5) or "").lstrip(":") or "0"
                h24 = int(hh) % 12 + (12 if time_m.group(6).lower() == "pm" else 0)
                hh = str(h24)
            elif prefix_w in ("下午", "晚上", "今晚", "傍晚") and int(hh) < 12:
                hh = str(int(hh) + 12)   # 晚上8点 → 20 点
            elif prefix_w == "中午" and int(hh) <= 2:
                hh = str(int(hh) + 12)
            hhmm = "%02d:%02d" % (int(hh) % 24, int(mm or 0) % 60)
            prefix = {"明天": "明天 ", "后天": "后天 "}.get(time_m.group(1) or "", "")
            new_dl = (prefix + hhmm).strip()
            changed = new_dl != (task.get("deadline_txt") or "")
            task["hhmm"] = hhmm
            task["deadline_txt"] = new_dl
            self._push_undo({"kind": "deadline", "id": task["id"]})
            # 任务是从原文里带出时间的（用户只是补答优先级），不必再念一遍
            if changed and not task.get("_from_raw"):
                replies.append(tr("dl_set", t=task["title"], d=task["deadline_txt"]))
            need_dl = False
            if self._is_expired(hhmm, task.get("due_date")):
                self._pending_expired = {"mode": "dl", "id": task["id"],
                                         "hhmm": hhmm, "due": task.get("due_date")}
                self._pending_q = "expired"
                task["hhmm"] = None
                self.store.save()
                self.refresh_tasks(scroll_top=True)
                return True, tr("dl_expired", t=task["title"]), ""
        elif no_dl and need_dl:
            replies.append(tr("dl_none", t=task["title"]))
            need_dl = False

        if not need_pri and not need_dl:
            self._pending_task = None
        else:
            pt["need_pri"], pt["need_dl"] = need_pri, need_dl
        self.store.save()
        self.refresh_tasks(scroll_top=True)
        reply_txt = (" ".join(replies) if i18n.is_en() else "，".join(replies))
        # 还差截止时间 → 只追问缺的那一半，别把标题再念一遍
        if need_dl:
            follow = tr("ask_dl_only",
                        hey=(tr("hey_name", name=self.nickname) if self.nickname else ""),
                        t=task["title"])
            if replies:
                sep = " " if i18n.is_en() else "，"
                reply_txt = reply_txt + sep + tr("ask_dl_short")
            else:
                reply_txt = follow
            return True, reply_txt, ""
        # 设了截止时间 → 顺势问提醒提前量
        if (not need_dl and task.get("hhmm")
                and task.get("remind_before") is None
                and not getattr(self, "_remind_asked_for", None) == task["id"]):
            self._remind_asked_for = task["id"]
            self._pending_remind = task["id"]
            self._pending_q = "remind"
            sep = " " if i18n.is_en() else "，"
            reply_txt += (sep if reply_txt else "")
            if reply_txt:
                reply_txt += self._ask_remind_text(task, short=True)
            else:
                reply_txt = self._ask_remind_text(task)
        return True, reply_txt, ""

    # ---------------- 「一点/两点…」歧义追问（v1.9.5）
    _AMBIG_HOURS = (1, 2, 3, 4, 5)

    def _ambig_meridiem(self, text):
        """无时段词且钟点在 1~5 点 → 可能是凌晨也可能是下午，返回原片段
        （带「凌晨/早上/上午/下午/晚上/中午/傍晚」等前缀的不算歧义）"""
        t = text or ""
        if not re.search(r"[\u4e00-\u9fff0-9]", t):
            return None
        # 整句里出现任何时段词就不算歧义（「下午一点」的「午」紧邻，
        # 单字符 lookbehind 看不全，所以直接查全句）
        if re.search(r"(凌晨|半夜|深夜|早上|早晨|上午|中午|下午|傍晚|晚上|今晚|明晚|夜里|早上)", t):
            return None
        m = re.search(
            r"(\d{1,2}|[一二三四五六七八九十]{1,3})\s*(?:点|时)", t)
        if not m:
            return None
        try:
            h = int(m.group(1))
        except ValueError:
            h = core._num(m.group(1)) if hasattr(core, "_num") else 0
        if h in self._AMBIG_HOURS:
            return m.group(0)
        return None

    def _ask_meridiem(self, seg, raw):
        """记下待确认的时段歧义，返回追问文案"""
        self._pending_meridiem = {"text": seg, "raw": raw}
        return tr("ask_meridiem", t=raw)

    def _resolve_meridiem(self, text):
        """用户回答「下午/凌晨」后，把任务按正确时段重新入库"""
        pm = getattr(self, "_pending_meridiem", None)
        self._pending_meridiem = None
        if not pm:
            return None
        low = (text or "").strip()
        if re.search(r"(下午|中午|傍晚|晚上|pm|PM)", low):
            prefix = "下午"
        elif re.search(r"(凌晨|半夜|深夜|早上|上午|am|AM)", low):
            # 凌晨/半夜/深夜 与 早上/上午 是两回事，保留用户自己的说法
            mm = re.search(r"(凌晨|半夜|深夜|早上|上午)", low)
            prefix = mm.group(1) if mm else "早上"
        elif re.search(r"(算了|不用|取消|不加|no\b)", low, re.I):
            # 放弃这条：清掉待答指针，避免悬空（v1.9.5）
            self._pending_q = None
            return tr("meridiem_skip")
        else:
            # 没听懂：原句再问一次
            self._pending_meridiem = pm
            return tr("ask_meridiem", t=pm["raw"])
        seg = re.sub(r"(\d{1,2}|[一二三四五六七八九十]{1,3})\s*(?:点|时)",
                     lambda mm: prefix + mm.group(0), pm["text"], count=1)
        # 直接走解析管线（不重复记一条用户消息，回复照常记录双语）
        self._pending_q = None          # 先清指针，respond 里若产生新追问会重设
        self._internal_input = True
        try:
            reply = self.respond(seg)
        finally:
            self._internal_input = False
            # respond 没产生新追问 → 指针必须归零，否则悬空（v1.9.5）
            if getattr(self, "_pending_q", None) == "meridiem":
                self._pending_q = None
        if reply:
            self.push("bot", reply)
        self.refresh_tasks(scroll_top=True)
        return tr("meridiem_ok", p=prefix, t=seg)

    # ---------------- 提醒提前量：选项按剩余时长裁剪（v1.9.5）
    def _remind_opts(self, task):
        """按「截止时刻 − 现在」剩余分钟数生成可选项：
        剩 40 分钟就只给 5/15/30，不给 1 小时；都不够则只给 E/F。
        返回 (选项文本, 映射 {字母: 分钟})"""
        left = None
        hhmm = task.get("hhmm")
        if hhmm:
            try:
                h, mi = hhmm.split(":")
                due = dt.date.today()
                dd = task.get("due_date")
                if dd:
                    y, mo, d = [int(x) for x in dd.split("-")]
                    due = dt.date(y, mo, d)
                tdue = dt.datetime(due.year, due.month, due.day, int(h), int(mi))
                left = int((tdue - dt.datetime.now()).total_seconds() // 60)
            except Exception:
                left = None
        cand = [(  "opt_5",  5, "A"), ("opt_15", 15, "B"),
                ( "opt_30", 30, "C"), ("opt_60", 60, "D")]
        parts, mapping = [], {}
        for key, mins, letter in cand:
            # 剩 40 分钟 → 30 分钟可以，60 分钟不行；留 1 分钟缓冲
            if left is None or left > mins:
                parts.append(tr(key))
                mapping[letter] = mins
        # E / F 的字母跟着压缩后的位置走，保证连号
        nxt = "ABCDEFG"[len(parts)]
        parts.append(tr("opt_off"))
        mapping[nxt] = 0
        nxt2 = "ABCDEFG"[len(parts)]
        at_txt = tr("opt_at") + tr("opt_at_hint")
        parts.append(at_txt)
        mapping[nxt2] = None          # None = 指定时刻
        self._remind_letter_map = mapping
        return " ".join(parts), left

    def _ask_remind_text(self, task, short=False):
        opts, left = self._remind_opts(task)
        if short:
            return tr("ask_remind_short", opts=opts)
        return tr("ask_remind", t=task["title"],
                  d=task.get("deadline_txt") or task.get("hhmm"), opts=opts)

    # ---------------- 透明度滑块
    def toggle_alpha_panel(self):
        """底栏「透明度」：就地弹一个滑块，拖完即时生效并记住"""
        p = getattr(self, "_alpha_panel", None)
        if p is not None and p.winfo_exists():
            p.destroy()
            self._alpha_panel = None
            return
        p = tk.Toplevel(self.root)
        p.overrideredirect(True)
        p.attributes("-topmost", True)
        p.configure(bg=C.LINE)
        try:
            p.attributes("-alpha", 0.97)
        except Exception:
            pass
        inner = tk.Frame(p, bg=C.BG)
        inner.pack(fill="both", expand=True, padx=1, pady=1)
        tk.Label(inner, text=tr("alpha_title"), bg=C.BG, fg=C.TEXT,
                 font=self.f_small).pack(anchor="w", padx=10, pady=(6, 0))
        row = tk.Frame(inner, bg=C.BG)
        row.pack(fill="x", padx=10, pady=(2, 8))
        val = tk.Label(row, text="", bg=C.BG, fg=C.ACCENT, font=self.f_small,
                       width=4, anchor="e")
        val.pack(side="right")
        sc = tk.Scale(row, from_=40, to=100, orient="horizontal",
                      showvalue=False, resolution=1, length=140,
                      bg=C.BG, fg=C.TEXT, troughcolor=C.LINE,
                      highlightthickness=0, bd=0,
                      activebackground=C.ACCENT, sliderrelief="flat")
        sc.set(int(round(getattr(self.store, "alpha", 0.88) * 100)))
        sc.pack(side="left", fill="x", expand=True)

        def _apply(_v=None):
            a = max(0.40, min(1.0, sc.get() / 100.0))
            try:
                self.root.attributes("-alpha", a)
            except Exception:
                pass
            # 时钟 / 日历跟着一起变，免得主窗透、副窗实
            cw = getattr(self, "_clock_win", None)
            if cw is not None and cw.winfo_exists():
                try:
                    cw.attributes("-alpha", min(1.0, a + 0.02))
                except Exception:
                    pass
            self.store.alpha = a
            val.config(text="%d%%" % int(round(a * 100)))
            # 文字加深：手动滑块优先，否则按透明度推导
            C.set_darken(self._effective_darken(a))
            self.debounce("alpha_recolor", self._recolor_soft, 300)
            # 右下角气泡透明度跟着一起变
            b = getattr(self, "_bubble", None)
            if b is not None and b.alive():
                try:
                    b.win.attributes("-alpha", a)
                except Exception:
                    pass
            self.debounce("alpha", lambda: self.store.save(), 600)

        sc.config(command=_apply)
        _apply()

        # —— 字体大小滑块（80%~130%） ——
        tk.Label(inner, text=tr("font_size"), bg=C.BG, fg=C.TEXT,
                 font=self.f_small).pack(anchor="w", padx=10)
        frow = tk.Frame(inner, bg=C.BG)
        frow.pack(fill="x", padx=10, pady=(2, 4))
        fval = tk.Label(frow, text="", bg=C.BG, fg=C.ACCENT, font=self.f_small,
                        width=4, anchor="e")
        fval.pack(side="right")
        fsc = tk.Scale(frow, from_=80, to=130, orient="horizontal",
                       showvalue=False, resolution=5, length=140,
                       bg=C.BG, fg=C.TEXT, troughcolor=C.LINE,
                       highlightthickness=0, bd=0,
                       activebackground=C.ACCENT, sliderrelief="flat")
        fsc.set(int(round(float(getattr(self.store, "font_scale", 1.0)) * 100)))
        fsc.pack(side="left", fill="x", expand=True)

        def _apply_font(_v=None):
            pct = fsc.get()
            fval.config(text="%d%%" % pct)
            self.store.font_scale = max(0.8, min(1.3, pct / 100.0))
            self._build_fonts()
            self.debounce("font_recolor", self._recolor_soft, 300)
            self.debounce("alpha", lambda: self.store.save(), 600)

        fsc.config(command=_apply_font)
        fval.config(text="%d%%" % fsc.get())

        # —— 字体深浅滑块（0~100%，拖过即接管自动推导） ——
        tk.Label(inner, text=tr("text_dark"), bg=C.BG, fg=C.TEXT,
                 font=self.f_small).pack(anchor="w", padx=10)
        drow = tk.Frame(inner, bg=C.BG)
        drow.pack(fill="x", padx=10, pady=(2, 8))
        dval = tk.Label(drow, text="", bg=C.BG, fg=C.ACCENT, font=self.f_small,
                        width=4, anchor="e")
        dval.pack(side="right")
        dsc = tk.Scale(drow, from_=0, to=100, orient="horizontal",
                       showvalue=False, resolution=5, length=140,
                       bg=C.BG, fg=C.TEXT, troughcolor=C.LINE,
                       highlightthickness=0, bd=0,
                       activebackground=C.ACCENT, sliderrelief="flat")
        dsc.set(int(round((getattr(self.store, "text_darken", None) or
                           self._effective_darken()) * 100)))
        dsc.pack(side="left", fill="x", expand=True)

        def _apply_dark(_v=None):
            dval.config(text="%d%%" % dsc.get())
            self.store.text_darken = dsc.get() / 100.0
            C.set_darken(self.store.text_darken)
            self.debounce("alpha_recolor", self._recolor_soft, 300)
            self.debounce("alpha", lambda: self.store.save(), 600)

        dsc.config(command=_apply_dark)
        dval.config(text="%d%%" % dsc.get())
        # 贴在「透明度」按钮上方（update_idletasks 只在必要时调一次，
        # 原来在无边框窗口里连续调用会触发重入，偶发界面僵住）
        try:
            bw = self.alpha_btn.winfo_width()
            bx = self.alpha_btn.winfo_rootx()
            by = self.alpha_btn.winfo_rooty()
            pw, ph = p.winfo_reqwidth(), p.winfo_reqheight()
            p.geometry("%dx%d+%d+%d" % (pw, ph, bx - pw + bw + 8, by - ph - 6))
        except Exception:
            p.geometry("%dx%d+%d+%d" % (240, 78, 200, 200))
        self._alpha_panel = p
        # 点别处自动收起：overrideredirect 窗口收不到 <FocusOut>（Windows 下尤其），
        # 所以改用「全局点一下」判定 —— 点在面板外就关。
        def _away(e):
            try:
                if not p.winfo_exists():
                    return
                wx, wy = p.winfo_rootx(), p.winfo_rooty()
                ww, wh = p.winfo_width(), p.winfo_height()
                if wx <= e.x_root <= wx + ww and wy <= e.y_root <= wy + wh:
                    return          # 点在面板内部，不动
            except Exception:
                pass
            try:                p.destroy()
            except Exception:
                pass
            self._alpha_panel = None
            self._unbind_alpha_away()

        def _bind_away(_e=None):
            # 走常驻路由器注册（Tk 无精确解绑，避免 unbind_all 误杀别的回调）
            self._hook_click("alpha_away", _away)

        self._unbind_alpha_away = lambda: self._unhook_click("alpha_away")
        # 延迟绑：否则「打开面板」的那一次点击会立刻把它关掉
        p.after(180, _bind_away)
        p.protocol("WM_DELETE_WINDOW", lambda: (p.destroy(), setattr(self, "_alpha_panel", None)))
        try:
            sc.focus_set()
        except Exception:
            pass

    def _effective_darken(self, alpha=None):
        """文字加深系数：手动「字体深浅」滑块优先；没设置时按透明度推导"""
        manual = getattr(self.store, "text_darken", None)
        if manual is not None:
            return round(max(0.0, min(1.0, manual)), 3)
        a = alpha if alpha is not None else getattr(self.store, "alpha", 0.88)
        return round(max(0.0, (0.88 - a)) * 0.65, 3)

    def _recolor_soft(self):
        """透明度变化后的轻量重刷（不动主题、不重建气泡）"""
        try:
            self._recolor_widgets()
            self.draw_head()
            self.draw_bar()
            self.render_messages()
            self.refresh_tasks()
            # 气泡跟随：透明度 + 字体大小变化后重测宽度（文本不截断）
            b = getattr(self, "_bubble", None)
            if b is not None and b.alive():
                b.refresh()
            cw = getattr(self, "_clock_win", None)
            if cw is not None and cw.winfo_exists():
                self._recolor_clock()
            self._recolor_calendar()
        except Exception:
            pass

    # ---------------- 全局点击路由
    # Tk 的 bind_all 没有精确解绑能力，unbind_all 会把所有 <Button-1> 回调
    # 一起清掉（包括编辑框的点击兜底），并且重复 add="+" 会让同一个回调
    # 越挂越多。这里只挂一个常驻路由，各功能按 key 注册/注销自己的处理。
    def _hook_click(self, key, fn):
        if not hasattr(self, "_click_hooks"):
            self._click_hooks = {}
        self._click_hooks[key] = fn
        self._ensure_click_router()

    def _unhook_click(self, key):
        hooks = getattr(self, "_click_hooks", None)
        if hooks:
            hooks.pop(key, None)

    def _ensure_click_router(self):
        if getattr(self, "_click_router_on", False):
            return
        self._click_router_on = True
        self.root.bind_all("<Button-1>", self._click_route, add="+")

    def _click_route(self, e):
        """常驻兜底：编辑框收编 + 各浮动面板的「点外面关闭」"""
        for fn in list(getattr(self, "_click_hooks", {}).values()):
            try:
                fn(e)
            except Exception:
                pass

    def _parse_remind_clock(self, text):
        import re as _re
        t = (text or "").strip()
        if not t:
            return None
        day = 1 if _re.search(r"(前一晚|前一天|头天|头一晚|前一天晚上)", t) else 0
        m = _re.search(r"(\d{1,2})\s*[:：]\s*(\d{1,2})", t)
        m_num = m
        per = ""
        if m:
            h, mi = int(m.group(1)), int(m.group(2))
        else:
            from parser import _num as _cn  # 复用中文数字解析（十一点 / 半点）
            m = _re.search(r"(上午|下午|中午|早上|早晨|晚上|傍晚|夜里|凌晨)?\s*"
                           r"(\d{1,2}|[零〇一二两三四五六七八九十]{1,3})\s*(?:点|时)"
                           r"(?:\s*半|\s*一刻|\s*(?:(\d{1,2})|([零〇一二两三四五六七八九十]{1,3}))\s*分?)?", t)
            if not m:
                return None
            h = _cn(m.group(2))
            if "半" in m.group(0):
                mi = 30
            elif "一刻" in m.group(0):
                mi = 15
            elif m.group(3):
                mi = int(m.group(3))
            elif m.group(4):
                mi = _cn(m.group(4))
            else:
                mi = 0
            per = m.group(1) or ""
            if per in ("下午", "晚上", "傍晚", "夜里") and h < 12:
                h += 12
            elif per == "中午" and h < 11:
                h += 12
            elif per == "凌晨" and h == 12:
                h = 0
        # v1.9.9.9：裸「三点二十分」没说时段（仅中文钟点；数字型 9:20 视为明确写法）
        # → 上午读数已过、下午读数还没到时按下午理解
        if m_num is None and per == "" and 1 <= h <= 11:
            _now = __import__("datetime").datetime.now()
            _nowm = _now.hour * 60 + _now.minute
            if (h * 60 + mi) <= _nowm < (h + 12) * 60 + mi:
                h += 12
        if not (0 <= h <= 23 and 0 <= mi <= 59):
            return None
        return "%02d:%02d" % (h, mi), day

    @staticmethod
    def _remind_at_text(hhmm, day):
        if i18n.is_en():
            return ("the night before at " + hhmm) if day else ("at " + hhmm)
        return ("前一晚 " + hhmm) if day else ("在 " + hhmm)

    def _maybe_ask(self, task, raw):
        """新任务加进来后，若缺优先级/截止时间信息就发问；返回回复或 None"""
        pz = self.p()
        import re as _re
        _raw = raw or ""
        # 「你认为该任务的优先级为…」是我们自己的提问回声，不能算用户表过态
        _echo = bool(_re.search(r"(优先级|重要性)\s*(为|是|怎么样|如何)|"
                                r"(你|您)(认为|觉得|看)", _raw))
        need_pri = not pz.has_priority_signal(_raw) and not _echo
        need_dl = not task.get("hhmm")
        if _re.search(r"(?<![A-Za-z])[ABCD](?![A-Za-z])", _raw, _re.I):
            need_pri = False     # 用户已用字母表态
        # 「晚上八点提醒我…」= 用户指定了一个时刻，本身就够明确了，
        # 不必再盘问优先级——直接问「提前多久提醒」，不打扰。
        if _re.search(r"(提醒我|叫我|通知我|到点)", _raw) and task.get("hhmm"):
            need_pri = False
        # 已经开始答别的任务了：清掉上一条残留的待答状态，别串台
        old = getattr(self, "_pending_task", None)
        if old and old.get("id") != task["id"]:
            self._pending_task = None
        if not need_pri and not need_dl:
            # 信息齐了：还差提醒提前量吗？
            if task.get("hhmm") and task.get("remind_before") is None:
                self._remind_asked_for = task["id"]
                self._pending_remind = task["id"]
                self._pending_q = "remind"
                return self._ask_remind_text(task)
            return None
        self._pending_task = {"id": task["id"], "need_pri": need_pri,
                              "need_dl": need_dl}
        self._pending_q = "pri"
        hey = tr("hey_name", name=self.nickname) if self.nickname else ""
        if need_pri and need_dl:
            return tr("ask_pri", hey=hey, t=task["title"])
        if need_pri:
            return tr("ask_pri_only", hey=hey, t=task["title"])
        return tr("ask_dl_only", hey=hey, t=task["title"])

    # ---------------- 首次见面：昵称 / 助手名
    @staticmethod
    def _taskish(s):
        """粗判一句像不像「派活儿」（给昵称流程用）：
        含动作动词、量词、日期词、或长度明显超出名字范围"""
        import re as _r
        if len(s or "") > 12:
            return True
        if _r.search(r"(帮我|记一下|提醒|完成|做好|准备|整理|交|写|发|买|去|看|读|做|"
                     r"开会|报告|作业|周报|邮件|分钟|小时|点|号|周|明天|后天|今天|"
                     r"每天|周末|之前|前)", s or ""):
            return True
        return False

    def _onboarding(self, text):
        """首轮引导：自我介绍 → 问昵称 → 使用指南。返回回复文本；已完成则返回 None
        v1.9.9.5：顺序改为「先说明我是谁，再问怎么称呼，答完给一份简短使用指南」"""
        s = (text or "").strip()
        stage = int(getattr(self.store, "setup_stage", 0) or 0)
        # 还没问过 → 第一句先自我介绍，再问称呼
        if stage == 0:
            self.store.setup_stage = 1
            self.store.save()
            bot = getattr(self.store, "bot_name", "") or (
                "小宁" if not i18n.is_en() else "Note")
            return tr("intro_first", bot=bot) + "\n" + tr("ask_user_name")
        if stage == 1:
            # 用户可能一上来就问「你是谁」，先答，别硬拽着问名字
            if core.SELF_RE.search(s) and len(s) <= 30 and not core.extract_name(s):
                bot = getattr(self.store, "bot_name", "") or (
                    "小宁" if not i18n.is_en() else "Note")
                return tr("intro_first", bot=bot) + "\n" + tr("ask_user_name")
            nm = core.extract_name(s)
            if not nm:
                return tr("ask_user_name_again")
            self.store.user_name = nm
            # v1.8.1：不再问「助手叫什么」——问完称呼直接开聊
            self.store.setup_stage = 3
            if not self.store.bot_name:
                self.store.bot_name = "小宁" if not i18n.is_en() else "Note"
            self.store.save()
            # v1.9.9.5：称呼记住后，附一份简短使用指南（含提醒说明）
            return tr("name_ok", name=nm) + "\n" + tr("usage_guide")
        return None

    def _intro_self(self):
        """回答「你是谁 / 介绍你自己」"""
        bot = getattr(self.store, "bot_name", "") or ("小宁" if not i18n.is_en() else "Note")
        nm = getattr(self.store, "user_name", "")
        if nm:
            return tr("intro_self", bot=bot, name=nm)
        return tr("intro_self_noname", bot=bot)

    @property
    def nickname(self):
        """给回复用的称呼（没设置就返回空串）"""
        return getattr(self.store, "user_name", "") or ""

    # ---------------- 撤回（v1.9.5）
    # 用户输错时间时，一句话撤回上一次的设置，不用翻聊天记录
    _UNDO_RE = None
    _UNDO_PAT = None

    def _undo_re(self):
        import re as _re
        if NoteApp._UNDO_RE is None:
            NoteApp._UNDO_RE = _re.compile(
                r"^\s*(撤回|撤销|退回|退回一下|撤消|重来|重输|重新输入|"
                r"改时间|改截止|时间错了|输错了|我打错了|打错了|"
                r"undo|revert)\s*[。.！!～~]*\s*$", _re.I)
        return NoteApp._UNDO_RE

    def _undo_pat(self):
        """宽松版撤回口语：撤一下（时间）/ 把时间撤了 / 时间去掉 / 不要这个时间了 (v1.9.9)"""
        import re as _re
        if NoteApp._UNDO_PAT is None:
            NoteApp._UNDO_PAT = _re.compile(
                r"^[\s，,]*(?:帮我|请|麻烦)?\s*"
                r"(?:把)?(?:这个|那个|刚才的?|刚才那个)?\s*(?:截止)?时间\s*"
                r"(?:撤|删|去掉|取消|清掉|清空|不要)(?:掉|了|一下)?\s*[。.！!～~]*\s*$|"
                r"^[\s，,]*(?:撤|删|取消|清|去掉)\s*(?:一下|掉)?\s*(?:这个|那个)?"
                r"(?:截止)?时间\s*(?:了|吧)?\s*[。.！!～~]*\s*$", _re.I)
        return NoteApp._UNDO_PAT

    def _match_undo(self, text):
        """识别撤回指令；返回 "deadline" / "task" / None

        v1.9.9 修复：以前光秃秃一句「撤回」一律当成「撤截止时间」，
        于是对一条本来就没有截止时间的任务说「撤回」，会得到
        「已经把【买牛奶】的截止时间撤掉了」这种凭空捏造的回复，
        任务本身也没被撤掉。现在改为：明确说了「撤回任务」才撤任务；
        只说「撤回」时看上一次操作是什么（_undo_last.kind）——
        上一次是新建任务就撤整个任务，否则才按撤时间处理。
        """
        import re as _re
        t = (text or "").strip()
        if not t or len(t) > 20:
            return None
        # 「撤回任务」「撤回待办」「撤回上一条」= 撤整个任务
        # v1.9.9.3：以前只认「任务」，说「撤回待办」会漏进解析器变成一条
        # 叫「撤回待办」的新任务
        if _re.search(r"(撤回|撤销|撤掉|退回|删掉|去掉)\s*(这个|那个|刚才|上一|这|最)?(条|个|的|一)?\s*(任务|待办|事项|条目)", t, _re.I):
            return "task"
        if self._undo_re().match(t) or self._undo_pat().match(t):
            rec = getattr(self, "_undo_last", None)
            # 没有任何可撤回的操作（刚启动 / 已经撤过一次）→ 别硬编一句话出来
            if not rec:
                return None
            # 话里点名了「时间/截止」→ 意图明确，直接按撤时间走，不看记录类型
            _explicit_time = bool(self._undo_pat().match(t)) or bool(
                _re.search(r"时间|截止|点钟|点儿", t))
            if rec.get("kind") == "remind_at" and not _explicit_time:
                return "remind_at"      # v1.9.9.9：撤回刚才设的提醒时刻
            if rec.get("kind") == "task" and not _explicit_time:
                return "task"
            if rec.get("kind") == "deadline":                # 记录里写明这次是「清空截止时间」且任务本来就没有时间 → 无可撤回
                if rec.get("hhmm") is None and rec.get("due") is None \
                        and rec.get("deadline_txt") is None and "hhmm" in rec:
                    return None
                task = None
                for x in self.store.tasks:
                    if x.get("id") == rec.get("id"):
                        task = x
                        break
                # 任务上压根没有截止时间，就别假装撤掉了
                if task is not None and not (task.get("hhmm") or task.get("due_date")) \
                        and not _explicit_time:
                    return None
            return "deadline"
        return None

    def _push_undo(self, rec):
        """记一条可撤回的操作（只留最近 1 条，避免语义混乱）"""
        self._undo_last = rec

    def _do_undo(self, kind):
        """执行撤回。kind=deadline 撤时间并重新追问；kind=task 撤掉整个任务"""
        # 先把所有待答状态清干净：撤回是一次「重新开始」
        self._pending_q = None
        self._pending_task = None
        self._pending_expired = None
        self._pending_remind = None
        self._pending_dup = None
        self._pending_meridiem = None
        rec = getattr(self, "_undo_last", None)
        task = None
        if rec:
            for t in self.store.tasks:
                if t["id"] == rec.get("id"):
                    task = t
                    break
        if kind == "task":
            if rec and rec.get("state") is not None and task is None:
                # 撤回「刚加进来」的任务：优先用记录里的索引位置还原
                pass
            if task is None:
                return tr("undo_none")
            self.store.tasks.remove(task)
            # v1.9.9.3：撤回 = 撤销这次录入，历史里的当日记录一并清掉
            # （与右键删除 delete_task 的行为保持一致），否则历史窗口里
            # 还躺着一条已被撤回的任务
            _t = task.get("title", "")
            if _t:
                self.store.purge_history({_t})
            self.store.save()
            self._undo_last = None
            try:
                if self._hist_win is not None and self._hist_win.winfo_exists():
                    self._render_history()
            except Exception:
                pass
            self.refresh_tasks(scroll_top=True)
            return tr("undo_task_done", t=task["title"])
        # kind == remind_at（v1.9.9.9）：退回刚才设定的提醒时刻，
        # 恢复旧设置并重新进入「提前多久提醒」问答
        if kind == "remind_at":
            if task is None:
                return tr("undo_none")
            prev = rec.get("prev") or {}
            task["remind_at"] = prev.get("remind_at")
            task["remind_day"] = prev.get("remind_day")
            task["remind_before"] = prev.get("remind_before")
            self.store.save()
            self.refresh_tasks(scroll_top=True)
            self._undo_last = None
            self._remind_asked_for = task["id"]
            self._pending_remind = task["id"]
            self._pending_q = "remind"
            return tr("undo_remind_done") + "\n" + self._ask_remind_text(task)
        # kind == deadline
        if task is None:
            return tr("undo_none")
        # v1.9.9：任务本来就没有截止时间，就不要谎称「撤掉了截止时间」
        if not (task.get("hhmm") or task.get("due_date")):
            self._undo_last = None
            return tr("undo_no_dl", t=task["title"])
        task["hhmm"] = None
        task["due_date"] = None
        task["deadline_txt"] = None
        task.pop("remind_before", None)
        self.store.save()
        self.refresh_tasks(scroll_top=True)
        self._undo_last = None
        # 重新走一遍截止时间追问，用户直接说新时间即可
        self._pending_task = {"id": task["id"], "need_pri": False, "need_dl": True}
        self._pending_q = "pri"
        return tr("undo_dl_done", t=task["title"])

    def respond(self, text):
        """生成回复，并处理任务增删"""
        # ① 首次见面：先问昵称，再问助手叫什么（问完之前不解析任务）
        onboarding = self._onboarding(text)
        if onboarding is not None:
            return onboarding

        # ② 「你是谁 / 介绍你自己」
        if core.SELF_RE.search(text or "") and len((text or "").strip()) <= 30:
            return self._intro_self()

        # ②b 给助手起名：「我希望你叫小宁同志」「你就叫小宁吧」
        m_bn = _BOT_NAME_RE.search(text or "")
        if m_bn:
            nm = (m_bn.group(1) or "").strip().strip("\"'“”‘’「」")
            if nm:
                nm = re.split(r"[，,。.!！?？；;\s]", nm)[0]
                nm = re.sub(r"(就行|就好|好了|便好|得了|吧|哦|呀|啊|啦|哈)$", "", nm) or nm
                self.store.bot_name = nm
                self.store.save()
                return tr("bot_name_ok", bot=nm)

        # ②c 撤回（v1.9.5）：元指令，优先级最高——必须早于所有追问路由，
        #     否则「撤回」会被当成上一个问题的回答吃掉
        _undo = self._match_undo(text)
        if _undo:
            return self._do_undo(_undo)
        # v1.9.9：一句干巴巴的「撤回」如果没东西可撤，也要给个交代，
        # 不能掉进解析器变成一条叫「撤回」的任务
        if self._undo_re().match((text or "").strip()):
            return tr("undo_none")

        # ②d 便签指令（v1.9.7）：对话里直接「记便签：xxx」→ 存进便签页
        m_note = re.match(r"^(?:记个?便签|便签|帮我记个?便签)[：:，,\s]\s*(.+)$",
                          (text or "").strip())
        if m_note and m_note.group(1).strip():
            self.add_note(m_note.group(1).strip()[:200])
            return None          # add_note 已播报，避免重复消息

        # ⓪ 最新问题优先（v1.9.5）：同时挂着多个待答状态时，回答只送给最近问的那一个，
        #    避免「不用」被优先级/提醒等旧问题吃掉，导致错配（用户反馈的串线 bug）
        q = getattr(self, "_pending_q", None)
        if q == "meridiem" and getattr(self, "_pending_meridiem", None):
            ans = self._resolve_meridiem(text)
            if ans is not None:
                return ans
        if q == "expired" and getattr(self, "_pending_expired", None):
            _ans = self._resolve_expired(text)
            if _ans is not None:
                return _ans
            # 返回 None：用户输的是新任务句，继续往下正常解析
        if q == "remind" and getattr(self, "_pending_remind", None):
            pass        # 落到下面原有的提醒回答分支
        elif q == "pri" and getattr(self, "_pending_task", None):
            pass        # 落到下面原有的优先级/截止回答分支

        # 上一轮在等用户选「提前多久提醒」
        pr = getattr(self, "_pending_remind", None)
        if pr:
            task = None
            for t in self.store.tasks:
                if t["id"] == pr:
                    task = t
                    break
            import re as _re_r
            # 只有「短答复」才算回答；像「晚上8点前做好新闻稿，A」这种长句
            # 应当按新任务解析，不能被提醒问答吞掉
            _s = text.strip()
            is_short = len(_s) <= 12
            # 明显的任务句（带动作/宾语）一律按新输入处理
            if is_short and _re_r.search(r"(做好|做完|完成|写|交|准备|整理|发|去|买|做|开|打|看|读)", _s) \
                    and len(_s) > 6:
                is_short = False
            m_r = _re_r.search(
                r"(?<![A-Za-z])([ABCDEF])(?![A-Za-z])|不用|无需|不用了|\bno\b|\bnone\b",
                text, _re_r.I) if is_short else None
            # 指定时刻：直接写「08:00」「前一晚21点」「早上7点半」
            at_min = self._parse_remind_clock(text) if is_short else None
            if task is not None and (m_r or at_min is not None):
                tok = (m_r.group(1) or "").strip().upper() if m_r else ""
                if tok == "F" and at_min is None:
                    return tr("ask_remind_at")     # 只想指定时刻，等下一句
                if at_min is not None:
                    self._pending_remind = None
                    # v1.9.9.9：记录旧提醒设置，说「撤回」可退回本问并重设
                    self._push_undo({"kind": "remind_at", "id": task["id"],
                                     "prev": {"remind_at": task.get("remind_at"),
                                              "remind_day": task.get("remind_day"),
                                              "remind_before": task.get("remind_before")}})
                    task["remind_at"] = at_min[0]          # "HH:MM"
                    task["remind_day"] = at_min[1]         # 0=当天 1=前一天
                    task["remind_before"] = None
                    self.store.save()
                    return tr("remind_at", t=task["title"],
                              d=self._remind_at_text(at_min[0], at_min[1]))
                self._pending_remind = None
                if tok == "E" or "不用" in text or "无需" in text \
                        or _re_r.search(r"\b(no|none)\b", text, _re_r.I):
                    task["remind_before"] = 0
                    reply = tr("remind_off", t=task["title"])
                else:
                    # 字母归属随「剩余时长裁剪」动态变化（v1.9.5），按映射取
                    lmap = getattr(self, "_remind_letter_map", None) \
                        or {"A": 5, "B": 15, "C": 30, "D": 60}
                    if tok in lmap and lmap[tok]:
                        mins = lmap[tok]
                    elif tok in lmap:          # 选到了「不用提醒」
                        mins = 0
                    elif "15" in text:
                        mins = 15
                    elif "30" in text:
                        mins = 30
                    elif "5" in text:
                        mins = 5
                    else:
                        mins = 5
                    if mins == 0:
                        task["remind_before"] = 0
                        self.store.save()
                        return tr("remind_off", t=task["title"])
                    task["remind_before"] = mins
                    task["remind_at"] = None
                    key = {5: "remind_5", 15: "remind_15",
                           30: "remind_30", 60: "remind_60"}[mins]
                    reply = tr("remind_set", t=task["title"], d=tr(key))
                self.store.save()
                return reply
            self._pending_remind = None    # 不是回答，按普通输入处理

        # 上一轮在等用户回答新任务的优先级/截止时间
        matched, reply, rest = self._apply_pri_answer(text)
        if matched:
            return reply
        text = rest or text

        # 上一轮在等用户确认「过期的截止时间」（v1.9.4）
        pe = getattr(self, "_pending_expired", None)
        if pe:
            return self._resolve_expired(text)

        # 上一轮在等用户确认「重复任务」
        pd = getattr(self, "_pending_dup", None)
        if pd:
            self._pending_dup = None
            if self._dup_ok_re().search(text):
                self._add_single(pd["title"], pd["hhmm"], pd["score"],
                                 pd["dur"], override=pd["new_title"])
                return tr("dup_added", title=pd["new_title"])
            # 其他回答：放弃确认，按普通输入继续解析

        pz = self.p()
        # 英文模式下用户输入中文：解析仍用中文引擎（否则识别不出），
        # 回复文案全部走英文 i18n（tr），标题保留用户原文
        if i18n.is_en() and re.search(r"[\u4e00-\u9fff]", text or ""):
            pz = core
        parsed_now = pz.parse_tasks(text)

        # 查询进度
        if pz.QUERY_RE.search(text) and not parsed_now:
            left = [x for x in self.store.tasks if not x.get("done")]
            if not left:
                return tr("left_none")
            top = sorted(left, key=lambda x: -x.get("score", 0))[0]
            return tr("left_some", n=len(left), title=top["title"])

        # 勾选意图
        if pz.DONE_RE.search(text) and len(text) <= 24:
            cand = [x for x in parsed_now if not pz.DONE_RE.search(x[0])]
            if cand:
                target = cand[0][0]
                for task in self.store.tasks:
                    if self._match(target, task["title"]):
                        if not task.get("done"):
                            task["done"] = True
                            task["done_at"] = dt.datetime.now().strftime("%H:%M")
                            self.store.save()
                            return self._praise(tr("done_ok", title=task["title"]))
                return tr("done_notfound", title=target)

        # 删除意图
        if pz.DEL_RE.search(text) and parsed_now:
            target = parsed_now[0][0]
            for i, task in enumerate(list(self.store.tasks)):
                if self._match(target, task["title"]):
                    self.store.tasks.pop(i)
                    self.store.save()
                    return tr("deleted", title=task["title"])

        if pz.GREET_RE.search(text) and len(text) <= 16:
            return self.greeting()
        if pz.THANKS_RE.search(text) and len(text) <= 16:
            return i18n.pick(random, "thanks")

        # 「天气预报说有雨」这类背景说明不是任务，从解析结果里剔掉
        parsed_now = [x for x in parsed_now if not self._is_tell_phrase(x[3])]

        parsed = parsed_now
        if not parsed:
            return i18n.pick(random, "no_parse")

        # 「一点/两点…五点」没说上午下午 → 先问清是凌晨还是下午（v1.9.5）
        if len(parsed) == 1:
            _amb = self._ambig_meridiem(text)
            if _amb:
                self._pending_q = "meridiem"
                return self._ask_meridiem(parsed[0][3] if len(parsed[0]) > 3 else text,
                                          _amb)

        added = 0
        new_tasks = []
        import re as _re_ad
        pending_expired_asked = False
        for item in parsed:
            title, hhmm, score = item[0], item[1], item[2]
            dur = item[4] if len(item) > 4 else None      # 时长（次要信息）
            # 输入里直接带了 A/B/C/D：提取出来打分，别留在标题里
            raw_seg = item[3] if len(item) > 3 else title
            # parser 可能把「，A」当评价语清掉，单任务时回退查完整输入
            letter_m = _re_ad.search(r"(?<![A-Za-z])([ABCD])(?![A-Za-z])",
                                     raw_seg, _re_ad.I)
            if letter_m is None and len(parsed) == 1:
                letter_m = _re_ad.search(r"(?<![A-Za-z])([ABCD])(?![A-Za-z])",
                                         text, _re_ad.I)
            if letter_m is None:
                letter_m = _re_ad.search(r"(?<![A-Za-z])([ABCD])(?![A-Za-z])",
                                         title, _re_ad.I)
            if letter_m:
                scores = {"A": 95, "B": 75, "C": 55, "D": 30}
                score = scores[letter_m.group(1).upper()]
                title = _re_ad.sub(r"[，,、；;]?\s*[ABCD]\s*$", "", title).strip() or title
            similar = self._find_similar(title)
            if similar is not None:
                # 有相似任务：不默默合并，先问用户（记次数区分）
                n = sum(1 for t in self.store.tasks
                        if self._same_title(t["title"], title)) + 1
                new_title = tr("dup_times_fmt", t=title, n=n)
                self._pending_dup = {"title": title, "new_title": new_title,
                                     "hhmm": hhmm, "score": score, "dur": dur}
                return tr("dup_ask", title=similar, new=new_title)
            dup = None
            for task in self.store.tasks:
                if task["title"] == title and not task.get("done"):
                    dup = task
                    break
            if dup:
                dup["hhmm"] = hhmm or dup.get("hhmm")
                dup["dur"] = dur or dup.get("dur")
                if not dup.get("manual"):
                    dup["score"] = max(dup.get("score", 0), score)
                continue
            # v1.9.4：截止时间已过（昨天/今天已过的时刻）→ 先别入库，问用户
            # v1.9.9：原先这里直接 return，会中断整批解析——同一句里第二条
            # 过期任务被静默丢弃，且在确认环节回「A」会被当成未听懂而卡死。
            # 改为：过期项排进队列，循环继续处理其余项，全部处理完再逐条确认。
            due_iso = item[6].isoformat() if (len(item) > 6 and item[6]) else None
            if self._is_expired(hhmm, due_iso):
                q_item = {
                    "task": {
                        "id": "%d%03d" % (int(time.time() * 1000),
                                          random.randint(0, 999)),
                        "title": title, "hhmm": hhmm, "dur": dur,
                        "score": score, "manual": False, "done": False,
                        "created": dt.datetime.now().strftime("%H:%M"),
                        "day": self.store._today(),
                        "repeat": item[5] if len(item) > 5 else None,
                        "due_date": due_iso,
                        "_from_raw": bool(hhmm),
                    },
                }
                _pe_now = getattr(self, "_pending_expired", None)
                if _pe_now and _pe_now.get("queue") is not None:
                    _pe_now["queue"].append(q_item)
                else:
                    q_item["queue"] = []
                    self._pending_expired = q_item
                    self._pending_expired["mode"] = "new"
                pending_expired_asked = True
                continue
            self.store.tasks.append({
                "id": "%d%03d" % (int(time.time() * 1000), random.randint(0, 999)),
                "title": title,
                "hhmm": hhmm,
                "dur": dur,
                "score": score,
                "manual": False,
                "done": False,
                "created": dt.datetime.now().strftime("%H:%M"),
                "day": self.store._today(),
                "repeat": item[5] if len(item) > 5 else None,
                "due_date": item[6].isoformat() if (len(item) > 6 and item[6]) else None,
                "_from_raw": bool(hhmm),   # 时间来自原句，回复里不必复述
            })
            # 截止日期：原文里的 明天/后天 → 记下具体日期（日历用）
            if not self.store.tasks[-1].get("due_date"):
                if "明天" in (raw_seg or ""):
                    self.store.tasks[-1]["due_date"] = (
                        dt.date.today() + dt.timedelta(days=1)).isoformat()
                elif "后天" in (raw_seg or ""):
                    self.store.tasks[-1]["due_date"] = (
                        dt.date.today() + dt.timedelta(days=2)).isoformat()
            added += 1
            new_tasks.append(self.store.tasks[-1])
            # 撤回点：记住刚加的这一条（「撤回任务」用）
            self._push_undo({"kind": "task", "id": self.store.tasks[-1]["id"]})
        self.store.save()
        # v1.9.9：本句里有过期任务 → 先逐条确认（确认完自动续问下一条）
        if pending_expired_asked and getattr(self, "_pending_expired", None):
            self._pending_q = "expired"
            _first = self._pending_expired.get("task") or {}
            _more = len(self._pending_expired.get("queue") or [])
            _msg = tr("dl_expired", t=_first.get("title", ""))
            if _more:
                _msg += tr("dl_expired_more", n=_more + 1)
            return _msg
        if added:
            # 缺优先级/截止时间 → 追问；信息齐 → 直接确认
            for t in new_tasks:
                q = self._maybe_ask(t, text)
                if q:
                    return q
            if i18n.is_en():
                names = ", ".join('"%s"' % p[0] for p in parsed[:3])
            else:
                names = "、".join("「%s」" % p[0] for p in parsed[:3])
            extra = tr("added_more", n=len(parsed)) if len(parsed) > 3 else ""
            hey = tr("hey_name", name=self.nickname) if self.nickname else ""
            return tr("added", hey=hey, names=names, extra=extra)
        return tr("duplicated")

    # ---------------- 任务列表
    def sorted_tasks(self):
        tasks = list(enumerate(self.store.tasks))
        undone = [x for x in tasks if not x[1].get("done")]
        done = [x for x in tasks if x[1].get("done")]
        undone.sort(key=lambda x: (-x[1].get("score", 0), x[1].get("hhmm") or "99:99", x[0]))
        done.sort(key=lambda x: x[1].get("done_at", ""), reverse=True)
        return undone + done

    def row_height(self):
        return 30

    def switch_mode(self, mode):
        if mode == self.list_mode:
            return
        self.list_mode = mode
        self.tab_todo.config(fg=C.ACCENT if mode == "task" else C.SUB)
        self.tab_note.config(fg=C.ACCENT if mode == "note" else C.SUB)
        self.entry.delete(0, "end")
        self.entry.insert(0, tr("input_ph") if mode == "task" else tr("note_ph"))
        self._compose_placeholder = True
        self.entry.config(fg=C.SUB)
        if mode == "note":
            self.refresh_notes()
        else:
            self.refresh_tasks()
        self.flash(tr("tab_note") if mode == "note" else tr("tab_todo"))

    def add_note(self, text):
        note = {"id": "%d%03d" % (int(time.time() * 1000), random.randint(0, 999)),
                "text": text[:200], "created": dt.datetime.now().strftime("%H:%M"),
                "day": self.store._today()}
        self.store.notes = (getattr(self.store, "notes", []) or []) + [note]
        self.store.save()
        self.refresh_notes()
        self.push_tr("bot", "note_saved")

    def _del_note(self, nid):
        self.store.notes = [n for n in (getattr(self.store, "notes", []) or [])
                            if n["id"] != nid]
        self.store.save()
        self.refresh_notes()
        self.flash(tr("note_deleted"))

    def _note_menu(self, e, nid):
        """便签右键菜单：编辑 / 删除（v1.9.8，与待办一致）"""
        m = tk.Menu(self.root, tearoff=0)
        row_y = None
        cv = self.list_cv
        for n_idx, n in enumerate(getattr(self.store, "notes", []) or []):
            if n["id"] == nid:
                row_y = 2 + n_idx * self.row_height()
                break
        m.add_command(label=tr("menu_edit"),
                      command=lambda: self._edit_note(nid, row_y if row_y is not None else 2))
        m.add_command(label=tr("menu_delete"), command=lambda: self._del_note(nid))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _note_del_show(self, nid, show):
        """悬停便签行时显示/隐藏该行的「删除」键（v1.9.4）"""
        try:
            cv = self.list_cv
            items = cv.find_withtag("nx_" + nid)
            for it in items:
                cv.itemconfigure(it, state="normal" if show else "hidden")
        except Exception:
            pass

    def _edit_note(self, nid, y):
        """单击便签 → 行内编辑（v1.9.8 与待办编辑完全同一套处理：
        之前缺了焦点收编/抑制窗口，编辑框刚弹出就被全局点击路由销毁，
        表现为「便签内容改不了」）"""
        note = None
        for n in (getattr(self.store, "notes", []) or []):
            if n["id"] == nid:
                note = n
                break
        if not note:
            return
        cv = self.list_cv
        w = cv.winfo_width()
        e = tk.Entry(cv, relief="flat", bg="white", fg=C.TEXT, font=self.f_task,
                     highlightthickness=1, highlightbackground=C.ACCENT)
        cv.create_window(14, y + self.row_height() / 2, window=e, anchor="w",
                         width=max(60, w - 46), height=22)
        e.insert(0, note["text"])
        e.select_range(0, "end")
        self._activate_window(focus_entry=False)   # 别抢编辑框的焦点
        e.focus_set()
        try:
            e.focus_force()
        except Exception:
            pass
        e.bind("<Button-1>", lambda ev: (e.focus_force(),
                                         e.icursor(e.index("@%d" % ev.x))))
        self._edit_entry = e                # 全局点击收编（同待办编辑）
        self._edit_opened_t = time.time()   # 刚弹出：放行同一次点击

        def commit(evt=None):
            try:
                if not e.winfo_exists():
                    return
            except Exception:
                return
            self._edit_entry = None
            val = e.get().strip()
            if val and val != note.get("text"):
                note["text"] = val
                self.store.save()
                self.flash(tr("note_saved"))
            try:
                e.destroy()
            except Exception:
                pass
            self.refresh_notes()
        e.bind("<Return>", commit)
        e.bind("<Escape>", lambda evt: (e.destroy(), self.refresh_notes()))
        e.bind("<FocusOut>", lambda evt: commit())

    def refresh_notes(self):
        """便签模式：卡片式列表"""
        cv = self.list_cv
        cv.delete("all")
        w = max(cv.winfo_width(), 60)
        rh = self.row_height()
        notes = getattr(self.store, "notes", []) or []
        fits = self.measure_many([n.get("text", "") for n in notes],
                                 self.f_task, w - 110)
        y = 2
        for idx, n in enumerate(notes):
            nid = n["id"]
            # 同色系：偶数行浅、奇数行更浅（主题派生，不再残留纸黄）
            bg = C.BG if idx % 2 == 0 else _mix(C.BG, C.ACCENT, 0.07)
            cv.create_rectangle(8, y, w - 8, y + rh - 3, fill=bg,
                                outline=_mix(C.ACCENT, "#FFFFFF", 0.55), width=1)
            txt = n.get("text", "")
            if not fits[idx] if idx < len(fits) else True:
                txt = self.ellipsize(txt, self.f_task, w - 110)
            # 整行热区（不透明填背景色）：悬停行内任意位置都能弹出删除键
            cv.create_rectangle(9, y + 1, w - 9, y + rh - 4, fill=bg,
                                outline="", tags=("nh_" + nid,))
            cv.create_text(16, y + (rh - 3) / 2, text=txt, anchor="w",
                           font=self.f_task, fill=C.TEXT, tags=("nh_" + nid,))
            cv.create_text(w - 16, y + (rh - 3) / 2, text=n.get("created", ""),
                           anchor="e", font=self.f_tiny, fill=C.SUB,
                           tags=("nh_" + nid,))
            # 删除键：悬停该行时浮现（自己也挂 nx_ 以便点得到），移开消失
            del_t = cv.create_text(w - 62, y + (rh - 3) / 2, text=tr("note_del"),
                                   anchor="e", font=self.f_tiny, fill="#B4463C",
                                   tags=("nx_" + nid,))
            cv.itemconfigure(del_t, state="hidden")
            cv.tag_bind("nh_" + nid, "<Button-1>",
                        lambda e, k=nid, yy=y: self._edit_note(k, yy))
            # 右键：菜单（编辑 / 删除），与待办一致；之前右键=直接删除，太危险
            cv.tag_bind("nh_" + nid, "<Button-3>",
                        lambda e, k=nid: self._note_menu(e, k))
            cv.tag_bind("nh_" + nid, "<Enter>",
                        lambda e, k=nid: self._note_del_show(k, True))
            cv.tag_bind("nh_" + nid, "<Leave>",
                        lambda e, k=nid: self._note_del_show(k, False))
            cv.tag_bind("nx_" + nid, "<Enter>",
                        lambda e, k=nid: self._note_del_show(k, True))
            cv.tag_bind("nx_" + nid, "<Leave>",
                        lambda e, k=nid: self._note_del_show(k, False))
            cv.tag_bind("nx_" + nid, "<Button-1>",
                        lambda e, k=nid: self._del_note(k))
            y += rh
        total = max(len(notes), 1) * rh
        cv.config(scrollregion=(0, 0, w, max(total + 4, cv.winfo_height())))
        cv.yview_moveto(0)
        self.counter.config(text=tr("counter", left=len(notes), done=0)
                            if False else "%s %d" % (tr("tab_note"), len(notes)))
        self.draw_bar()

    def refresh_tasks(self, scroll_top=False):
        if getattr(self, "list_mode", "task") == "note":
            return self.refresh_notes()
        cv = self.list_cv
        self.store.sync_history()
        cv.delete("all")
        w = max(cv.winfo_width(), 60)
        rh = self.row_height()
        ordered = self.sorted_tasks()
        # 先一次性批量算好每行标题是否放得下，避免逐行逐字量宽。
        # v1.9.7：每行按「时间 + 用时」算自己的可用宽度，与 draw_row 完全同口径
        # （旧版统一用 w-15-34，带时间的行实际可用更窄 → fits 高估 → 截断失真）
        avails = []
        for _, t in ordered:
            tx, dw, _dtxt = self._row_prefix_w(t, w)
            avails.append(max(24, w - tx - 46 - dw))
        fits = self.measure_many([t.get("title", "") for _, t in ordered],
                                 self.f_task, avails)
        total = 0
        y = 2
        for idx, (_, t) in enumerate(ordered):
            self.draw_row(cv, y, w, rh, t, idx,
                          fits[idx] if idx < len(fits) else True,
                          avail=avails[idx] if idx < len(avails) else None)
            y += rh
            total += rh
        cv.config(scrollregion=(0, 0, w, max(total + 4, cv.winfo_height())))
        if scroll_top:
            cv.yview_moveto(0)
        left = sum(1 for t in self.store.tasks if not t.get("done"))
        done = len(self.store.tasks) - left
        self.counter.config(text=tr("counter", left=left, done=done))
        self.draw_bar()
        # 日历视图打开时实时跟随任务变化（增删改/勾选都会走到这）
        cal = getattr(self, "_cal_win", None)
        if cal is not None and cal.winfo_exists() and getattr(self, "_cal_cv", None):
            self._draw_calendar()
        self._update_bubble()

    def _update_bubble(self):
        """未完成任务数变化后同步右下角气泡"""
        b = getattr(self, "_bubble", None)
        if b is not None and getattr(self.store, "bubble_enabled", True):
            try:
                b.refresh()
            except Exception:
                pass

    def _row_prefix_w(self, t, w):
        """一行里「时间 + 用时」占掉的宽度（draw_row 与 refresh_tasks 共用，
        保证 fits 判断与实际绘制同口径，v1.9.7）"""
        tx = 15
        hhmm = t.get("hhmm")
        if hhmm:
            tshow = self._tshow(t, hhmm)
            # 间隔 10px ≈ 一个半角字符宽（v1.9.9.3：用户反馈时间与标题之间
            # 空太多——draw_row 曾把这个宽度又加了一遍，间隔翻倍）
            tx += self.text_width(tshow, self.f_small) + 10
        dur = t.get("dur")
        dur_txt = tr("spent", d=dur) if dur else ""
        dw = self.text_width(dur_txt, self.f_tiny) if dur_txt else 0
        # 用时文字过长会把标题挤没了：封顶 88px，超出改省略
        # （v1.9.9.3：旧封顶 64px，「用时：1分钟」≈70px 也被截成省略号；
        #   另外绘制端右移到勾选框热区左侧，不再被盖尾巴）
        if dw > 88:
            dur_txt = self.ellipsize(dur_txt, self.f_tiny, 88)
            dw = 88
        return tx, dw, dur_txt

    def _tshow(self, t, hhmm):
        """时间列显示文本：非今天的任务在时间前带日期（v1.9.5）"""
        dd = t.get("due_date")
        if dd and dd != self.store._today():
            try:
                _y, _m, _d = [int(x) for x in dd.split("-")]
                return "%d/%d %s" % (_m, _d, hhmm)
            except Exception:
                return hhmm
        return hhmm

    def draw_row(self, cv, y, w, rh, task, idx, title_fits=True, avail=None):
        tid = task["id"]
        done = bool(task.get("done"))
        bg = C.BG if idx % 2 == 0 else _mix(C.BG, C.ACCENT, 0.07)
        cv.create_rectangle(0, y, w, y + rh, fill=bg, outline="",
                            tags=("row_" + tid,))
        # 优先级竖条
        label, color = core.priority_label(task.get("score", 0))
        if not done:
            cv.create_rectangle(6, y + 6, 9, y + rh - 6, fill=color, outline="")
        # 时间（主）+ 时长（次，更浅的小字）：与 refresh_tasks 同口径（v1.9.7）
        # v1.9.8：时间固定画在行首 15px —— 之前误用 _row_prefix_w 返回的
        # 「标题起点」当时间起点，带截止时间的行整体右移了一截（时间前留空）
        # v1.9.9.3：tx 已含「时间宽 + 间隔」，这里不能再加上一遍
        # （之前时间宽被算两次，标题与时间之间空出一大截）
        tx, dw, dur_txt = self._row_prefix_w(task, w)
        hhmm = task.get("hhmm")
        if hhmm:
            tshow = self._tshow(task, hhmm)
            cv.create_text(15, y + rh / 2, text=tshow, anchor="w",
                           font=self.f_small, fill=C.SUB if done else color)
        # 标题
        fnt = self.f_task
        title = task["title"]
        if avail is None:
            avail = max(24, w - tx - 46 - dw)
        if not title_fits:
            title = self.ellipsize(title, fnt, avail)
        cv.create_text(tx, y + rh / 2, text=title, anchor="w", font=fnt,
                       fill=C.DONE if done else C.TEXT,
                       tags=("t_" + tid,))
        if done:
            tw = self.text_width(title, fnt)
            cv.create_line(tx, y + rh / 2 + 1, tx + tw, y + rh // 2 + 1,
                           fill=C.DONE, width=1)
        # 用时（打勾框左侧）
        # v1.9.9.3：右端从 w-34 挪到 w-46。勾选框的整行点击热区（同底色
        # 不透明矩形）从 w-40 开始且绘制在后，会把用时文字的尾巴盖掉
        # ——「用时：1分钟」只剩「1分」就是它
        if dur_txt:
            cv.create_text(w - 46, y + rh / 2, text=dur_txt, anchor="e",
                           font=self.f_tiny, fill=C.DONE if done else C.SUB)
        # 完成勾选框（右侧）：图形只有 12px，但点击热区做成整行高度的一整块。
        # ⚠ 热区不能 fill=""：Tkinter 里全透明图形只有边框线可命中（内部点击穿透），
        #   这就是「只能点到两边」的原因。填与背景同色 → 视觉不可见但整块可点。
        bx2 = w - 16
        by = y + rh / 2
        s = 6
        cv.create_rectangle(bx2 - 24, y + 1, w - 1, y + rh - 1,
                            fill=bg, outline="", tags=("zk_" + tid,))
        cv.create_rectangle(bx2 - s, by - s, bx2 + s, by + s,
                                     outline=color if not done else C.DONE,
                                     width=1.6, fill="white",
                                     tags=("zk_" + tid,))
        if done:
            # 对勾线必须带 zk_ tag：它们画在白框上层，不带 tag 会吞掉
            # 方框中心的点击（「完成过的任务点不动」的根因，v1.9.7）
            cv.create_line(bx2 - s + 1.5, by, bx2 - 1, by + s - 1.5,
                           fill=color, width=1.8, tags=("zk_" + tid,))
            cv.create_line(bx2 - 1, by + s - 1.5, bx2 + s - 1, by - s + 1.5,
                           fill=color, width=1.8, tags=("zk_" + tid,))
        cv.tag_bind("zk_" + tid, "<Button-1>", lambda e, k=tid: self.toggle_done(k))
        cv.tag_bind("zk_" + tid, "<Enter>",
                    lambda e: cv.config(cursor="hand2"))
        cv.tag_bind("zk_" + tid, "<Leave>",
                    lambda e: cv.config(cursor=""))
        # 标题点击：单击编辑，双击完成
        cv.tag_bind("t_" + tid, "<Button-1>", lambda e, k=tid, yy=y: self.begin_edit(k, yy))
        cv.tag_bind("t_" + tid, "<Button-3>", lambda e, k=tid: self.row_menu(e, k))
        # v1.9.7：整行任意位置都能右键弹菜单（以前必须对准标题文字）
        cv.tag_bind("row_" + tid, "<Button-3>", lambda e, k=tid: self.row_menu(e, k))

    def toggle_done(self, tid):
        changed = False
        for t in self.store.tasks:
            if t["id"] == tid:
                t["done"] = not t.get("done")
                t["done_at"] = dt.datetime.now().strftime("%H:%M") if t["done"] else ""
                if t["done"]:
                    changed = True
                    task = dict(t)
                break
        self.store.save()
        self.refresh_tasks()
        if changed:
            left = len([x for x in self.store.tasks if not x.get("done")])
            q = self.quote_on_complete(task, left)
            if q:
                self.push("bot", q)

    def _praise(self, text):
        """口语勾选任务时：不再附加哲言（太冗长），全部完成才补一句鼓励"""
        done, total, ratio = self.progress_state()
        if total and done >= total:
            text += "\n" + self.encourage(total)
        return text

    # ---------------- 语言
    @staticmethod
    def p():
        """当前语言的解析器"""
        return core_en if i18n.is_en() else core

    def app_name(self):
        return i18n.t("app_name")

    def theme_label(self, theme_id):
        names = i18n.t("theme_names")
        for i, tid in enumerate(palette.ids()):
            if tid == theme_id:
                return names[i] if i < len(names) else theme_id
        return theme_id

    def encourage(self, seed=0):
        pool = i18n.t("encourage")
        return pool[seed % len(pool)]

    @staticmethod
    def _match(target, title):
        """目标文本与任务标题是否指同一件事（大小写无关）"""
        a, b = (target or "").lower(), (title or "").lower()
        return bool(a) and bool(b) and (a in b or b in a)

    def toggle_lang(self):
        new = "en" if not i18n.is_en() else "zh"
        self.switch_lang(new)

    def switch_lang(self, code, announce=True):
        i18n.set_lang(code)
        self.store.lang = code
        self.store.save()
        self.refresh_labels()
        # 时钟窗口的文字在创建时生成，语言变了就重建（几何/计时状态保留）
        cw = getattr(self, "_clock_win", None)
        if cw is not None and cw.winfo_exists():
            self._save_clock_geom()
            # 先把计时状态存下来（_close_clock 会把控件置空）
            sw_running = self._sw_running
            sw_base = self._sw_base
            sw_t0 = getattr(self, "_sw_t0", 0.0)
            sw_task = getattr(self, "_sw_task", None)
            cd_until, cd_secs = getattr(self, "_cd_until", None), getattr(self, "_cd_secs", 60.0)
            cd_left = getattr(self, "_cd_left", None)
            cd_total = getattr(self, "_cd_total", None)
            self._close_clock()
            self.open_clock()
            # 再灌回去
            self._sw_running, self._sw_base = sw_running, sw_base
            self._sw_t0 = time.time() - (sw_t0 and (time.time() - sw_t0) or 0.0) \
                if sw_running else sw_t0
            self._sw_task = sw_task
            self._cd_until, self._cd_secs = cd_until, cd_secs
            self._cd_left, self._cd_total = cd_left, cd_total
            if sw_running:
                self._setw("_sw_btn", text=tr("clock_pause"))
            if sw_task:
                for t in self.store.tasks:
                    if t["id"] == sw_task:
                        self._link_task(t["id"], t["title"])
                        break
        if announce:
            self.flash("Language: English" if code == "en" else "界面已切换到中文")

    def refresh_labels(self):
        """把静态控件文字按当前语言刷一遍"""
        self.root.title(self.app_name() + "  v" + VERSION)
        self.send_btn.configure(text=tr("send"))
        self.clear_btn.configure(text=tr("clear_done"))
        self.tab_todo.configure(text=tr("tab_todo"))
        self.tab_note.configure(text=tr("tab_note"))
        self.hist_btn.configure(text=tr("history_btn"))
        self.clock_btn.configure(text=tr("clock_btn"))
        try:
            self.cal_btn.configure(text=tr("cal_btn"))
            self.alpha_btn.configure(text=tr("alpha_btn"))
            self.bubble_btn.configure(text=tr("bubble_btn"))
        except Exception:
            pass
        self.f_note.configure(text=self.today_text())
        # 底部哲言要随语言换：英文模式显示英文那句，中文模式显示中文那句
        self.restore_quote()
        if self._compose_placeholder:
            self.entry.delete(0, "end")
            self.entry.insert(0, tr("input_ph"))
        self.draw_head()
        self.draw_bar()
        self.refresh_tasks()
        self.render_messages()
        if self._hist_win is not None and self._hist_win.winfo_exists():
            self._hist_win.title(tr("hist_title") + " · " + self.app_name())
            self._render_history()
        if self._theme_win is not None and self._theme_win.winfo_exists():
            self._theme_win.destroy()
            self._theme_win = None

    def today_text(self):
        d = dt.date.today()
        if i18n.is_en():
            md = "%s %d" % (i18n.t("month_names")[d.month - 1], d.day)
        else:
            md = "%d月%d日" % (d.month, d.day)
        return tr("today_fmt", date=md)

    def begin_edit(self, tid, y):
        task = None
        for t in self.store.tasks:
            if t["id"] == tid:
                task = t
                break
        if not task:
            return
        cv = self.list_cv
        w = cv.winfo_width()
        e = tk.Entry(cv, relief="flat", bg="white", fg=C.TEXT, font=self.f_task,
                     highlightthickness=1, highlightbackground=C.ACCENT)
        item = cv.create_window(14, y + self.row_height() / 2, window=e, anchor="w",
                                width=max(60, w - 46), height=22)
        self._edit_item = item
        e.insert(0, task["title"])
        e.select_range(0, "end")
        self._activate_window(focus_entry=False)   # 别抢编辑框的焦点（v1.9.7）
        e.focus_set()
        try:
            e.focus_force()                        # Windows 上确保键入进编辑框
        except Exception:
            pass
        e.bind("<Button-1>", lambda ev: (e.focus_force(),
                                         e.icursor(e.index("@%d" % ev.x))))
        self._edit_entry = e      # 全局点击收编（见 _global_edit_click）
        self._edit_opened_t = time.time()   # 刚弹出：放行同一次点击（v1.9.3）

        def commit(evt=None):
            # Return 与 FocusOut 都会触发：Entry 已销毁就立即退出，
            # 否则第二次进来会拿失效控件再刷一遍列表（偶发「点了没反应」）。
            try:
                if not e.winfo_exists():
                    return
            except Exception:
                return
            self._edit_entry = None
            val = e.get().strip()
            if val:
                _old = task.get("title", "")
                task["title"] = val
                if not task.get("manual"):
                    task["score"] = core.score_task(val, val, task.get("hhmm"))
                # v1.9.9.5：改名后历史里不能留着旧名字（历史按标题合并，
                # 旧标题行会被永久遗留）。清掉旧行、按新名字重新归档。
                if _old and _old != val:
                    self.store.purge_history({_old})
                    self.store.sync_history()
                self.store.save()
            try:
                e.destroy()
            except Exception:
                pass
            self.refresh_tasks()

        def cancel(evt=None):
            self._edit_entry = None
            try:
                if e.winfo_exists():
                    e.destroy()
            except Exception:
                pass
            self.refresh_tasks()

        e.bind("<Return>", commit)
        e.bind("<FocusOut>", commit)
        e.bind("<Escape>", cancel)

    def _global_edit_click(self, ev):
        """编辑标题期间点了别处：无边框窗口在 Windows 上常收不到 FocusOut，
        Entry 会一直悬在画布上层吞掉后续点击（表现为「打勾点不动」）。
        这里全局兜底：点在编辑框外就先收起编辑。"""
        # 编辑框刚因这次点击弹出（bind_all 的路由器在同一事件里晚于画布绑定
        # 执行），跳过这一次，否则框刚出现就被立刻收走（v1.9.3 修复）。
        if time.time() - getattr(self, "_edit_opened_t", 0.0) < 0.25:
            return
        e = getattr(self, "_edit_entry", None)
        if e is None:
            return
        try:
            if not e.winfo_exists():
                self._edit_entry = None
                return
            ex, ey = e.winfo_rootx(), e.winfo_rooty()
            ew, eh = e.winfo_width(), e.winfo_height()
        except Exception:
            return
        if ex - 2 <= ev.x_root <= ex + ew + 2 and ey - 2 <= ev.y_root <= ey + eh + 2:
            return
        # 点在编辑框外：收起（保存）编辑
        self._edit_entry = None
        try:
            val = e.get().strip()
            self._finish_edit_entry(e, val)
        except Exception:
            pass

    def _finish_edit_entry(self, e, val):
        """把编辑框的值写回任务并刷新（_global_edit_click 的收尾）"""
        item = getattr(self, "_edit_item", None)
        target = None
        if item is not None:
            try:
                info = self.list_cv.coords(item)   # (x, y)
                cy = info[1] if info else -1
            except Exception:
                cy = -1
            if cy >= 0:
                rh = self.row_height()
                idx = int((cy - 2) // rh)
                ordered = self.sorted_tasks()
                if 0 <= idx < len(ordered):
                    target = ordered[idx][1]
        try:
            e.destroy()
        except Exception:
            pass
        if target is not None and val and val != target["title"]:
            _old = target.get("title", "")
            target["title"] = val
            if not target.get("manual"):
                target["score"] = core.score_task(val, val, target.get("hhmm"))
            # v1.9.9.5：改名同步清历史旧行（同 begin_edit 的 commit）
            if _old:
                self.store.purge_history({_old})
                self.store.sync_history()
            self.store.save()
        self.refresh_tasks()

    def row_menu(self, e, tid):
        task = None
        for t in self.store.tasks:
            if t["id"] == tid:
                task = t
                break
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label=tr("menu_toggle"), command=lambda: self.toggle_done(tid))
        # 显式入口：就地编辑任务内容（v1.9.5）
        m.add_command(label=tr("menu_edit"),
                      command=lambda: self._menu_edit(tid))
        # 手动调整优先级
        sub = tk.Menu(m, tearoff=0)
        for lv in (4, 3, 2, 1):
            label = core.priority_label(lv * 25 - 5)[0]
            # 只显示档位名，不再带分数（v1.9.5）
            sub.add_command(label=label,
                            command=lambda s=lv * 25 - 5: self.set_priority(tid, s))
        if task is not None and task.get("manual"):
            sub.add_separator()
            sub.add_command(label=tr("menu_auto"), command=lambda: self.set_priority(tid, None))
        m.add_cascade(label=tr("menu_priority"), menu=sub)
        m.add_separator()
        m.add_command(label=tr("menu_delete"), command=lambda: self.delete_task(tid))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    def _menu_edit(self, tid):
        """右键「编辑内容」：定位到该行并打开行内编辑框"""
        y = 2
        # sorted_tasks() 返回 [(原索引, 任务dict), ...]，第二个才是任务本身
        for _idx, _orig, t in [(i, o, tk) for i, (o, tk) in enumerate(self.sorted_tasks())]:
            if t.get("id") == tid:
                self.begin_edit(tid, y)
                return
            y += self.row_height()

    def set_priority(self, tid, score):
        """手动设定或恢复（score=None）优先级；手动的不会被后续自动打分覆盖"""
        for t in self.store.tasks:
            if t["id"] == tid:
                if score is None:
                    t["score"] = core.score_task(t["title"], t["title"], t.get("hhmm"))
                    t["manual"] = False
                else:
                    t["score"] = score
                    t["manual"] = True
                break
        self.store.save()
        self.refresh_tasks()
        self.diag("手动设优先级 tid=%s score=%s" % (tid, score))

    def delete_task(self, tid):
        # v1.9.8：手动删除的任务从历史里一并清掉（按标题匹配所有天），
        # 之前只删待办，历史窗口里还躺着
        titles = set()
        for t in self.store.tasks:
            if t["id"] == tid:
                titles.add(t.get("title", ""))
        self.store.tasks = [t for t in self.store.tasks if t["id"] != tid]
        if titles:
            self.store.purge_history(titles)
        self.store.save()
        self.refresh_tasks()

    def clear_done(self):
        n = len([t for t in self.store.tasks if t.get("done")])
        if not n:
            self.flash(tr("no_cleared"))
            return
        self.store.tasks = [t for t in self.store.tasks if not t.get("done")]
        self.store.save()
        self.refresh_tasks()
        self.flash(tr("cleared_n", n=n))

    def on_list_wheel(self, e, direction=None):
        if direction is None:
            direction = -1 if getattr(e, "delta", 0) > 0 else 1
        self.list_cv.yview_scroll(direction, "units")

    # ---------------- 历史窗口
    # ---------------- 时钟 / 正计时 / 倒计时（v1.3.8）
    def _setw(self, attr, **kw):
        """安全地改时钟里的某个控件：窗口已关/控件已销毁就安静跳过。
        此前多处直接 self._xxx.config(...)，时钟一关就抛 TclError，
        表现为「某个按钮点了没反应」或整个心跳停掉。"""
        w = getattr(self, attr, None)
        if w is None:
            return False
        try:
            if not w.winfo_exists():
                return False
            w.config(**kw)
            return True
        except Exception:
            return False

    def open_clock(self):
        win = getattr(self, "_clock_win", None)
        if win is not None and win.winfo_exists():
            # 关闭：计时状态要留住（倒计时转后台心跳继续跑）
            self._close_clock()
            return
        win = tk.Toplevel(self.root)
        self._clock_win = win
        win.title(tr("clock_title"))
        win.configure(bg=C.BG)
        geom = getattr(self.store, "clock_geom", None) or "260x220+120+120"
        try:
            win.geometry(geom)
        except Exception:
            win.geometry("260x220+120+120")
        win.minsize(220, 180)
        win.attributes("-topmost", True)
        win.attributes("-alpha", min(1.0, getattr(self.store, "alpha", 0.88) + 0.02))
        self._clock_top = tk.BooleanVar(value=True)
        self._clock_widgets = []          # 主题换色用
        self._clock_fs = 0                # 已应用的时钟字号（变化才重设）
        # 计时状态只在「首次创建」时初始化；关掉时钟再打开（或切语言重建）
        # 之后由调用方回灌，不能在这里无条件清零，否则倒计时/关联任务会丢。
        if not getattr(self, "_clock_inited", False):
            self._sw_running = False
            self._sw_t0 = 0.0
            self._sw_base = 0.0
            self._sw_task = None              # 关联的任务 id
            self._cd_until = None
            self._cd_secs = 60.0              # 上次倒计时的秒数（重新计时用）
            self._cd_left = None              # 暂停时剩余秒数（v1.9.9.8）
            self._cd_total = None             # 已设定的总时长（v1.9.9.8）
            self._clock_inited = True
        self._cd_unit = tk.StringVar(value=tr("clock_min"))

        # 当前时间（常显，字号随窗口宽高缩放，充满剩余空间）
        self._clock_now = tk.Label(win, text="", bg=C.BG, fg=C.TEXT,
                                   font=(self.f_ui, 26, "bold"))
        self._clock_widgets.append(self._clock_now)

        # 正计时 + 关联任务
        swf = tk.Frame(win, bg=C.BG)
        swf.pack(side="top", fill="x", padx=10, pady=(6, 0))
        self._clock_widgets.append(swf)
        self._sw_lbl = tk.Label(swf, text=tr("clock_sw") + "  00:00",
                                bg=C.BG, fg=C.TEXT, font=(self.f_ui, 12))
        self._sw_lbl.pack(side="left")
        self._clock_widgets.append(self._sw_lbl)
        self._link_lbl = tk.Label(swf, text="", bg=C.BG, fg=C.SUB, font=self.f_tiny)
        self._link_lbl.pack(side="left", padx=(6, 0))
        self._clock_widgets.append(self._link_lbl)
        mk = tk.Menubutton(swf, text=tr("clock_link"), bg=C.ROW2, fg=C.TEXT,
                           relief="flat", font=self.f_tiny, padx=5)
        mk.pack(side="right", padx=(4, 0))
        self._clock_widgets.append(mk)
        self._fin_btn = tk.Button(swf, text=tr("clock_finish"), bg=C.ROW2, fg=C.TEXT,
                                  relief="flat", font=self.f_tiny, padx=6,
                                  command=self._sw_finish,
                                  activebackground=C.ACCENT,
                                  activeforeground="white")
        # 关联任务后才显示
        self._clock_widgets.append(self._fin_btn)
        menu = tk.Menu(mk, tearoff=0, bg=C.BG, fg=C.TEXT)
        menu.add_command(label=tr("clock_min") if False else "—", state="disabled")
        for t in self.store.tasks:
            if not t.get("done"):
                menu.add_command(label=t["title"],
                                 command=lambda tid=t["id"], tt=t["title"]:
                                 self._link_task(tid, tt))
        mk.config(menu=menu)
        for txt, fn in ((tr("clock_start"), self._sw_toggle),
                        (tr("clock_reset"), self._sw_reset)):
            b = tk.Button(swf, text=txt, bg=C.ROW2, fg=C.TEXT, relief="flat",
                          font=self.f_tiny, padx=6, command=fn,
                          activebackground=C.ACCENT, activeforeground="white")
            b.pack(side="right", padx=(4, 0))
            self._clock_widgets.append(b)
            if fn == self._sw_toggle:
                self._sw_btn = b

        # 倒计时：数值 + 单位（分钟/小时）+ 快捷档
        cdf = tk.Frame(win, bg=C.BG)
        cdf.pack(side="top", fill="x", padx=10, pady=(8, 0))
        self._clock_widgets.append(cdf)
        self._cd_lbl = tk.Label(cdf, text=tr("clock_cd") + "  --:--",
                                bg=C.BG, fg=C.TEXT, font=(self.f_ui, 12))
        self._cd_lbl.pack(side="left")
        self._clock_widgets.append(self._cd_lbl)
        self._cd_btn = tk.Button(cdf, text=tr("clock_start"), bg=C.ROW2, fg=C.TEXT,
                                 relief="flat", font=self.f_tiny, padx=6,
                                 command=self._cd_toggle,
                                 activebackground=C.ACCENT, activeforeground="white")
        self._cd_btn.pack(side="right", padx=(4, 0))
        self._clock_widgets.append(self._cd_btn)
        # v1.9.9.8：清零按钮——停掉倒计时并恢复到已设定的完整时长，方便重设
        self._cd_rst = tk.Button(cdf, text=tr("clock_reset"), bg=C.ROW2, fg=C.TEXT,
                                 relief="flat", font=self.f_tiny, padx=6,
                                 command=self._cd_reset,
                                 activebackground=C.ACCENT, activeforeground="white")
        self._cd_rst.pack(side="right", padx=(4, 0))
        self._clock_widgets.append(self._cd_rst)
        om = tk.Menubutton(cdf, text=tr("clock_min"), bg=C.ROW2, fg=C.TEXT,
                           relief="flat", font=self.f_tiny, padx=5)
        self._clock_widgets.append(om)
        umenu = tk.Menu(om, tearoff=0, bg=C.BG, fg=C.TEXT)
        def _switch_unit(new_unit):
            # 先用旧单位把输入框值换算成秒，再换成新单位显示
            secs = self._cd_unit_secs()
            self._cd_unit.set(new_unit)
            om.config(text=new_unit)
            if secs is not None:
                self._cd_spin.delete(0, "end")
                self._cd_spin.insert(0, self._fmt_unit_input(secs))

        for _u in (tr("clock_min"), tr("clock_hr"), tr("clock_sec")):
            umenu.add_command(label=_u,
                              command=lambda u=_u: _switch_unit(u))
        om.config(menu=umenu)
        om.pack(side="right")
        self._cd_unit_btn = om
        self._cd_spin = tk.Spinbox(cdf, from_=1, to=999, width=4,
                                   bg=C.INPUT_BG, fg=C.TEXT, relief="flat",
                                   buttonbackground=C.ROW2, font=self.f_small)
        self._cd_spin.pack(side="right", padx=(0, 4))
        self._clock_widgets.append(self._cd_spin)
        quick = tk.Frame(win, bg=C.BG)
        quick.pack(side="top", fill="x", padx=10, pady=(4, 0))
        self._clock_widgets.append(quick)
        for mins in (5, 25, 45):
            b = tk.Button(quick, text="%d %s" % (mins, tr("clock_min")),
                          bg=C.ROW2, fg=C.TEXT, relief="flat", font=self.f_tiny,
                          padx=5, command=lambda m=mins: self._cd_quick(m),
                          activebackground=C.ACCENT, activeforeground="white")
            b.pack(side="left", padx=(0, 4))
            self._clock_widgets.append(b)

        # 置顶开关 + 铃声选择
        bar = tk.Frame(win, bg=C.BG)
        bar.pack(side="bottom", fill="x", padx=10, pady=(0, 6))
        self._clock_widgets.append(bar)
        cb = tk.Checkbutton(bar, text=tr("clock_top"), variable=self._clock_top,
                            bg=C.BG, fg=C.SUB, font=self.f_tiny, relief="flat",
                            highlightthickness=0, activebackground=C.BG,
                            command=lambda: win.attributes(
                                "-topmost", self._clock_top.get()))
        cb.pack(side="left")
        self._clock_widgets.append(cb)
        bm = tk.Menubutton(bar, text=tr("clock_bell"), bg=C.ROW2, fg=C.SUB,
                           relief="flat", font=self.f_tiny, padx=5)
        bm.pack(side="right")
        self._clock_widgets.append(bm)
        bmenu = tk.Menu(bm, tearoff=0, bg=C.BG, fg=C.TEXT)
        for mid, zh, en, _cands in self.BELL_SOUNDS:
            bmenu.add_command(label=zh if not i18n.is_en() else en,
                              command=lambda m=mid: self._set_bell(m))
        bm.config(menu=bmenu)

        # 当前时间最后 pack，用 expand 充满中间所有剩余空间
        self._clock_now.pack(side="top", expand=True, fill="both")

        # 关闭时记住位置大小；拖动/缩放结束也记
        win.protocol("WM_DELETE_WINDOW", self._close_clock)
        win.bind("<Configure>", lambda e: self.debounce("clockgeom", self._save_clock_geom, 400))
        # 重建后把按钮/标签文字同步到真实计时状态（否则会显示「开始」但其实在跑）
        try:
            self._setw("_sw_btn", text=tr("clock_pause") if self._sw_running
                                else tr("clock_start"))
            if self._cd_until:
                left = max(0, int(self._cd_until - time.time()))
                mm, ss = divmod(left, 60)
                self._setw("_cd_lbl", text="%s  %02d:%02d" % (tr("clock_cd"), mm, ss))
                self._setw("_cd_btn", text=tr("clock_pause"))
            elif getattr(self, "_cd_left", None):
                # 暂停中（v1.9.9.8）
                self._cd_show_static(self._cd_left)
                self._setw("_cd_btn", text=tr("clock_resume"))
            elif getattr(self, "_cd_total", None):
                # 已设定未开始（v1.9.9.8）
                self._cd_show_static(self._cd_total)
                self._setw("_cd_btn", text=tr("clock_start"))
            if self._sw_task:
                for t in self.store.tasks:
                    if t["id"] == self._sw_task:
                        self._link_task(t["id"], t["title"])
                        break
        except Exception:
            pass
        self._clock_tick()

    def _save_clock_geom(self):
        win = getattr(self, "_clock_win", None)
        if win is None or not win.winfo_exists():
            return
        try:
            g = win.geometry()
            if g and g != getattr(self.store, "clock_geom", None):
                self.store.clock_geom = g
                self.store.save()      # 几何没变就不写盘，避免拖动时反复全量写
        except Exception:
            pass

    def _set_bell(self, mode):
        """选铃声：立刻试听一次并记住"""
        self.store.bell_mode = mode
        self.store.save()
        try:
            if sys.platform == "win32":
                import winsound
                path = None
                for mid, _zh, _en, cands in self.BELL_SOUNDS:
                    if mid == mode:
                        path = self._find_wav(cands)
                        break
                if path:
                    threading.Thread(
                        target=lambda: winsound.PlaySound(
                            path, winsound.SND_FILENAME | winsound.SND_ASYNC),
                        daemon=True).start()
        except Exception:
            pass

    def _link_task(self, tid, title):
        self._sw_task = tid
        self._setw("_link_lbl", text=tr("clock_linked", t=title))
        try:
            self._fin_btn.pack(side="right", padx=(4, 0), before=self._sw_lbl)
        except Exception:
            pass

    # ---- 倒计时：内部一律用「秒」，三种单位（分钟/小时/秒）都精确 ----
    def _cd_unit_secs(self, unit=None):
        """当前输入框里的数值按单位换算成秒"""
        try:
            val = float(self._cd_spin.get())
        except Exception:
            return None
        u = unit or self._cd_unit.get()
        if u == tr("clock_hr"):
            return val * 3600.0
        if u == tr("clock_sec"):
            return val
        return val * 60.0

    def _cd_rescale(self, old_unit=None):
        """切换单位时换算输入框数值（分钟/小时/秒），剩余时间不受影响"""
        secs = self._cd_unit_secs(old_unit)
        if secs is None:
            return
        self._cd_spin.delete(0, "end")
        self._cd_spin.insert(0, self._fmt_unit_input(secs))

    def _cd_quick(self, mins):
        """快捷档：v1.9.9.8 只「设定」时长，不开始、不叠加。
        之前点 5 分钟直接开跑、再点 25 分钟会把剩余时间叠加成 30 分钟。"""
        secs = mins * 60.0
        # 自动选合适的显示单位
        if secs < 60:
            self._cd_unit.set(tr("clock_sec"))
        elif secs < 3600:
            self._cd_unit.set(tr("clock_min"))
        else:
            self._cd_unit.set(tr("clock_hr"))
        om = getattr(self, "_cd_unit_btn", None)
        if om is not None:
            om.config(text=self._cd_unit.get())
        self._cd_spin.delete(0, "end")
        self._cd_spin.insert(0, self._fmt_unit_input(secs))
        self._cd_total = secs
        self._cd_left = None
        self._cd_until = None            # 若正在跑，改选档位 = 重新设定并停止
        self._cd_secs = secs
        self._setw("_cd_btn", text=tr("clock_start"))
        self._cd_show_static(secs)

    def _cd_show_static(self, secs):
        """未开始/已暂停：把剩余时长静态显示出来"""
        lbl = getattr(self, "_cd_lbl", None)
        if lbl is None or not lbl.winfo_exists():
            return
        mm, ss = divmod(int(round(secs)), 60)
        try:
            lbl.config(text="%s  %02d:%02d" % (tr("clock_cd"), mm, ss),
                       fg=C.TEXT)
        except Exception:
            pass

    def _cd_reset(self):
        """清零：停止倒计时，回到「已设定、未开始」状态（保留时长便于重设）"""
        self._cd_until = None
        total = getattr(self, "_cd_total", None)
        self._cd_left = None
        self._setw("_cd_btn", text=tr("clock_start"))
        if total:
            self._cd_show_static(total)
        else:
            self._setw("_cd_lbl", fg=C.TEXT,
                       text=tr("clock_cd") + "  --:--")

    def _fmt_unit_input(self, secs):
        """把秒数格式化成当前单位的输入框文本（小数位随单位变化，保证换回原单位不丢精度）"""
        u = self._cd_unit.get()
        if u == tr("clock_sec"):
            return "%g" % int(round(secs))
        if u == tr("clock_hr"):
            # 小时单位：最多 5 位小数，1 秒 = 0.00028 小时
            v = round(secs / 3600.0, 5)
            return ("%g" % v) if v else "0"
        v = round(secs / 60.0, 3)
        return ("%g" % v) if v else "0"

    def _sw_toggle(self):
        if self._sw_running:
            self._sw_base += time.time() - self._sw_t0
            self._sw_running = False
            self._setw("_sw_btn", text=tr("clock_start"))
            # 停止时把实际时长写进关联任务
            mins = int(self._sw_base // 60)
            if self._sw_task and mins >= 1:
                for t in self.store.tasks:
                    if t["id"] == self._sw_task:
                        t["dur"] = "%d%s" % (mins, tr("clock_min"))
                        t["dur_min"] = mins
                        self.store.save()
                        self.refresh_tasks()

                        def _cw(l, _m=mins, _t=t["title"]):
                            return i18n.render("clock_wrote", dict(
                                d="%d%s" % (_m, i18n.render("clock_min", {}, l)),
                                t=_t), l)
                        lg = i18n.get_lang()
                        self.push_dual("bot", _cw(lg), _cw(
                            "en" if lg == "zh" else "zh"))
                        break
        else:
            self._sw_t0 = time.time()
            self._sw_running = True
            self._setw("_sw_btn", text=tr("clock_pause"))

    def _sw_finish(self):
        """结束正计时：写时长 + 给任务打勾 + 播报"""
        if self._sw_running:
            self._sw_base += time.time() - self._sw_t0
            self._sw_running = False
        self._setw("_sw_btn", text=tr("clock_start"))
        secs = self._sw_base
        mins = int(secs // 60)
        task = None
        for t in self.store.tasks:
            if t["id"] == getattr(self, "_sw_task", None):
                task = t
                break
        self._sw_reset()
        self._sw_task = None
        try:
            self._fin_btn.pack_forget()
            self._setw("_link_lbl", text="")
        except Exception:
            pass
        if task is None:
            return
        if not task.get("done"):
            task["done"] = True
            task["done_at"] = dt.datetime.now().strftime("%H:%M")
        if secs >= 60:
            task["dur"] = "%d%s" % (mins, tr("clock_min"))
            task["dur_min"] = mins
            dtxt = task["dur"]
        else:
            dtxt = tr("sw_lt1")

        def _sw(l, _t=task["title"], _d=dtxt):
            return i18n.render("sw_done", dict(t=_t, d=_d), l)
        lg = i18n.get_lang()
        self.store.save()
        self.refresh_tasks()
        self.push_dual("bot", _sw(lg), _sw("en" if lg == "zh" else "zh"))
        q = self.draw_quote()
        if q:
            self.push("bot", self.fmt_quote(q))

    def _sw_reset(self):
        self._sw_running = False
        self._sw_base = 0.0
        self._setw("_sw_lbl", text=tr("clock_sw") + "  00:00")

    def _cd_total_text(self, secs):
        """把秒数转成显示文本（自动选合适单位）"""
        if secs >= 3600:
            return "%g %s" % (round(secs / 3600.0, 2), tr("clock_hr"))
        if secs >= 60:
            return "%d %s" % (int(round(secs / 60.0)), tr("clock_min"))
        return "%d %s" % (int(round(secs)), tr("clock_sec"))

    def _cd_toggle(self):
        """v1.9.9.8：开始 / 暂停 / 继续三态。
        暂停不再清零——记住剩余秒数，再按「开始/继续」接着倒。"""
        if getattr(self, "_cd_until", None):
            # 正在跑 → 暂停
            self._cd_left = max(1.0, self._cd_until - time.time())
            self._cd_until = None
            self._setw("_cd_btn", text=tr("clock_resume"))
            self._cd_show_static(self._cd_left)
            return
        if getattr(self, "_cd_left", None) and self._cd_left > 0:
            # 暂停中 → 继续
            secs = self._cd_left
            self._cd_left = None
        else:
            # 全新开始：读输入框
            secs = self._cd_unit_secs()
            if secs is None or secs < 1:
                return
            self._cd_total = secs
            self._cd_secs = secs
        self._cd_until = time.time() + secs
        self._setw("_cd_btn", text=tr("clock_pause"))
        self._setw("_cd_lbl", fg=C.TEXT)

    def _cd_start_same(self):
        """弹窗里的「重新计时」：用上次的时长重来"""
        secs = getattr(self, "_cd_secs", 0) or 60
        self._cd_total = secs
        self._cd_left = None
        self._cd_until = time.time() + secs
        self._setw("_cd_btn", text=tr("clock_pause"))
        self._setw("_cd_lbl", fg=C.TEXT)
        pw = getattr(self, "_cd_popup_win", None)
        if pw is not None:
            try:
                pw.destroy()
            except Exception:
                pass
            self._cd_popup_win = None

    def _cd_dismiss(self):
        pw = getattr(self, "_cd_popup_win", None)
        if pw is not None:
            try:
                pw.destroy()
            except Exception:
                pass
            self._cd_popup_win = None
        self._cd_until = None
        try:
            self._setw("_cd_btn", text=tr("clock_start"))
            self._setw("_cd_lbl", fg=C.TEXT, text=tr("clock_cd") + "  --:--")
        except Exception:
            pass    # 时钟窗口已关闭，只清状态

    def _cd_popup(self):
        """倒计时结束：屏幕正中置顶弹窗（可拖动）+ 系统铃声"""
        # 双心跳（250ms 时钟 / 500ms 全局）都可能走到这里，
        # 若不判重会一次弹出两层窗口，前一个变孤儿且铃声叠着响。
        old = getattr(self, "_cd_popup_win", None)
        if old is not None:
            try:
                if old.winfo_exists():
                    old.lift()
                    old.attributes("-topmost", True)
                    return
            except Exception:
                pass
            self._cd_popup_win = None
        d = self._cd_total_text(getattr(self, "_cd_secs", 60))
        pw = tk.Toplevel(self.root)
        self._cd_popup_win = pw
        pw.title(tr("clock_done_title"))
        pw.configure(bg=C.BG)
        pw.attributes("-topmost", True)
        pw.resizable(False, False)
        tk.Label(pw, text="⏰" if False else "!", bg=C.BG, fg="#E2434B",
                 font=(self.f_ui, 18, "bold")).pack(pady=(14, 0))
        tk.Label(pw, text=tr("clock_body", d=d), bg=C.BG, fg=C.TEXT,
                 font=(self.f_ui, 12)).pack(padx=24, pady=(4, 10))
        bf = tk.Frame(pw, bg=C.BG)
        bf.pack(pady=(0, 14))
        tk.Button(bf, text=tr("clock_again"), bg=C.ROW2, fg=C.TEXT, relief="flat",
                  padx=10, command=self._cd_start_same).pack(side="left", padx=6)
        tk.Button(bf, text=tr("clock_close_cd"), bg=C.ROW2, fg=C.TEXT, relief="flat",
                  padx=10, command=self._cd_dismiss).pack(side="left", padx=6)
        pw.update_idletasks()
        sw, sh = pw.winfo_screenwidth(), pw.winfo_screenheight()
        pw.geometry("+%d+%d" % ((sw - pw.winfo_width()) // 2,
                                (sh - pw.winfo_height()) // 2))
        # 可拖动（无标题栏，按住任意位置拖动）
        st = {"x": 0, "y": 0}

        def _press(e):
            st["x"], st["y"] = e.x_root - pw.winfo_x(), e.y_root - pw.winfo_y()

        def _drag(e):
            pw.geometry("+%d+%d" % (e.x_root - st["x"], e.y_root - st["y"]))

        def _bind(w):
            if isinstance(w, tk.Button):
                return
            w.bind("<Button-1>", _press)
            w.bind("<B1-Motion>", _drag)
            for ch in w.winfo_children():
                _bind(ch)
        _bind(pw)
        self._ring_bell(pw)

    # Windows 自带音效文件（C:\Windows\Media），每个声音确实不同
    BELL_SOUNDS = [
        ("chime",     "风铃（清脆）",    "Chimes",
         ["Windows Notify System Generic.wav", "chimes.wav", "ding.wav"]),
        ("notify",    "通知（柔和）",    "Notify",
         ["Windows Notify.wav", "Windows Notify Email.wav", "notify.wav"]),
        ("exclaim",   "感叹号（警示）",  "Exclamation",
         ["Windows Exclamation.wav", "exclamation.wav"]),
        ("stop",      "关键停止（急促）", "Critical Stop",
         ["Windows Critical Stop.wav", "Windows Critical.wav"]),
        ("question",  "疑问（轻问）",    "Question",
         ["Windows Foreground.wav", "Windows Question.wav", "chord.wav"]),
        ("tada",      "胜利（号角）",    "Ta-da",
         ["tada.wav"]),
    ]

    @staticmethod
    def _find_wav(names):
        if sys.platform != "win32":
            return None
        for n in names:
            p = os.path.join(r"C:\Windows\Media", n)
            if os.path.exists(p):
                return p
        return None

    def _ring_bell(self, win):
        """系统铃声：播放 C:\Windows\Media 的真实音效文件，线程里响不卡界面"""
        mode = getattr(self.store, "bell_mode", "chime")

        def _bell_once():
            """Tk 的 bell() 不是线程安全的 → 一律排回主线程执行"""
            try:
                if win is not None and win.winfo_exists():
                    win.bell()
            except Exception:
                pass

        def play():
            try:
                path = None
                if sys.platform == "win32":
                    import winsound
                    for mid, _zh, _en, cands in self.BELL_SOUNDS:
                        if mid == mode:
                            path = self._find_wav(cands)
                            break
                    if path:
                        # SND_ASYNC 本身就是异步播放，不必再套线程反复 sleep
                        for i in range(3):
                            try:
                                winsound.PlaySound(
                                    path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                            except Exception:
                                pass
                            if i < 2:
                                time.sleep(1.0)
                        return
                # 非 Windows 或找不到 wav：用 Tk 提示音兜底，三次排回主线程
                for _ in range(3):
                    try:
                        self.root.after(0, _bell_once)
                    except Exception:
                        pass
                    time.sleep(0.5)
            except Exception:
                pass
        try:
            threading.Thread(target=play, daemon=True).start()
        except Exception:
            pass

    def _recolor_clock(self):
        """换主题时刷新时钟窗口颜色"""
        win = getattr(self, "_clock_win", None)
        if win is None or not win.winfo_exists():
            return
        try:
            win.configure(bg=C.BG)
            for w in getattr(self, "_clock_widgets", []):
                try:
                    if isinstance(w, tk.Frame):
                        w.configure(bg=C.BG)
                    elif isinstance(w, tk.Label):
                        if w is self._cd_lbl:
                            w.configure(bg=C.BG)
                        else:
                            w.configure(bg=C.BG)
                    elif isinstance(w, tk.Button):
                        w.configure(bg=C.ROW2, fg=C.TEXT,
                                    activebackground=C.ACCENT,
                                    activeforeground="white")
                    elif isinstance(w, tk.Checkbutton):
                        w.configure(bg=C.BG, activebackground=C.BG)
                    elif isinstance(w, tk.Menubutton):
                        w.configure(bg=C.ROW2, fg=C.TEXT)
                    elif isinstance(w, tk.Spinbox):
                        w.configure(bg=C.INPUT_BG, fg=C.TEXT,
                                    buttonbackground=C.ROW2)
                except Exception:
                    pass
        except Exception:
            pass

    def _recolor_calendar(self):
        """换主题时刷新日历窗口颜色（此前完全没处理，日历换主题不变色）"""
        win = getattr(self, "_cal_win", None)
        if win is None:
            return
        try:
            if not win.winfo_exists():
                return
        except Exception:
            return
        try:
            win.configure(bg=C.BG)
        except Exception:
            pass
        seen = set()

        def _walk(w):
            for ch in w.winfo_children():
                if id(ch) in seen:
                    continue
                seen.add(id(ch))
                cls = ch.winfo_class()
                try:
                    if cls in ("Frame", "Label", "Canvas", "Toplevel"):
                        ch.configure(bg=C.BG)
                    if cls == "Label":
                        ch.configure(fg=C.SUB)
                    elif cls == "Button":
                        ch.configure(bg=C.ROW2, fg=C.TEXT,
                                     activebackground=C.ROW2, activeforeground=C.TEXT)
                    elif cls == "Spinbox":
                        ch.configure(bg=C.ROW2, fg=C.TEXT, buttonbackground=C.ROW2)
                except Exception:
                    pass
                _walk(ch)
        try:
            _walk(win)
            # 标题是重色标题，单独给回来
            t = getattr(self, "_cal_title", None)
            if t is not None and t.winfo_exists():
                t.configure(bg=C.BG, fg=C.TEXT)
            self._draw_calendar()      # Canvas 图元必须重画
        except Exception:
            pass

    def _close_clock(self):
        self._save_clock_geom()
        # 停掉 250ms 心跳，否则窗口销毁后它还会空转一阵
        win0 = getattr(self, "_clock_win", None)
        aid = getattr(self, "_clock_after", None)
        if aid is not None and win0 is not None:
            try:
                win0.after_cancel(aid)
            except Exception:
                pass
        self._clock_after = None
        pw = getattr(self, "_cd_popup_win", None)
        if pw is not None:
            try:
                if pw.winfo_exists():
                    pw.destroy()
            except Exception:
                pass
        self._cd_popup_win = None
        win = getattr(self, "_clock_win", None)
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass
        self._clock_win = None
        # 控件引用置空：菜单/拖拽回调若残留，访问到也不会炸
        for attr in ("_clock_now", "_sw_lbl", "_cd_lbl", "_cd_btn", "_cd_spin",
                     "_sw_btn", "_fin_btn", "_link_lbl", "_cd_unit_btn"):
            setattr(self, attr, None)
        self._clock_fs = 0

    def show_due_card(self, task):
        """在屏幕右下角弹一张截止提醒小卡片（同一任务只留一张）"""
        try:
            self._due_cards = [c for c in getattr(self, "_due_cards", []) if c.alive()]
        except Exception:
            self._due_cards = []
        for c in self._due_cards:
            if c.tid == task.get("id"):
                try:
                    c.refresh()
                    c.win.lift()
                except Exception:
                    pass
                return
        try:
            card = DueCard(self, task)
            self._due_cards.append(card)
        except Exception:
            import traceback as _tb
            self.diag("!! 截止提醒卡片失败:\n" + _tb.format_exc())

    def open_task_detail(self, tid):
        """点提醒卡片 → 打开该任务的详情页"""
        task = None
        for t in self.store.tasks:
            if t["id"] == tid:
                task = t
                break
        if task is None:
            self.flash(tr("done_notfound", title=""))
            return
        win = getattr(self, "_detail_win", None)
        if win is not None:
            try:
                if win.winfo_exists():
                    win.destroy()
            except Exception:
                pass
        win = tk.Toplevel(self.root)
        self._detail_win = win
        win.title(tr("due_win_title"))
        win.configure(bg=C.BG)
        # v1.9.7：窗口 360x300 → 300x220。旧窗口信息少时空一大片
        win.geometry("300x226")
        win.attributes("-topmost", True)
        win.attributes("-alpha", min(1.0, getattr(self.store, "alpha", 0.88) + 0.05))
        win.resizable(False, False)
        # 贴着主便签右侧打开，别盖住列表
        try:
            win.update_idletasks()
            x = self.root.winfo_x() + self.root.winfo_width() + 8
            y = self.root.winfo_y() + 30
            sw = win.winfo_screenwidth()
            if x + 310 > sw:
                x = max(4, sw - 314)
            win.geometry("300x226+%d+%d" % (x, y))
        except Exception:
            pass
        tk.Label(win, text=tr("due_detail_head", t=task["title"]), bg=C.BG,
                 fg=C.TEXT, font=(self.f_ui, 11, "bold"),
                 wraplength=264, justify="left").pack(anchor="w", padx=14, pady=(12, 4))
        label, pcolor = core.priority_label(task.get("score", 0))
        # 优先级值带档位色，一眼分清急缓（v1.9.7）
        rows = [(tr("menu_priority"), label, pcolor)]
        if task.get("hhmm"):
            rows.append((tr("due_at", d=""), task["hhmm"], None))
            # 剩余时间：今天的任务给出「还有多久」，已过给出提示（v1.9.7）
            left_min = self._left_minutes(task)
            if left_min is not None:
                if left_min >= 0:
                    h6, m6 = divmod(left_min, 60)
                    left_txt = (tr("detail_left_hm") % (h6, m6)) if h6 \
                        else (tr("detail_left_m") % m6)
                else:
                    left_txt = tr("detail_left_over")
                rows.append((tr("detail_left"), left_txt,
                             None if left_min >= 0 else "#B4463C"))
        if task.get("due_date"):
            rows.append((tr("detail_due_date"), task["due_date"], None))
        if task.get("remind_at"):
            rows.append((tr("detail_remind"), task["remind_at"], None))
        elif task.get("remind_before"):
            rows.append((tr("detail_remind"), tr("remind_%d" % task["remind_before"])
                         if task["remind_before"] in (5, 15, 30, 60)
                         else "%d %s" % (task["remind_before"], tr("clock_min")), None))
        if task.get("dur"):
            rows.append((tr("detail_spent"), task["dur"], None))
        if task.get("repeat"):
            rows.append((tr("detail_repeat"),
                         self._repeat_text(task["repeat"]), None))
        if task.get("done"):
            rows.append((tr("detail_done"), task.get("done_at") or "", None))
        for k, v, vc in rows:
            r = tk.Frame(win, bg=C.BG)
            r.pack(fill="x", padx=16, pady=1)
            tk.Label(r, text=str(k), bg=C.BG, fg=C.SUB,
                     font=self.f_small, width=10, anchor="w").pack(side="left")
            tk.Label(r, text=str(v), bg=C.BG, fg=vc or C.TEXT,
                     font=self.f_small, anchor="w").pack(side="left")
        bf = tk.Frame(win, bg=C.BG)
        bf.pack(side="bottom", fill="x", padx=14, pady=10)
        if not task.get("done"):
            tk.Button(bf, text=tr("due_done"), bg=C.ACCENT, fg="white", relief="flat",
                      padx=10, command=lambda: (self.toggle_done(tid),
                                                self._close_detail())).pack(side="left")
        tk.Button(bf, text=tr("due_ignore"), bg=C.ROW2, fg=C.TEXT, relief="flat",
                  padx=10, command=self._close_detail).pack(side="right")

    def _left_minutes(self, task):
        """距截止还有多少分钟；无法判断返回 None，已过返回负数"""
        hhmm = task.get("hhmm")
        if not hhmm:
            return None
        try:
            h, mi = [int(x) for x in hhmm.split(":")]
            dd = task.get("due_date") or self.store._today()
            y, mo, d = [int(x) for x in dd.split("-")]
            due = dt.datetime(y, mo, d, h, mi)
            return int((due - dt.datetime.now()).total_seconds() // 60)
        except Exception:
            return None

    def _repeat_text(self, rep):
        """周期任务的中文描述（详情窗用，v1.9.7）"""
        kind = (rep or {}).get("kind")
        wd = (rep or {}).get("weekday")
        names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        zh = not i18n.is_en()
        if kind == "daily":
            return tr("rep_daily") if zh else "Every day"
        if kind == "weekly":
            if wd is not None and 0 <= int(wd) < 7:
                return names[int(wd)] if zh else "Every " + ["Mon", "Tue", "Wed",
                        "Thu", "Fri", "Sat", "Sun"][int(wd)]
            return tr("rep_weekly") if zh else "Every week"
        if kind == "monthly":
            return tr("rep_monthly") if zh else "Every month"
        return str((rep or {}).get("kind", ""))

    def _close_detail(self):
        w = getattr(self, "_detail_win", None)
        if w is not None:
            try:
                if w.winfo_exists():
                    w.destroy()
            except Exception:
                pass
        self._detail_win = None

    def check_reminders(self):
        """到提醒时间：右下角悬浮卡片 + 聊天播报 + 铃声（每任务只提醒一次）"""
        now = dt.datetime.now()
        fired = []       # 这一轮命中的任务，批量处理避免反复全量重绘
        for t in self.store.tasks:
            if t.get("done"):
                continue
            if not t.get("hhmm") and not t.get("remind_at"):
                continue
            if not t.get("remind_before") and not t.get("remind_at"):
                continue
            rep = t.get("repeat")
            if rep:
                # 周期任务：今天不该做就跳过；跨天了就重置提醒标记
                if not core.repeat_due_today(rep):
                    continue
                if t.get("reminded_day") != self.store._today():
                    t["reminded"] = False
            elif t.get("due_date") and t["due_date"] != self.store._today():
                continue
            if t.get("reminded"):
                continue
            # ① 用户指定了「几点提醒」：到点直接播报
            rat = t.get("remind_at")
            if rat and len(rat) == 5:
                target_day = now.date() - dt.timedelta(days=t.get("remind_day") or 0)
                if now.date() != target_day:
                    continue
                h2, m2 = rat.split(":")
                at2 = now.replace(hour=int(h2), minute=int(m2), second=0)
                if at2 <= now <= at2 + dt.timedelta(minutes=30):
                    t["reminded"] = True
                    t["reminded_day"] = self.store._today()
                    fired.append((t, "at"))
                continue
            h, mi = t["hhmm"].split(":")
            due = now.replace(hour=int(h), minute=int(mi), second=0)
            at = due - dt.timedelta(minutes=t["remind_before"])
            if at <= now <= due + dt.timedelta(minutes=1):
                t["reminded"] = True
                t["reminded_day"] = self.store._today()
                fired.append((t, "before"))
        if not fired:
            return
        self.store.save()
        for t, kind in fired:
            self.show_due_card(t)                 # 右下角小窗
            lg = i18n.get_lang()
            ol = "en" if lg == "zh" else "zh"
            if kind == "at":
                def _rn(l, _t=t):
                    return i18n.render("remind_now", dict(
                        t=_t["title"],
                        h=(_t.get("deadline_txt") or _t.get("hhmm")
                           or _t.get("remind_at"))), l)
                self.push_dual("bot", _rn(lg), _rn(ol))
            else:
                mins = int((now.replace(hour=int(t["hhmm"].split(":")[0]),
                                        minute=int(t["hhmm"].split(":")[1]),
                                        second=0) - now).total_seconds() // 60) + 1

                def _rp(l, _t=t, _m=mins):
                    d = ("%d%s" % (_m, i18n.render("clock_min", {}, l))
                         if _m >= 1 else i18n.render("sw_lt1", {}, l))
                    return i18n.render("remind_push", dict(
                        t=_t["title"], d=d, h=_t["hhmm"]), l)
                self.push_dual("bot", _rp(lg), _rp(ol))
        self.refresh_tasks()      # 只刷一次
        self._ring_bell(self.root)

    def _cd_bg_tick(self):
        """全局心跳：倒计时到点就弹窗，与时钟窗口是否开着无关"""
        until = getattr(self, "_cd_until", None)
        if not until:
            # 底部按钮恢复常规文字
            cb = getattr(self, "clock_btn", None)
            if cb is not None and str(cb.cget("text")) != tr("clock_btn"):
                try:
                    cb.config(text=tr("clock_btn"))
                except Exception:
                    pass
            return
        left = until - time.time()
        if left <= 0:
            self._cd_until = None
            self._cd_left = None            # v1.9.9.8：到点后没有「剩余」可继续
            # 兜底清一次：避免别的路径（时钟 250ms 心跳）抢先后留下「时间到」红字
            try:
                cb = getattr(self, "_cd_btn", None)
                if cb is not None and cb.winfo_exists():
                    cb.config(text=tr("clock_start"))
                lb = getattr(self, "_cd_lbl", None)
                if lb is not None and lb.winfo_exists():
                    lb.config(text=tr("clock_done"), fg="#E2434B")
            except Exception:
                pass
            self._cd_popup()
        else:
            # 时钟窗口开着 → 那边刷新；关着 → 底部按钮显示剩余
            cw = getattr(self, "_clock_win", None)
            if cw is None or not cw.winfo_exists():
                mm, ss = divmod(int(left), 60)
                cb = getattr(self, "clock_btn", None)
                if cb is not None:
                    txt = tr("clock_left") % ("%02d:%02d" % (mm, ss))
                    try:
                        if str(cb.cget("text")) != txt:      # 变一次才刷，防抖
                            cb.config(text=txt)
                    except Exception:
                        pass

    def _clock_tick(self):
        win = getattr(self, "_clock_win", None)
        if win is None or not win.winfo_exists():
            return
        # 关键：续期必须放在 finally 里。此前 after 写在函数末尾，
        # 中途任何一个控件已销毁就抛异常 → 心跳永久断掉（时钟停走、按钮失灵）。
        try:
            self._clock_tick_body(win)
        except Exception:
            pass
        finally:
            try:
                if win.winfo_exists():
                    self._clock_after = win.after(250, self._clock_tick)
            except Exception:
                pass

    def _clock_tick_body(self, win):
        now_lbl = getattr(self, "_clock_now", None)
        if now_lbl is None or not now_lbl.winfo_exists():
            return
        now_lbl.config(text=dt.datetime.now().strftime("%H:%M:%S"))
        # 用「时间标签自身」拿到的可用宽高来算字号：
        # 标签已 expand 充满剩余空间，宽高随窗口变化，
        # 且自动扣掉了正计时/倒计时/底栏占掉的部分
        lw = now_lbl.winfo_width()
        lh = now_lbl.winfo_height()
        if lw < 40 or lh < 20:      # 首帧还没布局好，先按窗口估
            lw, lh = win.winfo_width(), max(60, win.winfo_height() - 120)
        # 四周留白：文字宽约占 60%、高约占 55%
        size = int(min(lw * 0.60 / 5.2, lh * 0.55 / 1.35))
        size = max(16, min(120, size))
        if size != getattr(self, "_clock_fs", 0):
            try:
                now_lbl.config(font=(self.f_ui, size, "bold"))
                self._clock_fs = size        # 只在字号变化时才重设，省掉无谓重排
            except Exception:
                pass
        # 正计时
        sw = getattr(self, "_sw_lbl", None)
        if sw is not None and sw.winfo_exists():
            el = self._sw_base + (time.time() - self._sw_t0 if self._sw_running else 0)
            m, sec = divmod(int(el), 60)
            txt = "%s  %02d:%02d" % (tr("clock_sw"), m, sec)
            if str(sw.cget("text")) != txt:
                sw.config(text=txt)
        # 倒计时（到期弹窗由全局心跳 _cd_bg_tick 统一负责，这里只显示）
        if self._cd_until:
            left = self._cd_until - time.time()
            if left > 0:
                lbl = getattr(self, "_cd_lbl", None)
                if lbl is not None and lbl.winfo_exists():
                    hh, rem = divmod(int(left), 3600)
                    mm, ss = divmod(rem, 60)
                    if hh:
                        txt = "%s  %d:%02d:%02d" % (tr("clock_cd"), hh, mm, ss)
                    else:
                        txt = "%s  %02d:%02d" % (tr("clock_cd"), mm, ss)
                    if str(lbl.cget("text")) != txt:
                        lbl.config(text=txt)
        # 每 2 拍同步一次颜色（换主题后必定跟上，开销极小）
        self._clock_n = getattr(self, "_clock_n", 0) + 1
        if self._clock_n % 2 == 0:
            self._recolor_clock()

    # ---------------- 日历视图
    def open_calendar_view(self):
        win = getattr(self, "_cal_win", None)
        if win is not None and win.winfo_exists():
            win.lift()
            return
        win = tk.Toplevel(self.root)
        self._cal_win = win
        win.title(tr("cal_title"))
        win.configure(bg=C.BG)
        win.geometry("560x480+260+140")
        win.attributes("-alpha", min(1.0, getattr(self.store, "alpha", 0.88) + 0.04))
        self._cal_y, self._cal_m = dt.date.today().year, dt.date.today().month
        nav = tk.Frame(win, bg=C.BG)
        nav.pack(side="top", fill="x", pady=(8, 2))
        tk.Button(nav, text="‹", bg=C.ROW2, fg=C.TEXT, relief="flat",
                  width=3, command=lambda: self._cal_nav(-1)).pack(side="left", padx=8)
        self._cal_title = tk.Label(nav, text="", bg=C.BG, fg=C.TEXT,
                                   font=(self.f_ui, 13, "bold"))
        self._cal_title.pack(side="left", expand=True)
        tk.Button(nav, text="›", bg=C.ROW2, fg=C.TEXT, relief="flat",
                  width=3, command=lambda: self._cal_nav(1)).pack(side="right", padx=8)
        # 快速跳转：年 / 月 / 回到今天
        quick = tk.Frame(win, bg=C.BG)
        quick.pack(side="top", fill="x", padx=8)
        tk.Label(quick, text=tr("cal_jump"), bg=C.BG, fg=C.SUB,
                 font=self.f_tiny).pack(side="left")
        self._cal_ys = tk.Spinbox(quick, from_=1970, to=2100, width=6,
                                  bg=C.ROW2, fg=C.TEXT, buttonbackground=C.ROW2,
                                  relief="flat", justify="center",
                                  command=self._cal_jump)
        self._cal_ys.pack(side="left", padx=(6, 2))
        self._cal_ms = tk.Spinbox(quick, from_=1, to=12, width=4,
                                  bg=C.ROW2, fg=C.TEXT, buttonbackground=C.ROW2,
                                  relief="flat", justify="center")
        self._cal_ms.pack(side="left", padx=2)
        # 确认按钮：输完年月点一下才跳（Spinbox 的箭头不再即时跳转）
        tk.Button(quick, text=tr("cal_jump_go"), bg=C.ROW2, fg=C.TEXT,
                  relief="flat", padx=6,
                  command=self._cal_jump).pack(side="left", padx=(4, 0))
        tk.Button(quick, text=tr("cal_today"), bg=C.ROW2, fg=C.TEXT, relief="flat",
                  command=self._cal_today).pack(side="right")
        self._cal_cv = tk.Canvas(win, bg=C.BG, highlightthickness=0)
        self._cal_cv.pack(side="top", fill="both", expand=True, padx=8, pady=(0, 2))
        # 拖动窗口时 Configure 会连续触发，直接重绘 = 重绘风暴（拖起来卡）。
        # 走 debounce，拖完再画一次。
        self._cal_cv.bind("<Configure>",
                          lambda e: self.debounce("caldraw", self._draw_calendar, 90))
        # 点击日期查看当天安排
        self._cal_info = tk.Label(win, text="", bg=C.BG, fg=C.SUB,
                                  font=self.f_tiny, anchor="w", justify="left")
        self._cal_info.pack(side="bottom", fill="x", padx=10, pady=(0, 6))
        self._draw_calendar()

    def _cal_jump(self):
        try:
            y = int(self._cal_ys.get())
            m = int(self._cal_ms.get())
            if 1970 <= y <= 2100 and 1 <= m <= 12:
                self._cal_y, self._cal_m = y, m
                self._draw_calendar()
        except (ValueError, tk.TclError):
            pass

    def _cal_today(self):
        t = dt.date.today()
        self._cal_y, self._cal_m = t.year, t.month
        self._draw_calendar()

    def _cal_nav(self, d):
        m = self._cal_m + d
        y = self._cal_y
        if m < 1:
            m, y = 12, y - 1
        elif m > 12:
            m, y = 1, y + 1
        self._cal_y, self._cal_m = y, m
        self._draw_calendar()

    def _draw_calendar(self):
        cv = getattr(self, "_cal_cv", None)
        if cv is None or not cv.winfo_exists():
            return
        cv.delete("all")
        w = max(cv.winfo_width(), 300)
        h = max(cv.winfo_height(), 240)
        y, m = self._cal_y, self._cal_m
        if i18n.is_en():
            self._cal_title.config(text="%d-%02d" % (y, m))
        else:
            self._cal_title.config(text="%d 年 %d 月" % (y, m))
        # 有日程的日期集合（截止日期 / 创建日）
        busy = set()
        today_s = self.store._today()
        for t in self.store.tasks:
            dd = t.get("due_date")
            if dd:
                busy.add(dd)
            if t.get("day"):
                busy.add(t["day"])
        first = dt.date(y, m, 1)
        ndays = (dt.date(y + (m == 12), (m % 12) + 1, 1) - first).days
        lead = (first.weekday() + 1) % 7          # 周日开头
        rows = (lead + ndays + 6) // 7
        wd_names = ["日", "一", "二", "三", "四", "五", "六"] \
            if not i18n.is_en() else ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"]
        cw, ch = w / 7.0, min(h / (rows + 1.4), 74)
        for i, nm in enumerate(wd_names):
            col = C.ACCENT if i in (0, 6) else C.SUB
            cv.create_text(i * cw + cw / 2, 14, text=nm, font=self.f_small, fill=col)
        for d in range(ndays):
            r, c = divmod(lead + d, 7)
            x0, y0 = c * cw, 30 + r * ch
            date = first + dt.timedelta(days=d)
            ds = date.isoformat()
            tag = "day_%s" % ds
            # 今天高亮
            if ds == today_s:
                cv.create_rectangle(x0 + 4, y0 + 2, x0 + cw - 4, y0 + ch - 4,
                                    fill=C.ACCENT, outline="", stipple="gray25")
            hol, fest = cn_holidays.get(ds)
            col = "#E2434B" if c in (0, 6) or hol == "休" else C.TEXT
            cv.create_text(x0 + cw / 2, y0 + 20, text=str(d + 1),
                           font=(self.f_ui, 12, "bold"), fill=col, tags=(tag,))
            # 休 / 班 角标
            if hol == "休":
                cv.create_text(x0 + cw - 14, y0 + 12, text="休",
                               font=(self.f_ui, 8), fill="#E2434B", tags=(tag,))
            elif hol == "班":
                cv.create_text(x0 + cw - 14, y0 + 12, text="班",
                               font=(self.f_ui, 8), fill="#3E8ED0", tags=(tag,))
            # 节日名
            if fest:
                cv.create_text(x0 + cw / 2, y0 + 44, text=fest,
                               font=self.f_tiny, fill="#EE9A2B", tags=(tag,))
            # 有日程：小圆点
            if ds in busy:
                cv.create_oval(x0 + cw / 2 - 3, y0 + ch - 14,
                               x0 + cw / 2 + 3, y0 + ch - 8,
                               fill=C.ACCENT, outline="", tags=(tag,))
            # 点击日期 -> 底部显示当天安排
            cv.tag_bind(tag, "<Button-1>",
                        lambda e, dd=ds: self._cal_show_day(dd))

    def _cal_show_day(self, ds):
        try:
            d = dt.date.fromisoformat(ds)
        except ValueError:
            return
        hol, fest = cn_holidays.get(ds)
        parts = []
        if i18n.is_en():
            parts.append(d.strftime("%Y-%m-%d %a"))
        else:
            wd = "一二三四五六日"[d.weekday()]
            parts.append("%d月%d日 周%s" % (d.month, d.day, wd))
        if hol == "休":
            parts.append(tr("cal_off"))
        elif hol == "班":
            parts.append(tr("cal_work"))
        if fest:
            parts.append(fest)
        items = [t for t in self.store.tasks if t.get("day") == ds
                 or t.get("due_date") == ds]
        if items:
            done = sum(1 for t in items if t.get("done"))
            parts.append(tr("cal_day_tasks", n=len(items), d=done))
            for t in items[:3]:
                mark = "✓" if t.get("done") else "·"
                parts.append("  %s %s" % (mark, t["title"]))
        else:
            parts.append(tr("cal_day_empty"))
        self._cal_info.config(text="   ".join(parts[:7]))

    def open_history(self):
        self.store.sync_history()
        win = self._hist_win
        if win is not None and win.winfo_exists():
            win.lift()
            self._render_history()
            return

        win = tk.Toplevel(self.root)
        self._hist_win = win
        win.title(tr("hist_title") + " · " + self.app_name())
        win.configure(bg=C.BG)
        win.transient(self.root)
        win.attributes("-topmost", bool(self.store.topmost))
        rw = max(340, min(self.root.winfo_width() + 110, 520))
        rh = max(320, min(self.root.winfo_height() + 130, 560))
        x = self.root.winfo_x() - rw - 10
        if x < 0:
            x = self.root.winfo_x() + self.root.winfo_width() + 10
        y = self.root.winfo_y()
        win.geometry("%dx%d+%d+%d" % (rw, rh, x, y))
        win.minsize(300, 240)
        win.protocol("WM_DELETE_WINDOW", self.close_history)

        # 顶部汇总
        head = tk.Frame(win, bg=C.HEAD)
        head.pack(side="top", fill="x")
        self.hist_title = tk.Label(head, text="", bg=C.HEAD, fg=C.TEXT,
                                   font=(self.f_ui, 10, "bold"), anchor="w", padx=10,
                                   pady=6)
        self.hist_title.pack(side="left")
        close = tk.Label(head, text=tr("hist_close"), bg=C.HEAD, fg=C.SUB,
                         font=self.f_tiny, padx=10, cursor="hand2")
        close.pack(side="right")
        close.bind("<Button-1>", lambda e: self.close_history())
        close.bind("<Enter>", lambda e: close.config(fg="#B4463C"))
        close.bind("<Leave>", lambda e: close.config(fg=C.SUB))

        # 汇总条（总天数 / 总任务 / 总完成 / 完成率）
        self.hist_sum = tk.Label(win, text="", bg=C.BG, fg=C.SUB,
                                 font=self.f_small, anchor="w", padx=10, pady=5)
        self.hist_sum.pack(side="top", fill="x")

        sep = tk.Frame(win, bg=C.LINE, height=1)
        sep.pack(side="top", fill="x", padx=8)

        # 可滚动的天数列表
        wrap = tk.Frame(win, bg=C.BG)
        wrap.pack(side="top", fill="both", expand=True)
        self.hist_cv = Canvas(wrap, bg=C.BG)
        sb = tk.Scrollbar(wrap, orient="vertical", command=self.hist_cv.yview)
        self.hist_cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.hist_cv.pack(side="left", fill="both", expand=True)
        self.hist_cv.bind("<Configure>", lambda e: self.debounce("hist", self._render_history))
        for seq, d in (("<MouseWheel>", 0), ("<Button-4>", -1), ("<Button-5>", 1)):
            self.hist_cv.bind(seq, lambda e, dd=d: self._hist_wheel(e, dd))

        self._render_history()

    def close_history(self):
        if self._hist_win is not None and self._hist_win.winfo_exists():
            self._hist_win.destroy()
        self._hist_win = None

    def _hist_wheel(self, e, direction=0):
        if direction == 0:
            direction = -1 if getattr(e, "delta", 0) > 0 else 1
        # 内容不足一屏时不滚（否则能拖出一段空白）
        if getattr(self, "_hist_locked", False):
            return
        self.hist_cv.yview_scroll(direction, "units")

    def _render_history(self):
        if self._hist_win is None or not self._hist_win.winfo_exists():
            return
        cv = self.hist_cv
        cv.delete("all")
        w = max(cv.winfo_width(), 120)
        days = self.store.history_days()
        today = self.store.today

        all_rows = [r for d in days for r in self.store.history.get(d, [])]
        all_total = len(all_rows)
        all_done = sum(1 for r in all_rows if r.get("done"))
        rate = int(round(all_done * 100.0 / all_total)) if all_total else 0
        self.hist_title.config(text=tr("hist_title"))
        self.hist_sum.config(
            text=tr("hist_sum", days=len(days), tasks=all_total,
                   done=all_done, pct=rate))

        if not days:
            cv.create_text(w / 2, 60, text=tr("hist_empty"),
                           font=self.f_small, fill=C.SUB, justify="center")
            cv.config(scrollregion=(0, 0, w, 140))
            return

        line_h = 15
        y = 6
        for day in days:
            rows = self.store.history.get(day, [])
            done = sum(1 for r in rows if r.get("done"))
            total = len(rows)
            ratio = (done / total) if total else 0

            # —— 日期头
            hd_h = 24
            cv.create_rectangle(6, y, w - 6, y + hd_h, fill=_mix(C.ACCENT, "#FFFFFF", 0.82), outline="")
            cv.create_rectangle(6, y, 9, y + hd_h, fill=self.bar_color(ratio), outline="")
            label = self._day_label(day, today)
            cv.create_text(14, y + hd_h / 2, text=label, anchor="w",
                           font=(self.f_ui, 9, "bold"), fill=C.TEXT)
            cv.create_text(w - 12, y + hd_h / 2, text="%d/%d" % (done, total),
                           anchor="e", font=(self.f_ui, 8, "bold"),
                           fill=self.bar_color(ratio))
            y += hd_h + 2

            # —— 该天的任务：已完成在前？不，按优先级，完成的沉底（与当日体验一致）
            if not rows:
                cv.create_text(22, y + line_h / 2, text=tr("hist_none_day"), anchor="w",
                               font=self.f_tiny, fill=C.SUB)
                y += line_h
            else:
                undone = [r for r in rows if not r.get("done")]
                dones = [r for r in rows if r.get("done")]
                undone.sort(key=lambda r: (-r.get("score", 0), r.get("hhmm") or "99:99"))
                dones.sort(key=lambda r: r.get("done_at") or "")
                for r in undone + dones:
                    self._draw_check(cv, 20, y + line_h / 2, 4.5, bool(r.get("done")))
                    tx = 30
                    hhmm = r.get("hhmm")
                    if hhmm:
                        cv.create_text(tx, y + line_h / 2, text=hhmm, anchor="w",
                                       font=self.f_tiny, fill=C.SUB)
                        tx += 34
                    title = r.get("title", "")
                    avail = w - tx - 14
                    title = self.ellipsize(title, self.f_small, avail)
                    tid = "h_%s_%d" % (day, y)
                    done_flag = bool(r.get("done"))
                    cv.create_text(tx, y + line_h / 2, text=title, anchor="w",
                                   font=self.f_small,
                                   fill=C.DONE if done_flag else C.TEXT, tags=(tid,))
                    if done_flag:
                        tw = self.text_width(title, self.f_small)
                        cv.create_line(tx, y + line_h / 2 + 1,
                                       tx + tw, y + line_h / 2 + 1,
                                       fill=C.DONE, width=1)
                    if r.get("done_at"):
                        cv.create_text(w - 12, y + line_h / 2,
                                       text=r.get("done_at"), anchor="e",
                                       font=self.f_tiny, fill=C.DONE)
                    y += line_h
            y += 6
            cv.create_line(8, y - 3, w - 8, y - 3, fill=C.LINE)

        cv.config(scrollregion=(0, 0, w, y + 6))
        # 内容不足一屏：锁住滚动（否则滚动条能拖出一截空白）
        vh = cv.winfo_height()
        if vh > 10 and y + 6 <= vh:
            cv.config(scrollregion=(0, 0, w, vh))
            cv.yview_moveto(0)
            self._hist_locked = True
        else:
            self._hist_locked = False

    def _draw_check(self, cv, cx, cy, s, done):
        """自绘勾选框（历史窗口用）：空框 / 框内打勾"""
        if done:
            cv.create_rectangle(cx - s, cy - s, cx + s, cy + s,
                                fill=C_BAR_FULL, outline=C_BAR_FULL, width=1)
            cv.create_line(cx - s + 2.0, cy, cx - 0.8, cy + s - 2.2,
                           fill="#FFFFFF", width=1.8)
            cv.create_line(cx - 0.8, cy + s - 2.2, cx + s - 1.2, cy - s + 2.0,
                           fill="#FFFFFF", width=1.8)
        else:
            cv.create_rectangle(cx - s, cy - s, cx + s, cy + s,
                                fill="", outline=C.SUB, width=1.2)

    @staticmethod
    def _day_label(day, today):
        try:
            d = dt.date.fromisoformat(day)
        except Exception:
            return day
        delta = (dt.date.fromisoformat(today) - d).days if today else 0
        if i18n.is_en():
            mon = i18n.t("month_names")[d.month - 1]
            wd = i18n.t("weekdays")[d.weekday()]
            md = "%s %d" % (mon, d.day)
            if day == today:
                return tr("day_head_today", md=md, wd=wd)
            if delta == 1:
                return tr("day_head_yesterday", md=md, wd=wd)
            return tr("day_head_full", y="%s %d" % (mon, d.year), m=mon, d=d.day, wd=wd)
        week = "一二三四五六日"[d.weekday()]
        md = "%d月%d日" % (d.month, d.day)
        if day == today:
            return tr("day_head_today", md=md, wd=week)
        if delta == 1:
            return tr("day_head_yesterday", md=md, wd=week)
        return tr("day_head_full", y=d.year, m=d.month, d=d.day, wd=week)


# ---- 单实例保护（v1.9.8）----
# 双击两次 exe 会开两个实例，两边同时读写同一份数据、互相覆盖。
# 现在用本机端口做锁：第二个实例启动时把已有窗口唤到前台后自己退出。
_SINGLE_PORT = 27190

def _single_instance_register(on_show, root0):
    """尝试成为唯一实例。成功返回 socket（保活）；已有实例在跑则
    通知它显示窗口并返回 None。

    v1.9.9.1 关键修复：accept 彻底移出 UI 线程。
    v1.9.9 曾把带 0.2s 超时的 accept 放在 Tk 主线程的 after 回调里——
    实测 Windows 上仍可能因杀毒软件钩住 socket 调用 / select 延迟，
    把主循环卡住数秒（→「未响应」）。现在：
      · 后台守护线程阻塞式 accept（线程里阻塞无所谓）；
      · 收到 show 后只往线程安全队列塞一个标记；
      · UI 线程用 after 每 300ms 非阻塞地取队列（queue.get_nowait）。
    UI 线程从此不碰任何 socket。
    """
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        srv.bind(("127.0.0.1", _SINGLE_PORT))
        srv.listen(2)
    except OSError:
        # 端口被占 → 已有实例：通知它亮出窗口
        try:
            c = socket.create_connection(("127.0.0.1", _SINGLE_PORT), timeout=1)
            c.sendall(b"show")
            c.close()
        except Exception:
            pass
        return None, None

    import queue as _q, threading as _th
    show_q = _q.Queue()

    def _accept_loop():
        """后台线程：阻塞 accept 完全没问题；UI 永远不被拖累"""
        while True:
            try:
                conn, _ = srv.accept()
                data = b""
                try:
                    conn.settimeout(0.5)
                    data = conn.recv(16)
                except Exception:
                    pass
                if b"show" in data:
                    show_q.put(True)      # 线程安全，UI 轮询取
                try:
                    conn.close()
                except Exception:
                    pass
            except Exception:
                # 监听挂了就别再空转（比如进程退出时 socket 已关）
                try:
                    srv.close()
                except Exception:
                    pass
                return

    try:
        _th.Thread(target=_accept_loop, daemon=True).start()
    except Exception:
        return srv, None

    def serve():
        """UI 线程每 300ms 调一次：只做非阻塞取队列 + 调 on_show"""
        try:
            while True:
                show_q.get_nowait()
                on_show()
        except Exception:
            pass
        try:
            root0.after(300, serve)
        except Exception:
            pass

    return srv, serve


def _ensure_desktop_shortcut():
    """首次运行在桌面 + 程序目录生成快捷方式（v1.9.8 起，仅 Windows）。
    v1.9.9.12：彻底解决「快捷方式图标不是最新版」——
      ① 显式 IconLocation 指向 assets/icon.ico（不用 exe 内嵌的旧图标）
      ② 每次启动无条件重建（旧 lnk 不会自己更新）
      ③ 重建后主动刷新 Windows 图标缓存（否则资源管理器仍显示旧图）
    任何失败静默，绝不打扰使用。"""
    if os.name != "nt":
        return

    def _mk():
        try:
            desktop = os.path.join(os.path.expanduser("~"), "Desktop")
            if getattr(sys, "frozen", False):
                progdir = os.path.dirname(sys.executable)
                target = sys.executable
            else:
                progdir = os.path.dirname(os.path.abspath(__file__))
                # 源码运行：快捷方式指向 pythonw.exe + main.py，
                # 双击不弹黑框（python.exe 会留一个控制台窗口）
                pw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
                target = pw if os.path.isfile(pw) else sys.executable
            targets = [d for d in (desktop, progdir)
                       if d and os.path.isdir(d)]
            if not targets:
                return
            # 图标文件：优先 assets/icon.ico，缺失则退回 exe/png
            ico = os.path.join(progdir, "assets", "icon.ico")
            if not os.path.isfile(ico):
                png = os.path.join(progdir, "assets", "icon.png")
                ico = png if os.path.isfile(png) else ""
            icon_part = ("$s.IconLocation='%s,0';" % ico) if ico else ""
            ps = "$ws=New-Object -ComObject WScript.Shell;"
            for d in targets:
                lnk = os.path.join(d, "每日记事本.lnk")
                ps += ("$s=$ws.CreateShortcut('%s');"
                       "$s.TargetPath='%s';" % (lnk, target))
                if getattr(sys, "frozen", False):
                    ps += "$s.WorkingDirectory='%s';" % progdir
                else:
                    ps += ("$s.Arguments='\"%s\"';"
                           "$s.WorkingDirectory='%s';"
                           % (os.path.join(progdir, "main.py"), progdir))
                ps += icon_part + "$s.Save();"
            # ③ 刷新图标缓存：让资源管理器重新读取 lnk 的图标
            #   ie4uinit.exe -show 会重建 iconcache，比手删 db 安全
            ps += ("try{Start-Process -FilePath ie4uinit.exe "
                   "-ArgumentList '-show' -WindowStyle Hidden -Wait "
                   "-ErrorAction SilentlyContinue}catch{}")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle",
                              "Hidden", "-Command", ps])
        except Exception:
            pass

    try:
        import threading as _th
        _th.Thread(target=_mk, daemon=True).start()
    except Exception:
        _mk()


def main():
    def _diag(msg):
        """启动阶段黑匣子：走 NoteApp 的后台写日志线程（绝不在 UI 线程碰磁盘），
        若再出现卡死，data/log.txt 能定位到阶段"""
        try:
            app.diag("[main] " + msg)
        except Exception:
            pass

    root = tk.Tk()
    app = NoteApp(root)
    _diag("NoteApp 构建完成")

    # 单实例：锁被占说明已有一个在跑，弹它到前台后本进程退出
    def _show_existing():
        try:
            app.root.deiconify()
            app.root.lift()
            app.root.attributes("-topmost", True)
            app.root.after(120, lambda: app.root.attributes("-topmost",
                       getattr(app.store, "topmost", True)))
            app._activate_window()
        except Exception:
            pass
    _srv, _serve = _single_instance_register(_show_existing, root)
    if _srv is None:
        root.destroy()
        return
    _diag("单实例注册完成（后台线程监听）")
    root.after(300, _serve)
    root.after(1500, _ensure_desktop_shortcut)

    def tick():
        # 截止时间提醒
        try:
            app.check_reminders()
        except Exception:
            pass
        # 每分钟检查跨天
        if dt.date.today().isoformat() != app.store.today:
            app.store.sync_history()            # 先把昨天归档
            app.store.today = dt.date.today().isoformat()
            for t in app.store.tasks:
                t["reminded"] = False
                t["reminded_day"] = None
                if t.get("repeat"):
                    # 周期任务：到点复活；昨天没做的沿用原时刻
                    if core.repeat_due_today(t["repeat"]):
                        t["done"] = False
                        t["done_at"] = None
                    else:
                        t["done"] = True        # 今天不该做，先压到已完成区
                    continue
                if t.get("due_date"):
                    # 有明确截止日：还没到就留着时刻，过了才清
                    if t["due_date"] < app.store.today and not t.get("done"):
                        t["hhmm"] = None
                    continue
                if not t.get("done"):
                    t["hhmm"] = None
            app.store.messages = []
            app.store.save()
            app.refresh_tasks()
            app.draw_bar()
            # 跨天开场也从轮换池取，避免每天都是同一句（双语推送）
            cur, dual = app._daily_greet_dual()
            app.push("bot", cur, dual=dual)
            if app._hist_win is not None and app._hist_win.winfo_exists():
                app._render_history()
        root.after(60000, tick)

    root.after(60000, tick)

    # 倒计时后台心跳：时钟窗口关了也照样到点弹窗
    def cd_bg():
        try:
            app._cd_bg_tick()
        except Exception:
            pass
        root.after(500, cd_bg)
    root.after(500, cd_bg)
    root.after(100, lambda: _diag("即将进入主循环"))
    root.mainloop()
    _diag("主循环退出")


if __name__ == "__main__":
    main()
