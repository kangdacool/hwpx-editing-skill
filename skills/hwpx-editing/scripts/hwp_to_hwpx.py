#!/usr/bin/env python3
"""Batch-convert legacy .hwp (OLE binary) to .hwpx — including password-protected ones.

This skill edits `.hwpx` only, so a legacy `.hwp` has to be converted first. The
documentation used to say "open it in 한글 and 다른 이름으로 저장" — fine for one
file, useless for a folder of 5,000. This automates it by driving the installed
한글 program through its COM interface (the same thing a person clicks), so the
output is exactly 한글's own export.

Requires: Windows + 한글(HWP) installed + `pywin32`.
Optional:  `pywinauto` (only for password-protected files), `olefile` (password
detection without opening anything).

    python hwp_to_hwpx.py FOLDER                     # convert every .hwp under FOLDER
    python hwp_to_hwpx.py FOLDER --password 1234     # try this password on locked files
    python hwp_to_hwpx.py FOLDER --scan              # only report which files are locked
    python hwp_to_hwpx.py FOLDER --to pdf            # convert to .pdf instead
    python hwp_to_hwpx.py FILE.hwp                   # a single file works too

WHY THIS FILE IS LONGER THAN YOU EXPECT (2026-08-19, 5,187-file batch)
---------------------------------------------------------------------
Every guard below exists because its absence produced a **silent infinite hang**,
not an error. 한글's COM surface has no timeout: when it wants a dialog answered,
`Open()` simply never returns. Four separate causes look identical from outside:

1. **Security module not registered** → 한글 raises an INVISIBLE "파일 접근 허용"
   dialog (window class `HNC_DIALOG`, `IsWindowVisible == 0`). The module name must
   be exactly `FilePathCheckerModule`; 한컴's own sample code says
   `FilePathCheckerModuleExample`, and copying that is the classic way to lose an
   afternoon. `_register_security_module()` self-heals by installing+registering
   the DLL, then re-checks.
2. **Password-protected document** → the "문서 암호" dialog. 한컴 deliberately
   provides no API to pass a password to `Open()` (official forum answer), which is
   easy to read as "impossible" — but the *dialog* is automatable. Two catches:
   the OK button's `invoke()`/`click` do nothing (send `{ENTER}` to the edit field),
   and UIA manipulation only works from the **main thread**.
3. **Post-open modal** → even after the password is accepted, every later COM call
   (`SaveAs`, `GetTextFile`, …) hangs on another unnamed `HNC_DIALOG` that has no
   usable button. `SetMessageBoxMode(0x00011011)` before `Open()` clears it.
4. **A genuinely broken file** → nothing helps, so each file gets its own timeout
   and the batch moves on instead of stopping.

Because all four present as "it stopped", diagnose by turning conditions on one at
a time rather than guessing.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

MODULE_NAME = "FilePathCheckerModule"
_REG_KEY = r"Software\HNC\HwpAutomation\Modules"

# Makes 한글 auto-answer the dialogs that otherwise block every COM call once a
# password-protected document is open. 0x20 and "unset" both fail; this value was
# established by trial on real locked files.
MESSAGEBOX_AUTO_ANSWER = 0x00011011

TIMEOUT_SEC = 45          # per file; a stuck file must not stop the batch
PASSWORD_DIALOG_TITLE = "문서 암호"


# ---------------------------------------------------------------- password bit

def is_password_protected(path):
    """(True/False/None, reason). Reads the HWP 5.0 `FileHeader` stream: the DWORD
    at offset 36 is a property bitfield and **bit 1 (0x02) means "password set"**.
    No 한글, no opening, no risk — a 5,000-file folder scans in minutes, which is
    what makes it practical to skip or specially-handle locked files up front."""
    try:
        import olefile
    except ImportError:
        return None, "olefile not installed"
    try:
        if not olefile.isOleFile(str(path)):
            return None, "not an OLE (HWP5) file — .hwpx or something else"
        with olefile.OleFileIO(str(path)) as ole:
            if not ole.exists("FileHeader"):
                return None, "no FileHeader stream"
            head = ole.openstream("FileHeader").read(40)
        if len(head) < 40 or not head.startswith(b"HWP Document File"):
            return None, "HWP signature mismatch"
        return bool(int.from_bytes(head[36:40], "little") & 0x02), None
    except Exception as e:
        return None, f"read failed: {e}"


# ------------------------------------------------------------- security module

def _security_module_dll():
    local = os.environ.get("LOCALAPPDATA", os.path.expanduser(r"~\AppData\Local"))
    stable = Path(local) / "HwpSecurityModule" / "FilePathCheckerModule.dll"
    candidates = [stable, Path(__file__).resolve().parent / "FilePathCheckerModule.dll"]
    try:
        import pyhwpx
        candidates.append(Path(pyhwpx.__file__).resolve().parent / "FilePathCheckerModule.dll")
    except Exception:
        pass
    src = next((p for p in candidates if p.exists()), None)
    if src is None:
        return None
    try:
        stable.parent.mkdir(parents=True, exist_ok=True)
        if not stable.exists():
            shutil.copyfile(src, stable)
        dll = stable if stable.exists() else src
        import winreg
        k = winreg.CreateKey(winreg.HKEY_CURRENT_USER, _REG_KEY)
        winreg.SetValueEx(k, MODULE_NAME, 0, winreg.REG_SZ, str(dll))
        winreg.CloseKey(k)
        return dll
    except Exception:
        return src


def _register_security_module(hwp):
    """Suppress the invisible "파일 접근 허용" modal. Self-heals a missing/broken
    registration. Returns False only if no DLL exists anywhere — in which case do
    NOT proceed to Open(), or it will hang forever with nothing on screen."""
    if hwp.RegisterModule("FilePathCheckDLL", MODULE_NAME):
        return True
    if _security_module_dll() is None:
        return False
    return bool(hwp.RegisterModule("FilePathCheckDLL", MODULE_NAME))


# ------------------------------------------------------------ password dialog

def _find_password_dialog():
    try:
        import win32gui
        import win32process
        import psutil
    except ImportError:
        return None
    found = []

    def cb(hwnd, _):
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if psutil.Process(pid).name().lower() != "hwp.exe":
                return
        except Exception:
            return
        if win32gui.IsWindowVisible(hwnd) and win32gui.GetWindowText(hwnd) == PASSWORD_DIALOG_TITLE:
            found.append(hwnd)

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        return None
    return found[0] if found else None


def _fill_password_dialog(passwords, attempt, report):
    """Fill the visible 문서 암호 dialog with one candidate. Returns True if it acted.

    ⚠️ **Call this from the MAIN thread.** From a worker thread the dialog is still
    *found* but the UIA manipulation silently does nothing — no exception, so the
    only symptom is that the file never converts.
    ⚠️ **Submit with `{ENTER}` on the edit field.** The 확인 button's `invoke()` and
    `click_input()` leave the dialog open."""
    hwnd = _find_password_dialog()
    if hwnd is None:
        return False
    try:
        from pywinauto import Desktop
    except ImportError:
        report["error"] = "pywinauto not installed — cannot answer the password dialog"
        return False
    try:
        dlg = Desktop(backend="uia").window(handle=hwnd)
        edits = dlg.descendants(control_type="Edit")
        if not edits:
            return False
        if attempt < len(passwords):
            edits[0].set_focus()
            edits[0].set_edit_text(passwords[attempt])
            edits[0].type_keys("{ENTER}")
            report["tried"] = report.get("tried", 0) + 1
        else:
            cancel = next((b for b in dlg.descendants(control_type="Button")
                           if b.window_text().startswith("취소")), None)
            if cancel is not None:
                cancel.click_input()
            report["exhausted"] = True
        return True
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        return False


# ------------------------------------------------------------------ conversion

def _kill_hwp():
    """⚠️ Kills EVERY Hwp.exe. Run only one instance of this tool at a time, and
    not while someone is using 한글 interactively."""
    subprocess.run(["taskkill", "/IM", "Hwp.exe", "/F"], capture_output=True)


def _convert_worker(src, dst, fmt, result):
    """Own COM object per file: a COM object is apartment-bound to the thread that
    created it, so handing one to another thread fails outright. A fresh object
    also means a timed-out file cannot corrupt the next one's state."""
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    hwp = None
    try:
        hwp = win32com.client.Dispatch("HWPFrame.HwpObject")
        if not _register_security_module(hwp):
            result["error"] = ("security module (FilePathCheckerModule) not registered — "
                               "Open() would hang on an invisible dialog. pip install pyhwpx")
            return
        try:
            hwp.SetMessageBoxMode(MESSAGEBOX_AUTO_ANSWER)
        except Exception:
            pass
        in_fmt = "HWPX" if str(src).lower().endswith(".hwpx") else "HWP"
        result["stage"] = "opening"
        if not hwp.Open(str(src), in_fmt, "forceopen:true"):
            result["error"] = "Open() returned False (wrong password?)"
            return

        # A password-protected source **carries its protection into the .hwpx**:
        # 한글 happily exports, but `Contents/section0.xml` comes out encrypted, so
        # every XML tool (this skill included) sees binary garbage instead of markup.
        # Copying the body into a fresh document drops the document-level protection.
        # (PDF export is unaffected — this is only needed for HWPX/HWP output.)
        if result.get("_locked") and fmt in ("HWPX", "HWP"):
            result["stage"] = "stripping_password"
            hwp.Run("SelectAll")
            hwp.Run("Copy")
            hwp.XHwpDocuments.Add(0)      # new, unprotected document
            hwp.Run("Paste")

        result["stage"] = "saving"
        hwp.SaveAs(str(dst), fmt, "")
        result["stage"] = "done"
        result["ok"] = True
        try:
            hwp.Clear(1)
        except Exception:
            pass
    except Exception as e:
        result["error"] = repr(e)
    finally:
        try:
            if hwp is not None:
                hwp.Quit()
        except Exception:
            pass
        pythoncom.CoUninitialize()


