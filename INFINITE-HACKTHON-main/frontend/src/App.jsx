import React, { useState, useEffect, useRef } from 'react';
import './App.css';
import IntroLoader from './IntroLoader';

const API_BASE = 'http://localhost:5050';

function App() {
  const [showIntro, setShowIntro] = useState(true);
  const [activeTab, setActiveTab] = useState('dashboard');
  
  // Toast notifications state
  const [toasts, setToasts] = useState([]);
  
  // Dashboard state
  const [runs, setRuns] = useState([]);
  const [stats, setStats] = useState({ total: 0, completed: 0, failed: 0, partial: 0, ollama_mocked: true });
  const [uploadName, setUploadName] = useState('');
  const [uploadText, setUploadText] = useState('');
  const [uploadFile, setUploadFile] = useState(null);
  const [isBackendConnected, setIsBackendConnected] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  // Live Runner state
  const [currentRunId, setCurrentRunId] = useState(null);
  const [currentRun, setCurrentRun] = useState(null); // { run: {}, steps: [] }
  const [consoleLogs, setConsoleLogs] = useState([]);
  const [isExecuting, setIsExecuting] = useState(false);
  const [approvalStep, setApprovalStep] = useState(null);
  const [approvalWarning, setApprovalWarning] = useState('');
  
  // Audit details state
  const [auditRunId, setAuditRunId] = useState(null);
  const [auditRunDetails, setAuditRunDetails] = useState(null);
  const [expandedSteps, setExpandedSteps] = useState({});

  // Agent Live Panel state
  const [agentMode, setAgentMode] = useState('STRICT'); // 'STRICT' or 'SIMULATION'
  const [analysisDelay, setAnalysisDelay] = useState(1000); // 1000, 2000, 3000 ms
  const [agentLogs, setAgentLogs] = useState([
    { time: new Date().toLocaleTimeString(), text: 'Safety Agent Engine initialized.', type: 'system' },
    { time: new Date().toLocaleTimeString(), text: 'Policy engine loaded: allowed binaries allowlist active.', type: 'check' }
  ]);
  const agentFeedEndRef = useRef(null);

  const addAgentLog = (text, type = 'system') => {
    const time = new Date().toLocaleTimeString();
    setAgentLogs(prev => [...prev, { time, text, type }]);
  };

  const getFeedTitle = () => {
    if (!currentRun || !currentRun.steps || currentRun.steps.length === 0) {
      return "Live Feed";
    }
    const types = new Set(currentRun.steps.map(s => s.step_type));
    if (types.has("DB_QUERY") && (types.has("SHELL") || types.has("REST_API") || types.has("CLOUD_CLI"))) {
      return "Hybrid Live Feed";
    }
    if (types.has("DB_QUERY")) {
      return "Database Live Feed";
    }
    if (types.has("CLOUD_CLI")) {
      return "Cloud Live Feed";
    }
    if (types.has("REST_API")) {
      return "API Live Feed";
    }
    return "Shell Live Feed";
  };

  const consoleEndRef = useRef(null);

  // Toast helper
  const triggerToast = (message, type = 'info') => {
    const id = Date.now() + Math.random().toString(36).substr(2, 9);
    setToasts(prev => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id));
    }, 4000);
  };

  // Restore run state from localStorage on startup — validate the run still exists first
  useEffect(() => {
    const savedRunId = localStorage.getItem('antigravity_current_run_id');
    if (savedRunId) {
      const runId = parseInt(savedRunId, 10);
      // Validate the run still exists before restoring
      fetch(`${API_BASE}/api/run/${runId}/status`)
        .then(res => {
          if (!res.ok) throw new Error('Run not found');
          return res.json();
        })
        .then(data => {
          setCurrentRunId(runId);
          setCurrentRun(data);
          setActiveTab('runner');
          setConsoleLogs([{ type: 'system', text: `[SYSTEM] Restored runner state from last session (Run ID: ${runId}).` }]);
          triggerToast('Restored last active session.', 'info');
        })
        .catch(() => {
          // Run no longer exists — clear stale localStorage silently
          localStorage.removeItem('antigravity_current_run_id');
          setActiveTab('dashboard');
        });
    }
  }, []);

  // Sync currentRunId to localStorage
  useEffect(() => {
    if (currentRunId) {
      localStorage.setItem('antigravity_current_run_id', currentRunId);
    } else {
      localStorage.removeItem('antigravity_current_run_id');
    }
  }, [currentRunId]);

  // Poll backend connection and fetch run history
  useEffect(() => {
    fetchRuns();
    const interval = setInterval(fetchRuns, 5000);
    return () => clearInterval(interval);
  }, []);

  // Poll active run details when executing or in runner view to keep states synchronized
  useEffect(() => {
    let interval;
    if (currentRunId && activeTab === 'runner') {
      interval = setInterval(() => {
        loadRunDetails(currentRunId);
      }, 3000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [currentRunId, activeTab]);

  // Auto-scroll console
  useEffect(() => {
    if (consoleEndRef.current) {
      consoleEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [consoleLogs]);

  // Auto-scroll Agent Feed
  useEffect(() => {
    if (agentFeedEndRef.current) {
      agentFeedEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [agentLogs]);

  // Log execution state changes to the Agent Live Feed
  useEffect(() => {
    if (!currentRunId) return;
    if (isExecuting) {
      addAgentLog('Safety Guardrail pipeline started. Scanning commands...', 'system');
    } else {
      if (approvalStep) {
        addAgentLog('Pipeline BLOCKED: Awaiting manual operator bypass signature.', 'danger');
      } else {
        const hasPending = currentRun?.steps.some(s => s.status === 'PENDING');
        if (hasPending) {
          addAgentLog('[PAUSED] Safety Guardrail pipeline paused. Waiting for operator dispatch.', 'warning');
        }
      }
    }
  }, [isExecuting, currentRunId]);

  // Reactive auto-runner pipeline loop
  useEffect(() => {
    let timer;
    if (isExecuting && currentRun) {
      const nextPending = currentRun.steps.find(s => s.status === 'PENDING');
      const hasWaiting = currentRun.steps.some(s => s.status === 'WAITING_APPROVAL');
      const isRunRunning = currentRun.run.status === 'RUNNING' || currentRun.run.status === 'PENDING';

      if (hasWaiting) {
        if (agentMode === 'SIMULATION') {
          const waitingStep = currentRun.steps.find(s => s.status === 'WAITING_APPROVAL');
          if (waitingStep) {
            timer = setTimeout(() => {
              addAgentLog(`[Simulation Bypass] Auto-approving risky command Step ${waitingStep.step_number}.`, 'warning');
              handleApprove();
            }, analysisDelay);
          }
        } else {
          setIsExecuting(false);
        }
      } else if (nextPending) {
        timer = setTimeout(() => {
          runNextStep();
        }, analysisDelay);
      } else if (isRunRunning) {
        timer = setTimeout(() => {
          runNextStep();
        }, analysisDelay);
      }
    }
    return () => clearTimeout(timer);
  }, [isExecuting, currentRun, agentMode, analysisDelay]);

  const fetchRuns = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/runs`);
      if (!res.ok) throw new Error('API server returned error status');
      const data = await res.json();
      setRuns(data.runs || []);
      setStats(data.stats || { total: 0, completed: 0, failed: 0, partial: 0, ollama_mocked: true });
      setIsBackendConnected(true);
    } catch (err) {
      console.error(err);
      setIsBackendConnected(false);
    }
  };

  const loadRunDetails = async (runId, forceReconstructLogs = false) => {
    try {
      const res = await fetch(`${API_BASE}/api/run/${runId}/status`);

      // If run no longer exists, clear stale state and redirect to dashboard
      if (res.status === 404 || res.status === 500) {
        localStorage.removeItem('antigravity_current_run_id');
        setCurrentRunId(null);
        setCurrentRun(null);
        setConsoleLogs([]);
        setIsExecuting(false);
        setActiveTab('dashboard');
        return null;
      }

      if (!res.ok) throw new Error('Failed to fetch status');
      const data = await res.json();
      setCurrentRun(data);
      
      // Reconstruct terminal console logs from backend step run history
      if (forceReconstructLogs || consoleLogs.length <= 1) {
        const reconstructedLogs = [];
        reconstructedLogs.push({ type: 'system', text: `[SYSTEM] Initialized runner for Run ID ${data.run.id} (${data.run.name})` });
        
        const sortedSteps = [...data.steps].sort((a, b) => a.step_number - b.step_number);
        sortedSteps.forEach(step => {
          if (step.status === 'SUCCESS') {
            reconstructedLogs.push({ type: 'system', text: `[SYSTEM] Automated Step ${step.step_number}: ${step.description}` });
            if (step.command) {
              reconstructedLogs.push({ type: 'input', text: step.command });
              if (step.output) {
                reconstructedLogs.push({ type: 'output', text: step.output });
              }
            }
          } else if (step.status === 'FAILED') {
            reconstructedLogs.push({ type: 'system', text: `[SYSTEM] Step ${step.step_number} FAILED: ${step.description}` });
            if (step.command) {
              reconstructedLogs.push({ type: 'input', text: step.command });
              if (step.output) {
                reconstructedLogs.push({ type: 'error', text: step.output });
              }
            }
          } else if (step.status === 'DENIED') {
            reconstructedLogs.push({ type: 'system', text: `[SYSTEM] Step ${step.step_number} DENIED: ${step.description}` });
            if (step.command) {
              reconstructedLogs.push({ type: 'input', text: step.command });
              reconstructedLogs.push({ type: 'error', text: `[Execution denied by operator]` });
            }
          } else if (step.status === 'WAITING_APPROVAL') {
            reconstructedLogs.push({ type: 'system', text: `[APPROVAL REQUIRED] Step ${step.step_number} requires approval.` });
            if (step.command) {
              reconstructedLogs.push({ type: 'input', text: step.command });
            }
          }
        });
        
        if (data.run.status === 'COMPLETED' || data.run.status === 'FAILED' || data.run.status === 'PARTIAL') {
          reconstructedLogs.push({ type: 'system', text: `[SYSTEM] Run finalized. Status: ${data.run.status}` });
          if (data.run.audit_summary) {
            reconstructedLogs.push({ type: 'output', text: data.run.audit_summary });
          }
        }
        
        setConsoleLogs(reconstructedLogs);
      }

      // Auto-detect approval state during status updates
      const waitingStep = data.steps.find(s => s.status === 'WAITING_APPROVAL');
      if (waitingStep && (!approvalStep || approvalStep.id !== waitingStep.id)) {
        setApprovalStep(waitingStep);
        const nextRes = await fetch(`${API_BASE}/api/run/${runId}/execute_next`, { method: 'POST' });
        const nextData = await nextRes.json();
        if (nextData.status === 'PAUSED_FOR_APPROVAL') {
          setApprovalWarning(nextData.warning);
        }
      }
      return data;
    } catch (err) {
      console.error(err);
      // Do not spam error messages — just log silently
    }
  };

  const loadAuditDetails = async (runId) => {
    try {
      const res = await fetch(`${API_BASE}/api/run/${runId}/status`);
      if (!res.ok) throw new Error('Failed to fetch audit status');
      const data = await res.json();
      setAuditRunDetails(data);
      setAuditRunId(runId);
      setActiveTab('audit');
      triggerToast(`Loaded Audit Report for Run ${runId}.`, 'success');
    } catch (err) {
      console.error(err);
      triggerToast('Failed to load audit details.', 'error');
    }
  };

  const handleUpload = async (e) => {
    if (e) e.preventDefault();

    if (!uploadText.trim() && !uploadFile) {
      triggerToast('Please paste runbook markdown or upload a file.', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('runbook_name', uploadName || 'Unnamed Runbook');
    if (uploadFile) {
      formData.append('runbook_file', uploadFile);
    } else {
      formData.append('runbook_markdown', uploadText);
    }

    try {
      const res = await fetch(`${API_BASE}/api/upload`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      if (!res.ok) {
        triggerToast(data.error || 'Upload failed', 'error');
        return;
      }

      triggerToast('Runbook staged successfully!', 'success');
      setUploadText('');
      setUploadFile(null);
      setUploadName('');

      setCurrentRunId(data.run_id);
      setConsoleLogs([
        { type: 'system', text: `[SYSTEM] Runbook staged successfully. Staged Run ID: ${data.run_id}` },
        { type: 'system', text: `[SYSTEM] Ready for automated execution. Start pipeline to begin.` }
      ]);

      await loadRunDetails(data.run_id);
      setActiveTab('runner');
      fetchRuns();
    } catch (err) {
      console.error(err);
      triggerToast('Connection to backend failed.', 'error');
    }
  };

  const runNextStep = async () => {
    if (!currentRunId) return;

    // Find the next step to log safety evaluation on the agent feed before executing
    const nextStep = currentRun?.steps.find(s => s.status === 'PENDING' || s.status === 'WAITING_APPROVAL');
    if (nextStep) {
      addAgentLog(`Initiating safety guardrails assessment for Step ${nextStep.step_number}...`, 'system');
      if (nextStep.has_command && nextStep.command) {
        addAgentLog(`Scanning command: "${nextStep.command}"`, 'check');
        const isAllowed = nextStep.step_type !== 'SHELL' || !nextStep.explanation?.includes('[ALLOWLIST BLOCK]');
        addAgentLog(`Policy Checker: binary check ${isAllowed ? 'PASSED' : 'FAILED'}`, isAllowed ? 'check' : 'danger');
        addAgentLog(`LLM Safety Model: Risk classified as ${nextStep.risk_level}.`, nextStep.risk_level === 'SAFE' ? 'check' : nextStep.risk_level === 'MEDIUM' ? 'warning' : 'danger');
      } else {
        addAgentLog(`Informational step. Proceeding without command execution.`, 'check');
      }
    }

    try {
      const res = await fetch(`${API_BASE}/api/run/${currentRunId}/execute_next`, { method: 'POST' });
      const data = await res.json();

      if (!res.ok) {
        addLog('error', `Execution failed: ${data.error || 'unknown error'}`);
        addAgentLog(`Assessment execution failed: ${data.error || 'unknown error'}`, 'danger');
        setIsExecuting(false);
        return;
      }

      await loadRunDetails(currentRunId);

      if (data.status === 'PAUSED_FOR_APPROVAL') {
        if (agentMode === 'SIMULATION') {
          addAgentLog(`[Simulation Bypass] Step ${data.step.step_number} auto-approved.`, 'warning');
          handleApprove();
        } else {
          setIsExecuting(false);
          setApprovalStep(data.step);
          setApprovalWarning(data.warning);
          setConsoleLogs(prev => [
            ...prev,
            { type: 'system', text: `[APPROVAL REQUIRED] Step ${data.step.step_number} is flagged as risky (${data.step.risk_level}). Operator approval needed.` },
            { type: 'input', text: data.step.command }
          ]);
          addAgentLog(`ALERT: Step ${data.step.step_number} execution BLOCKED. Operator approval signature required.`, 'warning');
          triggerToast('Action blocked: Risky command detected.', 'error');
        }
      } else if (data.status === 'RECOVERING') {
        const step = data.step;
        setConsoleLogs(prev => [
          ...prev,
          { type: 'system', text: `[SYSTEM] Automated Step ${step.step_number}: ${step.description}` },
          { type: 'input', text: step.command },
          { type: 'error', text: `[FAILURE DETECTED] Fetching correct command via MCP...` }
        ]);
        addAgentLog(`Step ${step.step_number} failed. MCP auto-recovery protocol initiated.`, 'danger');
        
      } else if (data.status === 'RECOVERED') {
        const step = data.step;
        setConsoleLogs(prev => [
          ...prev,
          { type: 'system', text: `[MCP RECOVERY] Command successfully swapped!` },
          { type: 'input', text: step.command },
          { type: 'output', text: step.output || 'Recovered.' }
        ]);
        addAgentLog(`Step ${step.step_number} successfully auto-recovered via MCP.`, 'check');
        
      } else if (data.status === 'FAILED') {
        const step = data.step;
        setConsoleLogs(prev => [
          ...prev,
          { type: 'system', text: `[SYSTEM] Automated Step ${step.step_number}: ${step.description}` },
          { type: 'input', text: step.command },
          { type: 'error', text: `[FAILURE DETECTED] Step execution failed.` }
        ]);
        addAgentLog(`Step ${step.step_number} failed.`, 'danger');
      } else if (data.status === 'SUCCESS') {
        const step = data.step;
        const logLines = [];
        logLines.push({ type: 'system', text: `[SYSTEM] Automated Step ${step.step_number}: ${step.description}` });
        if (step.command) {
          logLines.push({ type: 'input', text: step.command });
          if (step.output) {
            logLines.push({ type: 'output', text: step.output });
          }
        }
        setConsoleLogs(prev => [...prev, ...logLines]);
        addAgentLog(`Step ${step.step_number} safety assessment successful. Dispatched to executor.`, 'check');
      } else if (data.status === 'FINISHED') {
        setIsExecuting(false);
        setConsoleLogs(prev => [
          ...prev,
          { type: 'system', text: `[SYSTEM] Runbook completed. Status: ${data.run.status}` },
          { type: 'output', text: data.run.audit_summary || 'Run complete.' }
        ]);
        addAgentLog(`All runbook steps successfully executed. Run status: ${data.run.status}.`, 'check');
        addAgentLog(`Audit safety summary generated.`, 'system');
        triggerToast('Runbook execution finished!', 'success');
        fetchRuns();
      }
    } catch (err) {
      console.error(err);
      addLog('error', 'Network error during step execution.');
      addAgentLog(`Network error during execution.`, 'danger');
      setIsExecuting(false);
    }
  };

  const handleApprove = async () => {
    if (!approvalStep) return;
    const stepId = approvalStep.id;
    addAgentLog(`Bypass signature approved by operator for Step ${approvalStep.step_number}.`, 'check');
    try {
      setApprovalStep(null);
      setApprovalWarning('');

      setConsoleLogs(prev => [...prev, { type: 'system', text: `[SYSTEM] Operator approved execution of step ${approvalStep.step_number}.` }]);

      const res = await fetch(`${API_BASE}/api/step/${stepId}/approve`, { method: 'POST' });
      const data = await res.json();

      if (!res.ok) {
        addLog('error', `Execution failed: ${data.error || 'unknown error'}`);
        addAgentLog(`Bypass execution failed: ${data.error || 'unknown error'}`, 'danger');
        return;
      }

      const step = data.step;
      const logLines = [];
      if (step.command) {
        logLines.push({ type: 'input', text: step.command });
        if (step.output) {
          logLines.push({ type: 'output', text: step.output });
        }
      }
      setConsoleLogs(prev => [...prev, ...logLines]);
      addAgentLog(`Step ${step.step_number} executed successfully.`, 'check');
      triggerToast('Step approved & executed.', 'success');

      await loadRunDetails(currentRunId);
      setIsExecuting(true);
    } catch (err) {
      console.error(err);
      addLog('error', 'Failed to approve step.');
      addAgentLog(`Failed to approve step ${approvalStep.step_number}.`, 'danger');
    }
  };

  const handleDeny = async () => {
    if (!approvalStep) return;
    const stepId = approvalStep.id;
    addAgentLog(`Operator block confirmation received for Step ${approvalStep.step_number}. skipping...`, 'danger');
    try {
      setApprovalStep(null);
      setApprovalWarning('');

      setConsoleLogs(prev => [...prev, { type: 'system', text: `[SYSTEM] Operator DENIED execution of step ${approvalStep.step_number}. Skipping command.` }]);

      const res = await fetch(`${API_BASE}/api/step/${stepId}/deny`, { method: 'POST' });
      const data = await res.json();

      if (!res.ok) {
        addLog('error', `Denial failed: ${data.error || 'unknown error'}`);
        addAgentLog(`Denial processing failed: ${data.error || 'unknown error'}`, 'danger');
        return;
      }
      addAgentLog(`Step ${approvalStep.step_number} denied and skipped.`, 'warning');
      triggerToast('Step execution denied & skipped.', 'info');

      await loadRunDetails(currentRunId);
      setIsExecuting(true);
    } catch (err) {
      console.error(err);
      addLog('error', 'Failed to deny step.');
      addAgentLog(`Failed to deny step ${approvalStep.step_number}.`, 'danger');
    }
  };

  const handleClearHistory = async () => {
    if (!window.confirm("Are you sure you want to clear all execution runs in the database?")) return;
    try {
      const res = await fetch(`${API_BASE}/api/runs/clear`, { method: 'POST' });
      if (!res.ok) throw new Error('Wipe failed');
      fetchRuns();
      triggerToast('History wiped successfully.', 'info');
      if (currentRunId) {
        setCurrentRunId(null);
        setCurrentRun(null);
        setConsoleLogs([]);
      }
      if (auditRunId) {
        setAuditRunId(null);
        setAuditRunDetails(null);
      }
    } catch (err) {
      console.error(err);
      triggerToast('Failed to clear database.', 'error');
    }
  };

  const addLog = (type, text) => {
    setConsoleLogs(prev => [...prev, { type, text }]);
  };

  const toggleStepExpansion = (id) => {
    setExpandedSteps(prev => ({
      ...prev,
      [id]: !prev[id]
    }));
  };

  // Drag and drop handlers
  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setUploadFile(e.dataTransfer.files[0]);
      triggerToast(`Selected: ${e.dataTransfer.files[0].name}`, 'info');
    }
  };

  // Stepper progress calculations
  const calculateProgress = () => {
    if (!currentRun || !currentRun.steps.length) return 0;
    const total = currentRun.steps.length;
    const completed = currentRun.steps.filter(s => ['SUCCESS', 'FAILED', 'DENIED'].includes(s.status)).length;
    return Math.round((completed / total) * 100);
  };

  const activeProgress = calculateProgress();

  return (
    <>
      {showIntro && <IntroLoader onComplete={() => { setShowIntro(false); setActiveTab('dashboard'); }} />}
      <div className="app-container">
      {/* Toast Notification Container */}
      <div className="toast-container">
        {toasts.map(toast => (
          <div key={toast.id} className={`toast-message ${toast.type}`}>
            {toast.type === 'success' && '✓'}
            {toast.type === 'error' && '⚠'}
            {toast.type === 'info' && 'ℹ'}
            {toast.message}
          </div>
        ))}
      </div>

      {/* System Status Header */}
      <header className="app-header">
        <div className="logo-section">
          <img src="/logo.png" alt="Runbook Agent Logo" className="app-logo" />
<h1>VEGA</h1>
          
        </div>
        <div className="system-status">
          <div className="status-indicator">
            <span className={`status-dot ${isBackendConnected ? 'active' : ''}`}></span>
            Backend: {isBackendConnected ? 'Online' : 'Offline'}
          </div>
          <div className="status-indicator">
            <span className={`status-dot ${isBackendConnected ? (stats.ollama_mocked ? 'warning' : 'active') : ''}`}></span>
            Ollama: {isBackendConnected ? (stats.ollama_mocked ? 'Offline (Mocking)' : 'Online') : 'Unknown'}
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="app-nav">
        <button className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`} onClick={() => setActiveTab('dashboard')}>
          Dashboard
        </button>
        <button className={`nav-tab ${activeTab === 'runner' ? 'active' : ''}`} onClick={() => {
          if (currentRunId) {
            loadRunDetails(currentRunId);
          }
          setActiveTab('runner');
        }}>
          {getFeedTitle()} {currentRun && `(ID: ${currentRun.run.id})`}
        </button>
        <button className={`nav-tab ${activeTab === 'audit' ? 'active' : ''}`} onClick={() => setActiveTab('audit')}>
          Audit Report
        </button>
      </nav>

      {/* Main Tab Content */}
      <main style={{ flexGrow: 1, display: 'flex', flexDirection: 'column', gap: '24px' }}>
        {activeTab === 'dashboard' && (
          <>
            {/* Quick Stats Grid */}
            <section className="stats-grid">
              <div className="glass-panel stat-card">
                <h3>Total Staged Runs</h3>
                <div className="value">{stats.total}</div>
              </div>
              <div className="glass-panel stat-card" style={{ borderLeft: '4px solid var(--color-success)' }}>
                <h3>Completed</h3>
                <div className="value" style={{ color: 'var(--color-success)' }}>{stats.completed}</div>
              </div>
              <div className="glass-panel stat-card" style={{ borderLeft: '4px solid var(--color-warning)' }}>
                <h3>Skipped / Partial</h3>
                <div className="value" style={{ color: 'var(--color-warning)' }}>{stats.partial}</div>
              </div>
              <div className="glass-panel stat-card" style={{ borderLeft: '4px solid var(--color-danger)' }}>
                <h3>Failed</h3>
                <div className="value" style={{ color: 'var(--color-danger)' }}>{stats.failed}</div>
              </div>
            </section>

            {/* Dashboard Input Area */}
            <div className="dashboard-grid">
              {/* Form Input */}
              <section className="glass-panel" style={{ padding: '24px' }}>
                <h2 className="card-title">Stage Runbook</h2>

                <form onSubmit={handleUpload} className="input-section">
                  <div className="form-group">
                    <label>Runbook Context Name (Optional)</label>
                    <input 
                      type="text" 
                      className="text-input" 
                      placeholder="e.g. MySQL Database Restart" 
                      value={uploadName} 
                      onChange={(e) => setUploadName(e.target.value)} 
                    />
                  </div>

                  <div className="form-group">
                    <label>Upload Runbook File</label>
                    <label 
                      className="upload-zone"
                      style={{
                        borderColor: isDragging ? 'var(--color-primary)' : 'rgba(255, 255, 255, 0.12)',
                        background: isDragging ? 'rgba(127, 90, 240, 0.05)' : 'rgba(0, 0, 0, 0.1)'
                      }}
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                    >
                      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="17 8 12 3 7 8" />
                        <line x1="12" y1="3" x2="12" y2="15" />
                      </svg>
                      <div style={{ textAlign: 'center' }}>
                        {uploadFile ? (
                          <strong style={{ color: 'var(--color-success)' }}>{uploadFile.name}</strong>
                        ) : (
                          <>
                            <div>Drag & drop or <span style={{ color: 'var(--color-primary)', textDecoration: 'underline' }}>browse</span></div>
                            <div style={{ fontSize: '11px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                              Supports PDF, DOCX, XLSX, JSON, YAML, CSV, HTML, MD, TXT
                            </div>
                          </>
                        )}
                      </div>
                      <input 
                        type="file" 
                        accept=".md,.txt,.pdf,.docx,.xlsx,.json,.yaml,.yml,.csv,.rst,.html,.htm" 
                        onChange={(e) => {
                          if (e.target.files && e.target.files[0]) {
                            setUploadFile(e.target.files[0]);
                          }
                        }} 
                      />
                    </label>
                  </div>

                  <div style={{ textAlign: 'center', color: 'var(--color-text-muted)', fontSize: '13px', margin: '-8px 0' }}>— OR —</div>

                  <div className="form-group">
                    <label>Paste Runbook Text (Markdown format)</label>
                    <textarea 
                      className="paste-area" 
                      placeholder="# System Diagnostics Runbook&#10;1. Check memory usage: `free -m`&#10;2. Check storage status: `df -h`"
                      value={uploadText}
                      onChange={(e) => setUploadText(e.target.value)}
                    />
                  </div>

                  <button type="submit" className="btn-primary" disabled={!isBackendConnected}>
                    Stage & Parse Runbook
                  </button>
                </form>
              </section>

              {/* History List */}
              <section className="glass-panel history-section" style={{ padding: '24px' }}>
                <h2 className="card-title">
                  Run History
                  {runs.length > 0 && (
                    <button className="btn-danger" onClick={handleClearHistory}>
                      Clear History
                    </button>
                  )}
                </h2>
                
                <div className="runs-table-container" style={{ flexGrow: 1 }}>
                  {runs.length === 0 ? (
                    <div style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: '40px 0' }}>
                      No runbook execution records found.
                    </div>
                  ) : (
                    <table className="runs-table">
                      <thead>
                        <tr>
                          <th>Runbook</th>
                          <th>Status</th>
                          <th>Progress</th>
                          <th>Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {runs.map((r) => (
                          <tr key={r.id}>
                            <td>
                              <div style={{ fontWeight: 700 }}>{r.name}</div>
                              <div style={{ fontSize: '12px', color: 'var(--color-text-muted)', marginTop: '4px' }}>
                                ID: {r.id} • {new Date(r.created_at).toLocaleString()}
                              </div>
                            </td>
                            <td>
                              <span className={`badge ${r.status.toLowerCase()}`}>{r.status}</span>
                            </td>
                            <td>
                              <div style={{ fontSize: '13px' }}>
                                Steps: {r.executed_steps}/{r.total_steps}
                              </div>
                              <div style={{ fontSize: '11px', color: 'var(--color-text-muted)' }}>
                                Skipped: {r.skipped_steps} | Errors: {r.errors_count}
                              </div>
                            </td>
                            <td>
                              {r.status === 'PENDING' || r.status === 'RUNNING' ? (
                                <button className="btn-resume" onClick={() => {
                                  setCurrentRunId(r.id);
                                  loadRunDetails(r.id);
                                  setConsoleLogs([
                                    { type: 'system', text: `[SYSTEM] Resumed runner on Run ID ${r.id}.` }
                                  ]);
                                  setActiveTab('runner');
                                }}>
                                  Resume
                                </button>
                              ) : (
                                <button className="btn-report" onClick={() => loadAuditDetails(r.id)}>
                                  Report
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </div>
              </section>
            </div>
          </>
        )}

        {activeTab === 'runner' && (
          <div className="runner-layout">
            {/* Stepper Panel */}
            <section className="glass-panel stepper-container">
              <div className="stepper-header">
                {currentRun ? (
                  <>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                      <div>
                        <h2>{getFeedTitle()}</h2>
                        <p style={{ color: 'var(--color-text-secondary)', fontSize: '13px', marginTop: '4px' }}>
                          Runbook: <strong>{currentRun.run.name}</strong> • ID: {currentRun.run.id} • Status: <span className={`badge ${currentRun.run.status.toLowerCase()}`}>{currentRun.run.status}</span>
                        </p>
                      </div>
                      <button className="btn-sync" onClick={() => {
                        loadRunDetails(currentRunId);
                        triggerToast('Status successfully synchronized with backend.', 'success');
                      }}>
                        Sync Status
                      </button>
                    </div>

                    {/* Progress Bar Display */}
                    <div style={{ marginTop: '16px' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: 'var(--color-text-secondary)' }}>
                        <span>Progress</span>
                        <span>{activeProgress}%</span>
                      </div>
                      <div className="progress-bar-container">
                        <div className="progress-bar-filler" style={{ width: `${activeProgress}%` }} />
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <h2>No Run Selected</h2>
                    <p style={{ color: 'var(--color-text-secondary)', fontSize: '13px' }}>Please go to Dashboard to stage a runbook.</p>
                  </>
                )}
              </div>

              {currentRun && currentRun.steps.map((step) => (
                <div 
                  key={step.id} 
                  className={`step-node ${step.status.toLowerCase()} ${step.id === approvalStep?.id ? 'active' : ''}`}
                >
                  <div className="step-icon-wrapper">
                    <div className="step-circle">
                      {step.status === 'SUCCESS' && '✓'}
                      {step.status === 'FAILED' && '✗'}
                      {step.status === 'DENIED' && '⊘'}
                      {step.status === 'WAITING_APPROVAL' && '!'}
                      {step.status === 'PENDING' && step.step_number}
                      {step.status === 'RUNNING' && '▶'}
                    </div>
                  </div>
                  <div className="step-details">
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <h4>Step {step.step_number}</h4>
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        {/* Step Type Badge */}
                        <span className={`step-type-badge ${(step.step_type || 'SHELL').toLowerCase()}`}>
                          {step.step_type === 'REST_API' && '🌐 REST'}
                          {step.step_type === 'DB_QUERY' && '🗄️ SQL'}
                          {step.step_type === 'CLOUD_CLI' && '☁️ Cloud'}
                          {(!step.step_type || step.step_type === 'SHELL') && '🖥️ Shell'}
                        </span>
                        {/* Risk Level Badge */}
                        {step.command && (
                          <span className={`step-risk ${step.risk_level.toLowerCase()}`}>
                            {step.risk_level}
                          </span>
                        )}
                      </div>
                    </div>
                    <p style={{ fontSize: '14px', color: 'var(--color-text-secondary)' }}>{step.description}</p>
                    {step.command && (
                      <div className="step-command-line">
                        <span className="code-badge">{step.command}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </section>

            {/* Console Log Panel */}
            <section className="glass-panel console-container">
              <div className="console-header">
                <div className="console-title">
                  <div className="mac-dots">
                    <span className="mac-dot close"></span>
                    <span className="mac-dot minimize"></span>
                    <span className="mac-dot zoom"></span>
                  </div>
                  Database Console
                </div>
                {currentRun && (
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button 
                      className="btn-primary" 
                      onClick={() => {
                        setIsExecuting(!isExecuting);
                        triggerToast(isExecuting ? 'Execution paused.' : 'Execution started.', 'info');
                      }} 
                      disabled={currentRun.run.status === 'COMPLETED' || currentRun.run.status === 'FAILED' || currentRun.run.status === 'PARTIAL'}
                      style={{ padding: '6px 12px', fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}
                    >
                      {isExecuting ? (
                        <>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
                          Pause Pipeline
                        </>
                      ) : (
                        <>
                          <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
                          Run Steps
                        </>
                      )}
                    </button>
                    <button 
                      className="btn-clear-logs" 
                      onClick={() => {
                        setConsoleLogs([]);
                        triggerToast('Console cleared.', 'info');
                      }}
                    >
                      Clear Logs
                    </button>
                  </div>
                )}
              </div>

              <div className="console-body">
                {consoleLogs.length === 0 ? (
                  <div className="console-line system">Console is ready. Start execution pipeline.</div>
                ) : (
                  consoleLogs.map((log, idx) => (
                    <div key={idx} className={`console-line ${log.type}`}>
                      {log.text}
                    </div>
                  ))
                )}
                <div ref={consoleEndRef} />
              </div>
            </section>

            {/* Agent Live Panel */}
            <section className="agent-panel-container">
              <div className="agent-panel-header">
                <div className="agent-panel-title">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" style={{ color: 'var(--color-primary)' }}>
                    <path d="M12 2a10 10 0 0 1 10 10c0 5.523-4.477 10-10 10S2 17.523 2 12 6.477 2 12 2z" />
                    <path d="M12 6v6l4 2" />
                  </svg>
                  <span>Safety Guardrails</span>
                </div>
                
                {/* Agent Pulse Indicator */}
                <div className="agent-status-indicator">
                  <span className="agent-pulse-dot" style={{ 
                    backgroundColor: !currentRun ? 'var(--color-text-muted)' :
                                   approvalStep ? 'var(--color-danger)' : 
                                   isExecuting ? 'var(--color-success)' : 'var(--color-warning)' 
                  }}></span>
                  <span>
                    {!currentRun ? 'IDLE' :
                     approvalStep ? 'BLOCKED' : 
                     isExecuting ? 'SCANNING' : 'PAUSED'}
                  </span>
                </div>
              </div>

              <div className="agent-panel-body">
                {/* Active Step Panel */}
                <div className="agent-card-section">
                  <span className="agent-card-title">Active Safety Analysis</span>
                  {currentRun && currentRun.steps.find(s => s.status === 'PENDING' || s.status === 'RUNNING' || s.status === 'WAITING_APPROVAL') ? (() => {
                    const activeStep = currentRun.steps.find(s => s.status === 'PENDING' || s.status === 'RUNNING' || s.status === 'WAITING_APPROVAL');
                    const isAllowed = activeStep.step_type !== 'SHELL' || !activeStep.explanation?.includes('[ALLOWLIST BLOCK]');
                    
                    return (
                      <div className="agent-active-step-info">
                        <div className="agent-active-step-header">
                          <span className="agent-active-step-title">Step {activeStep.step_number} • {activeStep.step_type || 'SHELL'}</span>
                          <span className={`badge ${activeStep.risk_level.toLowerCase()}`}>{activeStep.risk_level}</span>
                        </div>
                        <div className="agent-active-step-desc">{activeStep.description}</div>
                        {activeStep.command && (
                          <div className="agent-active-step-command">{activeStep.command}</div>
                        )}
                        
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginTop: '12px' }}>
                          {/* Policy check */}
                          <div className={`agent-checklist-item ${isAllowed ? 'success' : 'danger'}`}>
                            <span className={`agent-checklist-icon ${isAllowed ? 'success' : 'danger'}`}>{isAllowed ? '✓' : '✗'}</span>
                            <span>Allowed Binary Check: {isAllowed ? 'Allowed' : 'Blocked Binary'}</span>
                          </div>
                          
                          {/* Risk level check */}
                          <div className={`agent-checklist-item ${activeStep.risk_level === 'SAFE' ? 'success' : activeStep.risk_level === 'MEDIUM' ? 'warning' : 'danger'}`}>
                            <span className={`agent-checklist-icon ${activeStep.risk_level === 'SAFE' ? 'success' : activeStep.risk_level === 'MEDIUM' ? 'warning' : 'danger'}`}>
                              {activeStep.risk_level === 'SAFE' ? '✓' : '!'}
                            </span>
                            <span>Ollama Assessment: {activeStep.risk_level === 'SAFE' ? 'No anomaly detected' : `${activeStep.risk_level} Risk flagged`}</span>
                          </div>
                          
                          {/* Authorization check */}
                          <div className={`agent-checklist-item ${activeStep.status === 'WAITING_APPROVAL' ? 'danger' : 'success'}`}>
                            <span className={`agent-checklist-icon ${activeStep.status === 'WAITING_APPROVAL' ? 'danger' : 'success'}`}>
                              {activeStep.status === 'WAITING_APPROVAL' ? '!' : '✓'}
                            </span>
                            <span>Operator Approval: {activeStep.status === 'WAITING_APPROVAL' ? 'Awaiting bypass signature' : 'Auto-authorized'}</span>
                          </div>
                        </div>

                        {/* LLM Safety Explanation */}
                        {activeStep.explanation && (
                          <div className={`agent-guidance-card ${activeStep.risk_level.toLowerCase()}`} style={{ marginTop: '12px' }}>
                            <div style={{ fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', color: 'var(--color-text-muted)', marginBottom: '4px' }}>AI Safety Reasoning</div>
                            <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', lineHeight: '1.4' }}>{activeStep.explanation}</div>
                            {activeStep.recommendation && (
                              <>
                                <div style={{ fontSize: '11px', fontWeight: 'bold', textTransform: 'uppercase', color: 'var(--color-text-muted)', marginTop: '8px', marginBottom: '4px' }}>Mitigation Action</div>
                                <div style={{ fontSize: '12px', color: 'var(--color-text-secondary)', lineHeight: '1.4' }}>{activeStep.recommendation}</div>
                              </>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })() : (
                    <div style={{ textAlign: 'center', padding: '24px 10px', color: 'var(--color-text-muted)', fontSize: '13px' }}>
                      No active step. Select a runbook and click "Run Steps".
                    </div>
                  )}
                </div>

                {/* Internal Agent Log Feed */}
                <div className="agent-card-section">
                  <span className="agent-card-title">Live Feed</span>
                  <div className="agent-feed-container">
                    {agentLogs.map((log, idx) => (
                      <div key={idx} className="agent-feed-line">
                        <span className="agent-feed-time">[{log.time}]</span>
                        <span className={`agent-feed-text ${log.type}`}>{log.text}</span>
                      </div>
                    ))}
                    <div ref={agentFeedEndRef} />
                  </div>
                </div>

                {/* Agent Simulation & Tuning Controls */}
                <div className="agent-card-section">
                  <span className="agent-card-title">Guardrail Settings</span>
                  <div className="agent-controls-panel">
                    <div className="agent-control-row">
                      <span>Safety Mode</span>
                      <button 
                        className={`agent-toggle-button ${agentMode === 'STRICT' ? 'active' : ''}`}
                        onClick={() => {
                          const newMode = agentMode === 'STRICT' ? 'SIMULATION' : 'STRICT';
                          setAgentMode(newMode);
                          triggerToast(newMode === 'STRICT' ? 'Strict enforcement active.' : 'Guardrail simulation mode active.', 'info');
                          addAgentLog(`Safety mode changed to: ${newMode}.`, 'warning');
                        }}
                      >
                        {agentMode === 'STRICT' ? '🛡️ Strict Enforce' : '🔓 Permit All'}
                      </button>
                    </div>
                    
                    <div className="agent-control-row">
                      <span>Analysis Pulse Delay</span>
                      <select 
                        className="agent-select" 
                        value={analysisDelay} 
                        onChange={(e) => {
                          const val = Number(e.target.value);
                          setAnalysisDelay(val);
                          addAgentLog(`Analysis pulse delay updated to ${val}ms.`, 'system');
                        }}
                      >
                        <option value={1000}>1.0s (Normal)</option>
                        <option value={2000}>2.0s (Detailed)</option>
                        <option value={3000}>3.0s (Slow Thoughts)</option>
                        <option value={300}>0.3s (Instant)</option>
                      </select>
                    </div>
                  </div>
                </div>
              </div>
            </section>
          </div>
        )}

        {activeTab === 'audit' && (
          <section className="glass-panel audit-layout" style={{ padding: '24px' }}>
            {auditRunDetails ? (
              <>
                <div className="audit-header">
                  <div className="audit-meta">
                    <h2 style={{ fontSize: '24px' }}>{auditRunDetails.run.name}</h2>
                    <p style={{ color: 'var(--color-text-secondary)', fontSize: '14px' }}>
                      Run ID: {auditRunDetails.run.id} • Started: {new Date(auditRunDetails.run.created_at).toLocaleString()}
                      {auditRunDetails.run.completed_at && ` • Ended: ${new Date(auditRunDetails.run.completed_at).toLocaleString()}`}
                    </p>
                  </div>
                  <span className={`badge ${auditRunDetails.run.status.toLowerCase()}`} style={{ fontSize: '14px', padding: '6px 12px' }}>
                    {auditRunDetails.run.status}
                  </span>
                </div>

                {/* AI generated audit report */}
                <div className="glass-panel" style={{ background: 'rgba(0, 0, 0, 0.2)', border: '1px solid var(--border-glass)' }}>
                  <div className="report-markdown">
                    <h3 style={{ marginTop: 0, borderBottom: '1px solid var(--border-glass)', paddingBottom: '8px' }}>Execution Audit Summary Report</h3>
                    <div style={{ whiteSpace: 'pre-line', marginTop: '16px', color: 'var(--color-text-primary)' }}>
                      {auditRunDetails.run.audit_summary || 'No audit report generated for this run.'}
                    </div>
                  </div>
                </div>

                {/* Step breakdowns */}
                <div>
                  <h3 style={{ marginBottom: '16px', fontSize: '18px' }}>Individual Step Executions</h3>
                  <div className="audit-steps-list">
                    {auditRunDetails.steps.map((step) => {
                      const isExpanded = !!expandedSteps[step.id];
                      return (
                        <div key={step.id} className="audit-step-card">
                          <button className="audit-step-trigger" onClick={() => toggleStepExpansion(step.id)}>
                            <div className="audit-step-info">
                              <div style={{
                                width: '24px',
                                height: '24px',
                                borderRadius: '50%',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                fontSize: '11px',
                                fontWeight: 700,
                                background: step.status === 'SUCCESS' ? 'var(--color-success-glow)' : (step.status === 'FAILED' || step.status === 'FAILED_NEEDS_MCP' ? 'var(--color-danger-glow)' : 'rgba(255, 255, 255, 0.05)'),
                                color: step.status === 'SUCCESS' ? 'var(--color-success)' : (step.status === 'FAILED' || step.status === 'FAILED_NEEDS_MCP' ? 'var(--color-danger)' : 'var(--color-text-secondary)'),
                                border: '1px solid currentColor'
                              }}>
                                {step.step_number}
                              </div>
                              <div>
                                <span style={{ fontWeight: 600 }}>{step.description}</span>
                                {step.command && !step.corrected_command && <code style={{ marginLeft: '12px', fontSize: '12px', color: 'var(--color-primary-hover)' }}>{step.command}</code>}
                                {step.command && step.corrected_command && (
                                  <>
                                    <code style={{ marginLeft: '12px', fontSize: '12px', color: 'var(--color-danger)', textDecoration: 'line-through' }}>{step.command}</code>
                                    <span style={{ margin: '0 8px', color: 'var(--color-text-muted)', fontSize: '12px' }}>→</span>
                                    <code style={{ fontSize: '12px', color: 'var(--color-success)' }}>{step.corrected_command}</code>
                                  </>
                                )}
                              </div>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                              {step.command && <span className={`step-risk ${step.risk_level.toLowerCase()}`} style={{ marginRight: '8px' }}>{step.risk_level}</span>}
                              <span className={`badge ${step.status === 'FAILED_NEEDS_MCP' ? 'failed' : step.status.toLowerCase()}`}>
                                {step.status === 'FAILED_NEEDS_MCP' ? 'FAILED' : step.status}
                              </span>
                              <svg 
                                width="16" 
                                height="16" 
                                viewBox="0 0 24 24" 
                                fill="none" 
                                stroke="currentColor" 
                                strokeWidth="2.5" 
                                style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
                              >
                                <polyline points="6 9 12 15 18 9" />
                              </svg>
                            </div>
                          </button>

                          {isExpanded && (
                            <div className="audit-step-details">
                              {step.command && (
                                <>
                                  <div>
                                    <h4 style={{ fontSize: '13px', textTransform: 'uppercase', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>Safety Classification Detail</h4>
                                    <div style={{ fontSize: '14px', lineHeight: 1.5 }}>
                                      <strong>Explanation:</strong> {step.explanation || 'None'}
                                    </div>
                                    {step.recommendation && (
                                      <div style={{ fontSize: '14px', lineHeight: 1.5, marginTop: '4px' }}>
                                        <strong>Recommendation:</strong> {step.recommendation}
                                      </div>
                                    )}
                                  </div>
                                  {step.corrected_command && (
                                    <div style={{ borderLeft: '3px solid var(--color-success)', background: 'rgba(16, 185, 129, 0.05)', padding: '10px 14px', borderRadius: '4px' }}>
                                      <h4 style={{ fontSize: '13px', textTransform: 'uppercase', color: 'var(--color-success)', margin: '0 0 6px 0', fontWeight: 'bold' }}>Corrected Command / Action Suggestion</h4>
                                      <div style={{ fontFamily: 'var(--font-mono)', fontSize: '14px', whiteSpace: 'pre-wrap', color: 'var(--color-text-primary)' }}>
                                        {step.corrected_command}
                                      </div>
                                    </div>
                                  )}
                                  <div>
                                    <h4 style={{ fontSize: '13px', textTransform: 'uppercase', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>Terminal Stdout / Output</h4>
                                    <div className="output-box">{step.output || 'No output recorded.'}</div>
                                  </div>
                                </>
                              )}
                              {!step.command && (
                                <div style={{ fontStyle: 'italic', color: 'var(--color-text-muted)', fontSize: '14px' }}>
                                  Informational step (no command executed).
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>
              </>
            ) : (
              <div style={{ textAlign: 'center', color: 'var(--color-text-secondary)', padding: '60px 0' }}>
                Please select a completed run from the Dashboard Run History to view its audit report.
              </div>
            )}
          </section>
        )}
      </main>

      {/* Manual Approval Warning Alert Modal */}
      {approvalStep && (
        <div className="modal-overlay">
          <div className="glass-panel modal-content">
            <div className="warning-header">
              <svg className="warning-icon" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                <line x1="12" y1="9" x2="12" y2="13"/>
                <line x1="12" y1="17" x2="12.01" y2="17"/>
              </svg>
              <div>
                <h3 style={{ fontSize: '20px', fontWeight: 800 }}>Risky Action Blocked</h3>
                <p style={{ color: 'var(--color-text-secondary)', fontSize: '13px', marginTop: '2px' }}>
                  Safety Rating: <span className="step-risk high" style={{ fontSize: '10px' }}>{approvalStep.risk_level}</span>
                </p>
              </div>
            </div>

            <div>
              <h4 style={{ fontSize: '13px', textTransform: 'uppercase', color: 'var(--color-text-secondary)', marginBottom: '6px' }}>Staged Command</h4>
              <div className="warning-command-box">{approvalStep.command}</div>
            </div>

            <div className="warning-details">
              <h5>Safety Model Classification</h5>
              <p>{approvalStep.explanation || 'Risky command pattern matching standard blacklist/restricted binary rules.'}</p>
              {approvalStep.recommendation && (
                <p style={{ marginTop: '8px', borderTop: '1px solid rgba(255, 142, 60, 0.1)', paddingTop: '8px', fontSize: '13px' }}>
                  <strong>Recommendation:</strong> {approvalStep.recommendation}
                </p>
              )}
            </div>

            <div className="modal-actions">
              <button className="btn-deny" onClick={handleDeny}>
                Deny & Skip Step
              </button>
              <button className="btn-approve" onClick={handleApprove}>
                Approve & Execute
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
    </>
  );
}

export default App;
