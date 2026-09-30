"""Juiz determinístico do texto do laudo — fidedignidade e verificado × declarado.

PLANO §5: "Fidedignidade do laudo — % de afirmações com evidência citada (100%)"
e "Verificado vs. declarado — % de campos classificados corretamente (100%)".

Sem LLM como juiz: reproduzível e sem custo. Verifica as afirmações que dá para
checar mecanicamente:
- **números**: todo número do texto precisa bater com uma evidência (valores do
  pedido, números do texto original, PD, contribuições dos fatores);
- **fatores**: todo nome entre crases precisa ser fator do modelo ou campo do pedido;
- **normas**: toda norma citada precisa estar no corpus permitido e em `evidencias`.

Limite: afirmações qualitativas ("setor resiliente") não são checadas.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

# Corpus do prompt do Redator (agents/redator/prompt.md, "Normas disponíveis")
NORMAS_PERMITIDAS = {
    "lgpd_art20": "LGPD art. 20",
    "cmn_4966": "Res. CMN 4.966",
    "politica_pme": "Política de crédito PME",
}

# Citação de norma no texto → chave canônica (None = norma fora do corpus)
_PADROES_NORMA = [
    (re.compile(r"LGPD[^\n]{0,40}?art(?:igo|\.)?\s*20\b", re.I), "lgpd_art20"),
    (re.compile(r"art(?:igo|\.)?\s*20[^\n]{0,20}?LGPD", re.I), "lgpd_art20"),
    # Nome por extenso: "Art. 20 da Lei Geral de Proteção de Dados (LGPD)"
    (
        re.compile(r"art(?:igo|\.)?\s*20[^\n]{0,20}?Lei Geral de Prote[çc][ãa]o de Dados", re.I),
        "lgpd_art20",
    ),
    (re.compile(r"Res(?:olução|\.)?\s*(?:CMN\s*)?(?:n[º°.]?\s*)?4\.?966", re.I), "cmn_4966"),
    (re.compile(r"Pol[íi]tica de cr[ée]dito(?: PME)?", re.I), "politica_pme"),
    (
        re.compile(
            r"\b(?:Lei(?: Complementar)?|LC|Res(?:olução|\.)|Circular|Instru[çc][ãa]o)"
            r"\s*(?:CMN\s*|BCB\s*|CVM\s*)?(?:n[º°.]?\s*)?\d[\d.]*(?:/\d+)?",
            re.I,
        ),
        None,
    ),
]

# Número (com sinal, milhar/decimal pt-BR ou en), sufixo de escala e % opcionais
_NUMERO = re.compile(
    r"(?<![\w.])([-+−]?\d[\d.,]*\d|[-+−]?\d)(\s*%)?"
    r"(\s*(?:mil\b|milh(?:ão|ões|oes)\b|mi\b|bilh(?:ão|ões)\b|[kMB]\b))?",
    re.I,
)
# Enumerador de lista ou título numerado ("1. ", "## 2. Dados", "**3. Análise**")
_ENUMERADOR = re.compile(r"^[\s#*>_-]*\d+[.)]\s", re.M)
_CRASE = re.compile(r"`([a-z_][a-z0-9_]*)`")
# Nomes próprios com dígito que não são afirmação numérica: o programa da base
# de treino do v3 ("SBA 7(a)", citado por instrução do prompt do Redator)
_CNPJ_FORMATADO = re.compile(r"\b\d{2}\.\d{3}\.\d{3}/\d{4}-\d{2}\b")
_NOMES_COM_NUMERO = re.compile(r"\bSBA\s*7\s*\(a\)", re.I)

_ESCALA = {"mil": 1e3, "k": 1e3, "mi": 1e6, "m": 1e6, "b": 1e9}


def _escala(sufixo: str | None) -> float:
    if not sufixo:
        return 1.0
    s = sufixo.strip().lower()
    if s.startswith("milh"):
        return 1e6
    if s.startswith("bilh"):
        return 1e9
    return _ESCALA.get(s, 1.0)


def _casas(parte_decimal: str) -> int:
    return len(parte_decimal)


def interpretar_numero(bruto: str) -> set[tuple[float, int]]:
    """Leituras plausíveis (valor, casas decimais escritas) de um número (pt-BR ou en).

    "150.000" pode ser 150000 (milhar pt-BR, 0 casas) ou 150.0 (decimal en, 3
    casas) — o juiz aceita se qualquer leitura tiver evidência.
    """
    s = bruto.replace("−", "-").lstrip("+")
    sinal = -1.0 if s.startswith("-") else 1.0
    s = s.lstrip("-")
    leituras: set[tuple[float, int]] = set()
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):  # 1.800.000,50
            leituras.add((float(s.replace(".", "").replace(",", ".")), _casas(s.split(",")[-1])))
        else:  # 1,800,000.50
            leituras.add((float(s.replace(",", "")), _casas(s.split(".")[-1])))
    elif "," in s:
        if re.fullmatch(r"[1-9]\d{0,2}(,\d{3})+", s):  # milhar nunca começa com 0
            leituras.add((float(s.replace(",", "")), 0))
        if s.count(",") == 1:
            leituras.add((float(s.replace(",", ".")), _casas(s.split(",")[-1])))
    elif "." in s:
        if re.fullmatch(r"[1-9]\d{0,2}(\.\d{3})+", s):
            leituras.add((float(s.replace(".", "")), 0))
        if s.count(".") == 1:
            leituras.add((float(s), _casas(s.split(".")[-1])))
    else:
        leituras.add((float(s), 0))
    return {(sinal * v, c) for v, c in leituras}


@dataclass(frozen=True)
class NumeroNoTexto:
    trecho: str
    # (valor, casas decimais escritas) — as casas toleram o arredondamento do texto
    leituras: frozenset[tuple[float, int]]

    @property
    def valores(self) -> set[float]:
        return {v for v, _ in self.leituras}


def extrair_numeros(texto: str) -> list[NumeroNoTexto]:
    """Números do texto, sem enumeradores, números de normas e nomes como SBA 7(a)."""
    limpo = _NOMES_COM_NUMERO.sub(" ", _ENUMERADOR.sub(" ", texto))
    for padrao, _ in _PADROES_NORMA:
        limpo = padrao.sub(" ", limpo)
    numeros = []
    for m in _NUMERO.finditer(limpo):
        bruto, pct, sufixo = m.group(1), m.group(2), m.group(3)
        base = interpretar_numero(bruto)
        escala = _escala(sufixo)
        leituras = {(v * escala, c if escala == 1 else 0) for v, c in base}
        if pct:  # "5,59%" também vale como 0.0559, com 2 casas a mais
            leituras |= {(v / 100, c + 2) for v, c in base}
        numeros.append(NumeroNoTexto(m.group(0).strip(), frozenset(leituras)))
    return numeros


def tem_evidencia(numero: NumeroNoTexto, evidencias: set[float]) -> bool:
    """Casa com alguma evidência, tolerando o arredondamento que o texto aplicou.

    "0.057" casa com 0.05742 (3 casas); "5,59%" casa com a PD 0.05589;
    "-0.034" casa com -0.03452 (truncado).
    """
    for v, casas in numero.leituras:
        for e in evidencias:
            if math.isclose(v, e, rel_tol=5e-3, abs_tol=1e-9):
                return True
            if casas > 0 or float(v).is_integer():
                # arredondado (0.0746 → 0.075) ou truncado (0.0746 → 0.074) — os
                # dois aparecem nos laudos; nenhum é invenção
                truncado = math.trunc(e * 10**casas) / 10**casas
                if round(v, casas) in (round(e, casas), round(truncado, casas)):
                    return True
    return False


def normas_citadas(texto: str) -> list[str | None]:
    """Chaves das normas citadas; None para norma fora do corpus permitido."""
    achadas: list[tuple[int, str | None]] = []
    ocupado: list[tuple[int, int]] = []
    for padrao, chave in _PADROES_NORMA:
        for m in padrao.finditer(texto):
            if any(a < m.end() and m.start() < b for a, b in ocupado):
                continue  # já contada por um padrão mais específico
            ocupado.append((m.start(), m.end()))
            achadas.append((m.start(), chave))
    return [chave for _, chave in sorted(achadas, key=lambda x: x[0])]


def normalizar_evidencia(item: str) -> str | None:
    for chave in normas_citadas(item):
        return chave
    return None


@dataclass
class Julgamento:
    """Resultado do juiz para um laudo."""

    afirmacoes: int = 0
    com_evidencia: int = 0
    numeros_sem_evidencia: list[str] = field(default_factory=list)
    fatores_desconhecidos: list[str] = field(default_factory=list)
    normas_fora_do_corpus: int = 0
    normas_sem_citacao: list[str] = field(default_factory=list)
    evidencias_fora_do_corpus: list[str] = field(default_factory=list)
    pd_citada: bool = False
    campos_mencionados: int = 0
    campos_marcados_ok: int = 0
    campos_marcados_errado: list[str] = field(default_factory=list)
    marcas_verificado: int = 0

    @property
    def fidedignidade(self) -> float:
        return self.com_evidencia / self.afirmacoes if self.afirmacoes else 1.0

    @property
    def marcacao(self) -> float:
        return self.campos_marcados_ok / self.campos_mencionados if self.campos_mencionados else 1.0


def julgar(
    texto: str,
    evidencias_citadas: list[str],
    pd: float,
    fatores: list[tuple[str, float]],
    campos: dict[str, object],
    texto_pedido: str,
    fonte_por_campo: dict[str, str] | None = None,
    cnpj_dados: dict | None = None,
) -> Julgamento:
    """Julga um laudo contra suas fontes.

    Args:
        texto: texto do laudo
        evidencias_citadas: lista `evidencias` devolvida pelo redator
        pd: PD do modelo
        fatores: (nome, contribuição) do modelo
        campos: valores de referência do pedido (golden set)
        texto_pedido: texto original do pedido — números dele têm evidência
        fonte_por_campo: classificação por campo; None = todos declarados
        cnpj_dados: dados públicos do CNPJ — números deles têm evidência
    """
    j = Julgamento()

    # Números
    evid: set[float] = {pd, *(c for _, c in fatores)}
    evid |= {float(v) for v in campos.values() if isinstance(v, int | float)}
    # Contas verificáveis a partir do pedido ("representa 20% do faturamento",
    # parcela por mês) — derivadas, não soltas
    valor = campos.get("valor_solicitado")
    fat = campos.get("faturamento_anual_declarado")
    prazo = campos.get("prazo_meses")
    if isinstance(valor, int | float) and isinstance(fat, int | float) and fat:
        evid.add(valor / fat)
    if isinstance(valor, int | float) and isinstance(prazo, int | float) and prazo:
        evid.add(valor / prazo)
    for n in extrair_numeros(texto_pedido):
        evid |= set(n.valores)
    # Dados públicos (anos desde a abertura, CNAE) — só os numéricos de topo
    evid |= {
        float(v)
        for v in (cnpj_dados or {}).values()
        if isinstance(v, int | float) and not isinstance(v, bool)
    }
    # CNPJ formatado (12.345.678/0001-00) é um identificador, não três números:
    # vale se os dígitos batem com o CNPJ do pedido ou da consulta pública
    cnpjs_fonte = {
        re.sub(r"\D", "", str(c)) for c in (campos.get("cnpj"), (cnpj_dados or {}).get("cnpj")) if c
    }
    for m in _CNPJ_FORMATADO.finditer(texto):
        j.afirmacoes += 1
        if re.sub(r"\D", "", m.group(0)) in cnpjs_fonte:
            j.com_evidencia += 1
        else:
            j.numeros_sem_evidencia.append(m.group(0))
    for n in extrair_numeros(_CNPJ_FORMATADO.sub(" ", texto)):
        j.afirmacoes += 1
        if tem_evidencia(n, evid):
            j.com_evidencia += 1
        else:
            j.numeros_sem_evidencia.append(n.trecho)
    # PD citada = algum número decimal do texto é a PD (0.0664, 6,64%)
    j.pd_citada = any(
        tem_evidencia(n, {pd}) for n in extrair_numeros(texto) if any(c > 0 for _, c in n.leituras)
    )

    # Fatores / campos entre crases
    # Fatores, campos e a faixa de risco (derivada da PD pela função do modelo —
    # faixa errada entre crases continua sendo acusada)
    from model.predict import classificar_faixa_risco

    # Valores categóricos do pedido também são citáveis (o fator `secao_cnae`
    # convida a citar o setor, ex. `saude_servicos_sociais`) — só se iguais ao
    # pedido ou à consulta pública
    valores_citaveis = {v for v in campos.values() if isinstance(v, str)}
    valores_citaveis |= {x for v in campos.values() if isinstance(v, list) for x in v}
    valores_citaveis |= {v for v in (cnpj_dados or {}).values() if isinstance(v, str)}
    nomes_validos = (
        {nome for nome, _ in fatores}
        | set(campos)
        | valores_citaveis
        | {classificar_faixa_risco(pd)}
    )
    for nome in _CRASE.findall(texto):
        j.afirmacoes += 1
        if nome in nomes_validos:
            j.com_evidencia += 1
        else:
            j.fatores_desconhecidos.append(nome)

    # Normas
    citadas_evid = {normalizar_evidencia(e) for e in evidencias_citadas}
    for e in evidencias_citadas:
        if normalizar_evidencia(e) is None:
            j.evidencias_fora_do_corpus.append(e)
    for chave in normas_citadas(texto):
        j.afirmacoes += 1
        if chave is None:
            j.normas_fora_do_corpus += 1
        elif chave not in citadas_evid:
            j.normas_sem_citacao.append(NORMAS_PERMITIDAS[chave])
        else:
            j.com_evidencia += 1

    # Verificado × declarado: linha onde o valor do campo aparece precisa da marca
    fonte_por_campo = fonte_por_campo or {}
    linhas = texto.splitlines()
    j.marcas_verificado = texto.count("✅")
    for campo, valor in campos.items():
        if valor is None or campo in (
            "setor",
            "finalidade",
            "cnpj",
            "atividade",
            "finalidade_detalhe",
        ):
            continue  # rótulos normalizados não aparecem literalmente no texto
        linhas_campo = [ln for ln in linhas if _linha_menciona(ln, valor)]
        if not linhas_campo:
            continue
        j.campos_mencionados += 1
        esperada = "✅" if fonte_por_campo.get(campo) == "verificado" else "⚠️"
        oposta = "⚠️" if esperada == "✅" else "✅"
        if any(esperada in ln and oposta not in ln for ln in linhas_campo):
            j.campos_marcados_ok += 1
        else:
            j.campos_marcados_errado.append(campo)
    return j


def _linha_menciona(linha: str, valor: object) -> bool:
    if isinstance(valor, str):
        return re.search(rf"\b{re.escape(valor)}\b", linha) is not None
    alvo = float(valor)  # type: ignore[arg-type]
    return any(tem_evidencia(n, {alvo}) for n in extrair_numeros(linha))
