// Cliente da API pme-risk — mesmo contrato do backend (api/routes/laudos.py).

export type Status = "pendente" | "aprovado" | "corrigido" | "rejeitado" | string;
export type Decisao = "aprovado" | "corrigido" | "rejeitado";

export interface PedidoResumo {
  setor?: string | null;
  porte?: string | null;
  uf?: string | null;
  valor_solicitado?: number | null;
}

export interface LaudoResumo {
  laudo_id: string;
  status: Status;
  criado_em?: string | null;
  decidido_em?: string | null;
  decidido_por?: string | null;
  pd?: number | null;
  faixa_risco?: string | null;
  pedido: PedidoResumo;
}

export interface Pedido extends PedidoResumo {
  anos_operacao?: number | null;
  faturamento_anual_declarado?: number | null;
  prazo_meses?: number | null;
  finalidade?: string | null;
  finalidade_detalhe?: string | null;
}

export interface Laudo {
  laudo_id: string;
  status: Status;
  enriquecidos?: { extraidos?: { pedido?: Pedido } };
  resultado_modelo?: {
    pd?: number;
    faixa_risco?: string;
    model_version?: string;
    fatores?: [string, number][];
  };
  texto?: string;
  evidencias?: string[];
  decidido_por?: string | null;
  decidido_em?: string | null;
  observacao_humana?: string | null;
  criado_em?: string | null;
}

export interface Resposta<T> {
  ok: boolean;
  status: number;
  corpo: T | null;
  erro?: unknown;
}

const CHAVE_LOCAL = "pme-risk-api-key";

export function chaveApi(): string {
  try {
    return localStorage.getItem(CHAVE_LOCAL) || "";
  } catch {
    return "";
  }
}

export function guardarChave(valor: string) {
  try {
    if (valor) localStorage.setItem(CHAVE_LOCAL, valor);
    else localStorage.removeItem(CHAVE_LOCAL);
  } catch {
    /* navegação privada: a chave vale só para esta sessão */
  }
}

async function chamar<T>(caminho: string, opcoes: RequestInit = {}): Promise<Resposta<T>> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  const chave = chaveApi();
  if (chave) headers["X-API-Key"] = chave;
  // no-store: /laudos/{id} também é URL de página — nunca reaproveitar a casca HTML do cache.
  const resposta = await fetch(caminho, { cache: "no-store", ...opcoes, headers });
  const texto = await resposta.text();
  let corpo: unknown = null;
  if (texto) {
    try {
      corpo = JSON.parse(texto);
    } catch {
      corpo = { detail: texto };
    }
  }
  const json = (resposta.headers.get("content-type") || "").includes("json");
  return resposta.ok && json
    ? { ok: true, status: resposta.status, corpo: corpo as T }
    : { ok: false, status: resposta.status, corpo: null, erro: corpo };
}

export const api = {
  listar: (limite = 50) => chamar<LaudoResumo[]>(`/laudos?limite=${limite}`),
  obter: (id: string) => chamar<Laudo>(`/laudos/${encodeURIComponent(id)}`),
  criar: (texto: string, prazo_meses: number) =>
    chamar<{ laudo_id: string; status: Status }>("/laudos", {
      method: "POST",
      body: JSON.stringify({ texto, prazo_meses }),
    }),
  decidir: (id: string, decisao: Decisao, decidido_por: string, observacao: string | null) =>
    chamar<unknown>(`/laudos/${encodeURIComponent(id)}/decisao`, {
      method: "PATCH",
      body: JSON.stringify({ decisao, decidido_por, observacao }),
    }),
};

/** Mensagem legível do corpo de erro do FastAPI ({detail: string | {motivo_recusa}}). */
export function detalheErro(erro: unknown, status: number): string {
  const detail = (erro as { detail?: unknown } | null)?.detail;
  if (typeof detail === "string") return detail;
  const motivo = (detail as { motivo_recusa?: string } | undefined)?.motivo_recusa;
  if (motivo) return motivo;
  return `HTTP ${status}`;
}
