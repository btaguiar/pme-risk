import Markdown, { type Components } from "react-markdown";
import { rotuloFator } from "../lib/format";

// Texto do Redator (LLM) em Markdown. react-markdown não interpreta HTML bruto
// (sem rehype-raw), então o texto não injeta marcação na página.
const COMPONENTES: Components = {
  h1: ({ children }) => <h3 className="mt-8 mb-3 text-lg font-semibold text-ink first:mt-0">{children}</h3>,
  h2: ({ children }) => <h3 className="mt-8 mb-3 text-lg font-semibold text-ink first:mt-0">{children}</h3>,
  h3: ({ children }) => <h4 className="mt-6 mb-2 text-base font-semibold text-ink first:mt-0">{children}</h4>,
  h4: ({ children }) => <h4 className="mt-6 mb-2 text-base font-semibold text-ink first:mt-0">{children}</h4>,
  p: ({ children }) => <p className="my-3 first:mt-0">{children}</p>,
  ul: ({ children }) => <ul className="my-3 list-disc space-y-1.5 pl-5 marker:text-faint">{children}</ul>,
  ol: ({ children }) => <ol className="my-3 list-decimal space-y-1.5 pl-5 marker:text-faint">{children}</ol>,
  strong: ({ children }) => <strong className="font-semibold text-ink">{children}</strong>,
  blockquote: ({ children }) => <blockquote className="my-3 border-l-2 border-line-strong pl-4 text-muted">{children}</blockquote>,
  hr: () => <hr className="my-6 border-line" />,
  // Nomes entre crases são fatores/campos do modelo (o juiz de fidedignidade
  // os confere): mantém o nome técnico e mostra o rótulo legível no título.
  code: ({ children }) => {
    const nome = String(children);
    return (
      <code
        title={rotuloFator(nome)}
        className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono text-[13px] text-ink ring-1 ring-inset ring-line"
      >
        {nome}
      </code>
    );
  },
  a: ({ children }) => <span className="underline decoration-line-strong">{children}</span>,
};

export function TextoLaudo({ texto }: { texto: string }) {
  return (
    <div className="max-w-[72ch] text-[15px] leading-[1.75] text-ink/90">
      <Markdown components={COMPONENTES}>{texto}</Markdown>
    </div>
  );
}
