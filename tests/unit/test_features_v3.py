"""Vazamento e contrato do feature set v3 (Task 3 do plano).

O prazo da SBA vaza o desfecho: 33,64% de CHGOFF no prazo "quebrado" contra
0,91% no redondo (levantamento §1) — a regra é regravada depois do problema.
Nenhum campo de prazo ou desfecho pode entrar em FEATURE_COLUMNS ou no SQL
de treino.
"""

from __future__ import annotations

from pathlib import Path

from model.features import FEATURE_COLUMNS, FEATURE_SET_VERSION, FEATURES_TABLE

SQL_DIR = Path(__file__).parents[2] / "model" / "sql"

# TermInMonths (o vazamento) e campos do desfecho — nem como feature, nem no
# SQL de treino. GrossChargeOffAmount nem existe na ingestão (lista branca).
CAMPOS_VAZAMENTO = [
    "term_in_months",
    "charge_off_date",
    "paid_in_full_date",
    "gross_charge_off",
    "loan_status",
]

SQL_TREINO = ["08_train_logreg_v3.sql", "09_train_candidate_v3.sql"]


def test_features_sem_campo_de_vazamento():
    for col in CAMPOS_VAZAMENTO:
        assert col not in FEATURE_COLUMNS


def test_sql_de_treino_sem_campo_de_vazamento():
    for nome in SQL_TREINO:
        sql = (SQL_DIR / nome).read_text(encoding="utf-8").lower()
        for col in CAMPOS_VAZAMENTO:
            assert col not in sql, f"{nome} menciona {col}"


def test_sql_de_features_nao_carrega_prazo_nem_datas_de_desfecho():
    # 07 lê loan_status para COMPUTAR o rótulo (legítimo); prazo e datas de
    # desfecho nem aparecem.
    sql = (SQL_DIR / "07_load_features_v3.sql").read_text(encoding="utf-8").lower()
    for col in ("term_in_months", "charge_off_date", "paid_in_full_date"):
        assert col not in sql


def test_features_sao_as_tres_do_plano():
    assert FEATURE_COLUMNS == ["secao_cnae", "faixa_idade", "log_valor_usd"]


def test_versao_e_tabela_apontam_para_o_v3():
    assert FEATURE_SET_VERSION == "v3_sba"
    assert FEATURES_TABLE == "features_v3"
