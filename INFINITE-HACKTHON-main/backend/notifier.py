import requests
from config import Config

def send_discord_notification(event_type, event_details):
    """
    Generates a concise notification message using Ollama (Prompt 5)
    and sends it to the configured Discord Webhook URL.
    """
    webhook_url = Config.DISCORD_WEBHOOK_URL
    mock_ollama = Config.MOCK_OLLAMA
    ollama_url = Config.OLLAMA_API_URL
    model = Config.OLLAMA_MODEL

    content = ""
    if not mock_ollama:
        try:
            prompt = f"""You are a concise notification writer for a DevOps AI agent called ANTIGRAVITY.

Event: {event_type}
Details: {event_details}

Write a short Discord notification message (max 2 lines) that:
- States clearly what happened
- Uses relevant emoji (✅ for success, ⚠️ for warning, 🚀 for start, 🏁 for complete)
- Is easy to read on a phone at 2am

Respond in plain text only."""

            headers = {"Content-Type": "application/json"}
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            
            response = requests.post(f"{ollama_url}/api/generate", json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                res_data = response.json()
                content = res_data.get("response", "").strip()
        except Exception as e:
            print(f"Ollama notification generation failed: {e}. Falling back to template.")

    if not content:
        content = _format_notification_fallback(event_type, event_details)

    # Log to server console
    print(f"[Discord Webhook Payload] {content}")

    # Send to Discord Webhook if configured
    if webhook_url:
        try:
            payload = {"content": content}
            resp = requests.post(webhook_url, json=payload, timeout=5)
            return resp.status_code in [200, 204]
        except Exception as ex:
            print(f"Failed to post to Discord webhook: {ex}")
            return False
            
    return True

def _format_notification_fallback(event_type, event_details):
    """
    Formats Discord notifications locally using standard formatting rules.
    """
    event_upper = event_type.upper()
    
    if "START" in event_upper:
        return f"🚀 **ANTIGRAVITY**: Runbook run started: *{event_details}*."
    elif "COMPLETE" in event_upper or "FINISH" in event_upper:
        return f"🏁 **ANTIGRAVITY**: Runbook run completed: *{event_details}*."
    elif "WARNING" in event_upper or "RISKY" in event_upper or "APPROVAL" in event_upper:
        return f"⚠️ **ANTIGRAVITY**: Human approval needed: *{event_details}*."
    elif "SUCCESS" in event_upper:
        return f"✅ **ANTIGRAVITY**: Step completed: *{event_details}*."
    elif "FAILURE" in event_upper or "ERROR" in event_upper:
        return f"❌ **ANTIGRAVITY**: Error occurred: *{event_details}*."
    else:
        return f"ℹ️ **ANTIGRAVITY**: Event: {event_type} - {event_details}"
