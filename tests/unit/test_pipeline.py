"""Testes do Pipeline — orquestração com fakes, sem GCP."""

from __future__ import annotations

from agents.redator.redator import ResultadoRedacao
from agents.schemas import DadosEnriquecidos, DadosExtraidos, PedidoCredito
from api.pipeline import LaudoCriado, Pipeline, Recusa

_PEDIDO = PedidoCredito(
    setor="saude_odontologica",
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


def _pipeline(recusa: bool = False) -> tuple[Pipeline, FakePortao, FakeAuditoria]:
    portao = FakePortao()
    auditoria = FakeAuditoria()

    def extrair_fn(texto: str) -> DadosExtraidos:
        return DadosExtraidos(
            pedido=_PEDIDO,
            fora_de_escopo=recusa,
            motivo_recusa="pessoa física" if recusa else None,
        )

    def enriquecer_fn(extraidos: DadosExtraidos) -> DadosEnriquecidos:
        return DadosEnriquecidos(extraidos=extraidos, fonte_por_campo={"setor": "declarado"})

    def prever_fn(features: dict[str, float], project_id: str, dataset: str):
        from model.predict import ResultadoPredicao

        return ResultadoPredicao(
            pd=0.07, faixa_risco="medio", fatores=[("amt_credit", 0.02)], model_version="logreg_v1"
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
