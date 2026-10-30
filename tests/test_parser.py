# -*- coding: utf-8 -*-
"""解析器单元测试（重点：解析准确率）

覆盖维度：
  - 时间：绝对钟点 / 中文数字 / 半点·一刻 / 时段词 / 全天候 12/24 进位
  - 日期：今天·明天·后天 / 周X / 月日 / 相对天数
  - 拆分：一句话多任务 / 空格分隔 / 时间区间不拆 / 连词
  - 清洗：口头语 / 前置动词 / 量词不被当噪音 / 「把水电费交了」病句
  - 打分：紧急词 / 重要词 / 松弛词 / 时间临近 / 周期任务降权
  - 不误判：问候 / 感谢 / 纯时间句 / 空输入
  - 中英隔离：英文引擎不认中文、中文引擎不认英文

对应文档条目：使用说明.md 第九节「怎么聊任务」
"""
import datetime as dt

import pytest

import parser as core
import parser_en as core_en


# --------------------------------------------------------------- 时间识别
class TestFindTimes:
    @pytest.mark.parametrize("text,expect", [
        ("9点开会", "09:00"),
        ("九点开会", "09:00"),
        ("九点半开会", "09:30"),
        ("八点一刻", "08:15"),
        ("23:45 交报告", "23:45"),
        ("晚上8点吃饭", "20:00"),
        ("下午三点交作业", "15:00"),
        ("中午1点45分出发", "13:45"),
        ("凌晨两点睡", "02:00"),
        ("早上七点跑步", "07:00"),
        ("傍晚六点散步", "18:00"),
    ])
    def test_zh_clock(self, text, expect):
        r = core.find_times(text)
        assert r, "未识别出时间：%s" % text
        assert r[0][0] == expect, "期望 %s，实际 %s（%s）" % (expect, r[0][0], text)

    def test_no_time(self):
        assert core.find_times("买瓶酱油") == []

    def test_twelve_noon_not_pm(self):
        """12 点不应被「下午」加成 24 点"""
        r = core.find_times("中午12点吃饭")
        assert r[0][0] == "12:00"

    def test_english_engine_clock(self):
        cases = {
            "meeting at 2pm": "14:00",
            "call at 9am": "09:00",
            "submit before 5pm": "17:00",
            "lunch at noon": "12:00",
        }
        for text, expect in cases.items():
            r = core_en.find_times(text) if hasattr(core_en, "find_times") else None
            if r is None:
                # parser_en 以 parse_tasks 为入口
                r = core_en.parse_tasks(text)
                assert r and r[0][1] == expect, (text, r)
            else:
                assert r and r[0][0] == expect, (text, r)


# --------------------------------------------------------------- 日期识别
class TestDates:
    def test_tomorrow(self, tomorrow):
        d = core.find_deadline_date("明天上午10点体检")
        assert d and d[0] == tomorrow

    def test_day_after(self):
        d = core.find_deadline_date("后天交材料")
        assert d and d[0] == dt.date.today() + dt.timedelta(days=2)

    def test_weekday(self):
        d = core.find_deadline_date("周五前交周报")
        assert d and d[0].weekday() == 4

    def test_month_day(self):
        d = core.find_deadline_date("10月20日交报告")
        assert d and d[0].month == 10 and d[0].day == 20

    def test_month_day_within_half_year_keeps_year(self):
        """半年内的过去日期：保留今年 → 触发「已过截止日期」确认（不静默推明年）"""
        today = dt.date.today()
        mo, dy = today.month, today.day
        text = "%d月%d日交报告" % (mo, dy)
        d = core.find_deadline_date(text)
        assert d and d[0].year == today.year, d[0]   # 今天当天 → 走过期确认

    def test_month_day_beyond_half_year_rolls_next_year(self):
        """超过半年的过去日期：用户多半指明年（v1.9.4 既定规则，防止误判为「早已过期」）"""
        today = dt.date.today()
        # 构造一个距今 > 184 天的日期
        far = today - dt.timedelta(days=200)
        text = "%d月%d日交报告" % (far.month, far.day)
        if abs((today - dt.date(today.year, far.month, far.day)).days) > 184:
            d = core.find_deadline_date(text)
            assert d and d[0].year == today.year + 1, d[0]


