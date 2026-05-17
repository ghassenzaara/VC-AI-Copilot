"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useClerk, useUser } from "@clerk/nextjs";
import { Bell, Search, ChevronDown, LogOut, UserCircle } from "lucide-react";
import { Logo } from "./logo";
import { cn } from "@/lib/utils";
import { useApi } from "@/lib/use-api";
import type { StartupSummary } from "@/lib/types";
import { PipelinePill } from "./badges";

const TABS = [
  { href: "/dashboard", label: "Dashboard" },
  { href: "/startups", label: "Startups" },
  { href: "/chatbot", label: "Chatbot" },
  { href: "/market-maps", label: "Market Maps" },
  { href: "/integrations", label: "Integrations" },
];

function getInitials(name: string | null | undefined, email: string | null | undefined) {
  if (name) {
    const parts = name.trim().split(/\s+/).filter(Boolean);
    if (parts.length === 1) return parts[0]!.slice(0, 2).toUpperCase();
    return (parts[0]![0]! + parts[parts.length - 1]![0]!).toUpperCase();
  }
  if (email) return email.slice(0, 2).toUpperCase();
  return "??";
}

export function TopNav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoaded } = useUser();
  const { signOut } = useClerk();

  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  // Global search state
  const [query, setQuery] = useState("");
  const [searchOpen, setSearchOpen] = useState(false);
  const [activeIdx, setActiveIdx] = useState(0);
  const searchRef = useRef<HTMLDivElement>(null);

  // Reset query when navigating
  useEffect(() => {
    setSearchOpen(false);
    setQuery("");
  }, [pathname]);

  // Cache the companies list once; refresh on focus so post-extraction adds appear.
  const api = useApi();
  const [companies, setCompanies] = useState<StartupSummary[]>([]);
  useEffect(() => {
    if (!api.isReady) return;
    let cancelled = false;
    api
      .fetchCompanies()
      .then((rows) => {
        if (!cancelled) setCompanies(rows);
      })
      .catch(() => {
        if (!cancelled) setCompanies([]);
      });
    return () => {
      cancelled = true;
    };
  }, [api]);

  const results = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return companies
      .filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          (s.sector ?? "").toLowerCase().includes(q) ||
          (s.one_liner ?? "").toLowerCase().includes(q) ||
          s.tags.some((t) => t.toLowerCase().includes(q)),
      )
      .slice(0, 6);
  }, [query, companies]);

  useEffect(() => {
    setActiveIdx(0);
  }, [query]);

  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!searchOpen) return;
    function onClick(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setSearchOpen(false);
      }
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setSearchOpen(false);
        setQuery("");
      }
    }
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [searchOpen]);

  const displayName =
    user?.fullName ??
    [user?.firstName, user?.lastName].filter(Boolean).join(" ") ??
    null;
  const email = user?.primaryEmailAddress?.emailAddress ?? null;
  const initials = getInitials(displayName, email);

  return (
    <header className="sticky top-0 z-30 bg-bg-base/80 backdrop-blur border-b border-line">
      <div className="max-w-[1400px] mx-auto px-6 h-14 flex items-center gap-6">
        <Link href="/dashboard" className="shrink-0">
          <Logo />
        </Link>

        <nav className="flex items-center gap-1 ml-2">
          {TABS.map((t) => {
            const active =
              pathname === t.href || pathname?.startsWith(t.href + "/");
            return (
              <Link
                key={t.href}
                href={t.href}
                className={cn("nav-tab", active && "nav-tab-active")}
              >
                {t.label}
              </Link>
            );
          })}
        </nav>

        <div className="flex-1" />

        <div className="relative hidden md:block" ref={searchRef}>
          <div
            className={cn(
              "flex items-center gap-2 bg-bg-card border rounded-full px-3 py-1.5 text-sm w-64 transition",
              searchOpen ? "border-ink/30" : "border-line",
            )}
          >
            <Search size={14} className="text-ink-faint" />
            <input
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSearchOpen(true);
              }}
              onFocus={() => setSearchOpen(true)}
              onKeyDown={(e) => {
                if (!results.length) return;
                if (e.key === "ArrowDown") {
                  e.preventDefault();
                  setActiveIdx((i) => Math.min(i + 1, results.length - 1));
                } else if (e.key === "ArrowUp") {
                  e.preventDefault();
                  setActiveIdx((i) => Math.max(i - 1, 0));
                } else if (e.key === "Enter") {
                  e.preventDefault();
                  const pick = results[activeIdx];
                  if (pick) {
                    router.push(`/startups/${pick.id}`);
                    setSearchOpen(false);
                    setQuery("");
                  }
                }
              }}
              placeholder="Search companies, sectors, tags…"
              className="bg-transparent outline-none flex-1 text-ink placeholder:text-ink-faint"
            />
            {query && (
              <button
                type="button"
                onClick={() => {
                  setQuery("");
                  setSearchOpen(false);
                }}
                className="text-[10px] text-ink-faint px-1.5 py-0.5 rounded bg-bg-subtle border border-line"
              >
                esc
              </button>
            )}
          </div>

          {searchOpen && query.trim() && (
            <div className="absolute right-0 mt-2 w-[28rem] rounded-xl bg-bg-card border border-line shadow-elev z-40 overflow-hidden">
              {results.length === 0 ? (
                <div className="p-4 text-sm text-ink-muted">
                  No matches for{" "}
                  <span className="text-ink font-medium">“{query}”</span>.
                </div>
              ) : (
                <>
                  <div className="px-3 py-2 text-[10px] uppercase tracking-wider text-ink-faint border-b border-line">
                    Startups · {results.length}
                  </div>
                  <div className="max-h-80 overflow-y-auto py-1">
                    {results.map((s, i) => (
                      <button
                        key={s.id}
                        onMouseEnter={() => setActiveIdx(i)}
                        onClick={() => {
                          router.push(`/startups/${s.id}`);
                          setSearchOpen(false);
                          setQuery("");
                        }}
                        className={cn(
                          "w-full text-left px-3 py-2.5 flex items-start gap-3 transition",
                          i === activeIdx ? "bg-bg-subtle" : "hover:bg-bg-subtle/60",
                        )}
                      >
                        <div className="h-8 w-8 rounded-lg bg-bg-subtle border border-line flex items-center justify-center text-xs font-semibold text-ink shrink-0">
                          {s.name[0]}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-ink truncate">
                              {s.name}
                            </span>
                            <span className="text-[11px] text-ink-faint">
                              · {s.sector}
                            </span>
                          </div>
                          <div className="text-xs text-ink-muted truncate">
                            {s.one_liner}
                          </div>
                        </div>
                        <div className="shrink-0">
                          <PipelinePill stage={s.pipeline_stage} />
                        </div>
                      </button>
                    ))}
                  </div>
                  <div className="px-3 py-2 border-t border-line text-[11px] text-ink-faint flex items-center justify-between">
                    <span>
                      <kbd className="px-1 py-0.5 rounded bg-bg-subtle border border-line text-ink-muted">
                        ↵
                      </kbd>{" "}
                      to open
                    </span>
                    <Link
                      href={`/startups`}
                      onClick={() => {
                        setSearchOpen(false);
                        setQuery("");
                      }}
                      className="text-ink-muted hover:text-ink"
                    >
                      Browse all →
                    </Link>
                  </div>
                </>
              )}
            </div>
          )}
        </div>

        <button className="btn-ghost relative" aria-label="Notifications">
          <Bell size={16} />
          <span className="absolute top-1.5 right-2.5 h-1.5 w-1.5 rounded-full bg-accent-greenInk" />
        </button>

        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-haspopup="menu"
            aria-expanded={open}
            className="flex items-center gap-2 rounded-full bg-bg-card border border-line pl-1 pr-2.5 py-1 hover:border-ink/20 transition"
          >
            <div className="h-6 w-6 rounded-full bg-accent-green/60 flex items-center justify-center text-[11px] font-semibold text-accent-greenInk overflow-hidden">
              {user?.imageUrl ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={user.imageUrl}
                  alt=""
                  className="h-full w-full object-cover"
                />
              ) : (
                <span>{isLoaded ? initials : "··"}</span>
              )}
            </div>
            <span className="text-sm text-ink hidden sm:block max-w-[140px] truncate">
              {isLoaded ? (displayName ?? email ?? "Account") : "Loading…"}
            </span>
            <ChevronDown size={14} className="text-ink-muted" />
          </button>

          {open && (
            <div
              role="menu"
              className="absolute right-0 mt-2 w-64 rounded-xl bg-bg-card border border-line shadow-elev py-1.5 z-40"
            >
              <div className="px-3 py-2.5 border-b border-line">
                <div className="text-sm font-medium text-ink truncate">
                  {displayName ?? "Account"}
                </div>
                {email && (
                  <div className="text-xs text-ink-muted truncate">{email}</div>
                )}
              </div>

              <Link
                href="/account"
                role="menuitem"
                onClick={() => setOpen(false)}
                className="flex items-center gap-2 px-3 py-2 text-sm text-ink hover:bg-bg-subtle"
              >
                <UserCircle size={14} className="text-ink-muted" />
                Account settings
              </Link>

              <button
                type="button"
                role="menuitem"
                onClick={async () => {
                  setOpen(false);
                  await signOut();
                  router.push("/login");
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-ink hover:bg-bg-subtle"
              >
                <LogOut size={14} className="text-ink-muted" />
                Sign out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
