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
import shutil
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
VERSION = "1.9.9.45"

# 对话消息最多保留条数。v1.9.9.40 及以前是 60——聊天一多旧记录
# 被三处 [-60:] 硬裁剪**永久删除**（读盘/写盘/追加各一处），用户
# 实测「对话数量过多，之前的记录会消失」。放宽到 2000 条：滚动条
# 拖到顶就能翻回几个月前的对话，tasks.json 体积仍在百 KB 量级。
MSG_KEEP = 2000


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

# v1.9.9.27：日常任务（每天/每周X 重复）专用色。
# 用青绿色系与临时任务的「红橙蓝灰」优先级色区分开——日常不参与优先级，
# 只在视觉上让人一眼看出「这是每天要做的事」。
C_DAILY = "#2F8F83"          # 日常任务竖条 / 徽标 / 气泡强调条
C_DAILY_BG = "#EAF6F3"       # 日常行极淡底色（浅色主题下）
C_DAILY_SOFT = "#BFE3DC"     # 日常行底色（与主题底色混合用）

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
        # v1.9.9.45：默认 0.88 太透，桌面图标压在字上影响阅读；新装默认 0.95（已有用户保存过的值不受影响）
        self.alpha = 0.95          # 便签透明度（底栏滑块可调，0.40~1.00）
        self.bell_mode = "chime"
        self.user_name = ""        # 用户昵称（首次启动问出来）
        self.bot_name = ""         # 助手自己的名字
        self.setup_stage = 0       # 0=没问过 1=已问昵称 2=都问好了
        self.bubble_enabled = True # 右下角「未完成任务」气泡开关
        self.bubble_w = 84         # 气泡宽度（拖拽缩放，60~160）
        self.font_scale = 1.0      # 字体缩放（0.8~1.3）
        self.enter_hint_done = False  # 「回车发送」提示已教过（v1.9.9.21）
        self.text_darken = None    # 手动字体深浅；None=按透明度自动推导
        self.notes = []
        self.note_pos = None
        self.note_geom = None
        self.chat_h = None
        self.quotes = {"zh": {"last": "", "recent": []},
                       "en": {"last": "", "recent": []}}   # 中英各一套
        # v1.9.9.45：读盘失败标记（界面据此提示 + 保护原文件）
        self.load_failed = False
        self.load_error = ""
        self.corrupt_copy = None
        self.hist_failed = False
        self.load()
        self.load_history()
        self.sync_history()

    @staticmethod
    def _today():
        return dt.date.today().isoformat()

    def load(self):
        """读任务文件。

        v1.9.9.45：旧版把整个读取塞进一个 try 里 `except: pass`——
        文件坏一格（断电、手改错一个逗号）就静默变成空数据，随后
        第一次保存把**原件覆盖**，任务和昵称一起永久消失（用户实测
        丢过 7 条任务）。现在：
          1. 编码兼容 UTF-8（含 BOM）/ GBK，记事本另存为哪种都能读；
          2. 真读不懂 → 把原文件另存一份 `.corrupt-时间戳`，再继续；
          3. 每个字段独立兜底，一个值坏不再连累后面的设置（B5）。
        """
        if not os.path.exists(self.path):
            return
        text = None
        try:
            with open(self.path, "rb") as f:
                raw = f.read()
            for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
                try:
                    text = raw.decode(enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
        except Exception as exc:
            self._mark_corrupt("读取失败：%s" % exc)
            return
        if text is None:
            self._mark_corrupt("编码无法识别（不是 UTF-8 也不是 GBK）")
            return
        try:
            obj = json.loads(text.lstrip("\ufeff"))
            if not isinstance(obj, dict):
                raise ValueError("顶层不是对象")
        except Exception as exc:
            self._mark_corrupt("JSON 解析失败：%s" % exc)
            return
        self._apply_obj(obj)

    def _mark_corrupt(self, reason):
        """数据文件读不了：**先把原文件留一份**，绝不无声覆盖。

        保留的不是「加载失败状态」而是原件本身——用户还能拿去人工抢救，
        也方便我们复盘。副本名字带时间戳，多次损坏不会互相覆盖。"""
        ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        keep = self.path + ".corrupt-" + ts
        try:
            shutil.copy2(self.path, keep)
            self.corrupt_copy = keep
        except Exception:
            self.corrupt_copy = None
        self.load_failed = True
        self.load_error = reason
        try:
            with open(os.path.join(data_dir(), "load_error.log"), "a",
                      encoding="utf-8") as lf:
                lf.write("%s  %s  %s\n" % (
                    dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    self.path, reason))
        except Exception:
            pass

    def _apply_obj(self, obj):
        """把读出来的字典灌进 Store；每个字段独立 try（B5）。

        旧版一个 float() 抛错，后面昵称/主题/字体全被跳过，等于「一处坏
        字段把所有设置恢复默认」。"""
        def _safe(fn, default=None):
            try:
                return fn()
            except Exception:
                return default

        self.tasks = _safe(lambda: [t for t in obj.get("tasks", [])
                                    if isinstance(t, dict)], []) or []
        # 坏时间清洗（B4）：hhmm 不是 HH:MM 就清空，否则提醒循环会整轮抛异常
        for _t in self.tasks:
            _h = _t.get("hhmm")
            if _h is not None:
                try:
                    _hh, _mm = str(_h).split(":")
                    if not (0 <= int(_hh) <= 23 and 0 <= int(_mm) <= 59):
                        raise ValueError
                except Exception:
                    _t["hhmm"] = None
                    _t["deadline_txt"] = None
        self.messages = _safe(lambda: obj.get("messages", [])[-MSG_KEEP:], []) or []
        self.topmost = _safe(lambda: bool(obj.get("topmost", True)), True)
        self.theme = _safe(lambda: obj.get("theme", palette.DEFAULT_ID),
                           palette.DEFAULT_ID)
        self.lang = _safe(lambda: obj.get("lang", "zh"), "zh")
        self.quotes = _safe(lambda: obj.get("quotes"), None) or {
            "zh": {"last": obj.get("quote_last", ""),
                   "recent": (obj.get("quote_recent") or [])[-60:]},
            "en": {"last": "", "recent": []},
        }
        self.clock_geom = _safe(lambda: obj.get("clock_geom"))
        self.bell_mode = _safe(lambda: obj.get("bell_mode", "chime"), "chime")
        self.notes = _safe(lambda: [n for n in obj.get("notes", [])
                                    if isinstance(n, dict)], []) or []
        self.note_pos = _safe(lambda: obj.get("note_pos"))
        self.note_geom = _safe(lambda: obj.get("note_geom"))
        self.chat_h = _safe(lambda: obj.get("chat_h"))
        self.alpha = _safe(lambda: float(obj.get("alpha", 0.95)), 0.95)
        self.user_name = _safe(lambda: (obj.get("user_name") or "").strip(), "")
        self.bot_name = _safe(lambda: (obj.get("bot_name") or "").strip(), "")
        self.setup_stage = _safe(lambda: int(obj.get("setup_stage", 0)), 0)
        self.bubble_enabled = _safe(lambda: bool(obj.get("bubble_enabled", True)), True)
        self.bubble_w = _safe(lambda: max(60, min(160, int(obj.get("bubble_w", 84) or 84))), 84)
        self.font_scale = _safe(lambda: max(0.8, min(1.3, float(obj.get("font_scale", 1.0) or 1.0))), 1.0)

        def _darken():
            td = obj.get("text_darken")
            if td is None:
                return None
            td = float(td)
            if td > 1.0:                  # 旧版本存 0~45 的百分数
                td = td / 100.0
            return max(0.0, min(1.0, td))
        self.text_darken = _safe(_darken, None)
        # v1.8.1 起不再问助手名：停留在旧阶段 2 的直接视为完成
        if self.setup_stage >= 2:
            self.setup_stage = 3
        self.enter_hint_done = _safe(lambda: bool(obj.get("enter_hint_done", False)), False)
        self.tray_notify_shown = _safe(lambda: bool(obj.get("tray_notify_shown", False)), False)
        self.tray_notify_off = _safe(lambda: bool(obj.get("tray_notify_off", False)), False)
        for k in ("zh", "en"):
            self.quotes.setdefault(k, {"last": "", "recent": []})
        saved_day = _safe(lambda: obj.get("date", self._today()), self._today())
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
            self._roll_day(today)
            self.today = today
            self.messages = []

    def _roll_day(self, today):
        """跨天重置（v1.9.9.27：抽成一处，启动和运行时 tick 共用一套规则）

        日常任务（带 repeat）：
          - 今天该做 → 复活（done=False），`last_done_day` 留着，靠它算连续；
          - 今天不该做（如每周一三五的跑，今天是周二）→ 压在已完成区，
            不让用户看到一件「今天根本不用做」的活。
        """
        for t in self.tasks:
            t["reminded"] = False
            t["reminded_day"] = None
            rep = t.get("repeat")
            if rep:
                # v1.9.9.32：兼容旧数据的字符串 repeat（「每周三」）
                if isinstance(rep, str):
                    rep = core.find_repeat(rep)
                    if rep is None:
                        continue
                    t["repeat"] = rep
                try:
                    due = core.repeat_due_today(rep)
                except Exception:
                    due = False
                if due:
                    t["done"] = False
                    t["done_at"] = None
                else:
                    t["done"] = True
                continue
            dd = t.get("due_date")
            if dd:
                # 有明确截止日：还没到就保留时刻，过期才清
                if dd < today and not t.get("done"):
                    t["hhmm"] = None
                continue
            if not t.get("done"):
                t["hhmm"] = None

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
            "messages": self.messages[-MSG_KEEP:],
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
            "enter_hint_done": bool(getattr(self, "enter_hint_done", False)),
            # v1.9.9.34：托盘后台气泡（首次最小化只弹一次 + 用户可关）
            "tray_notify_shown": bool(getattr(self, "tray_notify_shown", False)),
            "tray_notify_off": bool(getattr(self, "tray_notify_off", False)),
        }
        # v1.9.9.45：**写盘前**先覆盖当天快照——备份的价值在于「覆盖发生前
        # 的那一刻」。旧版是写完之后每天只快照一次，结果当天记了 23 条任务、
        # 备份里还是开机时的空壳（实测 704 字节）。
        try:
            import exporter as _exp
            _exp.auto_snapshot(data_dir(),
                               [("tasks.json", self.path),
                                ("history.json", self.hist_path)],
                               force=True)
        except Exception:
            pass
        self._atomic(self.path, obj)
        # 首次保存时上面没有源文件可拷，写完后补一次（保证备份从第一天就有）
        try:
            import exporter as _exp2
            _exp2.auto_snapshot(data_dir(),
                                [("tasks.json", self.path),
                                 ("history.json", self.hist_path)],
                                force=True)
        except Exception:
            pass

    # ---------------- 历史归档
    def load_history(self):
        """读历史文件（v1.9.9.45：损坏时保护原件，绝不静默清空）

        旧版读失败就当空历史，而 __init__ 紧接着调 sync_history()——
        于是启动瞬间就把损坏文件重写成「只剩今天」，过去所有天消失。
        现在读失败会：① 留一份 `.corrupt-时间戳` 副本；② 置 hist_failed，
        sync_history 在本次会话内拒绝写盘。"""
        if not os.path.exists(self.hist_path):
            return
        text = None
        try:
            with open(self.hist_path, "rb") as f:
                raw = f.read()
            for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
                try:
                    text = raw.decode(enc)
                    break
                except (UnicodeDecodeError, LookupError):
                    continue
        except Exception:
            text = None
        obj = None
        if text is not None:
            try:
                obj = json.loads(text.lstrip("\ufeff"))
            except Exception:
                obj = None
        if not isinstance(obj, dict):
            ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            keep = self.hist_path + ".corrupt-" + ts
            try:
                shutil.copy2(self.hist_path, keep)
                self.hist_corrupt_copy = keep
            except Exception:
                self.hist_corrupt_copy = None
            self.hist_failed = True
            try:
                with open(os.path.join(data_dir(), "load_error.log"), "a",
                          encoding="utf-8") as lf:
                    lf.write("%s  %s  历史文件解析失败，已保留副本 %s\n" % (
                        dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        self.hist_path, self.hist_corrupt_copy or "(复制失败)"))
            except Exception:
                pass
            return
        days = obj.get("days", {})
        if isinstance(days, dict):
            self.history = {k: v for k, v in days.items() if isinstance(v, list)}
        # 记下当前签名：内容没变就不该在启动时写盘
        self._hist_last_sig = self._hist_sig(self.history.get(self.today, []))

    def save_history(self):
        if getattr(self, "hist_failed", False):
            return          # 原件已另存副本；本次会话不覆盖损坏的历史文件
        self._atomic(self.hist_path, {"days": self.history})

    def purge_history(self, titles=None, only_today=False, tids=None):
        """从历史里移除指定条目的记录。

        注意 only_today 的语义（v1.9.9.45 起删除/改名默认**只动今天**）：
        用户删掉「今天这条买牛奶」，昨天的买牛奶是他真实完成过的记录，
        不该被一起抹掉——旧版遍历所有天按标题清，历史会一片片消失，
        而且撤回也补不回来。"""
        titles = titles or set()
        tids = tids or set()
        if not titles and not tids:
            return
        try:
            days = [dt.date.today().isoformat()] if only_today \
                else list(self.history.keys())
            changed = False
            for day in days:
                rows = self.history.get(day) or []
                def _keep(r):
                    if r.get("tid"):
                        return r["tid"] not in tids
                    return r.get("title", "") not in titles
                kept = [r for r in rows if _keep(r)]
                if len(kept) != len(rows):
                    self.history[day] = kept
                    changed = True
            if changed and not getattr(self, "hist_failed", False):
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
        """把当日任务快照写进历史。

        v1.9.9.45：行绑定任务 id（tid）。旧版只按标题合并——同一天两条
        「跑步」会被并成一条，删掉其中一条还会把另一条的历史也带走。
        没有 tid 的旧数据继续按标题匹配，读旧文件不会突然多出一堆重复行。
        """
        if getattr(self, "hist_failed", False):
            return          # 历史文件损坏：本次会话不写，先把原件留给人抢救
        day = day or self.today
        snap = self.history.get(day, [])
        by_title = {}
        by_tid = {}
        for r in snap:
            if r.get("tid"):
                by_tid.setdefault(r["tid"], r)
            by_title.setdefault(r.get("title", ""), r)
        changed = False
        for t in self.tasks:
            title = t.get("title", "")
            if not title:
                continue
            tid = t.get("id")
            old = by_tid.get(tid) if tid else None
            if old is None:
                cand = by_title.get(title)
                # 旧行没有 tid 时才按标题接管（并补上 tid）
                if cand is not None and not cand.get("tid"):
                    old = cand
                    old["tid"] = tid
                    if tid:
                        by_tid[tid] = old
                    changed = True
            if old is None:
                old = {
                    "title": title,
                    "tid": tid,
                    "hhmm": t.get("hhmm"),
                    "score": t.get("score", 30),
                    "done": bool(t.get("done")),
                    "done_at": t.get("done_at", "") if t.get("done") else "",
                }
                snap.append(old)
                by_title[title] = old
                if tid:
                    by_tid[tid] = old
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
# v1.9.9.23：锚定句首/句尾，避免「小王叫小张帮他买东西」把「小张」当助手名
_BOT_NAME_RE = re.compile(
    r"^[\s，,]*(?:你|您)(?:以后|就|都|要|希望|得)?(?:就)?叫(?!我|自己|什么|啥)"
    r"([^，,。.!！?？\s]{1,8})\s*[吧哦呀啊啦哈。.！!～~]*\s*$")

# v1.9.9.23：用户随时改自己的昵称——「你叫我boss吧 / 以后叫我Alex /
# 我叫小李 / 我的名字是老王 / 设置我的名字是小李」
_USER_NAME_RE = re.compile(
    r"^[\s，,]*(?:(?:你|您)(?:以后|就|都|要|希望|得)?(?:就)?叫我|"
    r"以后叫我|以后就叫我|就叫我|叫我|我叫|我的名字是|我的名字叫|"
    r"设置我的名字是|设置我的昵称是|改名叫)\s*([^，,。.!！?？\s]{1,12}?)\s*"
    r"[吧哦呀啊啦哈。.！!～~]*\s*$")

