# -*- coding: utf-8 -*-
"""v1.9.9.58 回归：完整测试轮发现的两个健壮性漏洞。

  1. 字体深浅（text_darken）存成脏值（"深" / [45] / {} / true / NaN）时，
     加载后被清洗成 None → UI 退回「按透明度推导」，95% 透明下算出 0%，
     字淡得看不见（v1.9.9.53 修过的老毛病会被重新引回来）。现在一律
     回退默认 0.45；
  2. 任务缺 title（手改 JSON / 旧数据 / 插件写坏）或 tasks 里混进非 dict
     时，refresh_tasks 先崩在 sync_history 的 .get() 上，整张列表白屏。
     现在渲染入口先就地清洗（过滤非 dict、补 title / id），draw_row 也
     改用 .get 兜底。
"""
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


# ------------------------------------------ 1. 字体深浅脏值
class TestTextDarkenDirty:
    @pytest.mark.parametrize("bad", ['"深"', "[45]", "{}", "true", "null",
                                     '"abc"', '[]'])
    def test_dirty_falls_back_default(self, data_dir, bad):
        with open(os.path.join(str(data_dir), "tasks.json"), "w",
                  encoding="utf-8") as f:
            f.write('{"text_darken": %s}' % bad)
        st = M.Store()
        assert st.text_darken == pytest.approx(0.45), \
            "脏值 %s 应回退默认 45%%，实际 %r" % (bad, st.text_darken)

    def test_numeric_ranges_kept(self, data_dir):
        for raw, exp in (("0.8", 0.8), ("45", 0.45), ("150", 1.0), ("-3", 0.0)):
            with open(os.path.join(str(data_dir), "tasks.json"), "w",
                      encoding="utf-8") as f:
                f.write('{"text_darken": %s}' % raw)
            st = M.Store()
            assert st.text_darken == pytest.approx(exp), \
                "%s 应为 %r，实际 %r" % (raw, exp, st.text_darken)

    def test_effective_darken_not_none(self, app, data_dir):
        """_effective_darken 不能因脏值退化成 0%（字看不见）"""
        a = app
        a.store.text_darken = 0.45
        assert a._effective_darken(0.95) == pytest.approx(0.45)


# ------------------------------------------ 2. 脏任务渲染
class TestDirtyTasksRender:
    def test_missing_title_no_crash(self, app):
        a = app
        a.store.tasks = [{"id": "x1"}, {"title": "只有标题"}]
        a.refresh_tasks()          # 旧版这里 KeyError('title')
        a.root.update()
        assert all(isinstance(t.get("title"), str) for t in a.store.tasks)

    def test_title_none_no_crash(self, app):
        a = app
        a.store.tasks = [{"id": "z", "title": None}]
        a.refresh_tasks()
        a.root.update()
        assert a.store.tasks[0]["title"] == ""

    def test_non_dict_filtered(self, app):
        a = app
        a.store.tasks = ["不是字典", 42, {"id": "ok", "title": "正常任务"}]
        a.refresh_tasks()          # 旧版先崩在 sync_history
        a.root.update()
        assert len(a.store.tasks) == 1
        assert a.store.tasks[0]["title"] == "正常任务"

    def test_missing_id_filled(self, app):
        a = app
        a.store.tasks = [{"title": "没 id"}]
        a.refresh_tasks()
        a.root.update()
        assert a.store.tasks[0].get("id")

    def test_normal_tasks_unaffected(self, app):
        a = app
        a.store.tasks = [{"id": "a", "title": "买牛奶", "score": 30, "done": False},
                         {"id": "b", "title": "写周报", "score": 40, "done": True}]
        a.refresh_tasks()
        a.root.update()
        assert [t["title"] for t in a.store.tasks] == ["买牛奶", "写周报"]

    def test_after_clean_can_add(self, app):
        """清洗后继续正常建任务"""
        a = app
        a.store.tasks = ["乱七八糟"]
        a.refresh_tasks()
        a.entry.delete(0, "end")
        a._compose_placeholder = False
        a.entry.insert(0, "明天下午3点开会")
        a.on_send()
        a.root.update()
        assert any("开会" in t.get("title", "") for t in a.store.tasks)


# ------------------------- 3. 完成语不再造重复任务（本轮完整测试发现）
class TestDoneHintNoDup:
    def test_done_existing_task_no_new(self, app):
        """「完成开会」而清单里正有未完成的「开会」——不建重复任务"""
        a = app
        a.entry.delete(0, "end")
        a._compose_placeholder = False
        a.entry.insert(0, "明天下午3点开会")
        a.on_send()
        a.root.update()
        n0 = len(a.store.tasks)
        a.entry.delete(0, "end")
        a.entry.insert(0, "完成开会")
        a.on_send()
        a.root.update()
        assert len(a.store.tasks) == n0, "不应新建「完成开会（第2次）」"
        assert not any(t.get("done") for t in a.store.tasks), \
            "对话不打勾（v1.9.9.32 的设计），只指路"

    def test_done_suffix_form_no_new(self, app):
        """「开会完成了」同样不建新任务"""
        a = app
        a.store.tasks = [{"id": "m1", "title": "开会", "score": 30, "done": False}]
        a.refresh_tasks()
        a.entry.delete(0, "end")
        a._compose_placeholder = False
        a.entry.insert(0, "开会完成了")
        a.on_send()
        a.root.update()
        assert len(a.store.tasks) == 1
        assert a.store.tasks[0]["title"] == "开会"

    def test_done_without_match_still_creates(self, app):
        """没有同名任务时「完成写报告」仍按老行为建任务"""
        a = app
        a.store.tasks = []
        a.entry.delete(0, "end")
        a._compose_placeholder = False
        a.entry.insert(0, "完成写报告")
        a.on_send()
        a.root.update()
        assert any("报告" in t.get("title", "") for t in a.store.tasks)
