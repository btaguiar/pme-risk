"""Vocabulário fechado de finalidade do crédito.

Até o eval v6 `finalidade` era rótulo livre em snake_case: `modernizacao`,
`automacao` e `equipamentos` nomeavam a mesma compra, e o F1 do campo (0.86)
media concordância de vocabulário, não extração — o mesmo problema que o
`setor` tinha antes da CNAE.

Não há tabela oficial de finalidade para crédito PME. As categorias seguem a
divisão usual entre **capital de giro** e **investimento** (itens financiáveis:
máquinas e equipamentos, veículos, obras civis, software), acrescida dos casos
que o golden set mostra em pedido de PME. Cada código traz a regra de desempate
que o Extrator e o anotador seguem.

O detalhe do pedido ("forno industrial", "abrir filial") vai em
`PedidoCredito.finalidade_detalhe`, texto livre usado no laudo e não avaliado.
"""

from __future__ import annotations

from typing import Literal

# código → (grupo, descrição com a regra de desempate)
FINALIDADES: dict[str, tuple[str, str]] = {
    "capital_de_giro": (
        "giro",
        "Despesas correntes da operação: caixa, folha, contratação de equipe, marketing",
    ),
    "estoque": ("giro", "Mercadorias ou insumos para revenda ou produção (inclui coleção)"),
    "refinanciamento": ("giro", "Quitar ou renegociar dívidas existentes"),
    "maquinas_equipamentos": (
        "investimento",
        "Máquinas, equipamentos e ferramentas — inclui modernizar ou automatizar maquinário",
    ),
    "veiculos": ("investimento", "Veículos e frota (carro, moto, caminhão)"),
    "obras_reforma": (
        "investimento",
        "Reforma, construção ou instalações físicas (galpão, centro de distribuição)",
    ),
    "tecnologia": ("investimento", "Software, sistemas e infraestrutura de TI"),
    "expansao": (
        "investimento",
        "Nova unidade, filial, loja ou linha de produção; ampliar a operação sem item dominante",
    ),
    "abertura_de_empresa": ("investimento", "Investimento inicial de empresa ainda sem operação"),
}

Finalidade = Literal[tuple(FINALIDADES)]  # type: ignore[valid-type]
