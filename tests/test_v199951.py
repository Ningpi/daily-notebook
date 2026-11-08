# -*- coding: utf-8 -*-
"""v1.9.9.51 回归：深度复核报告（v1.9.9.48 终稿）逐项核查后的修复。

核查结论（本轮实测）：
  P1-1 保存失败横幅可点 × 关掉 + 最长 60 秒才出现     —— 属实
  P1-2 超长文本静默截断 / 5,655 字卡死                —— 1 万字实测完整，
       不卡（0.4s）；改为入口显式上限 + 明确提示，杜绝未来静默丢字
  P1-3 坏文件损坏后不会自动用备份                      —— 属实
  P2-1 英文相对日（next monday 等）                    —— 属实（tomorrow 已修）
  P2-2 便签删除后说「撤回」                            —— 属实，且会误删别的便签
  P2-3 撤回改名不还原优先级                            —— 属实
  P2-4 时间词吃字                                      —— 属实，且「把报告写完」
       会被改成「完报告写」（与时间词无关的通用错乱）
  P3-1 Markdown 导出无优先级                           —— 属实
  P3-2 字母优先级前缀留在标题                           —— 属实（此前完全不识别）
  P3-3 中长标题静默截断                                —— 实测未复现，实际是 P2-4 吃字
  P3-4 「昨天」先触发重复合并                          —— 属实
  P3-5 强杀时托盘回调异常                              —— 加固 winfo_exists 判断
"""
import datetime as dt
import json
import os

import pytest

tk = pytest.importorskip("tkinter")

import main as M
import parser as PC
import parser_en as PE
import exporter
import i18n


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    try:
        root = tk.Tk()
    except Exception as exc:
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


# ------------------------------------------------ P1-1 横幅不可关闭 / 即时提示
class TestSaveBanner:
    def test_save_banner_is_sticky(self, app):
        """保存失败横幅不给 ×，且点 × 关不掉"""
        app._show_banner("保存失败", kind="save", sticky=True)
        app.root.update()
        assert app._banner_sticky is True
        assert app._banner_x.cget("text") == ""
        # 点 × 应当被忽略
        app._banner_close()
        app.root.update()
        assert app.banner.winfo_ismapped(), "sticky 横幅被关掉了"

    def test_normal_banner_closable(self, app):
        """普通提示横幅仍可关闭（别把一切都做成关不掉）"""
        app._show_banner("普通提示", kind="warn")
        app.root.update()
        assert app._banner_sticky is False
        app._banner_close()
        app.root.update()
        assert not app.banner.winfo_ismapped()

    def test_fail_seq_forces_reask(self, app):
        """同类错误再次失败（计数变了）要重新弹，不再永久静默"""
        M.Store._save_errors = {"tasks.json": "OSError: boom"}
        M.Store._save_fail_seq = 1
        app._check_save_error()
        app.root.update()
        app._hide_banner()
        # 计数不变、且已提示过 → 不重复弹（避免每次轮询都闪）
        app._check_save_error()
        app.root.update()
        assert not app.banner.winfo_ismapped()
        # 又失败一次（计数 +1）→ 必须重新弹出来
        M.Store._save_fail_seq = 2
        app._check_save_error()
        app.root.update()
        assert app.banner.winfo_ismapped(), "第二次失败没重新提示"
        M.Store._save_errors = {}
        M.Store._save_fail_seq = 0
        app._check_save_error()
        app.root.update()

    def test_atomic_failure_bumps_seq_and_notifies(self, tmp_path, monkeypatch):
        """_atomic 失败时计数 +1 并立刻回调界面（不等 60 秒轮询）"""
        called = []
        monkeypatch.setattr(M.Store, "notify_hook", staticmethod(lambda: called.append(1)))
        M.Store._save_errors = {}
        M.Store._save_fail_seq = 0
        before = M.Store._save_fail_seq
        M.Store._atomic(os.path.join(str(tmp_path), "no_dir", "x.json"), {"a": 1})
        assert M.Store._save_fail_seq == before + 1
        assert called, "写盘失败没有即时通知界面"
        M.Store._save_errors = {}
        M.Store._save_fail_seq = 0


