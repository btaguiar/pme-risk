"""Ingestão SCR.data — funções puras, sem rede nem BigQuery."""

from __future__ import annotations

import math
import zipfile

import pandas as pd

from model.dados.ingest_scr import COLUNAS, _dec, _numero, ler_meses, ultimos_meses


def test_dec_campo_utf8_e_latin1_viram_o_mesmo_texto():
    # O CSV do BCB mistura encodings por campo (levantamento da ingestão)
    assert _dec("Água".encode()) == _dec("Água".encode("latin-1")) == "Água"


def test_numero_formato_brasileiro():
    assert _numero("1.234,56") == 1234.56
    assert _numero("0,00") == 0.0
    assert math.isnan(_numero(""))
    assert _numero("-1") == -1.0


def _zip_com_csv(tmp_path, nome: str, corpo: bytes) -> object:
    caminho = tmp_path / f"{nome}.zip"
    with zipfile.ZipFile(caminho, "w") as z:
        z.writestr(nome, corpo)
    return caminho


# Cabeçalho real (BOM UTF-8); uma linha em latin-1, outra em UTF-8
_CORPO = (
    b"\xef\xbb\xbfdata_base;uf;cliente;cnae_ocupacao;porte;modalidade;"
    b"carteira_ativa;carteira_inadimplencia\n"
    b"2026-07-31;SP;PJ;Constru\xe7\xe3o;Micro;Capital de giro;1000,50;50,25\n"
    b"2026-07-31;RJ;PJ;Ind\xc3\xbastrias de transforma\xc3\xa7\xc3\xa3o;Pequeno;"
    b"Capital de giro;2000,00;100,00\n"
    b"2026-07-31;SP;PF;Com\xe9rcio;Micro;Capital de giro;999,00;0,00\n"
    b"2026-07-31;SP;PJ;N\xe3o informados;Micro;Capital de giro;10,00;0,00\n"
)


def test_ler_meses_filtra_pj_e_mapeia_secao(tmp_path):
    df = ler_meses([_zip_com_csv(tmp_path, "scrdata_202607.csv", _CORPO)])
    assert list(df.columns) == [c.nome_bq for c in COLUNAS]
    assert len(df) == 3  # PF fora
    assert set(df["cliente"]) == {"PJ"}
    assert df["secao"].tolist()[:2] == ["construcao", "industria_transformacao"]
    assert pd.isna(df["secao"].tolist()[2])  # "Não informados"
    assert df["carteira_ativa"].tolist()[0] == 1000.50


def test_ultimos_meses_mantem_12(tmp_path):
    bases = [f"2025-{m:02d}-28" for m in range(1, 13)] + ["2026-01-31", "2026-02-28"]
    df = pd.DataFrame({"data_base": bases})
    recorte = ultimos_meses(df)
    assert recorte["data_base"].min() == "2025-03-28"
    assert len(recorte) == 12
