# -*- coding: utf-8 -*-
"""v1.9.9.52 回归：一轮「拿到手能用吗」的破坏性测试。

测试思路不是再跑一遍功能，而是**故意把数据和输入搞坏**，看程序会不会
静默丢数据、启动崩溃、或者给用户一个错误的日期：

  1. tasks.json 能读懂但字段坏（手改 / 同步冲突 / 旧版本残留）
     —— 旧版直接 KeyError / AttributeError，启动即崩；
  2. 「9:99」「5点65分」这类越界时间 —— 旧版产出 "09:99"，写进文件后
     提醒循环 now.replace(minute=99) 抛错被吞，任务永远不提醒；
  3. 「2月30日」—— 旧版退化成「当月30号」，凭空造一个截止日；
  4. 「明天9点开会，10点写周报」—— 第二段没有日期，晚上录入被当成
     「今天10点已过」而卡在确认里，用户以为第二条没记上；
  5. 「取消完成买牛奶」—— 被当成「取消 + 买牛奶」删掉整条任务；
  6. 英文「on friday」不认日期、标题残留 sunday；
  7. 英文界面里备份列表 / 撤回提示 / 截止时间还是中文。
"""
import datetime as dt
import json
import os

import pytest

import main as M
import parser as PC
import parser_en as PE
import i18n

tk = pytest.importorskip("tkinter")