# --------------------------------------------------------------- 分句与拆分
class TestSplit:
    def test_multi_task_comma(self):
        r = core.parse_tasks("9点开会，下午3点前交周报，顺便买瓶酱油")
        titles = [x[0] for x in r]
        assert len(r) == 3, titles
        assert "开会" in titles[0]
        assert "交周报" in titles[1]
        assert "买瓶酱油" in titles[2]

    def test_space_separated(self):
        r = core.parse_tasks("9点开会 下午3点交周报")
        assert len(r) == 2, [x[0] for x in r]

    def test_time_range_not_split(self):
        """「下午三点到四点」是一个时间区间，不能拆成两个任务"""
        r = core.parse_tasks("下午三点到四点开会")
        assert len(r) == 1, [x[0] for x in r]

    def test_join_verbs(self):
        r = core.parse_tasks("买牛奶然后交电费")
        assert len(r) == 2, [x[0] for x in r]

    def test_empty(self):
        assert core.parse_tasks("") == []
        assert core.parse_tasks("   ") == []


# --------------------------------------------------------------- 标题清洗
class TestCleanTitle:
    @pytest.mark.parametrize("raw,expect_contains", [
        ("记得下午4点接孩子", "接孩子"),
        ("帮我买瓶酱油", "买瓶酱油"),
        ("麻烦提醒我8点吃药", "吃药"),
        ("把水电费交了", "交水电费"),
    ])
    def test_clean(self, raw, expect_contains):
        r = core.parse_tasks(raw)
        assert r, raw
        assert expect_contains in r[0][0], (raw, r[0][0])

    def test_quantity_not_stripped(self):
        """「三个鸡蛋」里的数量不能当噪音删掉"""
        r = core.parse_tasks("买三个鸡蛋")
        assert r and ("三" in r[0][0] or "3" in r[0][0]), r


# --------------------------------------------------------------- 打分
class TestScore:
    def test_urgent_beats_normal(self):
        a = core.score_task("开会", "马上开会", None)
        b = core.score_task("开会", "开会", None)
        assert a > b

    def test_important_words(self):
        a = core.score_task("体检", "明天体检非常重要", None)
        b = core.score_task("体检", "明天体检", None)
        assert a > b

    def test_relax_words(self):
        a = core.score_task("整理房间", "有空整理房间", None)
        b = core.score_task("整理房间", "整理房间", None)
        assert a < b

    def test_score_bounds(self):
        for raw in ("马上立刻火速紧急处理合同", "有空顺便随便看看"):
            s = core.score_task("x", raw, "08:00")
            assert 0 <= s <= 100, (raw, s)

    def test_soon_time_boosts(self, now):
        """距现在 30 分钟内应显著加分"""
        soon = (now + dt.timedelta(minutes=10)).strftime("%H:%M")
        s_soon = core.score_task("x", "x", soon)
        s_none = core.score_task("x", "x", None)
        assert s_soon > s_none

    def test_repeat_task_lower(self):
        a = core.score_task("喝水", "每天喝水", None)
        b = core.score_task("喝水", "喝水", None)
        assert a < b


# --------------------------------------------------------------- 周期任务
class TestRepeat:
    @pytest.mark.parametrize("raw,kind", [
        ("每天跑步", "daily"),
        ("每个工作日打卡", "workday"),
        ("每周一开会", "weekly"),
        ("每月5号交房租", "monthly"),
        ("每周复盘", "weekly"),
    ])
    def test_detect(self, raw, kind):
        r = core.find_repeat(raw)
        assert r and r["kind"] == kind, (raw, r)

    def test_no_repeat(self):
        assert core.find_repeat("明天开会") is None

    def test_due_today(self):
        rep = {"kind": "daily", "weekday": None, "monthday": None}
        assert core.repeat_due_today(rep) is True
        rep_w = {"kind": "weekly", "weekday": 0, "monthday": None}
        monday = dt.date(2026, 10, 26)   # 周一
        assert core.repeat_due_today(rep_w, monday) is True
        assert core.repeat_due_today(rep_w, monday + dt.timedelta(days=1)) is False


