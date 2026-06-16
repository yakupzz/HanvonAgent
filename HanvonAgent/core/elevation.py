"""
UAC elevation helper.

Re-launches the current executable with administrator rights to run a
``--svc-admin <action>`` subcommand (install / remove / start / stop the
Windows service). Service control under NSSM requires elevation, so the GUI
spawns an elevated copy of itself rather than running privileged code inline.

Mechanism
---------
``ShellExecuteW`` with the ``runas`` verb triggers the UAC prompt. We request
``SEE_MASK_NOCLOSEPROCESS`` so we receive a process handle and can wait for the
elevated subcommand to finish, then read its exit code.

The Win32 calls are isolated in ``_shell_execute_and_wait`` so the public
``run_elevated`` function is trivially unit-testable by patching that seam.
"""

from __future__ import annotations

import sys
from typing import List, Optional, Tuple

# ShellExecute returns a value > 32 on success; anything <= 32 is an error
# (including the user cancelling the UAC prompt).
_SHELL_EXECUTE_MIN_SUCCESS = 32

#: ShellExecuteEx mask: keep the process handle open so we can wait on it.
_SEE_MASK_NOCLOSEPROCESS = 0x00000040

#: WaitForSingleObject return value when the timeout elapses.
_WAIT_TIMEOUT = 0x00000102

#: Max time (ms) to wait for the elevated subprocess before giving up. Without a
#: bound a hung elevated copy would block the GUI thread forever.
_WAIT_TIMEOUT_MS = 60_000


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def _exe_path() -> str:
    """
    Path to relaunch with the 'runas' verb.

    Frozen: the bundled .exe (app_paths.exe_path()).
    Dev:    sys.executable (python.exe). ShellExecute cannot 'runas' a .py
            script, so we elevate the interpreter and let _build_args inject
            main.py as its first argument.
    """
    from core import app_paths

    if app_paths.is_frozen():
        return str(app_paths.exe_path())
    return sys.executable


def _build_args(action: str) -> List[str]:
    """Arguments passed to the elevated process (excluding the exe itself)."""
    args: List[str] = []
    # In dev mode the exe is the python interpreter and the "real" program is
    # main.py, so we must inject the script path before our flags.
    from core import app_paths

    if not app_paths.is_frozen():
        args.append(str(app_paths.app_dir() / "main.py"))
    args.extend(["--svc-admin", action])
    return args


def _shell_execute_and_wait(
    exe: str, args: List[str]
) -> Tuple[bool, Optional[int], Optional[str]]:
    """
    Launch ``exe`` elevated with ``args`` and wait for completion.

    Returns (launched, exit_code, message):
      * launched=False, message=None  → UAC cancelled or ShellExecute failed.
      * launched=False, message set    → the wait timed out; process was killed.
      * launched=True                  → exit_code holds the subprocess return code.
    """
    import ctypes
    from ctypes import wintypes

    class SHELLEXECUTEINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("fMask", wintypes.ULONG),
            ("hwnd", wintypes.HWND),
            ("lpVerb", wintypes.LPCWSTR),
            ("lpFile", wintypes.LPCWSTR),
            ("lpParameters", wintypes.LPCWSTR),
            ("lpDirectory", wintypes.LPCWSTR),
            ("nShow", ctypes.c_int),
            ("hInstApp", wintypes.HINSTANCE),
            ("lpIDList", ctypes.c_void_p),
            ("lpClass", wintypes.LPCWSTR),
            ("hkeyClass", wintypes.HKEY),
            ("dwHotKey", wintypes.DWORD),
            ("hIcon", wintypes.HANDLE),
            ("hProcess", wintypes.HANDLE),
        ]

    params = " ".join(_quote(a) for a in args)

    info = SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = _SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = exe
    info.lpParameters = params
    info.nShow = 0  # SW_HIDE — window gizli

    ok = ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info))
    if not ok or not info.hProcess:
        return (False, None, None)

    kernel32 = ctypes.windll.kernel32

    # Bounded wait: a hung elevated subprocess must not block the GUI forever.
    result = kernel32.WaitForSingleObject(info.hProcess, _WAIT_TIMEOUT_MS)
    if result == _WAIT_TIMEOUT:
        kernel32.TerminateProcess(info.hProcess, 1)
        kernel32.CloseHandle(info.hProcess)
        return (False, None, "Zaman aşımı: işlem yanıt vermedi")

    exit_code = wintypes.DWORD()
    kernel32.GetExitCodeProcess(info.hProcess, ctypes.byref(exit_code))
    kernel32.CloseHandle(info.hProcess)
    return (True, int(exit_code.value), None)


def _quote(arg: str) -> str:
    """Quote an argument for the ShellExecute parameter string if needed."""
    if " " in arg and not arg.startswith('"'):
        return f'"{arg}"'
    return arg


def run_elevated(action: str) -> Tuple[bool, str]:
    """
    Re-launch this app elevated to run ``--svc-admin <action>``.

    Returns (success, message). ``message`` is Turkish, suitable for surfacing
    in the GUI (status bar / message box / tray balloon).
    """
    if not _is_windows():
        return (False, "Windows olmayan sistemde servis işlemi yapılamaz.")

    exe = _exe_path()
    args = _build_args(action)

    try:
        launched, exit_code, message = _shell_execute_and_wait(exe, args)
    except Exception as exc:  # ShellExecute / ctypes failure
        return (False, f"İptal edildi veya başlatılamadı: {exc}")

    if not launched:
        if message:  # wait timed out — process was force-terminated
            return (False, message)
        return (False, "İptal edildi (yönetici izni verilmedi).")

    if exit_code == 0:
        return (True, f"Başarılı: {action}")

    return (False, f"Hata: çıkış kodu {exit_code}")
