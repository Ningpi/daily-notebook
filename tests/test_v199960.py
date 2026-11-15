# -*- coding: utf-8 -*-
"""v1.9.9.60 回归测试：实测第七轮（导入丢字段 / 备份失败中止 / 清洗留档 /
吞符号 / 问候重复 / 确认框被盖 / 弹窗置顶 / 日期显示 / 删除回执 / 空态错位）"""
import datetime as dt
import json
import os
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


# ------------------------- 1. normalize_tasks 不再丢字段
class TestNormalizeKeepsFields:
    def test_remind_fields_survive(self):
        raw = [{"id": "t1", "title": "交周报", "hhmm": "18:00",
                "remind_before": 15, "remind_at": "17:45", "remind_day": 1,
                "reminded": True, "reminded_day": None, "_from_raw": True,
                "dur_min": 30, "deadline_txt": "今天下午六点",
                "last_done_day": "2026-11-08"}]
        out = M.normalize_tasks(raw)
        assert len(out) == 1
        t = out[0]
        assert t["remind_before"] == 15
        assert t["remind_at"] == "17:45"
        assert t["remind_day"] == 1
        assert t["reminded"] is True
        assert t["_from_raw"] is True
        assert t["dur_min"] == 30
        assert t["deadline_txt"] == "今天下午六点"
        assert t["last_done_day"] == "2026-11-08"
        assert "last_done" not in t

    def test_legacy_last_done_mapped(self):
        out = M.normalize_tasks([{"title": "背单词", "last_done": "2026-11-07",
                                  "streak": 3}])
        assert out[0]["last_done_day"] == "2026-11-07"
        assert "last_done" not in out[0]
        assert out[0]["streak"] == 3

    def test_empty_title_kept_with_placeholder(self):
        out = M.normalize_tasks([{"title": ""}, {"title": "  "},
                                 {"title": "买牛奶"}])
        assert len(out) == 3
        assert all(t["title"] for t in out)

    def test_bad_remind_values_clamped(self):
        out = M.normalize_tasks([{"title": "x", "remind_before": "abc",
                                  "remind_day": 99999, "remind_at": "25:00"}])
        t = out[0]
        assert t["remind_before"] == 0
        assert t["remind_day"] == 3650
        assert t["remind_at"] is None

    def test_restore_confirm_count_matches(self, app, tmp_path):
        """导入 3 条（1 条空标题）→ 确认框条数 = 实际导入条数"""
        src = tmp_path / "in.json"
        json.dump({"tasks": [{"title": "a"}, {"title": ""}, {"title": "b"}]},
                  open(src, "w", encoding="utf-8"))
        n = len(M.normalize_tasks(json.load(open(src, encoding="utf-8"))["tasks"]))
        assert n == 3


# ------------------------- 2. 备份失败必须中止
class TestBackupGuard:
    def test_missing_file_is_ok(self, app, tmp_path):
        assert app._backup_before_overwrite(
            [(str(tmp_path / "nope.json"), ".b-1")]) is None

    def test_copy_success(self, app, tmp_path):
        f = tmp_path / "tasks.json"
        f.write_text("{}", encoding="utf-8")
        assert app._backup_before_overwrite([(str(f), ".b-2")]) is None
        assert (tmp_path / "tasks.json.b-2").exists()

    def test_copy_failure_aborts(self, app, tmp_path):
        f = tmp_path / "tasks.json"
        f.write_text("{}", encoding="utf-8")
        # 目标目录不存在 → copy2 必失败
        bad = (".未存在目录" + os.sep + "x")
        err = app._backup_before_overwrite([(str(f), bad)])
        assert err and "tasks.json" in err


