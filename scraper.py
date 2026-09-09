import os
import sys
import re
import time
import urllib.request
import urllib.error
import logging
from typing import Optional, Dict, Any

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}

DEFAULT_URL = "https://dex.coinmarketcap.com/token/solana/poLisWXnNRwC6oBu1vHiuKQzFjGL4XDSu4g9qjz9qVk/"

def fetch_cmc_dex_data(url: str = DEFAULT_URL, max_retries: int = 3) -> Optional[Dict[str, Any]]:
    """
    CoinMarketCap DEX sayfasından POLIS token verilerini çeker ve ayrıştırır.
    """
    html_content = None
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    html_content = resp.read().decode("utf-8", errors="ignore")
                    break
                else:
                    logger.warning(f"Deneme {attempt}: HTTP {resp.status} döndü.")
        except Exception as e:
            logger.warning(f"Deneme {attempt}: Bağlantı hatası - {e}")
            if attempt < max_retries:
                time.sleep(2 * attempt)

    if not html_content:
        logger.error("CoinMarketCap DEX sayfası çekilemedi.")
        return None

    # Fiyat Ayrıştırma
    price_m = re.search(r'class=\"[^\"]*TopStats_price[^\"]*\">.*?(\$[\d\.,]+)', html_content, re.DOTALL)
    if not price_m:
        # Alternatif desen
        price_m = re.search(r'TopStats_price.*?(\$[\d\.,]+)', html_content, re.DOTALL)
    price = price_m.group(1) if price_m else None

    # 24s Değişim Ayrıştırma
    change_m = re.search(r'TopStats_percentageChange.*?href=\"#(caret-(?:up|down))\".*?([0-9\.]+\%)', html_content, re.DOTALL)
    if change_m:
        is_up = "up" in change_m.group(1).lower()
        direction_sign = "+" if is_up else "-"
        change_pct = f"{direction_sign}{change_m.group(2)}"
        is_positive = is_up
    else:
        # Caret olmadan sadece yüzde
        simple_change = re.search(r'TopStats_percentageChange.*?([0-9\.]+\%)', html_content, re.DOTALL)
        change_pct = simple_change.group(1) if simple_change else "N/A"
        is_positive = True

    # Piyasa Değeri (Market Cap)
    mc_m = re.search(r'MarketCapSelector_value.*?(\$[\d\.,]+[KMBkmb]?)', html_content, re.DOTALL)
    market_cap = mc_m.group(1) if mc_m else "N/A"

    # Likidite (Liquidity)
    liq_m = re.search(r'Liquidity.*?TopStats_liquidityValue.*?(\$[\d\.,]+[KMBkmb]?)', html_content, re.DOTALL)
    liquidity = liq_m.group(1) if liq_m else "N/A"

    # 24s Hacim (24h Volume)
    vol_m = re.search(r'24h Volume.*?(\$[\d\.,]+[KMBkmb]?)', html_content, re.DOTALL)
    volume_24h = vol_m.group(1) if vol_m else "N/A"

    if not price:
        logger.error("Fiyat bilgisi sayfada tespit edilemedi.")
        return None

    return {
        "token": "POLIS",
        "chain": "Solana",
        "price": price,
        "change_24h": change_pct,
        "is_positive": is_positive,
        "market_cap": market_cap,
        "liquidity": liquidity,
        "volume_24h": volume_24h,
        "url": url,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }

if __name__ == "__main__":
    print("CoinMarketCap DEX verisi çekiliyor...")
    data = fetch_cmc_dex_data()
    if data:
        print("\n=== ÇEKİLEN VERİLER ===")
        for k, v in data.items():
            print(f"{k}: {v}")
    else:
        print("Veri çekilemedi!")
