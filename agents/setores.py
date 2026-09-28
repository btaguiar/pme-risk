"""Vocabulário fechado de setor — seções da CNAE 2.0 (IBGE/CONCLA).

Até o eval v5 `setor` era rótulo livre em snake_case: o Extrator e o anotador
escreviam sinônimos (`varejo_otica` × `varejo_optica`) e o F1 do campo media
concordância de vocabulário (0.60). A seção CNAE é um padrão externo, é o que
uma consulta de CNPJ devolve e restringe a saída do Gemini via response_schema.

O detalhe do negócio ("padaria", "clínica odontológica") vai em
`PedidoCredito.atividade`, texto livre usado no laudo e não avaliado.
"""

from __future__ import annotations

from typing import Literal

# código → (letra da seção CNAE 2.0, título oficial resumido)
SETORES_CNAE: dict[str, tuple[str, str]] = {
    "agropecuaria": ("A", "Agricultura, pecuária, produção florestal, pesca e aquicultura"),
    "industria_extrativa": ("B", "Indústrias extrativas"),
    "industria_transformacao": ("C", "Indústrias de transformação"),
    "eletricidade_gas": ("D", "Eletricidade e gás"),
    "agua_esgoto_residuos": ("E", "Água, esgoto, gestão de resíduos e descontaminação"),
    "construcao": ("F", "Construção"),
    "comercio": ("G", "Comércio; reparação de veículos automotores e motocicletas"),
    "transporte_armazenagem": ("H", "Transporte, armazenagem e correio"),
    "alojamento_alimentacao": ("I", "Alojamento e alimentação"),
    "informacao_comunicacao": ("J", "Informação e comunicação"),
    "financeiro_seguros": ("K", "Atividades financeiras, de seguros e serviços relacionados"),
    "atividades_imobiliarias": ("L", "Atividades imobiliárias"),
    "profissionais_cientificas_tecnicas": ("M", "Atividades profissionais, científicas e técnicas"),
    "administrativas_servicos_complementares": (
        "N",
        "Atividades administrativas e serviços complementares",
    ),
    "administracao_publica": ("O", "Administração pública, defesa e seguridade social"),
    "educacao": ("P", "Educação"),
    "saude_servicos_sociais": ("Q", "Saúde humana e serviços sociais"),
    "artes_cultura_esporte": ("R", "Artes, cultura, esporte e recreação"),
    "outros_servicos": ("S", "Outras atividades de serviços"),
    "servicos_domesticos": ("T", "Serviços domésticos"),
    "organismos_internacionais": ("U", "Organismos internacionais e outras instituições"),
}

SetorCNAE = Literal[tuple(SETORES_CNAE)]  # type: ignore[valid-type]
