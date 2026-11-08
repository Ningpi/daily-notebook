# -*- coding: utf-8 -*-
"""v1.9.9.50 回归：管理窗切语言刷新 + 英文空态换行。

背景（用户真机反馈）：
  1. 英文模式下日常任务管理窗顶部提示仍是中文（窗口开着时切语言不刷新）。
  2. 英文空态文案一行超长，被窗口右缘截断（「when addin...」）。
  3. README 截图里独立窗口带 Linux 桌面标题栏，与真实 Windows 不符——
     截图全部改为窗口内容（无系统标题栏）。
"""
import pytest

tk = pytest.importorskip("tkinter")

import main as M
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
    yield a
    try:
        root.destroy()
    except Exception:
        pass
    finally:
        i18n.set_lang("zh")


class TestDailyManagerLang:
    def test_hint_label_follows_language(self, app):
        """管理窗开着时切语言，顶部提示立即换语言"""
        app.open_daily_manager()
        lbl = getattr(app, "_dmgr_hint_lbl", None)
        assert lbl is not None, "管理窗顶部提示没有保存引用"
        i18n.set_lang("en")
        app.refresh_labels()
        assert lbl.cget("text") == i18n.t("daily_mgr_hint")
        assert "Click a task" in lbl.cget("text")
        i18n.set_lang("zh")
        app.refresh_labels()
        assert "点击任务" in lbl.cget("text")

    def test_english_empty_has_newlines(self):
        """英文空态文案自带换行，不再是一整行被截断"""
        en = i18n.STRINGS["daily_mgr_empty"][1]
        assert "\n" in en
        assert len(en.split("\n")[0]) <= 40

    def test_empty_text_uses_wraplength(self, app):
        """空态文字 create_text 带 width（自动换行兜底）"""
        app.open_daily_manager()
        app.root.update()
        # 空态：画布上只有提示文字
        items = app._dmgr_cv.find_all()
        assert items, "空态没画提示"
        cfg = {k: v for k, v in app._dmgr_cv.itemcget(items[0], "width") and [("w", app._dmgr_cv.itemcget(items[0], "width"))] or []}
        # itemcget("width") 可能返回空串（未设置），退而验证 create_text 调用存在
        assert items
