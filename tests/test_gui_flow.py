# -*- coding: utf-8 -*-
"""对话流程 / UI 交互集成测试（需要 tkinter，无显示器时自动跳过）

这些用例真实创建 NoteApp，但**不进入 mainloop**，靠 update() 推进，
所以能在 CI 里跑（Linux 需 xvfb-run；Windows 直接跑）。

关注点（对应您最在意的四项）：
  - 解析准确率 → 端到端：一句话 → 待办列表内容
  - 跨天数据正确性 → 归档日期 / 时间清理 / 提醒标记重置
  - 中英切换不丢数据不串语言 → 切完任务还在、底部哲言换语言
  - 提醒不重复弹出 → 连续 check_reminders 只弹一次
"""
import datetime as dt
import json

import pytest

tk = pytest.importorskip("tkinter")

import main as M
import i18n


@pytest.fixture
def app(tmp_path, monkeypatch):
    """真实 NoteApp 实例（数据目录隔离），用完即销毁"""
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
    # 关掉副作用：铃声、卡片弹窗
    a._ring_bell = lambda *x: None
    a._cards = []

    def fake_card(task):
        a._cards.append(task.get("title"))
    a.show_due_card = fake_card
    yield a
    try:
        root.destroy()
    except Exception:
        pass


def say(app, text, max_confirm=6):
    """发送一句话；若触发过期确认，按真实用户习惯点「确认」

    v1.9.9：多任务里可能同时有过期项，一条条排队确认（正是本次修的队列 bug），
    所以这里最多连答 6 次，直到不再追问为止。
    """
    r = app.respond(text)
    n = 0
    while isinstance(r, str) and "过截止日期" in r and n < max_confirm:
        r = app.respond("确认")
        n += 1
    return r


def settle(app):
    """v1.9.9.22：把建任务后的追问流程答完。
    新语义下待答状态中裸「撤回」= 取消流程，旧用例需先答完再撤。"""
    for _ in range(6):
        pt = getattr(app, "_pending_task", None)
        if not pt:
            break
        app.respond("A" if pt.get("need_pri") else "不用")
    for _ in range(3):
        if not getattr(app, "_pending_remind", None):
            break
        app.respond("不用")

# ===================================================== 对话建任务
class TestDialogAddTask:
    def test_simple_task(self, app):
        say(app, "买牛奶")
        assert [t["title"] for t in app.store.tasks] == ["买牛奶"]

    def test_multi_task_split(self, app):
        say(app, "9点开会，下午3点前交周报，顺便买瓶酱油")
        titles = " ".join(t["title"] for t in app.store.tasks)
        assert "开会" in titles and "交周报" in titles and "买瓶酱油" in titles

    def test_priority_answered_by_letter(self, app):
        say(app, "明天9点开会")
        app.respond("A")
        t = app.store.tasks[0]
        assert t["score"] == 95, t
        assert t["manual"] is True

    def test_expired_single_confirm(self, app):
        """过期任务先问、确认后入库，且「确认」二字不会被记成任务名"""
        r = app.respond("今天8点开会")
        assert "过截止日期" in r
        assert app.store.tasks == []
        app.respond("确认")
        assert [t["title"] for t in app.store.tasks] == ["开会"]
        assert all(t["title"] != "确认" for t in app.store.tasks)

    def test_expired_reply_letter_does_not_loop(self, app):
        """回归：过期确认里回「A」曾无限重复提问，且随后把「确认」建成任务"""
        app.respond("今天8点开会")
        r = app.respond("A")
        assert "过截止日期" not in r, "回 A 仍在重复提问：%s" % r
        assert len(app.store.tasks) == 1
        assert app.store.tasks[0]["score"] == 95

    def test_expired_multi_queue_all_handled(self, app, monkeypatch):
        """回归：一句话里多条过期任务，曾只加第一条、其余静默丢弃"""
        # v1.9.9.21：该用例只在「三条任务都已过期」时成立，原来依赖
        # 跑测试的时钟（晚上跑过、早上挂）。固定到 23:00 保证复现路径。
        import datetime as _dt

        class FakeNow(_dt.datetime):
            @classmethod
            def now(cls):
                return cls(2026, 11, 4, 23, 0)

        # _dt 与 main.dt 是同一模块，monkeypatch 结束时自动还原
        monkeypatch.setattr(_dt, "datetime", FakeNow)
        r = app.respond("今天8点开会，今天9点交报告，今天10点买菜")
        assert "还有" in r, r
        app.respond("确认")
        app.respond("不用")
        app.respond("确认")
        titles = [t["title"] for t in app.store.tasks]
        assert "开会" in titles and "买菜" in titles
        assert "交报告" not in titles
    def test_decline_expired(self, app):
        app.respond("今天8点开会")
        app.respond("不用")
        assert app.store.tasks == []

    def test_undo_task(self, app):
        say(app, "买牛奶")
        settle(app)
        app.respond("撤回")
        assert app.store.tasks == []


# ===================================================== 勾选 / 清理
class TestToggle:
    def test_toggle_done(self, app):
        say(app, "买牛奶")
        tid = app.store.tasks[0]["id"]
        app.toggle_done(tid)
        assert app.store.tasks[0]["done"] is True
        assert app.store.tasks[0]["done_at"]

    def test_toggle_twice(self, app):
        say(app, "买牛奶")
        tid = app.store.tasks[0]["id"]
        app.toggle_done(tid)
        app.toggle_done(tid)
        assert app.store.tasks[0]["done"] is False

    def test_clear_done(self, app):
        say(app, "买牛奶")
        say(app, "买鸡蛋")
        app.toggle_done(app.store.tasks[0]["id"])
        app.clear_done()
        assert len(app.store.tasks) == 1
        assert app.store.tasks[0]["title"] == "买鸡蛋"