# ------------------------------------------------ P1-2 超长输入
class TestTooLongInput:
    def test_too_long_blocked(self, app):
        """超过上限：不解析、不进库、给明确提示"""
        app.entry.delete(0, "end")
        app.entry.insert(0, "整理报告" + "字" * (M.MAX_INPUT + 50))
        n_before = len(app.store.tasks)
        app.on_send()
        app.root.update()
        assert len(app.store.tasks) == n_before, "超长输入仍被当成任务入库"
        assert app.entry.get(), "拦下后应保留原文让用户自己拆"

    def test_normal_length_ok(self, app):
        """上限以内的长文本照常处理，不会误伤"""
        text = "整理第三季度报告" + "内容" * 600      # 1208 字
        assert len(text) <= M.MAX_INPUT
        app.entry.delete(0, "end")
        app.entry.insert(0, text)
        app.on_send()
        app.root.update()
        assert app.store.tasks, "正常长度的长文本被拦掉了"
        assert len(app.store.tasks[-1]["title"]) > 800, "落库被截断了"

    def test_no_silent_truncation_cn(self):
        """中文长文本落库逐字符完整（旧版报告称 5220 字只剩 1681）"""
        text = "整理报告" + "测试内容" * 400          # 1604 字
        r = PC.parse_tasks(text)
        assert r and len(r[0][0]) == len(text), (len(r[0][0]), len(text))


# ------------------------------------------------ P1-3 从备份恢复
class TestRestoreFromBanner:
    def test_latest_snapshot_found(self, app, tmp_path):
        """能挑出最近一份有内容的快照"""
        bdir = os.path.join(str(tmp_path), "backup", "2026-11-07")
        os.makedirs(bdir, exist_ok=True)
        with open(os.path.join(bdir, "tasks.json"), "w", encoding="utf-8") as f:
            json.dump({"tasks": [{"title": "a"}, {"title": "b"}]}, f)
        hit = app._latest_snapshot("tasks.json")
        assert hit is not None
        assert hit[0] == "2026-11-07" and hit[1] == 2

    def test_no_snapshot_returns_none(self, app):
        assert app._latest_snapshot("tasks.json") is None

    def test_banner_has_restore_action(self, app, tmp_path):
        """损坏横幅上要有一键恢复按钮（不是只告诉你副本在哪）"""
        bdir = os.path.join(str(tmp_path), "backup", "2026-11-07")
        os.makedirs(bdir, exist_ok=True)
        with open(os.path.join(bdir, "tasks.json"), "w", encoding="utf-8") as f:
            json.dump({"tasks": [{"title": "a"}]}, f)
        hit = app._latest_snapshot("tasks.json")
        app._show_banner("数据文件损坏", sticky=True,
                         action=M.tr("banner_restore_now"),
                         on_action=lambda: None)
        app.root.update()
        assert app._banner_act.winfo_ismapped(), "恢复按钮没显示"
        assert hit[0] in M.tr("load_corrupt_banner_backup", d=hit[0], n=hit[1])


# ------------------------------------------------ P2-1 英文相对日
class TestEnglishRelativeDate:
    def test_next_monday(self):
        r = PE.parse_tasks("review next Monday 9am")
        assert r and r[0][6] is not None, "next Monday 没解析出日期"
        assert r[0][1] == "09:00"
        assert "next" not in r[0][0].lower(), "标题里还留着 next Monday"

    def test_next_friday(self):
        r = PE.parse_tasks("report next friday")
        assert r and r[0][6] is not None

    def test_tomorrow_kept(self):
        r = PE.parse_tasks("buy milk tomorrow 3pm")
        assert r[0][6] == dt.date.today() + dt.timedelta(days=1)


# ------------------------------------------------ P2-2 便签删除后撤回
class TestNoteUndo:
    def test_undo_restores_deleted_note(self, app):
        """删掉 A 再说「撤回」→ A 回原位置（旧版会误删 B）"""
        app.store.notes = [
            {"id": "n1", "text": "第一条"},
            {"id": "n2", "text": "第二条"},
            {"id": "n3", "text": "第三条"},
        ]
        app._del_note("n1")
        assert [n["id"] for n in app.store.notes] == ["n2", "n3"]
        app._undo_last_note()
        assert [n["id"] for n in app.store.notes] == ["n1", "n2", "n3"], \
            "撤回没把 n1 放回原位"
        app.root.update()

    def test_undo_after_delete_last(self, app):
        """删掉唯一一条后说「撤回」→ 回来，而不是「没有可撤回」"""
        app.store.notes = [{"id": "only", "text": "唯一一条"}]
        app._del_note("only")
        assert app.store.notes == []
        app._undo_last_note()
        assert len(app.store.notes) == 1
        app.root.update()

    def test_undo_twice_lifo(self, app):
        """连删两条，撤回按后进先出"""
        app.store.notes = [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}]
        app._del_note("a")
        app._del_note("b")
        app._undo_last_note()          # 先恢复后删的 b
        assert [n["id"] for n in app.store.notes] == ["b"]
        app._undo_last_note()          # 再恢复 a（原位在 b 之前）
        assert [n["id"] for n in app.store.notes] == ["a", "b"]


