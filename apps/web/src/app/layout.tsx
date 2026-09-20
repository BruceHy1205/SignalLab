import { SiteHeader } from "@/components/SiteHeader";
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "signal — 机构推荐胜率",
  description: "个人投资研究平台",
};

const themeScript = `
(function() {
  try {
    var saved = localStorage.getItem('signal-theme');
    var theme = (saved === 'light' || saved === 'dark') ? saved : 'dark';
    document.documentElement.setAttribute('data-theme', theme);
  } catch (e) {
    document.documentElement.setAttribute('data-theme', 'dark');
  }
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      </head>
      <body>
        <SiteHeader />
        <main className="site-main">{children}</main>
      </body>
    </html>
  );
}
