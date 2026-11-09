# -*- coding: utf-8 -*-
"""v1.9.9.59 回归测试：用户真人实测第六轮反馈 8 项修复

1. 字体调大后气泡文字溢出窗口/气泡框（宽度缓存未失效）
2. 空状态「今天还没有任务」随窗口居中
3. 便签详情窗增加「修改内容」
4. 「背英语单词的时间改为…」误改「英语」
5. 右键编辑内容定位到错误任务行
6. 日常任务右键无「调整优先级」
7. 哲言判定排除非今日日常
8. 已开弹窗再点底栏按钮时置顶还原
"""
import datetime as dt
import pytest

tk = pytest.importorskip("tkinter")
import main as M
import i18n


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


def _daily(a, title, hhmm=None, rep=None):
    t = {"id": "d_%s" % title, "title": title, "score": 0, "done": False,
         "done_at": None, "hhmm": hhmm, "due_date": None,
         "day": a.store._today(), "repeat": rep or {"kind": "daily"},
         "created": "08:00"}
    a.store.tasks.append(t)
    return t


def _tmp(a, title, score=50, hhmm=None, due=None):
    t = {"id": "t_%s" % title, "title": title, "score": score, "done": False,
         "done_at": None, "hhmm": hhmm, "due_date": due, "repeat": None,
         "day": a.store._today(), "created": "08:00"}
    a.store.tasks.append(t)
    return t


# ------------------------- 1. 字号变化后气泡不溢出
class TestBubbleFont:
    def test_cache_cleared_on_font_change(self, app):
        """字号原地 configure 后，字符宽度缓存必须清空（溢出根因）"""
        a = app
        a.store.messages.append({"role": "bot", "text": "初次见面，你希望我怎么称呼您呢？（比如「你叫我小李吧」）不想设也行，直接说事情就好，比如「明天下午3点开会」。"})
        a.render_messages()
        a.root.update()
        assert a._charw_cache, "渲染后应有宽度缓存"
        a.store.font_scale = 1.3
        a._build_fonts()
        assert a._charw_cache == {}, "字号变化后字符宽度缓存应清空"
        assert a._width_cache == {}

    def test_no_overflow_after_font_grow(self, app):
        """字号调大后重排，文字与气泡都不超出画布右缘"""
        a = app
        a.store.messages.append({"role": "bot", "text": "初次见面，你希望我怎么称呼您呢？（比如「你叫我小李吧」）不想设也行，直接说事情就好，比如「明天下午3点开会」。"})
        a.render_messages()
        a.root.update()
        a.store.font_scale = 1.3
        a._build_fonts()
        a.render_messages()
        a.root.update()
        cv = a.chat_cv
        w = cv.winfo_width()
        mx_t = mx_p = 0
        for it in cv.find_all():
            bb = cv.bbox(it)
            if not bb:
                continue
            if cv.type(it) == "text":
                mx_t = max(mx_t, bb[2])
            elif cv.type(it) == "polygon":
                mx_p = max(mx_p, bb[2])
        assert mx_t <= w + 1, "文本最右 %s 超出画布 %s" % (mx_t, w)
        assert mx_p <= w + 1, "气泡最右 %s 超出画布 %s" % (mx_p, w)

    def test_narrow_window_no_overflow(self, app):
        """窄窗口 + 大字号也不溢出"""
        a = app
        a.store.font_scale = 1.3
        a._build_fonts()
        a.root.geometry("330x660+20+20")
        a.root.update()
        a.store.messages.append({"role": "me", "text": "明天下午3点开一个很长的会议需要准备很多材料并且通知所有人参加"})
        a.render_messages()
        a.root.update()
        cv = a.chat_cv
        w = cv.winfo_width()
        mx = 0
        for it in cv.find_all():
            bb = cv.bbox(it)
            if bb and cv.type(it) in ("text", "polygon"):
                mx = max(mx, bb[2])
        assert mx <= w + 1


