import { StrictMode, Suspense, lazy } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router";
import { MotionConfig } from "motion/react";
import "./index.css";
import { Layout } from "./components/Layout";
import { Landing } from "./pages/Landing";
import { NovoPedido } from "./pages/NovoPedido";
import { LaudoPage } from "./pages/LaudoPage";
import { NaoEncontrada } from "./pages/NaoEncontrada";

// recharts é ~⅔ do bundle — só carrega quando o painel abre.
const Dashboard = lazy(() => import("./pages/Dashboard").then((m) => ({ default: m.Dashboard })));

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MotionConfig reducedMotion="user">
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Landing />} />
            <Route path="novo" element={<NovoPedido />} />
            <Route path="laudos" element={<Suspense><Dashboard /></Suspense>} />
            <Route path="laudos/:id" element={<LaudoPage />} />
            <Route path="*" element={<NaoEncontrada />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </MotionConfig>
  </StrictMode>,
);
