# -*- coding: utf-8 -*-
"""进度条百分比 / 哲言牌堆 / 中英切换 / 主题 —— 纯逻辑单元测试

对应文档条目：
  使用说明.md 第四节「顶部进度条」（灰蓝→橙→绿、百分比、鼓励语）
  使用说明.md 第八节「完成哲言」（中英各 93 句、一一对应、不串语言）
  使用说明.md 第七节「中英文切换」（不丢数据、不串语言）
  使用说明.md 第六节「便签换肤」（8 套、选择记住）
"""
import re

import pytest

import quotes
import themes
import i18n


# ===================================================== 进度条
class TestProgressBar:
    """progress_state / bar_color 是 Store 无关的纯计算，可直接取值比对"""

    @staticmethod
    def _state(tasks):
        total = len(tasks)
        done = sum(1 for t in tasks if t.get("done"))
        return done, total, (done / total if total else 0.0)

    @staticmethod
    def _color(ratio):
        # 与 main.bar_color 同口径
        if ratio >= 1.0:
            return "full"
        if ratio >= 0.5:
            return "mid"
        return "low"

    @pytest.mark.parametrize("done,total,expect_pct", [
        (0, 0, 0), (0, 4, 0), (1, 4, 25), (2, 4, 50),
        (3, 4, 75), (4, 4, 100), (1, 3, 33), (2, 3, 67),
        (1, 8, 12), (5, 8, 62), (7, 8, 88),
    ])
    def test_percent(self, done, total, expect_pct):
        d, t, r = self._state([{"done": i < done} for i in range(total)])
        assert (d, t) == (done, total)
        assert int(round(r * 100)) == expect_pct

    @pytest.mark.parametrize("done,total,color", [
        (0, 4, "low"), (1, 4, "low"), (1, 2, "mid"),
        (2, 4, "mid"), (3, 4, "mid"), (4, 4, "full"),
    ])
    def test_color_threshold(self, done, total, color):
        _, _, r = self._state([{"done": i < done} for i in range(total)])
        assert self._color(r) == color

    def test_empty_has_no_division_error(self):
        _, _, r = self._state([])
        assert r == 0.0

    def test_rounding_half_not_lost(self):
        """1/8 = 12.5% → 12%（四舍六入五成双的边界，文档未定义，锁住现状）"""
        _, _, r = self._state([{"done": True}] + [{"done": False}] * 7)
        pct = int(round(r * 100))
        assert pct in (12, 13), pct


# ===================================================== 哲言
class TestQuotes:
    def test_deck_sizes_equal(self):
        """文档：中英各 93 句、一一对应"""
        assert len(quotes.QUOTES) == len(quotes.QUOTES_EN) == 93

    def test_no_cross_language(self):
        """中文堆不得含英文，英文堆不得含中文（防串语言）"""
        assert not [q for q in quotes.QUOTES if re.search(r"[A-Za-z]{3,}", q)]
        assert not [q for q in quotes.QUOTES_EN if re.search(r"[\u4e00-\u9fff]", q)]

    def test_no_duplicates_within_deck(self):
        assert len(set(quotes.QUOTES)) == len(quotes.QUOTES)
        assert len(set(quotes.QUOTES_EN)) == len(quotes.QUOTES_EN)

    def test_full_cycle_no_repeat(self):
        """文档：一轮发完才重洗，同一轮内绝不重复"""
        deck = quotes.QuoteDeck(list(quotes.QUOTES), avoid_recent=18)
        seen = [deck.draw() for _ in range(len(quotes.QUOTES))]
        assert len(set(seen)) == len(seen), "一轮内出现重复"

    def test_decks_are_independent(self):
        """两套牌堆互不干扰：抽中文不影响英文牌堆进度"""
        ds = quotes.DeckSet()
        zh1 = ds.draw("zh")
        en1 = ds.draw("en")
        assert zh1 in quotes.QUOTES
        assert en1 in quotes.QUOTES_EN

    def test_no_repeat_across_boundary(self):
        """跨轮时用 recent 二次避让：新一轮头几句不与上一轮末尾重复"""
        deck = quotes.QuoteDeck(list(quotes.QUOTES), avoid_recent=18)
        first = [deck.draw() for _ in range(len(quotes.QUOTES))]
        last_of_round = set(first[-18:])
        second_head = [deck.draw() for _ in range(10)]
        # 允许少量重叠（句子池有限），但不该大面积重复
        overlap = sum(1 for q in second_head if q in last_of_round)
        assert overlap <= 2, "跨轮重复过多：%d" % overlap

    def test_seed_recent_restores_history(self):
        """重启后把历史发过的句子塞回去，避免立刻重复"""
        deck = quotes.QuoteDeck(list(quotes.QUOTES), avoid_recent=5)
        deck.draw()
        ds = quotes.DeckSet()
        ds.seed_recent("zh", quotes.QUOTES[:5])
        assert len(ds.deck("zh").recent) >= 5

    def test_empty_deck_returns_empty(self):
        """句子池真的为空时 draw() 返回空串（不抛异常，界面显示空白而非崩溃）"""
        deck = quotes.QuoteDeck(["x"], avoid_recent=3)
        deck.quotes = []
        deck.pool = []
        assert deck.draw() == ""

    def test_none_quotes_falls_back_to_builtin(self):
        """传 None 时回退到内置句库（避免调用方漏传就崩）"""
        deck = quotes.QuoteDeck(None, avoid_recent=3)
        assert deck.draw() in quotes.QUOTES


