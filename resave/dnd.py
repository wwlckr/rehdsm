"""Accept files dropped from Explorer onto a Tk window (Windows only, no extra packages).

Tkinter has no built-in file drop on Windows, so the top-level window procedure is
subclassed with ctypes to handle WM_DROPFILES.
"""
from __future__ import annotations

import sys
from typing import Callable

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4
POLL_MS = 100  # how often dropped files are handed to Tk

_hooks: list = []  # keep the callbacks alive (they are called from C)


def enable_file_drop(root, on_drop: Callable[[list[str]], None]) -> bool:
    """Call on_drop(paths) when files are dropped on `root`. Returns False if unsupported."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return False

    user32 = ctypes.windll.user32
    shell32 = ctypes.windll.shell32
    LRESULT = ctypes.c_ssize_t
    WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    # 32-bit Windows has no SetWindowLongPtrW export (it is a macro for SetWindowLongW there).
    set_window_long = getattr(user32, "SetWindowLongPtrW", None) or user32.SetWindowLongW
    set_window_long.restype = ctypes.c_void_p
    set_window_long.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_void_p)
    user32.CallWindowProcW.restype = LRESULT
    user32.CallWindowProcW.argtypes = (ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM,
                                       wintypes.LPARAM)
    shell32.DragAcceptFiles.argtypes = (wintypes.HWND, wintypes.BOOL)
    shell32.DragQueryFileW.restype = wintypes.UINT
    shell32.DragQueryFileW.argtypes = (wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT)
    shell32.DragFinish.argtypes = (wintypes.HANDLE,)

    root.update_idletasks()
    hwnd = int(root.wm_frame(), 16)  # outer frame window; child widgets pass drops up to it
    old_proc = None
    pending: list[list[str]] = []

    def proc(h, msg, wparam, lparam):
        if msg == WM_DROPFILES:
            hdrop = wintypes.HANDLE(wparam)
            paths = []
            for i in range(shell32.DragQueryFileW(hdrop, 0xFFFFFFFF, None, 0)):
                size = shell32.DragQueryFileW(hdrop, i, None, 0) + 1
                buf = ctypes.create_unicode_buffer(size)
                shell32.DragQueryFileW(hdrop, i, buf, size)
                paths.append(buf.value)
            shell32.DragFinish(hdrop)
            pending.append(paths)  # never call Tk from here: _tkinter is not re-entrant at this point
            return 0
        return user32.CallWindowProcW(old_proc, h, msg, wparam, lparam)

    callback = WNDPROC(proc)
    _hooks.append(callback)
    old_proc = set_window_long(hwnd, GWLP_WNDPROC, ctypes.cast(callback, ctypes.c_void_p))
    if not old_proc:
        _hooks.remove(callback)
        return False
    shell32.DragAcceptFiles(hwnd, True)

    def poll():
        while pending:
            on_drop(pending.pop(0))
        root.after(POLL_MS, poll)

    root.after(POLL_MS, poll)
    return True