# v1.9.9.29：元指令处理器的「已处理但不回话」哨兵。
# 用独立对象而不是 ""——空串会和 None（=没处理）混在一起。
_SILENT = object()


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
        self.W = int(getattr(app.store, "bubble_w", 100) or 100)  # v1.9.9.17: 84→100
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
        # v1.9.9.40：右键气泡 = 菜单。主窗口收到托盘后，右下角这个气泡
        # 是屏幕上唯一的可见入口，必须能右键找回主窗口
        self._rb_targets = [self.main, self.count_lbl, self.txt_lbl]
        if img is not None:
            self._rb_targets.append(self.ic_lbl)
        for w in self._rb_targets:
            w.bind("<Button-3>", self._popup_menu)
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
    def _popup_menu(self, e):
        """v1.9.9.40：右键桌面气泡——显示主窗口 / 记一条 / 展开(收起)任务"""
        m = tk.Menu(self.win, tearoff=0)
        m.add_command(label=tr("tray_show"), command=self.app.restore_from_tray)
        m.add_command(label=tr("empty_add"),
                      command=lambda: (self.app.restore_from_tray(),
                                       self.app._focus_entry()))
        m.add_command(label=tr("bubble_toggle"), command=self.toggle)
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

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
        """气泡展开顺序（v1.9.9.43：与主列表同构——今天的日常在最上）

        旧版把所有任务混在一起按「优先级→截止→时刻」排，日常任务被分数
        插进临时任务中间、上下一分为二，用户看不出规律。现在：
        ① 今天的日常（按时刻）→ ② 临时任务（按 优先级→截止→时刻，
        沿用 v1.9.9 规则）→ ③ 不在今天到期的日常（刚建的每周X任务，
        按创建顺序）。与主列表「日常组在前、临时在后」的心智一致。"""
        today = self.app.store._today()

        def _key(it):
            i, t = it
            if self.app._is_daily(t):
                if self.app._daily_due_today(t):
                    return (0, t.get("hhmm") or "99:99", i)   # 今天的日常：按时刻
                return (2, t.get("hhmm") or "99:99", i)       # 不在今天：垫底
            has_dl = bool(t.get("hhmm") or t.get("due_date"))
            dd = t.get("due_date") or (today if t.get("hhmm") else "9999")
            return (1, -t.get("score", 0), 0 if has_dl else 1,
                    dd, t.get("hhmm") or "99:99", i)          # 临时：按紧急度

        return [t for _, t in sorted(enumerate(self._undone()), key=_key)]

    def _dl_text(self, t):
        """任务条右侧的截止小字（v1.9.9.43：与主列表行首同口径）——
        日常任务显示「每周四 21:00」周期文字，临时任务「M/D HH:MM」"""
        try:
            if self.app._is_daily(t):
                rt = self.app._row_time_text(t)
                if rt:
                    return rt
        except Exception:
            pass
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
            # v1.9.9.27：日常任务（带 repeat）特殊标注 —— 青色色条 + 青色底 +
            # 标题前的 ● 与青色字，跟临时任务的优先级色一眼分开。用户明确要求
            # 「日常任务没有优先级，但气泡里必须能看出来不一样」。
            daily = self.app._is_daily(t)
            _rowbg = C_DAILY_BG if daily else C.ROW2
            inner = tk.Frame(row, bg=_rowbg, highlightthickness=1,
                             highlightbackground=(C_DAILY if daily else C.LINE))
            inner.pack(fill="both", expand=True, padx=1, pady=1)
            # v1.9.9：色条跟主列表同一套优先级色（紧急红/重要橙/一般蓝/不急灰）
            _plabel, pcolor = core.priority_label(t.get("score", 0))
            dot = tk.Frame(inner, bg=(C_DAILY if daily else pcolor), width=3)
            dot.pack(side="left", fill="y")
            lbl = tk.Label(inner, text=("● " + disp) if daily else disp,
                           bg=_rowbg, fg=(C_DAILY if daily else C.TEXT),
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
                dlc_lbl = tk.Label(inner, text="· " + dl, bg=_rowbg,
                                   fg=("#E2434B" if expired else
                                       (C_DAILY if daily else C.SUB)),
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
        # v1.9.9.45：界面回调异常统一进日志（打包后 stdout 不可见，
        # 否则「点了没反应」永远查不到线索）
        try:
            root.report_callback_exception = self._report_callback_exception
        except Exception:
            pass
        self._last_save_err = None     # 上一次提示过的保存错误
        self._save_warned = False
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
        self._tray = None          # 系统托盘（v1.9.9.20，Windows 才可用）
        # v1.9.9.23：托盘确定不可用（非 Windows / 初始化失败）才允许 ✕ 直接退出；
        # 启动窗口期内点 ✕ 先等托盘就绪（Bug 2）
        self._tray_failed = False
        self._tray_wait_deadline = None
        self._tray_hidden = False
        self._long_titles = {}     # 本屏被截断的标题 → 全文（悬停提示）
        self._title_tip = None
        self._edit_entry = None    # 当前正在编辑标题的 Entry
        self._bubble = None        # 右下角「未完成任务」气泡
        self._undo_last = None     # 最近一次可撤回的操作（v1.9.5）
        self._undo_stack = []      # 撤回栈：最近 3 步（v1.9.9.22）
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
        self._style_scrollbars()        # v1.9.9.35：滚动条主题配色
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
            # v1.9.9.45：数据读不出来要**当面说**，并给出保留的副本路径。
            # 旧版静默变成空列表，用户以为「软件把我的东西吃了」。
            if getattr(self.store, "load_failed", False):
                self.push("bot", tr("load_corrupt_notice",
                                    e=self.store.load_error or "?",
                                    p=self.store.corrupt_copy or "?"))
            if getattr(self.store, "hist_failed", False):
                self.push("bot", tr("hist_corrupt_notice",
                                    p=getattr(self.store, "hist_corrupt_copy", "?") or "?"))
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

    def _ime_composing(self):
        """中文输入法是否正在组字（候选词未上屏）。

        v1.9.9.20：拼音里按回车是「上屏」，原来被当成发送，消息发出去
        半截、拼音残留，用户只好再按一次回车——这就是「要按两次」的来源。
        Windows 下用 ImmGetContext + ImmGetCompositionStringW 读组字串，
        非空即组字中；读不到就当作没在组字（退回原行为，不会更糟）。
        """
        if os.name != "nt":
            return False
        try:
            import ctypes
            from ctypes import wintypes
            hwnd = self.entry.winfo_id()
            imm32 = ctypes.windll.imm32
            himc = imm32.ImmGetContext(wintypes.HWND(hwnd))
            if not himc:
                return False
            try:
                # GCS_COMPSTR = 0x0008，返回组字串字节数（宽字符）
                n = imm32.ImmGetCompositionStringW(himc, 0x0008, None, 0)
                # 返回负数表示当前没有组字
                return n is not None and n > 0
            finally:
                imm32.ImmReleaseContext(wintypes.HWND(hwnd), himc)
        except Exception:
            return False

    def _on_entry_return(self, e=None):
        """回车：组字中交给输入法，组字结束才发送"""
        if self._ime_composing():
            return None          # 不 return "break"，让输入法自己上屏
        self.on_send()
        return "break"

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
        # v1.9.9.45：行内改名/改便签时，哪怕焦点没落到编辑框，按键也
        # 必须进编辑框，不能进发送框（旧版在这里把字母塞进发送框，
        # 回车还会凭空新建一条脏任务——QA 实测「Milkbread」就是这么来的）
        ed = getattr(self, "_edit_entry", None)
        if ed is not None:
            try:
                alive = bool(ed.winfo_exists())
            except Exception:
                alive = False
            if alive and w is not ed:
                try:
                    ed.focus_force()
                    if ks == "BackSpace":
                        n = len(ed.get())
                        i = ed.index("insert")
                        if i > 0:
                            ed.delete(i - 1)
                    elif ks == "Delete":
                        i = ed.index("insert")
                        if i < len(ed.get()):
                            ed.delete(i)
                    elif ks in ("Return", "KP_Enter"):
                        ed.event_generate("<Return>")
                    elif ks == "Left":
                        ed.icursor(max(0, ed.index("insert") - 1))
                    elif ks == "Right":
                        ed.icursor(min(len(ed.get()), ed.index("insert") + 1))
                    elif ch and ch.isprintable():
                        ed.insert("insert", ch)
                    else:
                        return
                    self.diag("按键回补到行内编辑框 %s" % ks)
                except Exception:
                    pass
                return "break"
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
        r.attributes("-alpha", getattr(self.store, "alpha", 0.95))  # 半透明：可调
        # 文字加深：手动滑块优先；没动过就按透明度推导
        C.set_darken(self._effective_darken())
        sw, sh = r.winfo_screenwidth(), r.winfo_screenheight()
        w = int(sw / 6)
        h = int(sh / 3)
        # v1.9.9.17：默认最小尺寸 250x300 → 320x420（任务列表+聊天区太挤）
        # v1.9.9.20：再提到 360x460——320 宽下长标题常挤成两行、
        # 列表只能显示三四条，用户反馈「偏窄、留白多」
        w = max(360, min(w, 480))
        h = max(460, min(h, 560))
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
        r.protocol("WM_DELETE_WINDOW", self.close_or_hide)
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
        """按 store.font_scale（0.8~1.3）构建各处字号；字体大小滑块实时调用

        v1.9.9.42 两处关键改动：
        ① 改为**命名 Font 对象**并 configure() 原地改字号——所有引用同一
           字体的控件在滑块拖动瞬间同步更新。旧版只换元组，已创建的
           控件纹丝不动，界面大部分区域「字体大小调了没反应」就是它。
        ② 小字号整体上调一档：旧版界面文字 7/8pt（约 9/11px），对话区
           却是 9pt（12px）；雅黑在 10px 以下抗锯齿很糟，正是用户说的
           「马赛克感」。现在界面文字 9pt、辅助文字 8pt，与对话一致。"""
        sc = float(getattr(self.store, "font_scale", 1.0) or 1.0)
        for name, px in (("f_task", max(8, round(10 * sc))),
                         ("f_small", max(8, round(9 * sc))),
                         ("f_tiny", max(7, round(8 * sc))),
                         ("f_chat", max(8, round(9 * sc)))):
            f = getattr(self, "_" + name + "_f", None)
            if f is None:
                f = tkfont.Font(root=self.root, family=self.f_ui, size=px)
                setattr(self, "_" + name + "_f", f)
            else:
                f.configure(family=self.f_ui, size=px)
            setattr(self, name, f)

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
                                  font=self.f_tiny, anchor="e", justify="right",
                                  wraplength=300)
        self.quote_lbl.pack(side="right", fill="x", expand=True)
        self.quote_row.bind("<Button-1>", lambda e: self.roll_quote(manual=True))
        self.quote_lbl.bind("<Button-1>", lambda e: self.roll_quote(manual=True))
        # v1.9.9.35：右键哲言栏 = 找回主窗口。主窗收到托盘后没有任务栏
        # 图标可点，这条右键是除托盘图标外的第二条找回路径
        self.quote_row.bind("<Button-3>", lambda e: self._quote_bar_menu())
        self.quote_lbl.bind("<Button-3>", lambda e: self._quote_bar_menu())
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
        # v1.9.9.32：聊天区右侧滚动条（同待办区——拖一下直达旧消息）
        self.chat_sb = ttk.Scrollbar(self.chat_wrap, orient="vertical",
                                     command=self._chat_scroll)
        self.chat_sb.pack(side="right", fill="y")
        self.chat_cv = Canvas(self.chat_wrap, height=self.chat_h)
        self.chat_cv.pack(side="top", fill="both")
        self.chat_cv.configure(yscrollcommand=self._chat_sb_sync)
        self.chat_cv.bind("<Configure>", lambda e: self.debounce("chat", self.render_messages))
        # v1.9.9.37：滚轮统一走 bind_all 路由（_wheel_route）。
        # 这里不再绑控件级滚轮——Windows 会把滚轮派给「持有焦点的输入框」
        # 而不是指针下的控件，控件级绑定在那条路上根本收不到事件。

        # 输入行
        self.input_row = tk.Frame(r, bg=C.BG)
        self.input_row.pack(side="top", fill="x", padx=6, pady=(2, 4))
        self.entry = tk.Entry(self.input_row, relief="flat", bd=0, bg=C.INPUT_BG,
                              fg=C.TEXT, insertbackground=C.TEXT, font=self.f_chat,
                              highlightthickness=1, highlightbackground=C.INPUT_LINE,
                              highlightcolor=C.ACCENT)
        self.entry.pack(side="left", fill="x", expand=True, ipady=4)
        # v1.9.9.20：中文输入法组字中按回车是「上屏候选词」，不能当发送。
        # Tk 在组字时仍会把 <Return> 派发过来，这里先探一下组字状态再决定。
        self.entry.bind("<Return>", self._on_entry_return)
        self.entry.bind("<KP_Enter>", self._on_entry_return)
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
        # v1.9.9.20：显式告诉用户回车能发，也说明输入法上屏时回车不算发送
        # v1.9.9.21：只教一次——第一次成功发送后永久撤掉（_retire_enter_hint），
        # 且重启不再出现；输入框不再被这行字挤窄
        if not getattr(self.store, "enter_hint_done", False):
            self.hint_lbl = tk.Label(self.input_row, text=tr("enter_send_hint"),
                                     bg=C.BG, fg=C.SUB, font=self.f_tiny)
            self.hint_lbl.pack(side="left", padx=(4, 0))
        else:
            self.hint_lbl = None

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
        # v1.9.9.32：右侧可拖动滚动条——消息/任务一多，光靠滚轮一格一格
        # 挪太慢。先建画布对象（不布局），滚动条 pack 在右、画布 pack 占余下
        self.list_cv = Canvas(self.list_wrap)
        self.list_sb = ttk.Scrollbar(self.list_wrap, orient="vertical",
                                     command=self.list_cv.yview)
        self.list_sb.pack(side="right", fill="y")
        self.list_cv.pack(side="top", fill="both", expand=True)
        self.list_cv.configure(yscrollcommand=self.list_sb.set)
        self.list_cv.bind("<Configure>", lambda e: self.debounce("list", self.refresh_tasks))
        # v1.9.9.37：同聊天区，滚轮统一走全局路由

        # v1.9.9.36：滚轮全局路由——原来只绑在两块画布上，指针一放到
        # 滚动条/标题栏/底栏上滚轮就「没反应」。bind_all 统一收，
        # 自带绑定的画布跳过（避免一次滚动走两个 handler 加倍）
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(seq, self._wheel_route, add="+")

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
        # v1.9.9.45：短标签仍放不下（英文 + 大字体 + 窄窗口）→ 收紧内边距。
        # 旧版到此为止，最右侧「Clock」会被窗口边缘裁成「Cloc」
        try:
            self.foot.update_idletasks()
            need = 8
            for lbl, _k, _s in pairs:
                need += lbl.winfo_reqwidth() + 8
            if need > w:
                for lbl, _k, _s in pairs:
                    lbl.config(padx=1)
                    try:
                        lbl.pack_configure(padx=0)
                    except Exception:
                        pass
                self.cal_btn.pack_configure(padx=(0, 2))
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
        # v1.9.9.20：✕ 改成「收到托盘」（托盘可用时），右键才真正退出，
        # 这样关掉主窗口也不会丢提醒。托盘不可用（非 Windows）则保持退出。
        self._btn_close(bx, h // 2,
                        self.close_or_hide if self._tray_ok() else self.quit,
                        "#B4463C")
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

    def _daily_counts(self):
        """(今天该做的日常任务数, 其中已打卡数, 未做完的临时任务数,
        临时已完成数, 临时总数)

        日常任务按「今天到期」算，不是全量——每周一三五的跑步，周二
        不该出现在今天的分母里。
        v1.9.9.41：临时任务也带 x/y 完成度，与日常格式统一。"""
        dn = 0
        dtoday = 0
        tmp_left = 0
        tmp_total = 0
        for t in self.store.tasks:
            if self._is_daily(t):
                if self._daily_due_today(t):
                    dtoday += 1
                    if t.get("done"):
                        dn += 1
            else:
                tmp_total += 1
                if not t.get("done"):
                    tmp_left += 1
        return dtoday, dn, tmp_left, tmp_total - tmp_left, tmp_total

    def _counter_text(self, left, done):
        """底栏计数（v1.9.9.41 统一措辞与格式）

        「日常任务 2/4 · 临时任务 3/7」——两段都用 已完成/总数 格式；
        只有日常没有临时 → 只显示日常段；只有临时 → 「临时任务 x/y ·
        已完成 x」。原措辞「今日日常 / 待办」含义含混，一并更名。"""
        try:
            n, dn, tmp_left, tmp_done, tmp_total = self._daily_counts()
        except Exception:
            n, dn, tmp_left, tmp_done, tmp_total = 0, 0, left, 0, left
        if n and tmp_total:
            return tr("daily_left", d=dn, n=n, td=tmp_done, tt=tmp_total)
        if n:
            return tr("daily_only", d=dn, n=n)
        return tr("counter_plain", td=tmp_done, tt=tmp_total)

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
    def _check_save_error(self):
        """v1.9.9.45：保存失败要**当场说**，不能等下次重启才发现。

        旧版 `_save_error` 只在启动问候时读一次，运行期间失败完全无声；
        用户以为记上了，重启才知道丢了。"""
        err = Store._save_error
        if not err:
            self._save_warned = False
            return
        if err == getattr(self, "_last_save_err", None) and \
                getattr(self, "_save_warned", False):
            return
        self._last_save_err = err
        self._save_warned = True
        try:
            self.push("bot", tr("save_failed_runtime", e=err))
            self.flash(tr("save_failed_short"))
        except Exception:
            pass

    def _report_callback_exception(self, exc, val, tb):
        """v1.9.9.45：统一接管界面回调异常。

        打包成 windowed 程序后 stdout 不可见，回调里抛异常等于「点了没
        反应」，用户描述不清、维护者也没有线索。现在一律写日志 + 提示。"""
        try:
            import traceback
            detail = "".join(traceback.format_exception(exc, val, tb))
            self.diag("[EXC] " + detail.replace("\n", " | ")[:900])
        except Exception:
            detail = "%s: %s" % (exc, val)
        try:
            self.flash(tr("ui_error"))
        except Exception:
            pass

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
                        # v1.9.9.45：日志轮转——长期使用不会无限变大
                        try:
                            if os.path.getsize(self._diag_path) > 1024 * 1024:
                                for _i in (2, 1):
                                    _a = self._diag_path + (".%d" % _i)
                                    _b = self._diag_path + (".%d" % (_i + 1))
                                    if os.path.exists(_a):
                                        if os.path.exists(_b):
                                            os.remove(_b)
                                        os.rename(_a, _b)
                                _b1 = self._diag_path + ".1"
                                if os.path.exists(_b1):
                                    os.remove(_b1)
                                os.rename(self._diag_path, _b1)
                        except Exception:
                            pass
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
    def _style_scrollbars(self):
        """滚动条配色（v1.9.9.41 微调）：旧版底槽 = 背景色，轨道完全隐形，
        只剩一块浅色滑块悬在半空，看不出「这是滚动条」。
        现在：底槽比背景深一档（轨道可见），滑块**纯深色**——clam 默认
        会在滑块上画几道抓握白线（gripcount），设为 0 全部去掉，
        颜色再加深一档，就是一根干净的深色条。悬停/按下变主题强调色。"""
        try:
            style = ttk.Style(self.root)
            if style.theme_use() != "clam":
                style.theme_use("clam")     # clam 才允许逐项配色
            thumb = _mix(C.LINE, C.TEXT, 0.45)      # 滑块：纯深色
            trough = _mix(C.BG, C.SUB, 0.20)        # 底槽：比背景深一档
            style.configure("Vertical.TScrollbar",
                            background=thumb,
                            troughcolor=trough,
                            bordercolor=trough,
                            lightcolor=thumb,       # clam 的立体边也压平，
                            darkcolor=thumb,        # 整个滑块统一一种颜色
                            arrowcolor=thumb,
                            gripcount=0,            # 去掉滑块上的白色抓握线
                            relief="flat")
            style.map("Vertical.TScrollbar",
                      background=[("active", C.ACCENT),
                                  ("pressed", C.ACCENT)])
        except Exception:
            pass

    def apply_theme(self, theme_id, announce=True):
        self.diag("== apply_theme %s ==" % theme_id)
        try:
            self.timed("set_theme+save", lambda: (C.set_theme(palette.get(theme_id)),
                                                  setattr(self.store, "theme", theme_id),
                                                  self.store.save()))
            # Tk 控件（非 Canvas）要显式刷色
            self.timed("tk控件刷色", lambda: self._recolor_widgets())
            self.timed("滚动条刷色", self._style_scrollbars)
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
        """勾掉一项后：报「任务完成」。哲言只在今日全部完成时补一句
        （v1.9.9.35：用户实测——全勾完了对话里却没哲言）"""
        all_done = left <= 0
        q = self.draw_quote() if all_done else None

        def _mk(lang):
            s = i18n.render("task_done_push", dict(title=task["title"]), lang)
            if all_done:
                s += " " + i18n.render("task_done_all", dict(n=len(self.store.tasks)), lang)
                if q:
                    s += "\n" + self.fmt_quote(q)
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

    def _over_scrollbar(self, e):
        """v1.9.9.35：指针是否在滚动条上——滚动条贴着窗口右/下缘，
        会被边缘缩放热区覆盖（光标变「调整大小」、点下去拉窗口），
        必须先让位"""
        w = getattr(e, "widget", None)
        return isinstance(w, (tk.Scrollbar, ttk.Scrollbar))

    def _edge_cursor(self, e):
        """悬停在边缘 → 显示缩放光标（节流：值没变不刷）"""
        if getattr(self, "_edge", None):
            return
        if self._over_scrollbar(e):
            # 滚动条区域还原本来的光标（上次悬停边缘可能残留缩放样式）
            if self.root.cget("cursor") != "":
                self.root.config(cursor="")
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
        if self._over_scrollbar(e):
            return              # 点滚动条 = 滚动，不是拉窗口
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
            r.attributes("-alpha", getattr(self.store, "alpha", 0.95))  # 半透明：可调
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
        # v1.9.9.20：先撤托盘图标，否则退出后系统栏里会留一个死图标
        try:
            if getattr(self, "_tray", None):
                self._tray.stop()
        except Exception:
            pass
        b = getattr(self, "_bubble", None)
        if b is not None:
            b.close()
        for c in list(getattr(self, "_due_cards", [])):
            c.close()
        self.store.sync_history()
        self._save_note_pos()
        self.store.save()
        # v1.9.9.45：保存失败就别装作没事——旧版这里 save() 之后不管
        # 结果直接 os._exit(0)，磁盘满/文件被占用时最后一次改动静默丢失。
        if Store._save_error:
            try:
                from tkinter import messagebox
                self.root.deiconify()
                ok = messagebox.askyesno(
                    self.app_name(), tr("quit_save_failed", e=Store._save_error))
                if not ok:
                    self._closing = False
                    self.root.lift()
                    return
            except Exception:
                pass
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
        # v1.9.9.39：首次渲染发生在窗口映射之前，winfo_height() 还是 1，
        # 旧代码退到 40px 假视口算 offset，而滑块同步却用真实高度——
        # 两边比例对不上，表现就是「初始状态滑块悬在中间/奇怪位置」。
        # 现在高度未知时先不画，等 <Map>/尺寸就绪后用真实高度补画。
        if cv.winfo_height() <= 1:
            cv.delete("all")
            if not getattr(self, "_chat_defer_armed", False):
                self._chat_defer_armed = True
                cv.bind("<Map>", self._chat_map_redraw, add="+")
                cv.after(120, self._chat_map_redraw)   # 兜底：防个别环境不发 Map
            return
        self._chat_defer_armed = False
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
        self._chat_sb_sync()                 # v1.9.9.38：滑块随内容实时同步

    def _chat_map_redraw(self, _e=None):
        """窗口映射/尺寸就绪后的补画入口（v1.9.9.39，配合 render_messages 的
        「高度未知先不画」）：尺寸还没就绪时静候下一次 <Map>。"""
        if self.chat_cv.winfo_height() <= 1:
            return
        self.render_messages()

    def real_font(self, spec):
        """带缓存的 Font 获取：同一 spec 只创建一次（此前每次新建导致严重卡顿）
        v1.9.9.42：spec 本身已是命名 Font 对象时直接返回（ measure 走缓存）"""
        if isinstance(spec, tkfont.Font):
            return spec
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

    # v1.9.9.32：聊天区滚动条。消息是按像素 offset 手画的（不走 yview），
    # 所以滚动条两端都自己接：set() 由渲染后回调同步滑块位置，
    # command 把滑块比例换算回 offset 再重画。
    def _chat_sb_sync(self, first=None, last=None):
        """把当前聊天滚动位置同步到右侧滑块（v1.9.9.38，常规滚动条语义）。

        旧版两个致命伤：
        · 永远 set(f, 1.0)——滑块底边粘死在底端、长度随 f 缩到 0；
        · 这个函数挂在 yscrollcommand 上，但聊天画布根本没设
          scrollregion，yview 永远不变 → 函数从未被调用 → 滑块永远
          停在出厂的「铺满」态（铺满=无可滚动，拖了也没反应）。
        现在渲染后手动调用；滑块长度 = 可视高/内容总高，位置 = 已滚比例。"""
        lo = getattr(self, "_chat_min", 0)
        total = getattr(self, "_chat_total", 0)
        if lo >= 0 or total <= 0:        # 内容没超出可视区：滑块铺满
            try:
                self.chat_sb.set(0.0, 1.0)
            except tk.TclError:
                pass
            return
        h = max(self.chat_cv.winfo_height(), 40)
        top = -getattr(self, "_chat_offset", lo)     # 已滚过的内容像素
        f = max(0.0, min(1.0, top / float(total)))
        l = max(f, min(1.0, (top + h) / float(total)))
        try:
            self.chat_sb.set(f, l)
        except tk.TclError:
            pass

    def _chat_scroll(self, *args):
        """聊天区滚动条回调。三种调用形式都要接住（v1.9.9.37）：
        · 拖动滑块 / yscrollcommand：("0.35", "0.52") 两参
        · 点上下箭头 / 滚轮在滚动条上：("scroll", n, "units") 或
          ("scroll", n, "pages")——旧代码只接两参，这类调用直接
          TypeError 崩掉，表现为「滚动条上滚轮没反应」
        · ("moveto", f)：程序化定位"""
        lo = getattr(self, "_chat_min", 0)
        total = getattr(self, "_chat_total", 0)
        if lo >= 0 or total <= 0:
            return
        # 拖滑块语义（常规滚动条）：first = 滑块顶端占内容的比例，
        # 换算回 offset = -first*total，钳在可滚范围 [lo, 4]
        def _goto(f):
            f = max(0.0, min(1.0, float(f)))
            self.render_messages(offset=max(lo, min(4, -f * total)))
        if args and args[0] == "moveto":        # 程序化定位（先判，防被两参分支截走）
            _goto(args[1])
        elif len(args) == 2:                    # 拖动滑块 (first, last)
            _goto(args[0])
        elif args and args[0] == "scroll":
            try:
                n = int(args[1])
            except (TypeError, ValueError):
                return
            h = max(self.chat_cv.winfo_height(), 40)
            unit = max(10, h // 10) if (len(args) < 3 or args[2] == "units") else h
            cur = getattr(self, "_chat_offset", 0)
            self.render_messages(offset=max(lo, min(4, cur - n * unit)))

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
        # v1.9.9.45：先处理、成功再清空。旧版一进来就 delete，解析链路
        # 抛异常时用户刚打的话从输入框消失（内容还在聊天记录里，但观感
        # 就是「白打了」）。失败时把原文回填，并记日志。
        self._retire_enter_hint()      # 第一次成功发送后撤掉「回车发送」
        if self.list_mode == "note":
            try:
                self.add_note(text)
            except Exception as exc:
                self.diag("[EXC] add_note %r" % (exc,))
                return "break"
            self.entry.delete(0, "end")
            return "break"
        try:
            self.handle_user_text(text)
        except Exception as exc:
            self.diag("[EXC] handle_user_text %r" % (exc,))
            self.entry.delete(0, "end")
            self.entry.insert(0, text)
            self.entry.config(fg=C.TEXT)
            self._compose_placeholder = False
            self.flash(tr("ui_error"))
            return "break"
        self.entry.delete(0, "end")
        return "break"

    def _retire_enter_hint(self):
        """「回车发送」提示只在第一次成功发送前显示，之后永久撤掉，
        输入框回归正常宽度（v1.9.9.21）。记进 store，下次启动不再出现。"""
        if getattr(self, "hint_lbl", None) is not None:
            try:
                self.hint_lbl.destroy()
            except Exception:
                pass
            self.hint_lbl = None
        if not getattr(self.store, "enter_hint_done", False):
            self.store.enter_hint_done = True
            self.store.save()

    # ---------------- 消息流
    def push(self, role, text, dual=None):
        msg = {"role": role, "text": text,
               "t": dt.datetime.now().strftime("%H:%M")}
        if dual:
            # 双语回放：切语言时历史消息跟着换（zh, en)
            msg["zh"], msg["en"] = dual[0], dual[1]
        self.store.messages.append(msg)
        self.store.messages = self.store.messages[-MSG_KEEP:]
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
    def _strip_action(t):
        """剥掉动作词再比相似度（v1.9.9.25）。

        「取消写周报」和「写周报」语义完全相反，但按子串判会被当成同一
        件事——用户看到「已有相似任务『取消写周报』」会懵。"""
        import re as _re
        return _re.sub(r"^(?:取消|删除|删掉|去掉|完成|做完|搞定|不要|撤销)"
                       r"(?:掉|了)?\s*", "", (t or "").strip())

    @staticmethod
    def _same_title(a, b):
        """标题是否指同一件事（去空格、小写后互为子串或相等）"""
        a = (a or "").replace(" ", "").lower()
        b = (b or "").replace(" ", "").lower()
        if not a or not b:
            return False
        if a == b or a in b or b in a:
            return True
        # v1.9.9.25：剥掉动作词后再比（「取消写周报」≠「写周报」）
        a2 = NoteApp._strip_action(a)
        b2 = NoteApp._strip_action(b)
        if a2 and b2 and a2 != a or b2 != b:
            return bool(a2 and b2 and (a2 == b2 or a2 in b2 or b2 in a2))
        return False

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
        # v1.9.9.19：与手动菜单档位对齐（95/70/45/20），保证颜色一致
        _lv_score = {"A": 95, "B": 70, "C": 45, "D": 20}.get(
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
                _m = tr("dl_expired_keep" if nxt.get("mode") == "dl"
                        else "dl_expired", t=_t)
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
            # v1.9.9.42：这里必须清 _pending_q！v1.9.9.40 给 mode dl 单独
            # 出问法时只清了 _pending_task，_pending_q 还留着 "expired"，
            # 于是「确认」之后的下一句话被当成确认问答吃掉（用户实测：
            # 确认完时间再说话，回复「已取消当前的操作」）。队列里若还有
            # 别的过期项，_next_ask 会重新挂上状态。
            self._pending_q = None
            # v1.9.9.3：确认把时间设上后，说「撤回」= 清掉这个时间
            # （与「刚设过时间就撤回」的全局语义一致）；注意不能记 hhmm=None，
            # 否则会被「没时间别装撤过」防谎话分支判成无可撤回
            self._push_undo({"kind": "deadline", "id": task["id"]})
            _nxt = _next_ask()
            _msg = tr("dl_expired_added", t=task["title"])
            return (_msg + "\n" + _nxt) if _nxt else _msg
        # 没听懂：再问一遍（mode==dl 用「时间设不设」的问法，v1.9.9.40）
        self._pending_expired = pe
        return tr("dl_expired_keep" if pe.get("mode") == "dl" else "dl_expired",
                  t=(pe.get("task") or task or {}).get("title", ""))


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
            # v1.9.9.25：口语也要认——真实用户看到「A.紧急 B.重要」会直接
            # 回「急」「着急」「普通」「随便」，原来只认「紧急/很急」，
            # 回「急」会掉进任务解析器（P0-2）
            self.PRI_RE = _re.compile(
                r"(?<![A-Za-z])([ABCD])(?![A-Za-z])|"
                r"紧急|很急|着急|好急|太急|急|非常重要|重要|一般|普通|"
                r"不急|不赶|随便|都行|无所谓|"
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

        # P0-3 / 建议3、4（v1.9.9.25）：追问状态的兜底出口。
        # 原来只要进了 pri 追问，用户回「确认 / 好 / 取消」或说一句
        # 明显的新任务都被吞掉，甚至把「确认」建成任务。现在：
        #  - 纯应答词（确认/好的/取消/算了）→ 直接结束追问，不建任务
        #  - 明显的新任务句（带动作动词且不是纯时间）→ 退出追问，按新任务处理
        _s = (text or "").strip()
        if re.fullmatch(r"(?:确认|确定|好的?|可以|行|嗯+|哦+|取消|算了|不用了?|"
                        r"ok|okay|yes|no)[\s。.！!～~]*", _s, re.I):
            self._pending_task = None
            if getattr(self, "_pending_q", None) == "pri":
                self._pending_q = None
            return True, tr("pri_skipped", t=task["title"]), ""

        need_pri = pt.get("need_pri")
        need_dl = pt.get("need_dl")
        m = self._pri_re().search(text)
        # v1.9.9.45：字母必须「整句就是选项」才算回答。
        # 旧版在整段文字里 search，于是「处理<b>&特殊符号」里的 b 被当成
        # 「B.重要」，只回一句「优先级：重要」，**整条新任务静默消失**
        # （QA 实测任务数 24→24）。现在：匹配到的字母之外还有正文 → 按新任务处理。
        if m and m.group(0).isascii() and m.group(0).isalpha():
            _rest = (text or "").replace(m.group(0), "", 1)
            _rest = re.sub(r"[\s，,。.．、:：;；!！?？]+", "", _rest)
            _has_time = bool(self._dl_time_re().search(text)) or bool(
                re.search(r"[\u4e00-\u9fff]", text or "") and
                (core.find_times(text or "") or []))
            if _rest and not _has_time:
                return False, None, text          # 交给新任务解析，不吞
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
        def _miss():
            """没认出是回答 → 计数；连续 2 次就放弃追问、按默认值收尾
            （v1.9.9.25，建议7/3：别让用户卡在问答里出不来）"""
            pt["miss"] = int(pt.get("miss") or 0) + 1
            if pt["miss"] >= 2:
                self._pending_task = None
                if getattr(self, "_pending_q", None) == "pri":
                    self._pending_q = None
                self.store.save()
                self._miss_reply = tr("pri_skipped", t=task["title"])
            return False, None, text
        # 完全不像回答（没字母没时间也没说没有）→ 当普通输入处理。
        # 引擎解析出的时间也算「时间」（「明天下午三点」旧正则接不住，v1.9.5），
        # 但必须防住「晚上八点提醒我做20个俯卧撑」这种带动作的整句新任务：
        # 只有「整句就是时间」才算回答，否则交给新任务解析。
        if (eng_time or time_m) and not m and not no_dl and not self._is_pure_time_reply(text):
            return _miss()
        if not m and not time_m and not no_dl and not eng_time:
            return _miss()
        # P1 问题5（v1.9.9.22）：「A 明天下午三点开会」——字母前缀会被当成
        # 优先级回答、后半句被吞掉。剥掉字母前缀后若剩下带**动作动词**的
        # 实义任务，整句按新任务处理。注意不能用 _taskish（「点」「周」
        # 这些时间词会误伤「B 晚上八点」这种合法回答）。
        # v1.9.9.26：尾缀字母同样处理——「历史作业D」在等待截止时间时
        # 会被当成回答吞掉（D 落在 pri_re 上，「历史作业」凭空消失）。
        if not i18n.is_en():
            _txt = (text or "").strip()
            _rest = re.sub(r"^[abcdABCD][\s，,。.．]*", "", _txt)
            _rest = re.sub(r"[\s，,。.．]*[abcdABCD]$", "", _rest)
            if _rest and _rest != _txt and re.search(
                    r"帮我|开会|写|交|发|买|去|做|完成|整理|复习|提醒|"
                    r"报告|作业|周报|邮件|电话|考试|上课|下班", _rest):
                return False, None, text

        replies = []
        if m and need_pri:
            letter = (m.group(1) or m.group(0)).strip().upper()
            table = {"A": "pri_a", "B": "pri_b", "C": "pri_c", "D": "pri_d"}
            if letter not in table:
                # v1.9.9.25：口语映射补全——「急/着急」也算 A，
                # 「普通」算 C，「随便/都行/无所谓」算 D（P0-2）
                low = m.group(0).lower()
                if ("urgent" in low or "紧急" in low or "急" in low) and "不急" not in low:
                    letter = "A"
                elif "important" in low or "重要" in low:
                    letter = "B"
                elif "normal" in low or "一般" in low or "普通" in low:
                    letter = "C"
                else:
                    letter = "D"
            # v1.9.9.19：分数与手动菜单（lv*25-5 = 95/70/45/20）对齐。
            # 原来 B=75、C=55 正好压在 priority_label 的档位线上（≥75 红、
            # ≥55 橙），对话里选「重要」显示红色、「一般」显示橙色，
            # 和手动调整的颜色对不上。
            scores = {"A": 95, "B": 70, "C": 45, "D": 20}
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
            # v1.9.9.40：回答里带「每天 / 每周X / 每月X号」→ 这是要把任务
            # 变成日常任务，不是一次性截止时间。旧代码把「每天早上八点」
            # 当成今天 8 点的截止时间，8 点一过就弹「已过截止日期」确认，
            # 用户明明想设的是天天重复的日常
            _rep = core.find_repeat(text or "")
            if _rep is not None:
                self._push_undo({"kind": "deadline", "id": task["id"],
                                 "prev": {"repeat": task.get("repeat"),
                                          "hhmm": task.get("hhmm"),
                                          "due_date": task.get("due_date"),
                                          "deadline_txt": task.get("deadline_txt")}})
                task["repeat"] = _rep
                task["hhmm"] = hhmm
                task["due_date"] = None
                task["deadline_txt"] = hhmm
                task["_from_raw"] = False
                task["reminded"] = False
                task["reminded_day"] = None
                self.store.save()
                self.refresh_tasks(scroll_top=True)
                replies.append(tr("dl_set_rep", t=task["title"],
                                  r=self._repeat_text(_rep), d=hhmm))
                need_dl = False
                return True, "\n".join(replies), ""
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
                # v1.9.9.40：任务已在待办里，问的是「时间设不设」不是「加不加入」
                return True, tr("dl_expired_keep", t=task["title"]), ""
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
                # v1.9.9.40：任务已在待办里，问的是「时间设不设」不是「加不加入」
                return True, tr("dl_expired_keep", t=task["title"]), ""
        elif no_dl and need_dl:
            replies.append(tr("dl_none", t=task["title"]))
            need_dl = False

        if not need_pri and not need_dl:
            # P2 问题10（v1.9.9.22）：问答链结束必须连 _pending_q 一起清，
            # 否则后续输入仍被当作回答处理（新任务被吞）
            self._pending_task = None
            if getattr(self, "_pending_q", None) == "pri":
                self._pending_q = None
                self._pending_remind = None
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
                 font=self.f_small, wraplength=190
                 ).pack(anchor="w", padx=10, pady=(6, 0))
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
                 font=self.f_small, wraplength=190).pack(anchor="w", padx=10)
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
                 font=self.f_small, wraplength=190).pack(anchor="w", padx=10)
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
            self._style_scrollbars()
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
        # v1.9.9.28：日常任务（每天/每周X）**不问优先级**。
        # 设计上日常任务本来就不参与优先级排序（列表里青色统一样式），
        # 再问一句「A.紧急 B.重要」既自相矛盾又徒增一次追问——
        # 用户建一条「每天背单词」要连答三次才能安心，成本太高。
        if self._is_daily(task):
            need_pri = False
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
                              "need_dl": need_dl, "miss": 0}
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
        # v1.9.9.23：英文用户同样适用（原来只认中文，英文任务句会被
        # 当成昵称或直接放行）
        if _r.search(r"\b(homework|report|meeting|email|mail|buy|finish|submit|"
                     r"send|call|prepare|clean|todo|task|tomorrow|today|"
                     r"tonight|monday|tuesday|wednesday|thursday|friday|"
                     r"saturday|sunday|minutes?|hours?|o'?clock)\b",
                     s or "", _r.I):
            return True
        return False

    def _onboarding(self, text):
        """首轮引导：自我介绍 → 问昵称 → 使用指南。返回回复文本；已完成则返回 None
        v1.9.9.5：顺序改为「先说明我是谁，再问怎么称呼，答完给一份简短使用指南」

        v1.9.9.20：新用户第一件事通常是记一条待办，不该被昵称卡住。
        - 昵称只问一次：没听懂就直接跳过，进入正常记任务（原来会无限
          重复「没太听懂，你希望我怎么称呼您呢」，用户输入「明天下午3点
          跟张总开会」永远出不去）；
        - 引导阶段输入像任务就直接建任务，昵称之后再补；
        - 明确的「跳过 / 先不设 / skip」直接放行。"""
        s = (text or "").strip()
        stage = int(getattr(self.store, "setup_stage", 0) or 0)
        # 还没问过 → 第一句先自我介绍，再问称呼
        # v1.9.9.25（P0-1）：如果第一句本身就是任务（「数学作业」），
        # 先把它记下来再问称呼，不能吞掉用户的正事
        if stage == 0:
            self.store.setup_stage = 1
            self.store.save()
            bot = getattr(self.store, "bot_name", "") or (
                "小宁" if not i18n.is_en() else "Note")
            intro = tr("intro_first", bot=bot) + "\n" + tr("ask_user_name")
            if s and self._taskish(s) and not core.extract_name(s):
                self._finish_onboarding(None)
                return tr("onboard_task_first") + "\n\n" + self.respond(s)
            return intro
        if stage != 1:
            return None

        # 用户可能一上来就问「你是谁」，先答，别硬拽着问名字
        if core.SELF_RE.search(s) and len(s) <= 30 and not core.extract_name(s):
            bot = getattr(self.store, "bot_name", "") or (
                "小宁" if not i18n.is_en() else "Note")
            return tr("intro_first", bot=bot) + "\n" + tr("ask_user_name")

        # v1.9.9.20：明确表示跳过 → 直接进入使用，昵称留空
        if re.fullmatch(r"\s*(跳过|先不设|不设|不用了?|算了|不想|以后再说|"
                        r"skip|later|no)\s*[。.！!～~]*\s*", s, re.I):
            self._finish_onboarding(None)
            return tr("onboard_skipped") + "\n" + tr("usage_guide")

        # v1.9.9.25（P0-1 另一半）：用户在回答优先级/时间时说的「B」「今晚9点」
        # 不能被当成昵称。单个字母、纯时间、纯数字都不像名字。
        if re.fullmatch(r"[A-DFa-df]|[\d\s:：点分半]+|今晚|明天|下午|晚上|上午|早上|中午",
                        s) or self._is_pure_time_reply(s):
            self._finish_onboarding(None)
            return tr("onboard_no_name_ok") + "\n" + tr("usage_guide")

        # P0 问题4（v1.9.9.22）：像派活儿的短句（交作业 / 帮我买牛奶 /
        # 明天3点开会）先按任务处理，绝不能被 extract_name 的短名兜底
        # 当成昵称收下
        # v1.9.9.25（P0-1）：先记账再问称呼——任务绝不丢
        if self._taskish(s):
            self._finish_onboarding(None)
            return tr("onboard_as_task") + "\n\n" + self.respond(s)

        nm = core.extract_name(s)
        if nm:
            self._finish_onboarding(nm)
            return tr("name_ok", name=nm) + "\n" + tr("usage_guide")

        # 没提取到昵称：如果这句话本身像一条任务，就按任务处理并跳过昵称
        if core.parse_tasks(s, fallback=False):
            self._finish_onboarding(None)
            return tr("onboard_as_task") + "\n\n" + self.respond(s)

        # 既不像名字也不像任务 → 只提醒一次，然后放行（不再死循环追问）
        self._finish_onboarding(None)
        return tr("onboard_no_name_ok") + "\n" + tr("usage_guide")

    def _finish_onboarding(self, name):
        """结束引导：记下昵称（可为空），stage 置 3"""
        if name:
            self.store.user_name = name
        self.store.setup_stage = 3
        if not self.store.bot_name:
            self.store.bot_name = "小宁" if not i18n.is_en() else "Note"
        self.store.save()

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
    _UNDO_INTENT = None

    def _undo_re(self):
        import re as _re
        if NoteApp._UNDO_RE is None:
            NoteApp._UNDO_RE = _re.compile(
                r"^\s*(撤回|撤销|退回|退回一下|撤消|重来|重输|重新输入|"
                r"改时间|改截止|时间错了|输错了|我打错了|打错了|"
                r"undo|revert)\s*[。.！!～~]*\s*$", _re.I)
        return NoteApp._UNDO_RE

    def _undo_intent(self):
        """宽松的「撤回意图」识别（v1.9.9.22）。

        覆盖：撤回一下 / 撤销刚才的 / 撤回上一条 / 撤回内容 / 说错了 /
        打错了 / 刚才不算 / 重新记 等。规则：去掉标点后以撤回类词开头
        且整体很短，或整句就是口语认错说法。代价：「撤回邮件给客户」
        这类以撤回开头的真实任务会被当成指令（权衡后接受，见 QA 报告）。"""
        import re as _re
        if NoteApp._UNDO_INTENT is None:
            NoteApp._UNDO_INTENT = _re.compile(
                r"^[\s，,。.！!？?~～]*(?:帮我|请|麻烦)?\s*"
                r"(?:撤回|撤销|撤掉|撤消|退回|undo|revert)"
                r"[\s，,。.！!？?~～]*(?:一下|一下下|了|吧|呀|哈|"
                r"刚才的?|刚刚的?|上一条?|上一?个|那一条?|那个|这个|"
                r"内容|任务|待办|事项|操作|记录|时间|截止|提醒|优先级|"
                r"刚才那个操作|刚才那步)?"
                r"[\s，,。.！!？?~～]*(?:吧|了|呀)?[\s。.！!～~]*$"
                r"|^[\s，,。.！!？?~～]*"
                r"(?:说错了|我说错了|打错了|我打错了|输错了|我输错了|"
                r"刚才不算|不算了|不算|重新记|重记|重新输入|重输|重来|"
                r"刚才那(条|个|句)(不算|不要|删掉)|undo that|mistake)"
                r"[\s。.！!～~]*$", _re.I)
        return NoteApp._UNDO_INTENT

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
        """识别撤回指令；返回 "deadline" / "task" / "remind_at" / "cancel" / None

        v1.9.9 修复：以前光秃秃一句「撤回」一律当成「撤截止时间」，
        于是对一条本来就没有截止时间的任务说「撤回」，会得到
        「已经把【买牛奶】的截止时间撤掉了」这种凭空捏造的回复，
        任务本身也没被撤掉。现在改为：明确说了「撤回任务」才撤任务；
        只说「撤回」时看上一次操作是什么（撤回栈顶）——
        上一次是新建任务就撤整个任务，否则才按撤时间处理。

        v1.9.9.22：正在等用户确认/回答（_pending_q 非空）时，「撤回」
        优先**取消当前流程**，绝不去删原来的任务（原来在重复任务确认
        中说撤回会把老任务删掉）。撤流程不消耗撤回栈。"""
        import re as _re
        t = (text or "").strip()
        if not t or len(t) > 20:
            return None
        # ① 待确认流程中：撤回意图的处理分两种（v1.9.9.24 实测调整）：
        #    - _pending_q == "pri"：这是**刚建的这条新任务**在等配置，
        #      用户说「撤回一下 / 说错了」就是「这条别记了」——连任务
        #      一起撤掉（原实现只取消流程、任务留着，实测很困惑）；
        #    - dup/expired/meridiem/remind：涉及的是老任务或尚未入库的
        #      任务，一律只取消当前问答，绝不动已有数据。
        if getattr(self, "_pending_q", None) and self._undo_intent().match(t):
            if self._pending_q == "pri":
                return "task"
            return "cancel"
        # ② 「撤回任务」「撤回待办」「撤回上一条」= 撤整个任务
        # v1.9.9.3：以前只认「任务」，说「撤回待办」会漏进解析器变成一条
        # 叫「撤回待办」的新任务
        if _re.search(r"(撤回|撤销|撤掉|退回|删掉|去掉)\s*(这个|那个|刚才|上一|这|最)?(条|个|的|一)?\s*(任务|待办|事项|条目)", t, _re.I):
            return "task"
        # ③ 明确点名「时间」的撤回（撤一下时间 / 把时间撤了）
        explicit_time = bool(self._undo_pat().match(t)) or bool(
            _re.search(r"时间|截止|点钟|点儿", t))
        if explicit_time and self._undo_pat().match(t):
            return "deadline"
        # ④ 撤回意图（宽匹配）：有记录按栈顶类型撤，没记录给交代
        if self._undo_intent().match(t) or self._undo_re().match(t):
            rec = getattr(self, "_undo_last", None)
            if not rec:
                return None
            # v1.9.9.22：栈顶是 UI 操作（勾选/优先级/删除/改名）→ 撤回该操作
            if rec.get("kind") in ("done", "priority", "delete", "rename",
                                   "note_del"):
                return rec["kind"]
            if rec.get("kind") == "remind_at" and not explicit_time:
                return "remind_at"      # v1.9.9.9：撤回刚才设的提醒时刻
            if rec.get("kind") == "task" and not explicit_time:
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
                        and not explicit_time:
                    return None
            return "deadline"
        return None

    def _push_undo(self, rec):
        """记一条可撤回的操作（保留最近 3 步，v1.9.9.22 从 1 步扩到 3 步）"""
        stack = getattr(self, "_undo_stack", None)
        if stack is None:
            stack = self._undo_stack = []
        stack.append(rec)
        if len(stack) > 3:
            stack.pop(0)
        self._undo_last = rec

    def _pop_undo(self):
        """弹出栈顶记录；测试直接塞 _undo_last 时也能工作"""
        stack = getattr(self, "_undo_stack", None) or []
        if stack:
            rec = stack.pop()
        else:
            rec = getattr(self, "_undo_last", None)
        self._undo_last = stack[-1] if stack else None
        return rec

    def _do_undo(self, kind):
        """执行撤回。kind=deadline 撤时间并重新追问；kind=task 撤掉整个任务；
        kind=cancel 只取消当前待确认流程，不动撤回栈（v1.9.9.22）"""
        # 先把所有待答状态清干净：撤回是一次「重新开始」
        self._pending_q = None
        self._pending_task = None
        self._pending_expired = None
        self._pending_remind = None
        self._pending_dup = None
        self._pending_meridiem = None
        self._remind_asked_for = None
        if kind == "cancel":
            return tr("undo_cancelled")
        rec = self._pop_undo()
        task = None
        if rec:
            for t in self.store.tasks:
                if t["id"] == rec.get("id"):
                    task = t
                    break
        # v1.9.9.22：UI 操作类撤回（勾选 / 优先级 / 删除 / 改名）
        # v1.9.9.45：加 note_del（便签删除可撤回）
        if kind in ("done", "priority", "delete", "rename", "note_del"):
            return self._undo_ui_op(kind, rec)
        if kind == "task":
            if task is None:
                return tr("undo_none")
            self.store.tasks.remove(task)
            # v1.9.9.3：撤回 = 撤销这次录入，历史里的当日记录一并清掉
            # v1.9.9.22：只清**今天**的历史——昨天归档的是当时已经成立的
            # 记录，撤回今天的录入不应该把昨天的也抹掉（同名任务跨天）
            _t = task.get("title", "")
            if _t:
                # v1.9.9.45：历史行现在带 tid，要同时按 id 清——只按标题
                # 已经匹配不到新写入的行了
                self.store.purge_history({_t}, only_today=True,
                                         tids={task.get("id")})
            self.store.save()
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
            self._remind_asked_for = task["id"]
            self._pending_remind = task["id"]
            self._pending_q = "remind"
            return tr("undo_remind_done") + "\n" + self._ask_remind_text(task)
        # kind == deadline
        if task is None:
            return tr("undo_none")
        # v1.9.9.40：「改成每天/每周X」这类时间修改的撤回——恢复整个
        # prev 快照（含原 repeat/due_date），单纯的清时间不适用
        if rec and rec.get("prev") is not None and "repeat" in rec["prev"]:
            prev = rec["prev"]
            task["repeat"] = prev.get("repeat")
            task["hhmm"] = prev.get("hhmm")
            task["due_date"] = prev.get("due_date")
            task["deadline_txt"] = prev.get("deadline_txt")
            task.pop("remind_before", None)
            self.store.save()
            self.refresh_tasks(scroll_top=True)
            self._remind_asked_for = None
            return tr("undo_dl_done", t=task["title"])
        # v1.9.9：任务本来就没有截止时间，就不要谎称「撤掉了截止时间」
        if not (task.get("hhmm") or task.get("due_date")):
            return tr("undo_no_dl", t=task["title"])
        task["hhmm"] = None
        task["due_date"] = None
        task["deadline_txt"] = None
        task.pop("remind_before", None)
        self.store.save()
        self.refresh_tasks(scroll_top=True)
        # v1.9.9.22 问题6：清掉「已问过提醒」的标记——否则重新设时间时
        # 不再追问「提前多久提醒」
        self._remind_asked_for = None
        # 重新走一遍截止时间追问，用户直接说新时间即可
        self._pending_task = {"id": task["id"], "need_pri": False, "need_dl": True}
        self._pending_q = "pri"
        return tr("undo_dl_done", t=task["title"])

    def _undo_ui_op(self, kind, rec):
        """撤回 UI 操作（勾选/优先级/删除/改名），v1.9.9.22"""
        if not rec:
            return tr("undo_none")
        label = rec.get("label") or "上一步操作"
        if kind == "delete":
            old = rec.get("task")
            if not old:
                return tr("undo_none")
            # 还原到原来的位置（没有就放最前面）
            idx = rec.get("index")
            if isinstance(idx, int) and 0 <= idx <= len(self.store.tasks):
                self.store.tasks.insert(idx, old)
            else:
                self.store.tasks.insert(0, old)
            # v1.9.9.45：删除时只清了今天的历史行，撤回要把今天这条补回来
            try:
                self.store.sync_history()
            except Exception:
                pass
            self.store.save()
            self.refresh_tasks(scroll_top=True)
            return tr("undo_generic_done", label=label)
        if kind == "note_del":
            note = rec.get("note")
            if not note:
                return tr("undo_none")
            notes = list(getattr(self.store, "notes", []) or [])
            idx = rec.get("index")
            if isinstance(idx, int) and 0 <= idx <= len(notes):
                notes.insert(idx, note)
            else:
                notes.append(note)
            self.store.notes = notes
            self.store.save()
            self.refresh_notes()
            return tr("undo_generic_done", label=label)
        task = None
        for t in self.store.tasks:
            if t.get("id") == rec.get("id"):
                task = t
                break
        if task is None:
            return tr("undo_none")
        if kind == "done":
            task["done"] = bool(rec.get("prev"))
            task["done_at"] = rec.get("prev_at") or ""
        elif kind == "priority":
            task["score"] = rec.get("prev_score")
            task["manual"] = bool(rec.get("prev_manual"))
        elif kind == "rename":
            task["title"] = rec.get("prev") or task["title"]
        self.store.save()
        self.refresh_tasks(scroll_top=True)
        return tr("undo_generic_done", label=label)

    # ---------------- 元指令表（v1.9.9.29 重构）
    # 这 5 类输入不需要理解语义，只是识别固定句式，且必须早于任务解析
    # （否则「撤回」会被建成任务）。原来是一串平铺 if，谁在前面谁优先；
    # 现在优先级写进 _intercept 的表里，改顺序不用挪代码。
    def _try_self_intro(self, text):
        """「你是谁 / 介绍你自己」"""
        if core.SELF_RE.search(text or "") and len((text or "").strip()) <= 30:
            return self._intro_self()
        return None

    def _try_bot_name(self, text):
        """给助手起名：「我希望你叫小宁同志」「你就叫小宁吧」"""
        m_bn = _BOT_NAME_RE.search(text or "")
        if not m_bn:
            return None
        nm = (m_bn.group(1) or "").strip().strip("\"'“”‘’「」")
        if not nm:
            return None
        nm = re.split(r"[，,。.!！?？；;\s]", nm)[0]
        nm = re.sub(r"(就行|就好|好了|便好|得了|吧|哦|呀|啊|啦|哈)$", "", nm) or nm
        self.store.bot_name = nm
        self.store.save()
        return tr("bot_name_ok", bot=nm)

    def _try_user_name(self, text):
        """改自己的昵称（v1.9.9.23）：跳过取名后也能随时补设"""
        m_un = _USER_NAME_RE.match((text or "").strip())
        if not m_un:
            return None
        nm = (m_un.group(1) or "").strip().strip("\"'“”‘’「」")
        if not nm or nm in ("我", "自己", "什么", "啥", "谁"):
            return None
        old = getattr(self.store, "user_name", "") or ""
        self.store.user_name = nm
        self.store.save()
        if old and old != nm:
            return tr("user_name_changed", old=old, name=nm)
        return tr("name_ok", name=nm)

    def _try_undo(self, text):
        """撤回：必须早于所有追问路由，否则会被当成上一个问题的回答"""
        kind = self._match_undo(text)
        if kind:
            return self._do_undo(kind)
        if self._undo_re().match((text or "").strip()):
            return tr("undo_none")
        return None

    def _try_tray_pref(self, text):
        """v1.9.9.34：「关闭/打开托盘气泡提示」——后台气泡每次最小化都弹，
        用户嫌吵，要一个能关掉的开关"""
        t = (text or "").strip()
        if len(t) > 20:
            return None
        if re.search(r"(关闭|别再|不要|取消|关掉)(弹)?(托盘)?(气泡|通知|提示)", t):
            self.store.tray_notify_off = True
            self.store.save()
            return tr("tray_notify_off")
        if re.search(r"(打开|开启|恢复|要)(弹)?(托盘)?(气泡|通知|提示)", t):
            self.store.tray_notify_off = False
            self.store.tray_notify_shown = False
            self.store.save()
            return tr("tray_notify_on")
        return None

    def _try_note(self, text):
        """便签指令：「记便签：xxx」→ 存进便签页"""
        m_note = re.match(r"^(?:记个?便签|便签|帮我记个?便签)[：:，,\s]\s*(.+)$",
                          (text or "").strip())
        if m_note and m_note.group(1).strip():
            self.add_note(m_note.group(1).strip()[:200])
            return _SILENT
        return None

    def _intercept(self, text):
        """元指令拦截（有序表）。返回 (是否已处理, 回复)。

        顺序即优先级，与代码位置无关：
          引导 → 自我介绍 → 助手名 → 用户名 → 撤回 → 便签
        「撤回」排在改名之后是有意的：改名句式很窄（必须以「你叫我/我叫」
        开头），不会误吞「撤回」；而「撤回」泛用，放太后会抢走别的句式。
        """
        onboarding = self._onboarding(text)
        if onboarding is not None:
            return True, onboarding
        for fn in (self._try_self_intro, self._try_bot_name,
                   self._try_user_name, self._try_tray_pref,
                   self._try_undo, self._try_note):
            reply = fn(text)
            if reply is not None:
                return True, (None if reply is _SILENT else reply)
        return False, None

    # ---------------- 待答状态（v1.9.9.29 重构）
    # 原来散在 respond 里（_pending_q/_pending_remind/_pending_task/
    # _pending_expired/_pending_dup/_pending_meridiem），每个都是
    # 「先判断再处理」的平铺 if，谁写前面谁赢。统一成处理器后，
    # 返回 (handled, reply)；handled=False = 这不是回答 → 放行给任务解析
    # （关键：绝不能把「晚上8点前做好新闻稿」这种新任务句吞掉）。
    def _answer_remind(self, text):
        """回答「提前多久提醒」"""
        pr = getattr(self, "_pending_remind", None)
        if not pr:
            return False, None
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
            # P2 问题10（v1.9.9.22）：提醒问答已得到回答，追问状态
            # 必须清掉——否则紧跟着的「撤回」会被当成取消流程
            self._pending_q = None
            self._pending_remind = None
            tok = (m_r.group(1) or "").strip().upper() if m_r else ""
            if tok == "F" and at_min is None:
                return True, tr("ask_remind_at")     # 只想指定时刻，等下一句
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
                return True, tr("remind_at", t=task["title"],
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
                # v1.9.9.28：敲了选项表里没有的字母（这里问的是 E/F，
                # 用户还按上一问的习惯回了个 A）→ 当作跳过，不设提醒。
                # 原来会掉进最后的 else 静默设成「提前 5 分钟」，
                # 用户完全不知道给自己设了个提醒。
                if tok and tok not in lmap and tok != "F":
                    task["remind_before"] = 0
                    self.store.save()
                    return True, tr("remind_off", t=task["title"])
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
                    return True, tr("remind_off", t=task["title"])
                task["remind_before"] = mins
                task["remind_at"] = None
                key = {5: "remind_5", 15: "remind_15",
                       30: "remind_30", 60: "remind_60"}[mins]
                reply = tr("remind_set", t=task["title"], d=tr(key))
            self.store.save()
            return True, reply
        self._pending_remind = None    # 不是回答，按普通输入处理
        return False, None

    # ---------------- 查询类意图（v1.9.9.29 重构）
    # 三个只读意图，必须早于任务解析（否则「列表」会被建成任务）。
    # 原来写成三段平铺 if，现在集中到 _handle_query 按顺序试。
    def _q_list(self, text, parsed, pz):
        """「列表 / 我的任务 / 今天有什么任务」→ 播报未完成 Top5"""
        if not self._is_list_query(text):
            return None
        return self._list_report()

    def _q_done_today(self, text, parsed, pz):
        """「今天做了什么」→ 播报今天勾掉的任务（v1.9.9.28）"""
        if not re.fullmatch(r"[\s，,]*(?:今天|今日)(?:都)?(?:做了|干了|完成了|做完|搞定了?)"
                            r"(?:些)?(?:什么|啥|哪些)(?:事|活|活儿|任务)?(?:呢|吗|？|\?)?"
                            r"[\s。.！!～~]*", text or ""):
            return None
        rows = [r for r in (self.store.history.get(self.store._today()) or [])
                if r.get("done")]
        if not rows:
            return tr("done_today_none")
        lines = "\n".join("  · %s%s" % (r.get("title") or "",
                                        (" " + r["at"]) if r.get("at") else "")
                          for r in rows[:8])
        return tr("done_today_report", n=len(rows), lines=lines)

    def _q_progress(self, text, parsed, pz):
        """「我还有几件 / 完成多少」→ 剩余数量 + 最要紧的一件"""
        if not (pz.QUERY_RE.search(text) and not parsed):
            return None
        left = [x for x in self.store.tasks if not x.get("done")]
        if not left:
            return tr("left_none")
        top = sorted(left, key=lambda x: -x.get("score", 0))[0]
        return tr("left_some", n=len(left), title=top["title"])

    def _handle_query(self, text, parsed, pz):
        """按顺序试各查询意图，返回 (handled, reply)"""
        for fn in (self._q_list, self._q_done_today, self._q_progress):
            r = fn(text, parsed, pz)
            if r is not None:
                return True, r
        return False, None

    # ---------------- 勾选意图（v1.9.9.29 重构）
    #
    # 这一段是「软意图」的典型：口语里「完成X / X完成了 / X打卡了 / 做了X」
    # 都可能是完成语，也都可能是新任务（「买牛奶」曾被看成「买」+完成语）。
    # 处理原则只有一条：**先确认能匹配到已有任务，才认定是完成**；
    # 匹配不上就放行给任务解析。
    def _is_done_intent(self, text, pz):
        """(是否是完成语, 是否是软完成语)

        硬完成语：「完成X / X做完了」——带 DONE_RE 里的完成动词，
                  认错了至少会回一句「没找到」，不会静默建任务。
        软完成语：「X打卡了 / 做了X」——动词太泛，必须额外校验。"""
        if len(text or "") > 24:
            return False, False
        # v1.9.9.31：「完成数学作业，每天晚上八点」里的「完成」是**建任务**的
        # 动词不是打卡——句子里带重复信号（每天/每周/工作日）时
        # 绝不按完成语处理，交给建任务流程
        if re.search(r"每[天周月日]|工作日|礼拜[一二三四五六日天]|天天", text or ""):
            return False, False
        soft = bool(re.search(r"(打个?卡|打卡|签到|签个到)", text or "")) or \
            bool(re.match(r"^[\s，,]*(?:我)?(?:今天|刚刚|已经)?\s*"
                          r"(?:做|弄|搞|看|读|背|学|练|写|听|跑)(?:了|过|完)", text or ""))
        hard = bool(pz.DONE_RE.search(text or ""))
        return (hard or soft), (soft and not hard)

    def _finish_task(self, task):
        """把一个任务标记完成（日常任务走打卡），返回回复"""
        if self._is_daily(task):
            # v1.9.9.43：不在今天到期的日常不打卡（与勾选框同一条规则）
            if not self._daily_due_today(task) and not task.get("done"):
                return tr("daily_not_today", t=task["title"],
                          r=self._repeat_text(task.get("repeat")))
            # 日常任务：勾的是「今天打卡」，不是「这件事完了」
            self._daily_toggle(task)
            self.store.save()
            self.refresh_tasks()
            return tr("daily_checked", t=task["title"])
        task["done"] = True
        task["done_at"] = dt.datetime.now().strftime("%H:%M")
        self.store.save()
        self.store.sync_history()
        self.refresh_tasks()
        return self._praise(tr("done_ok", title=task["title"]))

    def _handle_complete(self, text, parsed_now, pz):
        """勾选意图。v1.9.9.32：对话不再打勾（用户实测反馈「很乱」）——
        打卡/完成一律在清单里手动打勾。

        现在只做两件事：
        1. 纯打卡话（「背单词打卡了」「签到」）→ 回一句提示，**不建任务**
           （原来会建出叫「背单词打卡」的临时任务）；
        2. 「完成X」这类动词句 → 放行 (False)，交给建任务流程——
           用户的心智模型里「完成数学作业」就是一条新任务。
        返回 (handled, reply)"""
        if len(text or "") > 24:
            return False, None
        # 序号勾选（「完成第一个」）仍保留：这是明确指向已有任务的操作
        if re.search(r"第\s*(?:[0-9]+|[一二三四五六七八九十]{1,3})\s*[个条项件]?",
                     text or "") and re.search(
                     r"(完成|做完|勾掉|勾了|办好)", text or ""):
            idx_title = self._done_by_index(text)
            if idx_title is not None:
                return True, idx_title
        if re.search(r"(打个?卡|打卡|签到|签个到)", text or ""):
            return True, tr("checkin_hint")
        return False, None

    # ---------------- 其余任务操作（v1.9.9.29 重构）
    # 改时间 / 删除 / 寒暄。原来是一串平铺 if，现在拆成三个方法，
    # 由 _handle_task_ops 按顺序试——顺序即优先级，与代码位置无关。
    def _apply_new_time(self, task, when):
        """v1.9.9.35：把「新时间」写进任务（对话改时间和右键菜单共用）。
        成功返回新的 deadline_txt；听不懂返回 None

        v1.9.9.40：输入里带「每天 / 每周X / 每月X号」→ 顺带把任务改成
        日常任务（旧代码只提取钟点、「每天」被静默丢弃，用户明明说了
        要改成日常却没生效）。"""
        _t = (core.find_times(when) or [None])[0]
        if not _t:
            return None
        rep = core.find_repeat(when)         # v1.9.9.40
        _d = core.find_deadline_date(when)
        # v1.9.9.40：快照必须记在改 hhmm 之前，否则撤回恢复的是新值
        _prev = {"repeat": task.get("repeat"), "hhmm": task.get("hhmm"),
                 "due_date": task.get("due_date"),
                 "deadline_txt": task.get("deadline_txt")}
        task["hhmm"] = _t[0]
        if rep is not None:
            self._push_undo({"kind": "deadline", "id": task["id"],
                             "prev": _prev})
            task["repeat"] = rep
            task["due_date"] = None          # 日常任务没有一次性截止日期
            task["deadline_txt"] = _t[0]
            task["_from_raw"] = False
            task["reminded"] = False
            task["reminded_day"] = None
            self.store.save()
            self.refresh_tasks()
            return "%s %s" % (self._repeat_text(rep), _t[0])
        task["due_date"] = (_d[0].isoformat() if _d and _d[0]
                            else task.get("due_date"))
        task["deadline_txt"] = (task["due_date"] and
                                "%s %s" % (
                                    "%d月%d日" % (int(task["due_date"][5:7]),
                                                 int(task["due_date"][8:10])),
                                    _t[0])) or _t[0]
        task["_from_raw"] = False
        task["reminded"] = False        # 时间变了，旧提醒作废
        task["reminded_day"] = None
        self._push_undo({"kind": "deadline", "id": task["id"]})
        self.store.save()
        self.refresh_tasks()
        return task["deadline_txt"]

    def _op_reschedule(self, text, parsed, pz):
        """改时间：「把开会改到下午4点」「开会改成明天3点」"""
        m_adj = re.match(r"^[\s，,]*(?:帮我|请)?(?:把|将)?\s*(.+?)\s*"
                         r"(?:改到|改成|改为|挪到|调整到|调到)\s*(.+)$",
                         (text or "").strip())
        if not m_adj:
            return False, None
        name, when = m_adj.group(1).strip(), m_adj.group(2).strip()
        for task in self.store.tasks:
            if not self._match(name, task["title"]):
                continue
            dl = self._apply_new_time(task, when)
            if dl is None:
                break
            return True, tr("dl_set", t=task["title"], d=dl)
        return False, None

    def _op_delete(self, text, parsed, pz):
        """删除：「取消写周报」「删除健身」「删除第二个任务」

        删不掉时明确回「没找到」，绝不落到新建任务分支。"""
        t = (text or "").strip()
        _cancel = re.match(r"^[\s，,]*(?:帮我|请)?(?:取消|不要了?|不做了?|别做|"
                           r"删掉|删了|删除|删|去掉|移除|干掉)"
                           r"(?:掉|了)?\s*(.+?)(?:了|吧|啦)?\s*[。.！!～~]*$", t)
        if _cancel and len(t) <= 20 and not re.search(
                r"第\s*(?:[0-9]+|[一二三四五六七八九十]{1,3})\s*[个条项件]", t):
            nm = _cancel.group(1).strip()
            if nm and nm not in ("任务", "待办"):
                for i, task in enumerate(list(self.store.tasks)):
                    if self._match(nm, task["title"]):
                        self._push_undo({"kind": "delete", "id": task["id"],
                                         "task": dict(task), "index": i,
                                         "label": "删除【%s】" % task["title"]})
                        self.store.tasks.pop(i)
                        self.store.save()
                        self.refresh_tasks()
                        return True, tr("deleted", title=task["title"])
                # 删不掉也要有回应，别掉进「新建任务」
                if re.match(r"^[\s，,]*(?:删掉|删了|删除|删|去掉|移除|干掉)", t):
                    return True, tr("done_notfound", title=nm)

        _del_idx = re.match(r"^[\s，,]*(?:删|删除|去掉|删掉)\s*第\s*"
                            r"([0-9]+|[一二三四五六七八九十]{1,3})\s*[个条项件]?"
                            r"(?:任务|待办|的)?\s*$", t)
        if _del_idx:
            raw = _del_idx.group(1)
            try:
                idx = int(raw)
            except ValueError:
                idx = core._num(raw)
            left = [x for x in self.sorted_tasks() if not x[1].get("done")]
            if idx and 1 <= int(idx) <= len(left):
                task = left[int(idx) - 1][1]
                i = self.store.tasks.index(task)
                self._push_undo({"kind": "delete", "id": task["id"],
                                 "task": dict(task), "index": i,
                                 "label": "删除【%s】" % task["title"]})
                self.store.tasks.pop(i)
                self.store.save()
                self.refresh_tasks()
                return True, tr("deleted", title=task["title"])
            return True, tr("done_notfound", title="第%s个任务" % raw)

        if pz.DEL_RE.search(t) and parsed:
            target = parsed[0][0]
            for i, task in enumerate(list(self.store.tasks)):
                if self._match(target, task["title"]):
                    self.store.tasks.pop(i)
                    self.store.save()
                    return True, tr("deleted", title=task["title"])
        return False, None

    def _op_greet(self, text, parsed, pz):
        """寒暄 / 道谢（只认短句，长句里带寒暄词仍按任务解析）"""
        if len(text or "") > 16:
            return False, None
        if pz.GREET_RE.search(text or ""):
            return True, self.greeting()
        if pz.THANKS_RE.search(text or ""):
            return True, i18n.pick(random, "thanks")
        return False, None

    def _handle_task_ops(self, text, parsed_now, pz):
        for fn in (self._op_reschedule, self._op_delete, self._op_greet):
            hit, rep = fn(text, parsed_now, pz)
            if hit:
                return True, rep
        return False, None

    # ---------------- 待答状态总入口（v1.9.9.29 重构）
    #
    # 用户上一轮被问了一个问题，这一轮的输入可能是在回答它，也可能是
    # 一件新事情。区别就在于处理器能不能「认领」这句输入：
    #   handled=True  → 是回答，直接用 reply
    #   handled=False → 不是回答，放行给任务解析
    #
    # 顺序即优先级（原来靠代码位置）：
    #   meridiem（上下午）→ expired（过期确认）→ remind（提前多久）
    #   → pri（优先级/截止）→ dup（重名确认）
    def _ans_meridiem(self, text):
        if getattr(self, "_pending_q", None) != "meridiem":
            return False, None
        if not getattr(self, "_pending_meridiem", None):
            return False, None
        ans = self._resolve_meridiem(text)
        return (True, ans) if ans is not None else (False, None)

    def _ans_expired(self, text):
        if not getattr(self, "_pending_expired", None):
            return False, None
        ans = self._resolve_expired(text)
        return (True, ans) if ans is not None else (False, None)

    def _ans_dup(self, text):
        pd = getattr(self, "_pending_dup", None)
        if not pd:
            return False, None
        self._pending_dup = None
        if self._dup_ok_re().search(text):
            self._add_single(pd["title"], pd["hhmm"], pd["score"],
                             pd["dur"], override=pd["new_title"])
            try:
                ok = getattr(self, "_dup_pass", None)
                if ok is None:
                    ok = self._dup_pass = {}
                ok[pd["title"]] = time.time()
            except Exception:
                pass
            return True, tr("dup_added", title=pd["new_title"])
        # 其他回答：放弃确认，按普通输入继续解析
        return False, None

    def _handle_pending(self, text):
        """返回 (handled, reply)。会顺带改写 _turn_text（pri 回答后剩下的部分）。"""
        # 上下午 / 过期确认：认领就直接回
        for fn in (self._ans_meridiem, self._ans_expired):
            hit, rep = fn(text)
            if hit:
                return True, rep

        # 提前多久提醒
        hit, rep = self._answer_remind(text)
        if hit:
            return True, rep

        # 优先级 / 截止时间：可能只消耗半句，剩下的仍要当新内容解析
        matched, reply, rest = self._apply_pri_answer(text)
        if matched:
            return True, reply
        # 连续答不上来已自动收尾 → 本次输入按新内容处理，
        # 把「已按默认优先级记着」的交代拼在前面
        _miss = getattr(self, "_miss_reply", None)
        if _miss:
            self._miss_reply = None
            _sub = self.respond(rest or text)
            return True, _miss + ("\n" + _sub if _sub else "")
        self._turn_rest = rest

        # 重名确认
        hit, rep = self._ans_dup(text)
        if hit:
            return True, rep
        return False, None

    def respond(self, text):
        """生成回复，并处理任务增删"""
        _hit, _rep = self._intercept(text)
        if _hit:
            return _rep

        # 待答状态：用户正在回答哪个问题？（meridiem/expired/remind/pri/dup）
        # 统一入口，顺序即优先级；handled=False 表示「这不是回答」→
        # 放行给下面的任务解析（不能把新任务句吞掉）
        self._turn_rest = None      # 本轮「答完问题后剩下的半句」，先清空
        _hit, _rep = self._handle_pending(text)
        if _hit:
            return _rep

        # 优先级追问可能只消耗半句（「答完优先级，后半句是新任务」）
        text = getattr(self, "_turn_rest", None) or text

        pz = self.p()
        # 英文模式下用户输入中文：解析仍用中文引擎（否则识别不出），
        # 回复文案全部走英文 i18n（tr），标题保留用户原文
        if i18n.is_en() and re.search(r"[\u4e00-\u9fff]", text or ""):
            pz = core
        parsed_now = pz.parse_tasks(text)

        # 查询类意图：列表 / 今日完成 / 进度（只读，必须早于任务解析）
        _hit, _rep = self._handle_query(text, parsed_now, pz)
        if _hit:
            return _rep

        # 勾选意图：完成 / 打卡
        _hit, _rep = self._handle_complete(text, parsed_now, pz)
        if _hit:
            return _rep

        # 其余意图：改时间 / 删除 / 寒暄
        _hit, _rep = self._handle_task_ops(text, parsed_now, pz)
        if _hit:
            return _rep

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
                # v1.9.9.19：与手动菜单档位对齐（见 _handle_pending 的同注释）
                scores = {"A": 95, "B": 70, "C": 45, "D": 20}
                score = scores[letter_m.group(1).upper()]
                title = _re_ad.sub(r"[，,、；;]?\s*[ABCD]\s*$", "", title).strip() or title
            similar = self._find_similar(title)
            # v1.9.9.45：批量录入同名任务时不再每条都拦。用户在 2 分钟内
            # 对同一个标题答过一次「就这个」，说明他就是要重复建，
            # 后面同名条目直接建（旧版 20 条只落 1 条，用户体验极差）。
            _batch_new = None
            if similar is not None:
                _ok = getattr(self, "_dup_pass", None) or {}
                _ts = _ok.get(title)
                if _ts and (time.time() - _ts) < 120:
                    # 刚确认过「就这个」→ 后面同名条目一律直接新建，
                    # 既不弹确认、也不并进已有那条
                    _n = sum(1 for t in self.store.tasks
                             if self._same_title(t["title"], title)) + 1
                    _batch_new = tr("dup_times_fmt", t=title, n=_n)
                    similar = None
            if similar is not None:
                # 有相似任务：不默默合并，先问用户（记次数区分）
                n = sum(1 for t in self.store.tasks
                        if self._same_title(t["title"], title)) + 1
                new_title = tr("dup_times_fmt", t=title, n=n)
                self._pending_dup = {"title": title, "new_title": new_title,
                                     "hhmm": hhmm, "score": score, "dur": dur}
                return tr("dup_ask", title=similar, new=new_title)
            if _batch_new:
                self._add_single(title, hhmm, score, dur, override=_batch_new)
                continue
            dup = None
            for task in self.store.tasks:
                # v1.9.9.32：日常任务即使今天已打卡（done=True）也算同名，
                # 再输入「完成数学作业」是更新它，不是再建一条
                if task["title"] == title and (not task.get("done")
                                               or task.get("repeat")):
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
            _rep = item[5] if len(item) > 5 else None
            # v1.9.9.27：重复任务（每天/每周X）的钟点是「每天几点做」，
            # 不是一次性截止时间——20 点设「每天早上八点背单词」不该被
            # 判为「已过截止日期」而拒绝录入
            if self._is_expired(hhmm, due_iso) and not (_rep and not due_iso):
                q_item = {
                    "task": {
                        "id": "%d%03d" % (int(time.time() * 1000),
                                          random.randint(0, 999)),
                        "title": title, "hhmm": hhmm, "dur": dur,
                        "score": score, "manual": False, "done": False,
                        "created": dt.datetime.now().strftime("%H:%M"),
                        "day": self.store._today(),
                        "repeat": item[5] if len(item) > 5 else None,
                        # v1.9.9.43：同下——周期任务不带一次性 due_date
                        "due_date": None if _rep else due_iso,
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
                # v1.9.9.43：周期任务不带一次性截止日期——「打扫卫生，每周四
                # 晚上九点」旧版会把下一个周四（11/12）一并写成 due_date，
                # 行首显示成「11/12 21:00」，看起来像临时任务，计数却不算
                # 今天（它是每周四的活）→「两个日常 0/1」。日常的下次到期
                # 由 repeat 自己表达，行首显示「每周四 21:00」。
                "due_date": None if (len(item) > 5 and item[5]) else
                            (item[6].isoformat() if (len(item) > 6 and item[6]) else None),
                "_from_raw": bool(hhmm),   # 时间来自原句，回复里不必复述
            })
            # 截止日期：原文里的 明天/后天 → 记下具体日期（日历用）
            # v1.9.9.43：周期任务不吃这套（它没有「某一天」的概念）
            if not self.store.tasks[-1].get("due_date") \
                    and not self.store.tasks[-1].get("repeat"):
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

    def list_groups(self):
        """列表分组（v1.9.9.27）：日常 → 临时。

        日常任务（带 repeat）：
          - 不参与优先级排序，只按时间排（08:00 在最上）；
          - **勾掉后仍留在日常区**（灰化 + 对勾），不像临时任务那样掉进
            底部已完成区——否则用户看不到「今天打卡了没」。
        临时任务：沿用原来的「未完成（按优先级）→ 已完成」。
        返回 [(组名, [(索引, 任务), ...]), ...]，空组省略。"""
        daily, tmp_undone, tmp_done = [], [], []
        for idx, t in enumerate(self.store.tasks):
            if self._is_daily(t):
                daily.append((idx, t))
            elif t.get("done"):
                tmp_done.append((idx, t))
            else:
                tmp_undone.append((idx, t))
        daily.sort(key=lambda x: (x[1].get("hhmm") or "99:99", x[0]))
        tmp_undone.sort(key=lambda x: (-x[1].get("score", 0),
                                       x[1].get("hhmm") or "99:99", x[0]))
        tmp_done.sort(key=lambda x: x[1].get("done_at", ""), reverse=True)
        groups = []
        if daily:
            groups.append(("daily", daily))
        if tmp_undone:
            groups.append(("tmp_undone", tmp_undone))
        if tmp_done:
            groups.append(("tmp_done", tmp_done))
        return groups

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
        # v1.9.9.45：不再截断到 200 字——粘一段长笔记只剩前 200 字是
        # 不可逆的内容丢失。显示层按行高省略，存储保留全文。
        note = {"id": "%d%03d" % (int(time.time() * 1000), random.randint(0, 999)),
                "text": text, "created": dt.datetime.now().strftime("%H:%M"),
                "day": self.store._today()}
        self.store.notes = (getattr(self.store, "notes", []) or []) + [note]
        self.store.save()
        self.refresh_notes()
        self.push_tr("bot", "note_saved")

    def _del_note(self, nid):
        """删除便签（v1.9.9.45：可撤回）。

        便签最容易误操作（悬停就出现删除键），旧版删了没有任何兜底。"""
        notes = getattr(self.store, "notes", []) or []
        target = None
        idx = None
        for i, n in enumerate(notes):
            if n["id"] == nid:
                target, idx = n, i
                break
        if target is None:
            return
        self.store.notes = [n for n in notes if n["id"] != nid]
        self._push_undo({"kind": "note_del", "note": dict(target),
                         "index": idx, "label": "删除便签"})
        self.store.save()
        self.refresh_notes()
        self.flash(tr("note_deleted_undo"))

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
        try:
            e.focus_force()
            e.after(40, lambda: e.winfo_exists() and e.focus_force())
        except Exception:
            pass
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
        self._long_titles = {}      # v1.9.9.20：本屏被截断的标题（悬停提示用）
        w = max(cv.winfo_width(), 60)
        rh = self.row_height()
        # v1.9.9.27：分组渲染——日常（灰化后仍留原位）→ 临时未完成 → 已完成
        groups = self.list_groups()
        ordered = [x for _g, items in groups for x in items]
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
        k = 0
        for gi, (gname, items) in enumerate(groups):
            # 组头：日常 / 临时 / 已完成（只有多组时才画，单组保持清爽）
            if len(groups) > 1:
                y = self._draw_group_head(cv, y, w, gname, items)
            for _idx, t in items:
                self.draw_row(cv, y, w, rh, t, k,
                              fits[k] if k < len(fits) else True,
                              avail=avails[k] if k < len(avails) else None)
                y += rh
                k += 1
        total = y - 2
        cv.config(scrollregion=(0, 0, w, max(total + 4, cv.winfo_height())))
        # v1.9.9.20：空列表时给一个显眼的「记一条」按钮，点击直接聚焦输入框
        # （只有聊天输入框时，鼠标用户第一次容易找不到从哪加任务）
        if not ordered:
            self._draw_empty_hint(cv, w)
        if scroll_top:
            cv.yview_moveto(0)
        left = sum(1 for t in self.store.tasks if not t.get("done"))
        done = len(self.store.tasks) - left
        self.counter.config(text=self._counter_text(left, done))
        self.draw_bar()
        # 日历视图打开时实时跟随任务变化（增删改/勾选都会走到这）
        cal = getattr(self, "_cal_win", None)
        if cal is not None and cal.winfo_exists() and getattr(self, "_cal_cv", None):
            self._draw_calendar()
        self._update_bubble()

    def _draw_empty_hint(self, cv, w):
        """空列表提示 + 「记一条」按钮（v1.9.9.20）"""
        try:
            ch = cv.winfo_height()
            if ch < 60:                 # 首帧还没布局好，按窗口高度估
                ch = max(120, self.root.winfo_height() - 160)
            cy = max(60, ch // 2 - 30)
            cv.create_text(w / 2, cy, text=tr("empty_hint"),
                           fill=C.SUB, font=self.f_small, anchor="center")
            bw, bh = 96, 26
            x0, y0 = w / 2 - bw / 2, cy + 22
            cv.create_rectangle(x0, y0, x0 + bw, y0 + bh,
                                fill=C.ACCENT, outline="", tags=("empty_btn",))
            cv.create_text(x0 + bw / 2, y0 + bh / 2, text=tr("empty_add"),
                           fill="white", font=self.f_small,
                           tags=("empty_btn",))
            cv.tag_bind("empty_btn", "<Button-1>",
                        lambda e: self._focus_entry())
            cv.tag_bind("empty_btn", "<Enter>",
                        lambda e: cv.config(cursor="hand2"))
            cv.tag_bind("empty_btn", "<Leave>",
                        lambda e: cv.config(cursor=""))
        except Exception:
            pass

    def _focus_entry(self):
        """把焦点给输入框并给出明确反馈（空状态按钮 / 托盘菜单共用）。

        v1.9.9.21：原来只 focus，界面毫无变化，用户不知道刚才点了个啥。
        现在：清掉占位符让光标落进去 + 输入框边框闪两下高亮 + 功能栏
        浮出一句「在下面输入…回车即可记录」。"""
        try:
            self.clear_placeholder()          # 占位符不走，光标像没进去
            self.entry.focus_force()
            self.entry.icursor("end")
        except Exception:
            pass
        self.flash(tr("focus_hint"), 2600)
        # 边框高亮闪两下：高亮色 ↔ 常规色
        try:
            base = C.INPUT_LINE

            def _set(c, w):
                self.entry.config(highlightbackground=c, highlightcolor=c,
                                  highlightthickness=w)

            def _back():
                try:
                    _set(base, 1)
                except Exception:
                    pass
            _set(C.ACCENT, 2)
            self.root.after(260, lambda: _set(base, 2))
            self.root.after(520, lambda: _set(C.ACCENT, 2))
            self.root.after(900, _back)
        except Exception:
            pass

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
            tshow = self._row_time_text(t)       # v1.9.9.43：与绘制同口径
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

    def _row_time_text(self, t):
        """任务行时间位的显示文本（draw_row / _row_prefix_w / 气泡共用）

        v1.9.9.43：日常任务显示「每周四 21:00」式周期文字。旧版把一次性
        due_date（建「每周四晚上九点」时顺手记下的下一个周四 11/12）拼在
        前面，行首显示「11/12 21:00」，看起来像临时任务、计数却不算今天，
        用户困惑「明明两个日常为什么 0/1」。"""
        if self._is_daily(t):
            rt = self._repeat_text(t.get("repeat"))
            if rt:
                hhmm = t.get("hhmm")
                return (rt + " " + hhmm) if hhmm else rt
        hhmm = t.get("hhmm")
        return self._tshow(t, hhmm) if hhmm else ""

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

    def _draw_group_head(self, cv, y, w, gname, items=None):
        """分组小标题（v1.9.9.27）：日常 / 临时 / 已完成

        用一条浅色分隔线 + 左侧小字，不用大色块——便签本身已经很安静，
        组头只是「视觉分段」，不该抢任务标题的注意力。"""
        labels = {"daily": tr("grp_daily"), "tmp_undone": tr("grp_tmp"),
                  "tmp_done": tr("grp_done")}
        txt = labels.get(gname, "")
        h = 20
        col = C_DAILY if gname == "daily" else C.SUB
        cv.create_text(8, y + h / 2, text=txt, anchor="w",
                       font=self.f_tiny, fill=col)
        if gname == "daily":
            # 日常组头右侧写「今日完成 x/y」——v1.9.9.32 起与底栏计数
            # 同一套口径（_daily_counts：只数今天该做的），修掉
            # 「底栏 0/2、组头 1/3」对不上的问题；今天不该做的
            # （如周二的每周一三五）不计入分母
            try:
                _n, _dn = self._daily_counts()[:2]
            except Exception:
                _n, _dn = len(items or []), 0
            if _n:
                cv.create_text(w - 8, y + h / 2, text=tr("daily_progress", d=_dn, n=_n),
                               anchor="e", font=self.f_tiny, fill=col)
        tw = self.text_width(txt, self.f_tiny) + 16
        cv.create_line(tw, y + h / 2, w - 8, y + h / 2,
                       fill=_mix(C.LINE, C.BG, 0.35))
        return y + h

    def draw_row(self, cv, y, w, rh, task, idx, title_fits=True, avail=None):
        tid = task["id"]
        done = bool(task.get("done"))
        daily = self._is_daily(task)
        if daily:
            # 日常行：极淡青底 + 青色竖条，和临时任务的 红/橙/蓝/灰 分开
            bg = _mix(C.BG, C_DAILY, 0.10) if not done else _mix(C.BG, C_DAILY, 0.05)
        else:
            bg = C.BG if idx % 2 == 0 else _mix(C.BG, C.ACCENT, 0.07)
        cv.create_rectangle(0, y, w, y + rh, fill=bg, outline="",
                            tags=("row_" + tid,))
        # 竖条：日常 = 固定青色（不参与优先级）；临时 = 优先级色
        label, color = core.priority_label(task.get("score", 0))
        if daily:
            color = C_DAILY
        if not done or daily:
            cv.create_rectangle(6, y + 6, 9, y + rh - 6,
                                fill=color if not done else _mix(color, bg, 0.55),
                                outline="")
        # 时间（主）+ 时长（次，更浅的小字）：与 refresh_tasks 同口径（v1.9.7）
        # v1.9.8：时间固定画在行首 15px —— 之前误用 _row_prefix_w 返回的
        # 「标题起点」当时间起点，带截止时间的行整体右移了一截（时间前留空）
        # v1.9.9.3：tx 已含「时间宽 + 间隔」，这里不能再加上一遍
        # （之前时间宽被算两次，标题与时间之间空出一大截）
        tx, dw, dur_txt = self._row_prefix_w(task, w)
        hhmm = task.get("hhmm")
        # 日常任务在时间前加一个青色小标记，扫一眼就知道「这是每天的事」
        if daily:
            cv.create_text(11, y + rh / 2, text="●", anchor="w",
                           font=self.f_tiny,
                           fill=C_DAILY if not done else _mix(C_DAILY, bg, 0.55))
        if hhmm:
            tshow = self._row_time_text(task)    # v1.9.9.43：日常显示周期文字
            cv.create_text(15, y + rh / 2, text=tshow, anchor="w",
                           font=self.f_small,
                           fill=(_mix(C_DAILY, bg, 0.35) if (done and daily)
                                 else (C.SUB if done else (C_DAILY if daily else color))))
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
        # v1.9.9.20：标题被截断时，悬停显示完整内容
        if not title_fits:
            self._long_titles[tid] = task["title"].replace("\n", " ")
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
        # v1.9.9.20：被截断的标题，悬停看全文
        if not title_fits:
            cv.tag_bind("t_" + tid, "<Enter>",
                        lambda e, k=tid: self._show_title_tip(e, k))
            cv.tag_bind("t_" + tid, "<Leave>", lambda e: self._hide_title_tip())
        # v1.9.7：整行任意位置都能右键弹菜单（以前必须对准标题文字）
        cv.tag_bind("row_" + tid, "<Button-3>", lambda e, k=tid: self.row_menu(e, k))

    def _show_title_tip(self, e, tid):
        """悬停显示被截断的完整标题（v1.9.9.20）"""
        txt = (getattr(self, "_long_titles", None) or {}).get(tid)
        if not txt:
            return
        self._hide_title_tip()
        try:
            tip = tk.Toplevel(self.root)
            tip.overrideredirect(True)
            tip.attributes("-topmost", True)
            tk.Label(tip, text=txt, bg=C.HEAD, fg=C.TEXT, font=self.f_small,
                     wraplength=300, justify="left", padx=6, pady=3,
                     relief="flat").pack()
            tip.geometry("+%d+%d" % (e.x_root + 12, e.y_root + 16))
            self._title_tip = tip
        except Exception:
            self._title_tip = None

    def _hide_title_tip(self):
        tip = getattr(self, "_title_tip", None)
        if tip is not None:
            try:
                tip.destroy()
            except Exception:
                pass
            self._title_tip = None

    def _tray_ok(self):
        return bool(getattr(self, "_tray", None) and self._tray.available)

    def close_or_hide(self):
        """✕：一律藏进后台，进程永不因关窗退出（v1.9.9.24，用户明确要求）。

        提醒靠 root 的 after 循环继续跑，窗口藏起后照常弹提醒/气泡。
        退出的唯一入口是托盘菜单的「退出」。托盘还没就绪时也先藏
        （图标随后会出现）；托盘彻底不可用（非 Windows/初始化失败）
        时同样只藏不退——此时用户重新双击应用图标，单实例探针会把
        窗口拉回来，不会出现「窗口藏了找不回」的死局。"""
        if self._tray_ok():
            self.hide_to_tray()
            return
        # v1.9.9.45：托盘不可用时不改「关窗只隐藏」的行为（v1.9.9.24 用户
        # 明确要求），但保证**一定还有第二条退出路径**：聊天栏的「退出」
        # 和右键菜单里的「退出」不依赖托盘，见 _quote_bar_menu / 托盘缺失
        # 时的兜底提示。
        # 托盘未就绪/不可用：仍然只藏窗口。延迟一点再提示托盘状态，
        # 避免 flash 在窗口已隐藏时白白执行。
        try:
            self.root.after(300, lambda: self.flash(tr("tray_hidden_fallback"))
                            if not self._tray_hidden else None)
        except Exception:
            pass
        try:
            self.root.withdraw()
        except Exception:
            pass
        self._tray_hidden = True

    def hide_to_tray(self):
        """藏到托盘：窗口消失，进程和定时器都留着，提醒照常弹"""
        try:
            self.root.withdraw()
        except Exception:
            pass
        self._tray_hidden = True
        self.push("bot", tr("to_tray"))
        # v1.9.9.34：气泡只弹**第一次**（用户反馈：每次都弹影响观感，
        # 但系统气泡没有按钮可点「已知晓」）；之后想再开/关走托盘
        # 右键菜单或对话「关闭托盘提示」
        try:
            if (not getattr(self.store, "tray_notify_off", False)
                    and not getattr(self.store, "tray_notify_shown", False)):
                self._tray.notify(self.app_name(), tr("to_tray_notify"))
                self.store.tray_notify_shown = True
                self.store.save()
        except Exception:
            pass

    def _quote_bar_menu(self):
        """v1.9.9.35：哲言栏右键菜单——显示主窗口 / 换一句"""
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label=tr("tray_show"), command=self.restore_from_tray)
        m.add_command(label=tr("quote_roll"), command=lambda: self.roll_quote(manual=True))
        # v1.9.9.45：不依赖托盘的退出入口（托盘不可用时不再只剩强杀一条路）
        m.add_separator()
        m.add_command(label=tr("tray_quit"), command=self.quit)
        try:
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
        finally:
            m.grab_release()

    def restore_from_tray(self):
        """托盘图标单击 → 还原窗口"""
        self._tray_hidden = False
        try:
            self.root.deiconify()
            self.root.overrideredirect(True)
            self.root.attributes("-topmost", True)
            self.root.after(120, lambda: self.root.attributes(
                "-topmost", getattr(self.store, "topmost", True)))
            self._activate_window()
        except Exception:
            pass

    def tray_menu(self):
        """托盘右键菜单：记一条 / 显示主窗 / 退出"""
        try:
            m = tk.Menu(self.root, tearoff=0)
            m.add_command(label=tr("empty_add"),
                          command=lambda: (self.restore_from_tray(),
                                           self._focus_entry()))
            m.add_command(label=tr("tray_show"), command=self.restore_from_tray)
            # v1.9.9.34：后台气泡开关（默认只弹一次，可在这里永久关/开）。
            # 用动态标签而不是 checkbutton——Menu 变量在 overrideredirect
            # 场景下状态同步麻烦，文字写明「开/关」更直白
            m.add_command(
                label=tr("tray_menu_notify",
                         st=tr("state_off") if getattr(self.store, "tray_notify_off", False)
                         else tr("state_on")),
                command=self._toggle_tray_notify)
            m.add_separator()
            m.add_command(label=tr("tray_quit"), command=self.quit)
            m.tk_popup(self.root.winfo_pointerx(), self.root.winfo_pointery())
            m.grab_release()
        except Exception:
            pass

    def _toggle_tray_notify(self):
        """v1.9.9.34：托盘右键菜单里的气泡开关"""
        self.store.tray_notify_off = not getattr(self.store, "tray_notify_off",
                                                 False)
        if not self.store.tray_notify_off:
            self.store.tray_notify_shown = False    # 重新打开 → 下次再弹一次
        self.store.save()

    def toggle_done(self, tid):
        changed = False
        for t in self.store.tasks:
            if t["id"] == tid:
                # v1.9.9.43：不在今天到期的日常（如每周四的任务在周五）
                # 不能打卡——打卡了计数也不动，用户会困惑「打了卡怎么还是 0」
                if self._is_daily(t) and not self._daily_due_today(t) \
                        and not t.get("done"):
                    self.flash(tr("daily_not_today",
                                  t=t["title"], r=self._repeat_text(t.get("repeat"))))
                    return
                # v1.9.9.22：勾选/取消勾选也可撤回
                self._push_undo({"kind": "done", "id": tid,
                                 "prev": bool(t.get("done")),
                                 "prev_at": t.get("done_at") or "",
                                 "label": ("取消完成【%s】" if t.get("done") else "勾选完成【%s】") % t.get("title", "")})
                if self._is_daily(t):
                    # v1.9.9.27：日常任务 = 今天打卡（不写历史归档行，
                    # 打卡记录由 _daily_toggle 单独写进当天 history）
                    was = bool(t.get("done"))
                    now_done, streak = self._daily_toggle(t)
                    if now_done and not was:
                        changed = True
                        task = dict(t)
                        self._daily_streak = streak
                    break
                t["done"] = not t.get("done")
                t["done_at"] = dt.datetime.now().strftime("%H:%M") if t["done"] else ""
                if t["done"]:
                    changed = True
                    task = dict(t)
                break
        self.store.save()
        self.refresh_tasks()
        if changed:
            # 日常任务：说「打卡了」；临时任务：走原来的鼓励语
            if getattr(self, "_daily_streak", None):
                self.flash(tr("daily_checked", t=task["title"]))
                self._daily_streak = None
                # v1.9.9.36：日常打卡也要看「今日是否全部完成」——
                # 原来直接 return，最后一件是日常时哲言永远不弹
                left = len([x for x in self.store.tasks if not x.get("done")])
                if left == 0:
                    self.quote_on_complete(task, 0)
                return
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

    def _done_target(self, text, parsed_now, pz):
        """从完成语句里抽出任务名（v1.9.9.25，P0-4）。

        「完成数学作业」→ 数学作业
        「数学作业完成了」→ 数学作业
        「做完了数学作业」→ 数学作业
        抽不出返回 None（交给序号分支）。"""
        import re as _re
        t = (text or "").strip()
        DONE = r"(?:已经)?(?:完成|做完|搞定|做好|干完|弄好|结束)(?:了)?"
        # ⓪ v1.9.9.28：打卡句式必须先判——「打个卡 背单词」里的「打个卡」
        # 会被 ②（后置完成式）当成标题尾巴的一部分，标题就变成「打个卡」。
        m = _re.match(r"^[\s，,]*(?:今天|今日|刚刚|已经)?\s*"
                      r"(?:打个?卡|打一下卡|打卡|签个到|签到)\s*[：:，,、]?\s*(.+?)"
                      r"\s*[。.！!～~]*$", t)
        if m:
            cand = m.group(1).strip(" 的了，,。.！!？?")
            if cand and len(cand) <= 20:
                return cand
        m = _re.match(r"^[\s，,]*(?:今天|今日|刚刚|已经)?\s*(.+?)\s*"
                      r"(?:打卡|打了卡|签个到|签到)(?:了|啦|喽)?\s*[。.！!～~]*$", t)
        if m:
            cand = m.group(1).strip(" 的了，,。.！!？?")
            if cand and len(cand) <= 20:
                return cand
        # ① 前置：「完成/做完了 XX」
        m = _re.match(r"^[\s，,]*(?:我)?(?:已经)?(?:把)?(?:完成|做完|搞定|做好|干完|弄好)"
                      r"(?:了|掉)?\s*[，,]?\s*(.+)$", t)
        if m:
            cand = m.group(1).strip(" 的了，,。.！!？?")
            if cand and not _re.fullmatch(r"[第\d一二三四五六七八九十]+[个条项]?", cand):
                return cand
        # ② 后置：「XX 完成了 / 做完了」
        m = _re.match(r"^[\s，,]*(?:我)?(?:已经)?(?:把)?(.+?)\s*(?:已经)?"
                      r"(?:完成|做完|搞定|做好|干完|弄好|结束)(?:了|掉)?\s*[。.！!～~]*$", t)
        if m:
            cand = m.group(1).strip(" 的了，,。.！!？?")
            cand = _re.sub(r"^(?:我|把|将)\s*", "", cand)
            if cand and not _re.fullmatch(r"[第\d一二三四五六七八九十]+[个条项]?", cand):
                return cand
        # ②c v1.9.9.28：「做了背单词 / 看了两章书 / 学了英语」——
        # 动词 + 宾语的口语完成式。只在**已有任务能匹配上**时才用它
        # （调用方会再核对一次），避免把「买牛奶」这种新活误判成完成。
        m = _re.match(r"^[\s，,]*(?:我)?(?:今天|刚刚|已经)?\s*"
                      r"(?:做|弄|搞|看|读|背|学|练|写|听|跑)(?:了|过|完)\s*(.+?)"
                      r"\s*[。.！!～~]*$", t)
        if m:
            cand = m.group(1).strip(" 的了，,。.！!？?")
            if cand and len(cand) <= 20:
                return cand
        # ③ 序号形式（「完成第一个」）：交给调用方的序号分支
        if _re.fullmatch(r"[\s，,]*(?:完成|做完|搞定|做好|干完|弄好|删|删除|删掉)?\s*"
                         r"第\s*(?:[0-9]+|[一二三四五六七八九十]+)\s*[个条项件]?\s*"
                         r"(?:任务|待办)?\s*[。.！!～~]*", t):
            return None
        # ④ 回退到解析器结果（去掉标题里的完成词）
        cand = [x for x in parsed_now if not pz.DONE_RE.search(x[0])]
        if cand:
            return cand[0][0]
        # ④ 标题里带着完成词：剥掉后再试（「完成数学作业」被解析成整句时）
        if parsed_now:
            ttl = _re.sub(DONE, "", parsed_now[0][0]).strip(" 的了，,。.")
            if ttl:
                return ttl
        return None

    def _done_by_index(self, text):
        """「完成第一个 / 做完了第2条」按当前排序的未完成任务勾选"""
        import re as _re
        m = _re.search(r"第\s*([0-9]+|[一二三四五六七八九十]{1,3})\s*[个条项件]?", text or "")
        if not m:
            return None
        raw = m.group(1)
        try:
            idx = int(raw)
        except ValueError:
            idx = core._num(raw) if hasattr(core, "_num") else None
            if idx is None:
                return None
        left = [x for x in self.sorted_tasks() if not x[1].get("done")]
        if not left:
            return tr("left_none")
        if 1 <= int(idx) <= len(left):
            task = left[int(idx) - 1][1]
            if not task.get("done"):
                task["done"] = True
                task["done_at"] = dt.datetime.now().strftime("%H:%M")
                self.store.save()
                self.store.sync_history()
                self.refresh_tasks()
            return self._praise(tr("done_ok", title=task["title"]))
        return tr("done_notfound", title="第%s个任务" % raw)

    def _is_list_query(self, text):
        """「列表 / 我的任务 / 今天有什么任务 / 看看待办」这类查列表意图"""
        import re as _re
        t = (text or "").strip()
        if len(t) > 16:
            return False
        # v1.9.9.28：这里的 `[\s，,]*` 前缀让「打个卡 背单词」也命中
        # （「打个卡」被当成前导空白外的任意内容）→ 一句打卡被当成查列表。
        # 改成先剥掉首尾标点空白，再整句精确匹配。
        t2 = _re.sub(r"^[\s，,]+|[\s，,。.！!～~？?]+$", "", t)
        if _re.fullmatch(r"(?:我的|所有|全部|今天的?|当前的?)?"
                         r"(?:任务|待办|列表|清单|todo|list)(?:列表|清单)?"
                         r"(?:呢|吗|？|\?)?", t2, _re.I):
            return True
        return bool(_re.fullmatch(
            r"(?:今天|现在|当前)?(?:我)?(?:还)?(?:有|剩下?)"
            r"(?:什么|哪些|几个|多少)(?:任务|待办|事|活儿|没做的?|没完成的?)"
            r"(?:呢|吗|？|\?)?", t2))

    def _list_report(self):
        """播报未完成任务（按分数排序，最多 5 条）"""
        left = [x for x in self.sorted_tasks() if not x[1].get("done")]
        if not left:
            return tr("left_none")
        lines = []
        for i, (_k, task) in enumerate(left[:5], 1):
            hh = task.get("hhmm")
            mark = " %s" % hh if hh else ""
            lines.append("  %d. %s%s" % (i, task["title"], mark))
        more = "" if len(left) <= 5 else tr("list_more", n=len(left) - 5)
        return tr("list_report", n=len(left), lines="\n".join(lines), more=more)

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
        # v1.9.9.45：再补一次延迟聚焦。Windows 上 SetForegroundWindow/
        # SetFocus 之后，焦点可能又被拉回根窗口，导致第一个字打不进编辑框
        try:
            e.after(40, lambda: e.winfo_exists() and e.focus_force())
        except Exception:
            pass
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
                    # v1.9.9.45：只改今天的历史行；往日记录保持当时的名字
                    self.store.purge_history({_old}, only_today=True,
                                             tids={task.get("id")})
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
            # v1.9.9.22：改名也可撤回
            self._push_undo({"kind": "rename", "id": target.get("id"),
                             "prev": _old,
                             "label": "改名「%s」→「%s」" % (_old, val)})
            target["title"] = val
            if not target.get("manual"):
                target["score"] = core.score_task(val, val, target.get("hhmm"))
            # v1.9.9.5：改名同步清历史旧行（同 begin_edit 的 commit）
            # v1.9.9.45：只清今天，且按 id 精确匹配（同名任务不再互相牵连）
            if _old:
                self.store.purge_history({_old}, only_today=True,
                                         tids={target.get("id")})
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
        # v1.9.9.35：修改截止时间——内容能改、时间也必须能改
        m.add_command(label=tr("menu_time"),
                      command=lambda: self._menu_time(tid))
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

    def _menu_time(self, tid):
        """v1.9.9.35：右键「修改时间」——弹输入框，自然语言解析
        （「21:30」「晚上9点半」「明天下午3点」都行）"""
        from tkinter import simpledialog
        task = None
        for t in self.store.tasks:
            if t.get("id") == tid:
                task = t
                break
        if task is None:
            return
        cur = task.get("hhmm") or ""
        when = simpledialog.askstring(
            tr("menu_time"),
            tr("time_ask", t=task["title"]) + "\n" + tr("time_hint"),
            initialvalue=cur, parent=self.root)
        if not when or not when.strip():
            return
        dl = self._apply_new_time(task, when.strip())
        if dl is None:
            self.flash(tr("time_bad", s=when.strip()))
        else:
            self.flash(tr("dl_set", t=task["title"], d=dl))

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
                # v1.9.9.22：优先级调整也可撤回
                self._push_undo({"kind": "priority", "id": tid,
                                 "prev_score": t.get("score"),
                                 "prev_manual": bool(t.get("manual")),
                                 "label": "调整【%s】的优先级" % t.get("title", "")})
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
                # v1.9.9.22：删除也可撤回（还原原位置）
                self._push_undo({"kind": "delete", "id": tid,
                                 "task": dict(t),
                                 "index": self.store.tasks.index(t),
                                 "label": "删除【%s】" % t.get("title", "")})
        self.store.tasks = [t for t in self.store.tasks if t["id"] != tid]
        if titles:
            # v1.9.9.45：只清**今天**这条的历史。旧版按标题清所有天——
            # 昨天的「买牛奶」是真实完成过的记录，不该跟着一起消失
            self.store.purge_history(titles, only_today=True, tids={tid})
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

    def _wheel_route(self, e):
        """v1.9.9.37：滚轮全局路由（bind_all），纯指针位置派发。

        关键教训（v1.9.9.36 修不好的根因）：Windows 上滚轮事件可能派给
        「持有键盘焦点的控件」而不是指针下的控件——本程序启动就把焦点
        锁在输入框，旧路由里「输入框 → 交给控件自己」一句，等于把
        全窗口的滚轮都送进了输入框的横向滚动（肉眼无反应）。
        所以这里不做任何控件跳过：事件不管落在谁头上，都按指针位置
        滚对应的区域。"""
        num = getattr(e, "num", 0)
        delta = getattr(e, "delta", 0)
        up = (num == 4) or delta > 0
        down = (num == 5) or delta < 0
        if not (up or down):
            return
        try:
            top = e.widget.winfo_toplevel()
            if top is not self.root:
                return      # 日历/历史等子窗口有自己的滚轮绑定
        except Exception:
            pass
        try:
            bottom = self.chat_cv.winfo_rooty() + self.chat_cv.winfo_height()
        except Exception:
            return
        # 注意两个 handler 的方向约定相反：
        # · on_list_wheel：+1 = yview 向下滚
        # · on_chat_wheel：+1 = offset 增大 = 看更旧的上一屏
        # 所以「滚轮向上」对列表是 -1、对聊天是 +1。（旧代码 Button-4
        # 直接传 -1 给聊天区，X11 下聊天滚轮方向一直是反的）
        if e.y_root < bottom:
            self.on_chat_wheel(e, 1 if up else -1)
        else:
            self.on_list_wheel(e, -1 if up else 1)

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
        # v1.9.9.33：与中文版口径统一——哲言不再每完成一件就发，
        # 今日任务全部完成才补一句（英文版实测反馈）
        left = len([x for x in self.store.tasks if not x.get("done")])
        if left == 0:
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
        r"""系统铃声：播放 C:\Windows\Media 的真实音效文件，线程里响不卡界面"""
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
        # v1.9.9.20：同时发一条系统托盘气泡——窗口藏进托盘 / 被其他
        # 全屏窗口盖住时，右下角卡片可能看不到，气泡是第二道保险
        if self._tray_ok():
            try:
                t_txt = task.get("title", "")
                h_txt = task.get("hhmm") or ""
                self._tray.notify(tr("due_win_title"),
                                  ("%s  %s" % (t_txt, h_txt)).strip())
            except Exception:
                pass

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
        # v1.9.9.44：不再写死 300x226——行数随任务信息变多，固定高度把
        # 底部「完成/关闭」按钮挤出窗口。改为先摆内容、按需求尺寸开窗
        win.attributes("-topmost", True)
        win.attributes("-alpha", min(1.0, getattr(self.store, "alpha", 0.88) + 0.05))
        win.resizable(False, False)
        # 贴着主便签右侧打开，别盖住列表（位置在内容摆完后按真实宽高算）
        try:
            x = self.root.winfo_x() + self.root.winfo_width() + 8
            y = self.root.winfo_y() + 30
            win._detail_pos = (x, y)
        except Exception:
            win._detail_pos = None
        rep = task.get("repeat")
        tk.Label(win, text=tr("due_detail_head", t=task["title"]), bg=C.BG,
                 fg=C.TEXT, font=(self.f_ui, 11, "bold"),
                 wraplength=264, justify="left").pack(anchor="w", padx=14, pady=(12, 4))
        label, pcolor = core.priority_label(task.get("score", 0))
        # 优先级值带档位色，一眼分清急缓（v1.9.7）
        # v1.9.9.19：行标签从「调整优先级」改成「优先级」——原来复用
        # 右键菜单的 menu_priority，读起来像能在这里调优先级
        rows = [(tr("pri_label"), label, pcolor)]
        # 周期任务：下次到期日（每周X任务显示「下个周四」，也是提醒时刻的基准）
        nxt = self._next_occurrence(task) if rep else None
        if task.get("hhmm"):
            rows.append((tr("due_at", d=""), task["hhmm"], None))
            # 剩余时间：一次性任务看 due_date/今天（v1.9.7）；周期任务
            # 看**下次到期**——旧版拿残留的一次性 due_date 算出
            # 「还有 128 小时」，完全不对
            if rep:
                left_min = self._left_minutes(task, day=nxt) if nxt else None
            else:
                left_min = self._left_minutes(task)
            if left_min is not None:
                if left_min >= 0:
                    h6, m6 = divmod(left_min, 60)
                    if h6 >= 24:
                        # v1.9.9.44：超过一天的剩余别再拿「146 小时」糊脸
                        d6, h6 = divmod(h6, 24)
                        left_txt = tr("detail_left_dm") % (d6, h6)
                    else:
                        left_txt = (tr("detail_left_hm") % (h6, m6)) if h6 \
                            else (tr("detail_left_m") % m6)
                else:
                    left_txt = tr("detail_left_over")
                rows.append((tr("detail_left"), left_txt,
                             None if left_min >= 0 else "#B4463C"))
        if rep:
            # v1.9.9.44：日常任务没有截止日期——旧数据里残留的一次性
            # due_date（如 2026-11-12）不再显示，改示「下次」到期日
            if nxt is not None and nxt != dt.date.today():
                wnames = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
                rows.append((tr("detail_next"),
                             "%d-%d（%s）" % (nxt.month, nxt.day,
                                              wnames[nxt.weekday()]), None))
        elif task.get("due_date"):
            rows.append((tr("detail_due_date"), task["due_date"], None))
        if task.get("remind_at"):
            rows.append((tr("detail_remind"), task["remind_at"], None))
        elif task.get("remind_before"):
            _m = task["remind_before"]
            _mtxt = tr("remind_%d" % _m) if _m in (5, 15, 30, 60) \
                else "%d %s" % (_m, tr("clock_min"))
            # v1.9.9.44：「5分钟」没头没尾——说清「提前5分钟」，带钟点的
            # 算出实际提醒时刻：「提前5分钟 · 20:55 提醒您」
            if task.get("hhmm"):
                try:
                    _h, _mi = [int(x) for x in task["hhmm"].split(":")]
                    _rt = (dt.datetime(2000, 1, 1, _h, _mi)
                           - dt.timedelta(minutes=_m))
                    rows.append((tr("detail_remind"),
                                 tr("detail_remind_plan",
                                    m=_mtxt, t=_rt.strftime("%H:%M")), None))
                except Exception:
                    rows.append((tr("detail_remind"), _mtxt, None))
            else:
                rows.append((tr("detail_remind"), _mtxt, None))
        if task.get("dur"):
            rows.append((tr("detail_spent"), task["dur"], None))
        if rep:
            rows.append((tr("detail_repeat"),
                         self._repeat_text(rep), None))
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
        # 内容摆完 → 按需求尺寸开窗（行再多按钮也不会被挤出去）
        win.update_idletasks()
        _w = max(win.winfo_reqwidth(), 280)
        _h = win.winfo_reqheight()
        _pos = getattr(win, "_detail_pos", None)
        _x, _y = _pos if _pos else (60, 60)
        _sw = win.winfo_screenwidth()
        if _x + _w + 8 > _sw:
            _x = max(4, _sw - _w - 8)
        win.geometry("%dx%d+%d+%d" % (_w, _h, _x, _y))

    def _next_occurrence(self, task, start=None):
        """周期任务的下一次到期日（从今天起往后找）；找不到返回 None。

        每周X任务的「下次」、剩余时间、提前提醒时刻都以它为基准，
        不再依赖旧数据残留的一次性 due_date。"""
        d0 = start or dt.date.today()
        for _i in range(367):
            _d = d0 + dt.timedelta(days=_i)
            try:
                if self._daily_due_today(task, _d):
                    return _d
            except Exception:
                return None
        return None

    def _left_minutes(self, task, day=None):
        """距截止还有多少分钟；无法判断返回 None，已过返回负数。

        v1.9.9.44：周期任务传入下次到期日 day，按那一天算剩余。"""
        hhmm = task.get("hhmm")
        if not hhmm:
            return None
        try:
            h, mi = [int(x) for x in hhmm.split(":")]
            dd = day or task.get("due_date") or self.store._today()
            y, mo, d = [int(x) for x in str(dd).split("-")]
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
                # v1.9.9.43：「每周四」比「周四」更像日常任务的周期描述
                return ("每周" + "一二三四五六日"[int(wd)]) if zh else \
                    "Every " + ["Mon", "Tue", "Wed",
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
            # v1.9.9.45：**逐条容错**。旧版一条任务的时间写坏（手改文件、
            # 旧数据残留）就会让 split(":") 抛 ValueError，整个循环中断 →
            # 从那一刻起所有任务都不再提醒，而且调用处把异常吞了。
            try:
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
                at = due - dt.timedelta(minutes=int(t.get("remind_before") or 0))
                if at <= now <= due + dt.timedelta(minutes=1):
                    t["reminded"] = True
                    t["reminded_day"] = self.store._today()
                    fired.append((t, "before"))
            except Exception as exc:
                self.diag("[remind] 跳过坏数据 %r id=%r hhmm=%r" % (
                    exc, t.get("id"), t.get("hhmm")))
                continue
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
            # v1.9.9.18：超过 1 小时用「xx小时xx分钟」，60分/90分 这种读着别扭；
            # 不到 1 小时仍用 mm:ss，方便看秒级
            if m >= 60:
                hh, mm = divmod(m, 60)
                txt = "%s  %d%s%d%s" % (tr("clock_sw"), hh, tr("clock_hr"),
                                        mm, tr("clock_min"))
            else:
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
        # v1.9.9.32：跳转框初始值应该是当前年月，不是 1970/1
        self._cal_ys.delete(0, "end")
        self._cal_ys.insert(0, str(self._cal_y))
        self._cal_ms.delete(0, "end")
        self._cal_ms.insert(0, str(self._cal_m))
        # 确认按钮：输完年月点一下才跳（Spinbox 的箭头不再即时跳转）
        tk.Button(quick, text=tr("cal_jump_go"), bg=C.ROW2, fg=C.TEXT,
                  relief="flat", padx=6,
                  command=self._cal_jump).pack(side="left", padx=(4, 0))
        tk.Button(quick, text=tr("cal_today"), bg=C.ROW2, fg=C.TEXT, relief="flat",
                  command=self._cal_today).pack(side="right")
        # v1.9.9.40：圆点图例——青绿=日常，深金=临时
        lg = tk.Frame(win, bg=C.BG)
        lg.pack(side="top", fill="x", padx=8, pady=(0, 1))
        self._cal_legend_temp = tk.Label(
            lg, text="● " + tr("cal_legend_temp"), bg=C.BG, fg=C.ACCENT,
            font=self.f_tiny)
        self._cal_legend_temp.pack(side="right")
        self._cal_legend_daily = tk.Label(
            lg, text="● " + tr("cal_legend_daily"), bg=C.BG, fg=C_DAILY,
            font=self.f_tiny)
        self._cal_legend_daily.pack(side="right", padx=(10, 0))
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
        # v1.9.9.31：首次打开就显示今天的安排（用户不必先点一下日期）。
        # 只有当底部面板还是空的时候才填，避免覆盖用户刚点选的日期
        if not self._cal_info.cget("text"):
            self._cal_show_day(dt.date.today().isoformat())

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
        # 有日程的日期集合（截止日期 / 创建日 / 重复任务命中日）
        # v1.9.9.26：与 _cal_day_items 同源，避免「点上说没有安排」
        # v1.9.9.27：日常任务当天已打卡的日期单独记一份，画成空心圈
        # v1.9.9.40：日常与临时分开记——圆点颜色区分（日常青绿/临时深金），
        # 两种都有时并排画两个点
        busy_daily = set()          # 日常任务（repeat）命中的日期
        busy_temp = set()           # 临时任务的创建日 / 截止日
        daily_all_done = set()      # 当天日常全部打卡的日期（画空心圈）
        today_s = self.store._today()
        for t in self.store.tasks:
            if t.get("repeat"):
                continue            # 重复任务走下面的整月推算
            if t.get("due_date"):
                busy_temp.add(t["due_date"])
            if t.get("day"):
                busy_temp.add(t["day"])
        first0 = dt.date(y, m, 1)
        ndays0 = (dt.date(y + (m == 12), (m % 12) + 1, 1) - first0).days
        # v1.9.9.35：圆点改为**按显示的月份**整月计算——原来的
        # 「未来 60 天」上限是随便定的，2027 年 1 月就断档了
        for _i in range(ndays0):
            _d = first0 + dt.timedelta(days=_i)
            _ds = _d.isoformat()
            if _ds in busy_daily:
                continue
            for _t in self.store.tasks:
                if _t.get("repeat") and (_t.get("day") or "") <= _ds \
                        and self._daily_due_today(_t, _d):
                    busy_daily.add(_ds)
                    break
        # 今天的日常若已全部打卡，圆点改成空心（○ = 还没打卡，● = 打完了）
        try:
            _n, _dn = self._daily_counts()[:2]
            if _n and _dn >= _n:
                daily_all_done.add(today_s)
        except Exception:
            pass
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
                               font=self.f_tiny, fill="#E2434B", tags=(tag,))
            elif hol == "班":
                cv.create_text(x0 + cw - 14, y0 + 12, text="班",
                               font=self.f_tiny, fill="#3E8ED0", tags=(tag,))
            # 节日名
            if fest:
                cv.create_text(x0 + cw / 2, y0 + 44, text=fest,
                               font=self.f_tiny, fill="#EE9A2B", tags=(tag,))
            # 有日程：小圆点（今天日常全部打完 → 空心圈，表示「已完成打卡」）
            # v1.9.9.35：圆点缩到 r=2.5 并压到格子底部——原来 r=3、
            # y0+ch-14 会压到节日名称（「元旦」和圆点叠在一起）
            # v1.9.9.40：日常=青绿、临时=深金；两种都有 → 并排两点
            has_d, has_t = ds in busy_daily, ds in busy_temp
            if has_d or has_t:
                _yc = y0 + ch - 9
                _xc = x0 + cw / 2
                if has_d and has_t:
                    cv.create_oval(_xc - 5.9, _yc - 2.2, _xc - 1.5, _yc + 2.2,
                                   fill=C_DAILY, outline="", tags=(tag,))
                    cv.create_oval(_xc + 1.5, _yc - 2.2, _xc + 5.9, _yc + 2.2,
                                   fill=C.ACCENT, outline="", tags=(tag,))
                elif has_d:
                    if ds in daily_all_done:
                        cv.create_oval(_xc - 2.5, _yc - 2.5, _xc + 2.5, _yc + 2.5,
                                       outline=C_DAILY, width=1.4, tags=(tag,))
                    else:
                        cv.create_oval(_xc - 2.5, _yc - 2.5, _xc + 2.5, _yc + 2.5,
                                       fill=C_DAILY, outline="", tags=(tag,))
                else:
                    cv.create_oval(_xc - 2.5, _yc - 2.5, _xc + 2.5, _yc + 2.5,
                                   fill=C.ACCENT, outline="", tags=(tag,))
            # 点击日期 -> 底部显示当天安排
            cv.tag_bind(tag, "<Button-1>",
                        lambda e, dd=ds: self._cal_show_day(dd))

    # ---------------- 日常任务（v1.9.9.27）
    # 设计要点：**不新建表、不分栏**。日常任务就是带 repeat 的普通任务，
    # 区别只有两点：
    #   ① 勾掉后留在原位置灰化（而不是掉进已完成区），因为「今天的打卡」
    #      和「这件事完结了」是两件事；
    #   ② 不参与优先级排序（没有 score 竖条），只按时间排。
    @staticmethod
    def _is_daily(task):
        """带 repeat 的任务 = 日常任务（每天 / 每周X / 工作日 / 每月X号）"""
        rep = (task or {}).get("repeat")
        return bool(rep and (rep.get("kind") if isinstance(rep, dict) else True))

    def _daily_due_today(self, task, day=None):
        """这个日常任务今天该不该做"""
        rep = task.get("repeat")
        if not rep:
            return False
        # v1.9.9.32：旧版本数据里 repeat 是字符串（「每周三」）——
        # 统一先归一化成 dict，否则 repeat_due_today 会崩
        if isinstance(rep, str):
            rep = core.find_repeat(rep)
            if rep is None:
                return True
        try:
            return core.repeat_due_today(rep, day)
        except Exception:
            return True

    def _daily_toggle(self, task, now=False):
        """日常任务打卡 / 取消打卡（当天内可撤）。

        返回 (是否已打卡, streak)。streak 只在「当天连续」时累加：
        昨天该做且打过卡才 +1，断签归 1。
        """
        today = self.store._today()
        if not task.get("done"):
            # 打卡
            task["done"] = True
            task["done_at"] = dt.datetime.now().strftime("%H:%M")
            last = task.get("last_done_day")
            prev_streak = int(task.get("streak") or 0)
            yday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
            if last == today:
                streak = max(1, prev_streak)         # 当天重复操作不叠加
            elif last == yday:
                streak = prev_streak + 1
            else:
                streak = 1
            task["streak"] = streak
            task["last_done_day"] = today
            self._write_daily_history(task, today, True)
            return True, streak
        # 取消打卡：只允许当天撤销
        task["done"] = False
        task["done_at"] = None
        if task.get("last_done_day") == today:
            task["streak"] = max(0, int(task.get("streak") or 1) - 1)
            task["last_done_day"] = None
            self._write_daily_history(task, today, False)
        return False, int(task.get("streak") or 0)

    def _write_daily_history(self, task, day, done):
        """把日常打卡写进 history（按 id 关联，改名不影响历史）"""
        try:
            rows = self.store.history.setdefault(day, [])
            rows = [r for r in rows if not (r.get("id") == task.get("id")
                                            and r.get("daily"))]
            if done:
                rows.append({"id": task.get("id"), "title": task.get("title"),
                             "hhmm": task.get("hhmm"), "done": True,
                             "daily": True, "at": task.get("done_at") or "",
                             "streak": task.get("streak") or 1})
            self.store.history[day] = rows
            self.store.save_history()
        except Exception:
            pass

    def _cal_day_items(self, ds):
        """某天的安排：创建日/截止日命名的任务，外加重复任务
        （每天 → 天天算；每周X → 命中星期几才算）。

        v1.9.9.26：原来只按 day/due_date 匹配——「每天背单词」只在
        创建那天显示，之后日历天天显示「这天没有安排」，和主界面
        的实际感受对不上（用户反馈的第二问）。"""
        try:
            d = dt.date.fromisoformat(ds)
        except ValueError:
            return []
        items = []
        for t in self.store.tasks:
            if t.get("day") == ds or t.get("due_date") == ds:
                items.append(t)
                continue
            # v1.9.9.32：repeat 是 dict，旧的 `"每" in rep` 字符串判断
            # 永远为 False → 日常任务在日历上只有创建日有一天
            if not t.get("repeat"):
                continue
            if (t.get("day") or "") > ds:
                continue      # 还没创建的任务不外推
            if self._daily_due_today(t, d):
                items.append(t)
        return items

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
        items = self._cal_day_items(ds)
        if items:
            done = sum(1 for t in items if t.get("done"))
            parts.append(tr("cal_day_tasks", n=len(items), d=done))
            # v1.9.9.35：原来只列前 3 件——4 件任务永远显示 3 件，
            # 用户以为漏了。放宽到 6 件（再多挤不下一行，以计数为准）
            for t in items[:6]:
                # v1.9.9.40：日常任务用 ◆ 标出，与圆点颜色呼应
                mark = "✓" if t.get("done") else \
                    ("◆" if t.get("repeat") else "·")
                parts.append("  %s %s" % (mark, t["title"]))
        else:
            parts.append(tr("cal_day_empty"))
        self._cal_info.config(text="   ".join(parts[:10]))

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
        # v1.9.9.20：导出入口放在历史窗口（数据都在这儿看，顺手就能导）
        self.export_btn = tk.Label(head, text=tr("export_btn"), bg=C.HEAD, fg=C.SUB,
                                   font=self.f_tiny, padx=8, cursor="hand2")
        self.export_btn.pack(side="right")
        self.export_btn.bind("<Button-1>", self.open_export_menu)
        self.export_btn.bind("<Enter>", lambda e: self.export_btn.config(fg=C.ACCENT))
        self.export_btn.bind("<Leave>", lambda e: self.export_btn.config(fg=C.SUB))

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

    def open_export_menu(self, e=None):
        """导出菜单：JSON（完整备份）/ Markdown（可读归档）/ 日历 ICS（v1.9.9.20）"""
        m = tk.Menu(self.root, tearoff=0)
        m.add_command(label=tr("export_json"),
                      command=lambda: self.do_export("json"))
        m.add_command(label=tr("export_md"),
                      command=lambda: self.do_export("md"))
        m.add_command(label=tr("export_ics"),
                      command=lambda: self.do_export("ics"))
        m.add_separator()
        # v1.9.9.45：能导出不能导入 = 备份不可恢复。补上恢复入口，
        # 恢复前先把当前数据另存一份，避免「恢复」变成第二次事故。
        m.add_command(label=tr("import_json"), command=self.restore_from_json)
        m.add_command(label=tr("export_open_dir"),
                      command=self.open_data_dir)
        try:
            if e is not None:
                m.tk_popup(e.x_root, e.y_root)
            else:
                m.tk_popup(self.root.winfo_pointerx(),
                           self.root.winfo_pointery())
        finally:
            m.grab_release()

    def restore_from_json(self):
        """从导出的 JSON 恢复任务 / 历史 / 对话（v1.9.9.45）。

        恢复前会先把当前 tasks.json 另存一份 `.before-import-时间戳`，
        万一选错文件还能回到原样。主题/语言不跟着改（会牵动整套界面
        重建，留给设置里手动选）。"""
        from tkinter import filedialog, messagebox
        try:
            p = filedialog.askopenfilename(
                title=tr("import_title"), initialdir=data_dir(),
                filetypes=[("JSON", "*.json"), (tr("all_files"), "*.*")])
        except Exception:
            p = None
        if not p:
            return
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                obj = json.load(f)
        except Exception as exc:
            self.push("bot", tr("import_fail", e=str(exc)))
            return
        if not isinstance(obj, dict):
            self.push("bot", tr("import_fail", e="not json object"))
            return
        tasks = obj.get("tasks")
        if not isinstance(tasks, list):
            self.push("bot", tr("import_fail", e="no tasks"))
            return
        if not messagebox.askyesno(
                self.app_name(), tr("import_confirm", n=len(tasks))):
            return
        # 先保命：当前数据另存一份
        try:
            ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            shutil.copy2(self.store.path, self.store.path + ".before-import-" + ts)
        except Exception:
            pass
        self.store.tasks = [t for t in tasks if isinstance(t, dict)]
        hist = obj.get("history")
        if isinstance(hist, dict):
            self.store.history = {k: v for k, v in hist.items()
                                  if isinstance(v, list)}
        msgs = obj.get("messages")
        if isinstance(msgs, list):
            self.store.messages = msgs[-MSG_KEEP:]
        st = obj.get("settings") or {}
        try:
            if st.get("user_name"):
                self.store.user_name = str(st["user_name"])
        except Exception:
            pass
        self.store.save()
        try:
            self.store.save_history()
        except Exception:
            pass
        self.refresh_tasks()
        self.render_messages()
        self.draw_bar()
        self.push("bot", tr("import_ok", n=len(self.store.tasks), p=p))

    def open_data_dir(self):
        """在资源管理器里打开数据目录（方便用户自己拿备份）"""
        try:
            d = data_dir()
            if os.name == "nt":
                os.startfile(d)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", d])
            else:
                subprocess.Popen(["xdg-open", d],
                                 stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL)
        except Exception:
            self.push("bot", tr("export_dir_fail", d=data_dir()))

    def do_export(self, kind):
        """生成导出文件：默认放到数据目录，成功后告诉用户路径"""
        try:
            import exporter as _exp
            self.store.sync_history()
            ext = {"json": "json", "md": "md", "ics": "ics"}[kind]
            # v1.9.9.45：精确到秒。旧版到分钟，一分钟内导两次后一次
            # 直接覆盖前一次（用户以为有两份备份，其实只有一份）
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            name = _exp.safe_name("每日记事本-%s.%s" % (stamp, ext))
            path = os.path.join(data_dir(), name)
            if kind == "json":
                data = _exp.to_json(self.store.tasks, self.store.history,
                                    {"user_name": self.nickname,
                                     "theme": self.store.theme,
                                     "lang": self.store.lang,
                                     "font_scale": self.store.font_scale,
                                     "alpha": self.store.alpha,
                                     "bell_mode": self.store.bell_mode,
                                     "version": VERSION},
                                    messages=self.store.messages)
            elif kind == "md":
                data = _exp.to_markdown(self.store.tasks, self.store.history)
            else:
                data = _exp.to_ics(self.store.tasks, self.store.history)
            # 先写临时文件再替换：导到一半失败不会留下半截文件
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8", newline="") as f:
                f.write(data)
            os.replace(tmp, path)
            self.push("bot", tr("export_ok", p=path))
            return path
        except Exception as exc:
            self.push("bot", tr("export_fail", e="%s" % exc))
            return None

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

def _single_instance_register(on_show, root0, srv0=None):
    """尝试成为唯一实例。成功返回 (socket, serve)；已有实例在跑则
    通知它显示窗口并返回 (None, None)。

    v1.9.9.1 关键修复：accept 彻底移出 UI 线程（后台线程阻塞 accept，
    UI 线程用 after 每 300ms 非阻塞取队列）。

    v1.9.9.17 修复「双击 exe 没反应」：原逻辑端口被占 → 发 show →
    连接也失败（端口被僵尸进程占据）→ 静默退出。现在改为：发 show
    失败后等 0.5 秒尝试**接管**端口（SO_REUSEADDR=1），接管成功就
    照常启动，只有真的接管不了才退出。

    v1.9.9.18：srv0 —— main() 早期探针已经 bind 好的 socket，
    直接复用，省掉一次 bind/listen。
    """
    def _bind():
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        srv.bind(("127.0.0.1", _SINGLE_PORT))
        srv.listen(2)
        return srv

    srv = srv0
    if srv is None:
        try:
            srv = _bind()
        except OSError:
            # 端口被占 → 通常已有实例：通知它亮出窗口
            notified = False
            try:
                c = socket.create_connection(("127.0.0.1", _SINGLE_PORT), timeout=1)
                c.sendall(b"show")
                c.close()
                notified = True
            except Exception:
                notified = False
            if notified:
                return None, None
            # show 也没送出去 → 大概率是僵尸进程占着端口。等 0.5 秒尝试接管
            time.sleep(0.5)
            try:
                srv = _bind()
            except OSError:
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
            # v1.9.9.45：路径里的单引号在 PowerShell 单引号串里要写成两个；
            # 旧版直接拼 '%s'，用户名是 O'Brien 这类会语法错误，快捷方式
            # 建不出来（极端情况下还被当成命令注入）
            def _psq(p):
                return "'" + str(p).replace("'", "''") + "'"

            icon_part = ("$s.IconLocation=%s;" % _psq(ico + ",0")) if ico else ""
            ps = "$ws=New-Object -ComObject WScript.Shell;"
            for d in targets:
                lnk = os.path.join(d, "每日记事本.lnk")
                ps += ("$s=$ws.CreateShortcut(%s);"
                       "$s.TargetPath=%s;" % (_psq(lnk), _psq(target)))
                if getattr(sys, "frozen", False):
                    ps += "$s.WorkingDirectory=%s;" % _psq(progdir)
                else:
                    ps += ("$s.Arguments=%s;"
                           "$s.WorkingDirectory=%s;"
                           % (_psq('"%s"' % os.path.join(progdir, "main.py")),
                              _psq(progdir)))
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


_MUTEX_NAME = "DailyNotebook_SingleInstance_Mutex"
_MUTEX_HANDLE = None        # 进程存活期间持有，退出即由系统释放


def _win_mutex_try():
    """Windows 命名互斥量单实例判据（v1.9.9.19）。

    端口判据在 Windows 上不可靠：SO_REUSEADDR 让两个进程同时 bind
    成功，不带又可能被残留连接的 TIME_WAIT 卡住。互斥量由内核保证
    一次只有一个进程持有，进程退出（哪怕被强杀）自动释放。
    返回 True=我是首个实例（句柄存全局，进程存活期间持有）；
    False=已有实例；None=非 Windows 或创建失败（退回端口判据）。"""
    global _MUTEX_HANDLE
    if os.name != "nt":
        return None
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.CreateMutexW(None, False, _MUTEX_NAME)
        if not h:
            return None
        # ERROR_ALREADY_EXISTS = 183：互斥量已存在 → 已有实例在跑。
        # 句柄仍要保存：持有它才能让「是否存在」的语义一直成立。
        already = k32.GetLastError() == 183
        _MUTEX_HANDLE = h
        return not already
    except Exception:
        return None


def _probe_existing_instance():
    """启动最早期判断「是不是已经有实例在跑」。

    v1.9.9.18：这是独立于 _single_instance_register 的“快速探针”。
    原流程是先 tk.Tk() + NoteApp(root)（读数据、建全部控件、约 6~10 秒），
    才做单实例检测 —— 于是重复启动会白build一整套界面再退出，
    用户感觉像卡住。现在先探一次：
      - 端口能用 → 说明没有别的实例，返回 ("free", None)，继续正常启动
      - 端口被占且能连上 → 已有实例，发 show 让它亮出窗口，返回 ("exists", None)
      - 端口被占但连不上 → 疑似僵尸占口，返回 ("zombie", None)，交给后面接管
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    ok = False
    try:
        # v1.9.9.19：探针**不带** SO_REUSEADDR——Windows 上带了这个选项
        # 就算端口已被别的实例持有也能 bind 成功，探针误报「free」，
        # 重复双击会白建整套界面（QA 实测命中）。绑定失败才是「被占」。
        s.bind(("127.0.0.1", _SINGLE_PORT))
        s.listen(2)
        ok = True
        return "free", s           # 顺手把已经 bind 好的 socket 交回去复用
    except OSError:
        ok = False
    finally:
        if not ok:
            try:
                s.close()
            except Exception:
                pass
    try:
        c = socket.create_connection(("127.0.0.1", _SINGLE_PORT), timeout=1)
        c.sendall(b"show")
        c.close()
        return "exists", None
    except Exception:
        return "zombie", None


def main():
    def _diag(msg):
        """启动阶段黑匣子：走 NoteApp 的后台写日志线程（绝不在 UI 线程碰磁盘），
        若再出现卡死，data/log.txt 能定位到阶段"""
        try:
            app.diag("[main] " + msg)
        except Exception:
            pass

    # v1.9.9.18：先探单实例，命中就直接退出（毫秒级），不再白建整个界面
    # v1.9.9.19：Windows 优先用命名互斥量判据（端口判据在 Windows 的
    # SO_REUSEADDR 语义下会误报 free）。互斥量说已有实例 → 通知已有
    # 实例亮窗口后立即返回，界面一个控件都不建。
    if _win_mutex_try() is False:
        try:
            c = socket.create_connection(("127.0.0.1", _SINGLE_PORT), timeout=1)
            c.sendall(b"show")
            c.close()
        except Exception:
            pass
        return
    _probe, _early_srv = _probe_existing_instance()
    if _probe == "exists":
        return

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
    _srv, _serve = _single_instance_register(_show_existing, root, _early_srv)
    if _srv is None:
        root.destroy()
        return
    _diag("单实例注册完成（后台线程监听）")
    root.after(300, _serve)
    root.after(1500, _ensure_desktop_shortcut)

    # v1.9.9.20：启动系统托盘（关窗口后进程常驻，提醒不丢）。
    # 非 Windows / 初始化失败会自动降级成 no-op，✕ 仍是直接退出。
    def _start_tray():
        try:
            import tray as _tray_mod
            t = _tray_mod.Tray(app)
            if t.start():
                app._tray = t
                app._tray_failed = False
                app._tray.update_tip(app.app_name())
            else:
                # 非 Windows 或初始化失败：明确标记，✕ 才允许直接退出
                app._tray = t
                app._tray_failed = True
        except Exception as exc:
            app._tray = None
            app._tray_failed = True
            try:
                app.diag("[tray] 托盘启动失败：%r" % (exc,))
            except Exception:
                pass
    root.after(800, _start_tray)

    def tick():
        # 截止时间提醒
        try:
            app.check_reminders()
        except Exception:
            pass
        # v1.9.9.45：保存失败要持续可见（磁盘满 / 文件被占用）
        try:
            app._check_save_error()
        except Exception:
            pass
        # 每分钟检查跨天
        if dt.date.today().isoformat() != app.store.today:
            app.store.sync_history()            # 先把昨天归档
            app.store.today = dt.date.today().isoformat()
            app.store._roll_day(app.store.today)
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
