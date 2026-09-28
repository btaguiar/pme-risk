#!/usr/bin/env bash
# Pre-commit check: previne vazamento de IDs de projeto, credenciais e chaves
# Regra: BRIEF.md — "Nada de dado privado"
set -euo pipefail

echo "Verificando vazamento de credenciais..."

# Padrões proibidos em qualquer arquivo (exceto .git/)
PATTERNS=(
  "<seu-projeto-gcp>"
  "<projeto-quimera>"
  "<projeto-grifo>"
  "KGAT_"
  "AIza"
  "ya29\."
)

FAIL=0
for pattern in "${PATTERNS[@]}"; do
  MATCHES=$(grep -r --include="*.py" --include="*.md" --include="*.json" --include="*.toml" --include="*.sh" --include="*.yaml" --include="*.yml" \
    --exclude-dir=".git" --exclude-dir=".venv" --exclude-dir="eval" --exclude-dir=".worktrees" \
    --exclude="check_secrets.sh" \
    -l "$pattern" . 2>/dev/null || true)
  if [ -n "$MATCHES" ]; then
    echo "ERRO: padrão '$pattern' encontrado em:"
    echo "$MATCHES"
    FAIL=1
  fi
done

if [ "$FAIL" -eq 1 ]; then
  echo ""
  echo "BRIEF.md proíbe expor IDs de projeto ou credenciais."
  echo "Use placeholders como <seu-projeto-gcp> em documentação."
  exit 1
fi

echo "OK: nenhum vazamento detectado."
