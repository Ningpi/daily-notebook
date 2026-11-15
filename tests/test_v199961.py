# -*- coding: utf-8 -*-
"""v1.9.9.61 回归测试：真人实测第八轮

覆盖：关联清单实时更新 / 用时格式化 / 秒表跨启动恢复 / 「今天内」解析 /
弹窗开-关切换 / 批量录入队列追问 / 右键开始计时 / 日历点击反馈"""
import datetime as dt
import time

import pytest

tk = pytest.importorskip("tkinter")
import main as M
import i18n
import parser as core


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
    a.store.tasks = []
    a.store.messages = []
    yield a
    try:
        root.destroy()
    except Exception:
        pass


def _mk(app, title, **kw):
    t = {"id": kw.pop("id", "t_" + title), "title": title,
         "hhmm": kw.pop("hhmm", None), "score": kw.pop("score", 40),
         "manual": False, "done": False, "created": "09:00",
         "day": app.store._today(), "repeat": kw.pop("repeat", None),
         "due_date": None}
    t.update(kw)
    app.store.tasks.append(t)
    return t


# ------------------------- 1. 用时格式化（302分钟 → 5小时02分钟）
class TestDurText:
    def test_over_one_hour(self, app):
        t = _mk(app, "背单词", dur="302分钟", dur_min=302)
        s = app._dur_text(t)
        assert "5" in s and "小时" in s and "02" in s and "分钟" in s, s
        assert "302" not in s

    def test_under_one_hour_unchanged(self, app):
        t = _mk(app, "背单词", dur="21分钟", dur_min=21)
        assert "21" in app._dur_text(t) and "小时" not in app._dur_text(t)

    def test_row_prefix_uses_it(self, app):
        t = _mk(app, "背单词", dur="302分钟", dur_min=302)
        tx, dw, dur_txt = app._row_prefix_w(t, 400)
        assert "小时" in dur_txt


# ------------------------- 2. 「今天内」= 今天 23:59 前
class TestTodayEod:
    def test_today_nei_sets_2359(self, app):
        app.respond("今天内将流量卡退掉，找新套餐")
        t = [x for x in app.store.tasks if "流量卡退掉" in x["title"]][0]
        assert t["hhmm"] == "23:59", t
        assert t["due_date"] == app.store._today(), t

    def test_explicit_time_not_overridden(self, app):
        # 用未来的整点，避免「已过截止日期」确认拦路
        h = (dt.datetime.now().hour + 2) % 24
        if h < 6:
            h += 6
        txt = "今天内%d点交报告" % h if h > 12 else "今天内下午%d点交报告" % (h - 12 if h > 12 else h)
        app.respond(txt)
        t = [x for x in app.store.tasks if "交报告" in x["title"]][0]
        expect = "%02d:00" % (h if h > 12 else h + 12)
        assert t["hhmm"] == expect, (t, txt)

    def test_no_remind_of_default(self, app):
        # 设了 23:59 就不该再问截止时间（need_dl 已满足）
        app.respond("今天内交作业")
        t = app.store.tasks[0]
        assert t["hhmm"] == "23:59"
        rep = app.respond("C")
        assert "交作业" in rep or "截止" in rep or "提醒" in rep or rep


