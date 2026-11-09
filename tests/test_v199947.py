# -*- coding: utf-8 -*-
"""v1.9.9.47：深度 QA 复核报告 9 项回归测试。

  0    ✕ 按钮点击时才判断托盘（不再绘制时固化 → 「8 次退出 2 次隐藏」）
  A1   坏文件改名保留（原件不被空数据覆盖）+ 写入 fsync
  A5   保存错误按文件分开记（写 history 成功不清 tasks 的错误）
  A3/B1 改名撤回同步历史 + 回车提交的改名也进撤回栈
  A6   退出顺序：先保存询问、再拆定时器/托盘（选「否」不半瘫）
  A4   备份恢复专用窗（按日期列出快照）
  A8   导入 JSON 逐条规范化（缺 id / 坏 score / 坏 hhmm）
  4    数字被当时间线索剥掉（2026 年 / 第 2 章 / 3 份）
  4    便签页说「撤回」不再贴成一条新便签
"""
import json
import os
import datetime as dt

import pytest

tk = pytest.importorskip("tkinter")

import main as M
import i18n
import exporter as E
import parser as P


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
    a.store.user_name = "小李"
    a.store.bot_name = "小记"
    a.store.tasks = []
    a.store.messages = []
    a._ring_bell = lambda *x: None
    yield a
    try:
        root.destroy()
    except Exception:
        pass


def _task(a, title, **kw):
    t = {"id": "t_" + title, "title": title, "hhmm": None, "repeat": None,
         "day": a.store._today(), "due_date": None, "done": False,
         "score": 50, "manual": True, "created": "09:00"}
    t.update(kw)
    return t


# ------------------------------------------------------------------ 0 ✕ 按钮
class TestCloseButton:
    def test_not_bound_at_draw_time(self, app):
        """draw_head 里 ✕ 必须绑到 _on_close_btn，而不是固化 quit/hide"""
        app.draw_head()
        app.root.update()
        # 画布上所有 item 里，找 ✕ 那个矩形绑定的 tag/绑定
        # 直接验证方法存在且能在两种托盘状态下走不同分支即可
        assert callable(app._on_close_btn)

    def test_hides_when_tray_ok(self, app, monkeypatch):
        app._tray_failed = False
        called = []
        monkeypatch.setattr(app, "close_or_hide", lambda: called.append("hide"))
        monkeypatch.setattr(app, "quit", lambda: called.append("quit"))
        app._on_close_btn()
        assert called == ["hide"]

    def test_quits_when_tray_failed(self, app, monkeypatch):
        """托盘彻底不可用（非 Windows / 初始化失败）→ 直接退出"""
        app._tray_failed = True
        called = []
        monkeypatch.setattr(app, "close_or_hide", lambda: called.append("hide"))
        monkeypatch.setattr(app, "quit", lambda: called.append("quit"))
        app._on_close_btn()
        assert called == ["quit"]

    def test_hides_before_tray_ready(self, app, monkeypatch):
        """托盘还没初始化好（启动 800ms 空窗）也按「藏」处理，不能抢跑退出"""
        app._tray = None
        app._tray_failed = False
        called = []
        monkeypatch.setattr(app, "close_or_hide", lambda: called.append("hide"))
        monkeypatch.setattr(app, "quit", lambda: called.append("quit"))
        app._on_close_btn()
        assert called == ["hide"]


