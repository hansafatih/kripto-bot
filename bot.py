import os
import sys
import time
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.request
import urllib.parse
from pathlib import Path

# Windows konsolunda UTF-8 / Emoji karakter desteği
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    CHECK_INTERVAL,
    UPDATE_MODE,
    POLIS_URL,
    ATLAS_URL,
)
from scraper import fetch_cmc_dex_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("TokenBot")

STATE_FILE = Path(__file__).parent / "last_message_id.txt"
LAST_PRICES_FILE = Path(__file__).parent / "last_prices.json"


class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"POLIS/ATLAS Price Bot Running 24/7!")

    def log_message(self, format, *args):
        pass


def run_health_server():
    port = int(os.getenv("PORT", 8080))
    try:
        server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
        logger.info(f"Bulut Web Portu aktif edildi: {port}")
        server.serve_forever()
    except Exception as e:
        logger.warning(f"Web sunucusu baslatilamadi: {e}")


def run_self_ping_loop():
    """Render'ın 15 dakikalık uyku moduna geçmesini önlemek için her 10 dakikada bir kendi kendine ping atar."""
    time.sleep(30)
    while True:
        url = os.getenv("RENDER_EXTERNAL_URL", "https://kripto-bot-hbos.onrender.com")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "SelfPinger/1.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                logger.info(f"Kendi kendine ping başarılı (HTTP {resp.status}) - Uyku modu engellendi.")
        except Exception as e:
            logger.warning(f"Self-ping uyarısı: {e}")
        time.sleep(600)  # Her 10 dakikada bir (15 dk sınırının altında)


