import { auth } from "@clerk/nextjs/server";
import { redirect } from "next/navigation";
import { AlreadySignedIn } from "@/components/already-signed-in";

export default async function WelcomeBackPage() {
  const { userId } = await auth();
  if (!userId) {
    redirect("/login");
  }
  return <AlreadySignedIn />;
}
