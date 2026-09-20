"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useTheme } from "@/components/useTheme";

const NAV = [
  { href: "/", label: "推荐" },
  { href: "/leaderboard", label: "机构排行" },
  { href: "/portfolio", label: "模拟盘" },
  { href: "/agents", label: "Agent" },
  { href: "/live", label: "实盘确认" },
  { href: "/research", label: "研究" },
  { href: "/import", label: "导入" },
] as const;

function isActive(pathname: string, href: string) {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function SunIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
    </svg>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const { theme, toggle, mounted } = useTheme();

  return (
    <header className="site-header">
      <Link href="/" className="site-logo">
        signal
      </Link>
      <nav className="site-nav">
        {NAV.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            className={isActive(pathname, href) ? "active" : undefined}
          >
            {label}
          </Link>
        ))}
      </nav>
      <span className="site-nav-spacer" />
      <button
        type="button"
        className="theme-toggle"
        onClick={toggle}
        aria-label="切换主题"
        title={mounted ? (theme === "dark" ? "切换到亮色" : "切换到暗色护眼") : "切换主题"}
      >
        {mounted && theme === "dark" ? <SunIcon /> : <MoonIcon />}
      </button>
    </header>
  );
}
