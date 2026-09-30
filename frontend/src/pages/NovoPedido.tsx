import { useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import {
  ArrowRight,
  CalendarClock,
  Check,
  ChevronDown,
  KeyRound,
  ListChecks,
  PenLine,
  RotateCcw,
  Sparkles,
  Wand2,
} from "lucide-react";
import { Container } from "../components/Layout";
import { Aviso, Button, Card, Eyebrow, cx } from "../components/ui";
import { PipelineProgress } from "../components/PipelineProgress";
import { PedidoGuiado } from "../components/PedidoGuiado";
import { api, chaveApi, detalheErro, guardarChave } from "../lib/api";
import {
  EXEMPLOS,
  PEDIDO_VAZIO,
  checklistGuiado,
  checklistTexto,
  compor,
  guiadoCompleto,
  type DadosPedido,
  type ItemChecklist,
} from "../lib/pedido";

const PRAZOS = [12, 24, 36, 48, 60];

/** Prazo válido: inteiro de 1 a 120 meses (mesmo limite da API). */
function prazoValido(v: string) {
  const n = Number(v);
  return Number.isInteger(n) && n >= 1 && n <= 120;
}

type Modo = "guiado" | "livre";

type Estado =
  | { tipo: "ocioso" }
  | { tipo: "gerando"; concluido: boolean }
  | { tipo: "erro"; tom: "erro" | "recusa"; titulo: string; mensagem: string };

export function NovoPedido() {
  const navegar = useNavigate();
  const [modo, setModo] = useState<Modo>("guiado");
  const [dados, setDados] = useState<DadosPedido>(PEDIDO_VAZIO);
  const [texto, setTexto] = useState("");
  const [prazo, setPrazo] = useState("");
  const [tocado, setTocado] = useState(false);
  const [prazoTocado, setPrazoTocado] = useState(false);
  const [chave, setChave] = useState(chaveApi);
  const [chaveAberta, setChaveAberta] = useState(false);
  const [estado, setEstado] = useState<Estado>({ tipo: "ocioso" });
  const campoTexto = useRef<HTMLTextAreaElement>(null);
  const formulario = useRef<HTMLFormElement>(null);
  const gerando = estado.tipo === "gerando";

  const textoFinal = modo === "guiado" ? compor(dados, prazo) : texto;
  const conteudoOk = modo === "guiado" ? guiadoCompleto(dados) : texto.trim().length >= 10;
  const itens: ItemChecklist[] = [
    ...(modo === "guiado" ? checklistGuiado(dados) : checklistTexto(texto)),
    { chave: "prazo", rotulo: "Prazo do crédito", ok: prazoValido(prazo) },
  ];
  const algoPreenchido = JSON.stringify(dados) !== JSON.stringify(PEDIDO_VAZIO) || !!texto || !!prazo;

  function mudarDados(parcial: Partial<DadosPedido>) {
    setDados((d) => ({ ...d, ...parcial }));
  }

  function trocarModo(novo: Modo) {
    if (novo === modo) return;
    // Guiado → livre: leva o texto montado para o usuário ajustar à vontade.
    if (novo === "livre" && !texto.trim() && JSON.stringify(dados) !== JSON.stringify(PEDIDO_VAZIO)) {
      setTexto(compor(dados, prazo));
    }
    setModo(novo);
  }

  function usarExemplo(i: number) {
    const ex = EXEMPLOS[i];
    setDados(ex.dados);
    setPrazo(String(ex.prazo));
    setTexto(compor(ex.dados, String(ex.prazo)));
    setEstado({ tipo: "ocioso" });
  }

  function limpar() {
    setDados(PEDIDO_VAZIO);
    setTexto("");
    setPrazo("");
    setTocado(false);
    setPrazoTocado(false);
    setEstado({ tipo: "ocioso" });
  }

  async function enviar(e: FormEvent) {
    e.preventDefault();
    setTocado(true);
    setPrazoTocado(true);
    if (!conteudoOk || !prazoValido(prazo)) {
      // Leva o foco ao primeiro campo pendente.
      requestAnimationFrame(() => {
        const alvo =
          formulario.current?.querySelector<HTMLElement>('[aria-invalid="true"]') ??
          (modo === "livre" && !conteudoOk ? campoTexto.current : null);
        alvo?.focus();
      });
      return;
    }
    guardarChave(chave.trim());
    setEstado({ tipo: "gerando", concluido: false });
    try {
      const r = await api.criar(textoFinal, Number(prazo));
      if (r.ok && r.corpo?.laudo_id) {
        setEstado({ tipo: "gerando", concluido: true });
        setTimeout(() => navegar(`/laudos/${r.corpo!.laudo_id}`), 900);
        return;
      }
      const recusa = (r.erro as { detail?: { motivo_recusa?: string } } | null)?.detail?.motivo_recusa;
      if (r.status === 422 && recusa) {
        setEstado({
          tipo: "erro",
          tom: "recusa",
          titulo: "Pedido fora de escopo",
          mensagem: `${recusa} Nenhum laudo foi gerado; a recusa ficou registrada na trilha de auditoria.`,
        });
      } else if (r.status === 401) {
        setChaveAberta(true);
        setEstado({
          tipo: "erro",
          tom: "erro",
          titulo: "Chave de analista inválida",
          mensagem: "Corrija ou apague a chave em “Chave de analista” — sem chave, a demo aceita pedidos dentro do limite diário.",
        });
      } else if (r.status === 429) {
        setEstado({
          tipo: "erro",
          tom: "recusa",
          titulo: "Limite diário da demo atingido",
          mensagem: detalheErro(r.erro, r.status),
        });
      } else if (r.status === 503) {
        setEstado({
          tipo: "erro",
          tom: "erro",
          titulo: "Serviço temporariamente indisponível",
          mensagem: "O LLM está com cota esgotada no momento. Aguarde ~30 segundos e gere novamente.",
        });
      } else {
        setEstado({ tipo: "erro", tom: "erro", titulo: "Falha ao gerar o laudo", mensagem: detalheErro(r.erro, r.status) });
      }
    } catch (erro) {
      setEstado({
        tipo: "erro",
        tom: "erro",
        titulo: "Sem conexão com a API",
        mensagem: erro instanceof Error ? erro.message : String(erro),
      });
    }
  }

  return (
    <Container className="py-12 sm:py-16">
      <div className="max-w-2xl">
        <Eyebrow>
          <Sparkles className="size-3.5 text-accent" /> Novo pedido
        </Eyebrow>
        <h1 className="mt-3 text-4xl font-semibold tracking-[-0.035em] sm:text-5xl">
          Monte o pedido de <span className="font-serif font-normal italic text-gradient">crédito</span>
        </h1>
        <p className="mt-4 text-lg text-muted">
          Preencha os campos — leva menos de um minuto. Prefere escrever? Use o texto livre, do jeito que chegaria por e-mail.
        </p>
      </div>

      <div className="mt-10 grid items-start gap-6 lg:grid-cols-[1fr_22rem]">
        <Card className="p-5 sm:p-7">
          <form ref={formulario} onSubmit={enviar} noValidate className="space-y-6">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
              <div role="tablist" aria-label="Forma de preenchimento" className="inline-flex rounded-xl border border-line bg-bg/50 p-1">
                {(
                  [
                    ["guiado", "Formulário guiado", ListChecks],
                    ["livre", "Texto livre", PenLine],
                  ] as const
                ).map(([valor, rotulo, Icone]) => (
                  <button
                    key={valor}
                    type="button"
                    role="tab"
                    aria-selected={modo === valor}
                    disabled={gerando}
                    onClick={() => trocarModo(valor)}
                    className={cx(
                      "relative flex h-9 items-center gap-2 rounded-lg px-3.5 text-sm font-medium transition-colors",
                      modo === valor ? "text-ink" : "text-muted hover:text-ink",
                    )}
                  >
                    {modo === valor && (
                      <motion.span
                        layoutId="modo-ativo"
                        className="absolute inset-0 -z-10 rounded-lg bg-surface-2 ring-1 ring-line-strong"
                        transition={{ type: "spring", bounce: 0.2, duration: 0.4 }}
                      />
                    )}
                    <Icone className="size-4" /> {rotulo}
                  </button>
                ))}
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="flex items-center gap-1 text-xs text-faint">
                  <Wand2 className="size-3.5" /> Exemplo:
                </span>
                {EXEMPLOS.map((ex, i) => (
                  <button
                    key={ex.rotulo}
                    type="button"
                    disabled={gerando}
                    onClick={() => usarExemplo(i)}
                    className="rounded-full border border-line bg-surface-2 px-2.5 py-1 text-xs text-muted transition-colors hover:border-accent/40 hover:text-ink disabled:opacity-50"
                  >
                    {ex.rotulo}
                  </button>
                ))}
              </div>
            </div>

            <AnimatePresence mode="wait" initial={false}>
              {modo === "guiado" ? (
                <motion.div key="guiado" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
                  <PedidoGuiado dados={dados} aoMudar={mudarDados} tocado={tocado} disabled={gerando} />
                </motion.div>
              ) : (
                <motion.div key="livre" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
                  <div className="flex items-baseline justify-between">
                    <label htmlFor="texto" className="text-sm font-medium">
                      Pedido <span className="text-alto" aria-hidden>*</span>
                    </label>
                    <span className={cx("num text-xs", texto.trim().length < 10 ? "text-faint" : "text-muted")}>
                      {texto.length} caracteres
                    </span>
                  </div>
                  <textarea
                    id="texto"
                    ref={campoTexto}
                    disabled={gerando}
                    value={texto}
                    onChange={(e) => setTexto(e.target.value)}
                    aria-invalid={tocado && texto.trim().length < 10}
                    placeholder="Ex.: Clínica odontológica em São Paulo, ME, 5 anos de operação, faturamento de R$ 2 mi, pede R$ 300 mil para expansão…"
                    className={cx(
                      "mt-2 block min-h-52 w-full resize-y rounded-xl border bg-bg/60 px-4 py-3.5 text-[15px] leading-relaxed text-ink placeholder:text-faint transition-colors focus:outline-none focus:ring-4 disabled:opacity-60",
                      tocado && texto.trim().length < 10
                        ? "border-alto/60 focus:ring-alto/10"
                        : "border-line-strong focus:border-accent/60 focus:ring-accent/10",
                    )}
                  />
                  <p className="mt-2 text-xs text-faint">O checklist ao lado marca cada item conforme você escreve.</p>
                </motion.div>
              )}
            </AnimatePresence>

            <div className="border-t border-line pt-6">
              <label htmlFor="prazo" className="flex items-center gap-1.5 text-sm font-medium">
                <CalendarClock className="size-4 text-muted" /> Prazo do crédito
                <span className="text-alto" aria-hidden>*</span>
                <span className="sr-only">(obrigatório)</span>
              </label>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <div className="relative">
                  <input
                    id="prazo"
                    type="number"
                    inputMode="numeric"
                    min={1}
                    max={120}
                    step={1}
                    disabled={gerando}
                    value={prazo}
                    onChange={(e) => setPrazo(e.target.value)}
                    onBlur={() => setPrazoTocado(true)}
                    placeholder="—"
                    aria-invalid={prazoTocado && !prazoValido(prazo)}
                    aria-describedby="prazo-ajuda"
                    className={cx(
                      "num h-11 w-32 rounded-xl border bg-bg/60 pr-16 pl-3.5 text-[15px] focus:outline-none focus:ring-4 disabled:opacity-60 [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none",
                      prazoTocado && !prazoValido(prazo)
                        ? "border-alto/60 focus:ring-alto/10"
                        : "border-line-strong focus:border-accent/60 focus:ring-accent/10",
                    )}
                  />
                  <span className="pointer-events-none absolute top-1/2 right-3.5 -translate-y-1/2 text-sm text-faint">meses</span>
                </div>
                {PRAZOS.map((m) => (
                  <button
                    key={m}
                    type="button"
                    disabled={gerando}
                    onClick={() => {
                      setPrazo(String(m));
                      setPrazoTocado(true);
                    }}
                    className={cx(
                      "num h-11 rounded-xl border px-3.5 text-sm transition-colors disabled:opacity-50",
                      prazo === String(m)
                        ? "border-accent/50 bg-accent-soft text-accent"
                        : "border-line bg-surface-2 text-muted hover:border-line-strong hover:text-ink",
                    )}
                  >
                    {m}
                  </button>
                ))}
              </div>
              <p id="prazo-ajuda" className={cx("mt-2 text-xs", prazoTocado && !prazoValido(prazo) ? "text-alto" : "text-faint")}>
                {prazoTocado && !prazoValido(prazo)
                  ? "Informe o prazo em meses, de 1 a 120."
                  : "Obrigatório — entra no cálculo da parcela e da PD. Se o texto citar outro prazo, vale o deste campo."}
              </p>
            </div>

            <div className="rounded-xl border border-line">
              <button
                type="button"
                onClick={() => setChaveAberta((a) => !a)}
                aria-expanded={chaveAberta}
                className="flex w-full items-center justify-between gap-3 px-4 py-3 text-sm text-muted hover:text-ink"
              >
                <span className="flex items-center gap-2">
                  <KeyRound className="size-4" /> Chave de analista <span className="text-faint">(opcional)</span>
                  {chave && <span className="rounded-full bg-accent-soft px-2 py-0.5 text-[11px] text-accent">salva</span>}
                </span>
                <ChevronDown className={cx("size-4 transition-transform", chaveAberta && "rotate-180")} />
              </button>
              <AnimatePresence initial={false}>
                {chaveAberta && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: "auto", opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    className="overflow-hidden"
                  >
                    <div className="px-4 pb-4">
                      <input
                        type="password"
                        aria-label="Chave da API"
                        autoComplete="off"
                        value={chave}
                        onChange={(e) => setChave(e.target.value)}
                        onBlur={() => guardarChave(chave.trim())}
                        className="h-10 w-full rounded-lg border border-line-strong bg-bg/60 px-3 font-mono text-sm focus:border-accent/60 focus:outline-none focus:ring-4 focus:ring-accent/10"
                      />
                      <p className="mt-2 text-xs text-faint">Enviada só no header X-API-Key deste navegador. Sem chave, a demo aceita um número limitado de laudos por dia; analistas com chave não têm limite e podem decidir no portão humano.</p>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>

            <Aviso tom="info" titulo="Use dados fictícios">
              <p>
                O pedido fica registrado na trilha de auditoria da demo, e um CNPJ informado é consultado na base
                pública da Receita. Não informe dados reais de pessoas ou empresas.
              </p>
            </Aviso>

            <div className="flex flex-wrap items-center gap-3">
              <Button type="submit" tamanho="lg" disabled={gerando}>
                {gerando ? "Gerando laudo…" : "Gerar laudo"} {!gerando && <ArrowRight className="size-4" />}
              </Button>
              <Button type="button" variante="fantasma" tamanho="lg" disabled={gerando || !algoPreenchido} onClick={limpar}>
                <RotateCcw className="size-4" /> Limpar
              </Button>
            </div>

            <AnimatePresence mode="wait">
              {estado.tipo === "erro" && (
                <motion.div key="erro" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
                  <Aviso tom={estado.tom} titulo={estado.titulo}>
                    <p>{estado.mensagem}</p>
                  </Aviso>
                </motion.div>
              )}
            </AnimatePresence>
          </form>
        </Card>

        <aside className="lg:sticky lg:top-24">
          <AnimatePresence mode="wait">
            {gerando ? (
              <motion.div key="progresso" initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0 }}>
                <Card className="p-5 sm:p-6">
                  <PipelineProgress concluido={estado.concluido} />
                </Card>
              </motion.div>
            ) : (
              <motion.div key="resumo" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
                <Resumo itens={itens} modo={modo} texto={textoFinal} />
              </motion.div>
            )}
          </AnimatePresence>
        </aside>
      </div>
    </Container>
  );
}

