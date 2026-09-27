# BRIEF — Regras herdadas do pme-risk

Regras de conduta do projeto, citadas no PLANO como fonte das restrições
de qualidade e privacidade.

## 1. Nenhum número sem fonte

Toda métrica, performance ou resultado citado em README, post ou laudo
precisa ser reproduzível a partir de `eval/*/results/`. Não existe afirmação
de performance sem um JSON versionado que a sustente.

- Não citar KS, AUC, Brier, F1 ou qualquer métrica que não esteja num
  arquivo em `eval/model/results/`, `eval/laudo/results/` ou
  `eval/extraction/results/`.
- Se não está no eval, não entra no README nem no post.

## 2. Nada de dado privado

Nenhum dado real de pessoas ou empresas sensíveis entra no repositório ou
em material público.

- O golden set é sintético.
- CNPJ de exemplo deve ser fictício ou de empresas públicas sem vínculo
  com decisões reais de crédito.
- Não expor IDs de projeto GCP, contas de serviço, chaves ou nomes de
  variáveis de ambiente em qualquer material público.
- `.env.example` contém nomes de variáveis, nunca valores.
