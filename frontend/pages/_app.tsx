import type { AppProps } from "next/app";
import Layout from "../components/Layout";
import { LanguageProvider } from "../lib/LanguageContext";
import { Toaster } from "react-hot-toast";
import "../styles/globals.css";

export default function App({ Component, pageProps }: AppProps) {
  return (
    <LanguageProvider>
      <Layout>
        <Component {...pageProps} />
        <Toaster
          position="top-right"
          toastOptions={{
            duration: 4000,
            style: { background: "#1a1a1a", color: "#eaecef", border: "1px solid #262626", fontSize: "13px" },
            success: { iconTheme: { primary: "#00c076", secondary: "#000" } },
            error: { iconTheme: { primary: "#f6465d", secondary: "#000" } },
          }}
        />
      </Layout>
    </LanguageProvider>
  );
}
