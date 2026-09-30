"""Ingestão SCR.data v2 (BCB) → BigQuery (`scr_pj_raw`).

Os últimos 12 meses de data-base disponíveis, só PJ, só as colunas da lista
branca. O SCR é AGREGADO por UF × seção CNAE × porte × modalidade ×
indexador — não há dado por operação nem nome de cliente: sem PII.

A inadimplência do SCR é estoque vencido acima de 90 dias sobre a carteira
ativa; a perda da SBA é acumulada ao longo da vida do empréstimo. Métricas
diferentes — por isso o SCR calibra o risco RELATIVO (porte, UF), nunca o
nível absoluto da PD (levantamento §2, decisão D7 do plano v3).

Fonte: https://www.bcb.gov.br/pda/desig/scrdata_{ANO}.zip (metodologia v2).
Detalhe de qualidade: o CSV mistura latin-1 e UTF-8 por campo — cada valor é
decodificado tentando UTF-8 primeiro (docs/dados/levantamento, nota da
ingestão v3).

Uso:
    GCP_PROJECT_ID=<projeto> uv run python -m model.dados.ingest_scr
"""

from __future__ import annotations

import csv
import io
import os
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from agents.setores import SETORES_CNAE

URL_BASE = "https://www.bcb.gov.br/pda/desig/scrdata_{ano}.zip"
TABELA = "scr_pj_raw"
DESTINO_LOCAL = Path(__file__).parents[2] / "data" / "raw" / "scr"  # gitignored
N_MESES = 12

# Títulos da seção CNAE como o SCR escreve, diferente do resumo oficial
# (levantamento §2: 19 de 22 batem direto)
_TITULO_PARA_SECAO: dict[str, str | None] = {
    titulo: slug for slug, (_letra, titulo) in SETORES_CNAE.items()
}
_TITULO_PARA_SECAO.update(
    {
        "Água, esgoto, atividades de gestão de resíduos e descontaminação": "agua_esgoto_residuos",
        "Organismos internacionais e outras instituições extraterritoriais": "organismos_internacionais",
        "Não informados": None,
    }
)


@dataclass(frozen=True)
class Coluna:
    nome_scr: str
    nome_bq: str
    tipo: str


COLUNAS: tuple[Coluna, ...] = (
    Coluna("data_base", "data_base", "DATE"),
    Coluna("uf", "uf", "STRING"),
    Coluna("cliente", "cliente", "STRING"),
    Coluna("porte", "porte", "STRING"),
    Coluna("cnae_ocupacao", "secao", "STRING"),  # título → slug (aqui em cima)
    Coluna("modalidade", "modalidade", "STRING"),
    Coluna("carteira_ativa", "carteira_ativa", "FLOAT64"),
    Coluna("carteira_inadimplencia", "carteira_inadimplencia", "FLOAT64"),
)


def _dec(b: bytes) -> str:
    """Decodifica campo tolerante a encoding misto (UTF-8 primeiro)."""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("latin-1")


def _numero(valor: str) -> float:
    """'1.234,56' → 1234.56; '-1' (mask) e vazio → NaN."""
    limpo = valor.strip().replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return float("nan")


def ler_meses(fontes: list[Path]) -> pd.DataFrame:
    """Lê os CSVs mensais dos zips (só PJ, só a lista branca). Função pura."""
    saida: list[dict] = []
    for fonte in fontes:
        with zipfile.ZipFile(fonte) as z:
            for nome in sorted(n for n in z.namelist() if n.endswith(".csv")):
                with z.open(nome) as f:
                    texto = io.TextIOWrapper(f, encoding="latin-1", newline="")
                    leitor = csv.reader(texto, delimiter=";")
                    cab = [_dec(c.encode("latin-1")).lstrip("\ufeff").strip() for c in next(leitor)]
                    ix = {c: i for i, c in enumerate(cab)}
                    for linha in leitor:
                        if linha[ix["cliente"]] != "PJ":
                            continue
                        titulo = _dec(linha[ix["cnae_ocupacao"]].encode("latin-1")).strip()
                        saida.append(
                            {
                                "data_base": linha[ix["data_base"]][:10],
                                "uf": linha[ix["uf"]].strip(),
                                "cliente": "PJ",
                                "porte": _dec(linha[ix["porte"]].encode("latin-1")).strip(),
                                "secao": _TITULO_PARA_SECAO.get(titulo),
                                "modalidade": _dec(
                                    linha[ix["modalidade"]].encode("latin-1")
                                ).strip(),
                                "carteira_ativa": _numero(linha[ix["carteira_ativa"]]),
                                "carteira_inadimplencia": _numero(
                                    linha[ix["carteira_inadimplencia"]]
                                ),
                            }
                        )
    return pd.DataFrame(saida, columns=[c.nome_bq for c in COLUNAS])


def ultimos_meses(df: pd.DataFrame, n: int = N_MESES) -> pd.DataFrame:
    """Mantém as `n` últimas data-bases (média de 12 meses suaviza sazonalidade)."""
    bases = sorted(df["data_base"].unique())
    keep = set(bases[-n:])
    return df[df["data_base"].isin(keep)].reset_index(drop=True)


def baixar(ano: int, destino: Path = DESTINO_LOCAL) -> Path:
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"scrdata_{ano}.zip"
    if not arquivo.exists():
        url = URL_BASE.format(ano=ano)
        req = urllib.request.Request(url, headers={"User-Agent": "pme-risk/0.1"})
        with urllib.request.urlopen(req, timeout=1800) as resp, open(arquivo, "wb") as f:
            while bloco := resp.read(1 << 20):
                f.write(bloco)
    return arquivo


def carregar_bq(df: pd.DataFrame, project_id: str, dataset: str) -> str:
    """Substitui `scr_pj_raw` com o recorte dos últimos 12 meses."""
    from google.cloud import bigquery

    client = bigquery.Client(project=project_id)
    table_id = f"{project_id}.{dataset}.{TABELA}"
    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        schema=[bigquery.SchemaField(c.nome_bq, c.tipo) for c in COLUNAS],
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )
    csv_text = df.to_csv(index=False)
    job = client.load_table_from_file(
        io.BytesIO(csv_text.encode("utf-8")), table_id, job_config=config
    )
    job.result()
    return table_id


def main() -> None:
    from datetime import date

    ano_atual = date.today().year
    fontes = [baixar(ano) for ano in (ano_atual, ano_atual - 1)]
    df = ultimos_meses(ler_meses(fontes))
    table_id = carregar_bq(
        df, os.environ["GCP_PROJECT_ID"], os.environ.get("BQ_DATASET", "pme_risk")
    )
    print(f"{len(df)} linhas -> {table_id.split('.', 1)[1]}")
    print(f"meses: {df['data_base'].min()} a {df['data_base'].max()}")
    print(df.groupby("porte")[["carteira_ativa", "carteira_inadimplencia"]].sum().to_string())


if __name__ == "__main__":
    main()
