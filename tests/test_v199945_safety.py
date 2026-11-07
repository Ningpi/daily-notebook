# -*- coding: utf-8 -*-
"""v1.9.9.45：QA 报告逐条核实后的回归测试。

覆盖：
  A1 任务文件损坏 → 原件另存副本、不再静默清空
  A2 历史文件损坏 → 原件另存副本、本次不覆盖
  A3 删除/改名只影响今天的历史（不抹掉过去所有天）
  A4 备份每次保存前覆盖（不再是当天开机空壳）
  A5/A6 保存失败有提示（运行期 + 退出确认）
  A7 便签不截断、删除可撤回
  A8 导出 JSON 含对话记录、文件名到秒
  A9 待答时含字母的正文不再被当成选项吞掉
  A10 标题不再硬截断到 24 字
  B1 行内编辑的按键兜底路由到编辑框
  B3 发送异常时原文回到输入框
  B4 一条坏时间不影响其他任务提醒
  B5 一个坏字段不再连累后面的设置
  C2 同日两个同名任务在历史里是两行
"""
import datetime as dt
import json
import os

import pytest

tk = pytest.importorskip("tkinter")

import main as M


# ------------------------------------------------------------------ Store 层
def _store(tmp_path, tasks_obj=None, raw=None, hist_raw=None, name="tasks.json"):
    path = tmp_path / name
    if raw is not None:
        path.write_bytes(raw)
    elif tasks_obj is not None:
        path.write_text(json.dumps(tasks_obj, ensure_ascii=False), encoding="utf-8")
    if hist_raw is not None:
        (tmp_path / "history.json").write_bytes(hist_raw)
    return path


def test_corrupt_tasks_keeps_copy(tmp_path, monkeypatch):
    """A1：截断的 tasks.json 不再被无声覆盖"""
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    bad = '{"tasks": [{"id": "1", "title": "买牛奶"}, {"id": "2"'
    _store(tmp_path, raw=bad.encode("utf-8"))
    s = M.Store()
    assert s.load_failed is True
    assert s.tasks == []
    assert s.corrupt_copy and os.path.exists(s.corrupt_copy)
    # 副本内容与原件一字不差（可人工抢救）
    with open(s.corrupt_copy, "rb") as f:
        assert f.read() == bad.encode("utf-8")


def test_tasks_with_bom_readable(tmp_path, monkeypatch):
    """A1 延伸：记事本「UTF-8 带 BOM」也能读"""
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    obj = {"tasks": [{"id": "1", "title": "买牛奶", "day": M.Store._today()}],
           "date": M.Store._today()}
    raw = b"\xef\xbb\xbf" + json.dumps(obj, ensure_ascii=False).encode("utf-8")
    _store(tmp_path, raw=raw)
    s = M.Store()
    assert not s.load_failed
    assert [t["title"] for t in s.tasks] == ["买牛奶"]


def test_tasks_with_gbk_readable(tmp_path, monkeypatch):
    """A1 延伸：GBK 存档也能读"""
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    obj = {"tasks": [{"id": "1", "title": "买牛奶", "day": M.Store._today()}],
           "date": M.Store._today()}
    raw = json.dumps(obj, ensure_ascii=False).encode("gbk")
    _store(tmp_path, raw=raw)
    s = M.Store()
    assert not s.load_failed
    assert [t["title"] for t in s.tasks] == ["买牛奶"]


def test_corrupt_history_not_overwritten(tmp_path, monkeypatch):
    """A2：历史文件坏了，启动不能把它重写成只剩今天"""
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    _store(tmp_path, tasks_obj={"tasks": [], "date": M.Store._today()})
    broken = '{"days": {"2026-11-01": [{"title": "旧记录"}],'.encode("utf-8")
    (tmp_path / "history.json").write_bytes(broken)
    s = M.Store()
    assert s.hist_failed is True
    assert os.path.exists(s.hist_corrupt_copy)
    # 任何一次同步都不许写盘
    s.sync_history()
    s.save_history()
    with open(tmp_path / "history.json", "rb") as f:
        assert f.read() == broken


def test_one_bad_setting_keeps_others(tmp_path, monkeypatch):
    """B5：alpha 是文字时，昵称/主题不该跟着回默认"""
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    _store(tmp_path, tasks_obj={
        "tasks": [], "date": M.Store._today(),
        "alpha": "很透明", "user_name": "小李", "theme": "ink",
        "font_scale": "big", "bubble_w": 96,
    })
    s = M.Store()
    assert s.alpha == 0.95            # 坏字段用默认
    assert s.user_name == "小李"      # 后面的设置不受牵连
    assert s.theme == "ink"
    assert s.bubble_w == 96


