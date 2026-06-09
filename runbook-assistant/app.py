import streamlit as st
import json
import os
from datetime import datetime

import db
import ai_engine
import notifications
import parser as rb_parser

db.init_db()

st.set_page_config(
    page_title="Runbook Execution Assistant",
    page_icon="📋",
    layout="wide",
)

# ── Session state defaults ────────────────────────────────────────────────────
for key, default in {
    "steps": [],
    "risk_data": {},
    "current_step": 0,
    "execution_id": None,
    "runbook_name": "",
    "execution_started": False,
    "step_statuses": {},
    "step_outputs": {},
    "verification_results": {},
    "guidance_cache": {},
    "discord_webhook": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default


# ── Helpers ────────────────────────────────────────────────────────────────────
RISK_BADGE = {
    "low":      "🟢 LOW",
    "medium":   "🟡 MEDIUM",
    "high":     "🔴 HIGH",
    "critical": "🚨 CRITICAL",
}

STATUS_BADGE = {
    "completed":  "✅ Completed",
    "skipped":    "⏭ Skipped",
    "failed":     "❌ Failed",
    "in_progress": "🔄 In Progress",
    "pending":    "⏳ Pending",
}


def risk_color(level: str) -> str:
    return {"low": "green", "medium": "orange", "high": "red", "critical": "darkred"}.get(level, "grey")


def reset_session():
    for key in ["steps", "risk_data", "current_step", "execution_id",
                "runbook_name", "execution_started", "step_statuses",
                "step_outputs", "verification_results", "guidance_cache"]:
        st.session_state[key] = [] if key in ("steps",) else {} if key in (
            "risk_data", "step_statuses", "step_outputs",
            "verification_results", "guidance_cache") else 0 if key == "current_step" else False if key == "execution_started" else "" if key in ("execution_id", "runbook_name") else None


# ══════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.title("📋 Runbook Assistant")
    st.caption("AI-powered incident runbook execution")
    st.divider()

    page = st.radio("Navigation", ["▶ Execute Runbook", "📜 Execution History", "⚙ Settings"])
    st.divider()

    st.subheader("Discord Notifications")
    webhook = st.text_input(
        "Webhook URL",
        value=st.session_state.discord_webhook,
        type="password",
        placeholder="https://discord.com/api/webhooks/...",
        help="Optional: paste a Discord webhook URL to receive step notifications"
    )
    if webhook != st.session_state.discord_webhook:
        st.session_state.discord_webhook = webhook

    if webhook:
        if st.button("Test Webhook"):
            ok, msg = notifications.send_discord_notification(
                webhook, "Runbook Assistant connected successfully!", "🔗 Test Notification", 0x5865F2
            )
            st.success(msg) if ok else st.error(msg)

    st.divider()
    st.caption("Powered by OpenAI GPT · Built for SRE & DevOps teams")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: EXECUTION HISTORY
# ══════════════════════════════════════════════════════════════════════════════
if page == "📜 Execution History":
    st.title("📜 Execution History")
    executions = db.get_all_executions()

    if not executions:
        st.info("No executions recorded yet. Run a runbook to get started.")
    else:
        for ex in executions:
            status_icon = {"completed": "✅", "failed": "❌", "in_progress": "🔄", "aborted": "⛔"}.get(ex["status"], "❓")
            with st.expander(f"{status_icon} **{ex['runbook_name']}** — {ex['started_at'][:16].replace('T', ' ')} UTC"):
                col1, col2, col3 = st.columns(3)
                col1.metric("Status", ex["status"].upper())
                col2.metric("Started", ex["started_at"][:16].replace("T", " "))
                col3.metric("Completed", (ex["completed_at"] or "—")[:16].replace("T", " "))

                if ex.get("summary"):
                    st.subheader("Incident Summary")
                    st.write(ex["summary"])

                steps = db.get_execution_steps(ex["id"])
                if steps:
                    st.subheader("Step Log")
                    for s in steps:
                        badge = STATUS_BADGE.get(s["status"], s["status"])
                        risk = RISK_BADGE.get(s["risk_level"], s["risk_level"])
                        st.markdown(
                            f"**Step {s['step_index']+1}: {s['step_title']}** &nbsp; {badge} &nbsp; `{risk}`"
                        )
                        if s.get("step_command"):
                            st.code(s["step_command"], language="bash")
                        if s.get("output"):
                            with st.expander("Output"):
                                st.text(s["output"])
                        if s.get("notes"):
                            st.caption(f"Notes: {s['notes']}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: SETTINGS
# ══════════════════════════════════════════════════════════════════════════════
elif page == "⚙ Settings":
    st.title("⚙ Settings")
    st.subheader("About")
    st.markdown("""
**AI-Powered Runbook Execution Assistant**

This tool helps DevOps and SRE engineers execute operational runbooks safely during incidents.

**Features:**
- Upload runbooks in Markdown, TXT, or JSON format
- AI-powered step extraction and risk assessment
- Human approval workflow for risky commands
- Output verification with AI analysis
- Rollback recommendations on failure
- Discord notifications for team awareness
- Full audit trail with SQLite persistence
- Automated post-incident summary generation

**Risk Levels:**
- 🟢 **Low** — Safe to proceed automatically
- 🟡 **Medium** — Review carefully before executing
- 🔴 **High** — Requires explicit approval
- 🚨 **Critical** — Extreme caution; team notification recommended
""")

    st.subheader("Database")
    executions = db.get_all_executions()
    st.metric("Total Executions", len(executions))
    completed = sum(1 for e in executions if e["status"] == "completed")
    failed = sum(1 for e in executions if e["status"] == "failed")
    col1, col2 = st.columns(2)
    col1.metric("Completed", completed)
    col2.metric("Failed", failed)


# ══════════════════════════════════════════════════════════════════════════════
# PAGE: EXECUTE RUNBOOK
# ══════════════════════════════════════════════════════════════════════════════
else:
    st.title("▶ Execute Runbook")

    # ── UPLOAD PHASE ─────────────────────────────────────────────────────────
    if not st.session_state.steps:
        st.subheader("Upload a Runbook")
        st.markdown("Supported formats: **Markdown** (`.md`), **Plain text** (`.txt`), **JSON** (`.json`)")

        col_upload, col_example = st.columns([2, 1])

        with col_upload:
            uploaded = st.file_uploader("Choose a runbook file", type=["md", "txt", "json"])

        with col_example:
            st.markdown("**No runbook handy?**")
            example_runbook = """# Database Failover Runbook

## Overview
This runbook describes the procedure to failover the primary database to the replica.

## Step 1: Verify Replica Status
Check that the replica is caught up and healthy.

**Command:**
```
psql -h replica-host -U admin -c "SELECT pg_last_wal_receive_lsn();"
```

**Expected output:** A WAL location within 100MB of primary.

## Step 2: Put Application in Maintenance Mode
Enable the maintenance page to stop new writes.

**Command:**
```
kubectl set env deployment/api MAINTENANCE_MODE=true
```

**Expected output:** `deployment.apps/api env updated`

## Step 3: Stop Primary Database Writes
Promote the replica to primary.

**Command:**
```
pg_ctl promote -D /var/lib/postgresql/data
```

**Expected output:** `server promoting`

**Warning:** This is irreversible without a full resync.

## Step 4: Update DNS/Load Balancer
Point the database endpoint to the new primary.

**Command:**
```
aws route53 change-resource-record-sets --hosted-zone-id Z123 --change-batch file://db-failover.json
```

**Expected output:** `{"ChangeInfo": {"Status": "PENDING"}}`

## Step 5: Verify Application Connectivity
Ensure the application connects to the new primary.

**Command:**
```
kubectl rollout restart deployment/api
```

**Expected output:** `deployment.apps/api restarted`
"""
            if st.button("📄 Load Example Runbook"):
                st.session_state["_example_content"] = example_runbook
                st.session_state["_example_filename"] = "db-failover.md"

        content = None
        filename = None

        if uploaded is not None:
            content = uploaded.read().decode("utf-8", errors="replace")
            filename = uploaded.name
        elif st.session_state.get("_example_content"):
            content = st.session_state["_example_content"]
            filename = st.session_state["_example_filename"]

        if content and filename:
            title = rb_parser.extract_title(content, filename)
            st.success(f"Loaded: **{title}**")

            with st.expander("Preview runbook content"):
                st.text(content[:3000] + ("..." if len(content) > 3000 else ""))

            if st.button("🤖 Analyze with AI", type="primary", use_container_width=True):
                with st.spinner("Analyzing runbook and extracting steps..."):
                    try:
                        normalized = rb_parser.parse_file(content, filename)
                        steps = ai_engine.parse_runbook(normalized, filename)
                        st.session_state.steps = steps
                        st.session_state.runbook_name = title
                        st.session_state.current_step = 0
                        st.session_state.step_statuses = {}
                        st.session_state.step_outputs = {}
                        st.session_state.verification_results = {}
                        st.session_state.guidance_cache = {}
                        # Pre-assess risk for all steps
                        risk_data = {}
                        for i, step in enumerate(steps):
                            risk_data[i] = ai_engine.assess_risk(step)
                        st.session_state.risk_data = risk_data
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to analyze runbook: {e}")

    # ── EXECUTION PHASE ───────────────────────────────────────────────────────
    else:
        steps = st.session_state.steps
        risk_data = st.session_state.risk_data
        current = st.session_state.current_step
        total = len(steps)
        runbook_name = st.session_state.runbook_name

        # ── Start execution session ───────────────────────────────────────────
        if not st.session_state.execution_started:
            st.subheader(f"Ready to execute: **{runbook_name}**")
            st.markdown(f"**{total} steps** identified. Review the plan below before starting.")

            # Step overview table
            st.subheader("Step Overview")
            for i, step in enumerate(steps):
                risk = risk_data.get(i, {})
                rl = risk.get("risk_level", "unknown")
                badge = RISK_BADGE.get(rl, rl)
                req_approval = risk.get("requires_approval", False)
                with st.expander(f"Step {i+1}: {step.get('title', 'Untitled')} — {badge}"):
                    st.write(step.get("description", ""))
                    if step.get("command"):
                        st.code(step["command"], language="bash")
                    if risk.get("risk_reason"):
                        st.warning(f"**Risk:** {risk['risk_reason']}")
                    if risk.get("precautions"):
                        st.markdown("**Precautions:**")
                        for p in risk["precautions"]:
                            st.markdown(f"- {p}")
                    if req_approval:
                        st.error("⚠️ This step requires explicit approval before execution.")

            col1, col2 = st.columns(2)
            if col1.button("🚀 Start Execution", type="primary", use_container_width=True):
                eid = db.start_execution(runbook_name)
                st.session_state.execution_id = eid
                st.session_state.execution_started = True
                if st.session_state.discord_webhook:
                    notifications.send_discord_notification(
                        st.session_state.discord_webhook,
                        f"Starting execution of **{runbook_name}** ({total} steps)",
                        "🚀 Runbook Execution Started",
                        0x5865F2
                    )
                st.rerun()

            if col2.button("🔄 Upload Different Runbook", use_container_width=True):
                reset_session()
                st.rerun()

        # ── Active step-by-step execution ─────────────────────────────────────
        else:
            # Progress bar
            completed_count = sum(1 for s in st.session_state.step_statuses.values() if s in ("completed", "skipped"))
            progress = completed_count / total
            st.progress(progress, text=f"Progress: {completed_count}/{total} steps completed")

            col_title, col_reset = st.columns([4, 1])
            col_title.subheader(f"📋 {runbook_name}")
            if col_reset.button("⛔ Abort"):
                db.complete_execution(st.session_state.execution_id, "aborted")
                reset_session()
                st.rerun()

            # ── Step pills / nav ──────────────────────────────────────────────
            st.markdown("**Steps:**")
            pill_cols = st.columns(min(total, 8))
            for i in range(total):
                status = st.session_state.step_statuses.get(i, "pending")
                icon = {"completed": "✅", "failed": "❌", "skipped": "⏭", "pending": "⏳"}.get(status, "⏳")
                label = f"{icon} {i+1}"
                if pill_cols[i % 8].button(label, key=f"nav_{i}", use_container_width=True):
                    st.session_state.current_step = i
                    st.rerun()

            st.divider()

            # ── Check if all done ─────────────────────────────────────────────
            all_done = all(
                st.session_state.step_statuses.get(i) in ("completed", "skipped", "failed")
                for i in range(total)
            )

            if all_done and current >= total:
                st.success("🎉 All steps processed!")
                st.subheader("Generate Incident Summary")
                if st.button("📝 Generate AI Summary", type="primary"):
                    with st.spinner("Generating incident summary..."):
                        steps_log = db.get_execution_steps(st.session_state.execution_id)
                        summary = ai_engine.generate_incident_summary(runbook_name, steps_log)
                        failed_any = any(
                            st.session_state.step_statuses.get(i) == "failed" for i in range(total)
                        )
                        final_status = "failed" if failed_any else "completed"
                        db.complete_execution(st.session_state.execution_id, final_status, summary)
                        if st.session_state.discord_webhook:
                            notifications.notify_execution_complete(
                                st.session_state.discord_webhook,
                                runbook_name, final_status, summary
                            )
                        st.subheader("Incident Summary")
                        st.write(summary)
                        st.caption(f"Execution recorded with ID #{st.session_state.execution_id}")

                if st.button("🔄 Start New Execution"):
                    reset_session()
                    st.rerun()

            elif current < total:
                step = steps[current]
                risk = risk_data.get(current, {})
                risk_level = risk.get("risk_level", "unknown")
                requires_approval = risk.get("requires_approval", False)
                step_status = st.session_state.step_statuses.get(current, "pending")

                # ── Step header ───────────────────────────────────────────────
                badge = RISK_BADGE.get(risk_level, risk_level)
                st.markdown(f"## Step {current+1} of {total}: {step.get('title', 'Untitled')}")
                st.markdown(f"**Risk Level:** :{risk_color(risk_level)}[{badge}]")

                if risk.get("risk_reason"):
                    if risk_level in ("high", "critical"):
                        st.error(f"⚠️ {risk['risk_reason']}")
                    elif risk_level == "medium":
                        st.warning(f"⚠️ {risk['risk_reason']}")
                    else:
                        st.info(f"ℹ️ {risk['risk_reason']}")

                # ── Step details ──────────────────────────────────────────────
                col_desc, col_guidance = st.columns([3, 2])

                with col_desc:
                    st.subheader("Description")
                    st.write(step.get("description", "No description provided."))

                    if step.get("command"):
                        st.subheader("Command to Run")
                        st.code(step["command"], language="bash")

                    if step.get("expected_output"):
                        st.subheader("Expected Output")
                        st.info(step["expected_output"])

                    if step.get("notes"):
                        st.subheader("Notes")
                        st.caption(step["notes"])

                with col_guidance:
                    st.subheader("AI Guidance")
                    if current not in st.session_state.guidance_cache:
                        with st.spinner("Loading AI guidance..."):
                            guidance = ai_engine.get_step_guidance(step)
                            st.session_state.guidance_cache[current] = guidance
                    st.write(st.session_state.guidance_cache[current])

                    if risk.get("precautions"):
                        st.subheader("Precautions")
                        for p in risk["precautions"]:
                            st.markdown(f"- {p}")

                    if risk.get("rollback_command"):
                        st.subheader("Rollback Command")
                        st.code(risk["rollback_command"], language="bash")

                st.divider()

                # ── Approval gate ─────────────────────────────────────────────
                approved = True
                if requires_approval and step_status == "pending":
                    st.error("🔒 **This step requires explicit approval before you can proceed.**")
                    approval_col1, approval_col2 = st.columns(2)
                    if approval_col1.button("✅ I approve — proceed with this step", type="primary", use_container_width=True):
                        st.session_state[f"approved_{current}"] = True
                        st.rerun()
                    if approval_col2.button("⛔ Skip this step", use_container_width=True):
                        db.log_step(
                            st.session_state.execution_id, current,
                            step.get("title", ""), step.get("command", ""),
                            risk_level, "skipped", "", "Skipped by user (approval not granted)"
                        )
                        st.session_state.step_statuses[current] = "skipped"
                        st.session_state.current_step = current + 1
                        st.rerun()
                    approved = st.session_state.get(f"approved_{current}", False)

                if approved or not requires_approval:
                    st.subheader("Record Execution")

                    if step_status in ("pending", "in_progress"):
                        output = st.text_area(
                            "Paste your command output here (or leave blank if not applicable):",
                            key=f"output_{current}",
                            height=150,
                            placeholder="Paste the actual terminal output from running the command above..."
                        )
                        notes = st.text_input("Notes (optional)", key=f"notes_{current}")

                        action_col1, action_col2, action_col3 = st.columns(3)

                        if action_col1.button("✅ Mark as Completed", type="primary", use_container_width=True):
                            if st.session_state.discord_webhook:
                                notifications.notify_step_started(
                                    st.session_state.discord_webhook,
                                    runbook_name, step.get("title", ""), risk_level
                                )

                            verification = None
                            if output.strip():
                                with st.spinner("AI verifying output..."):
                                    verification = ai_engine.verify_output(step, output)
                                st.session_state.verification_results[current] = verification

                            final_status = "completed"
                            if verification and not verification.get("success"):
                                final_status = "failed"

                            db.log_step(
                                st.session_state.execution_id, current,
                                step.get("title", ""), step.get("command", ""),
                                risk_level, final_status, output, notes
                            )
                            st.session_state.step_statuses[current] = final_status
                            st.session_state.step_outputs[current] = output

                            if final_status == "failed" and st.session_state.discord_webhook:
                                reason = verification.get("explanation", "Output did not match expected") if verification else "Marked as failed"
                                notifications.notify_step_failed(
                                    st.session_state.discord_webhook,
                                    runbook_name, step.get("title", ""), reason
                                )

                            st.session_state.current_step = current + 1
                            st.rerun()

                        if action_col2.button("❌ Mark as Failed", use_container_width=True):
                            if st.session_state.discord_webhook:
                                notifications.notify_step_failed(
                                    st.session_state.discord_webhook,
                                    runbook_name, step.get("title", ""),
                                    "Manually marked as failed"
                                )
                            db.log_step(
                                st.session_state.execution_id, current,
                                step.get("title", ""), step.get("command", ""),
                                risk_level, "failed", output, notes
                            )
                            st.session_state.step_statuses[current] = "failed"
                            st.session_state.step_outputs[current] = output
                            st.session_state.current_step = current + 1
                            st.rerun()

                        if action_col3.button("⏭ Skip", use_container_width=True):
                            db.log_step(
                                st.session_state.execution_id, current,
                                step.get("title", ""), step.get("command", ""),
                                risk_level, "skipped", "", notes or "Skipped by user"
                            )
                            st.session_state.step_statuses[current] = "skipped"
                            st.session_state.current_step = current + 1
                            st.rerun()

                    else:
                        # Already completed — show result
                        s = step_status
                        if s == "completed":
                            st.success("✅ Step completed successfully.")
                        elif s == "failed":
                            st.error("❌ Step failed.")
                            if risk.get("rollback_command"):
                                st.warning(f"**Rollback command:** `{risk['rollback_command']}`")
                        elif s == "skipped":
                            st.info("⏭ Step was skipped.")

                        vr = st.session_state.verification_results.get(current)
                        if vr:
                            st.subheader("AI Verification Result")
                            verdict = vr.get("verdict", "unknown")
                            if verdict == "success":
                                st.success(f"✅ {vr.get('explanation', '')}")
                            elif verdict == "failure":
                                st.error(f"❌ {vr.get('explanation', '')}")
                                rec = vr.get("recommended_action", "")
                                if rec and rec != "proceed":
                                    st.warning(f"**Recommended action:** {rec}")
                            else:
                                st.warning(f"⚠️ {vr.get('explanation', '')}")

                        if st.button("➡ Next Step", type="primary"):
                            st.session_state.current_step = min(current + 1, total)
                            st.rerun()
