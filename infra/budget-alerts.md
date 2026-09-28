# Budget Alerts — GCP

Configurar alertas de billing **antes de qualquer chamada de API**.

> **Status: ✅ configurado e verificado em 2026-09-27** — `pme-risk-budget`,
> R$ 200 BRL, thresholds 50/80/100, confirmado via
> `gcloud billing budgets list` no billing account do projeto.

## Passos (console)

1. Acessar [Billing Budgets](https://console.cloud.google.com/billing/budgets)
2. Selecionar o projeto GCP dedicado do pme-risk
3. Clicar em **Create Budget**
4. Configurar:
   - **Name:** `pme-risk-budget`
   - **Projects:** selecionar projeto pme-risk
   - **Budget type:** Specified amount
   - **Amount:** R$ 200 (envelope do PLANO §7)
   - **Time range:** Reset every month
5. Configure **Alert threshold rules**:
   - 50% — email para o administrador
   - 80% — email para o administrador
   - 100% — email para o administrador
6. **Save**

## Alternativa via gcloud

```bash
gcloud billing budgets create \
  --billing-account=BILLING_ACCOUNT_ID \
  --display-name="pme-risk-budget" \
  --budget-amount=200 \
  --threshold-rule=percent=50 \
  --threshold-rule=percent=80 \
  --threshold-rule=percent=100 \
  --all-updates-rule-pubsub-topic=projects/PROJECT_ID/topics/billing-alerts
```

Notas:
- O envelope de R$ 200 é custo alvo, não meta (PLANO §7).
- Créditos trial: ~R$ 1.753,25, validade ~2026-12-25.
- Pós-trial: tudo deve caber no free tier (regra de sobrevivência §7).
