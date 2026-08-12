import { redirect } from "next/navigation";

/** Event stream removed from the product surface. */
export default function ActivityRedirect() {
  redirect("/app");
}