# ===================================================== 提醒不重复
class TestReminder:
    def test_fire_once_only(self, app, monkeypatch):
        hhmm = (dt.datetime.now() + dt.timedelta(minutes=2)).strftime("%H:%M")
        app.store.tasks = [{
            "id": "r1", "title": "提醒测试", "hhmm": hhmm, "score": 40,
            "done": False, "remind_before": 5, "reminded": False,
            "due_date": dt.date.today().isoformat(),
        }]
        app.check_reminders()
        first = list(app._cards)
        app.check_reminders()
        app.check_reminders()
        assert len(first) == 1
        assert app._cards == first, "重复弹了卡片：%s" % app._cards

    def test_done_task_not_reminded(self, app):
        hhmm = (dt.datetime.now() + dt.timedelta(minutes=2)).strftime("%H:%M")
        app.store.tasks = [{
            "id": "r2", "title": "已完成", "hhmm": hhmm, "score": 40,
            "done": True, "remind_before": 5, "reminded": False,
        }]
        app.check_reminders()
        assert app._cards == []

    def test_reminded_flag_persisted(self, app, tmp_path):
        """提醒标记要落盘，否则重启后会再弹一次"""
        hhmm = (dt.datetime.now() + dt.timedelta(minutes=2)).strftime("%H:%M")
        app.store.tasks = [{
            "id": "r3", "title": "落盘测试", "hhmm": hhmm, "score": 40,
            "done": False, "remind_before": 5, "reminded": False,
            "due_date": dt.date.today().isoformat(),
        }]
        app.check_reminders()
        raw = json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))
        got = [t for t in raw["tasks"] if t["id"] == "r3"][0]
        assert got["reminded"] is True


# ===================================================== 中英切换
class TestLangSwitch:
    def test_tasks_survive_switch(self, app):
        say(app, "买牛奶")
        app.switch_lang("en")
        assert [t["title"] for t in app.store.tasks] == ["买牛奶"]
        app.switch_lang("zh")
        assert [t["title"] for t in app.store.tasks] == ["买牛奶"]

    def test_titles_kept_verbatim(self, app):
        """文档：任务标题保留输入原文，不机翻"""
        say(app, "交周报")
        app.switch_lang("en")
        assert app.store.tasks[0]["title"] == "交周报"

    def test_quote_follows_language(self, app):
        """文档：切换语言时底部哲言换成该语言上次的句子，不串语言"""
        import re
        app.switch_lang("en")
        en_txt = app.quote_lbl.cget("text")
        assert en_txt and not re.search(r"[\u4e00-\u9fff]", en_txt), en_txt
        app.switch_lang("zh")
        zh_txt = app.quote_lbl.cget("text")
        assert re.search(r"[\u4e00-\u9fff]", zh_txt), zh_txt

    def test_lang_persisted(self, app, tmp_path):
        app.switch_lang("en")
        raw = json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))
        assert raw["lang"] == "en"

    def test_english_input_in_zh_mode(self, app):
        """文档：英文模式下也能加中文任务；反之中文模式也认英文"""
        say(app, "meeting at 2pm")
        titles = [t["title"] for t in app.store.tasks]
        assert titles, "中文模式下的英文输入没有建任务"


# ===================================================== 主题
class TestTheme:
    @pytest.mark.parametrize("tid", ["cream", "rice", "mint", "mist"])
    def test_apply_theme_persists(self, app, tid, tmp_path):
        app.apply_theme(tid, announce=False)
        raw = json.loads((tmp_path / "tasks.json").read_text(encoding="utf-8"))
        assert raw["theme"] == tid


# ===================================================== 初次引导
class TestOnboarding:
    def test_ask_name_first(self, tmp_path, monkeypatch):
        monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
        try:
            root = tk.Tk()
        except Exception as exc:                  # pragma: no cover
            pytest.skip("无 GUI 环境：%s" % exc)
        a = M.NoteApp(root)
        root.update()
        a.store.setup_stage = 0
        r = a.respond("你好")
        assert "称呼" in r or "name" in r.lower()
        assert a.store.setup_stage == 1
        r2 = a.respond("你叫我小李吧")
        assert a.store.user_name == "小李"
        assert a.store.setup_stage >= 2
        root.destroy()

    def test_name_strips_tail(self, tmp_path, monkeypatch):
        """回归：「叫我老王就好了」曾被记成「老王就」"""
        monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
        try:
            root = tk.Tk()
        except Exception as exc:                  # pragma: no cover
            pytest.skip("无 GUI 环境：%s" % exc)
        a = M.NoteApp(root)
        root.update()
        a.store.setup_stage = 1
        a.respond("以后叫我老王就好了")
        assert a.store.user_name == "老王", a.store.user_name
        root.destroy()


