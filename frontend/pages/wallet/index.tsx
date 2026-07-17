import { useState, useEffect } from "react";
import { api } from "../../lib/api";
import { useLanguage } from "../../lib/LanguageContext";
import { Wallet, DollarSign, Bitcoin } from "lucide-react";

export default function WalletPage() {
  const [balance, setBalance] = useState<any>(null);
  const { t } = useLanguage();

  useEffect(() => {
    api.getBalance().then(setBalance).catch(() => {});
  }, []);

  return (
    <div className="space-y-6">
      <div><h2 className="text-lg font-semibold text-white">{t("wallet.title")}</h2><p className="text-xs text-dark-400 mt-1">{t("wallet.subtitle")}</p></div>
      {balance && Object.keys(balance).length > 0 ? (
        <div className="grid gap-4">
          {Object.entries(balance).map(([currency, data]: [string, any]) => (
            <div key={currency} className="card">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${currency === "USDT" ? "bg-green/10" : currency === "BTC" ? "bg-orange-500/10" : "bg-dark-800"}`}>
                    {currency === "USDT" ? <DollarSign size={20} className="text-okx-green" /> :
                     currency === "BTC" ? <Bitcoin size={20} className="text-okx-yellow" /> :
                     <Wallet size={20} className="text-dark-400" />}
                  </div>
                  <div><h3 className="text-sm font-semibold text-white">{currency}</h3><p className="text-xs text-dark-400">{t("wallet.total")}: {data.total?.toFixed(currency === "BTC" ? 6 : 2)}</p></div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-bold font-mono text-white">{data.free?.toFixed(currency === "BTC" ? 6 : 2)}</div>
                  <div className="text-xs text-dark-400">{t("wallet.available")}</div>
                </div>
              </div>
              <div className="mt-3 pt-3 border-t border-dark-800 flex gap-4 text-xs text-dark-400">
                <span>{t("wallet.inOrders")}: {data.used?.toFixed(currency === "BTC" ? 6 : 2) || "0"}</span>
                <span>{t("wallet.total")}: {data.total?.toFixed(currency === "BTC" ? 6 : 2)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="card text-center py-12">
          <Wallet size={40} className="mx-auto mb-3 text-dark-600" />
          <p className="text-dark-400 text-sm">{t("wallet.none")}</p>
          <p className="text-dark-500 text-xs mt-1">{t("wallet.noneHint")}</p>
        </div>
      )}
    </div>
  );
}
