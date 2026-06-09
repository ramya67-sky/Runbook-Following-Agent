import json
import re


def parse_file(content: str, filename: str) -> str:
    """Return the text content of a runbook file, normalised for AI parsing."""
    if filename.endswith(".json"):
        try:
            data = json.loads(content)
            return json.dumps(data, indent=2)
        except Exception:
            return content
    return content


def extract_title(content: str, filename: str) -> str:
    """Extract a human-readable title from the runbook."""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
        if line.startswith("Title:"):
            return line[6:].strip()
    name = filename.rsplit(".", 1)[0]
    name = re.sub(r"[-_]", " ", name).title()
    return name
