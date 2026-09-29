// Pedido guiado: campos estruturados → texto em português para o Extrator,
// e checklist ao vivo (campos preenchidos ou menções detectadas no texto livre).

export type Porte = "MEI" | "ME" | "EPP";

export interface DadosPedido {
  atividade: string;
  setor: string; // código CNAE de agents/setores.py; "" = o Extrator identifica
  cidade: string;
  uf: string;
  porte: Porte | "";
  anos: string;
  faturamento: number | null;
  valor: number | null;
  finalidade: string;
}

export const PEDIDO_VAZIO: DadosPedido = {
  atividade: "",
  setor: "",
  cidade: "",
  uf: "",
  porte: "",
  anos: "",
  faturamento: null,
  valor: null,
  finalidade: "",
};

/** Seções CNAE de agents/setores.py relevantes para PME: código → [letra, título oficial, rótulo curto]. */
export const SETORES: [string, string, string, string][] = [
  ["agropecuaria", "A", "Agricultura, pecuária, produção florestal, pesca e aquicultura", "Agropecuária"],
  ["industria_extrativa", "B", "Indústrias extrativas", "Indústria extrativa"],
  ["industria_transformacao", "C", "Indústrias de transformação", "Indústria / fabricação"],
  ["eletricidade_gas", "D", "Eletricidade e gás", "Energia e gás"],
  ["agua_esgoto_residuos", "E", "Água, esgoto, gestão de resíduos e descontaminação", "Água, esgoto e resíduos"],
  ["construcao", "F", "Construção", "Construção"],
  ["comercio", "G", "Comércio; reparação de veículos automotores e motocicletas", "Comércio e reparação de veículos"],
  ["transporte_armazenagem", "H", "Transporte, armazenagem e correio", "Transporte e armazenagem"],
  ["alojamento_alimentacao", "I", "Alojamento e alimentação", "Hotéis, bares e restaurantes"],
  ["informacao_comunicacao", "J", "Informação e comunicação", "Tecnologia e comunicação"],
  ["financeiro_seguros", "K", "Atividades financeiras, de seguros e serviços relacionados", "Financeiro e seguros"],
  ["atividades_imobiliarias", "L", "Atividades imobiliárias", "Imobiliário"],
  ["profissionais_cientificas_tecnicas", "M", "Atividades profissionais, científicas e técnicas", "Serviços profissionais e técnicos"],
  ["administrativas_servicos_complementares", "N", "Atividades administrativas e serviços complementares", "Serviços administrativos"],
  ["educacao", "P", "Educação", "Educação"],
  ["saude_servicos_sociais", "Q", "Saúde humana e serviços sociais", "Saúde e serviços sociais"],
  ["artes_cultura_esporte", "R", "Artes, cultura, esporte e recreação", "Artes, cultura e esporte"],
  ["outros_servicos", "S", "Outras atividades de serviços", "Outros serviços"],
];

export const UFS = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
  "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO",
];

export const PORTES: { valor: Porte; rotulo: string; dica: string }[] = [
  { valor: "MEI", rotulo: "MEI", dica: "microempreendedor" },
  { valor: "ME", rotulo: "ME", dica: "até R$ 360 mil/ano" },
  { valor: "EPP", rotulo: "EPP", dica: "até R$ 4,8 mi/ano" },
];
const PORTE_EXTENSO: Record<Porte, string> = {
  MEI: "MEI (microempreendedor individual)",
  ME: "ME (microempresa)",
  EPP: "EPP (empresa de pequeno porte)",
};

export const FINALIDADES = ["capital de giro", "compra de equipamentos", "expansão", "reforma", "estoque", "veículos"];

const fmtReais = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });

export function anosValidos(v: string) {
  const n = Number(v.replace(",", "."));
  return v.trim() !== "" && Number.isFinite(n) && n >= 0 && n <= 150;
}

/** Texto do pedido montado a partir dos campos — é o que o Extrator lê. */
export function compor(d: DadosPedido, prazo?: string): string {
  const partes: string[] = [];
  const quem = d.atividade.trim() || "Empresa";
  const cidade = d.cidade.trim();
  const onde = cidade && d.uf ? `${cidade} (${d.uf})` : cidade || d.uf;
  let frase = quem + (onde ? ` em ${onde}` : "");
  if (d.porte) frase += `, porte ${PORTE_EXTENSO[d.porte]}`;
  const anos = d.anos.trim().replace(".", ",");
  const detalhes: string[] = [];
  if (anosValidos(d.anos)) detalhes.push(`${anos} ${Number(d.anos.replace(",", ".")) === 1 ? "ano" : "anos"} de operação`);
  if (d.faturamento) detalhes.push(`faturamento anual declarado de ${fmtReais.format(d.faturamento)}`);
  if (detalhes.length) frase += `, com ${detalhes.join(" e ")}`;
  partes.push(frase + ".");

  if (d.valor || d.finalidade.trim()) {
    let pedido = "Solicita";
    if (d.valor) pedido += ` ${fmtReais.format(d.valor)}`;
    if (prazo && Number(prazo) > 0) pedido += ` em ${prazo} meses`;
    if (d.finalidade.trim()) pedido += ` para ${d.finalidade.trim()}`;
    partes.push(pedido + ".");
  }
  const setor = SETORES.find(([c]) => c === d.setor);
  if (setor) partes.push(`Setor CNAE: seção ${setor[1]} — ${setor[2]}.`);
  return partes.join(" ");
}

