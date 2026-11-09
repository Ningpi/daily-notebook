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


# ------------------------- 1. 时钟字号恢复 v1.9.9.54 算法
# v1.9.9.57：用户要求回到 v54 的大小——固定系数估算 + 上限 120。
# 小窗口字号跟着变小，全屏稳定在 120（不再铺满、也不再是 30%）。
class TestClockSizeV54:
    def test_cap_120_fullscreen(self, app):
        a = app
        win = open_clock_win(a)
        win.geometry("1920x1080+0+0")
        a.root.update()
        a._clock_tick_body(win)
        assert a._clock_fs == 120, "全屏应稳定在上限 120（现 %s）" % a._clock_fs
        a._close_clock()

    def test_width_ratio_v54(self, app):
        """全屏下数字宽约占窗口三到四成，四周有留白（不是铺满）"""
        from tkinter import font as tkfont
        a = app
        win = open_clock_win(a)
        win.geometry("1920x1080+0+0")
        a.root.update()
        a._clock_tick_body(win)
        real = tkfont.Font(font=a._clock_now.cget("font"))
        tw = real.measure("88:88:88")
        lw = a._clock_now.winfo_width()
        ratio = tw / lw
        assert 0.25 <= ratio <= 0.55, \
            "全屏数字宽度应约占窗口三到四成（现 %.0f%%）" % (ratio * 100)
        a._close_clock()

    def test_still_scales_small_window(self, app):
        """小窗口字号跟着变小，且不低于 16"""
        a = app
        win = open_clock_win(a)
        win.geometry("1920x1080+0+0")
        a.root.update()
        a._clock_tick_body(win)
        big = a._clock_fs
        win.geometry("360x280+10+10")
        a.root.update()
        a._clock_tick_body(win)
        assert a._clock_fs < big
        assert a._clock_fs >= 16
        a._close_clock()

    def test_never_exceeds_cap(self, app):
        a = app
        win = open_clock_win(a)
        for w, h in ((780, 620), (1280, 960), (1920, 1080)):
            win.geometry("%dx%d+0+0" % (w, h))
            a.root.update()
            a._clock_tick_body(win)
            assert a._clock_fs <= 120, "%dx%d 字号不应超过 120" % (w, h)
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
