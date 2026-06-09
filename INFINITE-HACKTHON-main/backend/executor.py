import re
import subprocess
import os
import sys
from config import Config

# ─────────────────────────────────────────────
# Step type detection
# ─────────────────────────────────────────────

REST_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"}

def detect_step_type(command):
    """
    Detects the execution type of a step command.
    Returns one of: SHELL, REST_API, DB_QUERY, CLOUD_CLI
    """
    if not command or not command.strip():
        return "SHELL"

    cmd = command.strip()
    first_word = cmd.split()[0].upper()

    # REST API: starts with HTTP method + URL
    if first_word in REST_METHODS and len(cmd.split()) >= 2:
        second = cmd.split()[1]
        if second.startswith("http://") or second.startswith("https://"):
            return "REST_API"

    # Database Query: starts with SQL:
    if cmd.upper().startswith("SQL:"):
        return "DB_QUERY"

    # Cloud CLI tools
    cloud_tools = Config.CLOUD_CLI_ALLOWLIST
    base = os.path.basename(cmd.split()[0].lower())
    if base in cloud_tools:
        return "CLOUD_CLI"

    return "SHELL"


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def get_base_command(cmd_str):
    """
    Extracts the base executable name from a shell command string.
    E.g. "sudo systemctl status mysql" -> "systemctl"
    """
    parts = cmd_str.strip().split()
    if not parts:
        return ""
    base = parts[0]
    if base == "sudo" and len(parts) > 1:
        base = parts[1]
    base = os.path.basename(base)
    base = base.replace("`", "").replace("'", "").replace('"', "")
    return base

def is_command_allowed(command):
    """
    Checks if the command's base binary is in the SHELL allowlist.
    """
    base_cmd = get_base_command(command)
    return base_cmd in Config.COMMAND_ALLOWLIST


# ─────────────────────────────────────────────
# Master dispatcher
# ─────────────────────────────────────────────

def execute_step(command, step_type="SHELL"):
    """
    Routes execution to the correct handler based on step_type.
    Returns (success: bool, output: str)
    """
    if step_type == "REST_API":
        return execute_rest_api(command)
    elif step_type == "DB_QUERY":
        return execute_db_query(command)
    elif step_type == "CLOUD_CLI":
        return execute_cloud_cli(command)
    else:
        return execute_command(command)


# ─────────────────────────────────────────────
# Executor 1: Shell / Bash
# ─────────────────────────────────────────────

def execute_command(command):
    """
    Executes a shell command via subprocess.
    Returns: (success_bool, output_str)
    """
    if not is_command_allowed(command):
        return False, f"[BLOCKED] Base command '{get_base_command(command)}' is not in the security allowlist."

    # macOS simulation for Linux-specific commands
    if sys.platform == "darwin":
        cmd_clean = command.replace("sudo ", "").strip()
        if "systemctl" in cmd_clean:
            if cmd_clean.startswith("systemctl status"):
                service = cmd_clean.split()[-1]
                return True, (
                    f"● {service}.service - Simulated {service} service\n"
                    f"   Loaded: loaded (/lib/systemd/system/{service}.service; enabled)\n"
                    f"   Active: active (running) since 2026-06-09 10:00:00 UTC; 1h ago\n"
                    f" Main PID: {os.getpid() + 2500} ({service})\n"
                    f"   Memory: 128.4M\n"
                    f"Jun 09 10:00:00 local systemd[1]: Started {service} (simulated on macOS)."
                )
            elif any(a in cmd_clean for a in ["start", "stop", "restart"]):
                action = "restarted" if "restart" in cmd_clean else ("started" if "start" in cmd_clean else "stopped")
                service = cmd_clean.split()[-1]
                return True, f"[Simulated] Service '{service}' {action} successfully."
        elif cmd_clean.startswith("free"):
            return True, (
                "              total        used        free      shared  buff/cache   available\n"
                "Mem:           16Gi       6.2Gi       5.8Gi       250Mi       4.0Gi        10Gi\n"
                "Swap:         2.0Gi       0.2Gi       1.8Gi"
            )

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        output = result.stdout
        if result.stderr:
            output = (output + "\n" + result.stderr).strip() if output else result.stderr
        if not output.strip():
            output = "[Command executed successfully with no output]"
        return (result.returncode == 0), output
    except subprocess.TimeoutExpired:
        return False, "Execution Error: Command timed out after 30 seconds."
    except Exception as e:
        return False, f"Execution Error: {str(e)}"


# ─────────────────────────────────────────────
# Executor 2: REST API
# ─────────────────────────────────────────────

