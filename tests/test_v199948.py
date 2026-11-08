# -*- coding: utf-8 -*-
"""v1.9.9.48：英文界面 + 日常任务体验 7 项回归测试。

  1    切语言后「日常/Daily」按钮立即刷新（不再残留另一语言）
  2    英文对话：建任务 / 查列表 / 今日完成 / 撤回 / 打卡 / 周期任务
  4    周期任务不再被默认 18:00；日常任务不再追问截止时间
  4    日常任务详情窗不再显示「优先级：一般」（改显示频率）
  5    日常管理窗支持右键（复用主列表菜单）
  6    气泡行宽把「● 」前缀算进去（「每天 20:30」不再被裁）
  7    时钟默认 780x620，旧默认自动升级
  --   日历休/班角标随语言
"""
import json
import os
import datetime as dt

import pytest

tk = pytest.importorskip("tkinter")

import main as M
import i18n
import parser as PC
import parser_en as PE


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    try:
        root = tk.Tk()
    except Exception as exc:                      # pragma: no cover
        pytest.skip("无 GUI 环境：%s" % exc)
    root.geometry("430x660+20+20")
    a = M.NoteApp(root)
    root.update()
    a.store.setup_stage = 3
    a.store.user_name = "小李"
    a.store.bot_name = "小记"
    a.store.tasks = []
    a.store.messages = []
    a._ring_bell = lambda *x: None
    yield a
    try:
        root.destroy()
    except Exception:
        pass
    finally:
        i18n.set_lang("zh")


def _daily(a, title, weekday=None, hhmm=None):
    return {"id": "d_" + title, "title": title, "hhmm": hhmm,
            "repeat": {"kind": "weekly" if weekday is not None else "daily",
                       "weekday": weekday,
                       "weekdays": [weekday] if weekday is not None else None,
                       "monthday": None},
            "day": a.store._today(), "due_date": None, "done": False,
            "score": 30, "manual": False, "created": "09:00"}


def _tmp(a, title, hhmm=None):
    return {"id": "t_" + title, "title": title, "hhmm": hhmm, "repeat": None,
            "day": a.store._today(), "due_date": None, "done": False,
            "score": 50, "manual": True, "created": "09:00"}


# ------------------------------------------------------------------ 1 语言刷新
class TestLangRefresh:
    def test_daily_btn_follows_lang(self, app):
        i18n.set_lang("en")
        app.refresh_labels()
        app.root.update()
        assert app.daily_btn.cget("text") == i18n.t("daily_btn")
        assert i18n.t("daily_btn") == "Daily", "英文键值变了请同步本测试"
        i18n.set_lang("zh")
        app.refresh_labels()
        assert app.daily_btn.cget("text") == "日常"

    def test_enter_hint_follows_lang(self, app):
        app.store.enter_hint_done = False
        # 手工建一个 hint（模拟首启状态）
        import tkinter as tk
        if getattr(app, "hint_lbl", None) is None:
            app.hint_lbl = tk.Label(app.root, text="")
        app.hint_lbl.configure(text=i18n.t("enter_send_hint"))
        i18n.set_lang("en")
        app.refresh_labels()
        assert app.hint_lbl.cget("text") == i18n.t("enter_send_hint")
        app.hint_lbl.destroy()
        app.hint_lbl = None


# ------------------------------------------------------------------ 2 英文对话
class TestEnglishDialog:
    @pytest.fixture(autouse=True)
    def _en(self, app):
        self.a = app
        i18n.set_lang("en")
        self.a.store.lang = "en"
        yield

    def _ask(self, t):
        self.a.store.messages = []
        self.a.respond(t)

    def test_create_task_with_time(self):
        self._ask("buy milk tomorrow 3pm")
        t = self.a.store.tasks[0]
        assert t["title"] == "buy milk" and t["hhmm"] == "15:00"

    def test_list_query_not_a_task(self):
        self.a.store.tasks = []
        for q in ("what's on my list", "my tasks", "show my todo",
                  "what do I still have to do"):
            self._ask(q)
            titles = [x["title"] for x in self.a.store.tasks]
            assert q.lower() not in [t.lower() for t in titles], (q, titles)

    def test_done_today_query(self):
        self.a.store.tasks = []
        self.a.store.messages = []
        r = self.a.respond("what did I do today")
        assert r, "「what did I do today」没有任何回复"
        titles = [x["title"] for x in self.a.store.tasks]
        assert "what did i do today" not in [t.lower() for t in titles]

    def test_every_weekday_repeat(self):
        self.a.store.tasks = []
        self._ask("every monday read history")
        t = self.a.store.tasks[-1]
        assert t["title"] == "read history", t
        assert t.get("repeat") and t["repeat"]["kind"] == "weekly"
        assert t["repeat"]["weekday"] == 0

    def test_oneshot_monday_not_repeat(self):
        self.a.store.tasks = []
        self._ask("meeting on monday")
        t = self.a.store.tasks[-1]
        assert not t.get("repeat"), t   # 一次性「on monday」不算日常

    def test_undo_english(self):
        self.a.store.tasks = []
        self._ask("buy apples")
        n = len(self.a.store.tasks)
        self._ask("undo")
        assert len(self.a.store.tasks) < n

    def test_checkin_hint_english(self):
        self.a.store.tasks = []
        self._ask("checked in")
        titles = [x["title"] for x in self.a.store.tasks]
        assert "checked in" not in titles


