import requests
from config import Config

def generate_audit_report(runbook_name, total_steps, executed, skipped, errors, duration):
    """
    Generates a professional post-run audit summary using Ollama (Prompt 6).
    Falls back to a standard audit template if Ollama is unavailable.
    """
    mock_ollama = Config.MOCK_OLLAMA
    ollama_url = Config.OLLAMA_API_URL
    model = Config.OLLAMA_MODEL

    report_text = ""
    if not mock_ollama:
        try:
            prompt = f"""You are ANTIGRAVITY, an AI DevOps audit assistant.

A runbook run just completed with these results:
- Runbook name: {runbook_name}
- Total steps: {total_steps}
- Steps executed: {executed}
- Steps skipped: {skipped}
- Any errors: {errors}
- Time taken: {duration}

Generate a professional post-run audit summary that includes:
1. Overall run status (success / partial / failed)
2. What was accomplished
3. What was skipped and why it matters
4. Recommended follow-up actions

Keep it under 150 words. Use plain English. No markdown headers."""

            headers = {"Content-Type": "application/json"}
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            
            response = requests.post(f"{ollama_url}/api/generate", json=payload, headers=headers, timeout=10)
            if response.status_code == 200:
                res_data = response.json()
                report_text = res_data.get("response", "").strip()
        except Exception as e:
            print(f"Ollama audit report generation failed: {e}. Falling back to template.")

    if not report_text:
        report_text = _generate_report_fallback(runbook_name, total_steps, executed, skipped, errors, duration)

    return report_text

def _generate_report_fallback(runbook_name, total_steps, executed, skipped, errors, duration):
    """
    Generates a templated audit report locally.
    """
    status = "success"
    if errors > 0:
        status = "failed"
    elif skipped > 0 or executed < total_steps:
        status = "partial"
        
    accomplished = "All targeted runbook verification and operational tasks completed successfully." if status == "success" else "A portion of the operational runbook steps were completed."
    
    skipped_text = "None."
    if skipped > 0:
        skipped_text = f"{skipped} steps were skipped because they failed verification, safety limits, or were denied by the operator. Skipping these ensures system stability but requires manual check-up of those pending steps."

    follow_up = "Monitor the system health logs. If steps were skipped or failed, manually review logs and complete outstanding steps."

    return (
        f"Post-run audit summary for runbook '{runbook_name}'.\n"
        f"Overall run status: {status.upper()}.\n"
        f"Accomplished: {accomplished} Total steps: {total_steps}, executed: {executed}, duration: {duration}.\n"
        f"Skipped steps details: {skipped_text}\n"
        f"Errors encountered: {errors}.\n"
        f"Recommended follow-up actions: {follow_up}"
    )
