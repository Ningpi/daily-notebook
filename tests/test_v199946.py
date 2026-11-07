# -*- coding: utf-8 -*-
"""v1.9.9.46：真人实测 15 项问题的回归测试。

  1/9  互动提示独占一行（不再叠在底栏按钮上）
  2    小技巧改编号、含日常任务建法、无「背单词打卡」
  3    「B，没有」→ 优先级 + 不设时间，不再建出叫【没有】的任务
  4    底栏计数拆两段双色；组头「今日完成 x/y」删除
  5    主列表只显示今天的日常；「日常」管理窗列出全部日常
  6    日历日常标记统一圆点（◆ → ●）
  8    便签空态有提示 + 记一条按钮
  10   窗口缩放保持聊天:列表比例
  11   查列表认「未完成 / 还有什么没完成」
  12   便签回复带内容
  14   聊天气泡行高随字体
  15   进度条 / 气泡只算今天的事
"""
import datetime as dt

import pytest

tk = pytest.importorskip("tkinter")

import main as M
import i18n


@pytest.fixture
def app(tmp_path, monkeypatch):
    """真实 NoteApp 实例（与 test_gui_flow 同款，数据目录隔离）"""
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
    a._cards = []
    a.show_due_card = lambda task: a._cards.append(task.get("title"))
    yield a
    try:
        root.destroy()
    except Exception:
        pass


def _daily_task(a, title, hhmm="08:00", kind="daily", weekday=None, done=False):
    return {"id": "d_" + title, "title": title, "hhmm": hhmm,
            "repeat": {"kind": kind, "weekday": weekday,
                       "weekdays": [weekday] if weekday is not None else None,
                       "monthday": None},
            "day": a.store._today(), "due_date": None, "done": done,
            "score": 20, "manual": False, "created": "09:00"}


def _tmp_task(a, title, done=False, score=50):
    return {"id": "t_" + title, "title": title, "hhmm": None, "repeat": None,
            "day": a.store._today(), "due_date": None, "done": done,
            "score": score, "manual": True, "created": "09:00"}


# ------------------------------------------------------------------ 问题 5/15
class TestTodayOnly:
    def test_main_list_hides_nontoday_daily(self, app):
        """主列表：非今天的日常不再出现（去日常管理窗看）"""
        a = app
        a.store.tasks = [
            _daily_task(a, "背单词"),
            _daily_task(a, "背历史书", kind="weekly",
                        weekday=(dt.date.today().weekday() + 1) % 7),
            _tmp_task(a, "买牛奶"),
        ]
        groups = dict(a.list_groups())
        daily_titles = [t["title"] for _i, t in groups.get("daily", [])]
        assert daily_titles == ["背单词"], daily_titles
        assert "背历史书" not in daily_titles

    def test_progress_excludes_nontoday_daily(self, app):
        """进度条只算今天的事——每周一的任务不进分母"""
        a = app
        a.store.tasks = [
            _daily_task(a, "背单词", done=True),
            _daily_task(a, "背历史书", kind="weekly",
                        weekday=(dt.date.today().weekday() + 1) % 7),
            _tmp_task(a, "买牛奶"),
        ]
        done, total, _ratio = a.progress_state()
        assert (done, total) == (1, 2), (done, total)

    def test_list_report_today_only(self, app):
        """「未完成」播报不含非今天的日常"""
        a = app
        a.store.tasks = [
            _daily_task(a, "背历史书", kind="weekly",
                        weekday=(dt.date.today().weekday() + 1) % 7),
            _tmp_task(a, "买牛奶"),
        ]
        r = a._list_report()
        assert "背历史书" not in r, r
        assert "买牛奶" in r, r

    def test_bubble_today_only(self, app):
        """气泡只数今天的事"""
        a = app
        a.store.tasks = [
            _daily_task(a, "背历史书", kind="weekly",
                        weekday=(dt.date.today().weekday() + 1) % 7),
            _tmp_task(a, "买牛奶"),
        ]
        a._ensure_bubble()
        if a._bubble is None:
            try:
                M.Bubble(a)
            except Exception as _e:      # pragma: no cover
                pytest.fail("Bubble 创建失败: %r" % (_e,))
            pytest.fail("bubble_enabled 被关了？")
        titles = [t["title"] for t in a._bubble._undone()]
        assert titles == ["买牛奶"], titles

    def test_nontoday_daily_manager_visible(self, app):
        """日常管理窗列出**全部**日常（含非今天的）"""
        a = app
        a.store.tasks = [
            _daily_task(a, "背单词"),
            _daily_task(a, "背历史书", kind="weekly",
                        weekday=(dt.date.today().weekday() + 1) % 7),
        ]
        a.open_daily_manager()
        win = a._dmgr_win
        assert win.winfo_exists()
        a._render_daily_manager()
        texts = [a._dmgr_cv.itemcget(it, "text")
                 for it in a._dmgr_cv.find_all()
                 if a._dmgr_cv.type(it) == "text"]
        joined = " ".join(texts)
        assert "背单词" in joined and "背历史书" in joined, joined
        win.destroy()


# ------------------------------------------------------------------ 问题 3
class TestCombinedAnswer:
    def _ask(self, a):
        r = a.respond("语文")
        assert "优先级" in r, r
        return r

    def test_b_no_means_priority_and_no_deadline(self, app):
        """「B，没有」= 重要 + 不设时间；不建叫【没有】的任务"""
        a = app
        a.store.setup_stage = 3
        a.store.user_name = "小李"
        a.store.bot_name = "小记"
        a.store.tasks = []
        self._ask(a)
        r = a.respond("B，没有")
        titles = [t["title"] for t in a.store.tasks]
        assert "没有" not in titles, (titles, r)
        assert len(a.store.tasks) == 1
        t = a.store.tasks[0]
        assert t["score"] == 70, t
        assert not t.get("hhmm") and not t.get("due_date"), t
        assert a._pending_task is None and a._pending_q is None

    def test_b_time_still_works(self, app):
        """「B 晚上8点」= 重要 + 设时间（旧能力不回退）"""
        a = app
        a.store.setup_stage = 3
        a.store.user_name = "小李"
        a.store.bot_name = "小记"
        a.store.tasks = []
        self._ask(a)
        a.respond("B 明天晚上8点")
        t = a.store.tasks[0]
        assert t["score"] == 70 and t.get("hhmm") == "20:00", t
        assert t.get("due_date") != a.store._today(), t