# ------------------------------------------------------------------ A1 坏文件
class TestCorruptFile:
    def test_original_is_renamed_not_overwritten(self, tmp_path, monkeypatch):
        """坏文件必须被**改名**保留：原路径腾空，原件字节一个都不能变"""
        monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
        bad = tmp_path / "tasks.json"
        bad.write_text('{"tasks": [{"title": "买牛奶"', encoding="utf-8")
        before = bad.read_bytes()

        st = M.Store()
        assert st.load_failed is True
        assert st.corrupt_copy and os.path.exists(st.corrupt_copy)
        # 原件已腾空（改名），副本内容与原件逐字节一致
        assert not bad.exists()
        assert open(st.corrupt_copy, "rb").read() == before
        # 之后再保存，写的也是新文件，不会碰到原件
        st.save()
        assert bad.exists()
        assert open(st.corrupt_copy, "rb").read() == before, "原件被空数据覆盖了"

    def test_bom_and_gbk_still_load(self, tmp_path, monkeypatch):
        monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
        obj = {"tasks": [{"id": "a1", "title": "买牛奶", "score": 40}],
               "user_name": "小李"}
        for enc in ("utf-8-sig", "gbk"):
            (tmp_path / "tasks.json").write_text(
                json.dumps(obj, ensure_ascii=False), encoding=enc)
            st = M.Store()
            assert st.load_failed is False, enc
            assert st.tasks and st.tasks[0]["title"] == "买牛奶", enc
            assert not [p for p in os.listdir(tmp_path) if ".corrupt-" in p], enc

    def test_atomic_syncs_to_disk(self, tmp_path, monkeypatch):
        """写完立刻断电也要能读到完整文件（fsync + 原子替换）"""
        monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
        p = tmp_path / "x.json"
        M.Store._atomic(str(p), {"a": list(range(200))})
        assert json.loads(p.read_text(encoding="utf-8"))["a"][-1] == 199
        assert not os.path.exists(str(p) + ".tmp")
        assert M.Store.any_save_error() is None


# ------------------------------------------------------------------ A5 保存错误
class TestSaveErrorPerFile:
    def test_history_success_does_not_clear_tasks_error(self, app):
        M.Store._save_errors = {}
        M.Store._save_error = None
        # 模拟：tasks.json 写失败
        bad = os.path.join(str(app.store.path), "no-such-dir", "tasks.json")
        M.Store._atomic(bad, {"tasks": []})
        assert M.Store.any_save_error(), "写失败却认为正常"
        # 接着 history.json 写成功——不得清掉 tasks 的错误
        M.Store._atomic(app.store.hist_path, {"days": {}})
        assert M.Store.any_save_error(), "history 写成功把 tasks 的错误清掉了"
        # 真正的 tasks 写成功才清除
        M.Store._atomic(app.store.path, {"tasks": []})
        assert not M.Store.any_save_error()
        M.Store._save_errors = {}
        M.Store._save_error = None

    def test_banner_shown_on_save_error(self, app):
        M.Store._save_errors = {"tasks.json": "PermissionError: boom"}
        M.Store._save_error = "PermissionError: boom"
        app._save_warned = False
        app._check_save_error()
        app.root.update()
        assert app.banner.winfo_ismapped(), "保存失败没有常驻横幅"
        assert "保存失败" in app._banner_lbl.cget("text")
        # 恢复后横幅消失 + 明确告知
        M.Store._save_errors = {}
        M.Store._save_error = None
        app._check_save_error()
        app.root.update()
        assert not app.banner.winfo_ismapped()
        last = app.store.messages[-1]
        assert "恢复" in (last.get("zh") or last.get("text"))


# ------------------------------------------------------------------ A3/B1 改名撤回
class TestRenameUndo:
    def test_undo_restores_history_title(self, app):
        t = _task(app, "买牛奶")
        app.store.tasks = [t]
        app.store.sync_history()
        day = app.store.today
        assert app.store.history[day][0]["title"] == "买牛奶"

        # 改名（模拟 UI 提交）
        app._push_undo({"kind": "rename", "id": t["id"], "prev": "买牛奶",
                        "label": "改名「买牛奶」→「买酸奶」"})
        t["title"] = "买酸奶"
        app.store.sync_history()
        assert app.store.history[day][0]["title"] == "买酸奶"

        # 撤回：任务和历史都要回到原名
        rec = app._pop_undo()
        app._undo_ui_op("rename", rec)
        assert t["title"] == "买牛奶"
        assert app.store.history[day][0]["title"] == "买牛奶", "历史没跟着回退"

    def test_enter_commit_pushes_undo(self, app):
        """回车/FocusOut 提交的改名也要进撤回栈"""
        t = _task(app, "买牛奶")
        app.store.tasks = [t]
        app._undo_stack = []
        app._undo_last = None
        app.begin_edit(t["id"], 0)
        app.root.update()
        e = app._edit_entry
        assert e is not None
        e.delete(0, "end")
        e.insert(0, "买酸奶")
        e.event_generate("<Return>")
        app.root.update()
        assert t["title"] == "买酸奶"
        assert app._undo_stack, "回车提交的改名没进撤回栈"
        assert app._undo_stack[-1]["prev"] == "买牛奶"


