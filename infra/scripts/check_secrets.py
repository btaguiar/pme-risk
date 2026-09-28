#!/usr/bin/env python3
"""Pre-commit check: previne vazamento de IDs de projeto, credenciais e chaves.

Regra: BRIEF.md — "Nada de dado privado"
Cross-platform (funciona em Windows, Linux, macOS).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Prefixos genéricos de credenciais (Kaggle, Google API key, OAuth token)
GENERIC_PATTERNS = ["KGAT_", "AIza", "ya29."]

# IDs de projeto NÃO ficam neste arquivo (ele é versionado — listá-los aqui
# seria o próprio vazamento). Vêm de fontes locais, fora do git:
#   - GCP_PROJECT_ID do ambiente ou do .env
#   - infra/scripts/secret_patterns.local (um padrão por linha, gitignored)
LOCAL_PATTERNS_FILE = Path(__file__).parent / "secret_patterns.local"

SKIP_FILES = {"check_secrets.py"}
SKIP_DIRS = {".git", ".venv", ".worktrees", "node_modules"}


def _load_patterns(root: Path) -> list[str]:
    patterns = list(GENERIC_PATTERNS)
    project_id = os.environ.get("GCP_PROJECT_ID", "")
    env_file = root / ".env"
    if not project_id and env_file.is_file():
        for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("GCP_PROJECT_ID="):
                project_id = line.split("=", 1)[1].strip().strip("\"'")
    if project_id:
        patterns.append(project_id)
    if LOCAL_PATTERNS_FILE.is_file():
        for line in LOCAL_PATTERNS_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                patterns.append(line)
    return list(dict.fromkeys(patterns))


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
    patterns = _load_patterns(root)
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

        for pattern in patterns:
            if pattern in text:
                # Não ecoa padrões locais — o log do hook também é "material"
                shown = pattern if pattern in GENERIC_PATTERNS else "<id-de-projeto>"
                print(f"ERRO: padrao '{shown}' encontrado em: {rel}")
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
