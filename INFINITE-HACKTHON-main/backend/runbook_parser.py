import json
import re
import requests
from config import Config
from executor import detect_step_type

def parse_runbook(markdown_content):
    """
    Parses a markdown runbook into structured steps.
    Utilizes Ollama Prompt 3, with a regex fallback if Ollama is unavailable.
    """
    mock_ollama = Config.MOCK_OLLAMA
    ollama_url = Config.OLLAMA_API_URL
    model = Config.OLLAMA_MODEL

    if not mock_ollama:
        try:
            prompt = f"""You are a DevOps runbook parser AI with advanced Natural Language Processing (NLP) capabilities.

Given the following Markdown/text runbook content, extract all numbered steps.

For each step:
1. Identify if the step contains a command (inside backticks or explicitly written).
2. If the step does NOT contain a command in backticks but describes an executable action in natural language (e.g. "Check the disk space", "Restart nginx daemon", or a Database Query like "Get the count of all staged runs in the database"), you MUST use your Natural Language Processing (NLP) capability to automatically generate the correct SHELL/BASH command (e.g. `df -h`, `systemctl restart nginx`) or SQL query prefixed with 'SQL:' (e.g. `SQL: SELECT count(*) FROM runbook_runs`).
3. Set has_command to true if a command is either extracted or successfully generated via NLP.
4. If the step is strictly informational with no actionable operation, set command to an empty string and has_command to false.

Runbook content:
{markdown_content}

Respond ONLY in JSON format:
{{
  "steps": [
    {{
      "number": 1,
      "command": "the extracted or NLP-generated command",
      "description": "plain English description of what the step does",
      "has_command": true,
      "step_type": "SHELL"
    }}
  ]
}}"""

            headers = {"Content-Type": "application/json"}
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json" # Forces Ollama to output valid JSON
            }
            
            response = requests.post(f"{ollama_url}/api/generate", json=payload, headers=headers, timeout=15)
            if response.status_code == 200:
                res_data = response.json()
                raw_response = res_data.get("response", "").strip()
                parsed_json = json.loads(raw_response)
                if "steps" in parsed_json:
                    steps = parsed_json["steps"]
                    # Ensure step_type is detected for each step
                    for s in steps:
                        if not s.get("step_type") and s.get("command"):
                            s["step_type"] = detect_step_type(s["command"])
                        elif not s.get("step_type"):
                            s["step_type"] = "SHELL"
                    return steps
        except Exception as e:
            # Fall back to regex parser if API fails
            print(f"Ollama parsing failed: {e}. Falling back to rule-based parser.")
            
    return _parse_runbook_fallback(markdown_content)

def _parse_runbook_fallback(markdown_content):
    """
    Fallback parser using regex and NLP heuristics to extract steps from markdown.
    Works offline or when Ollama is unavailable.
    """
    steps = []
    lines = markdown_content.split('\n')
    
    # Matches: "1. Check", "Step 1:", "- 1. Check", "1) Check", "1 - Check"
    step_pattern = re.compile(r'^\s*(?:[-*]\s+)?(?:[Ss]tep\s+)?(\d+)[.):-]\s*(.*)$')
    cmd_pattern = re.compile(r'`([^`]+)`')

    for line in lines:
        match = step_pattern.match(line)
        if match:
            step_num = int(match.group(1))
            step_text = match.group(2).strip()
            
            # Check for commands in backticks
            cmd_match = cmd_pattern.search(step_text)
            if cmd_match:
                command = cmd_match.group(1).strip()
                has_command = True
                description = cmd_pattern.sub(f"'{command}'", step_text)
            else:
                # Basic Natural Language rule-based NLP extraction for fallback/tests
                lower_text = step_text.lower()
                command = ""
                has_command = False
                
                # Check for Database query keywords
                if "select" in lower_text or "database" in lower_text or "db query" in lower_text or "sql" in lower_text or "query" in lower_text:
                    if "count" in lower_text:
                        command = "SQL: SELECT count(*) FROM runbook_runs;"
                    elif "runs" in lower_text:
                        command = "SQL: SELECT * FROM runbook_runs LIMIT 10;"
                    else:
                        command = "SQL: SELECT * FROM sqlite_master WHERE type='table';"
                    has_command = True
                # Check for Shell/Bash command keywords
                elif "disk" in lower_text or "storage" in lower_text or "space" in lower_text or "df" in lower_text:
                    command = "df -h"
                    has_command = True
                elif "memory" in lower_text or "ram" in lower_text or "free" in lower_text:
                    command = "free -m"
                    has_command = True
                elif "restart" in lower_text or "stop" in lower_text or "start" in lower_text:
                    service_match = re.search(r'(nginx|mysql|postgres|apache|docker|daemon)', lower_text)
                    service = service_match.group(1) if service_match else "nginx"
                    if "restart" in lower_text:
                        action = "restart"
                    elif "stop" in lower_text:
                        action = "stop"
                    else:
                        action = "start"
                    command = f"systemctl {action} {service}"
                    has_command = True
                elif "list files" in lower_text or "show files" in lower_text or "directory" in lower_text:
                    command = "ls -la"
                    has_command = True
                elif "ping" in lower_text or "network" in lower_text:
                    command = "ping -c 3 google.com"
                    has_command = True
                elif "print" in lower_text or "echo" in lower_text:
                    echo_match = re.search(r'(?:print|echo)\s+[\'"]?([^\'"]+)[\'"]?', step_text, re.IGNORECASE)
                    msg = echo_match.group(1) if echo_match else "Hello Operator"
                    command = f"echo {msg}"
                    has_command = True

                description = step_text

            steps.append({
                "number": step_num,
                "command": command,
                "description": description,
                "has_command": has_command,
                "step_type": detect_step_type(command) if has_command else "SHELL"
            })
            
    # Sort steps by number just in case
    steps.sort(key=lambda s: s["number"])
    return steps
