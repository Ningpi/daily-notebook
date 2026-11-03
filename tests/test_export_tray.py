# -*- coding: utf-8 -*-
"""v1.9.9.20：导出 / 备份 / 托盘降级 单元测试"""
import datetime as dt
import json
import os

import pytest

import exporter


TASKS = [{"title": "开会", "hhmm": "09:00", "score": 80, "done": False},
         {"title": "买牛奶", "hhmm": None, "done": True, "done_at": "10:20"}]
HIST = {"2026-11-01": [{"title": "交报告", "hhmm": "15:00", "done": True,
                        "done_at": "14:50"}]}


class TestExport:
    def test_json_roundtrip(self):
        s = exporter.to_json(TASKS, HIST, {"user_name": "小李"})
        obj = json.loads(s)
        assert obj["tasks"] == TASKS
        assert obj["history"] == HIST
        assert obj["settings"]["user_name"] == "小李"

    def test_markdown_structure(self):
        md = exporter.to_markdown(TASKS, HIST)
        assert md.startswith("# 每日记事本")
        assert "- [x] 买牛奶" in md
        assert "- [ ] 开会" in md
        assert "09:00" in md
        assert "完成率" in md

    def test_markdown_empty(self):
        md = exporter.to_markdown([], {})
        assert "还没有任何记录" in md

    def test_ics_valid(self):
        ics = exporter.to_ics(TASKS, HIST)
        assert ics.startswith("BEGIN:VCALENDAR")
        assert ics.rstrip().endswith("END:VCALENDAR")
        assert "BEGIN:VEVENT" in ics and "END:VEVENT" in ics
        # 有时间的任务是定时事件，没时间的是全天事件
        assert "DTSTART:202611" in ics
        assert "VALUE=DATE" in ics
        assert ics.count("BEGIN:VEVENT") == 3
        assert "\r\n" in ics

    def test_ics_escapes_special(self):
        ics = exporter.to_ics([{"title": "买A,B;C", "hhmm": None}], {})
        assert "买A\\,B\\;C" in ics

    def test_safe_name(self):
        assert "/" not in exporter.safe_name("a/b:c*d")
        assert exporter.safe_name("") == "export"


class TestBackup:
    def test_snapshot_and_prune(self, tmp_path):
        base = str(tmp_path)
        src = tmp_path / "tasks.json"
        src.write_text('{"tasks":[]}', encoding="utf-8")
        files = [("tasks.json", str(src))]
        # 造 9 天快照，只应留最近 7 个
        for i in range(9):
            d = dt.date(2026, 10, 1) + dt.timedelta(days=i)
            got = exporter.auto_snapshot(base, files, keep=7, today=d)
            assert got == d.isoformat()
        snaps = exporter.list_snapshots(base)
        assert len(snaps) == 7
        assert snaps[0] == "2026-10-09"
        assert snaps[-1] == "2026-10-03"

    def test_same_day_only_once(self, tmp_path):
        base = str(tmp_path)
        src = tmp_path / "tasks.json"
        src.write_text("{}", encoding="utf-8")
        d = dt.date(2026, 10, 1)
        assert exporter.auto_snapshot(base, [("tasks.json", str(src))], today=d)
        assert exporter.auto_snapshot(base, [("tasks.json", str(src))],
                                      today=d) is None

    def test_missing_files_no_snapshot(self, tmp_path):
        base = str(tmp_path)
        assert exporter.auto_snapshot(base, [("x.json", "/nope/x.json")]) is None


class TestTrayFallback:
    def test_import_safe(self):
        import tray
        assert hasattr(tray, "Tray")

    def test_noop_when_unavailable(self):
        import tray
        t = tray.Tray(None)
        if os.name != "nt":
            assert t.start() is False
            assert t.available is False
            assert t.notify("a", "b") is False
            t.update_tip("x")
            t.hide()
            t.stop()
