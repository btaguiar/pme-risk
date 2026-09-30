"""Ingestão SBA 7(a) — limpeza sem rede nem BigQuery."""

from __future__ import annotations

import io

import pandas as pd

from model.dados.ingest_sba import COLUNAS, ler_csv, limpar

# Cabeçalho real do FOIA 7(a) (as-of 260630), com PII
_CSV = """AsOfDate,Program,LocationID,BorrName,BorrStreet,BorrCity,BorrState,BorrZip,BankName,BankFDICNumber,BankNCUANumber,BankStreet,BankCity,BankState,BankZip,GrossApproval,SBAGuaranteedApproval,ApprovalDate,ApprovalFY,FirstDisbursementDate,ProcessingMethod,InitialInterestRate,FixedorVariableInterestInd,TermInMonths,NaicsCode,NaicsDescription,FranchiseCode,FranchiseName,ProjectCounty,ProjectState,SBADistrictOffice,CongressionalDistrict,BusinessType,BusinessAge,LoanStatus,PaidInFullDate,ChargeOffDate,GrossChargeOffAmount,RevolverStatus,JobsSupported,CollateralInd,SoldSecMrktInd
20260630,7A,1,JOHN DOE PLUMBING,1 MAIN ST,SPRINGFIELD,IL,62701,BANK A,1,,2 BANK ST,CHICAGO,IL,60601,150000,112500,2012-03-01,2012,2012-04-01,PLP,6.0,V,120,238220,Plumbing,,,SANGAMON,IL,ILLINOIS,IL-13,INDIVIDUAL,"Existing, 5 or more years",P I F,2020-01-01,,0,N,4,Y,N
20260630,7A,2,ACME LLC,9 ELM ST,AUSTIN,TX,73301,BANK B,2,,3 BANK ST,DALLAS,TX,75201,50000,25000,2014-06-01,2014,2014-07-01,SBX,7.5,V,37,722511,Restaurants,,,TRAVIS,TX,TEXAS,TX-10,CORPORATION,"Startup, Loan Funds will Open Business",CHGOFF,,2016-01-01,40000,N,6,N,N
"""

_PII = {"BorrName", "BorrStreet", "BorrCity", "BorrZip", "BankName", "BankStreet"}


def _df() -> pd.DataFrame:
    return limpar(ler_csv(io.StringIO(_CSV)))


def test_so_colunas_da_lista_branca_sem_pii():
    df = _df()
    assert list(df.columns) == [c.nome_bq for c in COLUNAS]
    texto = df.to_csv(index=False)
    assert "JOHN DOE" not in texto and "MAIN ST" not in texto and "ACME" not in texto
    assert not _PII & set(df.columns)


def test_status_normalizado():
    assert _df()["loan_status"].tolist() == ["PIF", "CHGOFF"]


def test_tipos_e_datas():
    df = _df()
    assert df["approval_fy"].tolist() == [2012, 2014]
    assert df["gross_approval"].tolist() == [150000.0, 50000.0]
    assert df["naics_code"].tolist() == ["238220", "722511"]
    assert df["charge_off_date"].tolist()[1] == "2016-01-01"


def test_prazo_fica_na_bruta_para_a_analise_de_vazamento():
    # Fica na tabela bruta (o achado do levantamento é reproduzível);
    # o teste de features da Task 3 garante que não entra no treino.
    assert "term_in_months" in _df().columns
