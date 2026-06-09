import unittest
import os
import sys

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Set up sqlite in-memory database configuration for testing isolation BEFORE imports
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from config import Config
Config.MOCK_OLLAMA = True

from database import init_db, get_db, RunbookRun, RunbookStep, engine
from runbook_parser import _parse_runbook_fallback
from command_classifier import _classify_command_fallback, _generate_warning_fallback
from executor import get_base_command, is_command_allowed


class TestAntigravityAgent(unittest.TestCase):

    def setUp(self):
        init_db()
        self.db = get_db()

    def tearDown(self):
        self.db.close()
        # Clean up connection pool resources to avoid ResourceWarning
        engine.dispose()

    def test_runbook_parsing(self):
        markdown = """
# Setup Runbook
1. Diagnostics with `df -h`
2. Informational note for operations team
3. Restart daemon using `systemctl restart nginx`
"""
        steps = _parse_runbook_fallback(markdown)
        self.assertEqual(len(steps), 3)
        
        self.assertEqual(steps[0]["number"], 1)
        self.assertEqual(steps[0]["command"], "df -h")
        self.assertTrue(steps[0]["has_command"])
        
        self.assertEqual(steps[1]["number"], 2)
        self.assertEqual(steps[1]["command"], "")
        self.assertFalse(steps[1]["has_command"])
        
        self.assertEqual(steps[2]["number"], 3)
        self.assertEqual(steps[2]["command"], "systemctl restart nginx")
        self.assertTrue(steps[2]["has_command"])

    def test_command_classification(self):
        # Test SAFE command
        safe_res = _classify_command_fallback("df -h")
        self.assertEqual(safe_res["risk_level"], "SAFE")
        self.assertTrue(safe_res["safe"])

        # Test MEDIUM command
        med_res = _classify_command_fallback("systemctl restart nginx")
        self.assertEqual(med_res["risk_level"], "MEDIUM")
        self.assertFalse(med_res["safe"])

        # Test HIGH command
        high_res = _classify_command_fallback("rm -rf /tmp/locks")
        self.assertEqual(high_res["risk_level"], "HIGH")
        self.assertFalse(high_res["safe"])

    def test_base_command_extraction(self):
        self.assertEqual(get_base_command("df -h"), "df")
        self.assertEqual(get_base_command("sudo systemctl restart nginx"), "systemctl")
        self.assertEqual(get_base_command("/usr/bin/df -h"), "df")
        self.assertEqual(get_base_command("echo 'hello'"), "echo")

    def test_allowlist_enforcement(self):
        self.assertTrue(is_command_allowed("df -h"))
        self.assertTrue(is_command_allowed("sudo systemctl status nginx"))
        self.assertFalse(is_command_allowed("rm -rf /tmp"))
        self.assertFalse(is_command_allowed("python script.py"))

    def test_warning_generation(self):
        warning = _generate_warning_fallback("rm -rf /var/log", "HIGH")
        self.assertIn("permanently delete", warning)
        
        warning2 = _generate_warning_fallback("systemctl restart mysql", "MEDIUM")
        self.assertIn("restarts a system service", warning2)

    def test_database_logging(self):
        # Create runbook record
        run = RunbookRun(name="Test Runbook Database Log", status="PENDING", total_steps=2)
        self.db.add(run)
        self.db.commit()

        # Check in DB
        retrieved_run = self.db.query(RunbookRun).filter_by(name="Test Runbook Database Log").first()
        self.assertIsNotNone(retrieved_run)
        self.assertEqual(retrieved_run.status, "PENDING")

        # Create step record
        step = RunbookStep(run_id=retrieved_run.id, step_number=1, description="Test step", command="ls", status="PENDING")
        self.db.add(step)
        self.db.commit()

        # Check step
        retrieved_step = self.db.query(RunbookStep).filter_by(run_id=retrieved_run.id).first()
        self.assertIsNotNone(retrieved_step)
        self.assertEqual(retrieved_step.command, "ls")

    def test_flask_endpoints(self):
        from app import app
        app.config['TESTING'] = True
        client = app.test_client()

        # Test clear history
        res = client.post('/api/runs/clear')
        self.assertEqual(res.status_code, 200)

        # Test get runs
        res = client.get('/api/runs')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('runs', data)
        self.assertIn('stats', data)
        self.assertEqual(data['stats']['total'], 0)

        # Test upload runbook
        res = client.post('/api/upload', data={
            'runbook_name': 'Test Route Runbook',
            'runbook_markdown': '# Test Runbook\n1. Run `df -h` to verify space.'
        })
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertIn('run_id', data)
        run_id = data['run_id']

        # Test status of run
        res = client.get(f'/api/run/{run_id}/status')
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data['run']['name'], 'Test Route Runbook')
        self.assertEqual(len(data['steps']), 1)
        self.assertEqual(data['steps'][0]['command'], 'df -h')

    def test_runbook_parsing_nlp_fallback(self):
        markdown = """
# NLP Runbook
1. Check disk space
2. Get the database count of elements
3. Restart nginx service
"""
        steps = _parse_runbook_fallback(markdown)
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[0]["command"], "df -h")
        self.assertEqual(steps[0]["step_type"], "SHELL")
        
        self.assertEqual(steps[1]["command"], "SQL: SELECT count(*) FROM runbook_runs;")
        self.assertEqual(steps[1]["step_type"], "DB_QUERY")
        
        self.assertEqual(steps[2]["command"], "systemctl restart nginx")
        self.assertEqual(steps[2]["step_type"], "SHELL")


if __name__ == '__main__':
    unittest.main()