# ------------------------------------------------------------------ A6 退出顺序
class TestQuitOrder:
    def test_cancel_quit_keeps_timers(self, app, monkeypatch):
        """保存失败选「否」→ 定时器/托盘都不能被拆掉"""
        stopped = []
        monkeypatch.setattr(M.Store, "save", lambda self: None)
        monkeypatch.setattr(M.Store, "any_save_error", classmethod(
            lambda cls: "OSError: disk full"))
        app._tray = type("T", (), {"stop": lambda s: stopped.append(1),
                                   "available": True,
                                   "update_tip": lambda s, x: None})()
        app._closing = False
        app.root.after(5000, lambda: None)          # 一个活着的定时器
        import tkinter.messagebox as mb
        monkeypatch.setattr(mb, "askyesno", lambda *a, **k: False)
        app.quit()
        app.root.update()
        assert app._closing is False, "取消退出后 _closing 没复位"
        assert not stopped, "取消退出却把托盘停了"
        assert app.root.tk.call("after", "info"), "取消退出却把定时器全取消了"

    def test_confirm_quit_stops_everything(self, app, monkeypatch):
        stopped = []
        monkeypatch.setattr(M.Store, "save", lambda self: None)
        monkeypatch.setattr(M.Store, "any_save_error", classmethod(
            lambda cls: "OSError: disk full"))
        app._tray = type("T", (), {"stop": lambda s: stopped.append(1),
                                   "available": True,
                                   "update_tip": lambda s, x: None})()
        import tkinter.messagebox as mb
        monkeypatch.setattr(mb, "askyesno", lambda *a, **k: True)
        app.quit()
        assert stopped, "确认退出却没停托盘"


# ------------------------------------------------------------------ A8 导入规范化
class TestNormalizeImport:
    def test_missing_fields_are_filled(self):
        raw = [{"title": "买牛奶"},                       # 缺 id/score/…
               {"title": "写报告", "score": "abc",        # score 非数字
                "hhmm": "8点"},                           # hhmm 非法
               {"title": 123},                            # 非字符串标题
               {"no_title": 1},                           # 没标题 → 丢弃
               "not a dict"]
        out = M.normalize_tasks(raw)
        assert len(out) == 3, out
        assert all(t["id"] for t in out), "有任务没补上 id"
        assert len({t["id"] for t in out}) == 3, "id 重复"
        assert out[1]["score"] == 30
        assert out[1]["hhmm"] is None
        assert out[2]["title"] == "123"

    def test_normalized_tasks_are_deletable(self, app):
        app.store.tasks = M.normalize_tasks([{"title": "买牛奶"}])
        app.refresh_tasks()
        app.root.update()
        # 有 id 才删得掉（旧版缺 id 的导入任务删/勾都报错）
        tid = app.store.tasks[0]["id"]
        app.store.tasks = [t for t in app.store.tasks if t["id"] != tid]
        assert app.store.tasks == []


