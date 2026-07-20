// v1.3 U8: App Router 根布局 — Pages Router 共存
import type { Metadata } from "next";
import { LanguageProvider } from "../lib/LanguageContext";
import "../styles/globals.css";

export const metadata: Metadata = {
  title: "AI Quant Trade",
  description: "AI 量化交易系统 - OKX",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <LanguageProvider>
          <main className="min-h-screen bg-dark-950">{children}</main>
        </LanguageProvider>
      </body>
    </html>
  );
}
