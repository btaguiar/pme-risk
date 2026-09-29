import { useState } from "react";
import { motion } from "motion/react";
import {
  ArrowRight,
  BadgeCheck,
  FileCheck2,
  Info,
  Quote,
  ShieldCheck,
  Sigma,
  SlidersHorizontal,
  UserCheck,
  Users,
} from "lucide-react";
import { FAIXA_ROTULO, LIMITES_FAIXA, type Faixa } from "../lib/format";
import { Container } from "../components/Layout";
import { ButtonLink, Card, Eyebrow, FaixaBadge, cx } from "../components/ui";
import { ETAPAS } from "../components/PipelineProgress";

const subir = {
  hidden: { opacity: 0, y: 18 },
  show: (i = 0) => ({ opacity: 1, y: 0, transition: { delay: 0.08 * i, duration: 0.7, ease: [0.16, 1, 0.3, 1] as const } }),
};

export function Landing() {
  return (
    <>
      <Hero />
      <PdExplicada />
      <Principios />
      <ComoFunciona />
      <ChamadaFinal />
    </>
  );
}

function Hero() {
  return (
    <section className="pt-14 pb-20 sm:pt-20 lg:pt-24 lg:pb-28">
      <Container className="grid items-center gap-14 lg:grid-cols-[1.05fr_1fr]">
        <div>
          <motion.div variants={subir} initial="hidden" animate="show" custom={0}>
            <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs text-muted backdrop-blur">
              <span className="relative flex size-2">
                <span className="absolute inset-0 animate-ping rounded-full bg-accent/60" />
                <span className="relative size-2 rounded-full bg-accent" />
              </span>
              Laudo de risco de crédito para PMEs
            </span>
          </motion.div>

          <motion.h1
            variants={subir}
            initial="hidden"
            animate="show"
            custom={1}
            className="mt-6 text-[2.6rem] leading-[1.02] font-semibold tracking-[-0.035em] sm:text-6xl lg:text-[4.4rem]"
          >
            O laudo que você pode{" "}
            <span className="font-serif text-[1.08em] font-normal italic tracking-[-0.01em] text-gradient">
              assinar embaixo.
            </span>
          </motion.h1>

          <motion.p
            variants={subir}
            initial="hidden"
            animate="show"
            custom={2}
            className="mt-6 max-w-xl text-lg leading-relaxed text-muted"
          >
            Do pedido em texto livre a um laudo com{" "}
            <a href="#o-que-e-pd" className="text-ink underline decoration-accent/50 decoration-dotted underline-offset-4 hover:decoration-accent">
              PD do modelo
            </a>
            ,{" "}
            <span className="text-ink">evidências citadas</span> e <span className="text-ink">decisão humana registrada</span>{" "}
            — em menos de um minuto.
          </motion.p>

          <motion.div variants={subir} initial="hidden" animate="show" custom={3} className="mt-9 flex flex-wrap gap-3">
            <ButtonLink to="/novo" tamanho="lg">
              Gerar um laudo <ArrowRight className="size-4" />
            </ButtonLink>
            <ButtonLink to="/laudos" variante="secundario" tamanho="lg">
              Ver painel de laudos
            </ButtonLink>
          </motion.div>

          <motion.dl
            variants={subir}
            initial="hidden"
            animate="show"
            custom={4}
            className="mt-12 grid max-w-lg grid-cols-3 gap-6 border-t border-line pt-6"
          >
            {[
              ["< 60s", "por laudo"],
              ["0", "PDs geradas por LLM"],
              ["100%", "decisões com autor"],
            ].map(([valor, rotulo]) => (
              <div key={rotulo}>
                <dt className="num text-2xl font-medium tracking-tight">{valor}</dt>
                <dd className="mt-1 text-xs text-muted">{rotulo}</dd>
              </div>
            ))}
          </motion.dl>
        </div>

        <LaudoDemo />
      </Container>
    </section>
  );
}

