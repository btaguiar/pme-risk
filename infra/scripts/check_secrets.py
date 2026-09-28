#!/usr/bin/env python3
"""Pre-commit check: previne vazamento de IDs de projeto, credenciais e chaves.

Regra: BRIEF.md — "Nada de dado privado"
Cross-platform (funciona em Windows, Linux, macOS).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PATTERNS = [
    "<seu-projeto-gcp>",
    "<projeto-quimera>",
    "<projeto-grifo>",
    "KGAT_",
    "AIza",
    "ya29.",
]

SKIP_FILES = {"check_secrets.py", "check_secrets.sh", "pre-commit"}
SKIP_DIRS = {".git", ".venv", "eval", ".worktrees", "node_modules"}


def _get_tracked_files() -> list[Path]:
    """Lista arquivos que o git vai commitar (staged + untracked)."""
    root = Path(__file__).parent.parent.parent
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    files = [root / f for f in result.stdout.strip().splitlines() if f]

    result2 = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    files += [root / f for f in result2.stdout.strip().splitlines() if f]

    return list({f.resolve(): f for f in files}.values())


def main() -> int:
    print("Verificando vazamento de credenciais...")
    root = Path(__file__).parent.parent.parent

    files = _get_tracked_files()
    fail = False

    for filepath in files:
        # Pular arquivos e diretórios
        rel = filepath.relative_to(root)
        if rel.name in SKIP_FILES:
            continue
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if not filepath.is_file():
            continue

        try:
            raw = filepath.read_bytes()
        except OSError:
            continue

        # Tentar múltiplos encodings (PowerShell escreve UTF-16)
        text = None
        for encoding in ("utf-8", "utf-16", "utf-16-le", "latin-1"):
            try:
                text = raw.decode(encoding)
                break
            except (UnicodeDecodeError, UnicodeError):
                continue
        if text is None:
            continue

        for pattern in PATTERNS:
            if pattern in text:
                print(f"ERRO: padrao '{pattern}' encontrado em: {rel}")
                fail = True

    if fail:
        print()
        print("BRIEF.md proibe expor IDs de projeto ou credenciais.")
        print("Use placeholders como <seu-projeto-gcp> em documentacao.")
        return 1

    print("OK: nenhum vazamento detectado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