def test_bad_hhmm_sanitized(tmp_path, monkeypatch):
    """B4 延伸：坏时间在加载时清洗掉，不给提醒循环留炸弹"""
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    _store(tmp_path, tasks_obj={
        "tasks": [{"id": "1", "title": "脏时间", "hhmm": "abc",
                   "day": M.Store._today()},
                  {"id": "2", "title": "好时间", "hhmm": "09:30",
                   "day": M.Store._today()}],
        "date": M.Store._today(),
    })
    s = M.Store()
    assert s.tasks[0]["hhmm"] is None
    assert s.tasks[1]["hhmm"] == "09:30"


def test_snapshot_refreshed_each_save(tmp_path, monkeypatch):
    """A4：备份不再是当天开机空壳"""
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    monkeypatch.setattr(M.Store, "_today", staticmethod(lambda: dt.date.today().isoformat()))
    s = M.Store()
    s.tasks = [{"id": "1", "title": "早上就有的", "day": s.today}]
    s.save()
    day = dt.date.today().isoformat()
    snap = tmp_path / "backup" / day / "tasks.json"
    assert snap.exists()
    first = json.loads(snap.read_text(encoding="utf-8"))
    assert len(first["tasks"]) == 1
    # 下午又记了 5 条
    for i in range(5):
        s.tasks.append({"id": "x%d" % i, "title": "下午%d" % i, "day": s.today})
    s.save()
    again = json.loads(snap.read_text(encoding="utf-8"))
    assert len(again["tasks"]) == 6, "备份没跟上当天的新内容"


# ------------------------------------------------------------------ 历史
def test_delete_only_touches_today_history(tmp_path, monkeypatch):
    """A3：今天删一条「买牛奶」，昨天的记录必须还在"""
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    s = M.Store()
    s.history = {
        "2026-11-05": [{"title": "买牛奶", "tid": "old", "done": True}],
        "2026-11-06": [{"title": "买牛奶", "tid": "old", "done": True}],
    }
    s.purge_history({"买牛奶"}, only_today=True, tids={"t1"})
    assert len(s.history["2026-11-05"]) == 1
    assert len(s.history["2026-11-06"]) == 1


def test_same_title_two_tasks_two_rows(tmp_path, monkeypatch):
    """C2：同一天两条「跑步」在历史里是两行"""
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    s = M.Store()
    s.tasks = [
        {"id": "a", "title": "跑步", "day": s.today, "done": True},
        {"id": "b", "title": "跑步", "day": s.today, "done": False},
    ]
    s.sync_history()
    rows = s.history[s.today]
    assert len(rows) == 2, rows
    assert {r.get("tid") for r in rows} == {"a", "b"}


# ------------------------------------------------------------------ GUI 层
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
    a.store.tasks = []
    a.store.messages = []
    a._ring_bell = lambda *x: None
    a.show_due_card = lambda t: None
    yield a
    try:
        root.destroy()
    except Exception:
        pass


def test_letter_in_text_not_eaten(app):
    """A9：待答优先级时输入含字母的正文，不能再被吞掉"""
    a = app
    a.respond("购买打印纸")          # 进优先级追问
    before = len(a.store.tasks)
    a.respond("处理<b>&特殊符号")
    assert len(a.store.tasks) == before + 1, [
        (t["title"], t.get("score")) for t in a.store.tasks]
    assert any("特殊符号" in t["title"] for t in a.store.tasks)


def test_single_letter_still_accepted(app):
    """A9 反向：只回一个「B」仍按优先级回答处理"""
    a = app
    a.respond("购买打印纸")
    r = a.respond("B")
    t = [x for x in a.store.tasks if x["title"] == "购买打印纸"][0]
    assert t["score"] >= 55, (r, t["score"])


def test_long_title_not_truncated(app):
    """A10：长标题完整落库"""
    a = app
    title = "整理项目资料并核对附件清单的最终版本备注说明"
    a.respond(title)
    got = [t["title"] for t in a.store.tasks]
    assert any(g == title for g in got), got


def test_note_not_truncated_and_undo(app):
    """A7：便签全文保存、删除可撤回"""
    a = app
    a.list_mode = "note"
    long_txt = "长便签" * 100          # 300 字
    a.add_note(long_txt)
    note = a.store.notes[-1]
    assert note["text"] == long_txt
    a._del_note(note["id"])
    assert not any(n["id"] == note["id"] for n in a.store.notes)
    a.respond("撤回")
    assert any(n["id"] == note["id"] for n in a.store.notes)