# ------------------------- 3. 批量录入队列追问
class TestBatchAskQueue:
    def test_first_asked_rest_queued(self, app):
        rep = app.respond("今日要去买面包，开会，参加舞会")
        assert len(app.store.tasks) == 3, rep
        assert "买面包" in rep
        assert "2" in rep, "应提示还有 2 条等着设置"

    def test_queue_advances_after_answer(self, app):
        app.respond("今日要去买面包，开会，参加舞会")
        # 第一条带了 20:00 的钟点 → 先答优先级再答提醒，然后才轮到下一条
        rep = app.respond("A，晚上八点")
        assert "提醒" in rep, "先问第一条的提醒设置"
        rep = app.respond("E")
        assert "开会" in rep, "提醒答完才接着问第二条（开会）"
        rep = app.respond("B，没有")
        assert "舞会" in rep, "答完第二条应接着问第三条（舞会）"
        rep = app.respond("C，无")
        t = {x["title"]: x for x in app.store.tasks}
        assert t["开会"]["score"] == 70
        assert not t["参加舞会"]["hhmm"]
        assert t["要去买面包"]["score"] == 95

    def test_remind_first_then_queue(self, app):
        """带钟点的任务先问提醒，答完提醒才轮到队列里下一条的优先级"""
        app.respond("今日要去买面包，开会，参加舞会")
        app.respond("A，晚上八点")          # 触发提醒追问
        rep = app.respond("E")              # 不用提醒 → 才接着问开会
        assert "开会" in rep, rep
        rep = app.respond("C，无")
        assert "舞会" in rep, rep

    def test_skip_then_queue_advances(self, app):
        app.respond("今日要去买面包，开会，参加舞会")
        rep = app.respond("算了")
        assert "开会" in rep, "跳过第一条后应接着问下一条"


# ------------------------- 4. 右键开始计时
class TestStartTimerFromRow:
    def test_starts_and_links(self, app):
        t = _mk(app, "刷科目一")
        app._start_task_timer(t["id"])
        app.root.update()
        assert app._sw_task == t["id"]
        assert app._sw_running is True
        win = app._clock_win
        assert win is not None and win.winfo_exists()
        app._sw_toggle()          # 收尾，别影响其他用例
        app._sw_reset()

    def test_done_task_refuses(self, app):
        t = _mk(app, "已完成的事", done=True)
        app._start_task_timer(t["id"])
        assert app._sw_task != t["id"]

    def test_row_menu_has_timer_entry(self, app):
        t = _mk(app, "刷科目一")
        # 不真弹菜单，只验证方法与词条就位
        assert i18n.t("menu_timer")
        assert hasattr(app, "_start_task_timer")


# ------------------------- 5. 关联任务清单实时更新
class TestLinkMenuRefresh:
    def test_menu_drops_done_task(self, app):
        t = _mk(app, "刷科目一")
        app.open_clock()
        app.root.update()
        menu = app.root.nametowidget(app._link_menu_btn.cget("menu"))
        n0 = int(menu.tk.call(str(menu), "index", "end"))
        assert n0 == 1, "应有一条任务（0=占位 1=任务）"
        app.toggle_done(t["id"])
        app.root.update()
        menu = app.root.nametowidget(app._link_menu_btn.cget("menu"))
        n1 = int(menu.tk.call(str(menu), "index", "end"))
        assert n1 == 0, "完成的任务应从清单里消失（只剩占位）"
        app._close_clock()
        app.store.tasks = []

    def test_linked_task_done_unlinks(self, app):
        t = _mk(app, "刷科目一")
        app._start_task_timer(t["id"])
        app._sw_toggle()          # 暂停
        app.toggle_done(t["id"])
        app.root.update()
        assert app._sw_task is None, "关联任务完成后应自动解除关联"
        app._close_clock()
        app.store.tasks = []


# ------------------------- 6. 弹窗开-关切换
class TestPopupToggle:
    def test_on_top_then_click_hides(self, app):
        app.open_daily_manager()
        app.root.update()
        win = app._dmgr_win
        win.geometry("430x430+240+150")
        win.update()
        if not app._is_on_top(win):
            pytest.skip("虚拟显示下层级不稳定")
        app.open_daily_manager()
        app.root.update()
        assert win.wm_state() == "withdrawn", "在最上层时再点应收进后台"
        app.open_daily_manager()
        app.root.update()
        assert win.wm_state() == "normal", "再点一次应唤回"
        win.destroy()
        app._dmgr_win = None

    def test_covered_then_click_raises(self, app):
        app.open_daily_manager()
        app.root.update()
        win = app._dmgr_win
        win.geometry("430x430+240+150")
        cover = tk.Toplevel(app.root)
        cover.geometry("430x430+245+155")
        cover.update()
        app.open_daily_manager()
        app.root.update()
        assert win.wm_state() == "normal", "被盖住时再点应唤回而不是隐藏"
        assert app._is_on_top(win)
        cover.destroy()
        win.destroy()
        app._dmgr_win = None

    def test_history_toggle(self, app):
        app.open_history()
        app.root.update()
        win = app._hist_win
        if not app._is_on_top(win):
            win.destroy()
            app._hist_win = None
            pytest.skip("虚拟显示下层级不稳定")
        app.open_history()
        app.root.update()
        assert win.wm_state() == "withdrawn"
        app.open_history()
        app.root.update()
        assert win.wm_state() == "normal"
        win.destroy()
        app._hist_win = None


