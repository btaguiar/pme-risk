import { useEffect, useState } from "react";

export type Tema = "dark" | "light";
const CHAVE = "aval-tema";

export function useTema() {
  const [tema, setTema] = useState<Tema>(() =>
    document.documentElement.dataset.theme === "light" ? "light" : "dark",
  );

  useEffect(() => {
    document.documentElement.dataset.theme = tema;
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", tema === "dark" ? "#07090d" : "#f5f7f8");
    try {
      localStorage.setItem(CHAVE, tema);
    } catch {
      /* sem storage: vale só nesta sessão */
    }
  }, [tema]);

  return { tema, alternar: () => setTema((t) => (t === "dark" ? "light" : "dark")) };
}
