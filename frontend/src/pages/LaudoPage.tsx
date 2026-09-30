import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import {
  ArrowLeft,
  Check,
  CheckCircle2,
  Copy,
  FileText,
  Link2,
  PencilLine,
  ShieldCheck,
  SlidersHorizontal,
  XCircle,
} from "lucide-react";
import { Container } from "../components/Layout";
import { AnimatedNumber } from "../components/AnimatedNumber";
import { Aviso, Button, ButtonLink, Card, Eyebrow, FaixaBadge, Skeleton, StatusBadge, cx } from "../components/ui";
import { api, chaveApi, detalheErro, guardarChave, type Decisao, type Laudo } from "../lib/api";
import { LIMITES_FAIXA, capitalizar, dataCurta, finalidade, fmtNum, moeda, rotuloFator } from "../lib/format";

type Carga = { tipo: "carregando" } | { tipo: "nao-encontrado" } | { tipo: "erro"; status: number } | { tipo: "ok"; laudo: Laudo };

export function LaudoPage() {
  const { id = "" } = useParams();
  const [carga, setCarga] = useState<Carga>({ tipo: "carregando" });

  const carregar = useCallback(async () => {
    try {
      const r = await api.obter(id);
      if (r.status === 404) setCarga({ tipo: "nao-encontrado" });
      else if (!r.ok || !r.corpo) setCarga({ tipo: "erro", status: r.status });
      else setCarga({ tipo: "ok", laudo: r.corpo });
    } catch {
      setCarga({ tipo: "erro", status: 0 });
    }
  }, [id]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  return (
    <Container className="py-10 sm:py-14">
      <ButtonLink to="/laudos" variante="fantasma" tamanho="sm" className="-ml-3">
        <ArrowLeft className="size-4" /> Todos os laudos
      </ButtonLink>
      <div className="mt-6">
        {carga.tipo === "carregando" && <Carregando />}
        {carga.tipo === "nao-encontrado" && (
          <Aviso titulo="Laudo não encontrado">
            <p className="font-mono">{id}</p>
          </Aviso>
        )}
        {carga.tipo === "erro" && (
          <Aviso titulo="Falha ao carregar o laudo">
            <p>{carga.status ? `A API respondeu HTTP ${carga.status}.` : "Sem conexão com a API."}</p>
          </Aviso>
        )}
        {carga.tipo === "ok" && <Detalhe laudo={carga.laudo} aoDecidir={carregar} />}
      </div>
    </Container>
  );
}

function Detalhe({ laudo, aoDecidir }: { laudo: Laudo; aoDecidir: () => void }) {
  const pedido = laudo.enriquecidos?.extraidos?.pedido ?? {};
  const modelo = laudo.resultado_modelo ?? {};

  return (
    <>
      <Cabecalho laudo={laudo} />

      <div className="mt-8 grid items-start gap-6 lg:grid-cols-[22rem_1fr]">
        <aside className="space-y-4 lg:sticky lg:top-24">
          <CartaoPd pd={modelo.pd} faixa={modelo.faixa_risco} versao={modelo.model_version} />
          <p className="px-1 text-xs leading-relaxed text-faint">
            Demonstração de método: o modelo foi treinado em empréstimos a pequenas empresas dos EUA (SBA 7(a)) e
            ajustado ao risco relativo brasileiro de porte e UF (SCR.data). Não use esta PD para decidir crédito.
          </p>
          <Card className="p-5">
            <h2 className="text-sm font-semibold">Pedido extraído</h2>
            <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-4 text-sm">
              <Campo rotulo="Setor" valor={capitalizar(pedido.setor)} />
              <Campo rotulo="Porte" valor={pedido.porte || "—"} />
              <Campo rotulo="UF" valor={pedido.uf || "—"} />
              <Campo rotulo="Operação" valor={pedido.anos_operacao != null ? `${pedido.anos_operacao} anos` : "—"} />
              <Campo rotulo="Faturamento anual" valor={moeda(pedido.faturamento_anual_declarado)} mono />
              <Campo rotulo="Valor solicitado" valor={moeda(pedido.valor_solicitado)} mono />
              <Campo rotulo="Prazo" valor={pedido.prazo_meses != null ? `${pedido.prazo_meses} meses` : "—"} />
              <Campo
                rotulo="Finalidade"
                valor={finalidade(pedido.finalidade, pedido.finalidade_detalhe)}
                className="col-span-2"
              />
            </dl>
          </Card>
        </aside>

        <div className="min-w-0 space-y-6">
          <Secao Icone={FileText} titulo="Laudo de risco">
            <div className="max-w-[72ch] text-[15px] leading-[1.75] whitespace-pre-wrap text-ink/90">
              {laudo.texto || <span className="text-muted">Sem texto.</span>}
            </div>
          </Secao>

          <Secao Icone={Link2} titulo="Evidências" contador={laudo.evidencias?.length}>
            {laudo.evidencias?.length ? (
              <ol className="space-y-2">
                {laudo.evidencias.map((e, i) => (
                  <motion.li
                    key={i}
                    initial={{ opacity: 0, x: -6 }}
                    whileInView={{ opacity: 1, x: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: Math.min(i, 8) * 0.04 }}
                    className="flex gap-3 rounded-xl border border-line bg-surface-2/60 p-3 text-sm"
                  >
                    <span className="num grid size-6 shrink-0 place-items-center rounded-md bg-accent-soft text-[11px] text-accent">
                      {i + 1}
                    </span>
                    <span className="min-w-0 leading-relaxed break-words text-muted">{e}</span>
                  </motion.li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted">Sem evidências registradas.</p>
            )}
          </Secao>

          <Secao Icone={SlidersHorizontal} titulo="Fatores do modelo" contador={modelo.fatores?.length}>
            <Fatores fatores={modelo.fatores ?? []} />
          </Secao>

          {laudo.status === "pendente" ? (
            <PortaoHumano laudoId={laudo.laudo_id} aoDecidir={aoDecidir} />
          ) : (
            <DecisaoRegistrada laudo={laudo} />
          )}
        </div>
      </div>
    </>
  );
}

function Cabecalho({ laudo }: { laudo: Laudo }) {
  const [copiado, setCopiado] = useState(false);
  async function copiar() {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopiado(true);
      setTimeout(() => setCopiado(false), 1600);
    } catch {
      /* clipboard bloqueado: sem feedback */
    }
  }
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2.5">
          <Eyebrow>Laudo</Eyebrow>
          <StatusBadge status={laudo.status} />
        </div>
        <h1 className="mt-2 truncate font-mono text-xl font-medium tracking-tight sm:text-2xl">{laudo.laudo_id}</h1>
        <p className="mt-1 text-sm text-muted">Criado em {dataCurta(laudo.criado_em)}</p>
      </div>
      <Button variante="secundario" tamanho="sm" onClick={copiar} aria-live="polite">
        {copiado ? <Check className="size-4 text-accent" /> : <Copy className="size-4" />}
        {copiado ? "Link copiado" : "Copiar link"}
      </Button>
    </div>
  );
}

const ESCALA_MAX = 0.4;

function CartaoPd({ pd, faixa, versao }: { pd?: number; faixa?: string; versao?: string }) {
  const temPd = typeof pd === "number";
  const posicao = temPd ? Math.min(1, pd / ESCALA_MAX) * 100 : 0;
  const trechos = [
    { ate: LIMITES_FAIXA.baixo, cor: "bg-baixo" },
    { ate: LIMITES_FAIXA.medio, cor: "bg-medio" },
    { ate: LIMITES_FAIXA.alto, cor: "bg-alto" },
    { ate: ESCALA_MAX, cor: "bg-alto/60" },
  ];
  let inicio = 0;

  return (
    <Card className="relative overflow-hidden p-6">
      <div aria-hidden className="absolute -top-24 -right-24 size-56 rounded-full bg-[radial-gradient(closest-side,var(--c-glow),transparent)]" />
      <Eyebrow>Probabilidade de default</Eyebrow>
      <div className="mt-3 flex items-baseline gap-2">
        {temPd ? (
          <AnimatedNumber
            valor={pd * 100}
            formatar={(n) => `${fmtNum.format(Number(n.toFixed(2)))}%`}
            duracao={1.4}
            className="num text-6xl font-medium tracking-[-0.04em]"
          />
        ) : (
          <span className="num text-6xl text-muted">—</span>
        )}
      </div>
      <FaixaBadge faixa={faixa} className="mt-3" />

      {temPd && (
        <div className="mt-7">
          <div className="relative">
            <div className="flex h-2 gap-0.5 overflow-hidden rounded-full">
              {trechos.map(({ ate, cor }) => {
                const largura = ((ate - inicio) / ESCALA_MAX) * 100;
                inicio = ate;
                return <span key={ate} className={cx("h-full opacity-80", cor)} style={{ width: `${largura}%` }} />;
              })}
            </div>
            <motion.span
              initial={{ left: "0%" }}
              animate={{ left: `${posicao}%` }}
              transition={{ duration: 1.4, ease: [0.16, 1, 0.3, 1] }}
              className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-[3px] border-[var(--c-solid)] bg-ink shadow-lg"
              aria-hidden
            />
          </div>
          <div className="num relative mt-2 h-3 text-[10px] text-faint">
            <span className="absolute left-0">0%</span>
            {Object.values(LIMITES_FAIXA).map((l) => (
              <span key={l} className="absolute -translate-x-1/2" style={{ left: `${(l / ESCALA_MAX) * 100}%` }}>
                {fmtNum.format(l * 100)}%
              </span>
            ))}
            <span className="absolute right-0">40%+</span>
          </div>
        </div>
      )}

      <div className="mt-6 flex items-center gap-2 border-t border-line pt-4 text-xs text-muted">
        <ShieldCheck className="size-4 text-accent" />
        <span>
          Calculada pelo modelo <span className="font-mono text-ink">{versao || "—"}</span> — não pelo LLM.
        </span>
      </div>
    </Card>
  );
}

function Campo({ rotulo, valor, mono, className }: { rotulo: string; valor: string; mono?: boolean; className?: string }) {
  return (
    <div className={cx("min-w-0", className)}>
      <dt className="text-xs text-faint">{rotulo}</dt>
      <dd className={cx("mt-0.5 break-words text-ink", mono && "num")}>{valor}</dd>
    </div>
  );
}

function Secao({
  Icone,
  titulo,
  contador,
  children,
}: {
  Icone: typeof FileText;
  titulo: string;
  contador?: number;
  children: React.ReactNode;
}) {
  return (
    <Card className="p-5 sm:p-7">
      <h2 className="flex items-center gap-2.5 text-base font-semibold">
        <span className="grid size-8 place-items-center rounded-lg bg-surface-2 text-muted ring-1 ring-line">
          <Icone className="size-4" />
        </span>
        {titulo}
        {contador ? <span className="num rounded-full bg-surface-2 px-2 py-0.5 text-xs font-normal text-muted">{contador}</span> : null}
      </h2>
      <div className="mt-5">{children}</div>
    </Card>
  );
}

function Fatores({ fatores }: { fatores: [string, number][] }) {
  if (!fatores.length) return <p className="text-sm text-muted">Sem fatores atribuídos pelo modelo.</p>;
  const ordenados = [...fatores].sort((a, b) => Math.abs(Number(b[1])) - Math.abs(Number(a[1])));
  const max = Math.max(0.0001, ...ordenados.map(([, v]) => Math.abs(Number(v) || 0)));

  return (
    <div>
      <ul className="space-y-2.5">
        {ordenados.map(([nome, bruto], i) => {
          const v = Number(bruto) || 0;
          const largura = (Math.abs(v) / max) * 50;
          return (
            <li key={nome} className="group grid grid-cols-[minmax(0,11rem)_1fr_4.5rem] items-center gap-3 text-sm">
              <span className="text-xs truncate text-muted group-hover:text-ink" title={nome}>
                {rotuloFator(nome)}
              </span>
              <span className="relative h-6">
                <span className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
                <motion.span
                  initial={{ width: 0 }}
                  whileInView={{ width: `${largura}%` }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.05, duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
                  className={cx(
                    "absolute top-1/2 h-3 -translate-y-1/2",
                    v >= 0 ? "left-1/2 rounded-r bg-accent" : "right-1/2 rounded-l bg-info",
                  )}
                />
              </span>
              <span className="num text-right text-xs text-ink">
                {v > 0 ? "+" : ""}
                {fmtNum.format(v)}
              </span>
            </li>
          );
        })}
      </ul>
      <p className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-faint">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-accent" /> atribuição positiva
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-info" /> atribuição negativa
        </span>
        <span>Contribuição de cada variável para a PD, em escala logit; os ajustes Brasil vêm do SCR.data (BCB).</span>
      </p>
    </div>
  );
}

const DECISOES: { valor: Decisao; rotulo: string; Icone: typeof Check; variante: "primario" | "secundario" | "perigo" }[] = [
  { valor: "aprovado", rotulo: "Aprovar", Icone: CheckCircle2, variante: "primario" },
  { valor: "corrigido", rotulo: "Corrigir", Icone: PencilLine, variante: "secundario" },
  { valor: "rejeitado", rotulo: "Rejeitar", Icone: XCircle, variante: "perigo" },
];

function PortaoHumano({ laudoId, aoDecidir }: { laudoId: string; aoDecidir: () => void }) {
  const [autor, setAutor] = useState("");
  const [observacao, setObservacao] = useState("");
  const [chave, setChave] = useState(chaveApi);
  const [confirmando, setConfirmando] = useState<Decisao | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function decidir(decisao: Decisao) {
    if (!autor.trim()) {
      setErro("Informe quem está decidindo.");
      setConfirmando(null);
      return;
    }
    setEnviando(true);
    setErro(null);
    guardarChave(chave.trim());
    try {
      const r = await api.decidir(laudoId, decisao, autor.trim(), observacao.trim() || null);
      if (r.ok) {
        aoDecidir();
        return;
      }
      setErro(
        r.status === 401
          ? "Só analistas decidem: informe uma chave de analista válida. Visitantes podem gerar laudos, não aprová-los."
          : detalheErro(r.erro, r.status),
      );
    } catch (e) {
      setErro(e instanceof Error ? e.message : String(e));
    }
    setEnviando(false);
    setConfirmando(null);
  }

  const escolhida = DECISOES.find((d) => d.valor === confirmando);

  return (
    <section
      id="portao-humano"
      className="relative overflow-hidden rounded-2xl border border-accent/30 bg-solid p-5 shadow-card sm:p-7"
    >
      <div aria-hidden className="absolute inset-0 bg-[radial-gradient(ellipse_80%_100%_at_0%_0%,var(--c-accent-soft),transparent_60%)]" />
      <div className="relative">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-accent text-accent-ink">
            <ShieldCheck className="size-5" />
          </span>
          <div>
            <h2 className="text-lg font-semibold">Portão humano</h2>
            <p className="text-sm text-muted">
              A decisão é final e fica registrada com autor, data e observação. Só analistas com chave decidem.
            </p>
          </div>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-[1fr_1.4fr]">
          <label className="block text-sm">
            <span className="font-medium">Decidido por</span>
            <input
              required
              value={autor}
              onChange={(e) => setAutor(e.target.value)}
              placeholder="ex.: ana.souza"
              disabled={enviando}
              className="mt-1.5 h-11 w-full rounded-xl border border-line-strong bg-bg/60 px-3.5 focus:border-accent/60 focus:outline-none focus:ring-4 focus:ring-accent/10"
            />
          </label>
          <label className="block text-sm sm:col-span-2">
            <span className="font-medium">Chave de analista</span>
            <input
              type="password"
              autoComplete="off"
              value={chave}
              onChange={(e) => setChave(e.target.value)}
              placeholder="X-API-Key"
              disabled={enviando}
              className="mt-1.5 h-11 w-full rounded-xl border border-line-strong bg-bg/60 px-3.5 font-mono focus:border-accent/60 focus:outline-none focus:ring-4 focus:ring-accent/10"
            />
          </label>
          <label className="block text-sm">
            <span className="font-medium">
              Observação <span className="font-normal text-faint">(opcional)</span>
            </span>
            <input
              value={observacao}
              onChange={(e) => setObservacao(e.target.value)}
              placeholder="Justificativa curta"
              disabled={enviando}
              className="mt-1.5 h-11 w-full rounded-xl border border-line-strong bg-bg/60 px-3.5 focus:border-accent/60 focus:outline-none focus:ring-4 focus:ring-accent/10"
            />
          </label>
        </div>

        <div className="mt-6 min-h-12">
          <AnimatePresence mode="wait" initial={false}>
            {escolhida ? (
              <motion.div
                key="confirmar"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                className="flex flex-wrap items-center gap-3"
              >
                <span className="text-sm">
                  Confirmar <strong>{escolhida.rotulo.toLowerCase()}</strong>? A decisão não pode ser desfeita.
                </span>
                <Button variante={escolhida.variante} disabled={enviando} onClick={() => decidir(escolhida.valor)}>
                  <escolhida.Icone className="size-4" /> {enviando ? "Registrando…" : `Sim, ${escolhida.rotulo.toLowerCase()}`}
                </Button>
                <Button variante="fantasma" disabled={enviando} onClick={() => setConfirmando(null)}>
                  Cancelar
                </Button>
              </motion.div>
            ) : (
              <motion.div
                key="botoes"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                className="flex flex-wrap gap-3"
              >
                {DECISOES.map(({ valor, rotulo, Icone, variante }) => (
                  <Button key={valor} variante={variante} tamanho="lg" onClick={() => setConfirmando(valor)}>
                    <Icone className="size-4" /> {rotulo}
                  </Button>
                ))}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {erro && (
          <div className="mt-4">
            <Aviso titulo="Não foi possível registrar a decisão">
              <p>{erro}</p>
            </Aviso>
          </div>
        )}
      </div>
    </section>
  );
}

function DecisaoRegistrada({ laudo }: { laudo: Laudo }) {
  return (
    <motion.section initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }}>
      <Card className="p-5 sm:p-7">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2.5 text-base font-semibold">
            <span className="grid size-8 place-items-center rounded-lg bg-accent-soft text-accent ring-1 ring-accent/20">
              <ShieldCheck className="size-4" />
            </span>
            Decisão registrada
          </h2>
          <StatusBadge status={laudo.status} />
        </div>
        <dl className="mt-5 grid gap-4 text-sm sm:grid-cols-3">
          <Campo rotulo="Decidido por" valor={laudo.decidido_por || "—"} />
          <Campo rotulo="Quando" valor={dataCurta(laudo.decidido_em)} />
          <Campo rotulo="Observação" valor={laudo.observacao_humana || "—"} className="sm:col-span-3" />
        </dl>
      </Card>
    </motion.section>
  );
}

function Carregando() {
  return (
    <div className="grid gap-6 lg:grid-cols-[22rem_1fr]" aria-busy="true" aria-label="Carregando laudo">
      <div className="space-y-4">
        <Skeleton className="h-72 rounded-2xl" />
        <Skeleton className="h-64 rounded-2xl" />
      </div>
      <div className="space-y-4">
        <Skeleton className="h-80 rounded-2xl" />
        <Skeleton className="h-48 rounded-2xl" />
      </div>
    </div>
  );
}
