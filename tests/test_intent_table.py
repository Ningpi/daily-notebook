# -*- coding: utf-8 -*-
"""意图快照测试（v1.9.9.29 重构配套）

目的：把「哪句话该归到哪类意图」从**代码里的 if 顺序**变成**一张可读的表**。

以前加一句话的处理，要看 488 行 respond 的顺序，改一处不知道撞到哪儿；
现在这张表就是唯一事实来源——新需求先在这里加一行，改错了测试直接红。

每条用例给出：
  · 输入
  · 期望意图（走哪个处理器）
  · 期望任务结果（建了哪些任务）

⚠ 改 main.py 里意图的优先级或正则时，**先改这张表**，再看测试对不对。
"""
import os
import sys
import datetime as dt

import pytest

pytest.importorskip("tkinter")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main as M   # noqa: E402


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    _ = M.NoteApp   # 保证模块已加载
    root = M.tk.Tk()
    root.withdraw()
    a = M.NoteApp(root)
    a.store.setup_stage = 3
    a.store.tasks = []
    a.store.save()
    for k in ("_pending_q", "_pending_task", "_pending_expired",
              "_pending_remind", "_pending_dup", "_pending_meridiem"):
        setattr(a, k, None)
    yield a
    try:
        root.destroy()
    except Exception:
        pass


# ---------------------------------------------------------------- 元指令
META = [
    # (输入, 说明)
    ("你是谁", "自我介绍"),
    ("你叫小宁吧", "给助手起名"),
    ("你叫我小林吧", "改用户昵称"),
    ("撤回", "撤回（无内容可撤时的兜底）"),
    ("记个便签：明天带伞", "便签指令"),
]

# ---------------------------------------------------------------- 查询
QUERY = [
    "列表",
    "我的任务",
    "我的待办",
    "今天有什么任务",
    "我今天有什么安排",
    "明天要做什么",
    "我一共有多少任务",
    "这周还有什么",
    "今天做了什么",
    "今天干了什么活",
]

# ---------------------------------------------------------------- 纯聊天
CHAT = [
    "算了不用了",
    "好的",
    "嗯",
    "没事",
    "我累了",
    "头疼",
    "好烦啊",
    "压力好大",
    "你好",
    "谢谢你",
]

# ---------------------------------------------------------------- 建任务
BUILD = [
    ("买牛奶", ["买牛奶"]),
    ("写周报", ["写周报"]),
    ("明天下午三点开会", ["开会"]),
    ("每天早上八点背单词", ["每天背单词"]),
    ("每周一三五跑步", ["跑步"]),
    ("每个工作日写日报", ["每个工作日写日报"]),   # 工作日限定词保留，语义不丢
    ("每个月5号交房租", ["每个月交房租"]),      # 号数进 repeat，标题留「每个月」
    ("买什么菜", ["买什么菜"]),          # 带动作的疑问句仍是任务
    ("明天要交什么报告", ["要交什么报告"]),
]


def _fresh(app):
    a = app
    a.store.tasks = []
    a.store.save()
    for k in ("_pending_q", "_pending_task", "_pending_expired",
              "_pending_remind", "_pending_dup", "_pending_meridiem",
              "_miss_reply"):
        setattr(a, k, None)
    return a


