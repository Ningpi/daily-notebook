# -*- coding: utf-8 -*-
"""pytest 共享夹具（conftest）

设计要点：
1. **不依赖真实 GUI**：绝大多数用例只测纯逻辑（解析器 / 历史 / 进度 / 哲言 / i18n），
   不需要 tkinter，可在 CI 的 headless 环境跑。
2. 需要 Store 的用例通过 tmp_path 隔离数据目录，绝不碰用户真实 data/。
3. 时间相关用例统一用 `freeze_now` 夹具，避免「上午跑过、下午跑挂」。
"""
import os
import sys
import json
import datetime as dt

import pytest

# 让 tests/ 能直接 import 上级目录的模块
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import parser as core          # noqa: E402
import parser_en as core_en    # noqa: E402
import i18n                    # noqa: E402
import quotes                  # noqa: E402
import themes                  # noqa: E402


@pytest.fixture
def now():
    """当前时间（用例里用它算期望值，避免硬编码）"""
    return dt.datetime.now()


@pytest.fixture
def tomorrow():
    return dt.date.today() + dt.timedelta(days=1)


@pytest.fixture
def yesterday():
    return dt.date.today() - dt.timedelta(days=1)


@pytest.fixture(autouse=True)
def reset_lang():
    """每个用例前后都把语言复位为中文，避免用例间串语言"""
    i18n.set_lang("zh")
    yield
    i18n.set_lang("zh")


@pytest.fixture
def zh():
    """强制中文解析器"""
    i18n.set_lang("zh")
    return core


@pytest.fixture
def en():
    """强制英文解析器"""
    i18n.set_lang("en")
    return core_en


@pytest.fixture
def store(tmp_path, monkeypatch):
    """隔离的 Store 实例（数据目录指向 tmp_path）"""
    import main as M
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))
    st = M.Store()
    yield st


@pytest.fixture
def seeded_store(tmp_path, monkeypatch):
    """带初始数据的 Store：方便测跨天 / 历史合并"""
    import main as M
    monkeypatch.setattr(M, "data_dir", lambda: str(tmp_path))

    def _make(tasks=None, history=None, date=None, **kw):
        obj = {
            "date": date or dt.date.today().isoformat(),
            "tasks": tasks or [],
            "messages": [],
            "user_name": "小李",
            "setup_stage": 3,
            "history": None,
        }
        obj.update(kw)
        with open(tmp_path / "tasks.json", "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        if history is not None:
            with open(tmp_path / "history.json", "w", encoding="utf-8") as f:
                json.dump({"days": history}, f, ensure_ascii=False)
        return M.Store()

    return _make


def task(title, hhmm=None, score=40, done=False, **kw):
    """构造一条任务字典（字段与运行时一致）"""
    t = {
        "id": kw.pop("id", "t_%s" % abs(hash(title)) % 100000),
        "title": title,
        "hhmm": hhmm,
        "score": score,
        "done": done,
        "manual": kw.pop("manual", False),
        "created": kw.pop("created", "09:00"),
        "day": kw.pop("day", dt.date.today().isoformat()),
    }
    t.update(kw)
    return t


@pytest.fixture
def mk():
    return task
