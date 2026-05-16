import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import { NextResponse } from "next/server";

const isProtectedRoute = createRouteMatcher([
  "/dashboard(.*)",
  "/startups(.*)",
  "/chatbot(.*)",
  "/market-maps(.*)",
  "/integrations(.*)",
  "/onboarding(.*)",
  "/account(.*)",
]);

const isLoginRoute = createRouteMatcher(["/login"]);

export default clerkMiddleware(async (auth, req) => {
  const { userId } = await auth();

  if (isLoginRoute(req) && userId) {
    return NextResponse.redirect(new URL("/welcome-back", req.url));
  }

  if (isProtectedRoute(req) && !userId) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
});

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
