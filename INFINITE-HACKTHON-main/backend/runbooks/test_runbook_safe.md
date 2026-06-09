# Server Health Diagnostic Runbook

This runbook checks system resources and network connectivity.

1. Check system disk usage via `df -h` to verify root partition space.
2. Check system load and uptime statistics with `uptime`.
3. Check current memory utilization using `free -h`.
4. Test external network latency via `ping -c 4 8.8.8.8`.
5. View mysql database daemon status using `systemctl status mysql`.
