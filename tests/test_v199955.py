# -*- coding: utf-8 -*-
"""v1.9.9.55 回归：全屏时钟自适应 + 「···」三点图标换新 + 颜色状态。

  1. 时钟：全屏下时间数字四周大片留白、最大化后字号不跟着放大——
     旧公式固定系数估算且上限 120，全屏早顶到上限。改为 tkfont 实测
     「88:88:88」像素宽高反解字号，上限 500，用负字号（像素）精确套用；
  2. 三点按钮：按用户提供的 SVG（三个点点-copy.svg，1024 视窗三颗
     r≈113.5 圆、圆心距 329）重绘比例，点更饱满；颜色有前后状态：
     平时主题字色 → 悬停/点开关于窗变强调色 → 关窗还原；
  3. 回归冒烟：对话建任务/打卡/便签/关于窗内容/窗口缩放风暴。
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


def send(a, text):
    a.entry.delete(0, "end")
    a._compose_placeholder = False
    a.entry.insert(0, text)
    a.on_send()
    a.root.update()


def find_head_dots(a, timeout=0.8):
    """等头部三点画出来再取（draw_head 是启动 30ms 后经 after 调用的）。

    头部画布里只有这三颗椭圆，直接按类型过滤即可。"""
    import time as _t
    deadline = _t.time() + timeout
    out = []
    while _t.time() < deadline:
        a.root.update()
        cv = a.head
        out = [it for it in cv.find_all() if cv.type(it) == "oval"]
        if len(out) == 3:
            return out
        _t.sleep(0.03)
    a.root.update()
    return [it for it in a.head.find_all() if a.head.type(it) == "oval"]


def open_clock_win(a):
    a.open_clock()
    a.root.update()
    win = a._clock_win
    win.update_idletasks()
    return win


# ------------------------------------------------ 1. 时钟全屏自适应

    def test_fullscreen_font_grows(self, app):
        a = app
        win = open_clock_win(a)
        # 先小窗
        win.geometry("500x400+30+30")
        a.root.update()
        a._clock_tick_body(win)
        small_fs = a._clock_fs
        # 放大到全屏量级：旧版上限 120，新版必须显著超过
        win.geometry("1280x960+0+0")
        a.root.update()
        a._clock_tick_body(win)
        big_fs = a._clock_fs
        assert big_fs > 120, "全屏字号应突破旧版 120 上限（现 %s）" % big_fs
        assert big_fs > small_fs * 1.5, "最大化后字号应明显变大"

    def test_shrink_font_falls(self, app):
        a = app
        win = open_clock_win(a)
        win.geometry("1280x960+0+0")
        a.root.update()
        a._clock_tick_body(win)
        big_fs = a._clock_fs
        win.geometry("360x280+10+10")
        a.root.update()
        a._clock_tick_body(win)
        small_fs = a._clock_fs
        assert small_fs < big_fs
        assert 16 <= small_fs <= 500

    def test_font_is_pixel_sized(self, app):
        """实测：时间文字宽度应基本铺满标签（旧版 120 上限只有一半左右）"""
        from tkinter import font as tkfont
        a = app
        win = open_clock_win(a)
        win.geometry("900x700+0+0")
        a.root.update()
        a._clock_tick_body(win)
        real = tkfont.Font(font=a._clock_now.cget("font"))
        tw = real.measure("88:88:88")
        lw = a._clock_now.winfo_width()
        lh = a._clock_now.winfo_height()
        assert tw <= lw * 1.02, "时间宽度不应溢出标签（%d vs %d）" % (tw, lw)
        assert tw >= lw * 0.85, "时间宽度应基本铺满（%d vs %d，旧版上限只占一半）" % (tw, lw)
        assert real.metrics("linespace") <= lh * 1.02, "行高不应超出标签"
        a._close_clock()

    def test_min_floor_16(self, app):
        a = app
        win = open_clock_win(a)
        win.geometry("240x200+0+0")
        a.root.update()
        a._clock_tick_body(win)
        assert a._clock_fs >= 16
        a._close_clock()

    def test_tick_survives_close(self, app):
        """关窗后心跳不再报错（finally 续期保护依然有效）"""
        a = app
        win = open_clock_win(a)
        a._close_clock()
        a.root.update()
        assert getattr(a, "_clock_win", None) is None


# ------------------------------------------------ 2. 三点按钮新图标
class TestDotsButton:
    def test_dots_exist_and_svg_ratio(self, app):
        a = app
        dots = find_head_dots(a)
        assert len(dots) == 3, "头部应有三颗圆点（SVG 同构）"
        xs = sorted((a.head.coords(d)[0] + a.head.coords(d)[2]) / 2 for d in dots)
        spacing = xs[1] - xs[0]
        r = (a.head.coords(dots[0])[2] - a.head.coords(dots[0])[0]) / 2
        ratio = r / spacing
        assert 0.30 <= ratio <= 0.40, "r/间距应落在 SVG 比例 0.345 附近（现 %.2f）" % ratio

    def test_dots_idle_color_is_text(self, app):
        a = app
        dots = find_head_dots(a)
        for d in dots:
            assert a.head.itemcget(d, "fill") == M.C.TEXT

    def test_open_about_lights_dots(self, app):
        """点击后（关于窗开着）三点变强调色——点击前后的颜色区分"""
        a = app
        a.open_about()
        a.root.update()
        for d in getattr(a, "_dots_items", []):
            assert a.head.itemcget(d, "fill") == M.C.ACCENT
        w = a._about_win
        assert w is not None and w.winfo_exists()

    def test_close_about_restores_dots(self, app):
        a = app
        a.open_about()
        a.root.update()
        a._about_win.destroy()
        a.root.update()
        time.sleep(0.25)               # 等 Destroy 重绘防抖（120ms）
        a.root.update()
        dots = find_head_dots(a)
        assert len(dots) == 3
        for d in dots:
            assert a.head.itemcget(d, "fill") == M.C.TEXT, "关掉关于窗后应还原主题字色"

    def test_redraw_with_about_open_keeps_accent(self, app):
        """关于窗开着时主题换色/头部重绘，三点保持强调色"""
        a = app
        a.open_about()
        a.root.update()
        a.draw_head()
        a.root.update()
        dots = find_head_dots(a)
        assert len(dots) == 3
        for d in dots:
            assert a.head.itemcget(d, "fill") == M.C.ACCENT


# ------------------------------------------------ 3. 回归冒烟
class TestRegression:
    def test_parse_task_still_works(self, app):
        a = app
        send(a, "明天下午3点开会")
        send(a, "后天买牛奶")
        todos = [t for t in a.store.tasks if not t.get("done")]
        assert len(todos) == 2

    def test_clock_geom_saved(self, app, tmp_path):
        a = app
        win = open_clock_win(a)
        win.geometry("600x500+40+40")
        a.root.update()
        a._save_clock_geom()
        a._close_clock()
        assert getattr(a.store, "clock_geom", None)

    def test_about_shows_version(self, app):
        a = app
        a.open_about()
        a.root.update()
        w = a._about_win
        assert w is not None and w.winfo_exists()
        w.destroy()
        a.root.update()
        time.sleep(0.25)
        a.root.update()

    def test_resize_storm_no_crash(self, app):
        a = app
        for w, h in ((500, 400), (700, 500), (430, 660), (900, 700), (430, 660)):
            a.root.geometry("%dx%d+0+0" % (w, h))
            a.root.update()
        a._watch_canvas_width()
        time.sleep(0.1)
        a.root.update()
        assert a.root.winfo_exists()
