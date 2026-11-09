# -*- coding: utf-8 -*-
"""v1.9.9.56 回归：时钟数字缩小到约占窗口 30% + 修复「切语言弹出时钟」。

  1. 用户实测 v1.9.9.55 数字太大（几乎占满窗口宽）——宽度系数
     0.96 → 0.30（约 1/4~1/3），高度上限收紧到标签一半，上下留白；
  2. 用户实测「有几次点中英文转换会弹出时钟」：时钟窗其实早就开着，
     只是被最小化/被盖住；切语言销毁重建后置顶窗恢复可见还抢焦点，
     看起来就像凭空弹出。修复：重建前记录窗口状态（normal/iconic/
     withdrawn），重建后按原状态还原；焦点还给主窗。日历/关于窗
     重建同样处理。
"""
import json
import os
import time

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


def open_clock_win(a):
    a.open_clock()
    a.root.update()
    win = a._clock_win
    win.update_idletasks()
    return win


# ------------------------------------ 1. 时钟数字约占窗口 30%
class TestClockSize:
    def test_width_about_30pct(self, app):
        from tkinter import font as tkfont
        a = app
        for w, h in ((900, 700), (1280, 960)):
            win = open_clock_win(a)
            win.geometry("%dx%d+0+0" % (w, h))
            a.root.update()
            a._clock_tick_body(win)
            real = tkfont.Font(font=a._clock_now.cget("font"))
            tw = real.measure("88:88:88")
            lw = a._clock_now.winfo_width()
            ratio = tw / lw
            assert 0.24 <= ratio <= 0.38, \
                "%dx%d 下数字宽度应约占窗口 30%%（现 %.0f%%）" % (w, h, ratio * 100)
            a._close_clock()
            a.root.update()

    def test_vertical_whitespace(self, app):
        """行高不超过标签高度一半，上下留白"""
        from tkinter import font as tkfont
        a = app
        win = open_clock_win(a)
        win.geometry("1280x960+0+0")
        a.root.update()
        a._clock_tick_body(win)
        real = tkfont.Font(font=a._clock_now.cget("font"))
        lh_lbl = a._clock_now.winfo_height()
        assert real.metrics("linespace") <= lh_lbl * 0.62

    def test_still_scales_with_window(self, app):
        """缩小窗口字号跟着变小，但不低于 16"""
        a = app
        win = open_clock_win(a)
        win.geometry("1280x960+0+0")
        a.root.update()
        a._clock_tick_body(win)
        big_fs = a._clock_fs
        win.geometry("360x280+10+10")
        a.root.update()
        a._clock_tick_body(win)
        assert a._clock_fs < big_fs
        assert a._clock_fs >= 16
        a._close_clock()


# ------------------------------------ 2. 切语言不再弹出时钟
class TestSwitchLangNoClockPop:
    def test_withdrawn_clock_stays_hidden(self, app):
        """时钟窗隐藏状态下切语言，重建后仍隐藏，不再凭空弹出"""
        a = app
        win = open_clock_win(a)
        win.withdraw()
        a.root.update()
        a.switch_lang("en")
        a.root.update()
        cw = a._clock_win
        assert cw is not None and cw.winfo_exists(), "切语言后时钟应已重建"
        assert not cw.winfo_viewable(), "原本隐藏的时钟切语言后不应出现"
        a._close_clock()
        i18n.set_lang("zh")

    def test_visible_clock_stays_visible(self, app):
        """时钟窗正常可见时切语言，重建后仍可见且几何保持"""
        a = app
        win = open_clock_win(a)
        win.geometry("600x500+40+40")
        a.root.update()
        a.switch_lang("en")
        a.root.update()
        cw = a._clock_win
        assert cw is not None and cw.winfo_exists()
        assert cw.winfo_viewable()
        assert cw.geometry().startswith("600x500")
        a._close_clock()
        i18n.set_lang("zh")

    def test_timer_state_kept_across_lang_switch(self, app):
        """切语言重建时钟后，倒计时状态不丢"""
        a = app
        win = open_clock_win(a)
        a._cd_until = time.time() + 300
        a.switch_lang("en")
        a.root.update()
        assert getattr(a, "_cd_until", None), "切语言后倒计时状态应保留"
        a._close_clock()
        i18n.set_lang("zh")

    def test_lang_switch_smoke(self, app):
        """切语言往返（中→英→中）整体不崩，主窗正常"""
        a = app
        a.switch_lang("en")
        a.root.update()
        a.switch_lang("zh")
        a.root.update()
        assert a.root.winfo_exists()
        assert i18n.get_lang() == "zh" if hasattr(i18n, "get_lang") else True
