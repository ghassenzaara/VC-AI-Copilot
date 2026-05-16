import { TopNav } from "@/components/top-nav";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen flex flex-col">
      <TopNav />
      <main className="flex-1">
        <div className="max-w-[1400px] mx-auto px-6 py-8">{children}</div>
      </main>
    </div>
  );
}