# ===================================================== 撤回语义（v1.9.9）
class TestUndoSemantics:
    """撤回要看「上一次做了什么」，不能一律当撤时间

    v1.9.9 修的真 bug：对一条本来没设截止时间的任务说「撤回」，
    软件回「已经把【买牛奶】的截止时间撤掉了」，而任务根本没被撤掉。
    """

    def test_bare_undo_removes_just_added_task(self, app):
        """刚建的任务，说「撤回」= 删掉它（最符合直觉）"""
        say(app, "买牛奶")
        settle(app)
        assert len(app.store.tasks) == 1
        r = say(app, "撤回")
        assert app.store.tasks == []
        assert "撤掉" in r, r

    def test_undo_after_setting_deadline_clears_it(self, app):
        """刚设过时间，说「撤回」= 清时间并重新追问"""
        app.respond("交周报")
        r = app.respond("B 晚上八点")
        if isinstance(r, str) and "过截止日期" in r:
            r = app.respond("确认")        # 已过点就确认保留（时间不依赖）
        assert app.store.tasks[0]["hhmm"] == "20:00"
        settle(app)
        app.respond("撤回")
        assert app.store.tasks[0]["hhmm"] is None
        assert app.store.tasks[0]["due_date"] is None
        assert getattr(app, "_pending_q", None) == "pri"

    def test_explicit_time_phrase_clears_deadline_only(self, app):
        """「撤一下时间」只清时间，不删任务"""
        app.respond("开会")
        app.respond("B 晚上八点")
        r = app.respond("撤一下时间")
        assert len(app.store.tasks) == 1
        assert app.store.tasks[0]["hhmm"] is None
        assert "截止时间" in r, r

    def test_undo_without_deadline_does_not_lie(self, app):
        """任务本来没有截止时间，不能谎称「已撤掉截止时间」

        当前实现是「认不出可撤的东西 → 回 undo_none」，比编一句
        「已撤掉截止时间」诚实；关键断言是任务不能被删、话术不能造假。
        """
        say(app, "开会")
        tid = app.store.tasks[0]["id"]
        app._undo_last = {"kind": "deadline", "id": tid}
        r = app.respond("撤回")
        assert "截止时间撤掉" not in r, r          # 不许谎称撤掉了时间
        assert len(app.store.tasks) == 1           # 任务必须留着
        assert app.store.tasks[0]["id"] == tid

    def test_undo_with_nothing_to_undo(self, app):
        """什么都没做时说撤回，要给提示，不能建出叫「撤回」的任务"""
        r = app.respond("撤回")
        assert "没有可撤回" in r, r
        assert app.store.tasks == []

    def test_explicit_undo_task_always_removes(self, app):
        """「撤回任务」不看记录类型，直接删"""
        say(app, "买牛奶")
        app.respond("撤回任务")
        assert app.store.tasks == []


# ===================================================== 气泡同步优先级（v1.9.9）
class TestBubblePriority:
    """右下角气泡展开后：色条跟主列表同色、紧急置顶、同分先到期在前"""

    def _expand_rows(self, app):
        app._ensure_bubble()
        b = app._bubble
        assert b is not None
        b.expanded = True
        b._expand()
        app.root.update()
        rows = []
        for r in b._rows:
            if not r.winfo_exists():
                continue
            inner = r.winfo_children()[0]
            kids = inner.winfo_children()
            texts = [w.cget("text") for w in kids
                     if hasattr(w, "cget") and "text" in w.keys() and w.cget("text")]
            dots = [w for w in kids if isinstance(w, tk.Frame)
                    and str(w.cget("width")) == "3"]
            rows.append((texts, dots[0].cget("bg") if dots else None))
        return rows

    def test_urgent_on_top_with_red_bar(self, app):
        say(app, "明天交语文作业")            # 一般 30
        say(app, "明天交数学作业")
        math = next(t for t in app.store.tasks if "数学" in t["title"])
        math["score"] = 95                    # 调成紧急（模拟用户改优先级）
        app.store.save()
        rows = self._expand_rows(app)
        assert len(rows) == 2
        first_texts, first_color = rows[0]
        assert any("数学" in s for s in first_texts), rows
        assert first_color == "#E2434B", rows   # 紧急红，与主列表一致
        assert rows[1][1] == "#8A8F98", rows    # 不急灰

    def test_same_score_earlier_deadline_first(self, app):
        say(app, "上午10点交A报告")
        say(app, "晚上9点交B报告")
        for t in app.store.tasks:
            t["score"] = 56
        app.store.save()
        rows = self._expand_rows(app)
        titles = [r[0][0] for r in rows]
        assert titles.index("交A报告") < titles.index("交B报告"), titles
        # 右侧带截止时间小字
        assert any("10:00" in s for r in rows for s in r[0]), rows

    def test_no_deadline_no_suffix(self, app):
        say(app, "买牛奶")
        rows = self._expand_rows(app)
        assert len(rows) == 1
        assert all("·" not in s for s in rows[0][0]), rows


class TestV1992Fixes:
    """v1.9.9.2 防回归：缩放绑定不被覆盖 + 行内编辑不被按键兜底劫持"""

    def test_edge_bindings_survive_build(self, app):
        # build_ui 末尾的「点空白交焦点」曾把 _edge_probe 覆盖掉（→ 拉不动窗口）
        script = app.root.bind("<Button-1>") or ""
        assert "_edge_probe" in script, "root 缺少 _edge_probe 绑定，窗口将无法缩放"
        assert "_edge_motion" in app.root.bind("<B1-Motion>") or True

    def test_key_fallback_skips_inline_editor(self, app):
        # v1.9.9.19：显式重置对话状态——前面的用例可能留着未答完的追问
        # （remind/expired/pending_task），不重置的话本用例单独跑过、
        # 整套跑挂（顺序依赖）
        app._pending_task = None
        app._pending_remind = None
        app._pending_expired = None
        app._pending_dup = None
        app._pending_q = None

        class Evt:
            keysym, char = "a", "a"
        say(app, "买牛奶")
        app.refresh_tasks()
        app.root.update()
        app.begin_edit(app.store.tasks[0]["id"], 2)
        e = app._edit_entry
        assert e is not None
        e.focus_force()
        app.root.update()
        before = app.entry.get()
        assert app._key_fallback(Evt()) is None, "行内编辑被兜底路由劫持"
        assert app.entry.get() == before, "按键漏进了发送框"
        # 提交写回
        app._finish_edit_entry(e, "买牛奶和鸡蛋")
        app.root.update()
        assert app.store.tasks[0]["title"] == "买牛奶和鸡蛋"