class TestIntentTable:
    """这张表 = 「哪句话归哪类」的唯一事实来源"""

    @pytest.mark.parametrize("text", QUERY)
    def test_query_never_creates_task(self, app, text):
        a = _fresh(app)
        a.respond(text)
        assert not a.store.tasks, "查询句被建成任务：%s" % [t["title"] for t in a.store.tasks]

    @pytest.mark.parametrize("text", CHAT)
    def test_chat_never_creates_task(self, app, text):
        a = _fresh(app)
        a.respond(text)
        assert not a.store.tasks, "聊天句被建成任务：%s" % [t["title"] for t in a.store.tasks]

    @pytest.mark.parametrize("text,expect", BUILD)
    def test_build_creates_task(self, app, text, expect):
        a = _fresh(app)
        a.respond(text)
        titles = [t["title"] for t in a.store.tasks]
        assert titles == expect, "%s → %s（期望 %s）" % (text, titles, expect)

    def test_meta_never_creates_task(self, app):
        a = _fresh(app)
        for text, _why in META:
            a.respond(text)
        assert not a.store.tasks, [t["title"] for t in a.store.tasks]

    # ---- 优先级顺序：查询必须先于「勾选」，否则「完成多少」会被当完成语
    def test_query_beats_complete(self, app):
        """「我完成了多少」是查询，不是「完成」某件任务"""
        a = _fresh(app)
        a.respond("买牛奶")
        a.respond("C")
        a.respond("不用")
        n = len(a.store.tasks)
        a.respond("我完成了多少")
        assert len(a.store.tasks) == n, "查询被当成了新任务"

    # ---- 软意图：必须匹配到已有任务才算完成
    def test_soft_done_requires_match(self, app):
        """「买牛奶」没有匹配到任务 → 是新任务，不是完成语"""
        a = _fresh(app)
        a.respond("买牛奶")
        assert [t["title"] for t in a.store.tasks] == ["买牛奶"]

    def test_soft_done_matches_existing(self, app):
        """「背单词打卡了」匹配到日常任务 → 打卡，不是新任务"""
        a = _fresh(app)
        a.respond("每天早上八点背单词")
        a.respond("不用")
        before = len(a.store.tasks)
        a.respond("背单词打卡了")
        assert len(a.store.tasks) == before
        assert a.store.tasks[0]["done"] is True

    # ---- 硬意图：认错了也要有回应，不能静默建任务
    def test_hard_done_missing_gets_reply(self, app):
        a = _fresh(app)
        r = a.respond("完成一个根本不存在的东西")
        assert not a.store.tasks
        assert "没找到" in (r or ""), r


class TestV199931DailyPhrasing:
    """v1.9.9.31：日常任务的自然说法

    用户原话：「如果我输入的是完成数学作业，每天晚上八点。
    这样的话，明天它还会在待办中吗？」
    """

    # ---- 解析层：「完成X，每天晚上八点」是一个任务，不是两个
    def test_bare_repeat_merges_into_previous(self):
        import parser
        r = parser.parse_tasks("背单词，每天晚上八点")
        assert len(r) == 1, r
        assert r[0][0] == "背单词"
        assert r[0][1] == "20:00"
        assert r[0][5] and r[0][5]["kind"] == "daily"

    def test_verb_then_daily_schedule(self):
        import parser
        r = parser.parse_tasks("完成数学作业，每天晚上八点")
        assert len(r) == 1, r
        assert r[0][0] == "完成数学作业"
        assert r[0][1] == "20:00"
        assert r[0][5]["kind"] == "daily"

    # ---- 意图层：「完成」+重复信号是建任务，不是打卡
    def test_complete_with_repeat_creates_task(self, app):
        a = _fresh(app)
        a.respond("完成数学作业，每天晚上八点")
        titles = [t["title"] for t in a.store.tasks]
        assert titles == ["完成数学作业"], titles
        t = a.store.tasks[0]
        assert t.get("repeat", {}).get("kind") == "daily"
        assert t.get("hhmm") == "20:00"

    def test_daily_task_survives_to_tomorrow(self, app):
        """建了日常任务后，次日它仍然在待办里（且未打卡）"""
        import datetime as _dt
        a = _fresh(app)
        a.respond("完成数学作业，每天晚上八点")
        t = a.store.tasks[0]
        t["done"] = True              # 今天打完了
        t["done_day"] = a.store._today()
        tomorrow = (_dt.date.today() + _dt.timedelta(days=1)).isoformat()
        a.store._roll_day(tomorrow)
        assert a.store.tasks[0]["done"] is False, "第二天应重新变成待办"
