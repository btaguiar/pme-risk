import { NavLink, Outlet, useLocation } from "react-router";
import { AnimatePresence, motion } from "motion/react";
import { FilePlus2, LayoutDashboard, Moon, Sun } from "lucide-react";
import { Link } from "react-router";
import { Logo } from "./Logo";
import { cx, ButtonLink } from "./ui";
import { useTema } from "../lib/theme";
import { useEffect } from "react";

const NAV = [
  { to: "/novo", rotulo: "Novo laudo", Icone: FilePlus2 },
  { to: "/laudos", rotulo: "Laudos", Icone: LayoutDashboard },
];

export function Layout() {
  const { tema, alternar } = useTema();
  const local = useLocation();
  const landing = local.pathname === "/";

  useEffect(() => {
    window.scrollTo({ top: 0 });
  }, [local.pathname]);

  return (
    <div className="relative flex min-h-dvh flex-col overflow-x-clip">
      {/* Atmosfera: brilho radial + grade sutil */}
      <div aria-hidden className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-[720px]">
        <div className="grid-bg absolute inset-0 opacity-60" />
        <div className="absolute left-1/2 top-[-280px] h-[620px] w-[1100px] -translate-x-1/2 rounded-full bg-[radial-gradient(closest-side,var(--c-glow),transparent)]" />
        <div className="absolute right-[-200px] top-[80px] h-[420px] w-[520px] rounded-full bg-[radial-gradient(closest-side,var(--c-glow-2),transparent)]" />
      </div>

      <header className="sticky top-0 z-30 border-b border-line bg-bg/70 backdrop-blur-xl">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6">
          <Link to="/" aria-label="Aval — início" className="rounded-lg">
            <Logo />
          </Link>

          <nav aria-label="Principal" className="flex items-center gap-1">
            {NAV.map(({ to, rotulo, Icone }) => (
              <NavLink
                key={to}
                to={to}
                className={({ isActive }) =>
                  cx(
                    "relative flex h-9 items-center gap-2 rounded-lg px-3 text-sm font-medium transition-colors",
                    isActive ? "text-ink" : "text-muted hover:text-ink",
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && (
                      <motion.span
                        layoutId="nav-ativo"
                        className="absolute inset-0 -z-10 rounded-lg bg-surface-2 ring-1 ring-line"
                        transition={{ type: "spring", bounce: 0.2, duration: 0.5 }}
                      />
                    )}
                    <Icone className="size-4" />
                    <span className="hidden sm:inline">{rotulo}</span>
                  </>
                )}
              </NavLink>
            ))}
            <span className="mx-1.5 h-5 w-px bg-line" />
            <button
              type="button"
              onClick={alternar}
              aria-label={tema === "dark" ? "Mudar para tema claro" : "Mudar para tema escuro"}
              className="grid size-9 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-ink"
            >
              <AnimatePresence mode="wait" initial={false}>
                <motion.span
                  key={tema}
                  initial={{ rotate: -90, opacity: 0, scale: 0.6 }}
                  animate={{ rotate: 0, opacity: 1, scale: 1 }}
                  exit={{ rotate: 90, opacity: 0, scale: 0.6 }}
                  transition={{ duration: 0.2 }}
                >
                  {tema === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
                </motion.span>
              </AnimatePresence>
            </button>
            {landing && (
              <ButtonLink to="/novo" tamanho="sm" className="ml-2 hidden md:inline-flex">
                Gerar laudo
              </ButtonLink>
            )}
          </nav>
        </div>
      </header>

      <main id="conteudo" className="flex-1">
        <AnimatePresence mode="wait">
          <motion.div
            key={local.pathname}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          >
            <Outlet />
          </motion.div>
        </AnimatePresence>
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-8 text-sm text-muted sm:px-6 md:flex-row md:items-center md:justify-between">
          <div className="flex items-center gap-3">
            <Logo className="scale-90 origin-left" />
            <span className="text-faint">·</span>
            <span className="text-faint">pme-risk</span>
          </div>
          <div className="max-w-2xl space-y-1 md:text-right">
            <p>PD vem do modelo, nunca do LLM. Toda afirmação carrega evidência. A decisão final é humana.</p>
            <p className="text-xs text-faint">
              Projeto de portfólio. Modelo treinado em PME dos EUA (SBA 7(a)) e ajustado ao risco relativo brasileiro
              (SCR.data) — não use para decisão de crédito real. Use apenas dados fictícios.
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}

export function Container({ className, children }: { className?: string; children: React.ReactNode }) {
  return <div className={cx("mx-auto w-full max-w-7xl px-4 sm:px-6", className)}>{children}</div>;
}
