import type { ReactNode } from "react";
import { ChevronDown } from "lucide-react";
import { cx } from "./ui";
import { moeda } from "../lib/format";
import { FINALIDADES, PORTES, SETORES, UFS, anosValidos, type DadosPedido } from "../lib/pedido";

const CAMPO =
  "h-11 w-full rounded-xl border bg-bg/60 px-3.5 text-[15px] text-ink placeholder:text-faint transition-colors focus:outline-none focus:ring-4 disabled:opacity-60";
const OK = "border-line-strong focus:border-accent/60 focus:ring-accent/10";
const ERRO = "border-alto/60 focus:ring-alto/10";

function Rotulo({ htmlFor, children, obrigatorio, dica }: { htmlFor?: string; children: ReactNode; obrigatorio?: boolean; dica?: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 flex items-baseline gap-1 text-sm font-medium">
      {children}
      {obrigatorio && (
        <>
          <span className="text-alto" aria-hidden>*</span>
          <span className="sr-only">(obrigatório)</span>
        </>
      )}
      {dica && <span className="ml-1 text-xs font-normal text-faint">{dica}</span>}
    </label>
  );
}

function Erro({ mostrar, children }: { mostrar: boolean; children: ReactNode }) {
  return mostrar ? <p className="mt-1.5 text-xs text-alto">{children}</p> : null;
}

/** Campo de reais: aceita só dígitos e mostra com separador de milhar. */
function CampoMoeda({
  id,
  valor,
  aoMudar,
  invalido,
  disabled,
  placeholder,
}: {
  id: string;
  valor: number | null;
  aoMudar: (v: number | null) => void;
  invalido: boolean;
  disabled?: boolean;
  placeholder: string;
}) {
  return (
    <div className="relative">
      <span className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-sm text-faint">R$</span>
      <input
        id={id}
        inputMode="numeric"
        autoComplete="off"
        disabled={disabled}
        value={valor ? valor.toLocaleString("pt-BR") : ""}
        onChange={(e) => {
          const digitos = e.target.value.replace(/\D/g, "").slice(0, 12);
          aoMudar(digitos ? Number(digitos) : null);
        }}
        placeholder={placeholder}
        aria-invalid={invalido}
        className={cx(CAMPO, "num pl-10", invalido ? ERRO : OK)}
      />
    </div>
  );
}

