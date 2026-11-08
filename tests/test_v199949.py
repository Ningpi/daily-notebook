# -*- coding: utf-8 -*-
"""v1.9.9.49 回归：英文日期丢失 + Release 打包命名。

背景（真机反馈）：
  1. GitHub Release 里的 exe 下载下来叫 default.exe —— PyInstaller 在
     Windows 上对 spec 的非 ASCII name 会回退成 default.exe。
  2. 下午说「tomorrow 3pm」时英文版追问「时间已过」，因为 parser_en
     把 tomorrow 的 day_offset 丢了，主程序按今天判断。
"""
import datetime as dt
import os
import re

import pytest

import parser_en as PE
import i18n

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestEnglishDueDate:
    """英文日期必须带 due 日期，否则下午会误判「时间已过」"""

    def test_tomorrow_with_time(self):
        item = PE.parse_tasks("buy milk tomorrow 3pm")[0]
        assert item[1] == "15:00"
        assert item[6] == dt.date.today() + dt.timedelta(days=1)

    def test_tomorrow_without_time(self):
        item = PE.parse_tasks("meeting tomorrow")[0]
        assert item[1] is None
        assert item[6] == dt.date.today() + dt.timedelta(days=1)

    def test_day_after_tomorrow(self):
        item = PE.parse_tasks("dentist day after tomorrow")[0]
        assert item[6] == dt.date.today() + dt.timedelta(days=2)

    def test_today_has_no_due_date(self):
        """今天/没日期的任务不设 due_date（否则列表里会冒出多余标记）"""
        for t in ("call mom at 5pm", "buy milk", "read a book today"):
            assert PE.parse_tasks(t)[0][6] is None

    def test_late_afternoon_tomorrow_not_expired(self):
        """核心场景：18 点说 tomorrow 3pm，不能判过期"""
        now = dt.datetime.now()
        item = PE.parse_tasks("buy milk tomorrow 3pm")[0]
        hhmm, due = item[1], item[6]
        # 与 main 里 expired 判定同构：有 due 且在未来 → 不过期
        h, m = map(int, hhmm.split(":"))
        target = dt.datetime.combine(due, dt.time(h, m))
        assert target > now or due > dt.date.today()


class TestReleaseNaming:
    """打包产物名必须是 ASCII，否则 Release 里变 default.exe"""

    def test_spec_name_is_ascii(self):
        spec = open(os.path.join(ROOT, "每日记事本.spec"), encoding="utf-8").read()
        m = re.search(r"name\s*=\s*'([^']+)'", spec)
        assert m, "spec 里找不到 name="
        assert m.group(1).isascii(), "spec 的 name 必须 ASCII，否则会变 default.exe"
        assert m.group(1) == "DailyNotebook"

    def test_workflow_uses_ascii_exe(self):
        wf = open(os.path.join(ROOT, ".github/workflows/build-windows.yml"),
                  encoding="utf-8").read()
        assert "dist/DailyNotebook.exe" in wf
        assert "dist\\DailyNotebook.exe" in wf
        # 发布资产带版本号
        assert "DailyNotebook-${{ github.ref_name }}.exe" in wf

    def test_version_info_relative_to_exe(self):
        """version_info.txt 必须留在仓库（spec 引用它，缺失 CI 直接失败）"""
        path = os.path.join(ROOT, "version_info.txt")
        assert os.path.exists(path)
        content = open(path, encoding="utf-8").read()
        assert "OriginalFilename', 'DailyNotebook.exe'" in content

    def test_spec_version_file_exists(self):
        spec = open(os.path.join(ROOT, "每日记事本.spec"), encoding="utf-8").read()
        assert "version='version_info.txt'" in spec