function Resumo({ itens, modo, texto }: { itens: ItemChecklist[]; modo: Modo; texto: string }) {
  const feitos = itens.filter((i) => i.ok).length;
  const completo = feitos === itens.length;

  return (
    <Card className="p-5 sm:p-6">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium">{completo ? "Tudo pronto" : "Checklist do pedido"}</p>
        <span className={cx("num text-xs", completo ? "text-accent" : "text-muted")}>
          {feitos} de {itens.length}
        </span>
      </div>
      <div className="mt-3 h-1 overflow-hidden rounded-full bg-surface-2">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-accent to-accent-2"
          animate={{ width: `${(feitos / itens.length) * 100}%` }}
          transition={{ ease: [0.16, 1, 0.3, 1], duration: 0.5 }}
        />
      </div>

      <ul className="mt-4 space-y-2.5">
        {itens.map((item) => (
          <li key={item.chave} className={cx("flex items-center gap-2.5 text-sm transition-colors", item.ok ? "text-ink" : "text-muted")}>
            <span
              className={cx(
                "grid size-5 shrink-0 place-items-center rounded-full transition-all duration-300",
                item.ok ? "bg-accent text-accent-ink" : "ring-1 ring-line-strong ring-inset",
              )}
            >
              <AnimatePresence>
                {item.ok && (
                  <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} exit={{ scale: 0 }} transition={{ type: "spring", bounce: 0.5, duration: 0.4 }}>
                    <Check className="size-3" strokeWidth={3} />
                  </motion.span>
                )}
              </AnimatePresence>
            </span>
            {item.rotulo}
          </li>
        ))}
      </ul>

      {modo === "guiado" ? (
        <div className="mt-5 border-t border-line pt-4">
          <p className="text-xs font-medium text-muted">Texto enviado ao Aval</p>
          <p className="mt-2 rounded-lg bg-bg/60 p-3 text-xs leading-relaxed text-muted ring-1 ring-line">
            {texto === "Empresa." ? <span className="text-faint">Preencha os campos para ver a prévia.</span> : texto}
          </p>
        </div>
      ) : (
        <p className="mt-5 border-t border-line pt-4 text-xs leading-relaxed text-faint">
          A marcação é uma ajuda visual. Faltou algo? Campos ambíguos viram premissas explícitas, citadas no laudo — nada é
          inventado.
        </p>
      )}
    </Card>
  );
}
