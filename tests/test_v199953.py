# -*- coding: utf-8 -*-
"""v1.9.9.53 回归：真人实测第五轮反馈。

  1. 首次引导文字冒出气泡框 —— 画布宽度变化后气泡没按新宽度重排
     （Windows 上个别 <Configure> 事件丢失），加 0.5s 看门狗兜底；
  2. 默认设置对齐用户期望：透明度 95% / 字体大小 100% / 字体深浅 45%
     （前两项原本就是，深浅旧默认是自动推导=0%，字太浅）；
  3. 日历窗切语言后「跳到/跳转/今天/图例」还是旧语言 —— 整窗重建；
  4. 相似任务判定太松：「英语」vs「完成英语作业」也被拦 ——
     归一化后核心词完全一致才算相似；软完成语（「今天做了背单词」）
     改由打卡引导承接，不再靠宽松匹配兜底；
  5. 便签：右键加「详情」看全文；撤回后清空输入框（旧版回填内容，
     下一条便签变成「111撤回」）；跨天便签时间加「昨天/前天/M/D」前缀。
"""
import datetime as dt
import json
import os

import pytest

import main as M
import i18n

tk = pytest.importorskip("tkinter")


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


# ------------------------------------------------------------ 1. 看门狗
class TestBubbleWatchdog:
    def test_watchdog_method_exists(self, app):
        assert hasattr(app, "_watch_canvas_width")
        app._watch_canvas_width()          # 跑一遍不抛异常即可

    def test_width_change_triggers_rerender(self, app):
        a = app
        a.root.update()
        cv = a.chat_cv
        real_w = max(cv.winfo_width(), 40)
        a._chat_last_w = real_w + 100      # 伪造一次「宽度已变」
        called = []
        orig = a.render_messages

        def spy():
            called.append(1)
            orig()
        a.render_messages = spy
        a._watch_canvas_width()
        import time as _t
        _t.sleep(0.08)                     # 等 debounce 的 40ms 定时器
        a.root.update()
        assert called, "宽度变化后应触发对话重排"


# ------------------------------------------------------------ 2. 默认设置
class TestDefaults:
    def test_darken_default_45(self, data_dir):
        st = make_store(data_dir)          # 全新安装
        assert st.alpha == pytest.approx(0.95)
        assert st.font_scale == pytest.approx(1.0)
        assert st.text_darken == pytest.approx(0.45)

    def test_darken_missing_in_file(self, data_dir):
        """老用户的文件里没有 text_darken 字段：也落到 45%，不再自动=0%"""
        st = make_store(data_dir, {"tasks": []})
        assert st.text_darken == pytest.approx(0.45)

    def test_darken_saved_roundtrip(self, data_dir):
        st = make_store(data_dir)
        st.save()
        st2 = make_store(data_dir)
        assert st2.text_darken == pytest.approx(0.45)


# ------------------------------------------------------------ 3. 日历切语言
class TestCalendarRelang:
    def test_rebuild_keeps_ym(self, app):
        a = app
        a.open_calendar_view()
        a.root.update()
        win = a._cal_win
        a._cal_y, a._cal_m = 2027, 3
        a.switch_lang("en", announce=False)
        a.root.update()
        assert a._cal_win is not None and a._cal_win is not win
        assert a._cal_win.winfo_exists()
        assert (a._cal_y, a._cal_m) == (2027, 3)
        assert i18n.get_lang() == "en"
        # 图例等静态控件换成英文
        assert "One-off" in str(a._cal_legend_temp.cget("text"))
        a.switch_lang("zh", announce=False)
        a.root.update()
        assert "待办" in str(a._cal_legend_temp.cget("text"))
        a._cal_win.destroy()
        a._cal_win = None


# ------------------------------------------------------------ 4. 相似判定
class TestSimilarStrict:
    def test_exact_and_filler_same(self):
        assert M.NoteApp._same_title("买牛奶", "买牛奶")
        assert M.NoteApp._same_title("买牛奶", "买牛奶吧")
        assert M.NoteApp._same_title("买牛奶", "买牛奶了")
        assert M.NoteApp._same_title("买 牛 奶", "买牛奶")
        assert M.NoteApp._same_title("交周报", "请交一下周报")
        assert M.NoteApp._same_title("取消写周报", "写周报")

    def test_substring_no_longer_similar(self):
        """用户实测：已有「英语」，再输「完成英语作业」不该被拦"""
        assert not M.NoteApp._same_title("英语", "英语作业")
        assert not M.NoteApp._same_title("英语", "完成英语作业")
        assert not M.NoteApp._same_title("英语", "请英语语法句子")
        assert not M.NoteApp._same_title("开会", "开电话会议")

    def test_find_similar_uses_new_rule(self, app):
        a = app
        a.store.tasks = [{"id": "t1", "title": "英语", "hhmm": None,
                          "score": 50, "done": False}]
        assert a._find_similar("英语作业") is None
        assert a._find_similar("英语") == "英语"

    def test_soft_done_still_guided(self, app):
        """「今天做了背单词」：相似判定加严后不再建「做了背单词」，
        由打卡引导承接"""
        a = app
        send(a, "每天早上八点背单词")
        send(a, "不用")                       # 结束优先级追问
        send(a, "今天做了背单词")
        titles = [t["title"] for t in a.store.tasks]
        assert titles == ["背单词"], "软完成语产生了副作用：%s" % titles

    def test_checkin_variants_no_side_effect(self, app):
        for w in ("背单词打卡了", "打个卡 背单词", "今日背单词打卡",
                  "今天做了背单词", "今天背了单词"):
            a = app
            send(a, "每天早上八点背单词")
            send(a, "不用")
            send(a, w)
            titles = [t["title"] for t in a.store.tasks]
            assert titles == ["背单词"], "%s 产生了副作用：%s" % (w, titles)


