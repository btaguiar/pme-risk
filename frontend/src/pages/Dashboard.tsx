import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { motion } from "motion/react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Activity, ArrowUpRight, CheckCircle2, FilePlus2, Files, Hourglass, Inbox, Search } from "lucide-react";
import { Container } from "../components/Layout";
import { AnimatedNumber } from "../components/AnimatedNumber";
import { Aviso, ButtonLink, Card, Eyebrow, FaixaBadge, Skeleton, StatusBadge, cx } from "../components/ui";
import { api, type LaudoResumo } from "../lib/api";
import {
  FAIXA_ROTULO,
  LIMITES_FAIXA,
  STATUS_ROTULO,
  capitalizar,
  classeFaixa,
  dataCurta,
  dia,
  idCurto,
  moeda,
  percentual,
  type Faixa,
} from "../lib/format";

type Carga = { tipo: "carregando" } | { tipo: "erro"; status: number } | { tipo: "ok"; laudos: LaudoResumo[] };

const FAIXAS: Faixa[] = ["baixo", "medio", "alto", "muito_alto"];
const COR_FAIXA: Record<Faixa, string> = {
  baixo: "var(--c-baixo)",
  medio: "var(--c-medio)",
  alto: "var(--c-alto)",
  muito_alto: "color-mix(in oklab, var(--c-alto) 70%, black)",
};
const FILTROS = ["todos", "pendente", "aprovado", "corrigido", "rejeitado"] as const;