# ------------------------- 3. 读盘清洗：deadline_txt 保留 + 回写留档
class TestSanitizeStartup:
    def test_deadline_txt_kept_when_hhmm_bad(self):
        raw = {"id": "t", "title": "开会", "hhmm": "25:70",
               "deadline_txt": "下午七点"}
        t = M.Store._sanitize_task(raw, set())
        assert t["hhmm"] is None
        assert t["deadline_txt"] == "下午七点"

    def test_startup_writeback_keeps_copy(self, app, tmp_path):
        """启动清洗回写前先留 .before-fix-* 副本（保护在 Store.__init__）"""
        app.store.tasks = [{"id": "t", "title": "开会", "hhmm": "25:70",
                            "deadline_txt": "下午七点", "score": 50,
                            "day": app.store._today(), "repeat": None}]
        app.store.save()
        # 重新实例化 Store = 模拟下一次启动
        s2 = M.Store()
        assert getattr(s2, "_dirty_fix", False), "坏 hhmm 应触发清洗"
        copies = [f for f in os.listdir(str(tmp_path))
                  if f.startswith("tasks.json.before-fix-")]
        assert copies, "回写前应留 .before-fix-* 副本"
        disk = json.load(open(s2.path, encoding="utf-8"))
        kept = [t for t in disk["tasks"] if t["id"] == "t"][0]
        assert kept["deadline_txt"] == "下午七点"
        assert kept["hhmm"] is None

    def test_data_fixed_notice(self, app):
        app.store._dirty_fix = True
        app._first_hello()
        assert any(tr_msg.get("role") == "bot" and "before-fix" in
                   (tr_msg.get("text") or "") for tr_msg in app.store.messages)


# ------------------------- 4. 录入不再吞符号
class TestSymbolKeeper:
    def test_version_number(self, zh):
        assert core.parse_tasks("记 v1.9.9.59 的发布")[0][0] == "记v1.9.9.59的发布"

    def test_email(self, zh):
        assert core.parse_tasks("给 test@example.com 发邮件")[0][0] == \
            "给test@example.com发邮件"

    def test_decimal_and_code(self, zh):
        assert core.parse_tasks("3.5公里跑步")[0][0] == "3.5公里跑步"
        assert core.parse_tasks("会议室A-102开会")[0][0] == "会议室A-102开会"

    def test_normal_parse_unaffected(self, zh):
        r = core.parse_tasks("明天下午三点交数学报告")[0]
        assert r[0] == "交数学报告" and r[1] == "15:00"
        r2 = core.parse_tasks("每天20:30修电脑")[0]
        assert r2[0] == "修电脑" and r2[1] == "20:30"
        assert r2[5] == {"kind": "daily", "weekday": None, "monthday": None}


# ------------------------- 5. 问候语同一天只推一次
class TestGreetOnce:
    def test_second_launch_no_dup(self, app):
        app.store.user_name = "小林"
        app.store.setup_stage = 3
        app.store.messages = []
        app._first_hello()
        n1 = len(app.store.messages)
        assert n1 >= 1
        app._first_hello()
        assert len(app.store.messages) == n1, "同一天二次启动不应再推问候"
        assert app.store.greet_day == app.store._today()

    def test_next_day_pushes_again(self, app):
        app.store.user_name = "小林"
        app.store.setup_stage = 3
        app.store.messages = []
        app.store.greet_day = "2000-01-01"
        app._first_hello()
        assert len(app.store.messages) >= 1

    def test_greet_day_persisted(self, app):
        app.store.greet_day = "2026-11-10"
        app.store.save()
        disk = json.load(open(app.store.path, encoding="utf-8"))
        assert disk.get("greet_day") == "2026-11-10"


# ------------------------- 6. 置顶安全确认框
def _pump_until(root, cond, frames=400):
    for _ in range(frames):
        root.update()
        if cond():
            return True
        root.after(10, lambda: None)
        root.update()
    return cond()


class TestAskYesno:
    def test_no_when_closed(self, app):
        result = {}

        def _run():
            result["v"] = app._ask_yesno("t", "m")

        def _close_when_seen():
            for w in app.root.winfo_children():
                if isinstance(w, tk.Toplevel) and w.winfo_exists():
                    w.destroy()          # 等价于用户点 ×
                    return
            app.root.after(30, _close_when_seen)

        app.root.after(10, _run)
        app.root.after(60, _close_when_seen)
        _pump_until(app.root, lambda: "v" in result)
        assert result["v"] is False

    def test_yes_button(self, app):
        result = {}

        def _run():
            result["v"] = app._ask_yesno("t", "m")

        def _click_when_seen():
            for w in app.root.winfo_children():
                if isinstance(w, tk.Toplevel) and w.winfo_exists():
                    for c in w.winfo_children():
                        if c.winfo_class() == "Frame":
                            for b in c.winfo_children():
                                if b.winfo_class() == "Button" and \
                                        b.cget("text") == i18n.t("confirm_yes"):
                                    b.invoke()
                                    return
            app.root.after(30, _click_when_seen)

        app.root.after(10, _run)
        app.root.after(60, _click_when_seen)
        _pump_until(app.root, lambda: "v" in result)
        assert result["v"] is True

    def test_follows_topmost(self, app):
        """确认框跟随主窗置顶开关（修复「点恢复没反应」）"""
        app.store.topmost = True
        holder = {}

        def _run():
            # 借 _ask_yesno 的构造路径验证 topmost 属性：
            # 打开一个模态确认框，在关闭前记录属性
            def _grab():
                for w in app.root.winfo_children():
                    if isinstance(w, tk.Toplevel) and w.winfo_exists():
                        holder["flag"] = str(w.attributes("-topmost"))
                        w.destroy()
                        return
                app.root.after(30, _grab)
            app.root.after(20, _grab)
            holder["v"] = app._ask_yesno("t", "m")
        app.root.after(10, _run)
        _pump_until(app.root, lambda: "v" in holder and "flag" in holder)
        assert holder.get("flag") in ("1", "True")


