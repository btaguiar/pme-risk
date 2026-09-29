import { ArrowLeft } from "lucide-react";
import { Container } from "../components/Layout";
import { ButtonLink } from "../components/ui";

export function NaoEncontrada() {
  return (
    <Container className="flex flex-col items-center py-28 text-center">
      <p className="num text-7xl font-medium tracking-tighter text-gradient">404</p>
      <h1 className="mt-4 text-2xl font-semibold">Página não encontrada</h1>
      <p className="mt-2 text-muted">O endereço não existe ou foi movido.</p>
      <ButtonLink to="/" variante="secundario" className="mt-8">
        <ArrowLeft className="size-4" /> Voltar ao início
      </ButtonLink>
    </Container>
  );
}