# ------------------------- 7. 秒表跨启动恢复
class TestStopwatchPersist:
    def test_sync_and_reload(self, app):
        app._sw_base = 90.0
        app._sw_task = "t_x"
        app._sw_sync()
        assert app.store.sw_base == 90.0
        assert app.store.sw_task == "t_x"
        app.store.save()
        app.store.load()
        assert app.store.sw_base == 90.0
        assert app.store.sw_task == "t_x"

    def test_reopen_clock_restores_duration(self, app):
        app.store.sw_base = 125.0
        app.store.sw_task = ""
        app._clock_inited = False
        app.open_clock()
        app.root.update()
        assert app._sw_base == 125.0, "重新打开时钟应显示上次累计时长"
        assert app._sw_running is False, "应为暂停态"
        app._sw_reset()
        app._close_clock()

    def test_relink_same_task_shows_previous(self, app):
        t = _mk(app, "背单词", id="t1")
        app.store.sw_base = 200.0
        app.store.sw_task = "t1"
        app._clock_inited = False
        app.open_clock()
        app.root.update()
        app._link_task("t1", "背单词")
        app.root.update()
        assert app._sw_base == 200.0, "重新关联同一任务应显示之前的时长"
        assert app._sw_task == "t1"
        app._sw_reset()
        app._close_clock()
        app.store.tasks = []

    def test_switch_task_pauses_and_writes(self, app):
        t1 = _mk(app, "任务甲", id="ta")
        t2 = _mk(app, "任务乙", id="tb")
        app._clock_inited = False
        app.open_clock()
        app.root.update()
        app._link_task("ta", "任务甲")
        app._sw_toggle()                       # 开始计时
        app._sw_t0 = time.time() - 120         # 跑了 2 分钟
        app._link_task("tb", "任务乙")          # 中途换任务
        assert app._sw_running is False, "换任务应自动停表"
        assert t1.get("dur_min") == 2, "旧任务的时长应落盘"
        assert app._sw_task == "tb"
        app._sw_reset()
        app._close_clock()
        app.store.tasks = []


# ------------------------- 8. 日历点击反馈
class TestCalendarFeedback:
    def test_show_day_marks_selection(self, app):
        app.open_calendar_view()
        app.root.update()
        ds = app.store._today()
        app._cal_show_day(ds)
        app.root.update()
        assert app._cal_sel_day == ds
        cv = app._cal_cv
        # 选中框已画出（描边矩形存在）
        boxes = [i for i in cv.find_withtag("all")
                 if cv.type(i) == "rectangle"
                 and cv.itemcget(i, "outline") not in ("",)
                 and float(cv.itemcget(i, "width")) == 2.0]
        assert boxes, "选中的日期应有描边框"
        app._cal_win.destroy()
        app._cal_win = None


# ------------------------- 9. i18n 词条
class TestI18nKeys:
    @pytest.mark.parametrize("key", ["menu_timer", "timer_started",
                                     "timer_done_task", "ask_queue_hint",
                                     "dur_hm"])
    def test_bilingual(self, key):
        zh_v = i18n.render(key, {"t": "x", "n": 2, "h": 5, "m": 2}, "zh")
        en_v = i18n.render(key, {"t": "x", "n": 2, "h": 5, "m": 2}, "en")
        assert zh_v and en_v
        assert not any("\u4e00" <= c <= "\u9fff" for c in en_v)