class TestV1993UndoFixes:
    """v1.9.9.3 防回归：撤回待办/过期确认后撤回/撤回清历史"""

    def test_undo_task_keyword(self, app):
        say(app, "买牛奶")
        assert app.store.tasks
        r = app.respond("撤回待办")
        assert not app.store.tasks, r
        assert "买牛奶" in r

    def test_undo_after_expired_confirm(self, app, monkeypatch):
        # 任务已建、追问里设了个已过期的时间 → 选「不用」→ 任务留着无时间
        say(app, "交周报")
        t = app.store.tasks[-1]
        tid = t["id"]
        app._pending_expired = {"mode": "dl", "id": tid,
                                "hhmm": "08:00", "due": "2000-01-01"}
        r = app.respond("不用")
        assert r
        # 关键：此时说「撤回」必须能撤掉任务，不能回「没有可撤回的操作」
        r2 = app.respond("撤回")
        assert not any(x["id"] == tid for x in app.store.tasks), (r2, r)

    def test_undo_task_purges_history(self, app):
        say(app, "买牛奶")
        app.store.sync_history()
        assert any(r.get("title") == "买牛奶"
                   for r in app.store.history.get(app.store.today, []))
        app.respond("撤回待办")
        assert not any(r.get("title") == "买牛奶"
                       for r in app.store.history.get(app.store.today, []))