def load_last_prices() -> dict:
    if LAST_PRICES_FILE.exists():
        try:
            return json.loads(LAST_PRICES_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_last_prices(prices: dict):
    try:
        LAST_PRICES_FILE.write_text(json.dumps(prices), encoding="utf-8")
    except Exception as e:
        logger.warning(f"Fiyatlar dosyaya kaydedilemedi: {e}")


def format_single_price(raw_val: str, prev_val: float | None) -> tuple[str, float | None]:
    """Tek bir token fiyatını ayrıştırıp değişim emojisiyle döndürür."""
    clean = str(raw_val).replace("$", "").replace(",", "").strip()
    try:
        curr_float = float(clean)
    except ValueError:
        curr_float = None

    display = f"{clean}$"
    if curr_float is not None and prev_val is not None:
        if curr_float > prev_val:
            display += " 🟢"
        elif curr_float < prev_val:
            display += " 🔻"

    return display, curr_float


def build_combined_message(atlas_raw: str, polis_raw: str, prev_prices: dict) -> tuple[str, dict]:
    """
    atlas: 0.0001411$ [🟢/🔻]
    polis: 0.009581$ [🟢/🔻]
    formatında mesaj üretir.
    """
    atlas_display, new_atlas = format_single_price(atlas_raw, prev_prices.get("atlas"))
    polis_display, new_polis = format_single_price(polis_raw, prev_prices.get("polis"))

    updated_prices = dict(prev_prices)
    if new_atlas is not None:
        updated_prices["atlas"] = new_atlas
    if new_polis is not None:
        updated_prices["polis"] = new_polis

    text = f"atlas: {atlas_display}\npolis: {polis_display}"
    return text, updated_prices


def telegram_api_request(endpoint: str, payload: dict) -> dict:
    """Telegram Bot API'ye JSON POST isteği gönderir."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="ignore")
        try:
            return json.loads(error_body)
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"ok": False, "description": str(e)}


def check_bot_credentials() -> bool:
    """Bot tokeninin doğruluğunu test eder."""
    res = telegram_api_request("getMe", {})
    if res.get("ok"):
        bot_user = res.get("result", {}).get("username", "BilinmeyenBot")
        logger.info(f"Telegram Bot bağlantısı başarılı! Bot Adı: @{bot_user}")
        return True
    else:
        logger.error(f"Telegram Bot bağlantı hatası: {res.get('description')}")
        return False


def send_new_message(text: str) -> int | None:
    """Yeni mesaj gönderir ve mesaj ID'sini döner."""
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    res = telegram_api_request("sendMessage", payload)
    if res.get("ok"):
        msg_id = res["result"]["message_id"]
        logger.info(f"Yeni mesaj iletildi (Message ID: {msg_id})")
        return msg_id
    else:
        logger.error(f"Mesaj gönderilemedi: {res.get('description')}")
        return None


def edit_existing_message(message_id: int, text: str) -> bool:
    """Mevcut mesajı günceller."""
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    res = telegram_api_request("editMessageText", payload)
    if res.get("ok"):
        logger.info(f"Mesaj güncellendi (Message ID: {message_id})")
        return True
    else:
        desc = res.get("description", "")
        if "message is not modified" in desc.lower():
            # İçerik değişmediğinde Telegram bu yanıtı döner, normal bir durumdur.
            logger.info("Fiyat/zaman bilgisi değişmediği için düzenleme atlandı.")
            return True
        logger.warning(f"Mesaj güncellenemedi: {desc}")
        return False


def load_last_message_id() -> int | None:
    if STATE_FILE.exists():
        try:
            return int(STATE_FILE.read_text().strip())
        except Exception:
            return None
    return None


def save_last_message_id(message_id: int):
    try:
        STATE_FILE.write_text(str(message_id))
    except Exception as e:
        logger.warning(f"Message ID dosyaya kaydedilemedi: {e}")


def main():
    print("=" * 60)
    print("  CoinMarketCap DEX - POLIS Token Fiyat Takip Telegram Botu")
    print("=" * 60)

def wait_and_detect_chat_id(timeout_seconds: int = 60) -> int | None:
    """Kullanıcı bota /start yazana veya kanala ekleyene kadar bekleyip Chat ID'yi otomatik yakalar."""
    logger.info("Telegram'dan mesaj veya kanal aktivitesi bekleniyor...")
    print("------------------------------------------------------------")
    print("👉 Telegram'da @polisssssss_bot hesabını açıp /start yazın")
    print("   VEYA botu mesaj göndermek istediğiniz kanala/gruba ekleyin.")
    print("------------------------------------------------------------")

    start_time = time.time()
    last_update_id = 0

    while time.time() - start_time < timeout_seconds:
        res = telegram_api_request("getUpdates", {"offset": last_update_id + 1, "timeout": 5})
        if res.get("ok"):
            updates = res.get("result", [])
            for u in updates:
                last_update_id = u.get("update_id", last_update_id)
                chat = None
                if "message" in u:
                    chat = u["message"].get("chat")
                elif "channel_post" in u:
                    chat = u["channel_post"].get("chat")
                elif "my_chat_member" in u:
                    chat = u["my_chat_member"].get("chat")

                if chat and "id" in chat:
                    detected_id = chat["id"]
                    title = chat.get("title") or chat.get("username") or chat.get("first_name", "")
                    logger.info(f"Hedef sayfa/sohbet tespit edildi! ID: {detected_id} ({title})")
                    return detected_id
        time.sleep(2)
    return None


def update_env_chat_id(chat_id: int | str):
    """Bulunan Chat ID'yi .env dosyasına kalıcı olarak yazar."""
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        content = env_file.read_text(encoding="utf-8")
        import re
        new_content = re.sub(r'TELEGRAM_CHAT_ID=.*', f'TELEGRAM_CHAT_ID={chat_id}', content)
        env_file.write_text(new_content, encoding="utf-8")
        logger.info(".env dosyası yeni Chat ID ile güncellendi.")


def main():
    global TELEGRAM_CHAT_ID
    print("=" * 60)
    print("  CoinMarketCap DEX - POLIS Token Fiyat Takip Telegram Botu")
    print("=" * 60)

    if not TELEGRAM_BOT_TOKEN or "BURAYA_" in TELEGRAM_BOT_TOKEN:
        print("\n[!] DİKKAT: Telegram Bot Token bulunamadı!")
        print("Lütfen .env dosyasındaki TELEGRAM_BOT_TOKEN değerini doldurun.\n")
        sys.exit(1)

    if not check_bot_credentials():
        print("[!] Bot token geçersiz veya Telegram sunucusuna erişilemiyor.")
        sys.exit(1)

    # Eğer CHAT_ID henüz girilmemişse otomatik tespit et
    if not TELEGRAM_CHAT_ID or "BURAYA_" in TELEGRAM_CHAT_ID:
        detected_id = wait_and_detect_chat_id(timeout_seconds=90)
        if detected_id:
            TELEGRAM_CHAT_ID = str(detected_id)
            update_env_chat_id(TELEGRAM_CHAT_ID)
        else:
            print("\n[!] Belirtilen sürede Telegram'dan bir mesaj alınamadı.")
            print("Lütfen bota (/start) gönderdikten sonra veya .env dosyasına Chat ID yazıp tekrar çalıştırın.\n")
            sys.exit(1)

    # Bulut / Render sağlık sunucusunu ve otomatik uyku önleyici pingi başlat
    threading.Thread(target=run_health_server, daemon=True).start()
    threading.Thread(target=run_self_ping_loop, daemon=True).start()

    logger.info(f"POLIS URL: {POLIS_URL}")
    logger.info(f"ATLAS URL: {ATLAS_URL}")
    logger.info(f"Kontrol Sıklığı: Her {CHECK_INTERVAL} saniyede bir")
    logger.info(f"Çalışma Modu: {UPDATE_MODE.upper()}")

    last_msg_id = load_last_message_id() if UPDATE_MODE == "edit" else None
    prev_prices = load_last_prices()

    while True:
        try:
            logger.info("ATLAS ve POLIS verileri CoinMarketCap DEX'ten çekiliyor...")
            atlas_data = fetch_cmc_dex_data(ATLAS_URL)
            polis_data = fetch_cmc_dex_data(POLIS_URL)

            if atlas_data or polis_data:
                atlas_raw = atlas_data.get("price", "N/A") if atlas_data else "N/A"
                polis_raw = polis_data.get("price", "N/A") if polis_data else "N/A"

                message_text, prev_prices = build_combined_message(atlas_raw, polis_raw, prev_prices)
                save_last_prices(prev_prices)

                if UPDATE_MODE == "edit":
                    success = False
                    if last_msg_id:
                        success = edit_existing_message(last_msg_id, message_text)
                    
                    if not success:
                        new_id = send_new_message(message_text)
                        if new_id:
                            last_msg_id = new_id
                            save_last_message_id(new_id)
                else:
                    send_new_message(message_text)
            else:
                logger.warning("Veriler çekilemedi, bir sonraki periyotta tekrar denenecek.")

        except KeyboardInterrupt:
            logger.info("Bot kullanıcı tarafından durduruldu (Ctrl+C). Çıkılıyor...")
            break
        except Exception as e:
            logger.error(f"Beklenmeyen döngü hatası: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
