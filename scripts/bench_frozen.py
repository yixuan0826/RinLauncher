"""Measure frozen-package cold start: process launch → first visible window.

Usage::

    python scripts/bench_frozen.py
    python scripts/bench_frozen.py --iterations 5 --json build/bench-frozen.json

The benchmark temporarily writes ``appmodset.conf`` next to the exe (first-run
off), uses a throwaway config directory, then restores the file.  It does not
touch the user's ``%APPDATA%\\RinLauncher`` data.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_EXE = ROOT / "dist" / "RinLauncher" / "RinLauncher.exe"
WINDOW_WAIT_SECONDS = 30.0

_user32 = ctypes.windll.user32 if sys.platform == "win32" else None
_WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)


def _visible_window(pid: int) -> int | None:
    if _user32 is None:
        return None
    found: list[int] = []

    @_WNDENUMPROC
    def callback(hwnd, _lparam):
        window_pid = ctypes.c_ulong()
        _user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
        if window_pid.value != pid or not _user32.IsWindowVisible(hwnd):
            return True
        rect = (ctypes.c_long * 4)()
        if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return True
        width, height = rect[2] - rect[0], rect[3] - rect[1]
        if width > 0 and height > 0:
            found.append(int(hwnd))
        return True

    _user32.EnumWindows(callback, 0)
    return found[0] if found else None


def _write_mode_file(exe: Path) -> Path:
    path = exe.parent / "appmodset.conf"
    backup = None
    if path.is_file():
        backup = path.with_name("appmodset.conf.bench-backup")
        path.replace(backup)
    path.write_text(
        "# temporary benchmark config\n"
        "first-run==false\nnormal-boot==true\nfailsafe==false\n"
        "debug==false\nchannel==stable\nrecovery==false\n",
        encoding="utf-8",
    )
    return backup or path


def _restore_mode_file(path: Path, backup: Path | None) -> None:
    path.unlink(missing_ok=True)
    if backup is not None and backup.is_file():
        backup.replace(path)


def _run_once(exe: Path, config_dir: Path) -> float:
    env = os.environ.copy()
    env["RINLAUNCHER_CONFIG_DIR"] = str(config_dir)
    started = time.perf_counter()
    proc = subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
    try:
        deadline = started + WINDOW_WAIT_SECONDS
        while time.perf_counter() < deadline:
            if proc.poll() is not None:
                raise RuntimeError(f"process exited early with {proc.returncode}")
            if _visible_window(proc.pid):
                elapsed = (time.perf_counter() - started) * 1000
                break
            time.sleep(0.005)
        else:
            raise TimeoutError("no visible window before timeout")
    finally:
        if proc.poll() is None:
            subprocess.run([str(exe), "--quit"], cwd=str(exe.parent), env=env,
                           timeout=10, check=False)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.terminate()
                proc.wait(timeout=5)
    return elapsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--exe", type=Path, default=DEFAULT_EXE)
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--json", type=Path, default=None,
                        help="write raw samples and median to this JSON file")
    args = parser.parse_args(argv)

    if sys.platform != "win32":
        print("bench_frozen is Windows-only", file=sys.stderr)
        return 2
    exe = args.exe.resolve()
    if not exe.is_file():
        print(f"missing exe: {exe}", file=sys.stderr)
        return 2

    mode_path = _write_mode_file(exe)
    backup = mode_path if mode_path.name.endswith(".bench-backup") else None
    samples: list[float] = []
    try:
        with tempfile.TemporaryDirectory(prefix="rin-bench-") as raw:
            config_dir = Path(raw)
            # 第一次算预热，不进入结果。
            _run_once(exe, config_dir)
            for _ in range(max(1, args.iterations)):
                samples.append(_run_once(exe, config_dir))
    finally:
        _restore_mode_file(exe.parent / "appmodset.conf", backup)

    samples.sort()
    median = statistics.median(samples)
    print("frozen cold start (launch -> first visible window)")
    for index, sample in enumerate(samples, 1):
        print(f"  #{index}: {sample:7.1f} ms")
    print(f"  median: {median:7.1f} ms")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps({"exe": str(exe), "samples_ms": samples,
                        "median_ms": median}, indent=2) + "\n",
            encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
