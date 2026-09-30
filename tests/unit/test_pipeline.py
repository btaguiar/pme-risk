"""Testes do Pipeline — orquestração com fakes, sem GCP."""

from __future__ import annotations

from agents.redator.redator import ResultadoRedacao
from agents.schemas import DadosEnriquecidos, DadosExtraidos, PedidoCredito
from api.pipeline import LaudoCriado, Pipeline, Recusa
from api.routes.portao_humano import LaudoJaDecididoError

_PEDIDO = PedidoCredito(
    setor="saude_servicos_sociais",
    porte="ME",
    uf="SP",
    anos_operacao=5,
    faturamento_anual_declarado=2_000_000,
    valor_solicitado=300_000,
    prazo_meses=36,
    finalidade="expansao",
)


class FakePortao:
    def __init__(self) -> None:
        self.laudos: dict[str, dict] = {}

    def criar(
        self,
        laudo_id,
        pedido_bruto,
        enriquecidos_json,
        resultado_modelo_json,
        texto,
        evidencias_json,
    ):
        self.laudos[laudo_id] = {
            "laudo_id": laudo_id,
            "pedido_bruto": pedido_bruto,
            "enriquecidos_json": enriquecidos_json,
            "resultado_modelo_json": resultado_modelo_json,
            "texto": texto,
            "evidencias_json": evidencias_json,
            "status": "pendente",
            "criado_em": "2026-09-27T00:00:00Z",
        }

    def obter(self, laudo_id: str) -> dict | None:
        return self.laudos.get(laudo_id)

    def decidir(self, laudo_id, decisao, decidido_por, observacao=None):
        row = self.laudos.get(laudo_id)
        if row is None:
            return None
        if row["status"] != "pendente":
            raise LaudoJaDecididoError(laudo_id, row["status"])
        row.update(
            status=decisao,
            decisao=decisao,
            decidido_por=decidido_por,
            decidido_em="2026-09-27T01:00:00Z",
            observacao_humana=observacao,
        )
        return row


class FakeAuditoria:
    def __init__(self) -> None:
        self.registros: list[dict] = []

    def registrar(self, **kwargs) -> None:
        self.registros.append(kwargs)


def _pipeline(
    recusa: bool = False, features_capturadas: list[dict[str, float]] | None = None
) -> tuple[Pipeline, FakePortao, FakeAuditoria]:
    portao = FakePortao()
    auditoria = FakeAuditoria()

    def extrair_fn(texto: str, project_id: str | None = None) -> DadosExtraidos:
        return DadosExtraidos(
            pedido=_PEDIDO,
            fora_de_escopo=recusa,
            motivo_recusa="pessoa física" if recusa else None,
        )

    def enriquecer_fn(extraidos: DadosExtraidos) -> DadosEnriquecidos:
        return DadosEnriquecidos(extraidos=extraidos, fonte_por_campo={"setor": "declarado"})

    def prever_fn(features: dict[str, float | str], project_id: str, dataset: str, **_calib):
        from model.predict import ResultadoPredicao

        if features_capturadas is not None:
            features_capturadas.append(features)
        return ResultadoPredicao(
            pd=0.07,
            faixa_risco="medio",
            fatores=[("log_valor_usd", 0.02), ("faixa_idade", -0.03)],
            model_version="logreg_v1",
        )

    def redigir_fn(enriquecidos, resultado_modelo, project_id=None) -> ResultadoRedacao:
        return ResultadoRedacao(texto="Laudo de risco.", evidencias=["LGPD art. 20"])

    pipeline = Pipeline(
        "projeto-teste",
        "dataset_teste",
        extrair_fn=extrair_fn,
        enriquecer_fn=enriquecer_fn,
        prever_fn=prever_fn,
        redigir_fn=redigir_fn,
        portao=portao,
        auditoria=auditoria,
    )
    return pipeline, portao, auditoria