/** Prévia ilustrativa de um laudo — composição visual, não um laudo real. */
function LaudoDemo() {
  const fatores: [string, number][] = [
    ["anos_operacao", 0.82],
    ["margem_setor", 0.55],
    ["alavancagem_pedido", -0.47],
    ["porte", 0.31],
  ];
  return (
    <motion.div
      initial={{ opacity: 0, y: 30, rotateX: 8 }}
      animate={{ opacity: 1, y: 0, rotateX: 0 }}
      transition={{ delay: 0.25, duration: 1, ease: [0.16, 1, 0.3, 1] }}
      style={{ perspective: 1200 }}
      className="relative"
      aria-label="Exemplo ilustrativo de laudo"
    >
      <div className="absolute -inset-6 -z-10 rounded-[2rem] bg-[radial-gradient(closest-side,var(--c-glow),transparent)] blur-2xl" />
      <Card className="relative overflow-hidden p-0">
        <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
          <div className="flex items-center gap-2">
            <span className="size-2.5 rounded-full bg-alto/70" />
            <span className="size-2.5 rounded-full bg-medio/70" />
            <span className="size-2.5 rounded-full bg-baixo/70" />
          </div>
          <span className="font-mono text-xs text-faint">laudo · 7f3a2c1e</span>
        </div>

        <div className="grid gap-5 p-5 sm:grid-cols-[auto_1fr] sm:p-6">
          <div className="rounded-xl border border-line bg-surface-2 p-4 sm:w-44">
            <Eyebrow>PD · modelo</Eyebrow>
            <p className="num mt-2 text-4xl font-medium tracking-tight">3,8%</p>
            <FaixaBadge faixa="baixo" className="mt-3" />
            <div className="mt-4 space-y-1.5 text-xs text-muted">
              <p className="flex justify-between"><span>Setor</span><span className="text-ink">Saúde</span></p>
              <p className="flex justify-between"><span>Porte</span><span className="text-ink">ME</span></p>
              <p className="flex justify-between"><span>Pedido</span><span className="num text-ink">R$ 300 mil</span></p>
            </div>
          </div>

          <div className="min-w-0 space-y-4">
            <div>
              <Eyebrow>Fatores do modelo</Eyebrow>
              <ul className="mt-3 space-y-2.5">
                {fatores.map(([nome, v], i) => (
                  <li key={nome} className="grid grid-cols-[1fr_5.5rem] items-center gap-3 text-xs">
                    <span className="font-mono truncate text-muted">{nome}</span>
                    <span className="h-1.5 overflow-hidden rounded-full bg-surface-2">
                      <motion.span
                        className={cx("block h-full rounded-full", v > 0 ? "bg-accent" : "bg-info")}
                        initial={{ width: 0 }}
                        animate={{ width: `${Math.abs(v) * 100}%` }}
                        transition={{ delay: 0.8 + i * 0.12, duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
                      />
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-xl border border-line bg-surface p-3 text-xs leading-relaxed text-muted">
              <Quote className="mb-1 size-3.5 text-accent" />
              Empresa com 5 anos de operação no setor de saúde; faturamento declarado compatível com o porte
              <sup className="num ml-0.5 text-accent">[1]</sup>, pedido equivalente a 15% da receita anual
              <sup className="num ml-0.5 text-accent">[2]</sup>.
            </div>
          </div>
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-line bg-surface px-5 py-3.5">
          <span className="inline-flex items-center gap-2 text-xs text-muted">
            <UserCheck className="size-4 text-info" /> Aguardando portão humano
          </span>
          <span className="inline-flex gap-1.5">
            <span className="rounded-md bg-accent px-2.5 py-1 text-[11px] font-medium text-accent-ink">Aprovar</span>
            <span className="rounded-md border border-line-strong px-2.5 py-1 text-[11px] text-muted">Corrigir</span>
          </span>
        </div>
      </Card>

      <motion.div
        initial={{ opacity: 0, scale: 0.9, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ delay: 1.3, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        className="glass absolute -bottom-6 -left-4 hidden items-center gap-3 px-4 py-3 sm:flex"
      >
        <span className="grid size-9 place-items-center rounded-lg bg-accent-soft text-accent">
          <BadgeCheck className="size-5" />
        </span>
        <div className="text-xs">
          <p className="font-medium text-ink">12 evidências citadas</p>
          <p className="text-muted">verificado × declarado</p>
        </div>
      </motion.div>
      <p className="mt-10 text-center text-[11px] text-faint sm:mt-12">Exemplo ilustrativo</p>
    </motion.div>
  );
}

const FAIXAS_PD: { faixa: Faixa; intervalo: string; em100: string; cor: string }[] = [
  { faixa: "baixo", intervalo: "abaixo de 5%", em100: "menos de 5 em 100", cor: "bg-baixo" },
  { faixa: "medio", intervalo: "de 5% a 15%", em100: "de 5 a 15 em 100", cor: "bg-medio" },
  { faixa: "alto", intervalo: "de 15% a 30%", em100: "de 15 a 30 em 100", cor: "bg-alto" },
  { faixa: "muito_alto", intervalo: "30% ou mais", em100: "30 ou mais em 100", cor: "bg-alto" },
];

function faixaDaPd(pd: number): Faixa {
  if (pd < LIMITES_FAIXA.baixo) return "baixo";
  if (pd < LIMITES_FAIXA.medio) return "medio";
  if (pd < LIMITES_FAIXA.alto) return "alto";
  return "muito_alto";
}

/** "O que é PD?" — simulador: arraste a PD e veja quantas de 100 empresas tendem a não pagar. */
function PdExplicada() {
  const [pd, setPd] = useState(7.5);
  const faixa = faixaDaPd(pd / 100);
  const emCem = Math.round(pd);
  const cor = FAIXAS_PD.find((f) => f.faixa === faixa)!.cor;

  return (
    <section id="o-que-e-pd" className="scroll-mt-20 py-20 sm:py-24">
      <Container>
        <div className="grid items-center gap-12 lg:grid-cols-[1fr_1.05fr]">
          <div>
            <Eyebrow>
              <Info className="size-3.5 text-accent" /> Entenda o número principal
            </Eyebrow>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">
              O que é <span className="font-serif font-normal italic text-gradient">PD</span>?
            </h2>
            <p className="mt-5 text-lg leading-relaxed text-muted">
              <strong className="font-semibold text-ink">PD é a Probabilidade de Default</strong> — a chance estimada de a
              empresa <span className="text-ink">não pagar</span> o crédito. É o número central de todo laudo do Aval.
            </p>
            <ul className="mt-6 space-y-3.5 text-sm leading-relaxed text-muted">
              <li className="flex gap-3">
                <Users className="mt-0.5 size-4 shrink-0 text-accent" />
                <span>
                  <span className="text-ink">Leia como frequência:</span> PD de 7% significa que, de cada 100 empresas com o
                  mesmo perfil, cerca de 7 tendem a não pagar.
                </span>
              </li>
              <li className="flex gap-3">
                <Sigma className="mt-0.5 size-4 shrink-0 text-accent" />
                <span>
                  <span className="text-ink">Quem calcula é o modelo estatístico</span>, a partir de setor, porte, tempo de
                  operação, faturamento, valor e prazo. O LLM nunca gera nem altera a PD.
                </span>
              </li>
              <li className="flex gap-3">
                <SlidersHorizontal className="mt-0.5 size-4 shrink-0 text-accent" />
                <span>
                  <span className="text-ink">A PD define a faixa de risco</span> do laudo — e é uma estimativa estatística
                  sobre um perfil, não uma certeza sobre uma empresa específica. Por isso a decisão final é humana.
                </span>
              </li>
            </ul>
          </div>

          <Card className="p-6 sm:p-8">
            <div className="flex items-start justify-between gap-4">
              <div>
                <label htmlFor="simulador-pd" className="text-sm font-medium">
                  Simule uma PD
                </label>
                <p className="mt-0.5 text-xs text-muted">Arraste para ver o que o número significa.</p>
              </div>
              <div className="text-right">
                <p className="num text-4xl font-medium tracking-tight">{pd.toLocaleString("pt-BR", { minimumFractionDigits: 1 })}%</p>
                <FaixaBadge faixa={faixa} className="mt-1.5" />
              </div>
            </div>

            <input
              id="simulador-pd"
              type="range"
              min={0.5}
              max={40}
              step={0.5}
              value={pd}
              onChange={(e) => setPd(Number(e.target.value))}
              aria-valuetext={`${pd}% — ${FAIXA_ROTULO[faixa]}`}
              className="mt-6 w-full cursor-pointer accent-[var(--c-accent)]"
            />

            <div className="mx-auto mt-6 grid max-w-[300px] grid-cols-10 gap-1.5 sm:gap-2" role="img" aria-label={`${emCem} de 100 empresas`}>
              {Array.from({ length: 100 }, (_, i) => (
                <span
                  key={i}
                  className={cx(
                    "aspect-square rounded-full transition-all duration-300",
                    i < emCem ? cx(cor, "scale-100") : "scale-75 bg-surface-2 ring-1 ring-line",
                  )}
                  style={{ transitionDelay: `${(i % 10) * 8}ms` }}
                />
              ))}
            </div>
            <p className="mt-5 text-sm text-muted">
              De cada <span className="text-ink">100 empresas</span> com este perfil, cerca de{" "}
              <span className="num font-semibold text-ink">{emCem}</span> tendem a não pagar o crédito.
            </p>
          </Card>
        </div>

        <div className="mt-12 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {FAIXAS_PD.map((f) => (
            <button
              key={f.faixa}
              type="button"
              onClick={() => setPd({ baixo: 3, medio: 9, alto: 22, muito_alto: 34 }[f.faixa])}
              className={cx(
                "glass p-4 text-left transition-colors hover:border-line-strong",
                faixa === f.faixa && "border-line-strong bg-surface-2",
              )}
            >
              <span className={cx("block h-1 w-10 rounded-full", f.cor, f.faixa === "muito_alto" && "ring-2 ring-alto/40")} />
              <p className="mt-3 text-sm font-semibold">{FAIXA_ROTULO[f.faixa]}</p>
              <p className="num mt-1 text-xs text-muted">PD {f.intervalo}</p>
              <p className="mt-0.5 text-xs text-faint">{f.em100} tendem a não pagar</p>
            </button>
          ))}
        </div>
      </Container>
    </section>
  );
}

const PRINCIPIOS = [
  {
    Icone: Sigma,
    titulo: "PD vem do modelo, nunca do LLM",
    texto:
      "A probabilidade de default sai de um modelo estatístico versionado. O LLM só lê o pedido e redige — e é proibido de alterar números.",
  },
  {
    Icone: FileCheck2,
    titulo: "Toda afirmação carrega evidência",
    texto:
      "Cada frase do laudo aponta para a fonte: dado verificado em base pública ou premissa declarada pelo cliente. Nada fica sem lastro.",
  },
  {
    Icone: ShieldCheck,
    titulo: "A decisão final é humana",
    texto:
      "Nenhum laudo sai sem um analista aprovar, corrigir ou rejeitar. Autor, data e justificativa ficam na trilha de auditoria.",
  },
];

function Principios() {
  return (
    <section className="py-20 sm:py-24">
      <Container>
        <div className="max-w-2xl">
          <Eyebrow>Por que confiar</Eyebrow>
          <h2 className="mt-3 text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">
            IA onde ela ajuda.{" "}
            <span className="font-serif font-normal italic text-muted">Controle onde importa.</span>
          </h2>
        </div>
        <div className="mt-12 grid gap-4 md:grid-cols-3">
          {PRINCIPIOS.map(({ Icone, titulo, texto }, i) => (
            <motion.div
              key={titulo}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-80px" }}
              transition={{ delay: i * 0.1, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            >
              <Card className="group h-full p-6 transition-colors hover:border-line-strong">
                <span className="grid size-11 place-items-center rounded-xl bg-accent-soft text-accent ring-1 ring-accent/20 transition-transform duration-300 group-hover:scale-110">
                  <Icone className="size-5" />
                </span>
                <h3 className="mt-5 text-lg font-semibold tracking-tight">{titulo}</h3>
                <p className="mt-2 text-sm leading-relaxed text-muted">{texto}</p>
              </Card>
            </motion.div>
          ))}
        </div>
      </Container>
    </section>
  );
}

function ComoFunciona() {
  return (
    <section className="border-y border-line bg-bg-2/60 py-20 sm:py-24">
      <Container>
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div className="max-w-2xl">
            <Eyebrow>Como funciona</Eyebrow>
            <h2 className="mt-3 text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">
              Cinco etapas, uma trilha auditável.
            </h2>
          </div>
          <p className="max-w-sm text-sm text-muted">
            Agentes especializados fazem o trabalho pesado; cada passo deixa registro para quem revisar depois.
          </p>
        </div>

        <ol className="relative mt-14 grid gap-4 md:grid-cols-5">
          <div aria-hidden className="absolute top-7 right-[10%] left-[10%] hidden h-px bg-gradient-to-r from-transparent via-line-strong to-transparent md:block" />
          {ETAPAS.map(({ Icone, titulo, descricao }, i) => (
            <motion.li
              key={titulo}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: "-60px" }}
              transition={{ delay: i * 0.08, duration: 0.5 }}
              className="relative"
            >
              <span
                className={cx(
                  "relative grid size-14 place-items-center rounded-2xl border bg-solid",
                  i === ETAPAS.length - 1 ? "border-accent/40 text-accent" : "border-line-strong text-ink",
                )}
              >
                <Icone className="size-5" />
                <span className="num absolute -top-2 -right-2 grid size-5 place-items-center rounded-full bg-surface-2 text-[10px] text-muted ring-1 ring-line">
                  {i + 1}
                </span>
              </span>
              <h3 className="mt-5 font-semibold">{titulo}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-muted">{descricao}</p>
            </motion.li>
          ))}
        </ol>
      </Container>
    </section>
  );
}

function ChamadaFinal() {
  return (
    <section className="py-20 sm:py-28">
      <Container>
        <div className="relative overflow-hidden rounded-3xl border border-line bg-solid px-6 py-14 text-center sm:px-12 sm:py-20">
          <div aria-hidden className="absolute inset-0 bg-[radial-gradient(ellipse_60%_80%_at_50%_120%,var(--c-glow),transparent)]" />
          <div aria-hidden className="grid-bg absolute inset-0 opacity-40" />
          <div className="relative">
            <h2 className="mx-auto max-w-3xl text-3xl font-semibold tracking-[-0.03em] sm:text-5xl">
              Descreva o pedido.{" "}
              <span className="font-serif font-normal italic text-gradient">O Aval faz o resto.</span>
            </h2>
            <p className="mx-auto mt-5 max-w-lg text-muted">
              Escreva em português, como no e-mail do gerente. Campos ambíguos viram premissas citadas no laudo.
            </p>
            <div className="mt-9 flex justify-center">
              <ButtonLink to="/novo" tamanho="lg">
                Gerar meu primeiro laudo <ArrowRight className="size-4" />
              </ButtonLink>
            </div>
          </div>
        </div>
      </Container>
    </section>
  );
}