# ------------------------- 7. 弹窗置顶与还原
class TestPopupRaise:
    def _flag(self, w):
        return str(w.attributes("-topmost")) in ("1", "True")

    def test_raise_keeps_topmost_on(self, app):
        app.store.topmost = True
        w = tk.Toplevel(app.root)
        w.attributes("-topmost", False)
        app._popup_raise(w)
        app.root.update()
        assert self._flag(w), "置顶开启时 raise 后应保持置顶"
        w.destroy()

    def test_raise_off_when_not_topmost(self, app):
        app.store.topmost = False
        w = tk.Toplevel(app.root)
        app._popup_raise(w)
        app.root.update()
        assert not self._flag(w)
        w.destroy()

    def test_daily_manager_topmost_follows(self, app):
        app.store.tasks = []
        app.open_daily_manager()
        app.root.update()
        win = app._dmgr_win
        assert win is not None and win.winfo_exists()
        assert bool(win.attributes("-topmost")) == bool(app.store.topmost)
        win.destroy()
        app._dmgr_win = None

    def test_toggle_top_syncs_popups(self, app):
        app.store.topmost = False
        w = tk.Toplevel(app.root)
        app._dmgr_win = w
        app.store.topmost = True
        app._sync_popups_topmost()
        app.root.update()
        assert str(w.attributes("-topmost")) in ("1", "True")
        w.destroy()
        app._dmgr_win = None

    def test_backup_window_reuse(self, app):
        app.open_backup_restore()
        app.root.update()
        w1 = app._restore_win
        app.open_backup_restore()
        app.root.update()
        assert app._restore_win is w1, "再次打开应复用并置顶，而不是叠新窗"
        w1.destroy()
        app._restore_win = None

    # ---- v1.9.9.60：真的能翻到最上层（用户实测「日常窗被历史窗压住」）
    def test_raise_buried_topmost_window(self, app):
        """两个常驻置顶窗重叠时，raise 后必须真的到最上面"""
        app.store.topmost = True
        t1 = tk.Toplevel(app.root)
        t1.geometry("300x300+200+200")
        app._popup_topmost(t1)
        t1.update()
        t2 = tk.Toplevel(app.root)
        t2.geometry("300x300+220+220")
        app._popup_topmost(t2)
        t2.update()
        assert not app._is_on_top(t1), "后建窗口应压住先建的"
        app._popup_raise(t1)
        for _ in range(5):
            app.root.update()
        assert app._is_on_top(t1), "raise 后应翻到最上层（消费级 bug）"
        t1.destroy()
        t2.destroy()

    def test_is_on_top_false_when_covered(self, app):
        t1 = tk.Toplevel(app.root)
        t1.geometry("300x300+200+200")
        t1.update()
        t2 = tk.Toplevel(app.root)
        t2.geometry("300x300+210+210")
        t2.update()
        assert app._is_on_top(t2)
        assert not app._is_on_top(t1)
        t1.destroy()
        t2.destroy()

    def test_clock_buried_then_click_raises(self, app):
        """时钟被盖住时再点底栏是「唤回来」，不是静默关掉"""
        app.open_clock()
        for _ in range(10):
            app.root.update()
        win = app._clock_win
        cover = tk.Toplevel(app.root)
        cover.geometry("%dx%d+%d+%d" % (win.winfo_width(),
                                        win.winfo_height(),
                                        win.winfo_rootx(), win.winfo_rooty()))
        cover.update()
        assert not app._is_on_top(win)
        app.open_clock()
        for _ in range(10):
            app.root.update()
        assert win.winfo_exists(), "被盖住的时钟再点不应关闭"
        assert app._is_on_top(win), "应翻到最上层"
        cover.destroy()
        app._close_clock()

    def test_clock_on_top_click_still_closes(self, app):
        """在最上层时再点仍是关闭（保留开关手感）"""
        app.open_clock()
        for _ in range(10):
            app.root.update()
        win = app._clock_win
        assert app._is_on_top(win)
        app.open_clock()
        for _ in range(5):
            app.root.update()
        assert not win.winfo_exists()