const fmtPct = (n: number) => `${n.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
const fmtInt = (n: number) => Math.round(n).toLocaleString("pt-BR");

export function Dashboard() {
  const [carga, setCarga] = useState<Carga>({ tipo: "carregando" });

  useEffect(() => {
    let vivo = true;
    api
      .listar(50)
      .then((r) => vivo && setCarga(r.ok ? { tipo: "ok", laudos: r.corpo ?? [] } : { tipo: "erro", status: r.status }))
      .catch(() => vivo && setCarga({ tipo: "erro", status: 0 }));
    return () => {
      vivo = false;
    };
  }, []);

  return (
    <Container className="py-12 sm:py-16">
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <Eyebrow>
            <Activity className="size-3.5 text-accent" /> Painel
          </Eyebrow>
          <h1 className="mt-3 text-4xl font-semibold tracking-[-0.035em] sm:text-5xl">Laudos</h1>
          <p className="mt-3 text-muted">
            {carga.tipo === "ok"
              ? `Visão dos ${carga.laudos.length} laudos mais recentes.`
              : "Visão dos laudos mais recentes."}
          </p>
        </div>
        <ButtonLink to="/novo">
          <FilePlus2 className="size-4" /> Novo laudo
        </ButtonLink>
      </div>

      <div className="mt-10">
        {carga.tipo === "carregando" && <Carregando />}
        {carga.tipo === "erro" && (
          <Aviso titulo="Não foi possível listar os laudos">
            <p>{carga.status ? `A API respondeu HTTP ${carga.status}.` : "Sem conexão com a API."}</p>
          </Aviso>
        )}
        {carga.tipo === "ok" && (carga.laudos.length ? <Painel laudos={carga.laudos} /> : <Vazio />)}
      </div>
    </Container>
  );
}

function Painel({ laudos }: { laudos: LaudoResumo[] }) {
  const kpis = useMemo(() => {
    const comPd = laudos.filter((l) => typeof l.pd === "number");
    const pdMedia = comPd.length ? comPd.reduce((s, l) => s + (l.pd as number), 0) / comPd.length : 0;
    const pendentes = laudos.filter((l) => l.status === "pendente").length;
    const decididos = laudos.length - pendentes;
    const aprovados = laudos.filter((l) => l.status === "aprovado").length;
    const volume = laudos.reduce((s, l) => s + (l.pedido?.valor_solicitado ?? 0), 0);
    return { pdMedia, pendentes, decididos, aprovados, volume };
  }, [laudos]);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 sm:gap-4">
        <Kpi i={0} Icone={Files} rotulo="Laudos" valor={laudos.length} formatar={fmtInt} nota={`${moeda(kpis.volume, true)} solicitados`} />
        <Kpi i={1} Icone={Activity} rotulo="PD média" valor={kpis.pdMedia * 100} formatar={fmtPct} nota="saída do modelo" />
        <Kpi
          i={2}
          Icone={Hourglass}
          rotulo="Aguardando decisão"
          valor={kpis.pendentes}
          formatar={fmtInt}
          nota="no portão humano"
          destaque={kpis.pendentes > 0}
        />
        <Kpi
          i={3}
          Icone={CheckCircle2}
          rotulo="Taxa de aprovação"
          valor={kpis.decididos ? (kpis.aprovados / kpis.decididos) * 100 : 0}
          formatar={fmtPct}
          nota={`${kpis.aprovados} de ${kpis.decididos} decididos`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <GraficoPd laudos={laudos} />
        <div className="grid gap-4">
          <DistribuicaoFaixa laudos={laudos} />
          <PorSetor laudos={laudos} />
        </div>
      </div>

      <Tabela laudos={laudos} />
    </div>
  );
}

function Kpi({
  i,
  Icone,
  rotulo,
  valor,
  formatar,
  nota,
  destaque,
}: {
  i: number;
  Icone: typeof Files;
  rotulo: string;
  valor: number;
  formatar: (n: number) => string;
  nota: string;
  destaque?: boolean;
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06, duration: 0.5 }}>
      <Card className={cx("relative h-full overflow-hidden p-4 sm:p-5", destaque && "border-info/30")}>
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted sm:text-sm">{rotulo}</span>
          <Icone className={cx("size-4", destaque ? "text-info" : "text-faint")} />
        </div>
        <AnimatedNumber valor={valor} formatar={formatar} className="num mt-3 block text-3xl font-medium tracking-tight sm:text-4xl" />
        <p className="mt-1.5 truncate text-xs text-faint">{nota}</p>
      </Card>
    </motion.div>
  );
}

function CardGrafico({ titulo, subtitulo, children, className }: { titulo: string; subtitulo?: string; children: React.ReactNode; className?: string }) {
  return (
    <Card className={cx("flex flex-col p-5", className)}>
      <h2 className="text-sm font-semibold">{titulo}</h2>
      {subtitulo && <p className="mt-0.5 text-xs text-muted">{subtitulo}</p>}
      <div className="mt-4 flex flex-1 flex-col">{children}</div>
    </Card>
  );
}

function DicaGrafico({ active, payload }: { active?: boolean; payload?: { payload: Record<string, unknown> }[] }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload as { titulo?: string; linhas?: [string, string][] };
  return (
    <div className="rounded-lg border border-line-strong bg-solid px-3 py-2 text-xs shadow-card">
      {p.titulo && <p className="mb-1 font-medium text-ink">{p.titulo}</p>}
      {p.linhas?.map(([k, v]) => (
        <p key={k} className="flex justify-between gap-4 text-muted">
          <span>{k}</span>
          <span className="num text-ink">{v}</span>
        </p>
      ))}
    </div>
  );
}

function GraficoPd({ laudos }: { laudos: LaudoResumo[] }) {
  const dados = useMemo(
    () =>
      laudos
        .filter((l) => typeof l.pd === "number" && l.criado_em)
        .sort((a, b) => String(a.criado_em).localeCompare(String(b.criado_em)))
        .map((l, i) => ({
          i,
          pd: (l.pd as number) * 100,
          dia: dia(l.criado_em),
          titulo: `${capitalizar(l.pedido?.setor)} · ${l.pedido?.uf || "—"}`,
          linhas: [
            ["PD", percentual(l.pd)],
            ["Faixa", FAIXA_ROTULO[classeFaixa(l.faixa_risco)]],
            ["Criado", dataCurta(l.criado_em)],
          ] as [string, string][],
        })),
    [laudos],
  );

  return (
    <CardGrafico titulo="PD por laudo" subtitulo="Em ordem de criação · linhas tracejadas marcam as faixas de risco (5%, 15%, 30%)">
      <div className="h-72 lg:h-auto lg:min-h-72 lg:flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={dados} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
            <defs>
              <linearGradient id="pd-area" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--c-accent)" stopOpacity={0.28} />
                <stop offset="100%" stopColor="var(--c-accent)" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} stroke="var(--c-line)" />
            <XAxis dataKey="dia" tickLine={false} axisLine={false} tick={{ fill: "var(--c-faint)", fontSize: 11 }} minTickGap={24} />
            <YAxis
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--c-faint)", fontSize: 11 }}
              tickFormatter={(v: number) => `${v}%`}
              width={48}
            />
            {Object.values(LIMITES_FAIXA).map((l) => (
              <ReferenceLine key={l} y={l * 100} stroke="var(--c-line-strong)" strokeDasharray="4 4" />
            ))}
            <Tooltip content={<DicaGrafico />} cursor={{ stroke: "var(--c-line-strong)" }} />
            <Area
              type="monotone"
              dataKey="pd"
              stroke="var(--c-accent)"
              strokeWidth={2}
              fill="url(#pd-area)"
              dot={dados.length <= 20 ? { r: 3, fill: "var(--c-accent)", stroke: "var(--c-solid)", strokeWidth: 2 } : false}
              activeDot={{ r: 5, fill: "var(--c-accent)", stroke: "var(--c-solid)", strokeWidth: 2 }}
              animationDuration={1200}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </CardGrafico>
  );
}

function DistribuicaoFaixa({ laudos }: { laudos: LaudoResumo[] }) {
  const contagem = useMemo(() => {
    const c: Record<Faixa, number> = { baixo: 0, medio: 0, alto: 0, muito_alto: 0 };
    laudos.forEach((l) => l.faixa_risco && c[classeFaixa(l.faixa_risco)]++);
    return c;
  }, [laudos]);
  const total = Object.values(contagem).reduce((a, b) => a + b, 0) || 1;
  const visiveis = FAIXAS.filter((f) => contagem[f] > 0 || f !== "muito_alto");

  return (
    <CardGrafico titulo="Distribuição por faixa de risco">
      <div className="flex h-3 gap-0.5 overflow-hidden rounded-full" role="img" aria-label="Distribuição por faixa">
        {visiveis.map((f) =>
          contagem[f] ? (
            <motion.span
              key={f}
              title={`${FAIXA_ROTULO[f]}: ${contagem[f]}`}
              initial={{ width: 0 }}
              animate={{ width: `${(contagem[f] / total) * 100}%` }}
              transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
              style={{ background: COR_FAIXA[f] }}
              className="h-full first:rounded-l-full last:rounded-r-full"
            />
          ) : null,
        )}
      </div>
      <ul className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2.5">
        {visiveis.map((f) => (
          <li key={f} className="flex items-center justify-between gap-2 text-sm">
            <span className="flex items-center gap-2 text-muted">
              <span className="size-2.5 rounded-sm" style={{ background: COR_FAIXA[f] }} />
              {FAIXA_ROTULO[f].replace("Risco ", "")}
            </span>
            <span className="num text-ink">
              {contagem[f]} <span className="text-faint">· {Math.round((contagem[f] / total) * 100)}%</span>
            </span>
          </li>
        ))}
      </ul>
    </CardGrafico>
  );
}

function PorSetor({ laudos }: { laudos: LaudoResumo[] }) {
  const dados = useMemo(() => {
    const m = new Map<string, number>();
    laudos.forEach((l) => {
      const s = capitalizar(l.pedido?.setor);
      m.set(s, (m.get(s) ?? 0) + 1);
    });
    return [...m.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 5)
      .map(([setor, n]) => ({ setor, n, titulo: setor, linhas: [["Laudos", String(n)]] as [string, string][] }));
  }, [laudos]);

  return (
    <CardGrafico titulo="Laudos por setor" subtitulo="Cinco setores mais frequentes">
      <div style={{ height: dados.length * 34 + 8 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={dados} layout="vertical" margin={{ top: 0, right: 28, bottom: 0, left: 0 }} barCategoryGap={6}>
            <XAxis type="number" hide />
            <YAxis
              type="category"
              dataKey="setor"
              width={110}
              tickLine={false}
              axisLine={false}
              tick={{ fill: "var(--c-muted)", fontSize: 12 }}
            />
            <Tooltip content={<DicaGrafico />} cursor={{ fill: "var(--c-surface-2)" }} />
            <Bar
              dataKey="n"
              fill="var(--c-accent)"
              radius={[0, 4, 4, 0]}
              label={{ position: "right", fill: "var(--c-muted)", fontSize: 11 }}
              animationDuration={900}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </CardGrafico>
  );
}

function Tabela({ laudos }: { laudos: LaudoResumo[] }) {
  const navegar = useNavigate();
  const [busca, setBusca] = useState("");
  const [filtro, setFiltro] = useState<(typeof FILTROS)[number]>("todos");

  const linhas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    return laudos.filter((l) => {
      if (filtro !== "todos" && l.status !== filtro) return false;
      if (!q) return true;
      return [l.laudo_id, l.pedido?.setor, l.pedido?.uf, l.pedido?.porte, l.decidido_por]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q));
    });
  }, [laudos, busca, filtro]);

  return (
    <Card className="overflow-hidden p-0">
      <div className="flex flex-col gap-3 border-b border-line p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap gap-1">
          {FILTROS.map((f) => (
            <button
              key={f}
              type="button"
              onClick={() => setFiltro(f)}
              className={cx(
                "rounded-lg px-3 py-1.5 text-xs font-medium transition-colors",
                filtro === f ? "bg-surface-2 text-ink ring-1 ring-line-strong" : "text-muted hover:text-ink",
              )}
            >
              {f === "todos" ? "Todos" : STATUS_ROTULO[f]}
              <span className="num ml-1.5 text-faint">
                {f === "todos" ? laudos.length : laudos.filter((l) => l.status === f).length}
              </span>
            </button>
          ))}
        </div>
        <label className="relative block sm:w-64">
          <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-faint" />
          <input
            type="search"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar setor, UF, ID…"
            aria-label="Buscar laudos"
            className="h-9 w-full rounded-lg border border-line bg-bg/50 pr-3 pl-9 text-sm placeholder:text-faint focus:border-accent/60 focus:outline-none"
          />
        </label>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-sm">
          <thead>
            <tr className="text-left text-xs text-faint">
              {["Laudo", "Pedido", "Valor", "PD", "Faixa", "Status", "Criado", ""].map((h) => (
                <th key={h} className="px-4 py-3 font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {linhas.map((l) => (
              <tr
                key={l.laudo_id}
                onClick={() => navegar(`/laudos/${l.laudo_id}`)}
                className="group cursor-pointer border-t border-line transition-colors hover:bg-surface-2"
              >
                <td className="px-4 py-3.5">
                  <Link to={`/laudos/${l.laudo_id}`} className="font-mono text-xs text-muted group-hover:text-ink" onClick={(e) => e.stopPropagation()}>
                    {idCurto(l.laudo_id)}
                  </Link>
                </td>
                <td className="px-4 py-3.5">
                  <span className="text-ink">{capitalizar(l.pedido?.setor)}</span>
                  <span className="text-faint"> · {l.pedido?.porte || "—"} · {l.pedido?.uf || "—"}</span>
                </td>
                <td className="num px-4 py-3.5 text-muted">{moeda(l.pedido?.valor_solicitado, true)}</td>
                <td className="num px-4 py-3.5 font-medium">{percentual(l.pd)}</td>
                <td className="px-4 py-3.5">
                  <FaixaBadge faixa={l.faixa_risco} />
                </td>
                <td className="px-4 py-3.5">
                  <StatusBadge status={l.status} />
                </td>
                <td className="num px-4 py-3.5 text-xs whitespace-nowrap text-muted">{dataCurta(l.criado_em)}</td>
                <td className="px-4 py-3.5 text-right">
                  <ArrowUpRight className="inline size-4 text-faint transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-accent" />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!linhas.length && <p className="border-t border-line px-4 py-10 text-center text-sm text-muted">Nenhum laudo com esses filtros.</p>}
      </div>
    </Card>
  );
}

function Carregando() {
  return (
    <div className="space-y-6" aria-busy="true" aria-label="Carregando laudos">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Skeleton key={i} className="h-32 rounded-2xl" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        <Skeleton className="h-96 rounded-2xl" />
        <Skeleton className="h-96 rounded-2xl" />
      </div>
    </div>
  );
}

function Vazio() {
  return (
    <Card className="flex flex-col items-center px-6 py-20 text-center">
      <span className="grid size-14 place-items-center rounded-2xl bg-accent-soft text-accent ring-1 ring-accent/20">
        <Inbox className="size-6" />
      </span>
      <h2 className="mt-5 text-xl font-semibold">Nenhum laudo ainda</h2>
      <p className="mt-2 max-w-sm text-sm text-muted">Gere o primeiro laudo e o painel ganha vida com PD, faixas e setores.</p>
      <ButtonLink to="/novo" className="mt-6">
        <FilePlus2 className="size-4" /> Gerar primeiro laudo
      </ButtonLink>
    </Card>
  );
}
