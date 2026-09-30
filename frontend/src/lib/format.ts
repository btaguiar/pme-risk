const fmtBRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 });
const fmtBRLCompacto = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
});
export const fmtNum = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
const fmtData = new Intl.DateTimeFormat("pt-BR", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "America/Sao_Paulo",
});
const fmtDia = new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", timeZone: "America/Sao_Paulo" });

export function dataCurta(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : fmtData.format(d);
}

export function dia(iso?: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : fmtDia.format(d);
}

export function percentual(pd?: number | null, casas = 2) {
  if (pd === null || pd === undefined) return "—";
  return `${(pd * 100).toLocaleString("pt-BR", { maximumFractionDigits: casas, minimumFractionDigits: casas > 1 ? 1 : 0 })}%`;
}

export function moeda(valor?: number | null, compacto = false) {
  if (valor === null || valor === undefined) return "—";
  return (compacto ? fmtBRLCompacto : fmtBRL).format(Number(valor));
}

export type Faixa = "baixo" | "medio" | "alto" | "muito_alto";

export function classeFaixa(faixa?: string | null): Faixa {
  const f = String(faixa || "").toLowerCase();
  if (f.includes("baix")) return "baixo";
  if (f.includes("muito")) return "muito_alto";
  if (f.includes("alt")) return "alto";
  return "medio";
}

export const FAIXA_ROTULO: Record<Faixa, string> = {
  baixo: "Risco baixo",
  medio: "Risco médio",
  alto: "Risco alto",
  muito_alto: "Risco muito alto",
};

/** Limites de model/predict.py::classificar_faixa_risco. */
export const LIMITES_FAIXA = { baixo: 0.05, medio: 0.15, alto: 0.3 } as const;

export const STATUS_ROTULO: Record<string, string> = {
  pendente: "Pendente",
  aprovado: "Aprovado",
  corrigido: "Corrigido",
  rejeitado: "Rejeitado",
};

export function idCurto(id: string) {
  return id.slice(0, 8);
}

/** Fatores do modelo v3 (model/features.py) e ajustes da calibração SCR (model/calibracao.py). */
const FATORES: Record<string, string> = {
  secao_cnae: "Setor (CNAE)",
  faixa_idade: "Idade do negócio",
  log_valor_usd: "Valor do crédito",
  ajuste_porte_br: "Ajuste Brasil · porte",
  ajuste_uf_br: "Ajuste Brasil · UF",
};

/** Rótulo legível do fator; laudos de modelos antigos caem no nome técnico. */
export function rotuloFator(nome: string) {
  return FATORES[nome] ?? nome;
}

/** Rótulos das finalidades de agents/finalidades.py (vocabulário fechado). */
const FINALIDADES: Record<string, string> = {
  capital_de_giro: "Capital de giro",
  estoque: "Estoque",
  refinanciamento: "Refinanciamento",
  maquinas_equipamentos: "Máquinas e equipamentos",
  veiculos: "Veículos",
  obras_reforma: "Obras e reforma",
  tecnologia: "Tecnologia",
  expansao: "Expansão",
  abertura_de_empresa: "Abertura de empresa",
};

/** "Máquinas e equipamentos — forno industrial"; laudos antigos (texto livre) caem no slug. */
export function finalidade(codigo?: string | null, detalhe?: string | null) {
  if (!codigo) return "—";
  const rotulo = FINALIDADES[codigo] ?? capitalizar(codigo);
  return detalhe ? `${rotulo} — ${detalhe}` : rotulo;
}

export function capitalizar(s?: string | null) {
  if (!s) return "—";
  const t = s.replaceAll("_", " "); // setores vêm como slug (saude_servicos_sociais)
  return t.charAt(0).toUpperCase() + t.slice(1);
}
