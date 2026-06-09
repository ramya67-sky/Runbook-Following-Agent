# MCP Auto-Recovery Showcase Runbook

This runbook contains intentional errors to trigger the Model Context Protocol (MCP) auto-recovery loop.

## Section 1: Intentional Failures

1. Check disk space (this one will succeed normally): `df -h`
2. Run a broken shell command (MCP should fix the typo from 'echho' to 'echo'): `echho "This command has a typo!"`
3. Database diagnostics with non-existent table (MCP should fix this to query sqlite_master instead): `SQL: SELECT * FROM non_existent_table_diagnostics;`
4. Querying a broken REST API endpoint (MCP should fix this to target the local backend /api/runs): `GET http://localhost:9999/api/broken-endpoint`
5. Print final message (Fallback step): `echo "MCP Error testing completed successfully!"`
