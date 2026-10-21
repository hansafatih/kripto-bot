import os
import sys
import re
import time
import json
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
    POLIS ve ATLAS token verilerini ceker:
    1. DexScreener API (Guvenilir on-chain Solana DEX verisi, Cloudflare takilmaz, kesintisiz calisir)
    2. CoinMarketCap DEX __NEXT_DATA__ JSON (Yedek kaynak)
    """
    addr = url.rstrip("/").split("/")[-1]

    # --- 1. DexScreener API (Birincil ve Hizli Cozum) ---
    for attempt in range(1, max_retries + 1):
        try:
            api_url = f"https://api.dexscreener.com/latest/dex/tokens/{addr}"
            req = urllib.request.Request(api_url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode("utf-8"))
                    pairs = data.get("pairs") or []
                    if pairs:
                        # En yuksek likiditeye sahip ana havuzu sec (Raydium / Orca)
                        pairs.sort(key=lambda p: float((p.get("liquidity") or {}).get("usd", 0) or 0), reverse=True)
                        top = pairs[0]
                        price = top.get("priceUsd")
                        change = top.get("priceChange", {}).get("h24")
                        symbol = top.get("baseToken", {}).get("symbol", "TOKEN")
                        if price:
                            return {
                                "token": symbol,
                                "chain": "Solana",
                                "price": f"${price}",
                                "change_24h": f"{change}%" if change is not None else "0%",
                                "is_positive": float(change or 0) >= 0,
                                "market_cap": "N/A",
                                "liquidity": "N/A",
                                "volume_24h": "N/A",
                                "url": url,
                                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                            }
        except Exception as e:
            logger.warning(f"DexScreener deneme {attempt} ({addr}): {e}")
            if attempt < max_retries:
                time.sleep(1)

    # --- 2. CoinMarketCap DEX __NEXT_DATA__ JSON (Yedek) ---
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=12) as resp:
                if resp.status == 200:
                    html_content = resp.read().decode("utf-8", errors="ignore")
                    m = re.search(r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>', html_content, re.DOTALL)
                    if m:
                        ndata = json.loads(m.group(1))
                        queries = ndata.get("props", {}).get("pageProps", {}).get("dehydratedState", {}).get("queries", [])
                        for q in queries:
                            k = q.get("queryKey", [])
                            if isinstance(k, list) and len(k) > 2 and k[0] == "dex-token-info":
                                tdata = q.get("state", {}).get("data", {})
                                p = tdata.get("p")
                                sym = tdata.get("sym")
                                if p:
                                    return {
                                        "token": sym,
                                        "chain": "Solana",
                                        "price": f"${p}",
                                        "change_24h": "0%",
                                        "is_positive": True,
                                        "market_cap": "N/A",
                                        "liquidity": "N/A",
                                        "volume_24h": "N/A",
                                        "url": url,
                                        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                                    }
        except Exception as e:
            logger.warning(f"CoinMarketCap deneme {attempt} ({url}): {e}")
            if attempt < max_retries:
                time.sleep(1)

    logger.error(f"Fiyat bilgisi cekilemedi: {url}")
    return None

if __name__ == "__main__":
    print("POLIS ve ATLAS verileri cekiliyor...")
    p = fetch_cmc_dex_data("https://dex.coinmarketcap.com/token/solana/poLisWXnNRwC6oBu1vHiuKQzFjGL4XDSu4g9qjz9qVk/")
    a = fetch_cmc_dex_data("https://dex.coinmarketcap.com/token/solana/ATLASXmbPQxBUYbxPsV97usA3fPQYEqzQBUHgiFCUsXx/")
    print("\nPOLIS:", p)
    print("ATLAS:", a)