export type ItemChecklist = { chave: string; rotulo: string; ok: boolean };

/** Checklist no modo guiado: cada item é um campo obrigatório preenchido. */
export function checklistGuiado(d: DadosPedido): ItemChecklist[] {
  return [
    { chave: "atividade", rotulo: "Atividade e UF", ok: !!d.atividade.trim() && !!d.uf },
    { chave: "porte", rotulo: "Porte (MEI, ME, EPP)", ok: !!d.porte },
    { chave: "anos", rotulo: "Tempo de operação", ok: anosValidos(d.anos) },
    { chave: "faturamento", rotulo: "Faturamento anual", ok: !!d.faturamento },
    { chave: "valor", rotulo: "Valor solicitado", ok: !!d.valor },
    { chave: "finalidade", rotulo: "Finalidade", ok: !!d.finalidade.trim() },
  ];
}

export function guiadoCompleto(d: DadosPedido) {
  return checklistGuiado(d).every((i) => i.ok);
}

const RE_UF = new RegExp(`\\b(${UFS.join("|")})\\b`);
const RE_LOCAL =
  /s[aã]o paulo|rio de janeiro|minas gerais|belo horizonte|curitiba|paran[aá]|bahia|salvador|porto alegre|rio grande|santa catarina|florian[oó]polis|goi[aá]s|goi[aâ]nia|bras[ií]lia|distrito federal|recife|pernambuco|fortaleza|cear[aá]|manaus|amazonas|bel[eé]m|par[aá]\b|esp[ií]rito santo|vit[oó]ria|campinas|natal|jo[aã]o pessoa|macei[oó]|aracaju|teresina|s[aã]o lu[ií]s|cuiab[aá]|campo grande/i;

/**
 * Checklist no modo texto livre: detecção heurística de cada item.
 * É só um guia para o usuário — o Extrator é quem interpreta o texto de verdade.
 */
export function checklistTexto(texto: string): ItemChecklist[] {
  const t = texto;
  return [
    { chave: "atividade", rotulo: "Atividade e cidade/UF", ok: RE_UF.test(t) || RE_LOCAL.test(t) },
    {
      chave: "porte",
      rotulo: "Porte (MEI, ME, EPP)",
      ok: /\b(MEI|ME|EPP)\b/.test(t) || /micro\s?empre|pequeno porte|microempreendedor/i.test(t),
    },
    {
      chave: "anos",
      rotulo: "Tempo de operação",
      ok:
        /\d+([.,]\d+)?\s*(anos?|meses)\s+(de\s+)?(opera|mercado|atividade|funcionamento|exist[eê]ncia|vida|estrada)/i.test(t) ||
        /h[aá]\s+\d+\s+anos/i.test(t) ||
        /(fundad[ao]|aberta|aberto|desde)\s.{0,15}\d{4}/i.test(t),
    },
    { chave: "faturamento", rotulo: "Faturamento anual", ok: /fatura|receita|vend[ae]s?\s+(anua|mensa)/i.test(t) },
    {
      chave: "valor",
      rotulo: "Valor solicitado",
      ok: /(solicit|ped[ei]|precisa|quer|busca|empr[eé]stimo|financiamento|cr[eé]dito)\D{0,40}(R\$|\d+\s*(mil|milh|k\b))/i.test(t),
    },
    {
      chave: "finalidade",
      rotulo: "Finalidade",
      ok:
        /capital de giro/i.test(t) ||
        /(para|finalidade:?|objetivo:?)\s+(a\s+|o\s+)?(expan|compr|capital|giro|reform|estoque|renov|ampli|contrat|abr|invest|adquir|pag|quit|equip|m[aá]quin|ve[ií]cul|obra|market|tecnolog|constru|moderniz)/i.test(t),
    },
  ];
}

export interface Exemplo {
  rotulo: string;
  dados: DadosPedido;
  prazo: number;
}

export const EXEMPLOS: Exemplo[] = [
  {
    rotulo: "Clínica odontológica",
    prazo: 24,
    dados: {
      atividade: "Clínica odontológica",
      setor: "saude_servicos_sociais",
      cidade: "São Paulo",
      uf: "SP",
      porte: "ME",
      anos: "5",
      faturamento: 2_000_000,
      valor: 300_000,
      finalidade: "expansão",
    },
  },
  {
    rotulo: "Padaria artesanal",
    prazo: 24,
    dados: {
      atividade: "Padaria artesanal",
      setor: "",
      cidade: "Belo Horizonte",
      uf: "MG",
      porte: "ME",
      anos: "3",
      faturamento: 850_000,
      valor: 120_000,
      finalidade: "comprar um forno e ampliar a produção",
    },
  },
  {
    rotulo: "Transportadora",
    prazo: 36,
    dados: {
      atividade: "Transportadora de cargas",
      setor: "transporte_armazenagem",
      cidade: "Curitiba",
      uf: "PR",
      porte: "EPP",
      anos: "8",
      faturamento: 4_500_000,
      valor: 600_000,
      finalidade: "renovar dois caminhões",
    },
  },
];
