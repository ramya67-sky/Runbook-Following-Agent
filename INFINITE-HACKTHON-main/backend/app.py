import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime

from config import Config
from database import init_db, get_db, RunbookRun, RunbookStep
from runbook_parser import parse_runbook
from command_classifier import classify_command, generate_warning, suggest_corrected_command
from executor import execute_command, execute_step, is_command_allowed, detect_step_type
from notifier import send_discord_notification
from reporter import generate_audit_report
from file_converter import extract_text_from_file

app = Flask(__name__)
app.config.from_object(Config)

# Enable CORS globally for local development cross-talk (React to Flask)
CORS(app)

# Initialize Database Schema
init_db()

# Auto-detect Ollama service availability
if not app.config.get("MOCK_OLLAMA"):
    try:
        import requests
        requests.get(app.config["OLLAMA_API_URL"], timeout=1.0)
        print(f"[Ollama Service] Connected to local Ollama at {app.config['OLLAMA_API_URL']}.")
    except Exception:
        print(f"[Ollama Service] WARNING: Could not connect to Ollama at {app.config['OLLAMA_API_URL']}. Dynamic MOCK_OLLAMA enabled.")
        app.config["MOCK_OLLAMA"] = True


# ----------------- REST API Routes -----------------

@app.route('/api/runs', methods=['GET'])
def get_runs():
    """
    Returns historical runs list and overall metrics statistics.
    """
    session = get_db()
    try:
        runs = session.query(RunbookRun).order_by(RunbookRun.id.desc()).all()
        runs_list = [r.to_dict() for r in runs]
        
        # Calculate stats
        total_runs = len(runs)
        completed = sum(1 for r in runs if r.status == 'COMPLETED')
        failed = sum(1 for r in runs if r.status == 'FAILED')
        partial = sum(1 for r in runs if r.status == 'PARTIAL')
        
        return jsonify({
            "runs": runs_list,
            "stats": {
                "total": total_runs,
                "completed": completed,
                "failed": failed,
                "partial": partial,
                "ollama_mocked": app.config.get("MOCK_OLLAMA", False)
            }
        })
    finally:
        session.close()

@app.route('/api/upload', methods=['POST'])
def upload_runbook():
    """
    Handles runbook markdown upload or manual textbox submission.
    Parses the runbook and initializes a new run record.
    """
    runbook_name = request.form.get('runbook_name', 'Unnamed Runbook')
    markdown_content = ""

    # Check file upload
    if 'runbook_file' in request.files and request.files['runbook_file'].filename != '':
        file = request.files['runbook_file']
        raw_bytes = file.read()
        try:
            markdown_content = extract_text_from_file(raw_bytes, file.filename)
        except Exception as e:
            return jsonify({"error": f"Failed to extract text from file: {str(e)}"}), 400
        if not runbook_name or runbook_name == 'Unnamed Runbook':
            base = file.filename.rsplit('.', 1)[0] if '.' in file.filename else file.filename
            runbook_name = base.replace('_', ' ').replace('-', ' ').title()
    else:
        # Check text body
        markdown_content = request.form.get('runbook_markdown', '')

    if not markdown_content.strip():
        return jsonify({"error": "No runbook content provided."}), 400

    # Parse runbook steps
    parsed_steps = parse_runbook(markdown_content)
    if not parsed_steps:
        return jsonify({"error": "Could not parse any numbered steps from the runbook."}), 400

    session = get_db()
    try:
        # Create new run
        run = RunbookRun(
            name=runbook_name,
            status='PENDING',
            total_steps=len(parsed_steps),
            executed_steps=0,
            skipped_steps=0,
            errors_count=0
        )
        session.add(run)
        session.flush() # Populate run.id

        # Add steps
        for step_data in parsed_steps:
            cmd = step_data.get("command", "")
            has_cmd = step_data.get("has_command", False)
            
            risk_level = "SAFE"
            explanation = "Informational step."
            recommendation = "None"
            
            if has_cmd and cmd:
                step_type = detect_step_type(cmd)
                classification = classify_command(cmd, step_type)
                risk_level = classification.get("risk_level", "SAFE")
                explanation = classification.get("explanation", "")
                recommendation = classification.get("recommendation", "")

                # Shell allowlist check — only applies to SHELL type
                if step_type == "SHELL" and not is_command_allowed(cmd):
                    risk_level = "HIGH"
                    explanation = f"[ALLOWLIST BLOCK] Command contains unauthorized binary. {explanation}"
            else:
                step_type = "SHELL"

            step = RunbookStep(
                run_id=run.id,
                step_number=step_data.get("number"),
                description=step_data.get("description"),
                command=cmd,
                has_command=has_cmd,
                step_type=step_type,
                risk_level=risk_level,
                explanation=explanation,
                recommendation=recommendation,
                status='PENDING'
            )
            session.add(step)

        session.commit()
        return jsonify({
            "message": "Runbook staged successfully.",
            "run_id": run.id
        })
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()