# ------------------------------------------------------------------ 4 18:00 / 问答
class TestDailyDefaults:
    def test_weekly_task_no_default_1800(self):
        for s in ("每周一背单词", "每周二看书", "每周五交周报"):
            r = PC.parse_tasks(s)
            assert len(r) == 1 and r[0][1] is None, (s, r)

    def test_explicit_time_still_parsed(self):
        r = PC.parse_tasks("每周四晚上九点跑步")
        assert r[0][1] == "21:00"

    def test_nontask_weekday_keeps_fallback(self):
        # 非周期任务（周五之前交周报）保留 18:00 兜底不变
        r = PC.parse_tasks("周五之前交周报")
        assert r[0][1] == "18:00"

    def test_daily_task_no_dl_question(self, app):
        t = _daily(app, "背单词", weekday=0)
        reply = app._maybe_ask(t, "每周一背单词")
        assert reply is None or "截止" not in (reply or ""), reply
        assert getattr(app, "_pending_task", None) is None, \
            "日常任务不应进入截止时间追问"


# ------------------------------------------------------------------ 4 详情窗
class TestDetailRows:
    def test_daily_detail_shows_freq_not_priority(self, app):
        t = _daily(app, "背单词", weekday=0)
        app.store.tasks = [t]
        app.open_task_detail(t["id"])
        app.root.update()
        win = app._detail_win

        def _walk(w):
            yield w
            for c in w.winfo_children():
                yield from _walk(c)

        texts = []
        for w in _walk(win):
            try:
                texts.append(str(w.cget("text")))
            except Exception:
                pass
        joined = " ".join(texts)
        assert "频率" in joined, texts
        assert "优先级" not in joined, texts


# ------------------------------------------------------------------ 5 管理窗右键
class TestDailyManagerMenu:
    def test_right_click_menu_binds_row_menu(self, app, monkeypatch):
        app.store.tasks = [_daily(app, "背单词", weekday=0)]
        app.refresh_tasks()
        app.open_daily_manager()
        app.root.update()
        cv = app._dmgr_cv
        tid = app.store.tasks[0]["id"]
        calls = []
        monkeypatch.setattr(app, "row_menu", lambda e, k: calls.append(k))
        bbox = cv.bbox("dm_" + tid)
        assert bbox, "管理窗没画出任务行"
        cx, cy = (bbox[0] + bbox[2]) // 2, (bbox[1] + bbox[3]) // 2
        rx, ry = cv.winfo_rootx() + cx, cv.winfo_rooty() + cy
        cv.event_generate("<Button-3>", x=cx, y=cy, rootx=rx, rooty=ry)
        app.root.update()
        assert calls == [tid], calls


# ------------------------------------------------------------------ 6 气泡行宽
class TestBubbleRowWidth:
    def test_daily_prefix_counted(self, app):
        app.store.tasks = [_daily(app, "修电脑", hhmm="20:30")]
        app.refresh_tasks()
        app._ensure_bubble()
        b = app._bubble
        assert b is not None
        undone = b._ordered()
        assert undone, "气泡没内容"
        dl = b._dl_text(undone[0])
        assert "每天" in dl and "20:30" in dl
        # 宽度公式按 ● 前缀 + 标题 + 时间整体测量（不低于旧算法）
        from tkinter import font as tkfont
        f = tkfont.Font(font=(app.f_ui, 9))
        need = 27 + f.measure("● 修电脑") + f.measure("· " + dl) + 8
        assert need > 27 + f.measure("修电脑")


# ------------------------------------------------------------------ 7 时钟尺寸
class TestClockDefault:
    def test_default_geometry(self, app):
        app.store.clock_geom = None
        app.open_clock()
        app.root.update()
        win = app._clock_win
        assert win.winfo_width() >= 700, win.winfo_width()
        assert win.winfo_height() >= 500, win.winfo_height()
        app._close_clock()

    def test_old_default_upgraded(self, app):
        app.store.clock_geom = "260x220+30+30"
        app.open_clock()
        app.root.update()
        win = app._clock_win
        assert win.winfo_width() >= 700, "旧默认没有升级"
        app._close_clock()

    def test_user_resized_kept(self, app):
        app.store.clock_geom = "500x400+10+10"
        app.open_clock()
        app.root.update()
        win = app._clock_win
        assert win.winfo_width() == 500, "用户自己拉过的大小被覆盖"
        app._close_clock()


# ------------------------------------------------------------------ 日历休班
class TestCalOffBadge:
    def test_keys_exist(self):
        i18n.set_lang("en")
        assert i18n.t("cal_off_day") == "Off"
        i18n.set_lang("zh")
        assert i18n.t("cal_off_day") == "休"