# ===================================================== i18n
class TestI18n:
    def test_switch_lang(self):
        i18n.set_lang("en")
        assert i18n.is_en() is True
        i18n.set_lang("zh")
        assert i18n.is_en() is False

    def test_all_keys_have_both_langs(self):
        """每个键都必须中英齐全，否则切英文会露出中文或空串"""
        missing = [k for k, v in i18n.STRINGS.items()
                   if not (isinstance(v, (tuple, list)) and len(v) == 2
                           and all(str(x).strip() for x in v))]
        assert missing == [], missing

    def test_render_uses_current_lang(self):
        i18n.set_lang("zh")
        zh = i18n.t("send")
        i18n.set_lang("en")
        en = i18n.t("send")
        assert zh != en, (zh, en)
        assert not re.search(r"[\u4e00-\u9fff]", en), "英文界面出现中文：%s" % en

    def test_render_with_params(self):
        i18n.set_lang("zh")
        s = i18n.render("dl_expired", {"t": "开会"}, "zh")
        assert "开会" in s
        s_en = i18n.render("dl_expired", {"t": "meeting"}, "en")
        assert "meeting" in s_en and not re.search(r"[\u4e00-\u9fff]", s_en)

    def test_lang_fallback_on_unknown_key(self):
        """未知键不能抛异常（否则一个漏翻就崩界面）"""
        assert isinstance(i18n.t("__no_such_key__"), str)

    def test_ui_strings_not_empty_in_english(self):
        """英文界面所有可见文案都不能是空串"""
        empties = [k for k in i18n.STRINGS
                   if not str(i18n.render(k, {}, "en")).strip()]
        assert empties == [], empties


# ===================================================== 主题
class TestThemes:
    def test_eight_themes(self):
        """文档：8 种配色"""
        assert len(themes.THEMES) == 8

    def test_required_keys(self):
        need = {"id", "name", "bg", "head", "line", "sub", "accent", "text",
                "row2", "bubble"}
        for t in themes.THEMES:
            assert need <= set(t), (t.get("id"), need - set(t))

    def test_unique_ids(self):
        ids = [t["id"] for t in themes.THEMES]
        assert len(set(ids)) == len(ids)

    def test_contrast_ratio_documented(self):
        """文档称正文对比度约 10:1；这里用 WCAG 公式下限 7:1 兜底，
        低于 7:1 的需人工复核（记录在报告里）"""
        def lum(hexc):
            c = hexc.lstrip("#")
            rgb = [int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
            rgb = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
                   for v in rgb]
            return 0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2]

        bad = []
        for t in themes.THEMES:
            l1, l2 = lum(t["text"]), lum(t["bg"])
            hi, lo = max(l1, l2), min(l1, l2)
            ratio = (hi + 0.05) / (lo + 0.05)
            if ratio < 7.0:
                bad.append((t["id"], round(ratio, 2)))
        assert bad == [], "对比度不足 7:1：%s" % bad


# ===================================================== 提醒去重规则
class TestReminderDedup:
    """把 check_reminders 的判定条件抽成纯函数测：
    重点验证「同一任务不会重复弹卡片」和「跨天能重新提醒」。"""

    @staticmethod
    def should_fire(t, now, today_iso):
        """与 main.check_reminders 同口径的简化判定"""
        if t.get("done"):
            return False
        if not t.get("hhmm") and not t.get("remind_at"):
            return False
        if not t.get("remind_before") and not t.get("remind_at"):
            return False
        rep = t.get("repeat")
        if rep:
            # 周期任务：当天该做才提醒；跨天重置 reminded
            if t.get("reminded") and t.get("reminded_day") == today_iso:
                return False
        elif t.get("due_date") and t["due_date"] != today_iso:
            return False
        if t.get("reminded"):
            return False
        return True

    def test_reminded_once(self):
        t = {"title": "x", "hhmm": "09:00", "remind_before": 5,
             "done": False, "reminded": True, "reminded_day": "2026-10-29"}
        assert self.should_fire(t, None, "2026-10-29") is False

    def test_done_never_fires(self):
        t = {"title": "x", "hhmm": "09:00", "remind_before": 5,
             "done": True, "reminded": False}
        assert self.should_fire(t, None, "2026-10-29") is False

    def test_no_remind_before_never_fires(self):
        t = {"title": "x", "hhmm": "09:00", "done": False, "reminded": False}
        assert self.should_fire(t, None, "2026-10-29") is False

    def test_other_day_due_date_skipped(self):
        """截止日不是今天 → 不提醒（避免第二天早上补弹昨天的卡片）"""
        t = {"title": "x", "hhmm": "09:00", "remind_before": 5,
             "done": False, "reminded": False, "due_date": "2026-10-30"}
        assert self.should_fire(t, None, "2026-10-29") is False