export function PedidoGuiado({
  dados,
  aoMudar,
  tocado,
  disabled,
}: {
  dados: DadosPedido;
  aoMudar: (parcial: Partial<DadosPedido>) => void;
  tocado: boolean;
  disabled?: boolean;
}) {
  const falta = {
    atividade: tocado && !dados.atividade.trim(),
    uf: tocado && !dados.uf,
    porte: tocado && !dados.porte,
    anos: tocado && !anosValidos(dados.anos),
    faturamento: tocado && !dados.faturamento,
    valor: tocado && !dados.valor,
    finalidade: tocado && !dados.finalidade.trim(),
  };

  return (
    <div className="grid gap-x-4 gap-y-5 sm:grid-cols-6">
      <div className="sm:col-span-6">
        <Rotulo htmlFor="g-atividade" obrigatorio>
          O que a empresa faz
        </Rotulo>
        <input
          id="g-atividade"
          disabled={disabled}
          value={dados.atividade}
          onChange={(e) => aoMudar({ atividade: e.target.value })}
          placeholder="Ex.: clínica odontológica, padaria, oficina mecânica…"
          aria-invalid={falta.atividade}
          className={cx(CAMPO, falta.atividade ? ERRO : OK)}
        />
        <Erro mostrar={falta.atividade}>Descreva a atividade em poucas palavras.</Erro>
      </div>

      <div className="sm:col-span-3">
        <Rotulo htmlFor="g-setor" dica="opcional">
          Setor
        </Rotulo>
        <div className="relative">
          <select
            id="g-setor"
            disabled={disabled}
            value={dados.setor}
            onChange={(e) => aoMudar({ setor: e.target.value })}
            className={cx(CAMPO, OK, "appearance-none pr-10", !dados.setor && "text-muted")}
          >
            <option value="">Identificar automaticamente</option>
            {SETORES.map(([codigo, , , rotulo]) => (
              <option key={codigo} value={codigo}>
                {rotulo}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute top-1/2 right-3.5 size-4 -translate-y-1/2 text-faint" />
        </div>
      </div>

      <div className="sm:col-span-3">
        <Rotulo obrigatorio>Porte</Rotulo>
        <div role="radiogroup" aria-label="Porte" className="grid grid-cols-3 gap-1.5">
          {PORTES.map((p) => {
            const ativo = dados.porte === p.valor;
            return (
              <button
                key={p.valor}
                type="button"
                role="radio"
                aria-checked={ativo}
                disabled={disabled}
                onClick={() => aoMudar({ porte: p.valor })}
                title={p.dica}
                className={cx(
                  "flex h-11 flex-col items-center justify-center rounded-xl border text-sm leading-tight transition-colors disabled:opacity-50",
                  ativo
                    ? "border-accent/50 bg-accent-soft text-accent"
                    : falta.porte
                      ? "border-alto/60 text-muted"
                      : "border-line-strong bg-bg/60 text-muted hover:text-ink",
                )}
              >
                <span className="font-medium">{p.rotulo}</span>
                <span className="hidden text-[10px] opacity-70 sm:block">{p.dica}</span>
              </button>
            );
          })}
        </div>
        <Erro mostrar={falta.porte}>Escolha o porte.</Erro>
      </div>

      <div className="sm:col-span-4">
        <Rotulo htmlFor="g-cidade" dica="opcional">
          Cidade
        </Rotulo>
        <input
          id="g-cidade"
          disabled={disabled}
          value={dados.cidade}
          onChange={(e) => aoMudar({ cidade: e.target.value })}
          placeholder="Ex.: Campinas"
          className={cx(CAMPO, OK)}
        />
      </div>

      <div className="sm:col-span-2">
        <Rotulo htmlFor="g-uf" obrigatorio>
          UF
        </Rotulo>
        <div className="relative">
          <select
            id="g-uf"
            disabled={disabled}
            value={dados.uf}
            onChange={(e) => aoMudar({ uf: e.target.value })}
            aria-invalid={falta.uf}
            className={cx(CAMPO, "appearance-none pr-10", falta.uf ? ERRO : OK, !dados.uf && "text-muted")}
          >
            <option value="">Selecione</option>
            {UFS.map((uf) => (
              <option key={uf} value={uf}>
                {uf}
              </option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute top-1/2 right-3.5 size-4 -translate-y-1/2 text-faint" />
        </div>
        <Erro mostrar={falta.uf}>Selecione a UF.</Erro>
      </div>

      <div className="sm:col-span-2">
        <Rotulo htmlFor="g-anos" obrigatorio>
          Tempo de operação
        </Rotulo>
        <div className="relative">
          <input
            id="g-anos"
            inputMode="decimal"
            disabled={disabled}
            value={dados.anos}
            onChange={(e) => aoMudar({ anos: e.target.value.replace(/[^\d.,]/g, "").slice(0, 5) })}
            placeholder="0"
            aria-invalid={falta.anos}
            className={cx(CAMPO, "num pr-14", falta.anos ? ERRO : OK)}
          />
          <span className="pointer-events-none absolute top-1/2 right-3.5 -translate-y-1/2 text-sm text-faint">anos</span>
        </div>
        <Erro mostrar={falta.anos}>Informe em anos (ex.: 2 ou 1,5).</Erro>
      </div>

      <div className="sm:col-span-2">
        <Rotulo htmlFor="g-faturamento" obrigatorio>
          Faturamento anual
        </Rotulo>
        <CampoMoeda
          id="g-faturamento"
          valor={dados.faturamento}
          aoMudar={(v) => aoMudar({ faturamento: v })}
          invalido={falta.faturamento}
          disabled={disabled}
          placeholder="0"
        />
        {dados.faturamento ? (
          <p className="num mt-1.5 text-xs text-faint">≈ {moeda(dados.faturamento, true)} por ano</p>
        ) : (
          <Erro mostrar={falta.faturamento}>Informe o faturamento.</Erro>
        )}
      </div>

      <div className="sm:col-span-2">
        <Rotulo htmlFor="g-valor" obrigatorio>
          Valor solicitado
        </Rotulo>
        <CampoMoeda
          id="g-valor"
          valor={dados.valor}
          aoMudar={(v) => aoMudar({ valor: v })}
          invalido={falta.valor}
          disabled={disabled}
          placeholder="0"
        />
        {dados.valor && dados.faturamento ? (
          <p className="num mt-1.5 text-xs text-faint">
            {Math.round((dados.valor / dados.faturamento) * 100).toLocaleString("pt-BR")}% do faturamento anual
          </p>
        ) : (
          <Erro mostrar={falta.valor}>Informe o valor.</Erro>
        )}
      </div>

      <div className="sm:col-span-6">
        <Rotulo htmlFor="g-finalidade" obrigatorio>
          Finalidade
        </Rotulo>
        <div className="mb-2 flex flex-wrap gap-1.5">
          {FINALIDADES.map((f) => (
            <button
              key={f}
              type="button"
              disabled={disabled}
              onClick={() => aoMudar({ finalidade: f })}
              className={cx(
                "rounded-full border px-3 py-1 text-xs transition-colors disabled:opacity-50",
                dados.finalidade === f
                  ? "border-accent/50 bg-accent-soft text-accent"
                  : "border-line bg-surface-2 text-muted hover:border-line-strong hover:text-ink",
              )}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
        <input
          id="g-finalidade"
          disabled={disabled}
          value={dados.finalidade}
          onChange={(e) => aoMudar({ finalidade: e.target.value })}
          placeholder="Escolha acima ou descreva: ex.: comprar um forno novo"
          aria-invalid={falta.finalidade}
          className={cx(CAMPO, falta.finalidade ? ERRO : OK)}
        />
        <Erro mostrar={falta.finalidade}>Diga para que o crédito será usado.</Erro>
      </div>
    </div>
  );
}