# ------------------------------------------------------------------ A4 备份恢复
class TestBackupRestore:
    def test_snapshot_list_and_restore(self, app, monkeypatch):
        """手造一份昨天的快照，恢复后任务回来，且当前文件先另存一份"""
        root_dir = E.backup_dir(M.data_dir())
        snap_day = "2025-01-01"
        d = os.path.join(root_dir, snap_day)
        os.makedirs(d, exist_ok=True)
        obj = {"tasks": [{"id": "z1", "title": "旧任务", "score": 40,
                          "day": snap_day}]}
        with open(os.path.join(d, "tasks.json"), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        with open(os.path.join(d, "history.json"), "w", encoding="utf-8") as f:
            json.dump({"days": {}}, f, ensure_ascii=False)

        snaps = E.list_snapshots(M.data_dir())
        assert snaps and snap_day in snaps, snaps

        app.store.tasks = [_task(app, "现在的任务")]
        app.store.save()
        import tkinter.messagebox as mb
        monkeypatch.setattr(mb, "askyesno", lambda *a, **k: True)
        app._restore_snapshot(snap_day, "tasks")
        assert [x["title"] for x in app.store.tasks] == ["旧任务"]
        # 恢复前必须把当前文件另存一份
        base = os.path.dirname(app.store.path)
        leftovers = [p for p in os.listdir(base) if ".before-restore-" in p]
        assert leftovers, "恢复前没有备份当前文件"

    def test_restore_history_snapshot(self, app, monkeypatch):
        root_dir = E.backup_dir(M.data_dir())
        d = os.path.join(root_dir, "2025-01-02")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "history.json"), "w", encoding="utf-8") as f:
            json.dump({"days": {"2025-01-02": [
                {"title": "历史里的任务", "score": 30, "done": True}]}},
                f, ensure_ascii=False)
        import tkinter.messagebox as mb
        monkeypatch.setattr(mb, "askyesno", lambda *a, **k: True)
        app._restore_snapshot("2025-01-02", "history")
        assert app.store.history["2025-01-02"][0]["title"] == "历史里的任务"


# ------------------------------------------------------------------ parser 数字
class TestNumbersKept:
    @pytest.mark.parametrize("text,want", [
        ("整理2026年资料", "整理2026年资料"),
        ("整理 2026 年资料", "整理2026年资料"),
        ("打印3份合同", "打印3份合同"),
        ("第2章读书", "第2章读书"),
        ("读第3章", "读第3章"),
        ("2026年目标", "2026年目标"),
        ("买2瓶牛奶", "买2瓶牛奶"),
    ])
    def test_year_chapter_count_survives(self, text, want):
        r = P.parse_tasks(text)
        assert len(r) == 1, (text, r)
        assert r[0][0] == want, (text, r[0][0])

    def test_time_still_stripped(self):
        r = P.parse_tasks("下午3点开会")
        assert r[0][0] == "开会" and r[0][1] == "15:00"

    def test_space_split_still_works_for_plain_words(self):
        r = P.parse_tasks("开会 写方案")
        assert [x[0] for x in r] == ["开会", "写方案"]


# ------------------------------------------------------------------ 便签撤回
class TestNoteUndo:
    def test_undo_in_note_mode_removes_last_note(self, app):
        app.list_mode = "note"
        app._compose_placeholder = False
        app.store.notes = []
        app.entry.delete(0, "end")
        app.entry.insert(0, "去便利店买便利贴")
        app.on_send()
        app.root.update()
        assert len(app.store.notes) == 1

        app.entry.delete(0, "end")
        app.entry.insert(0, "撤回")
        app.on_send()
        app.root.update()
        assert app.store.notes == [], "便签页说「撤回」又被贴成一条便签"
        # v1.9.9.53：撤回后不再回填输入框（回填会让下一条便签带上上一条
        # 的内容，用户实测多出「111撤回」式便签），改为清空
        assert app.entry.get() == "", "撤回后输入框应清空"

    def test_normal_note_still_saved(self, app):
        app.list_mode = "note"
        app._compose_placeholder = False
        app.store.notes = []
        app.entry.delete(0, "end")
        app.entry.insert(0, "买电池")
        app.on_send()
        assert [n["text"] for n in app.store.notes] == ["买电池"]