# ------------------------- 2. 空状态居中
class TestEmptyHint:
    def test_empty_hint_centered(self, app):
        a = app
        a.store.tasks = []
        a.refresh_tasks()
        a.root.update()
        cv = a.list_cv
        ch = cv.winfo_height()
        hint = None
        for it in cv.find_all():
            if cv.type(it) == "text" and "还没有任务" in cv.itemcget(it, "text"):
                hint = it
        assert hint is not None, "应画出空状态提示"
        bb = cv.bbox(hint)
        cy = (bb[1] + bb[3]) / 2
        assert abs(cy - ch / 2) < 50, "提示应大致居中（cy=%.0f, 中线=%.0f）" % (cy, ch / 2)

    def test_empty_hint_follows_resize(self, app):
        a = app
        a.refresh_tasks()
        a.root.update()
        cv = a.list_cv
        a.root.geometry("430x900+20+20")
        a.root.update()
        a.refresh_tasks()
        a.root.update()
        ch = cv.winfo_height()
        hint = None
        for it in cv.find_all():
            if cv.type(it) == "text" and "还没有任务" in cv.itemcget(it, "text"):
                hint = it
        assert hint is not None
        bb = cv.bbox(hint)
        cy = (bb[1] + bb[3]) / 2
        assert abs(cy - ch / 2) < 60, "窗口变高后提示应跟着居中"

    def test_empty_hint_viewport_not_scrolled(self, app):
        """空态滚动区钉在可视高度，不会被残留滚动位置顶出屏幕"""
        a = app
        a.refresh_tasks()
        a.root.update()
        cv = a.list_cv
        sr = cv.cget("scrollregion").split()
        assert len(sr) == 4
        assert float(sr[3]) <= cv.winfo_height() + 2


# ------------------------- 3. 便签详情可修改
class TestNoteDetailEdit:
    def _widgets(self, win):
        out = []
        stack = list(win.winfo_children())
        while stack:
            w = stack.pop()
            out.append(w)
            stack.extend(w.winfo_children())
        return out

    def test_detail_has_edit_and_save(self, app):
        a = app
        today = a.store._today()
        a.store.notes.append({"id": "n1", "text": "今天吃的挺饱的。",
                              "day": today, "created": "19:27"})
        a._note_detail("n1")
        a.root.update()
        win = a._note_detail_win
        assert win.winfo_exists()
        btns = [w for w in self._widgets(win) if isinstance(w, tk.Button)]
        labels = [b.cget("text") for b in btns]
        assert i18n.t("note_detail_edit") in labels, "应有「修改内容」按钮"
        assert i18n.t("note_detail_close") in labels
        texts = [w for w in self._widgets(win) if isinstance(w, tk.Text)]
        assert len(texts) == 1
        txt = texts[0]
        assert txt.cget("state") == "disabled", "默认只读"
        # 点「修改内容」→ 可编辑，按钮变「保存」
        edit_btn = next(b for b in btns if b.cget("text") == i18n.t("note_detail_edit"))
        edit_btn.invoke()
        a.root.update()
        assert str(txt.cget("state")) == "normal"
        assert edit_btn.cget("text") == i18n.t("note_detail_save")
        # 改内容 → 保存 → 写回便签
        txt.delete("1.0", "end")
        txt.insert("1.0", "今天吃的挺饱的，但是饭很难吃。")
        edit_btn.invoke()
        a.root.update()
        assert a.store.notes[0]["text"] == "今天吃的挺饱的，但是饭很难吃。"
        # 时间行不混进正文
        assert "19:27" not in a.store.notes[0]["text"]

    def test_detail_win_reuses_existing(self, app):
        a = app
        a.store.notes.append({"id": "n2", "text": "x", "day": a.store._today(),
                              "created": "10:00"})
        a._note_detail("n2")
        w1 = a._note_detail_win
        a._note_detail("n2")
        assert a._note_detail_win is w1, "重复打开应复用并置顶"


