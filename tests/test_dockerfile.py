"""Security tests for Dockerfile.render non-root execution."""

from __future__ import annotations

from pathlib import Path


def test_dockerfile_render_uses_non_root_user() -> None:
    """Dockerfile.render must configure and switch to a non-root USER."""
    content = Path(__file__).resolve().parents[1].joinpath("Dockerfile.render").read_text()
    user_lines = [
        line.strip()
        for line in content.splitlines()
        if line.strip().startswith("USER ")
    ]
    assert user_lines, "Dockerfile.render must define a USER directive"
    assert user_lines[-1] != "USER root"
    assert "PLAYWRIGHT_BROWSERS_PATH=" in content