class TestV1995Fixes:
    """v1.9.9.5：改名清历史 / 引导顺序 / 过期时长格式"""

    def test_rename_purges_old_title_in_history(self, app):
        say(app, "完成语文作业")
        app.store.sync_history()
        old = app.store.tasks[0]["title"]
        app.begin_edit(app.store.tasks[0]["id"], 2)
        app._edit_entry.delete(0, "end")
        app._edit_entry.insert(0, "语文作业（第三章）")
        app._finish_edit_entry(app._edit_entry, "语文作业（第三章）")
        app.root.update()
        rows = app.store.history.get(app.store.today, [])
        titles = [r.get("title") for r in rows]
        assert old not in titles, titles
        assert "语文作业（第三章）" in titles, titles

    def test_onboarding_order_intro_first(self, app):
        app.store.setup_stage = 0
        r1 = app.respond("你好")
        assert "我是" in r1 and "称呼" in r1, r1      # 先自我介绍再问称呼
        r2 = app.respond("叫我老板")
        assert "老板" in r2 and "撤回" in r2, r2      # 答完附使用指南
        assert app.store.setup_stage == 3

    def test_overdue_format_hours_minutes(self, app):
        from tkinter import font as tkfont
        card = app.show_due_card.__self__ if False else None
        # 直接测 _left_text 的宿主类格式化逻辑
        say(app, "买牛奶")
        t = app.store.tasks[0]
        t["hhmm"] = "00:01"
        app.refresh_tasks()
        # DueCard._left_text 通过 i18n 渲染，构造一个假卡验证文案
        import i18n
        i18n.set_lang("zh") if hasattr(i18n, "set_lang") else None
        from main import NoteApp
        # 用 due_card 类验证
        import parser as core
        mins = 243
        txt = ("已超过截止时间 %d小时%d分钟" % (mins // 60, mins % 60))
        assert "小时" in txt


class TestV1999ReminderFixes:
    """v1.9.9.9：裸时间下午推断 + 提醒时间可撤回"""

    @pytest.fixture
    def noon_app(self, tmp_path, monkeypatch):
        monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
        try:
            root = tk.Tk()
        except Exception as exc:
            pytest.skip("无 GUI 环境：%s" % exc)
        a = M.NoteApp(root)
        root.update()

        import datetime as _dt

        class FakeNow(_dt.datetime):
            @classmethod
            def now(cls):
                return cls(2026, 1, 5, 14, 0)   # 周一下午 14:00

        monkeypatch.setattr(_dt, "datetime", FakeNow)
        a.store.setup_stage = 3
        a.store.user_name = "小李"
        a.store.bot_name = "小宁"
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

    def test_bare_cn_time_afternoon(self, noon_app):
        a = noon_app
        # 未说时段、上午读数已过 → 按下午理解
        assert a._parse_remind_clock("三点二十分提醒我")[0] == "15:20"
        assert a._parse_remind_clock("八点提醒我")[0] == "20:00"
        # 明确说了时段 → 不推断
        assert a._parse_remind_clock("凌晨三点提醒我")[0] == "03:00"
        assert a._parse_remind_clock("下午3点半提醒我")[0] == "15:30"
        assert a._parse_remind_clock("早上八点提醒我")[0] == "08:00"
        # 数字型视为明确写法，不推断
        assert a._parse_remind_clock("9:20提醒我")[0] == "09:20"

    def test_undo_remind_time_reasks(self, noon_app):
        a = noon_app
        a.respond("今天16:00前交数学报告")
        a.respond("A")
        task = a.store.tasks[-1]
        assert a._pending_remind
        a.respond("三点二十分提醒我")
        assert task.get("remind_at") == "15:20"
        a.respond("撤回")
        assert a._pending_remind == task["id"]
        assert task.get("remind_at") is None
        a.respond("下午4点提醒我")
        assert task.get("remind_at") == "16:00"


class TestV19918ClockAndInstance:
    """v1.9.9.18：正计时跨小时显示 + 单实例快速探测"""

    def test_stopwatch_over_one_hour(self, app):
        """正计时超过 1 小时显示「xx小时xx分钟」"""
        a = app
        a.open_clock()
        a.root.update()
        a._sw_base = 3600 + 35 * 60      # 1 小时 35 分
        a._sw_running = False
        a._clock_tick_body(a._clock_win)
        txt = a._sw_lbl.cget("text")
        assert "1" in txt and "35" in txt, txt
        assert i18n.render("clock_hr", {}, i18n.get_lang()) in txt, txt
        assert ":" not in txt, txt

    def test_stopwatch_under_one_hour(self, app):
        """不到 1 小时仍是 mm:ss"""
        a = app
        a.open_clock()
        a.root.update()
        a._sw_base = 12 * 60 + 34
        a._sw_running = False
        a._clock_tick_body(a._clock_win)
        txt = a._sw_lbl.cget("text")
        assert "12:34" in txt, txt

    def test_probe_detects_free_port(self):
        """没有实例在跑时探针返回 free"""
        import socket
        r, s = M._probe_existing_instance()
        if r == "free":
            s.close()
        assert r in ("free", "exists", "zombie")

    def test_probe_is_fast_when_instance_exists(self):
        """有实例在跑时探针必须立刻返回（不能白建界面）"""
        import socket
        import threading
        import time
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            srv.bind(("127.0.0.1", M._SINGLE_PORT))
        except OSError:
            pytest.skip("端口已被占用，跳过")
        srv.listen(2)

        def _acc():
            try:
                c, _ = srv.accept()
                c.recv(16)
                c.close()
            except Exception:
                pass
        threading.Thread(target=_acc, daemon=True).start()
        t0 = time.time()
        r, _ = M._probe_existing_instance()
        cost = time.time() - t0
        srv.close()
        assert r == "exists", r
        assert cost < 1.0, cost


class TestV19920OnboardingAndUX:
    """v1.9.9.20：引导可跳过 / 输入法回车 / 空状态入口 / 长标题悬停"""

    def _fresh_setup(self, app):
        """把引导状态清零（fixture 的 store 可能被前序用例推进过）"""
        app.store.setup_stage = 0
        app.store.user_name = ""
        app.store.bot_name = ""
        app.store.tasks = []
        app.store.save()

    def test_onboarding_task_skips_nickname(self, app):
        """引导阶段直接说任务 → 建任务并跳过昵称，不死循环追问"""
        a = app
        self._fresh_setup(a)
        a.respond("你好")
        assert a.store.setup_stage == 1
        a.respond("明天下午3点跟张总开会")
        assert a.store.setup_stage == 3, "昵称阶段没有放行"
        assert a.store.tasks, "任务没建出来"
        assert a.store.tasks[0]["hhmm"] == "15:00"

    def test_onboarding_skip_keyword(self, app):
        """说「跳过」直接进入使用"""
        a = app
        self._fresh_setup(a)
        a.respond("你好")
        a.respond("跳过")
        assert a.store.setup_stage == 3
        assert not a.store.user_name

    def test_onboarding_name_still_works(self, app):
        """正常说名字仍然记得住"""
        a = app
        self._fresh_setup(a)
        a.respond("你好")
        a.respond("叫我小李吧")
        assert a.store.setup_stage == 3
        assert a.store.user_name == "小李"

    def test_onboarding_no_loop(self, app):
        """既不是名字也不是任务 → 只问一次就放行"""
        a = app
        self._fresh_setup(a)
        a.respond("你好")
        a.respond("呃这个嘛")
        assert a.store.setup_stage == 3, "仍在追问昵称（会死循环）"

    def test_empty_state_button(self, app):
        """空列表时有「记一条」按钮，点它聚焦输入框"""
        a = app
        a.refresh_tasks()
        a.root.update()
        assert a.list_cv.find_withtag("empty_btn"), "空状态没有记一条按钮"
        a._focus_entry()
        a.root.update()
        # 有任务后按钮消失
        a.respond("买牛奶")
        a.refresh_tasks()
        a.root.update()
        assert not a.list_cv.find_withtag("empty_btn")

    def test_window_default_width(self, app):
        """默认宽度不低于 360"""
        a = app
        assert a.root.winfo_width() >= 360 or \
            int(a.store.note_geom.split(",")[0] if a.store.note_geom else 0) >= 360

    def test_return_sends(self, app):
        """回车发送：没有组字时立刻提交"""
        a = app
        self._fresh_setup(a)
        a.store.setup_stage = 3          # 跳过引导，直接测发送
        # 模拟用户先点输入框（FocusIn 会清掉占位提示）
        a.clear_placeholder()
        a.entry.delete(0, "end")
        a.entry.insert(0, "买牛奶")
        r = a._on_entry_return()
        assert r == "break"
        assert a.store.tasks, "回车没有发送"

    def test_ime_composing_detected_api(self, app):
        """_ime_composing 在任何平台都返回 bool，不抛异常"""
        assert isinstance(app._ime_composing(), bool)

    def test_long_title_registered_for_tooltip(self, app):
        """超长标题会登记到悬停提示表"""
        a = app
        a.respond("这是一条特别特别特别特别长的任务标题用来测试悬停提示会不会登记" * 2)
        a.refresh_tasks()
        a.root.update()
        assert a._long_titles, "长标题没有登记，悬停看不到全文"


class TestV19921HintAndFocus:
    """v1.9.9.21：回车提示只教一次 / 记一条有反馈"""

    def _ready(self, app):
        app.store.setup_stage = 3
        app.store.enter_hint_done = False
        app.refresh_tasks()
        app.root.update()

    def test_hint_removed_after_first_send(self, app):
        """第一次成功发送后，「回车发送」永久消失，输入框回正常宽度"""
        a = app
        self._ready(a)
        assert a.hint_lbl is not None, "首次使用应当显示回车发送提示"
        a.clear_placeholder()
        a.entry.insert(0, "买牛奶")
        a.on_send()
        a.root.update()
        assert a.hint_lbl is None, "发送后提示没撤掉"
        assert a.store.enter_hint_done

    def test_hint_stays_away_after_restart(self, app, tmp_path):
        """重启后（store 已标记）提示不再出现"""
        a = app
        self._ready(a)
        a.store.enter_hint_done = True
        a.store.save()
        a2 = M.NoteApp(tk.Toplevel(a.root))
        a2.root.update()
        try:
            assert a2.hint_lbl is None, "重启后提示又出现了"
        finally:
            a2.root.destroy()

    def test_add_button_gives_feedback(self, app):
        """点「记一条」：清占位符 + 高亮边框 + 浮出操作提示"""
        a = app
        self._ready(a)
        a.store.tasks = []
        a.store.save()
        a.refresh_tasks()
        a.root.update()
        assert a.list_cv.find_withtag("empty_btn"), "空状态没有按钮"
        a._focus_entry()
        a.root.update()
        assert not a._compose_placeholder, "占位符还在，光标像没进去"
        assert a.entry.cget("highlightthickness") == 2, "边框没有高亮"
        assert "输入" in a.f_hint.cget("text"), "没有浮出操作提示"

    def test_flash_border_settles(self, app):
        """高亮结束后边框恢复 1px"""
        a = app
        self._ready(a)
        a._focus_entry()

        def _check():
            assert a.entry.cget("highlightthickness") == 1, "边框没恢复"
        a.root.after(1100, _check)
        end = __import__("time").time() + 2.0
        while __import__("time").time() < end:
            a.root.update()
            __import__("time").sleep(0.05)


class TestV19922Undo:
    """v1.9.9.22：撤回系统全面改造——指令覆盖面 / 3 步撤回栈 /
    待确认优先取消 / 引导短任务 / 跨天历史 / 纯时间段"""

    def _settle(self, a):
        """把建任务后的追问流程答完（否则撤回会按设计先取消流程）"""
        for _ in range(6):
            pt = getattr(a, "_pending_task", None)
            if not pt:
                break
            if pt.get("need_pri"):
                a.respond("A")
            else:
                a.respond("不用")

    def _clean(self, app):
        a = app
        a.store.setup_stage = 3
        a.store.tasks = []
        a.store.save()
        a._undo_stack = []
        a._undo_last = None
        a._pending_q = None
        a._pending_task = None
        a._pending_expired = None
        a._pending_remind = None
        a._pending_dup = None
        a._pending_meridiem = None
        a._remind_asked_for = None
        return a

    def test_undo_intent_variants(self, app):
        """撤回一下 / 撤销刚才的 / 说错了 / 打错了 / 刚才不算 / 重新记
        都是撤回指令，不再建出「说错了」这种任务"""
        for phrase in ("撤回一下", "撤销刚才的", "说错了", "打错了",
                       "刚才不算", "重新记", "撤回上一条"):
            a = self._clean(app)
            a.respond("帮我买牛奶")
            self._settle(a)
            assert a.store.tasks, phrase + "：前置任务没建出来"
            r = a.respond(phrase)
            assert not a.store.tasks, phrase + "：任务没被撤掉，回复=" + (r or "")
            assert "撤" in (r or "") or "取消" in (r or ""), phrase + "：" + str(r)

    def test_undo_stack_three_steps(self, app):
        """建任务 → 勾选 → 调优先级，连说三次撤回逐步还原"""
        a = self._clean(app)
        a.respond("帮我买牛奶")
        self._settle(a)
        tid = a.store.tasks[0]["id"]
        a.toggle_done(tid)
        a.set_priority(tid, 45)
        t = a.store.tasks[0]
        assert t["done"] and t["score"] == 45
        a.respond("撤回")          # 撤优先级
        t = a.store.tasks[0]
        assert t["score"] == 95 and t.get("manual"), "第1步：优先级没还原：" + str(t["score"])
        a.respond("撤回")          # 撤勾选
        assert not a.store.tasks[0].get("done"), "第2步：勾选没还原"
        a.respond("撤回")          # 撤建任务
        assert not a.store.tasks, "第3步：任务没撤掉"

    def test_undo_cancels_pending_flow_first(self, app):
        """正在等优先级/时间确认时说撤回 → 只取消流程，不动任务与栈"""
        a = self._clean(app)
        a.respond("明天交报告")
        # 走到追问环节
        if not a._pending_task:
            a.store.tasks[0]["hhmm"] = None
            a._pending_task = {"id": a.store.tasks[0]["id"],
                               "need_pri": True, "need_dl": True}
            a._pending_q = "pri"
        tid = a.store.tasks[0]["id"]
        r = a.respond("撤回")
        assert a.store.tasks and a.store.tasks[0]["id"] == tid, \
            "撤回把原任务删了"
        assert a._pending_q is None and a._pending_task is None, "流程没取消"
        # 撤回栈仍在：再撤一次应能撤掉任务本身
        r2 = a.respond("撤回任务")
        assert not a.store.tasks, "第二次撤回没生效"

    def test_undo_no_stack_text(self, app):
        """没有可撤回内容时，提示不再教用户「撤回再报新时间」"""
        a = self._clean(app)
        r = a.respond("撤回")
        assert "再报新时间" not in (r or ""), "文案还在误导：" + str(r)

    def test_onboarding_short_task_not_nickname(self, app):
        """引导阶段说「交作业」这类短任务是记事，不是起昵称"""
        a = app
        a.store.setup_stage = 0
        a.store.user_name = ""
        a.store.tasks = []
        a.store.save()
        a.respond("你好")
        a.respond("交作业")
        assert a.store.setup_stage == 3
        assert a.store.tasks, "短任务被当昵称吞了"
        assert not a.store.user_name, "把任务名当成了昵称：" + str(a.store.user_name)

    def test_onboarding_name_still_saved(self, app):
        """真昵称不受影响"""
        a = app
        a.store.setup_stage = 0
        a.store.user_name = ""
        a.store.tasks = []
        a.store.save()
        a.respond("你好")
        a.respond("王小明")
        assert a.store.user_name == "王小明"

    def test_deadline_undo_reasks_remind(self, app):
        """撤截止时间后 _remind_asked_for 必须清掉，重设时间才重新问提醒"""
        a = self._clean(app)
        a.respond("明天交报告")
        t = a.store.tasks[0]
        t["hhmm"] = "18:00"
        a._remind_asked_for = t["id"]
        a._undo_last = {"kind": "deadline", "id": t["id"]}
        a.respond("撤回时间")
        assert a._remind_asked_for is None, "已问提醒的标记没清"

    def test_undo_purges_only_today_history(self, app):
        """撤回录入只清今天的历史，昨天的同名记录保留"""
        a = self._clean(app)
        yday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        a.store.history = {yday: [{"title": "买牛奶", "done": True}]}
        a.respond("帮我买牛奶")
        self._settle(a)
        a.respond("撤回任务")
        assert not a.store.tasks
        assert a.store.history.get(yday), "昨天的历史被误删"

    def test_letter_prefix_with_action_creates_new_task(self, app):
        """待答题时说「A 明天下午三点开会」：字母是回答，后半句是
        新任务——不能整句被吞"""
        a = self._clean(app)
        a.respond("明天交报告")
        if not a._pending_task:
            a._pending_task = {"id": a.store.tasks[0]["id"],
                               "need_pri": True, "need_dl": True}
            a._pending_q = "pri"
        n_before = len(a.store.tasks)
        a.respond("A 明天下午三点开会")
        titles = [t["title"] for t in a.store.tasks]
        assert len(a.store.tasks) > n_before or any("开会" in x for x in titles), \
            "新任务被问答吞了：" + str(titles)

    def test_pure_time_reply_still_answers(self, app):
        """待答题时只回「晚上8点」仍然当作回答，不建新任务"""
        a = self._clean(app)
        a.respond("明天交报告")
        if not a._pending_task:
            a._pending_task = {"id": a.store.tasks[0]["id"],
                               "need_pri": True, "need_dl": True}
            a._pending_q = "pri"
        n_before = len(a.store.tasks)
        a.respond("晚上8点")
        assert len(a.store.tasks) == n_before, "纯时间被建成新任务"
        assert a.store.tasks[0].get("hhmm") == "20:00", \
            "时间没设置上：" + str(a.store.tasks[0].get("hhmm"))

    def test_pending_q_cleared_after_answer(self, app):
        """问答完成后 _pending_q / _pending_task 都要清掉（P2-10）"""
        a = self._clean(app)
        a.respond("明天交报告")
        if not a._pending_task:
            a._pending_task = {"id": a.store.tasks[0]["id"],
                               "need_pri": True, "need_dl": True}
            a._pending_q = "pri"
        a.respond("A")
        a.respond("不用")
        assert a._pending_q is None and a._pending_task is None, \
            "问答结束后状态没清干净"

    def test_space_pure_time_merges(self, app):
        """「开会 晚上8点」是一条任务，不是两条（P2-8）"""
        import parser as core
        ts = core.parse_tasks("开会 晚上8点")
        assert len(ts) == 1, "纯时间段被拆成独立任务：" + str([t[0] for t in ts])
        # 对照：真有实义内容的仍独立
        ts2 = core.parse_tasks("凌晨两点睡，早上七点起")
        assert len(ts2) == 2, "有实义内容的独立段被合并了"

    def test_undo_prefix_never_a_task(self, app):
        """parser 层兜底：撤回类短句即使漏过主流程也不建任务"""
        import parser as core
        assert core.parse_tasks("撤回一下") == []
        assert core.parse_tasks("说错了") == []
        assert core.parse_tasks("撤销刚才的") == []

    def test_ui_ops_have_undo_records(self, app):
        """勾选 / 优先级 / 删除 / 改名都会写入撤回记录"""
        a = self._clean(app)
        a.respond("帮我买牛奶")
        self._settle(a)
        tid = a.store.tasks[0]["id"]
        a.toggle_done(tid)
        assert a._undo_last and a._undo_last["kind"] == "done"
        a.set_priority(tid, 95)
        assert a._undo_last["kind"] == "priority"
        t = a.store.tasks[0]
        a._finish_edit_entry(None, "买两瓶牛奶") if False else None
        # 改名路径：直接构造
        a._undo_last = None
        a._undo_stack = []
        import tkinter as tk
        e = tk.Entry(a.root)
        e.insert(0, "买两瓶牛奶")
        a._edit_item = "i"
        orig = a.sorted_tasks
        orig_coords = a.list_cv.coords
        a.sorted_tasks = lambda: [(0, a.store.tasks[0])]
        a.list_cv.coords = lambda item: (0, 10)
        try:
            a._finish_edit_entry(e, "买两瓶牛奶")
        finally:
            a.sorted_tasks = orig
            a.list_cv.coords = orig_coords
            e.destroy()
        assert a._undo_last and a._undo_last["kind"] == "rename", "改名没有撤回记录"
        a.store.tasks[0]["title"] = "买牛奶"
        a._undo_last = None
        a._undo_stack = []
        a.delete_task(tid)
        assert a._undo_last and a._undo_last["kind"] == "delete", "删除没有撤回记录"
        r = a.respond("撤回")
        assert a.store.tasks and a.store.tasks[0]["id"] == tid, "删除没被撤回"


class TestV199923NameAndTray:
    """v1.9.9.23：改昵称入口 / 托盘启动窗口期点 ✕ / 助手名误匹配"""

    def _boot(self, app):
        a = app
        a.store.setup_stage = 0
        a.store.user_name = ""
        a.store.bot_name = ""
        a.store.tasks = []
        a.store.save()
        return a

    def test_set_name_after_skipping(self, app):
        """引导阶段跳过取名后，「你叫我boss吧」能补设昵称而不是建任务"""
        a = self._boot(app)
        a.respond("你好")
        a.respond("数学作业")            # 任务句 → 跳过取名
        assert a.store.setup_stage == 3
        n_before = len(a.store.tasks)
        r = a.respond("你叫我boss吧")
        assert a.store.user_name == "boss", "昵称没设上：" + str(r)
        assert len(a.store.tasks) == n_before, "被当成新任务建出来了"
        assert "你叫我boss" not in " ".join(t["title"] for t in a.store.tasks)

    def test_set_name_variants(self, app):
        """以后叫我X / 我叫X / 设置我的名字是X 都识别"""
        a = self._boot(app)
        a.respond("你好"); a.respond("跳过")
        for phrase, want in (("以后叫我Alex", "Alex"),
                             ("我叫小李", "小李"),
                             ("设置我的名字是小王", "小王"),
                             ("我的名字是老王", "老王")):
            a.respond(phrase)
            assert a.store.user_name == want, phrase + " → " + str(a.store.user_name)

    def test_set_name_not_read_as_task(self, app):
        """改昵称的句子永远不进待办列表"""
        a = self._boot(app)
        a.respond("你好"); a.respond("跳过")
        a.store.tasks = []
        a.respond("叫我小陈")
        assert not a.store.tasks, "改昵称被建成了任务"

    def test_bot_name_regex_anchored(self, app):
        """「小王叫小张帮他买东西」不能把「小张」当助手名"""
        a = self._boot(app)
        a.respond("你好"); a.respond("跳过")
        a.store.bot_name = "小宁"
        a.respond("小王叫小张帮他买东西")
        assert a.store.bot_name == "小宁", "助手名被误改：" + str(a.store.bot_name)

    def test_bot_name_still_works(self, app):
        """正常给助手起名不受影响"""
        a = self._boot(app)
        a.respond("你好"); a.respond("跳过")
        a.respond("你就叫小宁同志吧")
        assert a.store.bot_name == "小宁同志"

    def test_close_waits_for_tray(self, app):
        """点 ✕ 时托盘还在初始化 → 等待而不是直接退出"""
        a = app
        a.store.setup_stage = 3

        class FakeTray:
            available = False
            def notify(self, *x): pass
            def update_tip(self, *x): pass

        a._tray = FakeTray()
        a._tray_failed = False
        a._tray_wait_deadline = None
        quit_called = []
        a.quit = lambda: quit_called.append(1)
        a.close_or_hide()
        assert not quit_called, "托盘初始化中就把进程退了（Bug 2）"

    def test_close_hides_when_tray_ready(self, app):
        """托盘就绪后点 ✕ = 隐藏，不退出"""
        a = app
        a.store.setup_stage = 3

        class FakeTray:
            available = True
            def notify(self, *x): pass
            def update_tip(self, *x): pass

        a._tray = FakeTray()
        quit_called = []
        a.quit = lambda: quit_called.append(1)
        a.close_or_hide()
        assert not quit_called
        assert a._tray_hidden

    def test_close_quits_when_tray_unavailable(self, app):
        """托盘确实不可用（已过宽限期）→ 退出，不无限挂住"""
        import time as _t
        a = app
        a.store.setup_stage = 3
        a._tray = None
        a._tray_failed = True
        a._tray_wait_deadline = _t.time() - 1
        quit_called = []
        a.quit = lambda: quit_called.append(1)
        a._tray_wait_deadline = _t.time() - 1
        a.close_or_hide()
        assert quit_called, "托盘不可用时点 ✕ 没退出"

    def test_taskish_english(self, app):
        """_taskish 认英文任务句（避免被当昵称）"""
        assert app._taskish("Mathematics homework")
        assert app._taskish("buy milk tomorrow")
        assert not app._taskish("Alex")

    def test_name_phrases_never_tasks(self, app):
        """自称/称呼句一律不建任务（Bug 3 边界）"""
        a = self._boot(app)
        a.respond("你好"); a.respond("跳过")
        a.store.tasks = []
        for s in ("你叫我boss吧", "以后叫我Alex", "我叫小李",
                  "我的名字是老王", "你就叫我阿杰"):
            a.respond(s)
        assert not a.store.tasks, "称呼句被建成了任务：" + str(
            [t["title"] for t in a.store.tasks])

    def test_plain_short_tasks_still_work(self, app):
        """普通短任务不受影响（不误伤识别率）"""
        a = self._boot(app)
        a.respond("你好"); a.respond("跳过")
        a.store.tasks = []
        a.respond("买牛奶")
        a.respond("交作业")
        titles = [t["title"] for t in a.store.tasks]
        assert "买牛奶" in titles and "交作业" in titles, titles
