# Multi-Mode Diagnostic & Execution Runbook

**Purpose:** Verify system configuration across different execution providers, including REST APIs, SQLite databases, Local Shell, and Kubernetes / AWS Cloud CLI tools.

---

## 1. Local Diagnostics (SHELL)

1. Check current system disk capacity: `df -h`
2. Print current path information: `pwd`

---

## 2. API Diagnostics (REST_API)

3. Query local Flask application run statistics: `GET http://127.0.0.1:5050/api/runs`
4. Query external public API for connectivity test: `GET https://httpbin.org/get`

---

## 3. Database Diagnostics (DB_QUERY)

5. Inspect recent runs from the SQLite database: `SQL:SELECT id, name, status, total_steps FROM runbook_runs ORDER BY id DESC LIMIT 5;`
6. Count total execution steps logged: `SQL:SELECT COUNT(*) AS total_steps_count FROM runbook_steps;`

---

## 4. Kubernetes & Infrastructure Diagnostics (CLOUD_CLI)

7. Retrieve running Kubernetes pods (Requires operator approval): `kubectl get pods -A`
8. List configured AWS S3 buckets: `aws s3 ls`