def test_key_routed_to_inline_editor(app):
    """B1：行内编辑时按键进编辑框，不进发送框"""
    a = app
    a.respond("语文作业")
    tid = a.store.tasks[0]["id"]
    a.begin_edit(tid, 2)
    a.root.update()
    ed = a._edit_entry
    ed.delete(0, "end")
    # 模拟焦点没落到编辑框（Windows 上真实发生过）
    a.root.focus_force()
    ev = type("E", (), {"char": "z", "keysym": "z", "widget": a.root})()
    a._key_fallback(ev)

    class F:  # 构造一个"焦点在根窗口"的假事件
        pass
    assert ed.get() == "z", ed.get()
    assert "z" not in a.entry.get() or a._compose_placeholder, a.entry.get()


def test_send_failure_restores_text(app):
    """B3：解析链路抛异常时，原文回到输入框"""
    a = app
    a.clear_placeholder()

    def boom(_t):
        raise RuntimeError("boom")
    a.handle_user_text = boom
    a.entry.insert(0, "买牛奶")
    a.on_send()
    assert a.entry.get() == "买牛奶", a.entry.get()


def test_one_bad_task_does_not_stop_reminders(app):
    """B4：一条坏时间不影响其他任务照常提醒"""
    a = app
    now = dt.datetime.now()
    hhmm = (now + dt.timedelta(minutes=2)).strftime("%H:%M")
    a.store.tasks = [
        {"id": "bad", "title": "坏时间", "hhmm": "abc",
         "remind_before": 5, "day": a.store._today(), "done": False},
        {"id": "ok", "title": "好任务", "hhmm": hhmm,
         "remind_before": 30, "day": a.store._today(), "done": False},
    ]
    fired = []
    a.show_due_card = lambda t: fired.append(t.get("title"))
    a.check_reminders()
    assert "好任务" in fired, fired


def test_export_json_has_messages_and_seconds(app, tmp_path):
    """A8：JSON 含对话记录；文件名精确到秒"""
    a = app
    a.push("user", "测试一条")
    p = a.do_export("json")
    assert p and os.path.exists(p)
    obj = json.loads(open(p, encoding="utf-8").read())
    assert obj.get("messages"), "导出里没有对话记录"
    import re as _re
    base = os.path.basename(p)
    assert _re.search(r"-\d{8}-\d{6}\.json$", base), base   # 精确到秒


def test_quit_aborts_when_save_failed(app, monkeypatch):
    """A6：保存失败时退出要问一句，用户取消就不退"""
    a = app
    old = M.Store._save_error

    def bad_save():
        M.Store._save_error = "disk full"
    a.store.save = bad_save
    try:
        M.Store._save_error = "disk full"
        import tkinter.messagebox as mb
        monkeypatch.setattr(mb, "askyesno", lambda *x, **k: False)
        a.root.destroy = lambda: (_ for _ in ()).throw(AssertionError("不该销毁窗口"))
        a.quit()
        assert a._closing is False
    finally:
        M.Store._save_error = old


# ------------------------------------------------------------------ 其它
def test_batch_same_title_not_blocked(app):
    """C1：同名批量录入，确认过一次之后不再逐条拦"""
    a = app
    a.respond("批量压测条目")
    a.respond("不用")                        # 结束优先级追问
    a.respond("批量压测条目")                # 触发「已有相似任务」
    a.respond("就这个")                      # 首次确认
    for i in range(4):
        a.respond("批量压测条目")
        a.respond("不用")
    n = sum(1 for t in a.store.tasks if t["title"].startswith("批量压测条目"))
    assert n >= 6, [(t["title"]) for t in a.store.tasks]


def test_ics_folded_and_escaped():
    """C9：长标题按 75 字节折行、CR 被转义"""
    import exporter as E
    out = E.to_ics([{"title": "很长的任务标题" * 8 + "\r换行", "hhmm": "09:00"}],
                   {})
    assert "\r\n " in out                    # 有续行
    for line in out.split("\r\n"):
        assert len(line.encode("utf-8")) <= 76, line
    assert "\\n换行" in out                  # CR 已转义


def test_version_resource_matches_code():
    """C7：文件属性版本号与代码版本一致（避免发错包）"""
    import re
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    txt = open(os.path.join(root, "version_info.txt"), encoding="utf-8").read()
    m = re.search(r"filevers=\((\d+), (\d+), (\d+), (\d+)\)", txt)
    assert m, "版本资源里没有 filevers"
    want = [int(x) for x in M.VERSION.split(".")]
    want = (want + [0] * 4)[:4]
    assert [int(x) for x in m.groups()] == want, (m.groups(), M.VERSION)


def test_default_alpha_readable(app):
    """C4：新装默认透明度不低于 0.95"""
    assert app.store.alpha >= 0.95
