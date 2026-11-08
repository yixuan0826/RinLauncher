"""对 ``qml/`` 下所有 QML 文件跑 ``pyside6-qmllint``。

为什么不用 PowerShell 循环：GitHub Actions 的 ``pwsh`` 默认把
``$ErrorActionPreference`` 设成 ``Stop``，而 qmllint 会把 ``unqualified access``
之类的 **warning 写到 stderr**；同样的命令行在本地和 runner 上行为并不一致。
把这个步骤放进 Python，本地与 CI 走的是完全相同的代码路径。

导入路径：
* ``-I <repo>`` 让 ``import "components"`` / ``"dialogs"`` 这类相对导入成立；
* ``QML_IMPORT_PATH`` 补上 pip 安装的 RinUI，仓库里已经没有内联副本。

退出码：0 = 全部通过；1 = 有文件报错；2 = 找不到 qmllint。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def find_qmllint() -> str | None:
    """优先用当前解释器附近的脚本，退回 PATH。

    venv 里 ``pyside6-qmllint`` 与解释器同目录；CI 的全局 Python 则把它放在
    ``Scripts\\`` 子目录，所以两处都要看。
    """
    suffix = ".exe" if sys.platform == "win32" else ""
    name = f"pyside6-qmllint{suffix}"
    exe_dir = Path(sys.executable).parent
    for candidate in (exe_dir / name, exe_dir / "Scripts" / name):
        if candidate.is_file():
            return str(candidate)
    return shutil.which("pyside6-qmllint")


def main() -> int:
    qmllint = find_qmllint()
    if qmllint is None:
        print("pyside6-qmllint not found; install PySide6 first", file=sys.stderr)
        return 2

    import RinUI

    rinui_root = Path(RinUI.__file__).resolve().parent.parent
    env = dict(os.environ)
    env["QML_IMPORT_PATH"] = f"{ROOT}{os.pathsep}{rinui_root}"

    files = sorted((ROOT / "qml").rglob("*.qml"))
    if not files:
        print("no QML files found", file=sys.stderr)
        return 2

    failed: list[Path] = []
    for path in files:
        result = subprocess.run(
            [qmllint, "-I", str(ROOT), str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=env, cwd=ROOT, check=False)
        if result.returncode != 0:
            failed.append(path)
            print(f"--- {path.relative_to(ROOT).as_posix()}", file=sys.stderr)
            for stream in (result.stdout, result.stderr):
                if stream.strip():
                    print(stream.rstrip(), file=sys.stderr)

    print(f"qmllint: {len(files)} files, {len(failed)} failed")
    if failed:
        for path in failed:
            print(f"  FAILED  {path.relative_to(ROOT).as_posix()}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