def hwpx_is_readable(path):
    """(True/False, reason) — is this .hwpx actually parseable XML?

    Exists because a *successful-looking* conversion can still be useless: exporting
    a password-protected .hwp to .hwpx keeps the protection, so `Contents/section0.xml`
    is encrypted bytes rather than markup and every tool in this skill fails on it.
    Checking the output beats discovering it three steps later."""
    import zipfile
    try:
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.startswith("Contents/section")]
            if not names:
                return False, "no Contents/section*.xml in the package"
            head = z.read(names[0]).lstrip()[:1]
    except Exception as e:
        return False, f"not a readable zip: {e}"
    if head != b"<":
        return False, ("output is still encrypted (section XML is binary) — the source "
                       "password carried over; conversion needs the password-stripping path")
    return True, ""


def convert_one(src: Path, out_ext: str, fmt: str, passwords, stage_dir: Path):
    """Convert one file. Returns (ok, reason).

    The source is staged into a temp folder and only the result is moved back, so
    the original is never opened in place (safer, and avoids odd behaviour with
    cloud-synced placeholder files)."""
    dst = src.with_suffix(out_ext)
    staged_src = stage_dir / src.name
    staged_dst = staged_src.with_suffix(out_ext)
    shutil.copy2(src, staged_src)

    locked, _ = is_password_protected(src)
    result, report = {"_locked": bool(locked)}, {}
    t = threading.Thread(target=_convert_worker,
                         args=(staged_src, staged_dst, fmt, result), daemon=True)
    t.start()
    if locked and passwords:
        deadline, attempt = time.monotonic() + TIMEOUT_SEC, 0
        while t.is_alive() and time.monotonic() < deadline:
            if _fill_password_dialog(passwords, attempt, report):
                attempt += 1
                time.sleep(1.5)
            else:
                time.sleep(0.4)
        t.join(max(0.0, deadline - time.monotonic()))
    else:
        t.join(TIMEOUT_SEC)

    try:
        if t.is_alive():
            _kill_hwp()
            hint = "" if not locked else " (locked; pass --password, and install pywinauto)"
            return False, f"timeout after {TIMEOUT_SEC}s{hint}"
        if result.get("ok") and staged_dst.exists():
            if out_ext == ".hwpx":
                usable, why = hwpx_is_readable(staged_dst)
                if not usable:
                    return False, why       # don't hand back a file the tools can't open
            shutil.move(str(staged_dst), str(dst))
            return True, ""
        return False, report.get("error") or result.get("error") or "unknown failure"
    finally:
        for p in (staged_src, staged_dst):
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass          # 한글 may still hold it right after a kill


