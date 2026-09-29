import { useId } from "react";
import { cx } from "./ui";

/** Monograma "A" do Aval: o traço horizontal vira um check — a rubrica de quem avaliza. */
export function LogoMarca({ className }: { className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 32 32" className={cx("size-8", className)} aria-hidden>
      <defs>
        <linearGradient id={`${id}-g`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6ee7b7" />
          <stop offset="1" stopColor="#059669" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" className="fill-solid" />
      <rect x="0.5" y="0.5" width="31" height="31" rx="8.5" fill="none" className="stroke-line-strong" />
      <path
        d="M8.5 24 15 8h2l6.5 16"
        fill="none"
        stroke={`url(#${id}-g)`}
        strokeWidth="2.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="m11.6 18.2 3 2.6 6.2-5.4"
        fill="none"
        className="stroke-ink"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function Logo({ className }: { className?: string }) {
  return (
    <span className={cx("inline-flex items-center gap-2.5", className)}>
      <LogoMarca />
      <span className="text-[19px] font-semibold tracking-[-0.03em]">
        Aval<span className="text-accent">.</span>
      </span>
    </span>
  );
}
