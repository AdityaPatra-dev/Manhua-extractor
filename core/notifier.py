import requests
from typing import Optional, Dict, Any
from database.db import get_setting

def dispatch_notification(
    title: str,
    message: str,
    series_title: Optional[str] = None,
    chapter_num: Optional[float] = None,
    series_cover: Optional[str] = None,
    chapter_url: Optional[str] = None,
    file_path: Optional[str] = None
) -> Dict[str, bool]:
    """
    Send notifications to all configured channels: Discord Webhook, Telegram Bot, Ntfy.
    """
    results = {}

    # 1. Discord Webhook
    discord_url = get_setting("discord_webhook_url")
    if discord_url and discord_url.strip().startswith("http"):
        try:
            embed = {
                "title": f"⚡ {title}",
                "description": message,
                "color": 6521575,  # Accent indigo
                "fields": []
            }
            if series_title:
                embed["fields"].append({"name": "Series", "value": series_title, "inline": True})
            if chapter_num:
                embed["fields"].append({"name": "Chapter", "value": str(chapter_num), "inline": True})
            if chapter_url:
                embed["fields"].append({"name": "Source Link", "value": f"[Open Chapter]({chapter_url})", "inline": False})
            if series_cover:
                embed["thumbnail"] = {"url": series_cover}

            payload = {
                "username": "Manhua Extractor Bot",
                "avatar_url": "https://raw.githubusercontent.com/feathericons/feather/master/icons/book-open.svg",
                "embeds": [embed]
            }
            resp = requests.post(discord_url.strip(), json=payload, timeout=10)
            results["discord"] = (resp.status_code in (200, 204))
        except Exception:
            results["discord"] = False

    # 2. Telegram Bot
    tg_token = get_setting("telegram_bot_token")
    tg_chat_id = get_setting("telegram_chat_id")
    if tg_token and tg_chat_id:
        try:
            tg_url = f"https://api.telegram.org/bot{tg_token.strip()}/sendMessage"
            text_lines = [
                f"<b>⚡ {title}</b>",
                message
            ]
            if series_title:
                text_lines.append(f"<b>Series:</b> {series_title}")
            if chapter_num:
                text_lines.append(f"<b>Chapter:</b> {chapter_num}")
            if chapter_url:
                text_lines.append(f"<a href='{chapter_url}'>Read Online</a>")

            payload = {
                "chat_id": tg_chat_id.strip(),
                "text": "\n".join(text_lines),
                "parse_mode": "HTML"
            }
            resp = requests.post(tg_url, json=payload, timeout=10)
            results["telegram"] = (resp.status_code == 200)
        except Exception:
            results["telegram"] = False

    # 3. Ntfy / Gotify Push
    ntfy_url = get_setting("ntfy_topic_url")
    if ntfy_url and ntfy_url.strip().startswith("http"):
        try:
            headers = {
                "Title": title,
                "Tags": "book,white_check_mark"
            }
            if chapter_url:
                headers["Click"] = chapter_url
            resp = requests.post(ntfy_url.strip(), data=message.encode("utf-8"), headers=headers, timeout=10)
            results["ntfy"] = (resp.status_code in (200, 204))
        except Exception:
            results["ntfy"] = False

    return results

def send_test_alert(channel: str, webhook_target: str) -> bool:
    """Send a test ping to verify webhook target configuration."""
    if channel == "discord":
        try:
            payload = {
                "username": "Manhua Extractor Bot",
                "content": "✅ **Test Alert:** Discord Webhook successfully connected to Universal Manhua Extractor!"
            }
            r = requests.post(webhook_target, json=payload, timeout=10)
            return r.status_code in (200, 204)
        except Exception:
            return False
    elif channel == "ntfy":
        try:
            headers = {"Title": "Manhua Extractor Ping", "Tags": "tada"}
            r = requests.post(webhook_target, data="Notification channel test successful!".encode("utf-8"), headers=headers, timeout=10)
            return r.status_code in (200, 204)
        except Exception:
            return False
    return False