class TestPipelineGerar:
    def test_caminho_feliz_cria_laudo_pendente(self):
        pipeline, portao, _ = _pipeline()
        resultado = pipeline.gerar("texto do pedido")
        assert isinstance(resultado, LaudoCriado)
        assert resultado.status == "pendente"
        row = portao.obter(resultado.laudo_id)
        assert row is not None and row["status"] == "pendente"

    def test_caminho_feliz_registra_auditoria(self):
        pipeline, _, auditoria = _pipeline()
        resultado = pipeline.gerar("texto do pedido")
        assert isinstance(resultado, LaudoCriado)
        assert len(auditoria.registros) == 1
        registro = auditoria.registros[0]
        assert registro["laudo_id"] == resultado.laudo_id
        assert registro["model_version"] == "logreg_v1"
        assert "extrator" in registro["prompts_usados"]
        assert "redator" in registro["prompts_usados"]
        assert [e["etapa"] for e in registro["etapas"]] == [
            "extrator",
            "pesquisador",
            "modelo",
            "redator",
        ]

    def test_recusa_nao_cria_laudo_mas_audita(self):
        pipeline, portao, auditoria = _pipeline(recusa=True)
        resultado = pipeline.gerar("pedido de pessoa física")
        assert isinstance(resultado, Recusa)
        assert resultado.motivo == "pessoa física"
        assert portao.laudos == {}
        assert len(auditoria.registros) == 1
        assert auditoria.registros[0]["model_version"] is None

    def test_pd_no_laudo_e_a_do_modelo(self):
        import json

        pipeline, portao, _ = _pipeline()
        resultado = pipeline.gerar("texto")
        assert isinstance(resultado, LaudoCriado)
        row = portao.obter(resultado.laudo_id)
        resultado_modelo = json.loads(row["resultado_modelo_json"])
        assert resultado_modelo["pd"] == 0.07
        assert resultado_modelo["model_version"] == "logreg_v1"

    def test_fatores_do_modelo_vao_ao_laudo(self):
        import json

        pipeline, portao, _ = _pipeline()
        resultado = pipeline.gerar("texto")
        assert isinstance(resultado, LaudoCriado)
        row = portao.obter(resultado.laudo_id)
        fatores = json.loads(row["resultado_modelo_json"])["fatores"]
        assert fatores == [["log_valor_usd", 0.02], ["faixa_idade", -0.03]]

    def test_features_derivam_do_pedido(self):
        import math

        capturadas: list[dict[str, float | str]] = []
        pipeline, _, _ = _pipeline(features_capturadas=capturadas)
        resultado = pipeline.gerar("texto")
        assert isinstance(resultado, LaudoCriado)
        feats = capturadas[0]
        assert feats["secao_cnae"] == "saude_servicos_sociais"
        assert feats["faixa_idade"] == "5_mais"
        assert feats["log_valor_usd"] == math.log(300_000 / 2.55440835439356)

    def test_prazo_do_formulario_prevalece_sobre_o_extraido(self):
        import json

        capturadas: list[dict[str, float | str]] = []
        pipeline, portao, auditoria = _pipeline(features_capturadas=capturadas)
        resultado = pipeline.gerar("texto do pedido", prazo_meses=12)  # extraído: 36
        assert isinstance(resultado, LaudoCriado)
        row = portao.obter(resultado.laudo_id)
        assert json.loads(row["enriquecidos_json"])["extraidos"]["pedido"]["prazo_meses"] == 12
        assert "Prazo solicitado: 12 meses" in row["pedido_bruto"]
        assert "Prazo solicitado: 12 meses" in auditoria.registros[0]["pedido_bruto"]

    def test_sem_prazo_do_formulario_mantem_o_extraido(self):
        import json

        capturadas: list[dict[str, float | str]] = []
        pipeline, portao, _ = _pipeline(features_capturadas=capturadas)
        pipeline.gerar("texto do pedido")
        row = portao.obter(list(portao.laudos)[0])
        assert json.loads(row["enriquecidos_json"])["extraidos"]["pedido"]["prazo_meses"] == 36


class TestPipelineDecisao:
    def test_decidir_encaminha_para_portao(self):
        pipeline, _, _ = _pipeline()
        laudo = pipeline.gerar("texto")
        assert isinstance(laudo, LaudoCriado)
        row = pipeline.decidir(laudo.laudo_id, "aprovado", "analista-1")
        assert row is not None and row["status"] == "aprovado"

    def test_decidir_laudo_inexistente_retorna_none(self):
        pipeline, _, _ = _pipeline()
        assert pipeline.decidir("inexistente", "aprovado", "analista-1") is None

    def test_decisao_entra_na_trilha_de_auditoria(self):
        import json

        pipeline, _, auditoria = _pipeline()
        laudo = pipeline.gerar("texto")
        assert isinstance(laudo, LaudoCriado)
        pipeline.decidir(laudo.laudo_id, "rejeitado", "analista-1", "renda inconsistente")
        assert len(auditoria.registros) == 2
        registro = auditoria.registros[1]
        assert registro["laudo_id"] == laudo.laudo_id
        assert registro["model_version"] == "logreg_v1"
        assert [e["etapa"] for e in registro["etapas"]] == ["decisao_humana"]
        decisao = json.loads(registro["decisao_humana"])
        assert decisao["decisao"] == "rejeitado"
        assert decisao["decidido_por"] == "analista-1"
        assert decisao["observacao"] == "renda inconsistente"

    def test_redecidir_levanta_e_nao_audita(self):
        import pytest

        pipeline, portao, auditoria = _pipeline()
        laudo = pipeline.gerar("texto")
        assert isinstance(laudo, LaudoCriado)
        pipeline.decidir(laudo.laudo_id, "aprovado", "analista-1")
        with pytest.raises(LaudoJaDecididoError):
            pipeline.decidir(laudo.laudo_id, "rejeitado", "outra-pessoa")
        assert portao.obter(laudo.laudo_id)["decidido_por"] == "analista-1"
        assert len(auditoria.registros) == 2

    def test_falha_de_auditoria_nao_desfaz_decisao(self):
        pipeline, portao, auditoria = _pipeline()
        laudo = pipeline.gerar("texto")
        assert isinstance(laudo, LaudoCriado)

        def falhar(**_kwargs):
            raise RuntimeError("BigQuery fora")

        auditoria.registrar = falhar
        row = pipeline.decidir(laudo.laudo_id, "aprovado", "analista-1")
        assert row is not None and row["status"] == "aprovado"