# ------------------------------------------------------------ 5. 便签
class TestNotes:
    def test_undo_clears_entry(self, app):
        """撤回后不再回填内容（旧版回填 → 下一条便签变成「111撤回」）"""
        a = app
        a.list_mode = "note"
        send(a, "111")
        send(a, "222")
        send(a, "撤回")
        assert [n["text"] for n in a.store.notes] == ["111"]
        assert a.entry.get() == "", "撤回后输入框应清空"
        send(a, "333")
        assert [n["text"] for n in a.store.notes] == ["111", "333"], \
            "撤回后紧接着记录，不应带上旧内容"

    def test_time_text_today(self, app):
        today = dt.date.today().isoformat()
        assert M.NoteApp._note_time_text(today, "10:59") == "10:59"
        assert M.NoteApp._note_time_text("", "10:59") == "10:59"
        assert M.NoteApp._note_time_text(None, "10:59") == "10:59"

    def test_time_text_relative(self, app):
        y = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        d2 = (dt.date.today() - dt.timedelta(days=2)).isoformat()
        assert "昨天" in M.NoteApp._note_time_text(y, "10:59")
        assert "10:59" in M.NoteApp._note_time_text(y, "10:59")
        assert "前天" in M.NoteApp._note_time_text(d2, "08:00")

    def test_time_text_older_shows_date(self, app):
        d = dt.date.today() - dt.timedelta(days=9)
        s = M.NoteApp._note_time_text(d.isoformat(), "09:00")
        assert "%d/%d" % (d.month, d.day) in s

    def test_note_menu_has_detail(self, app):
        """右键菜单应有「详情」项"""
        a = app
        a.list_mode = "note"
        send(a, "一条长便签")
        nid = a.store.notes[0]["id"]
        # 不真正弹菜单（会阻塞），只验证入口存在
        assert hasattr(a, "_note_detail")
        assert i18n.t("menu_detail")

    def test_note_detail_window(self, app):
        a = app
        a.list_mode = "note"
        send(a, "很长" * 200)
        a._note_detail(a.store.notes[0]["id"])
        a.root.update()
        win = getattr(a, "_note_detail_win", None)
        assert win is not None and win.winfo_exists()
        win.destroy()

    def test_long_note_kept_full(self, app):
        """长便签存储不截断，详情窗能拿到全文"""
        a = app
        a.list_mode = "note"
        send(a, "内容" * 500)                 # 1000 字
        assert len(a.store.notes[0]["text"]) == 1000


# ------------------------------------------------- 6. v1.9.9.54 关于窗
class TestAbout:
    def test_dots_button_and_window(self, app):
        """标题栏「···」按钮 + 关于窗：三节内容 + 版本号"""
        a = app
        a.open_about()
        a.root.update()
        win = getattr(a, "_about_win", None)
        assert win is not None and win.winfo_exists()
        # 再次点击不重复开窗
        a.open_about()
        assert a._about_win is win
        # 窗里有一个 Text，内容包含三节标题和版本号
        texts = [w for w in a._about_win.winfo_children()
                 if isinstance(w, tk.Text)] or \
                [c for f in a._about_win.winfo_children()
                 if isinstance(f, tk.Frame)
                 for c in f.winfo_children() if isinstance(c, tk.Text)]
        assert texts, "关于窗里没找到正文 Text"
        content = texts[0].get("1.0", "end")
        for key in ("about_sec_intro", "about_sec_tips", "about_sec_feat"):
            assert i18n.t(key) in content, "缺少小节：%s" % i18n.t(key)
        assert M.VERSION in content, "页脚缺版本号"
        win.destroy()

    def test_about_bilingual(self, app):
        a = app
        i18n.set_lang("en")
        a.open_about()
        a.root.update()
        texts = [c for f in a._about_win.winfo_children()
                 if isinstance(f, tk.Frame)
                 for c in f.winfo_children() if isinstance(c, tk.Text)]
        content = texts[0].get("1.0", "end")
        assert "What is this" in content and "Features" in content
        a._about_win.destroy()

    def test_lang_switch_rebuilds_about(self, app):
        a = app
        a.open_about()
        a.root.update()
        win = a._about_win
        a.switch_lang("en", announce=False)
        a.root.update()
        assert a._about_win is not None and a._about_win is not win
        assert a._about_win.winfo_exists()
        a._about_win.destroy()
