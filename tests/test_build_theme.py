from __future__ import annotations

import argparse
import subprocess

from jobhunt import cli


def test_cmd_build_passes_enabled_brand_theme_to_typst(tmp_path, monkeypatch):
    app_dir = tmp_path / "Applications" / "Example-Role"
    app_dir.mkdir(parents=True)
    (app_dir / "cv-data.yaml").write_text("title: Example\n", encoding="utf-8")
    (app_dir / "letter-data.yaml").write_text("subtitle: Example\n", encoding="utf-8")
    (app_dir / "brand-theme.yaml").write_text(
        """
enabled: true
accent: '#0057FF'
accent_dark: '#1A1A1A'
soft_bg: '#F0F5FF'
rule: '#C8D6F0'
link: '#0057FF'
confidence: 0.8
notes: []
fallback: false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("jobhunt.config.ROOT", tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "typst")

    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(cli.subprocess, "run", fake_run)

    result = cli.cmd_build(argparse.Namespace(app="Example-Role"))

    assert result == 0
    assert len(calls) == 2
    assert all("--input" in call for call in calls)
    assert all("theme=/Applications/Example-Role/brand-theme.yaml" in call for call in calls)


def test_cmd_build_ignores_disabled_brand_theme(tmp_path, monkeypatch):
    app_dir = tmp_path / "Applications" / "Example-Role"
    app_dir.mkdir(parents=True)
    (app_dir / "cv-data.yaml").write_text("title: Example\n", encoding="utf-8")
    (app_dir / "letter-data.yaml").write_text("subtitle: Example\n", encoding="utf-8")
    (app_dir / "brand-theme.yaml").write_text("enabled: false\nconfidence: 0\n", encoding="utf-8")
    monkeypatch.setattr("jobhunt.config.ROOT", tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "typst")

    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))

    result = cli.cmd_build(argparse.Namespace(app="Example-Role"))

    assert result == 0
    assert all(not any(str(arg).startswith("theme=") for arg in call) for call in calls)


def test_cmd_build_passes_cached_font_path_to_typst(tmp_path, monkeypatch):
    app_dir = tmp_path / "Applications" / "Example-Role"
    font_dir = tmp_path / "fonts" / "chameleon" / "inter"
    app_dir.mkdir(parents=True)
    font_dir.mkdir(parents=True)
    (font_dir / "Inter-Regular.ttf").write_text("fake-font", encoding="utf-8")
    (app_dir / "cv-data.yaml").write_text("title: Example\n", encoding="utf-8")
    (app_dir / "letter-data.yaml").write_text("subtitle: Example\n", encoding="utf-8")
    (app_dir / "brand-theme.yaml").write_text(
        """
enabled: true
accent: '#0057FF'
accent_dark: '#1A1A1A'
soft_bg: '#F0F5FF'
rule: '#C8D6F0'
link: '#0057FF'
confidence: 0.8
typography_enabled: true
typography_available: true
body_font:
- Inter
- Segoe UI
typography_resolution:
  family: Inter
  font_path: fonts/chameleon/inter
notes: []
fallback: false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("jobhunt.config.ROOT", tmp_path)
    monkeypatch.setattr("jobhunt.font_theme.ROOT", tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "typst")

    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))

    result = cli.cmd_build(argparse.Namespace(app="Example-Role"))

    assert result == 0
    assert all("--font-path" in call for call in calls)
    assert all(str(font_dir) in call for call in calls)


def test_cmd_build_passes_two_font_paths_for_distinct_body_and_heading_fonts(tmp_path, monkeypatch):
    app_dir = tmp_path / "Applications" / "Example-Role"
    body_dir = tmp_path / "fonts" / "chameleon" / "georgia"
    heading_dir = tmp_path / "fonts" / "chameleon" / "verdana"
    app_dir.mkdir(parents=True)
    body_dir.mkdir(parents=True)
    heading_dir.mkdir(parents=True)
    (body_dir / "Georgia-Regular.ttf").write_text("fake-font", encoding="utf-8")
    (heading_dir / "Verdana-Regular.ttf").write_text("fake-font", encoding="utf-8")
    (app_dir / "cv-data.yaml").write_text("title: Example\n", encoding="utf-8")
    (app_dir / "letter-data.yaml").write_text("subtitle: Example\n", encoding="utf-8")
    (app_dir / "brand-theme.yaml").write_text(
        """
enabled: true
accent: '#0057FF'
accent_dark: '#1A1A1A'
soft_bg: '#F0F5FF'
rule: '#C8D6F0'
link: '#0057FF'
confidence: 0.8
typography_enabled: true
typography_available: true
body_font:
- Georgia
heading_font:
- Verdana
typography_resolution:
  body:
    family: Georgia
    font_path: fonts/chameleon/georgia
  heading:
    family: Verdana
    font_path: fonts/chameleon/verdana
notes: []
fallback: false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("jobhunt.config.ROOT", tmp_path)
    monkeypatch.setattr("jobhunt.font_theme.ROOT", tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "typst")

    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))

    result = cli.cmd_build(argparse.Namespace(app="Example-Role"))

    assert result == 0
    for call in calls:
        font_path_count = sum(1 for arg in call if arg == "--font-path")
        assert font_path_count == 2
        assert str(body_dir) in call
        assert str(heading_dir) in call


def test_cmd_build_dedupes_font_path_when_body_and_heading_share_family(tmp_path, monkeypatch):
    app_dir = tmp_path / "Applications" / "Example-Role"
    font_dir = tmp_path / "fonts" / "chameleon" / "inter"
    app_dir.mkdir(parents=True)
    font_dir.mkdir(parents=True)
    (font_dir / "Inter-Regular.ttf").write_text("fake-font", encoding="utf-8")
    (app_dir / "cv-data.yaml").write_text("title: Example\n", encoding="utf-8")
    (app_dir / "letter-data.yaml").write_text("subtitle: Example\n", encoding="utf-8")
    (app_dir / "brand-theme.yaml").write_text(
        """
enabled: true
accent: '#0057FF'
accent_dark: '#1A1A1A'
soft_bg: '#F0F5FF'
rule: '#C8D6F0'
link: '#0057FF'
confidence: 0.8
typography_enabled: true
typography_available: true
body_font:
- Inter
heading_font:
- Inter
typography_resolution:
  body:
    family: Inter
    font_path: fonts/chameleon/inter
  heading:
    family: Inter
    font_path: fonts/chameleon/inter
notes: []
fallback: false
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setattr("jobhunt.config.ROOT", tmp_path)
    monkeypatch.setattr("jobhunt.font_theme.ROOT", tmp_path)
    monkeypatch.setattr(cli.shutil, "which", lambda name: "typst")

    calls = []
    monkeypatch.setattr(cli.subprocess, "run", lambda cmd: calls.append(cmd) or subprocess.CompletedProcess(cmd, 0))

    result = cli.cmd_build(argparse.Namespace(app="Example-Role"))

    assert result == 0
    for call in calls:
        font_path_count = sum(1 for arg in call if arg == "--font-path")
        assert font_path_count == 1
        assert str(font_dir) in call