# ------------------------- 4. 改时间/删除按「最像」匹配
class TestBestMatch:
    def test_reschedule_picks_full_title(self, app):
        a = app
        en = _daily(a, "英语", hhmm="20:00")
        bei = _daily(a, "背英语单词")
        a.refresh_tasks()
        a.entry.delete(0, "end")
        a._compose_placeholder = False
        a.entry.insert(0, "背英语单词的时间改为每天早上八点")
        a.on_send()
        a.root.update()
        assert bei["hhmm"] == "08:00", "应改「背英语单词」的时间"
        assert en["hhmm"] == "20:00", "「英语」的时间不应被动"

    def test_delete_picks_full_title(self, app):
        a = app
        en = _daily(a, "英语")
        bei = _daily(a, "背英语单词")
        a.refresh_tasks()
        a.entry.delete(0, "end")
        a._compose_placeholder = False
        a.entry.insert(0, "删除背英语单词")
        a.on_send()
        a.root.update()
        titles = [t["title"] for t in a.store.tasks]
        assert "英语" in titles, "不能误删「英语」"
        assert "背英语单词" not in titles

    def test_exact_beats_contains(self, app):
        a = app
        _tmp(a, "英语", score=90)
        target = _tmp(a, "英语作业", score=10)
        assert a._best_task("英语作业") is target


# ------------------------- 5. 右键编辑定位到正确行
class TestMenuEditPosition:
    def test_edit_lands_on_target_row(self, app):
        a = app
        _daily(a, "英语", hhmm="08:00")
        _daily(a, "背英语单词")
        _tmp(a, "物理", hhmm="17:00", due=(dt.date.today() +
             dt.timedelta(days=1)).isoformat())
        _tmp(a, "英语", hhmm="20:00")
        _tmp(a, "数学", hhmm="15:00", due=(dt.date.today() +
             dt.timedelta(days=1)).isoformat())
        a.refresh_tasks()
        a.root.update()
        target = next(t for t in a.store.tasks if t["title"] == "背英语单词")
        assert target["id"] in a._row_y, "渲染后应记录每行坐标"
        a._menu_edit(target["id"])
        a.root.update()
        cv = a.list_cv
        xy = cv.coords(a._edit_item)
        rh = a.row_height()
        expect = a._row_y[target["id"]] + rh / 2
        assert abs(xy[1] - expect) < 2, \
            "编辑框应落在目标行（y=%.0f，期望 %.0f）" % (xy[1], expect)


# ------------------------- 6. 日常任务无优先级菜单
class TestDailyNoPriority:
    def _capture_menu(self, a, tid):
        menus = []
        orig = tk.Menu.tk_popup

        def fake(self, *ar, **kw):
            menus.append(self)
            return ""
        tk.Menu.tk_popup = fake
        try:
            a.row_menu(type("E", (), {"x_root": 10, "y_root": 10})(), tid)
        finally:
            tk.Menu.tk_popup = orig
        return menus[0] if menus else None

    def _labels(self, m):
        out = []
        try:
            n = m.index("end")
        except Exception:
            n = -1
        for i in range((n or -1) + 1):
            try:
                out.append(str(m.entrycget(i, "label")))
            except Exception:
                out.append(None)
        return out

    def test_daily_menu_has_no_priority(self, app):
        a = app
        _daily(a, "背英语单词")
        a.refresh_tasks()
        m = self._capture_menu(a, "d_背英语单词")
        assert m is not None
        labels = self._labels(m)
        assert i18n.t("menu_priority") not in labels, "日常任务右键不应有优先级"
        assert i18n.t("menu_toggle") in labels

    def test_tmp_menu_keeps_priority(self, app):
        a = app
        _tmp(a, "买牛奶")
        a.refresh_tasks()
        m = self._capture_menu(a, "t_买牛奶")
        labels = self._labels(m)
        assert i18n.t("menu_priority") in labels, "临时任务保留优先级"


