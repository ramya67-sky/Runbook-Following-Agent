# Error Diagnostic Runbook

1. Check disk space (This step should succeed): `df -h`
2. Test non-existent shell command (This step should fail with command not found): `invalid-command-xyz --args`
3. Database diagnostics with non-existent table (This query will trigger a database error): `SQL: SELECT * FROM non_existent_table_diagnostics;`
4. Querying a broken REST API endpoint (This REST step will fail): `GET http://localhost:9999/api/broken-endpoint`
5. Print final message (Fallback step): `echo "Error testing completed"`
