"""La ejecución real está deshabilitada: ningún módulo puede enviar órdenes ni manejar credenciales."""

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src"
FORBIDDEN = re.compile(r"\b(order_send|order_check|login\s*=|password\s*=)")


def test_no_order_or_credential_calls_in_source():
    offenders = []
    for path in SRC.rglob("*.py"):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if FORBIDDEN.search(line):
                offenders.append(f"{path.relative_to(SRC)}:{n}: {line.strip()}")
    assert offenders == []


def test_env_example_has_no_secrets():
    text = (SRC.parent / ".env.example").read_text(encoding="utf-8")
    assert not re.search(r"(?im)^\s*\w*(PASSWORD|LOGIN|ACCOUNT)\w*\s*=", text)


def test_dotenv_is_ignored():
    assert ".env" in (SRC.parent / ".gitignore").read_text(encoding="utf-8").splitlines()
