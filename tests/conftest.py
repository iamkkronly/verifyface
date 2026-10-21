"""Shared pytest fixtures.

Developer: Kaustav Kanti Ray
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:  # allow running pytest without installing
    sys.path.insert(0, str(SRC))

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture_path(name: str) -> Path:
    path = FIXTURES / name
    if not path.is_file():
        pytest.skip(f"missing test fixture {name}")
    return path


@pytest.fixture(scope="session")
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def verifier(tmp_path_factory):
    """A verifier with its own throw-away vault, shared to avoid reloading models."""
    import verifyface as vf

    vault = tmp_path_factory.mktemp("vault")
    return vf.Verifier(vault=vault)


@pytest.fixture()
def fresh_verifier(tmp_path):
    """A verifier with a clean vault for each test."""
    import verifyface as vf

    return vf.Verifier(vault=tmp_path / "vault")
