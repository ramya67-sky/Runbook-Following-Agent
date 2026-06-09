# Database Outage Restoration Runbook

This runbook resolves database replication lags and cleans transaction buffers.

1. Check current disk usage using `df -h` to verify storage state.
2. Restart the database engine using `systemctl restart mysql`.
3. Clear temporary lock files with `rm -rf /tmp/mysql_locks`.
4. Trigger manual system synchronization via `reboot`.
