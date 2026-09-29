import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { Link, type LinkProps } from "react-router";
import { AlertTriangle, Ban, CheckCircle2, Clock3, Info, PencilLine, XCircle } from "lucide-react";
import { classeFaixa, FAIXA_ROTULO, STATUS_ROTULO } from "../lib/format";

export function cx(...c: (string | false | null | undefined)[]) {
  return c.filter(Boolean).join(" ");
}

type Variante = "primario" | "secundario" | "fantasma" | "perigo";
type Tamanho = "sm" | "md" | "lg";

const BASE =
  "inline-flex items-center justify-center gap-2 rounded-xl font-medium whitespace-nowrap transition-all duration-200 disabled:opacity-50 disabled:pointer-events-none select-none active:scale-[0.98]";
const VARIANTES: Record<Variante, string> = {
  primario:
    "shine bg-accent text-accent-ink shadow-[0_0_0_1px_rgb(255_255_255/0.12)_inset,0_8px_24px_-8px_var(--c-glow)] hover:brightness-110 hover:shadow-[0_0_0_1px_rgb(255_255_255/0.18)_inset,0_10px_32px_-6px_var(--c-glow)]",
  secundario: "border border-line-strong bg-surface-2 text-ink hover:border-faint hover:bg-surface",
  fantasma: "text-muted hover:text-ink hover:bg-surface-2",
  perigo: "border border-alto/40 bg-alto/10 text-alto hover:bg-alto/20",
};
const TAMANHOS: Record<Tamanho, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-[15px]",
};

export function estiloBotao(v: Variante = "primario", t: Tamanho = "md", extra?: string) {
  return cx(BASE, VARIANTES[v], TAMANHOS[t], extra);
}

export function Button({
  variante = "primario",
  tamanho = "md",
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variante?: Variante; tamanho?: Tamanho }) {
  return <button className={estiloBotao(variante, tamanho, className)} {...props} />;
}

export function ButtonLink({
  variante = "primario",
  tamanho = "md",
  className,
  ...props
}: LinkProps & { variante?: Variante; tamanho?: Tamanho }) {
  return <Link className={estiloBotao(variante, tamanho, className)} {...props} />;
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cx("glass", className)} {...props} />;
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-muted",
        className,
      )}
    >
      {children}
    </span>
  );
}

const COR_FAIXA = {
  baixo: "text-baixo bg-baixo/10 ring-baixo/25",
  medio: "text-medio bg-medio/10 ring-medio/25",
  alto: "text-alto bg-alto/10 ring-alto/25",
  muito_alto: "text-alto bg-alto/20 ring-alto/50 font-semibold",
};

export function FaixaBadge({ faixa, className }: { faixa?: string | null; className?: string }) {
  if (!faixa) return <span className="text-faint">—</span>;
  const f = classeFaixa(faixa);
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset",
        COR_FAIXA[f],
        className,
      )}
    >
      <span className="size-1.5 rounded-full bg-current" />
      {FAIXA_ROTULO[f]}
    </span>
  );
}

const STATUS_ESTILO: Record<string, { cls: string; Icone: typeof Clock3 }> = {
  pendente: { cls: "text-info bg-info/10 ring-info/25", Icone: Clock3 },
  aprovado: { cls: "text-baixo bg-baixo/10 ring-baixo/25", Icone: CheckCircle2 },
  corrigido: { cls: "text-medio bg-medio/10 ring-medio/25", Icone: PencilLine },
  rejeitado: { cls: "text-alto bg-alto/10 ring-alto/25", Icone: XCircle },
};

export function StatusBadge({ status }: { status: string }) {
  const { cls, Icone } = STATUS_ESTILO[status] ?? STATUS_ESTILO.pendente;
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset", cls)}>
      <Icone className="size-3.5" strokeWidth={2.25} />
      {STATUS_ROTULO[status] ?? status}
    </span>
  );
}

type TomAviso = "erro" | "recusa" | "info";
const AVISO: Record<TomAviso, { cls: string; Icone: typeof Info }> = {
  erro: { cls: "border-alto/30 bg-alto/[0.07]", Icone: AlertTriangle },
  recusa: { cls: "border-medio/30 bg-medio/[0.07]", Icone: Ban },
  info: { cls: "border-info/30 bg-info/[0.07]", Icone: Info },
};
const AVISO_ICONE: Record<TomAviso, string> = { erro: "text-alto", recusa: "text-medio", info: "text-info" };

export function Aviso({
  tom = "erro",
  titulo,
  children,
}: {
  tom?: TomAviso;
  titulo: string;
  children?: ReactNode;
}) {
  const { cls, Icone } = AVISO[tom];
  return (
    <div role="alert" className={cx("flex gap-3 rounded-xl border p-4", cls)}>
      <Icone className={cx("mt-0.5 size-5 shrink-0", AVISO_ICONE[tom])} />
      <div className="min-w-0 text-sm">
        <p className="font-semibold text-ink">{titulo}</p>
        {children && <div className="mt-1 text-muted [&_p+p]:mt-1.5">{children}</div>}
      </div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("skeleton", className)} aria-hidden />;
}
