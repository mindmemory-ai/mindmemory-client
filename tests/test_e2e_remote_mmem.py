"""远端 opt-in：需 MMEM_BASE_URL（及可选凭证）时手动运行；仅只读烟测。"""

import os

import pytest
from typer.testing import CliRunner

from mmem_cli.main import app

runner = CliRunner()


@pytest.mark.e2e_remote
def test_mmem_doctor_with_base_url_optional():
    base = (os.environ.get("MMEM_BASE_URL") or "").strip()
    if not base:
        pytest.skip("MMEM_BASE_URL 未设置，跳过远端烟测")
    r = runner.invoke(app, ["doctor", "--base-url", base])
    assert r.exit_code == 0
    assert "MMEM_BASE_URL" in r.stdout or base in r.stdout
