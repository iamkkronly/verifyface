"""The command line must work end-to-end for non-programmers.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(__file__).resolve().parent / "fixtures"


def run_cli(*args: str, vault: Path | None = None) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    command = [sys.executable, "-m", "verifyface", *args]
    if vault is not None:
        command += ["--vault", str(vault)]
    # decode explicitly as UTF-8: the CLI always writes UTF-8, while a Windows
    # parent process would otherwise default to its ANSI code page
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=300,
    )


@pytest.fixture()
def vault(tmp_path) -> Path:
    return tmp_path / "vault"


def test_version_and_credit():
    result = run_cli("--version")
    assert result.returncode == 0
    assert "Kaustav Kanti Ray" in result.stdout


def test_help_lists_commands():
    result = run_cli("--help")
    assert result.returncode == 0
    for command in ("enroll", "verify", "identify", "compare", "doctor", "serve"):
        assert command in result.stdout


def test_enroll_verify_list_delete_flow(vault: Path):
    enroll = run_cli("enroll", "Kaustav", str(FIXTURES / "person_a_1.jpg"), vault=vault)
    assert enroll.returncode == 0, enroll.stderr
    assert "Kaustav" in enroll.stdout.strip()

    verify = run_cli("verify", "Kaustav", str(FIXTURES / "person_a_2.jpg"), vault=vault)
    assert verify.returncode == 0, verify.stdout + verify.stderr
    assert "VERIFIED" in verify.stdout

    impostor = run_cli("verify", "Kaustav", str(FIXTURES / "impostor_2.jpg"), vault=vault)
    assert impostor.returncode == 1
    assert "NOT verified" in impostor.stdout

    listing = run_cli("list", vault=vault)
    assert listing.returncode == 0
    assert "Kaustav" in listing.stdout

    deleted = run_cli("delete", "Kaustav", "--yes", vault=vault)
    assert deleted.returncode == 0
    assert "Kaustav" not in run_cli("list", vault=vault).stdout


def test_json_output_is_machine_readable(vault: Path):
    run_cli("enroll", "Kaustav", str(FIXTURES / "person_a_1.jpg"), vault=vault)
    result = run_cli("verify", "Kaustav", str(FIXTURES / "person_a_2.jpg"), "--json", vault=vault)
    payload = json.loads(result.stdout)
    assert payload["matched"] is True
    assert payload["developer"] == "Kaustav Kanti Ray"
    assert 0.0 <= payload["score"] <= 1.0


def test_unicode_name_in_cli(vault: Path):
    name = "কৌস্তভ"
    assert run_cli("enroll", name, str(FIXTURES / "person_b_1.jpg"), vault=vault).returncode == 0
    result = run_cli("identify", str(FIXTURES / "person_b_2.jpg"), "--json", vault=vault)
    assert json.loads(result.stdout)["identity"] == name


def test_compare_and_identify_exit_codes(vault: Path):
    same = run_cli(
        "compare", str(FIXTURES / "person_b_1.jpg"), str(FIXTURES / "person_b_2.jpg"), vault=vault
    )
    assert same.returncode == 0
    different = run_cli(
        "compare", str(FIXTURES / "person_b_1.jpg"), str(FIXTURES / "impostor_1.jpg"), vault=vault
    )
    assert different.returncode == 1


def test_doctor_reports_health(vault: Path):
    result = run_cli("doctor", vault=vault)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Kaustav Kanti Ray" in result.stdout
    assert "model" in result.stdout.lower()


def test_missing_file_produces_clean_error(vault: Path):
    result = run_cli("verify", "ghost", "nope.jpg", vault=vault)
    assert result.returncode == 2
    assert "Traceback" not in result.stderr