def find_inputs(target: Path):
    if target.is_file():
        return [target] if target.suffix.lower() == ".hwp" else []
    return sorted(p for p in target.rglob("*") if p.suffix.lower() == ".hwp" and p.is_file())


def main():
    ap = argparse.ArgumentParser(description="Legacy .hwp -> .hwpx batch converter")
    ap.add_argument("target", help="a .hwp file, or a folder to scan recursively")
    ap.add_argument("--to", choices=["hwpx", "pdf"], default="hwpx")
    ap.add_argument("--password", action="append", default=[],
                    help="candidate password for locked files (repeatable)")
    ap.add_argument("--scan", action="store_true", help="only report which files are locked")
    ap.add_argument("--force", action="store_true", help="reconvert even if output is newer")
    a = ap.parse_args()

    target = Path(a.target).resolve()
    if not target.exists():
        print(f"[ABORT] not found: {target}")
        return 2
    files = find_inputs(target)
    if not files:
        print("No .hwp files found. Nothing to do.")
        return 0

    if a.scan:
        locked = [f for f in files if is_password_protected(f)[0]]
        unknown = [f for f in files if is_password_protected(f)[0] is None]
        print(f"{len(files)} file(s): {len(locked)} password-protected, "
              f"{len(files) - len(locked) - len(unknown)} open, {len(unknown)} undetermined")
        for f in locked[:40]:
            print(f"  locked: {f}")
        if len(locked) > 40:
            print(f"  ... and {len(locked) - 40} more")
        return 1 if locked else 0

    out_ext = ".hwpx" if a.to == "hwpx" else ".pdf"
    fmt = "HWPX" if a.to == "hwpx" else "PDF"
    todo = [f for f in files
            if a.force or not (f.with_suffix(out_ext).exists()
                               and f.with_suffix(out_ext).stat().st_mtime >= f.stat().st_mtime)]
    print(f"{len(files)} .hwp file(s); converting {len(todo)} to {out_ext}"
          + (f" ({len(files) - len(todo)} already up to date)" if len(todo) < len(files) else ""))
    if not todo:
        return 0

    try:
        import win32com.client  # noqa: F401
    except ImportError:
        print("[ABORT] pywin32 missing.  pip install pywin32")
        return 1

    n_locked = sum(1 for f in todo if is_password_protected(f)[0])
    if n_locked:
        if a.password:
            print(f"  {n_locked} file(s) are password-protected — will answer the dialog.")
        else:
            print(f"  [WARN] {n_locked} file(s) are password-protected and no --password "
                  f"was given; they will time out. Re-run with --password.")

    stage_dir = Path(tempfile.mkdtemp(prefix="hwp2hwpx_"))
    ok, failed = [], []
    try:
        for i, src in enumerate(todo, 1):
            print(f"  [{i}/{len(todo)}] {src.name}", flush=True)
            good, why = convert_one(src, out_ext, fmt, a.password, stage_dir)
            (ok if good else failed).append((src, why))
            if not good:
                print(f"      FAILED: {why}")
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)

    print(f"\nconverted {len(ok)}, failed {len(failed)}")
    for src, why in failed[:30]:
        print(f"  - {src.name}: {why}")
    if len(failed) > 30:
        print(f"  ... and {len(failed) - 30} more")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
