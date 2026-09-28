#!/usr/bin/env bash
# Pre-commit check: previne vazamento de IDs de projeto, credenciais e chaves
# Regra: BRIEF.md — "Nada de dado privado". Lógica única em check_secrets.py.
set -euo pipefail
exec python "$(git rev-parse --show-toplevel)/infra/scripts/check_secrets.py"