# --------------------------------------------------------------- 不该建任务
class TestNotTask:
    @pytest.mark.parametrize("text", [
        "你好", "谢谢", "好的", "嗯", "在吗", "ok",
    ])
    def test_greetings(self, text):
        assert core.parse_tasks(text) == [], text

    def test_pure_time(self):
        """只说时间不说事，不该建任务"""
        assert core.parse_tasks("九点") == []


# --------------------------------------------------------------- 中英隔离
class TestLangIsolation:
    def test_zh_engine_ignores_english(self):
        """中文引擎不应把英文当时间解析（否则中英切换后会串）"""
        assert core.find_times("meeting at 2pm") == []

    def test_en_engine_ignores_chinese_time(self):
        r = core_en.parse_tasks("开会 at 2pm")
        # 英文引擎识别 2pm；中文标题原样保留
        assert any("14:00" == x[1] for x in r if len(x) > 1), r

    def test_en_parse_basic(self):
        r = core_en.parse_tasks("meeting at 2pm, submit report before 5pm")
        assert len(r) >= 2, r
        assert any(x[1] == "14:00" for x in r), r
        assert any(x[1] == "17:00" for x in r), r


# --------------------------------------------------------------- 姓名提取
class TestExtractName:
    @pytest.mark.parametrize("text,expect", [
        ("你叫我小李吧", "小李"),
        ("我叫张三", "张三"),
        ("call me Alex", "Alex"),
        ("以后叫我老王就好了", "老王"),
    ])
    def test_extract(self, text, expect):
        assert core.extract_name(text) == expect

    @pytest.mark.parametrize("text", ["你好", "你是谁", "谢谢"])
    def test_not_name(self, text):
        assert core.extract_name(text) in (None, ""), text


# --------------------------------------------------------------- 优先级分档
class TestPriorityLabel:
    @pytest.mark.parametrize("score,bucket", [
        (100, "紧急"), (75, "紧急"), (74, "重要"), (55, "重要"),
        (54, "一般"), (35, "一般"), (34, "不急"), (0, "不急"),
    ])
    def test_bucket(self, score, bucket):
        assert core.priority_label(score)[0] == bucket

    def test_monotonic_color(self):
        """四档颜色必须互不相同（否则列表上看不出差别）"""
        colors = {core.priority_label(s)[1] for s in (90, 60, 40, 10)}
        assert len(colors) == 4, colors


# ------------------------------------------------- 「时间/小时」里的「时」不是钟点
class TestShiNotClock:
    """v1.9.9 回归：TIME_STRIP_RE 的单字兜底会啃掉「时间」里的「时」

    这个 bug 有两个出口：
      ① 标题被吃字（「时间管理课」→「间管理课」）
      ② 「撤一下时间」被解析成新任务《撤一下间》，撤回指令彻底失效
    """

    @pytest.mark.parametrize("text,expect", [
        ("整理时间表", "整理时间表"),
        ("时间管理课", "时间管理课"),
        ("时间表和课表都改一下", "时间表和课表都改"),
        ("撤一下时间", "撤一下时间"),
        ("改时间", "改时间"),
        ("删除时间", "删除时间"),
        ("时差还没倒过来", "时差还没倒过来"),
        ("时不时看看邮件", "时不时看看邮件"),
    ])
    def test_shi_word_survives(self, text, expect):
        assert core.parse_tasks(text)[0][0] == expect, core.parse_tasks(text)

    @pytest.mark.parametrize("text,hhmm", [
        ("九点开会", "09:00"),
        ("九点半开会", "09:30"),
        ("下午三点前交作业", "15:00"),
        ("明天上午10点交报告", "10:00"),
    ])
    def test_real_clock_still_works(self, text, hhmm):
        """保护不能把真正的「点」也保护掉"""
        assert core.find_times(text)[0][0] == hhmm

    def test_hour_duration_not_broken(self):
        """「两小时后」是时长，不是钟点；不能被保护逻辑误伤"""
        got = core.parse_tasks("两小时后提醒我")[0]
        assert got[0] == "提醒我", got
        assert got[1] is None, got          # 不该有 hhmm
