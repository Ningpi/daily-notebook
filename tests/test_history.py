# -*- coding: utf-8 -*-
"""历史归档 / 跨天逻辑单元测试（重点：跨天数据正确性）

对应文档条目：
  使用说明.md 第五节「历史记录」、第十二节常见问题「第二天打开…」
  使用说明.md 二、2（tasks.json / history.json 分工）

设计原则：这些用例只依赖 Store（数据层），不需要 GUI。
"""
import json
import datetime as dt

import pytest

import main as M

TODAY = dt.date.today()
YDAY = TODAY - dt.timedelta(days=1)


def _t(title, **kw):
    d = {"id": kw.pop("id", title), "title": title, "hhmm": None, "score": 40,
         "done": False, "manual": False, "created": "09:00", "day": TODAY.isoformat()}
    d.update(kw)
    return d


# ------------------------------------------------------- 归档基本行为
class TestSyncHistory:
    def test_first_sync_creates_today(self, store):
        store.tasks = [_t("开会"), _t("写报告")]
        store.sync_history()
        rows = store.history[TODAY.isoformat()]
        assert {r["title"] for r in rows} == {"开会", "写报告"}

    def test_done_state_propagates(self, store):
        store.tasks = [_t("开会")]
        store.sync_history()
        store.tasks[0]["done"] = True
        store.tasks[0]["done_at"] = "10:30"
        store.sync_history()
        row = store.history[TODAY.isoformat()][0]
        assert row["done"] is True and row["done_at"] == "10:30"

    def test_undone_state_also_propagates(self, store):
        """取消勾选要同步回历史（此前只单向写 True）"""
        store.tasks = [_t("开会", done=True, done_at="10:30")]
        store.sync_history()
        store.tasks[0]["done"] = False
        store.tasks[0]["done_at"] = ""
        store.sync_history()
        row = store.history[TODAY.isoformat()][0]
        assert row["done"] is False and row["done_at"] == ""

    def test_score_never_downgraded(self, store):
        """历史里的分数只升不降（同一天先后改过优先级时保留最高）"""
        store.tasks = [_t("交周报", score=90)]
        store.sync_history()
        store.tasks[0]["score"] = 40
        store.sync_history()
        assert store.history[TODAY.isoformat()][0]["score"] == 90

    def test_merge_by_title_not_duplicated(self, store):
        store.tasks = [_t("开会")]
        store.sync_history()
        store.sync_history()
        store.sync_history()
        assert len(store.history[TODAY.isoformat()]) == 1

    def test_no_disk_write_when_unchanged(self, store, tmp_path, monkeypatch):
        """内容没变时不重复写盘（性能要求：refresh 每次都会调 sync_history）"""
        store.tasks = [_t("开会")]
        store.sync_history()
        calls = []
        monkeypatch.setattr(store, "save_history", lambda: calls.append(1))
        store.sync_history()
        assert calls == [], "内容未变却写了盘"