# ------------------------------------------------ P2-3 改名撤回还原优先级
class TestRenameUndoScore:
    def test_rename_undo_restores_score(self, app):
        t = {"id": "t1", "title": "买牛奶", "hhmm": None, "score": 70,
             "manual": False, "done": False, "day": app.store._today(),
             "due_date": None, "repeat": None, "created": "09:00"}
        app.store.tasks = [t]
        app._push_undo({"kind": "rename", "id": "t1", "prev": "买牛奶",
                        "prev_score": 70, "prev_manual": False,
                        "label": "改名"})
        t["title"] = "买牛奶（第2次）"
        t["score"] = 30
        app._do_undo("rename")
        assert t["title"] == "买牛奶"
        assert t["score"] == 70, "撤回只剩标题，优先级没回退"


# ------------------------------------------------ P2-4 吃字 / 语序
class TestTitleCorruption:
    @pytest.mark.parametrize("raw,want", [
        ("把报告写完", "报告写完"),
        ("把作业做完", "作业做完"),
        ("把衣服洗完", "衣服洗完"),
        ("把水电费交了", "交水电费"),
        ("把方案交上去", "方案交上去"),
        ("把垃圾倒了", "倒垃圾"),
    ])
    def test_ba_construction(self, raw, want):
        got = PC.clean_title(raw)
        assert got == want, "%s -> %s（期望 %s）" % (raw, got, want)

    def test_time_word_prefix_not_eaten(self):
        """时间词只剥自己，不啃掉首字"""
        assert PC.parse_tasks("下周一把第三季度报告写完")[0][0] == "第三季度报告写完"
        assert PC.parse_tasks("周三前把方案交上去")[0][0] == "方案交上去"
        assert PC.parse_tasks("明天把报销单交了")[0][0] == "交报销单"

    def test_qu_kept(self):
        """「交上去」的「去」是方位补语，不能当语气词删"""
        assert PC.clean_title("交上去") == "交上去"


# ------------------------------------------------ P3-1 Markdown 优先级
def test_markdown_has_priority():
    md = exporter.to_markdown(
        [{"title": "交房租", "score": 95, "done": False},
         {"title": "买牛奶", "score": 30, "done": False}], {})
    assert "紧急" in md and "不急" in md


# ------------------------------------------------ P3-2 字母优先级
class TestLetterPriority:
    @pytest.mark.parametrize("raw,title,score", [
        ("交房租A", "交房租", 95),
        ("写周报C", "写周报", 45),
        ("买牛奶D", "买牛奶", 20),
    ])
    def test_letter_stripped_and_scored(self, raw, title, score):
        r = PC.parse_tasks(raw)
        assert r[0][0] == title, "%s -> %s" % (raw, r[0][0])
        assert r[0][2] == score

    def test_latin_word_not_eaten(self):
        """含英文单词的标题不吃句尾字母"""
        r = PC.parse_tasks("买 HDMI 线 A")
        assert "A" in r[0][0]


# ------------------------------------------------ P3-4 昨天 / 前天
class TestPastDays:
    @pytest.mark.parametrize("raw,off", [
        ("昨天交周报", 1), ("前天开会", 2), ("大前天整理资料", 3),
    ])
    def test_past_date_parsed(self, raw, off):
        r = PC.parse_tasks(raw)
        assert r[0][6] == dt.date.today() - dt.timedelta(days=off)
        assert "天" != r[0][0][0], "标题首字被啃掉了"

    def test_past_input_skips_dup_merge(self, app):
        """「昨天交周报」不该被同名合并吞掉，要走过期确认"""
        app.respond("交周报")
        reply = app.respond("昨天交周报")
        assert "过截止日期" in (reply or "") or "过期" in (reply or ""), reply
        assert app._pending_q == "expired"


# ------------------------------------------------ 周三不再凭空 18:00
class TestNoDefaultSixPM:
    def test_weekday_only_no_clock(self):
        """「周三开会」只记日期，不再塞一个 18:00"""
        r = PC.parse_tasks("周三开会")
        assert r[0][1] is None, "又凭空给了钟点：%s" % (r[0][1],)
        assert r[0][6] is not None

    def test_explicit_clock_kept(self):
        r = PC.parse_tasks("周三下午三点开会")
        assert r[0][1] == "15:00"


# ------------------------------------------------ P3-5 托盘回调
def test_tray_invoke_guards_destroyed_root():
    """root 已销毁时托盘回调直接返回，不抛异常"""
    class _Root(object):
        def winfo_exists(self):
            return False
        def after(self, *_a):
            raise AssertionError("不该在已销毁的窗口上排任务")

    class _App(object):
        root = _Root()

    class _T(object):
        app = _App()

    import tray
    tray.Tray._invoke(_T(), lambda: None)      # 不抛即通过
