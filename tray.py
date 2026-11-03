# -*- coding: utf-8 -*-
"""系统托盘常驻（v1.9.9.20）

目标：关掉主窗口也不丢提醒。原来点 ✕ 直接退出进程，提醒随之失效。

实现选择：**不引入 pystray / Pillow**，直接用 ctypes 调 Windows 原生
Shell_NotifyIconW。理由：
  - 不增加任何 pip 依赖，打包体积不变，打包脚本无需改动；
  - 托盘图标用现成的 assets/icon.ico（LoadImage 直接读），不必再转
    HICON；
  - 气泡提醒用 NIF_INFO（系统原生通知），Windows 10/11 会走通知中心，
    点一下还能回到主窗口。

对外接口（全部在非 Windows 或初始化失败时安全降级为 no-op）：
    tray = Tray(app)
    tray.start()                     # 建图标 + 消息窗口（后台线程跑消息泵）
    tray.notify("标题", "正文")       # 弹气泡
    tray.update_tip("今日还有 3 件")  # 更新悬停提示
    tray.hide() / tray.show()        # 临时隐藏 / 恢复
    tray.stop()                      # 退出时清理
    tray.available                   # bool，是否真的可用
"""
import os
import threading

try:
    import ctypes
    from ctypes import wintypes
    _HAS_CTYPES = True
except Exception:                                   # pragma: no cover
    _HAS_CTYPES = False


WM_APP = 0x8000
WM_TRAYICON = WM_APP + 20
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIIF_INFO = 0x00000001
IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x0010, 0x0040
IDI_APPLICATION = 32512
CS_DBLCLKS = 0x0008


class _NOTIFYICONDATA(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
    ]


class _WNDCLASS(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", ctypes.c_void_p),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


# WINFUNCTYPE 只有 Windows 的 ctypes 才有；非 Windows 上用一个占位，
# 保证模块可以安全 import（否则 Linux/macOS 打包或跑测试直接 ImportError）
if hasattr(ctypes, "WINFUNCTYPE"):
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)
else:                                               # pragma: no cover
    WNDPROC = None


class Tray:
    """托盘图标 + 气泡通知。非 Windows 或任何一步失败都静默降级。"""

    available = False

    def __init__(self, app, icon_path=None):
        self.app = app
        self.icon_path = icon_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "assets", "icon.ico")
        self.hwnd = None
        self.hicon = None
        self._thread = None
        self._ready = threading.Event()
        self._nid = None
        self._wndproc_ref = None       # 必须持有引用，否则回调被 GC 掉

    # ---------------- 初始化
    def start(self):
        if os.name != "nt" or not _HAS_CTYPES:
            return False
        try:
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="tray")
            self._thread.start()
            self._ready.wait(3)        # 等窗口建好再回；失败也不阻塞启动
        except Exception:
            return False
        return self.available

    def _run(self):
        try:
            self._create_window()
            self._add_icon()
            self.available = True
        except Exception:
            self.available = False
        finally:
            self._ready.set()
        if self.available:
            self._pump()

    def _create_window(self):
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        hinst = k32.GetModuleHandleW(None)
        cls_name = "DailyNotebookTrayWnd"
        self._wndproc_ref = WNDPROC(self._wnd_proc)
        wc = _WNDCLASS()
        wc.style = CS_DBLCLKS
        wc.lpfnWndProc = ctypes.cast(self._wndproc_ref, ctypes.c_void_p)
        wc.hInstance = hinst
        wc.lpszClassName = cls_name
        # 已注册过（重启同一进程内）会失败，忽略即可
        u32.RegisterClassW(ctypes.byref(wc))
        self.hwnd = u32.CreateWindowExW(0, cls_name, "DailyNotebookTray",
                                        0, 0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            raise OSError("CreateWindowExW failed")

    def _load_icon(self):
        u32 = ctypes.windll.user32
        h = 0
        if os.path.exists(self.icon_path):
            h = u32.LoadImageW(None, self.icon_path, IMAGE_ICON, 0, 0,
                               LR_LOADFROMFILE | LR_DEFAULTSIZE)
        if not h:
            h = u32.LoadIconW(None, ctypes.c_wchar_p(IDI_APPLICATION))
        return h

    def _build_nid(self):
        nid = _NOTIFYICONDATA()
        nid.cbSize = ctypes.sizeof(_NOTIFYICONDATA)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        nid.uCallbackMessage = WM_TRAYICON
        nid.hIcon = self.hicon
        nid.szTip = self.app_name()[:100]
        return nid

    def app_name(self):
        try:
            return self.app.app_name()
        except Exception:
            return "每日记事本"

    def _add_icon(self):
        self.hicon = self._load_icon()
        if not self.hicon:
            raise OSError("no icon")
        self._nid = self._build_nid()
        if not ctypes.windll.shell32.Shell_NotifyIconW(NIM_ADD,
                                                       ctypes.byref(self._nid)):
            raise OSError("Shell_NotifyIcon NIM_ADD failed")

    # ---------------- 消息泵
    def _pump(self):
        u32 = ctypes.windll.user32
        msg = wintypes.MSG()
        while u32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u32.TranslateMessage(ctypes.byref(msg))
            u32.DispatchMessageW(ctypes.byref(msg))

    def _wnd_proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == WM_TRAYICON:
                low = lparam & 0xFFFF
                if low in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                    self._invoke(self._on_click)
                elif low == WM_RBUTTONUP:
                    self._invoke(self._on_right)
                return 0
            if msg == WM_DESTROY:
                ctypes.windll.user32.PostQuitMessage(0)
                return 0
        except Exception:
            pass
        return ctypes.windll.user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _invoke(self, fn):
        """从托盘线程回到 Tk 主线程执行（Tk 不是线程安全的）"""
        try:
            self.app.root.after(0, fn)
        except Exception:
            pass

    def _on_click(self):
        cb = getattr(self.app, "restore_from_tray", None)
        if cb:
            cb()

    def _on_right(self):
        cb = getattr(self.app, "tray_menu", None)
        if cb:
            cb()

    # ---------------- 外部操作
    def notify(self, title, text):
        """弹一个系统气泡（Windows 10/11 走通知中心）"""
        if not self.available or not self._nid:
            return False
        try:
            nid = self._nid
            nid.uFlags = NIF_INFO
            nid.szInfoTitle = (title or "")[:60]
            nid.szInfo = (text or "")[:250]
            nid.dwInfoFlags = NIIF_INFO
            ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY,
                                                    ctypes.byref(nid))
            self._nid = nid
            return True
        except Exception:
            return False

    def update_tip(self, text):
        if not self.available or not self._nid:
            return
        try:
            nid = self._build_nid()
            nid.szTip = (text or "")[:100]
            ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY,
                                                    ctypes.byref(nid))
            self._nid = nid
        except Exception:
            pass

    def hide(self):
        if not self.available or not self._nid:
            return
        try:
            ctypes.windll.shell32.Shell_NotifyIconW(NIM_DELETE,
                                                    ctypes.byref(self._nid))
        except Exception:
            pass

    def stop(self):
        self.hide()
        try:
            if self.hwnd:
                ctypes.windll.user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)
        except Exception:
            pass
        self.available = False
