import os

class Config:
    # SECRET KEY for Flask sessions
    SECRET_KEY = os.environ.get("SECRET_KEY", "antigravity-secret-key-1337")

    # Database: Supports SQLite (default) and MySQL
    # To use MySQL: set DATABASE_URL to 'mysql+pymysql://user:pass@host/dbname'
    # Default is SQLite database inside the project folder.
    DEFAULT_SQLITE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "antigravity.db")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", 
        f"sqlite:///{DEFAULT_SQLITE_PATH}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Ollama Integration
    OLLAMA_API_URL = os.environ.get("OLLAMA_API_URL", "http://localhost:11434")
    OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3")
    # Set to True to bypass Ollama API requests and use local heuristic parsing/classification fallback
    MOCK_OLLAMA = os.environ.get("MOCK_OLLAMA", "false").lower() == "true"

    # Discord Webhook Integration
    # Put your Discord webhook URL here to send notifications
    DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL", "")

    # Security Command Allowlist
    # For safety, only execution of these base commands is allowed directly
    # Commands not starting with one of these will automatically trigger confirmation, or block
    COMMAND_ALLOWLIST = {
        "df", "ls", "cat", "grep", "journalctl", "systemctl",
        "ps", "ping", "curl", "echo", "uptime", "free",
        "whoami", "pwd", "head", "tail"
    }

    # Cloud CLI Allowlist — these always require manual approval regardless of sub-command
    CLOUD_CLI_ALLOWLIST = {
        "aws", "gcloud", "az", "kubectl", "terraform", "helm"
    }

    # REST API config
    REST_API_TIMEOUT = int(os.environ.get("REST_API_TIMEOUT", "15"))  # seconds

    # Database Query config — defaults to the same SQLite DB used by the app
    DEFAULT_SQLITE_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), "antigravity.db")
    DB_QUERY_URL = os.environ.get("DB_QUERY_URL", f"sqlite:///{DEFAULT_SQLITE_PATH}")
