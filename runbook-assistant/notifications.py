import requests
import os
from datetime import datetime


def send_discord_notification(webhook_url: str, message: str, title: str = "", color: int = 0x00ff00):
    """Send a notification to a Discord channel via webhook."""
    if not webhook_url:
        return False, "No webhook URL configured"

    embed = {
        "title": title or "Runbook Assistant Notification",
        "description": message,
        "color": color,
        "footer": {"text": f"Runbook Assistant • {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}"}
    }

    payload = {"embeds": [embed]}
    try:
        resp = requests.post(webhook_url, json=payload, timeout=10)
        if resp.status_code in (200, 204):
            return True, "Notification sent"
        return False, f"Discord returned {resp.status_code}: {resp.text}"
    except Exception as e:
        return False, str(e)


RISK_COLORS = {
    "low": 0x57F287,
    "medium": 0xFEE75C,
    "high": 0xED4245,
    "critical": 0x8B0000,
}


def notify_step_started(webhook_url: str, runbook: str, step_title: str, risk_level: str):
    color = RISK_COLORS.get(risk_level, 0x5865F2)
    msg = f"**Runbook:** {runbook}\n**Step:** {step_title}\n**Risk:** `{risk_level.upper()}`"
    return send_discord_notification(webhook_url, msg, "▶ Step Started", color)


def notify_step_failed(webhook_url: str, runbook: str, step_title: str, reason: str):
    msg = f"**Runbook:** {runbook}\n**Step:** {step_title}\n**Failure:** {reason}"
    return send_discord_notification(webhook_url, msg, "❌ Step Failed", 0xED4245)


def notify_execution_complete(webhook_url: str, runbook: str, status: str, summary: str):
    color = 0x57F287 if status == "completed" else 0xED4245
    icon = "✅" if status == "completed" else "❌"
    msg = f"**Runbook:** {runbook}\n**Status:** {status.upper()}\n\n{summary[:800]}"
    return send_discord_notification(webhook_url, msg, f"{icon} Execution {status.capitalize()}", color)