# ------------------------------------------------------- 跨天
class TestCrossDay:
    def test_yesterday_tasks_archived_to_yesterday(self, seeded_store):
        """v1.9.9 修复项：跨天启动时，昨天的任务必须归到昨天，
        否则「历史 → 昨天」永远是空的。"""
        st = seeded_store(
            tasks=[_t("昨天没做完", hhmm="09:00")],
            date=YDAY.isoformat(),
        )
        days = st.history
        assert YDAY.isoformat() in days, "昨天没有被归档：%s" % list(days)
        assert {r["title"] for r in days[YDAY.isoformat()]} == {"昨天没做完"}

    def test_plain_task_loses_time_after_day_change(self, seeded_store):
        """文档：第二天打开，昨天没做完的还在，但会清掉具体时间点"""
        st = seeded_store(tasks=[_t("昨天的事", hhmm="09:00")], date=YDAY.isoformat())
        assert st.tasks[0]["hhmm"] is None
        assert st.tasks[0]["done"] is False      # 任务本身保留

    def test_task_keeps_score_after_day_change(self, seeded_store):
        """文档：重要性排序保留"""
        st = seeded_store(tasks=[_t("重要的事", hhmm="09:00", score=95)],
                          date=YDAY.isoformat())
        assert st.tasks[0]["score"] == 95

    def test_done_task_keeps_time(self, seeded_store):
        """已完成的任务不清时间（历史里要能看到当时几点做的）"""
        st = seeded_store(tasks=[_t("昨天完成的事", hhmm="09:00", done=True,
                                   done_at="09:30")],
                          date=YDAY.isoformat())
        assert st.tasks[0]["hhmm"] == "09:00"

    def test_future_due_date_keeps_time(self, seeded_store):
        """有明确截止日且还没到：保留时刻（不误清）"""
        future = (TODAY + dt.timedelta(days=3)).isoformat()
        st = seeded_store(tasks=[_t("后天的事", hhmm="09:00", due_date=future)],
                          date=YDAY.isoformat())
        assert st.tasks[0]["hhmm"] == "09:00", "未到期却被清了时间"

    def test_expired_due_date_clears_time(self, seeded_store):
        st = seeded_store(tasks=[_t("过期的事", hhmm="09:00", due_date=YDAY.isoformat())],
                          date=YDAY.isoformat())
        assert st.tasks[0]["hhmm"] is None

    def test_repeat_task_revived_on_same_day(self, seeded_store):
        """每天的任务跨天应复活为未完成"""
        st = seeded_store(
            tasks=[_t("每天喝水", hhmm="09:00", done=True,
                      repeat={"kind": "daily", "weekday": None, "monthday": None})],
            date=YDAY.isoformat())
        assert st.tasks[0]["done"] is False

    def test_repeat_not_due_today_pushed_to_done(self, seeded_store):
        """每周一的任务，今天不是周一 → 压到已完成区，不打扰"""
        monday_only = {"kind": "weekly", "weekday": 0, "monthday": None}
        st = seeded_store(tasks=[_t("每周一开会", repeat=monday_only)],
                          date=YDAY.isoformat())
        if TODAY.weekday() != 0:
            assert st.tasks[0]["done"] is True

    def test_reminded_flag_reset_on_day_change(self, seeded_store):
        """跨天必须重置提醒标记，否则今天不会再提醒"""
        st = seeded_store(tasks=[_t("提醒过的事", hhmm="09:00", reminded=True,
                                    reminded_day=YDAY.isoformat())],
                          date=YDAY.isoformat())
        assert st.tasks[0]["reminded"] is False

    def test_messages_cleared_on_day_change(self, seeded_store):
        """跨天清空聊天记录（但任务与历史都留着）"""
        st = seeded_store(tasks=[_t("x")], date=YDAY.isoformat())
        assert st.messages == []


# ------------------------------------------------------- 删除同步
class TestPurgeHistory:
    def test_delete_removes_from_all_days(self, store):
        store.history = {
            TODAY.isoformat(): [{"title": "要删的", "done": False, "score": 40}],
            YDAY.isoformat(): [{"title": "要删的", "done": False, "score": 40}],
        }
        store.purge_history({"要删的"})
        assert all(r["title"] != "要删的"
                   for rows in store.history.values() for r in rows)

    def test_delete_keeps_others(self, store):
        store.history = {TODAY.isoformat(): [
            {"title": "要删的", "done": False, "score": 40},
            {"title": "留下的", "done": True, "score": 40},
        ]}
        store.purge_history({"要删的"})
        titles = [r["title"] for r in store.history[TODAY.isoformat()]]
        assert titles == ["留下的"]

    def test_purge_empty_is_noop(self, store):
        store.history = {TODAY.isoformat(): [{"title": "x"}]}
        store.purge_history(set())
        assert len(store.history[TODAY.isoformat()]) == 1


# ------------------------------------------------------- 历史天数与汇总
class TestHistoryDays:
    def test_sorted_desc(self, store):
        store.history = {"2026-01-01": [], "2026-03-01": [], "2026-02-01": []}
        assert store.history_days() == ["2026-03-01", "2026-02-01", "2026-01-01"]

    def test_persist_roundtrip(self, store, tmp_path):
        store.history = {TODAY.isoformat(): [{"title": "x", "done": True,
                                              "score": 40, "done_at": "10:00"}]}
        store.save_history()
        st2 = M.Store()
        assert TODAY.isoformat() in st2.history

    def test_corrupt_history_file_does_not_crash(self, tmp_path, monkeypatch):
        """history.json 损坏时不能让整个程序起不来"""
        monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
        (tmp_path / "history.json").write_text("{ not json", encoding="utf-8")
        st = M.Store()
        assert isinstance(st.history, dict)
