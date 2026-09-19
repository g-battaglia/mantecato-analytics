"""Static guards for server/client package separation."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_server_distribution_has_no_cli_entry_point() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "cli.mantecato_cli" not in pyproject
    assert '"cli*"' not in pyproject
    assert '"typer>=' not in pyproject


def test_independent_clients_do_not_import_server_packages() -> None:
    forbidden = {"django", "apps", "core", "mantecato", "cli"}
    for package in ("mantecato-cli", "mantecato-mcp"):
        for source in (ROOT / "packages" / package / "src").rglob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported = {alias.name.split(".", 1)[0] for alias in node.names}
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported = {node.module.split(".", 1)[0]}
                else:
                    continue
                assert not imported & forbidden, f"{source} imports server package {imported}"


def test_server_dockerfile_does_not_copy_old_cli() -> None:
    dockerfile = (ROOT / "Dockerfile.standalone").read_text(encoding="utf-8")
    assert "COPY cli ./cli" not in dockerfile


def test_tracker_bundle_matches_recorded_baseline() -> None:
    import hashlib

    bundle = ROOT / "packages" / "tracker" / "dist" / "script.js"
    assert hashlib.sha256(bundle.read_bytes()).hexdigest() == (
        "c567e25198a0db6466b27a493183673a36f10030d62c40b762869b421f93f74a"
    )