# ------------------------------------------------------------ 工具
def write_json(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


@pytest.fixture
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    M.Store._save_errors.clear()
    M.Store._save_error = None
    return tmp_path


def make_store(data_dir, obj=None):
    if obj is not None:
        write_json(os.path.join(str(data_dir), "tasks.json"), obj)
    return M.Store()


# ------------------------------------------------------------ 1. 脏数据
class TestDirtyData:
    def test_missing_title_is_filled(self, data_dir):
        st = make_store(data_dir, {"tasks": [{"hhmm": "09:00", "done": False}]})
        assert len(st.tasks) == 1
        assert st.tasks[0]["title"]          # 补了占位名，不是空
        assert st.tasks[0]["id"]             # id 也补齐了

    def test_title_not_string(self, data_dir):
        st = make_store(data_dir, {"tasks": [{"title": 123}]})
        assert st.tasks[0]["title"] == "123"

    @pytest.mark.parametrize("bad", ["高", None, [], {}, float("nan")])
    def test_score_not_number(self, data_dir, bad):
        st = make_store(data_dir, {"tasks": [{"title": "任务", "score": bad}]})
        assert isinstance(st.tasks[0]["score"], int)
        assert 0 <= st.tasks[0]["score"] <= 100

    def test_score_clamped(self, data_dir):
        st = make_store(data_dir, {"tasks": [{"title": "a", "score": 999},
                                             {"title": "b", "score": -50}]})
        assert st.tasks[0]["score"] == 100
        assert st.tasks[1]["score"] == 0

    def test_quotes_not_dict(self, data_dir):
        """quotes 坏成数字：旧版 self.quotes.setdefault 启动即 AttributeError"""
        st = make_store(data_dir, {"quotes": 5})
        assert isinstance(st.quotes, dict)
        assert set(st.quotes) >= {"zh", "en"}
        assert isinstance(st.quotes["zh"]["recent"], list)

    def test_quotes_partial(self, data_dir):
        st = make_store(data_dir, {"quotes": {"zh": "坏", "en": {"last": 3}}})
        assert isinstance(st.quotes["zh"], dict)
        assert isinstance(st.quotes["en"]["last"], str)

    def test_due_date_invalid(self, data_dir):
        st = make_store(data_dir, {"tasks": [{"title": "a", "due_date": "2026-13-45"}]})
        assert st.tasks[0]["due_date"] is None

    def test_due_date_valid(self, data_dir):
        st = make_store(data_dir, {"tasks": [{"title": "a", "due_date": "2026-11-20"}]})
        assert st.tasks[0]["due_date"] == "2026-11-20"

    def test_repeat_invalid(self, data_dir):
        st = make_store(data_dir, {"tasks": [{"title": "a", "repeat": {"kind": "xx"}}]})
        assert st.tasks[0]["repeat"] is None

    def test_repeat_legacy_string(self, data_dir):
        """旧数据把 repeat 存成「每周三」字符串"""
        st = make_store(data_dir, {"tasks": [{"title": "开会", "repeat": "每周三"}]})
        assert isinstance(st.tasks[0]["repeat"], dict)

    def test_duplicate_ids(self, data_dir):
        st = make_store(data_dir, {"tasks": [{"title": "a", "id": "x"},
                                             {"title": "b", "id": "x"}]})
        assert st.tasks[0]["id"] != st.tasks[1]["id"]

    def test_chat_h_not_int(self, data_dir):
        """聊天区高度写成 "tall"：int() 抛错，旧版启动即崩"""
        st = make_store(data_dir, {"chat_h": "tall"})
        assert st.chat_h is None or isinstance(st.chat_h, int)

    def test_chat_h_clamped(self, data_dir):
        st = make_store(data_dir, {"chat_h": 99999})
        assert 60 <= st.chat_h <= 600

    def test_alpha_out_of_range(self, data_dir):
        st = make_store(data_dir, {"alpha": 5})
        assert 0.35 <= st.alpha <= 1.0
        st.save()           # 关键：不能因为 round(inf) 抛 OverflowError

    def test_font_scale_bad(self, data_dir):
        st = make_store(data_dir, {"font_scale": "big"})
        assert 0.8 <= st.font_scale <= 1.3

    def test_lang_fallback(self, data_dir):
        st = make_store(data_dir, {"lang": "fr"})
        assert st.lang in ("zh", "en")

    def test_messages_bad_role(self, data_dir):
        st = make_store(data_dir, {"messages": [{"x": 1}, {"role": "me", "text": 5}]})
        assert all(m["role"] in ("me", "bot") for m in st.messages)
        assert all(isinstance(m["text"], str) for m in st.messages)

    def test_notes_bad(self, data_dir):
        st = make_store(data_dir, {"notes": [{"text": 5}, "字符串便签", {"id": "a"}]})
        assert all(isinstance(n, dict) and isinstance(n["text"], str) for n in st.notes)

    def test_history_rows_not_dict(self, data_dir):
        """历史里混进字符串：旧版 _hist_sig 里 r.get 直接 AttributeError"""
        write_json(os.path.join(str(data_dir), "history.json"),
                   {"days": {dt.date.today().isoformat(): ["坏行", {"title": "好行"}]}})
        st = M.Store()
        rows = st.history[dt.date.today().isoformat()]
        assert all(isinstance(r, dict) for r in rows)
        assert len(rows) == 1

    def test_clean_is_written_back(self, data_dir):
        """修过的脏字段要回写，否则下次启动还得再修一遍"""
        st = make_store(data_dir, {"tasks": [{"title": "a", "score": "高"}]})
        raw = json.load(open(os.path.join(str(data_dir), "tasks.json"), encoding="utf-8"))
        assert raw["tasks"][0]["score"] == st.tasks[0]["score"]
        assert "due_date" in raw["tasks"][0]

    def test_clean_does_not_touch_good_file(self, data_dir):
        """干净的数据不该被无谓改写（mtime 不变）"""
        p = os.path.join(str(data_dir), "tasks.json")
        write_json(p, {"tasks": [{"id": "a1", "title": "买牛奶", "hhmm": "09:00",
                                  "score": 50, "done": False, "created": "09:00",
                                  "day": dt.date.today().isoformat(), "dur": None,
                                  "manual": False, "repeat": None, "due_date": None,
                                  "deadline_txt": None, "remind_before": 0,
                                  "remind_at": None, "remind_day": 0, "reminded": False,
                                  "reminded_day": None, "done_at": None,
                                  "_from_raw": True, "streak": 0, "last_done_day": None,
                                  "dur_min": None}]})
        before = open(p, encoding="utf-8").read()
        st = M.Store()
        after = open(p, encoding="utf-8").read()
        assert st.tasks[0]["title"] == "买牛奶"
        assert before == after, "干净文件被无谓改写了"


# ------------------------------------------------------------ 2. 越界时间
class TestTimeBounds:
    @pytest.mark.parametrize("text", ["9:99开会", "25:99开会", "5点65分写周报"])
    def test_out_of_range_clock_rejected(self, text):
        for item in PC.parse_tasks(text):
            hhmm = item[1]
            assert hhmm is None or (0 <= int(hhmm[:2]) <= 23 and
                                    0 <= int(hhmm[3:]) <= 59), hhmm

    def test_valid_clock_kept(self):
        r = PC.parse_tasks("明天9:30开会")
        assert r and r[0][1] == "09:30"

    def test_feb_30_not_downgraded(self):
        """「2月30日」不存在：不能退化成「当月30号」"""
        assert PC.find_deadline_date("2月30日体检")[0] is None

    def test_apr_31_not_downgraded(self):
        assert PC.find_deadline_date("4月31日交表")[0] is None

    def test_slash_date_invalid(self):
        assert PC.find_deadline_date("2/30 交表")[0] is None

    def test_valid_month_day(self):
        d, _ = PC.find_deadline_date("12月25日过圣诞")
        assert d.month == 12 and d.day == 25


# ------------------------------------------------------------ 3. 日期继承
class TestMultiTaskDate:
    def test_second_segment_inherits_date(self):
        """「明天9点开会，10点写周报」第二条也属于明天"""
        r = PC.parse_tasks("明天9点开会，10点写周报")
        assert len(r) == 2
        assert r[0][6] == r[1][6] is not None
        assert r[1][6] == dt.date.today() + dt.timedelta(days=1)

    def test_timeless_segment_not_given_date(self):
        """没有钟点的段不继承日期（「明天开会，顺便买菜」）"""
        r = PC.parse_tasks("明天9点开会，顺便买菜")
        assert len(r) == 2
        assert r[1][6] is None

    def test_no_date_no_inherit(self):
        r = PC.parse_tasks("9点开会，10点写周报")
        assert r[0][6] is None and r[1][6] is None


# ------------------------------------------------------------ 4. 取消完成 ≠ 删除
@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    try:
        root = tk.Tk()
    except Exception as exc:          # pragma: no cover
        pytest.skip("无 GUI 环境：%s" % exc)
    root.geometry("430x660+20+20")
    a = M.NoteApp(root)
    root.update()
    a.store.setup_stage = 3
    a.store.user_name = "小李"
    a.store.tasks = []
    a.store.messages = []
    a._compose_placeholder = False
    yield a
    try:
        root.destroy()
    except Exception:
        pass
    finally:
        i18n.set_lang("zh")


def send(a, text):
    a.entry.delete(0, "end")
    a._compose_placeholder = False
    a.entry.insert(0, text)
    a.on_send()
    a.root.update()


class TestCancelDone:
    def test_cancel_done_does_not_delete(self, app):
        """「取消完成买牛奶」是撤销打卡，旧版把任务整条删掉"""
        send(app, "买牛奶")
        assert len(app.store.tasks) == 1
        send(app, "取消完成买牛奶")
        assert len(app.store.tasks) == 1, "任务被误删了"
        assert app.store.tasks[0]["title"] == "买牛奶"

    def test_cancel_checkin_does_not_delete(self, app):
        send(app, "背单词")
        send(app, "取消打卡背单词")
        assert len(app.store.tasks) == 1

    def test_plain_cancel_still_deletes(self, app):
        """「取消写周报」仍然按删除处理（不能把正常删除也拦掉）"""
        send(app, "写周报")
        send(app, "取消写周报")
        assert len(app.store.tasks) == 0

    def test_multi_task_same_sentence(self, app):
        """一句两条：都要落库，且都被认成明天"""
        send(app, "明天9点开会，10点写周报")
        titles = [t["title"] for t in app.store.tasks]
        assert len(titles) == 2, titles
        assert all(t.get("due_date") == (dt.date.today() +
                                         dt.timedelta(days=1)).isoformat()
                   for t in app.store.tasks)


# ------------------------------------------------------------ 5. 英文
class TestEnglish:
    @pytest.mark.parametrize("text,expect_wd", [
        ("pay bill on friday", 4),
        ("dinner sunday", 6),
        ("meeting monday 9am", 0),
    ])
    def test_bare_weekday(self, text, expect_wd):
        r = PE.parse_tasks(text)
        assert r, text
        due = r[0][6]
        if dt.date.today().weekday() == expect_wd:
            assert due is None or due.weekday() == expect_wd
        else:
            assert due is not None and due.weekday() == expect_wd

    def test_weekday_stripped_from_title(self):
        r = PE.parse_tasks("dinner sunday")
        assert r and "sunday" not in r[0][0].lower()

    def test_every_weekday_has_no_due(self):
        """周期任务不带「某一天」，否则和中文侧规则冲突"""
        r = PE.parse_tasks("every monday standup")
        assert r and r[0][6] is None
        assert r[0][5] is not None            # repeat 在
        assert "monday" not in r[0][0].lower()

    def test_next_weekday_kept(self):
        r = PE.parse_tasks("call mom next monday")
        assert r and r[0][6] is not None


class TestEnglishUi:
    def test_dl_text(self):
        i18n.set_lang("en")
        assert M.NoteApp._dl_text("2026-11-09", "08:00") == "Nov 9, 08:00"
        i18n.set_lang("zh")
        assert M.NoteApp._dl_text("2026-11-09", "08:00") == "11月9日 08:00"

    def test_day_head_has_day(self):
        day = (dt.date.today() - dt.timedelta(days=6)).isoformat()
        i18n.set_lang("en")
        head = M.NoteApp._day_label(day, dt.date.today().isoformat())
        assert str(int(day[-2:])) in head, head       # 日号必须在
        assert "年" not in head and "月" not in head

    def test_undo_label_english(self):
        i18n.set_lang("en")
        assert "删除" not in i18n.t("undo_lbl_delete", t="milk")
        assert "tasks" in i18n.t("restore_row", d="2026-11-08", n=3, h=2)

    def test_cancel_done_hint_both_langs(self):
        for lang in ("zh", "en"):
            i18n.set_lang(lang)
            txt = i18n.t("cancel_done_hint")
            assert txt and not txt.startswith("cancel_done_hint")
        i18n.set_lang("zh")


# ------------------------------------------------------------ 6. 文案键完整
class TestI18nKeys:
    NEW_KEYS = ["cancel_done_hint", "restore_row", "undo_lbl_delete",
                "undo_lbl_rename", "undo_lbl_prio", "undo_lbl_done",
                "undo_lbl_undone", "undo_lbl_note", "undo_lbl_last",
                "the_nth_task"]

    @pytest.mark.parametrize("key", NEW_KEYS)
    def test_key_exists(self, key):
        item = i18n.STRINGS.get(key)
        assert item is not None and len(item) == 2, key

    def test_no_chinese_leaked_in_english_ui_strings(self):
        import re
        zh = re.compile(r"[\u4e00-\u9fff]")
        for key in ("restore_row", "undo_lbl_delete", "undo_lbl_last", "the_nth_task"):
            assert not zh.search(i18n.STRINGS[key][1]), key