# ------------------------- 8. 日期任务显示
class TestDateOnlyDisplay:
    def test_note_date_not_padded(self, app):
        """便签时间列日期不补零（「11/1」而不是「11/01」）"""
        d = dt.date.today() - dt.timedelta(days=9)
        s = M.NoteApp._note_time_text(d.isoformat(), "09:00")
        assert "%d/%d" % (d.month, d.day) in s, s
        assert "%02d/%02d" % (d.month, d.day) not in s, s

    def test_row_time_text_due_only(self, app):
        tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        t = {"id": "x", "title": "交方案", "hhmm": None, "due_date": tomorrow,
             "repeat": None, "day": app.store._today()}
        txt = app._row_time_text(t)
        m, d = int(tomorrow[5:7]), int(tomorrow[8:10])
        assert txt == "%d/%d前" % (m, d)

    def test_row_time_text_today_due_hidden(self, app):
        t = {"id": "x", "title": "交方案", "hhmm": None,
             "due_date": app.store._today(), "repeat": None}
        assert app._row_time_text(t) == ""

    def test_draw_row_paints_date(self, app):
        tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
        app.store.tasks = [{"id": "x", "title": "交方案", "hhmm": None,
                            "due_date": tomorrow, "score": 50, "done": False,
                            "repeat": None, "day": app.store._today(),
                            "created": ""}]
        app.refresh_tasks(scroll_top=True)
        app.root.update()
        texts = []
        for i in app.list_cv.find_withtag("all"):
            try:
                texts.append(app.list_cv.itemcget(i, "text"))
            except Exception:
                pass                # 矩形等图形项没有 -text
        assert any("前" in t for t in texts), "日期任务行首应出现 M/D前"


# ------------------------- 9. 删除回执
class TestDeleteReceipt:
    def test_right_click_delete_pushes_receipt(self, app):
        t = {"id": "x", "title": "买牛奶", "hhmm": None, "score": 50,
             "done": False, "repeat": None, "day": app.store._today(),
             "created": "", "due_date": None}
        app.store.tasks = [t]
        app.store.messages = []
        app.delete_task("x")
        texts = [m.get("text", "") for m in app.store.messages]
        assert any("买牛奶" in s and "已删除" in s for s in texts)


# ------------------------- 10. i18n 完整性
class TestI18n:
    @pytest.mark.parametrize("key", ["confirm_yes", "confirm_no",
                                     "backup_fail_abort", "data_fixed"])
    def test_bilingual(self, key):
        zh_v = i18n.render(key, {}, "zh")
        en_v = i18n.render(key, {}, "en")
        assert zh_v and en_v
        assert not any("\u4e00" <= ch <= "\u9fff" for ch in en_v), \
            "英文文案里不应残留中文"


# ------------------------- 11. 空态占位用画布实时宽度
class TestEmptyHintCentered:
    def test_hint_uses_live_width(self, app):
        app.store.tasks = []
        app.refresh_tasks(scroll_top=True)
        for _ in range(20):
            app.root.update()
        cv = app.list_cv
        w = cv.winfo_width()
        assert w > 40
        # 找「还没有任务」提示文字，其中心 x 应接近画布中线
        for i in cv.find_withtag("all"):
            txt = cv.itemcget(i, "text")
            if "还没有任务" in txt:
                x = cv.coords(i)[0]
                assert abs(x - w / 2) < w * 0.2, \
                    "空态提示应水平居中（x=%s, w=%s）" % (x, w)
                break
        else:
            pytest.fail("空态提示未绘制")
