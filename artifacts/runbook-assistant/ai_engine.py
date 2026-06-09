import os
import json
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
MODEL = "gpt-4.1-mini"


def parse_runbook(content: str, filename: str) -> list[dict]:
    """Parse runbook text into structured steps using GPT."""
    prompt = f"""You are an expert DevOps engineer. Parse the following runbook document and extract all steps as structured JSON.

For each step, extract:
- title: short step title (string)
- description: what this step does (string)
- command: the exact command to run, if any (string or null)
- expected_output: what success looks like (string)
- notes: any warnings, caveats, or context (string)

Return a JSON array of steps. Only return valid JSON, no markdown fences.

Runbook filename: {filename}
Runbook content:
{content}"""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.strip("```json").strip("```").strip()
    return json.loads(raw)


def assess_risk(step: dict) -> dict:
    """Assess risk level and provide safety guidance for a step."""
    prompt = f"""You are a DevOps safety expert. Assess the risk of the following runbook step.

Step title: {step.get('title', '')}
Description: {step.get('description', '')}
Command: {step.get('command', 'N/A')}
Notes: {step.get('notes', '')}

Return a JSON object with:
- risk_level: one of "low", "medium", "high", "critical"
- risk_reason: brief explanation of the risk (1-2 sentences)
- requires_approval: boolean (true if medium/high/critical)
- precautions: list of strings with safety precautions to take
- rollback_command: command to undo this action, or null if not applicable

Only return valid JSON, no markdown fences."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.strip("```json").strip("```").strip()
    return json.loads(raw)


def verify_output(step: dict, actual_output: str) -> dict:
    """Verify if the actual output matches the expected output."""
    prompt = f"""You are a DevOps engineer verifying a runbook step execution result.

Step: {step.get('title', '')}
Command run: {step.get('command', 'N/A')}
Expected outcome: {step.get('expected_output', 'N/A')}
Actual output: {actual_output}

Determine if the step succeeded or failed.

Return a JSON object with:
- success: boolean
- verdict: "success", "failure", or "uncertain"
- explanation: brief explanation (1-2 sentences)
- recommended_action: what to do next if failed, or "proceed" if success

Only return valid JSON, no markdown fences."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )
    raw = response.choices[0].message.content.strip()
    raw = raw.strip("```json").strip("```").strip()
    return json.loads(raw)


def generate_incident_summary(runbook_name: str, steps_log: list[dict]) -> str:
    """Generate a post-incident summary from the execution log."""
    steps_text = "\n".join([
        f"- Step {s['step_index']+1}: {s['step_title']} | Status: {s['status']} | Risk: {s['risk_level']}"
        + (f" | Output: {s['output'][:200]}" if s.get('output') else "")
        for s in steps_log
    ])

    prompt = f"""You are a senior DevOps engineer writing a post-incident runbook execution summary.

Runbook: {runbook_name}
Steps executed:
{steps_text}

Write a concise incident summary including:
1. What was done
2. Any issues encountered
3. Final outcome
4. Recommendations for next time

Keep it professional and under 300 words."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def get_step_guidance(step: dict, context: str = "") -> str:
    """Get detailed AI guidance for executing a specific step."""
    prompt = f"""You are an expert DevOps engineer guiding someone through a runbook step.

Step: {step.get('title', '')}
Description: {step.get('description', '')}
Command: {step.get('command', 'N/A')}
Notes: {step.get('notes', '')}
{f'Additional context: {context}' if context else ''}

Provide clear, actionable guidance for executing this step safely. Include:
- What this step accomplishes
- Exactly how to run it
- What to watch for
- Common pitfalls

Keep it concise and practical (under 200 words)."""

    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return response.choices[0].message.content.strip()
