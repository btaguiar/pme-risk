-- 10_scr_fatores.sql
-- Riscos relativos do SCR (RR) para a calibração da PD (Task 5 do plano v3).
--
--   RR_porte = inad_SCR(porte) / inad_SCR(Micro+Pequeno)
--   RR_uf    = inad_SCR(Micro+Pequeno, uf) / inad_SCR(Micro+Pequeno)
--
-- scr_pj_raw cobre 12 data-bases (média para suavizar sazonalidade): a razão
-- de somas equivale à média ponderada das taxas mensais.
-- O nível absoluto NÃO é calibrado: inadimplência do SCR é estoque vencido
-- > 90 dias; a perda da SBA é acumulada na vida do empréstimo (D7).
--
-- Piso de carteira: UF Micro+Pequeno com carteira média mensal abaixo de
-- R$ 1 bi tem taxa instável (ruído, não sinal) → RR = 1 (sem ajuste,
-- registrado aqui).

CREATE OR REPLACE TABLE `${BQ_DATASET}.scr_fatores` AS
WITH pme AS (
  SELECT *
  FROM `${BQ_DATASET}.scr_pj_raw`
  WHERE porte IN ('Micro', 'Pequeno')
    AND carteira_ativa > 0
),
base AS (
  SELECT SUM(carteira_inadimplencia) / SUM(carteira_ativa) AS tx
  FROM pme
),
porte AS (
  SELECT porte,
         SUM(carteira_inadimplencia) / SUM(carteira_ativa) AS tx
  FROM pme
  GROUP BY porte
),
uf AS (
  SELECT uf,
         SUM(carteira_inadimplencia) / SUM(carteira_ativa) AS tx,
         -- 12 data-bases na tabela: a soma é ~12x a carteira média mensal
         SUM(carteira_ativa) / 12 AS carteira_media_mensal
  FROM pme
  GROUP BY uf
)
SELECT
  'porte' AS tipo,
  porte AS chave,
  p.tx / b.tx AS rr
FROM porte p CROSS JOIN base b
UNION ALL
SELECT
  'uf' AS tipo,
  uf AS chave,
  IF(u.carteira_media_mensal < 1000000000, 1.0, u.tx / b.tx) AS rr
FROM uf u CROSS JOIN base b;
