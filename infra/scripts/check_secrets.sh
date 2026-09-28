#!/usr/bin/env bash
# Pre-commit check: previne vazamento de IDs de projeto, credenciais e chaves
# Regra: BRIEF.md — "Nada de dado privado"
set -euo pipefail

echo "Verificando vazamento de credenciais..."

PATTERNS=(
  "<seu-projeto-gcp>"
  "<projeto-quimera>"
  "<projeto-grifo>"
  "KGAT_"
  "AIza"
  "ya29\."
)

FAIL=0
FILES=$(git diff --cached --name-only 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null)
FILES=$(echo "$FILES" | sort -u | grep -v "check_secrets.sh" | grep -v "^$" || true)

for pattern in "${PATTERNS[@]}"; do
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    [ ! -f "$f" ] && continue
    if grep -q "$pattern" "$f" 2>/dev/null; then
      echo "ERRO: padrao '$pattern' encontrado em: $f"
      FAIL=1
    fi
  done <<< "$FILES"
done

if [ "$FAIL" -eq 1 ]; then
  echo ""
  echo "BRIEF.md proibe expor IDs de projeto ou credenciais."
  echo "Use placeholders como <seu-projeto-gcp> em documentacao."
  exit 1
fi

echo "OK: nenhum vazamento detectado."