@app.route('/api/run/<int:run_id>/status', methods=['GET'])
def get_run_status(run_id):
    """
    Returns the JSON representation of the run and all its steps.
    """
    session = get_db()
    try:
        run = session.get(RunbookRun, run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404
        
        steps = session.query(RunbookStep).filter_by(run_id=run_id).order_by(RunbookStep.step_number).all()
        return jsonify({
            "run": run.to_dict(),
            "steps": [s.to_dict() for s in steps]
        })
    finally:
        session.close()

@app.route('/api/run/<int:run_id>/execute_next', methods=['POST'])
def execute_next_step(run_id):
    """
    Runs the next step in the queue.
    If safe: executes automatically and returns status.
    If risky: pauses, flags approval state, and generates warning detail.
    """
    session = get_db()
    try:
        run = session.get(RunbookRun, run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404

        if run.status == 'PENDING':
            run.status = 'RUNNING'
            run.started_at = datetime.utcnow()
            session.commit()
            send_discord_notification("RUN_START", f"Runbook '{run.name}' (ID: {run.id}) is now running.")
                   # Find next pending/waiting/recovering step
        next_step = session.query(RunbookStep).filter(
            RunbookStep.run_id == run_id,
            RunbookStep.status.in_(['PENDING', 'WAITING_APPROVAL', 'RECOVERING', 'FAILED_NEEDS_MCP'])
        ).order_by(RunbookStep.step_number).first()
        
        if not next_step:
            # All steps completed, finalize run
            return finalize_run(session, run)

        # Pause on waiting approval
        if next_step.status == 'WAITING_APPROVAL':
            return jsonify({
                "status": "PAUSED_FOR_APPROVAL",
                "message": "Waiting for manual approval on risky command.",
                "step": next_step.to_dict(),
                "warning": generate_warning(next_step.command, next_step.risk_level)
            })

        # Phase 1.5 of Auto-Remediation: Call MCP synchronously, but return so UI sees RECOVERING
        if next_step.status == 'FAILED_NEEDS_MCP':
            print(f"Detecting failure... invoking MCP to fetch correction for: {next_step.command}")
            try:
                from mcp_client import get_corrected_command_sync
                corrected_command = get_corrected_command_sync(
                    next_step.command, 
                    next_step.step_type or 'SHELL', 
                    next_step.output
                )
                print(f"MCP returned corrected command: {corrected_command}")
                next_step.corrected_command = corrected_command
                next_step.status = 'RECOVERING'
            except Exception as e:
                print(f"MCP auto-recovery fetch failed: {e}")
                next_step.status = 'FAILED'
                
            session.commit()
            return jsonify({
                "status": "RECOVERING" if next_step.status == 'RECOVERING' else "FAILED",
                "message": "Fetched recovery command via MCP.",
                "step": next_step.to_dict()
            })

        # Phase 2 of Auto-Remediation: Execute the corrected command
        if next_step.status == 'RECOVERING':
            print(f"Executing MCP recovered command: {next_step.corrected_command}")
            
            # Execute the corrected command directly without erasing the original broken command from history
            retry_success, retry_output = execute_step(next_step.corrected_command, next_step.step_type or 'SHELL')
            
            # Update outputs to reflect recovery
            next_step.output = f"[MCP AUTO-RECOVERY SUCCESS]\n{retry_output}" if retry_success else f"[MCP AUTO-RECOVERY FAILED]\n{retry_output}"
            
            if retry_success:
                next_step.status = 'SUCCESS'
                run.errors_count -= 1 # Remove the error count since we successfully recovered
            else:
                next_step.status = 'FAILED'
                
            session.commit()
            return jsonify({
                "status": "RECOVERED",
                "message": f"Step {next_step.step_number} recovered via MCP.",
                "step": next_step.to_dict()
            })

        # Automatically execute informational steps
        if not next_step.has_command or not next_step.command:
            next_step.status = 'SUCCESS'
            next_step.executed_at = datetime.utcnow()
            next_step.output = "Informational step. No command executed."
            run.executed_steps += 1
            session.commit()
            return execute_next_step(run_id)

        # Check safety level (Binary allowlist only applies to pure SHELL commands)
        is_safe = next_step.risk_level == 'SAFE'
        if next_step.step_type == 'SHELL' or not next_step.step_type:
            is_safe = is_safe and is_command_allowed(next_step.command)
        
        if is_safe:
            next_step.status = 'RUNNING'
            session.commit()

            # Dispatch to the correct executor based on step type
            success, output = execute_step(next_step.command, next_step.step_type or 'SHELL')

            next_step.output = output
            next_step.executed_at = datetime.utcnow()

            if not success:
                # Intercept failure for auto-remediation via MCP protocol (Phase 1)
                # We set it to a special failure state so the UI can render the failure FIRST
                next_step.status = 'FAILED_NEEDS_MCP'
                run.errors_count += 1
                session.commit()
                return jsonify({
                    "status": "FAILED",
                    "message": f"Step {next_step.step_number} failed. Queued for MCP recovery.",
                    "step": next_step.to_dict()
                })
            else:
                next_step.status = 'SUCCESS'
                run.executed_steps += 1
                session.commit()
                
                emoji_status = "SUCCESS"
                send_discord_notification(
                    f"STEP_{emoji_status}", 
                    f"Step {next_step.step_number}: '{next_step.command}' ({emoji_status})"
                )
                
                return jsonify({
                    "status": "RUNNING",
                    "message": f"Step {next_step.step_number} executed successfully.",
                    "step": next_step.to_dict()
                })
        else:
            # Block and require approval
            next_step.status = 'WAITING_APPROVAL'
            session.commit()
            
            warning_msg = generate_warning(next_step.command, next_step.risk_level)
            send_discord_notification(
                "APPROVAL_REQUIRED", 
                f"Step {next_step.step_number}: '{next_step.command}' requires confirmation."
            )
            
            return jsonify({
                "status": "PAUSED_FOR_APPROVAL",
                "message": "Risky command detected. Human intervention required.",
                "step": next_step.to_dict(),
                "warning": warning_msg
            })
    finally:
        session.close()

@app.route('/api/step/<int:step_id>/approve', methods=['POST'])
def approve_step(step_id):
    """
    Approves and runs a paused step.
    """
    session = get_db()
    try:
        step = session.get(RunbookStep, step_id)
        if not step:
            return jsonify({"error": "Step not found"}), 404
        
        run = session.get(RunbookRun, step.run_id)
        
        if step.status != 'WAITING_APPROVAL':
            return jsonify({"error": "Step is not waiting for approval."}), 400

        step.status = 'RUNNING'
        session.commit()
        
        send_discord_notification("APPROVAL_GRANTED", f"Operator approved execution of: '{step.command}'")
        
        success, output = execute_step(step.command, step.step_type or 'SHELL')
        
        step.output = output
        step.status = 'SUCCESS' if success else 'FAILED'
        step.executed_at = datetime.utcnow()
        
        run.executed_steps += 1
        if not success:
            run.errors_count += 1
            try:
                correction_result = suggest_corrected_command(step.command, step.step_type or 'SHELL', output)
                step.corrected_command = correction_result
            except Exception as e:
                print(f"Error suggesting corrected command: {e}")
            
        session.commit()
        
        emoji_status = "SUCCESS" if success else "FAILURE"
        send_discord_notification(
            f"STEP_{emoji_status}", 
            f"Step {step.step_number}: '{step.command}' completed with status {emoji_status}"
        )

        return jsonify({
            "status": "SUCCESS",
            "step": step.to_dict()
        })
    finally:
        session.close()

@app.route('/api/step/<int:step_id>/deny', methods=['POST'])
def deny_step(step_id):
    """
    Denies execution of a paused step, marking it as DENIED.
    """
    session = get_db()
    try:
        step = session.get(RunbookStep, step_id)
        if not step:
            return jsonify({"error": "Step not found"}), 404
        
        run = session.get(RunbookRun, step.run_id)
        
        if step.status != 'WAITING_APPROVAL':
            return jsonify({"error": "Step is not waiting for approval."}), 400

        step.status = 'DENIED'
        step.output = "[Execution denied by operator]"
        step.executed_at = datetime.utcnow()
        
        run.skipped_steps += 1
        session.commit()
        
        send_discord_notification("APPROVAL_DENIED", f"Operator DENIED execution of: '{step.command}'")
        
        return jsonify({
            "status": "DENIED",
            "step": step.to_dict()
        })
    finally:
        session.close()

@app.route('/api/runs/clear', methods=['POST'])
def clear_history():
    """
    Wipes all records in the database.
    """
    session = get_db()
    try:
        session.query(RunbookStep).delete()
        session.query(RunbookRun).delete()
        session.commit()
        return jsonify({"message": "Successfully wiped run execution history databases."})
    except Exception as e:
        session.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        session.close()


def finalize_run(session, run):
    """
    Finalizes runbook metrics and outputs final Prompt 6 reports.
    """
    run.completed_at = datetime.utcnow()
    
    # If any steps were skipped, we consider the run PARTIAL regardless of errors
    if run.skipped_steps > 0:
        run.status = 'PARTIAL'
    elif run.errors_count > 0:
        run.status = 'FAILED'
    else:
        run.status = 'COMPLETED'
        
    duration_secs = int((run.completed_at - run.started_at).total_seconds())
    duration_str = f"{duration_secs} seconds" if duration_secs < 60 else f"{duration_secs // 60}m {duration_secs % 60}s"

    audit_summary = generate_audit_report(
        runbook_name=run.name,
        total_steps=run.total_steps,
        executed=run.executed_steps,
        skipped=run.skipped_steps,
        errors=run.errors_count,
        duration=duration_str
    )
    
    run.audit_summary = audit_summary
    session.commit()
    
    status_emoji = "✅" if run.status == 'COMPLETED' else ("⚠️" if run.status == 'PARTIAL' else "❌")
    send_discord_notification(
        "RUN_COMPLETE", 
        f"Runbook '{run.name}' finished. Status: {status_emoji} {run.status}. Time: {duration_str}."
    )
    
    return jsonify({
        "status": "FINISHED",
        "message": "Runbook run finalized.",
        "run": run.to_dict()
    })


# Global error handlers — always return JSON, never HTML crash pages
@app.errorhandler(400)
def bad_request(e):
    return jsonify({"error": "Bad request", "detail": str(e)}), 400

@app.route('/api/run/<int:run_id>/cancel', methods=['POST'])
def cancel_run(run_id):
    """
    Halts the runbook explicitly. Marks pending steps as skipped and finalizes the run as PARTIAL.
    """
    session = get_db()
    try:
        run = session.get(RunbookRun, run_id)
        if not run:
            return jsonify({"error": "Run not found"}), 404
            
        pending_steps = session.query(RunbookStep).filter(
            RunbookStep.run_id == run_id,
            RunbookStep.status.in_(['PENDING', 'WAITING_APPROVAL', 'RECOVERING'])
        ).all()
        
        for step in pending_steps:
            step.status = 'DENIED'
            step.output = "[Pipeline auto-execution manually halted by operator]"
            run.skipped_steps += 1
            
        session.commit()
        return finalize_run(session, run)
    finally:
        session.close()

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Endpoint not found", "detail": str(e)}), 404

@app.errorhandler(500)
def internal_error(e):
    return jsonify({"error": "Internal server error", "detail": str(e)}), 500

@app.errorhandler(Exception)
def unhandled_exception(e):
    import traceback
    print(f"[UNHANDLED ERROR] {traceback.format_exc()}")
    return jsonify({"error": "Unexpected server error", "detail": str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5050))
    app.run(host='0.0.0.0', port=port, debug=True)
