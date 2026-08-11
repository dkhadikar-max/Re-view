import { redirect } from "next/navigation";

/** Integrations UI removed from the product surface. */
export default function IntegrationsRedirect() {
  redirect("/app");
}
