"""生产部署文件存在性与脚本可解析性(不依赖 Docker 守护进程)。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_prod_compose_and_dockerfiles_exist():
    deploy = ROOT / "deploy"
    assert (deploy / "docker-compose.prod.yml").is_file()
    assert (deploy / "docker-compose.dev.yml").is_file()
    assert (deploy / "docker-compose.windows.yml").is_file()
    assert (deploy / "docker-compose.windows-miniqmt.yml").is_file()
    assert (deploy / "Caddyfile.windows-miniqmt").is_file()
    assert (deploy / "Dockerfile.api").is_file()
    assert (deploy / "Dockerfile.web").is_file()
    assert (deploy / "Dockerfile.backup").is_file()
    assert (deploy / "Caddyfile").is_file()
    assert (deploy / "api-entrypoint.sh").is_file()
    assert (deploy / "windows" / "up.ps1").is_file()
    assert (deploy / "windows" / "run-host-api.ps1").is_file()
    assert (ROOT / ".env.prod.example").is_file()
    assert (ROOT / "docs" / "deploy.md").is_file()
    assert (ROOT / "docs" / "deploy-windows.md").is_file()


def test_backup_scripts_are_shell():
    for name in ("backup_db.sh", "restore_db.sh", "backup_loop.sh"):
        path = ROOT / "deploy" / "backup" / name
        text = path.read_text(encoding="utf-8")
        assert text.startswith("#!")
        assert "pg_dump" in text or "backup_db" in text or "psql" in text


def test_compose_prod_mentions_caddy_and_services():
    text = (ROOT / "deploy" / "docker-compose.prod.yml").read_text(encoding="utf-8")
    for key in ("caddy:", "api:", "web:", "db:", "backup:", "basic_auth", "LIVE_BROKER"):
        if key == "basic_auth":
            caddy = (ROOT / "deploy" / "Caddyfile").read_text(encoding="utf-8")
            assert "basic_auth" in caddy
        else:
            assert key in text


def test_windows_compose_mentions_host_gateway_and_miniqmt():
    win = (ROOT / "deploy" / "docker-compose.windows.yml").read_text(encoding="utf-8")
    assert "host.docker.internal" in win
    assert "LIVE_BROKER" in win
    mq = (ROOT / "deploy" / "docker-compose.windows-miniqmt.yml").read_text(encoding="utf-8")
    assert "container-api" in mq
    assert "Caddyfile.windows-miniqmt" in mq
    caddy = (ROOT / "deploy" / "Caddyfile.windows-miniqmt").read_text(encoding="utf-8")
    assert "host.docker.internal" in caddy


def test_web_standalone_output_enabled():
    cfg = (ROOT / "apps" / "web" / "next.config.js").read_text(encoding="utf-8")
    assert 'output: "standalone"' in cfg or "output: 'standalone'" in cfg
