"""mmem CLI：Typer CliRunner 烟测（不依赖 pnms）。"""

from typer.testing import CliRunner

from mmem_cli.main import app

runner = CliRunner()


def test_mmem_help():
    r = runner.invoke(app, ["--help"])
    assert r.exit_code == 0
    assert "MindMemory" in r.stdout


def test_mmem_chat_help_lists_verbose_and_openai():
    r = runner.invoke(app, ["chat", "--help"])
    assert r.exit_code == 0
    assert "--verbose" in r.stdout or "-v" in r.stdout
    assert "openai" in r.stdout.lower()
    assert "chat-extras" in r.stdout or "extras" in r.stdout.lower()


def test_mmem_sync_help():
    r = runner.invoke(app, ["sync", "--help"])
    assert r.exit_code == 0
    assert "push" in r.stdout or "encrypt" in r.stdout