def execute_rest_api(command):
    """
    Executes a REST API call.
    Format:  METHOD URL [JSON_BODY]
    Example: GET http://localhost:5050/api/runs
    Example: POST http://api.example.com/data {"key": "value"}
    Returns: (success_bool, formatted_output_str)
    """
    import requests as req_lib
    import json as json_lib

    parts = command.strip().split(None, 2)
    if len(parts) < 2:
        return False, "[REST ERROR] Invalid format. Use: METHOD URL [JSON_BODY]"

    method = parts[0].upper()
    url = parts[1]
    body = None

    if len(parts) == 3:
        try:
            body = json_lib.loads(parts[2])
        except Exception:
            body = parts[2]

    if method not in REST_METHODS:
        return False, f"[REST ERROR] Unsupported HTTP method: {method}"

    try:
        timeout = Config.REST_API_TIMEOUT
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        response = req_lib.request(
            method=method,
            url=url,
            json=body if isinstance(body, dict) else None,
            data=body if isinstance(body, str) else None,
            headers=headers,
            timeout=timeout
        )

        # Format output
        status_line = f"HTTP {response.status_code} {response.reason}"
        content_type = response.headers.get("Content-Type", "")

        try:
            if "application/json" in content_type:
                body_out = json_lib.dumps(response.json(), indent=2)
            else:
                body_out = response.text[:2000]  # cap at 2000 chars
        except Exception:
            body_out = response.text[:2000]

        output = f"{status_line}\nURL: {url}\nMethod: {method}\n\n--- Response Body ---\n{body_out}"
        success = 200 <= response.status_code < 300
        return success, output

    except req_lib.exceptions.ConnectionError:
        return False, f"[REST ERROR] Could not connect to: {url}"
    except req_lib.exceptions.Timeout:
        return False, f"[REST ERROR] Request timed out after {Config.REST_API_TIMEOUT}s: {url}"
    except Exception as e:
        return False, f"[REST ERROR] {str(e)}"


# ─────────────────────────────────────────────
# Executor 3: Database Query (SQL)
# ─────────────────────────────────────────────

def execute_db_query(command):
    """
    Executes a SQL query against the configured database.
    Format:  SQL: SELECT * FROM table
    Example: SQL: SELECT count(*) FROM runbook_runs
    Returns: (success_bool, formatted_table_str)
    """
    from sqlalchemy import create_engine, text as sa_text

    # Strip SQL: prefix
    raw_sql = re.sub(r"^SQL:\s*", "", command.strip(), flags=re.IGNORECASE).strip()

    if not raw_sql:
        return False, "[DB ERROR] No SQL query provided after 'SQL:' prefix."

    # Safety: block destructive statements
    sql_upper = raw_sql.upper().lstrip()
    dangerous_keywords = ["DROP ", "TRUNCATE ", "DELETE ", "ALTER ", "CREATE ", "INSERT ", "UPDATE "]
    for kw in dangerous_keywords:
        if sql_upper.startswith(kw):
            return False, (
                f"[DB BLOCKED] Destructive SQL statement detected: '{kw.strip()}'.\n"
                "Only SELECT queries are permitted without approval.\n"
                "Use the approval workflow for write operations."
            )

    try:
        db_url = Config.DB_QUERY_URL
        engine = create_engine(
            db_url,
            connect_args={"check_same_thread": False} if "sqlite" in db_url else {}
        )

        with engine.connect() as conn:
            result = conn.execute(sa_text(raw_sql))
            rows = result.fetchall()
            columns = list(result.keys())

            if not rows:
                return True, f"[DB QUERY] Query returned 0 rows.\nSQL: {raw_sql}"

            # Format as ASCII table
            col_widths = [max(len(str(col)), max((len(str(r[i])) for r in rows), default=0)) for i, col in enumerate(columns)]
            separator = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
            header = "|" + "|".join(f" {str(col):<{col_widths[i]}} " for i, col in enumerate(columns)) + "|"

            table_lines = [
                f"[DB QUERY] {len(rows)} row(s) returned — SQL: {raw_sql}\n",
                separator, header, separator
            ]
            for row in rows:
                row_str = "|" + "|".join(f" {str(v):<{col_widths[i]}} " for i, v in enumerate(row)) + "|"
                table_lines.append(row_str)
            table_lines.append(separator)

            return True, "\n".join(table_lines)

    except Exception as e:
        return False, f"[DB ERROR] Query failed: {str(e)}\nSQL: {raw_sql}"


# ─────────────────────────────────────────────
# Executor 4: Cloud CLI (aws / gcloud / az / kubectl)
# ─────────────────────────────────────────────

def execute_cloud_cli(command):
    """
    Executes a Cloud CLI command (aws, gcloud, az, kubectl, terraform, helm).
    These are only reached after manual operator approval since classify_command
    always marks CLOUD_CLI steps as HIGH risk requiring approval.
    Returns: (success_bool, output_str)
    """
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=60  # Cloud CLIs can be slow
        )
        output = result.stdout
        if result.stderr:
            output = (output + "\n" + result.stderr).strip() if output else result.stderr
        if not output.strip():
            output = "[Cloud CLI] Command completed with no output."
        return (result.returncode == 0), f"[CLOUD CLI] {command}\n\n{output}"
    except subprocess.TimeoutExpired:
        return False, "[CLOUD CLI ERROR] Command timed out after 60 seconds."
    except Exception as e:
        return False, f"[CLOUD CLI ERROR] {str(e)}"
