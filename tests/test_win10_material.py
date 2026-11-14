"""Win10 材质分支与 rin_ui.json 恢复（不依赖真实 DWM）。"""

from __future__ import annotations

import json
from pathlib import Path

from rin_launcher import main


def test_window_backdrop_by_role(monkeypatch):
    launcher = object.__new__(main.Launcher)
    launcher.compact = object()
    other = object()

    monkeypatch.setattr(main, "is_win11", lambda: False)
    # 启动台始终 Acrylic；Win10 的其它窗口不铺材质（QML 用不透明背景）。
    assert main.Launcher._window_backdrop(launcher, launcher.compact) == "acrylic"
    assert main.Launcher._window_backdrop(launcher, other) == "none"

    monkeypatch.setattr(main, "is_win11", lambda: True)
    assert main.Launcher._window_backdrop(launcher, other) == "mica"


def test_corrupt_rinui_json_restored_from_backup(tmp_path: Path, monkeypatch):
    config = tmp_path / "rin_ui.json"
    config.write_text("{ definitely broken", encoding="utf-8")
    (tmp_path / "rin_ui.json.bak").write_text(
        json.dumps({"theme": {"current_theme": "Dark"}, "backdrop_effect": "mica"}),
        encoding="utf-8")
    monkeypatch.setattr(
        main.Launcher, "_rinui_config_path", classmethod(lambda cls: config))
    monkeypatch.setattr(main, "init_config", lambda: None)

    main.Launcher._prepare_rinui_config()

    data = json.loads(config.read_text(encoding="utf-8"))
    assert data["theme"]["current_theme"] == "Dark"
    assert list(tmp_path.glob("rin_ui.json.corrupt-*")), "坏文件应被保留"


def test_corrupt_rinui_json_without_backup_is_removed(tmp_path: Path, monkeypatch):
    config = tmp_path / "rin_ui.json"
    config.write_text("{ broken", encoding="utf-8")
    monkeypatch.setattr(
        main.Launcher, "_rinui_config_path", classmethod(lambda cls: config))
    monkeypatch.setattr(main, "init_config", lambda: None)

    main.Launcher._prepare_rinui_config()

    assert not config.exists()
    assert list(tmp_path.glob("rin_ui.json.corrupt-*"))
