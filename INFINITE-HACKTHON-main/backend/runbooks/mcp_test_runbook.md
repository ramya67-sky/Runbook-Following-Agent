# Auto-Remediation Test Runbook

**Purpose:** Test the MCP auto-remediation live feed by executing intentional errors.

1. This is a valid command to verify execution starts: `df -h`
2. This is an invalid command that should trigger a shell error and be auto-remediated by MCP: `invalid-command-xyz --args`
3. This is an invalid SQL command that targets a missing table, which MCP will replace: `SQL: SELECT * FROM non_existent_table_diagnostics;`
4. This tries to curl a missing endpoint: `GET http://localhost:9999/api/broken-endpoint`
5. Finish the runbook successfully: `echo "Error testing completed"`
