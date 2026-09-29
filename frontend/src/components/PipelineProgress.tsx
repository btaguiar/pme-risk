import { useEffect, useState } from "react";
import { motion } from "motion/react";
import { Check, FileSearch, Globe2, PenLine, Sigma, UserCheck } from "lucide-react";
import { cx } from "./ui";

export const ETAPAS = [
  {
    Icone: FileSearch,
    titulo: "Extração",
    descricao: "Lê o pedido em português e estrutura setor, porte, UF, valores e premissas.",
    segundos: 7,
  },
  {
    Icone: Globe2,
    titulo: "Pesquisa",
    descricao: "Enriquece com dados públicos do CNPJ e separa o verificado do declarado.",
    segundos: 14,
  },
  {
    Icone: Sigma,
    titulo: "Modelo",
    descricao: "Calcula a PD com o modelo estatístico versionado e atribui os fatores.",
    segundos: 6,
  },
  {
    Icone: PenLine,
    titulo: "Redação",
    descricao: "Redige o laudo citando evidências — sem inventar números.",
    segundos: 18,
  },
  {
    Icone: UserCheck,
    titulo: "Portão humano",
    descricao: "O laudo fica pendente até um analista aprovar, corrigir ou rejeitar.",
    segundos: 0,
  },
] as const;

const EM_EXECUCAO = ETAPAS.length - 1; // o portão humano acontece depois, fora deste fluxo

/**
 * Progresso do pipeline durante o POST /laudos (20–60 s). A API não expõe etapas,
 * então o avanço é estimado pelo tempo; a última etapa de máquina segura até a resposta.
 */
export function PipelineProgress({ concluido }: { concluido: boolean }) {
  const [decorrido, setDecorrido] = useState(0);

  useEffect(() => {
    const inicio = performance.now();
    const t = setInterval(() => setDecorrido((performance.now() - inicio) / 1000), 200);
    return () => clearInterval(t);
  }, []);

  let acumulado = 0;
  let atual = EM_EXECUCAO - 1;
  for (let i = 0; i < EM_EXECUCAO; i++) {
    acumulado += ETAPAS[i].segundos;
    if (decorrido < acumulado) {
      atual = i;
      break;
    }
  }
  if (concluido) atual = EM_EXECUCAO;

  const total = ETAPAS.slice(0, EM_EXECUCAO).reduce((s, e) => s + e.segundos, 0);
  const progresso = concluido ? 1 : Math.min(0.94, decorrido / total);

  return (
    <div role="status" aria-live="polite" className="space-y-5">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-ink">
            {concluido ? "Laudo pronto" : `${ETAPAS[atual].titulo} em andamento…`}
          </p>
          <p className="text-xs text-muted">Costuma levar de 20 a 60 segundos.</p>
        </div>
        <span className="num text-sm text-muted">{decorrido.toFixed(0)}s</span>
      </div>

      <div className="h-1 overflow-hidden rounded-full bg-surface-2">
        <motion.div
          className="h-full rounded-full bg-gradient-to-r from-accent to-accent-2"
          animate={{ width: `${progresso * 100}%` }}
          transition={{ ease: "easeOut", duration: 0.4 }}
        />
      </div>

      <ol className="grid min-w-0 grid-cols-1 gap-2">
        {ETAPAS.slice(0, EM_EXECUCAO).map(({ Icone, titulo, descricao }, i) => {
          const feito = i < atual || concluido;
          const ativo = i === atual && !concluido;
          return (
            <motion.li
              key={titulo}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: i * 0.06 }}
              className={cx(
                "flex min-w-0 items-center gap-3 rounded-xl border px-3.5 py-3 transition-colors duration-500",
                ativo ? "border-accent/40 bg-accent-soft" : "border-line bg-surface",
              )}
            >
              <span
                className={cx(
                  "relative grid size-9 shrink-0 place-items-center rounded-lg transition-colors duration-500",
                  feito ? "bg-accent text-accent-ink" : ativo ? "bg-accent/15 text-accent" : "bg-surface-2 text-faint",
                )}
              >
                {ativo && <span className="absolute inset-0 animate-ping rounded-lg bg-accent/25" />}
                {feito ? <Check className="size-4" strokeWidth={3} /> : <Icone className="size-4" />}
              </span>
              <div className="min-w-0">
                <p className={cx("text-sm font-medium", feito || ativo ? "text-ink" : "text-muted")}>{titulo}</p>
                <p className="text-xs leading-snug text-muted">{descricao}</p>
              </div>
            </motion.li>
          );
        })}
      </ol>
    </div>
  );
}
