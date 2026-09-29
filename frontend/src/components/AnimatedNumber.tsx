import { useEffect, useRef } from "react";
import { animate, useInView } from "motion/react";

/** Número que conta até o valor quando entra na tela (PD, KPIs). */
export function AnimatedNumber({
  valor,
  formatar,
  duracao = 1.1,
  className,
}: {
  valor: number;
  formatar: (n: number) => string;
  duracao?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const visivel = useInView(ref, { once: true });

  useEffect(() => {
    const el = ref.current;
    if (!el || !visivel) return;
    const controle = animate(0, valor, {
      duration: duracao,
      ease: [0.16, 1, 0.3, 1],
      onUpdate: (v) => {
        el.textContent = formatar(v);
      },
    });
    return () => controle.stop();
  }, [valor, visivel, duracao, formatar]);

  return (
    <span ref={ref} className={className}>
      {formatar(0)}
    </span>
  );
}
