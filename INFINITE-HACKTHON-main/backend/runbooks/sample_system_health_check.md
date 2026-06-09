# System Health Check & Diagnostics Runbook

**Purpose:** Perform a full system health verification including disk usage, memory, process inspection, and network connectivity.
**Environment:** Linux / macOS Production Server
**Author:** DevOps Team
**Version:** 1.0
**Date:** 2026-06-09

---

## Pre-Checks

1. Verify current logged-in user: `whoami`
2. Print current working directory: `pwd`
3. Check system uptime and load averages: `uptime`

---

## Section 1 — Disk & Storage

4. Check overall disk usage across all mounted volumes: `df -h`
5. List the root directory contents: `ls /`

---

## Section 2 — Memory & CPU

6. Check available memory and swap usage: `free -m`
7. List top running processes by memory: `ps aux`

---

## Section 3 — Network Connectivity

8. Ping Google DNS to verify internet connectivity: `ping -c 4 8.8.8.8`
9. Fetch HTTP headers from an external endpoint: `curl -I https://google.com`

---

## Section 4 — Log Inspection

10. View the last 20 lines of system messages log: `tail -n 20 /var/log/syslog`
11. Check for any recent authentication failures: `grep -i "failed" /var/log/auth.log`

---

## Section 5 — Service Status ⚠️ Requires Approval

12. Check the status of the SSH service: `systemctl status ssh`
13. Inspect journal logs for critical errors: `journalctl -p crit --since "1 hour ago"`

---

## Section 6 — Risky Operations 🔴 High Risk — Requires Operator Approval

14. Restart the nginx web server: `sudo systemctl restart nginx`
15. Kill all zombie processes: `sudo kill -9 -1`
16. Remove all temporary files older than 7 days: `sudo find /tmp -mtime +7 -delete`

---

## Post-Check Summary

17. Print final system status confirmation: `echo "Health check complete. All steps executed."`
18. Record the completion timestamp: `echo "Completed at: $(date)"`