# ------------------------------------------------------------------ 问题 11
def test_list_query_new_words(app):
    """查列表认「未完成 / 还有什么没完成」，旧词「列表」仍兼容"""
    a = app
    for phrase in ("未完成", "我没完成的", "我还有什么任务没完成",
                   "现在有什么没做的", "列表", "我的任务"):
        assert a._is_list_query(phrase), phrase


# ------------------------------------------------------------------ 问题 1/9
def test_hint_has_own_row(app):
    """互动提示独占一行，不再是叠在底栏上的 place 浮层"""
    a = app
    assert a.f_hint.master is a.hint_row
    assert not a.f_hint.place_info().get("relx")      # 不再用 place
    a.flash("测试提示")
    a.root.update()
    assert a.f_hint.cget("text") == "测试提示"


# ------------------------------------------------------------------ 问题 4
def test_group_head_no_progress_text(app):
    """日常组头不再写「今日完成 x/y」"""
    a = app
    a.store.tasks = [_daily_task(a, "背单词")]
    a.refresh_tasks()
    texts = [a.list_cv.itemcget(it, "text")
             for it in a.list_cv.find_all() if a.list_cv.type(it) == "text"]
    assert not any("今日完成" in t for t in texts), texts


def test_counter_two_colors(app):
    """计数两段：日常段青色标签、临时段灰色标签"""
    a = app
    a.store.tasks = [_daily_task(a, "背单词"), _tmp_task(a, "买牛奶")]
    a.refresh_tasks()
    assert a.counter_d.cget("text") == "日常任务 0/1"
    assert "临时任务 0/1" in a.counter.cget("text")


# ------------------------------------------------------------------ 问题 6
def test_calendar_day_mark_circle(app):
    """日历底部当天安排：日常用 ●，不再出现 ◆"""
    a = app
    a.store.tasks = [_daily_task(a, "背历史书")]
    a.open_calendar_view()
    a._cal_show_day(dt.date.today().isoformat())
    txt = a._cal_info.cget("text")
    assert "● 背历史书" in txt, txt
    assert "◆" not in txt, txt
    a._cal_win.destroy()


# ------------------------------------------------------------------ 问题 8
def test_note_empty_state(app):
    """便签空态：提示 + 记一条按钮"""
    a = app
    a.store.notes = []
    a.switch_mode("note")
    texts = [a.list_cv.itemcget(it, "text")
             for it in a.list_cv.find_all() if a.list_cv.type(it) == "text"]
    joined = " ".join(texts)
    assert "还没有便签" in joined, joined
    assert any("记一条" in t for t in texts), texts
    a.switch_mode("task")


# ------------------------------------------------------------------ 问题 12
def test_note_reply_echoes_content(app):
    """便签回复带内容：连贴两条不再是两行一样的「便签已贴好」"""
    a = app
    a.store.notes = []
    a.add_note("去便利店买便利贴")
    last = a.store.messages[-1]
    assert "去便利店买便利贴" in (last.get("zh") or last.get("text") or ""), last


# ------------------------------------------------------------------ 问题 2
def test_usage_guide_rewritten():
    zh = i18n.render("usage_guide", {}, "zh")
    assert "1." in zh and "2." in zh, zh
    assert "背单词打卡" not in zh, zh
    assert "每天" in zh and "撤回" in zh, zh
    for line in zh.splitlines():
        assert len(line) <= 30, "小技巧单行太长会在气泡里换行：" + line


def test_alpha_title_short():
    assert i18n.render("alpha_title", {}, "zh") == "透明度"


# ------------------------------------------------------------------ 问题 10
def test_resize_keeps_ratio(app):
    """缩放窗口后聊天区高度按比例跟随"""
    a = app
    a.root.update_idletasks()
    a.root.update()
    ch = a.chat_cv.winfo_height()
    lh = a.list_cv.winfo_height()
    if ch <= 1 or lh <= 1:
        pytest.skip("布局未就绪")
    a._split_ratio = 0.5
    h0 = a.root.winfo_height()
    a.root.geometry("430x%d" % (h0 + 120))
    a.root.update_idletasks()
    a.root.update()
    a._ratio_root_h = 0            # 强制重算（模拟高度已变）
    a._apply_split_ratio()
    a.root.update_idletasks()
    a.root.update()
    ch2 = a.chat_cv.winfo_height()
    lh2 = a.list_cv.winfo_height()
    assert abs(ch2 - round(0.5 * (ch2 + lh2))) <= 3, (ch2, lh2)


# ------------------------------------------------------------------ 问题 14
def test_chat_line_height_follows_font(app):
    """大字体下聊天气泡行高跟着涨，不再叠出边框"""
    a = app
    a.store.font_scale = 1.3
    a._build_fonts()
    a.render_messages()
    small = a.store.font_scale = 0.8
    a._build_fonts()
    a.render_messages()
    a.store.font_scale = 1.0
    a._build_fonts()
    a.render_messages()
    # 行高由内部计算，这里只验证三种字号下渲染都不抛异常、消息已画出
    assert a.chat_cv.find_all(), "聊天区没画出来"