# ------------------------- 7. 哲言判定排除非今日日常
class TestQuoteTodayScope:
    def _last_bot(self, a):
        for m in reversed(a.store.messages):
            if m.get("role") == "bot":
                return m.get("text", "")
        return ""

    def test_quote_ignores_not_today_daily(self, app):
        """唯一的临时任务勾掉即全部完成——每周X的日常不挡哲言"""
        a = app
        wd = (dt.date.today().weekday() + 1) % 7      # 明天的星期 → 今天不该做
        _daily(a, "背英语单词", rep={"kind": "weekly", "weekday": wd})
        milk = _tmp(a, "买牛奶")
        a.refresh_tasks()
        a.toggle_done(milk["id"])
        a.root.update()
        txt = self._last_bot(a)
        assert "全部收工" in txt, "非今日日常不应挡住哲言（实际：%s）" % txt[:60]
        assert "1 件全部收工" in txt, "件数应按今日口径（实际：%s）" % txt[:60]

    def test_quote_after_daily_reorg(self, app):
        """删日常、加日常后：今天只剩临时任务且全完成 → 哲言照弹"""
        a = app
        wd1 = (dt.date.today().weekday() + 2) % 7
        wd2 = (dt.date.today().weekday() + 3) % 7
        _daily(a, "唱歌", rep={"kind": "weekly", "weekday": wd1})
        _daily(a, "画画", rep={"kind": "weekly", "weekday": wd2})
        t1 = _tmp(a, "数学")
        t2 = _tmp(a, "物理")
        a.refresh_tasks()
        a.toggle_done(t1["id"])
        a.toggle_done(t2["id"])
        a.root.update()
        txt = self._last_bot(a)
        assert "全部收工" in txt

    def test_not_all_done_still_no_quote(self, app):
        """今天还有没做完的 → 不弹哲言（回归保护）"""
        a = app
        _daily(a, "背单词")
        t1 = _tmp(a, "数学")
        a.refresh_tasks()
        a.toggle_done(t1["id"])
        a.root.update()
        txt = self._last_bot(a)
        assert "全部收工" not in txt


# ------------------------- 8. 已开弹窗再点底栏 → 置顶还原
class TestPopupRaise:
    def test_clock_minimized_then_click_raises(self, app):
        a = app
        a.open_clock()
        a.root.update()
        win = a._clock_win
        win.withdraw()
        a.root.update()
        a.open_clock()                # 最小化状态下再点 → 还原而不是关闭
        a.root.update()
        assert win.winfo_exists(), "最小化的时钟再点不应被关闭"
        assert win.wm_state() == "normal", "应从最小化还原"
        assert win.winfo_viewable()
        a._close_clock()

    def test_clock_visible_then_click_closes(self, app):
        """可见状态下再点仍是关闭（保留原开关行为）"""
        a = app
        a.open_clock()
        a.root.update()
        win = a._clock_win
        a.open_clock()
        a.root.update()
        assert not win.winfo_exists()

    def test_daily_manager_minimized_raises(self, app):
        a = app
        a.open_daily_manager()
        a.root.update()
        win = a._dmgr_win
        win.withdraw()
        a.root.update()
        a.open_daily_manager()
        a.root.update()
        assert win.wm_state() == "normal" and win.winfo_viewable()

    def test_calendar_minimized_raises(self, app):
        a = app
        a.open_calendar_view()
        a.root.update()
        win = a._cal_win
        win.withdraw()
        a.root.update()
        a.open_calendar_view()
        a.root.update()
        assert win.wm_state() == "normal" and win.winfo_viewable()
        win.destroy()
        a._cal_win = None

    def test_about_minimized_raises(self, app):
        a = app
        a.open_about()
        a.root.update()
        win = a._about_win
        win.withdraw()
        a.root.update()
        a.open_about()
        a.root.update()
        assert win.wm_state() == "normal" and win.winfo_viewable()
        win.destroy()
        a._about_win = None

    def test_history_minimized_raises(self, app):
        a = app
        a.open_history()
        a.root.update()
        win = a._hist_win
        win.withdraw()
        a.root.update()
        a.open_history()
        a.root.update()
        assert win.wm_state() == "normal" and win.winfo_viewable()
