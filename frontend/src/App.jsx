import { useState, useEffect, useCallback } from 'react';
import './App.css';

const API_BASE = 'http://127.0.0.1:8000';

// ── Toast Notification System ─────────────────────────────────────────────────
function Toast({ toasts, removeToast }) {
  return (
    <div style={{
      position: 'fixed', top: '24px', right: '24px', zIndex: 9999,
      display: 'flex', flexDirection: 'column', gap: '10px', maxWidth: '380px',
    }}>
      {toasts.map(t => (
        <div key={t.id} style={{
          background: t.type === 'error' ? 'rgba(243,139,168,0.15)' :
                      t.type === 'success' ? 'rgba(166,227,161,0.15)' :
                      t.type === 'warning' ? 'rgba(249,226,175,0.15)' :
                      'rgba(137,180,250,0.15)',
          border: `1px solid ${
            t.type === 'error'   ? 'rgba(243,139,168,0.4)' :
            t.type === 'success' ? 'rgba(166,227,161,0.4)' :
            t.type === 'warning' ? 'rgba(249,226,175,0.4)' :
            'rgba(137,180,250,0.4)'}`,
          borderLeft: `4px solid ${
            t.type === 'error'   ? '#f38ba8' :
            t.type === 'success' ? '#a6e3a1' :
            t.type === 'warning' ? '#f9e2af' : '#89b4fa'}`,
          borderRadius: '10px',
          padding: '14px 16px',
          backdropFilter: 'blur(12px)',
          boxShadow: '0 8px 24px rgba(0,0,0,0.4)',
          display: 'flex', alignItems: 'flex-start', gap: '12px',
          animation: 'slideIn 0.3s ease',
        }}>
          <span style={{ fontSize: '18px', lineHeight: 1 }}>
            {t.type === 'error' ? '⚠️' : t.type === 'success' ? '✅' :
             t.type === 'warning' ? '🔔' : 'ℹ️'}
          </span>
          <div style={{ flex: 1, fontSize: '0.88rem', lineHeight: '1.5',
                        color: 'var(--text-main)' }}>
            {t.title && <div style={{ fontWeight: 700, marginBottom: '2px' }}>{t.title}</div>}
            <div style={{ color: 'var(--text-sub)' }}>{t.message}</div>
          </div>
          <button onClick={() => removeToast(t.id)} style={{
            background: 'none', border: 'none', color: 'var(--text-muted)',
            cursor: 'pointer', fontSize: '16px', padding: '0', lineHeight: 1,
          }}>×</button>
        </div>
      ))}
    </div>
  );
}

// ── Toast hook ────────────────────────────────────────────────────────────────
function useToast() {
  const [toasts, setToasts] = useState([]);

  const addToast = useCallback((message, type = 'info', title = '', duration = 5000) => {
    const id = Date.now() + Math.random();
    setToasts(prev => [...prev, { id, message, type, title }]);
    if (duration > 0) {
      setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), duration);
    }
  }, []);

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  return { toasts, addToast, removeToast };
}

// ── Main App ──────────────────────────────────────────────────────────────────
function App() {
  const { toasts, addToast, removeToast } = useToast();

  const [health, setHealth] = useState({ api: 'checking...', smtp: false, gemini: false });
  const [clientForm, setClientForm] = useState({ name: '', email: '', website: '' });
  const [singleResult, setSingleResult] = useState(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSending, setIsSending] = useState(false);

  const [campaignStats, setCampaignStats] = useState(null);
  const [runningCampaignMode, setRunningCampaignMode] = useState(null);

  // CSV Upload State
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);

  // Auto-Responder State
  const [responderStatus, setResponderStatus] = useState({ active: false, history_count: 0 });
  const [responderHistory, setResponderHistory] = useState([]);
  const [isTogglingResponder, setIsTogglingResponder] = useState(false);
  const [isCheckingResponder, setIsCheckingResponder] = useState(false);

  // Email Validation State
  const [validatorFile, setValidatorFile] = useState(null);
  const [isValidating, setIsValidating] = useState(false);
  const [validationResults, setValidationResults] = useState(null);
  const [validatorTab, setValidatorTab] = useState('single');

  // Single Email Verification State
  const [verifyEmailInput, setVerifyEmailInput] = useState('');
  const [isVerifyingSingle, setIsVerifyingSingle] = useState(false);
  const [singleVerifyResult, setSingleVerifyResult] = useState(null);

  // Top Navigation Tab State
  const [activeNavTab, setActiveNavTab] = useState('outreach'); // 'outreach' | 'internship' | 'verifier' | 'responder' | 'sales'

  // Sales Campaign State
  const [salesCount, setSalesCount] = useState(10);
  const [salesStatus, setSalesStatus] = useState(null);
  const [salesRunning, setSalesRunning] = useState(false);
  const [salesHistory, setSalesHistory] = useState([]);
  const [salesHistTotal, setSalesHistTotal] = useState(0);
  const [isFetchingSalesHistory, setIsFetchingSalesHistory] = useState(false);

  // ── Google Sheets Campaign State ──────────────────────────────────────────
  const [sheetUrl, setSheetUrl] = useState('');
  const [sheetLimit, setSheetLimit] = useState('');
  const [sheetMode, setSheetMode] = useState('dry_run');
  const [lastSession, setLastSession] = useState(null);
  const [isSheetLaunching, setIsSheetLaunching] = useState(false);
  const [sheetLaunchResult, setSheetLaunchResult] = useState(null);

  // Internship State
  const [internSubTab, setInternSubTab] = useState('single'); // 'single' | 'bulk'
  const [singleInternForm, setSingleInternForm] = useState({
    name: 'Alex Morgan',
    email: 'alex.morgan@example.com',
    role: 'AI Research Intern',
    department: 'Artificial Intelligence',
    start_date: 'September 1, 2026',
    duration: '3 Months',
    location: 'Remote',
    intern_id: 'NEX-2026-INT-001'
  });

  const [internsList, setInternsList] = useState([
    {
      name: 'Alex Morgan',
      email: 'alex.morgan@example.com',
      role: 'AI Research Intern',
      department: 'Artificial Intelligence',
      start_date: 'September 1, 2026',
      duration: '3 Months',
      location: 'Remote',
      intern_id: 'NEX-2026-INT-001',
    },
    {
      name: 'Sophia Chen',
      email: 'sophia.chen@example.com',
      role: 'Frontend Developer Intern',
      department: 'Web Platform',
      start_date: 'September 1, 2026',
      duration: '3 Months',
      location: 'Hybrid',
      intern_id: 'NEX-2026-INT-002',
    }
  ]);
  const [selectedInternFile, setSelectedInternFile] = useState(null);
  const [isUploadingInterns, setIsUploadingInterns] = useState(false);
  const [selectedInternIdx, setSelectedInternIdx] = useState(0);
  const [internConfig, setInternConfig] = useState({
    company_name: 'Nexariza AI Technologies',
    hr_name: 'Ahmad Yasin',
    hr_title: 'Founder & CEO',
    custom_note: 'We are thrilled to welcome you to our innovation team!'
  });
  const [internPreviewData, setInternPreviewData] = useState(null);
  const [isPreviewLoading, setIsPreviewLoading] = useState(false);
  const [internBatchStatus, setInternBatchStatus] = useState(null);
  const [isInternBatchRunning, setIsInternBatchRunning] = useState(false);
  const [isSendingSingleIntern, setIsSendingSingleIntern] = useState(false);
  const [previewTabMode, setPreviewTabMode] = useState('full_email'); // 'full_email' | 'card'

  // Background Campaign execution state
  const [campaignStatus, setCampaignStatus] = useState(null);
  const [isCampaignRunning, setIsCampaignRunning] = useState(false);

  const fetchSalesStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/sales/status`);
      if (res.ok) {
        const data = await res.json();
        setSalesStatus(data);
        setSalesRunning(data.status === 'running');
      }
    } catch (e) { /* ignore */ }
  };

  const fetchSalesHistory = async () => {
    setIsFetchingSalesHistory(true);
    try {
      const res = await fetch(`${API_BASE}/sales/history`);
      if (res.ok) {
        const data = await res.json();
        setSalesHistory(data.records || []);
        setSalesHistTotal(data.total || 0);
      }
    } catch (e) { /* ignore */ } finally {
      setIsFetchingSalesHistory(false);
    }
  };

  // ── Google Sheets Handlers ─────────────────────────────────────────────────
  const fetchLastSession = async () => {
    try {
      const res = await fetch(`${API_BASE}/campaign/last-session`);
      if (res.ok) {
        const data = await res.json();
        setLastSession(data);
        // Pre-fill the sheet URL from last session (only if user hasn't typed one yet)
        if (data.has_session && data.sheet_url) {
          setSheetUrl(prev => prev || data.sheet_url);
        }
      }
    } catch (e) { /* ignore */ }
  };

  const handleSheetCampaign = async () => {
    if (!sheetUrl.trim()) {
      addToast('Please paste your Google Sheets link first.', 'warning', 'Missing Sheet URL');
      return;
    }
    if (isCampaignRunning) {
      addToast('A campaign is already running. Wait for it to finish.', 'warning', 'Campaign Active');
      return;
    }
    setIsSheetLaunching(true);
    setSheetLaunchResult(null);
    try {
      const body = {
        sheet_url: sheetUrl.trim(),
        mode: sheetMode,
        delay_seconds: 60,
        sort_by_score: true,
      };
      if (sheetLimit && parseInt(sheetLimit, 10) > 0) {
        body.limit = parseInt(sheetLimit, 10);
      }
      const res = await fetch(`${API_BASE}/campaign/from-sheet`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (res.ok) {
        setSheetLaunchResult(data);
        setIsCampaignRunning(true);
        addToast(
          `${data.queued_for_sending} lead(s) queued from Google Sheet! ${data.already_emailed} already emailed (skipped).`,
          'success',
          '📊 Sheet Campaign Launched'
        );
        checkCampaignStatus();
        // Refresh session after a delay to pick up the new session save
        setTimeout(fetchLastSession, 5000);
      } else {
        addToast(data.detail || 'Failed to launch sheet campaign.', 'error', 'Launch Error');
      }
    } catch (e) {
      addToast('Could not reach backend. Is the server running?', 'error', 'Network Error');
    } finally {
      setIsSheetLaunching(false);
    }
  };

  const handleStartSales = async () => {
    if (salesRunning) return;
    setSalesRunning(true);
    try {
      const res = await fetch(`${API_BASE}/sales/run?count=${salesCount}`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        addToast(`Sales campaign started for ${data.total} prospects`, 'success', 'Campaign Launched');
        fetchSalesStatus();
      } else {
        addToast(data.detail || 'Failed to start campaign', 'error', 'Error');
        setSalesRunning(false);
      }
    } catch (e) {
      addToast('Cannot reach backend', 'error', 'Network Error');
      setSalesRunning(false);
    }
  };

  const handleCancelSales = async () => {
    try {
      await fetch(`${API_BASE}/sales/cancel`, { method: 'POST' });
      addToast('Cancel signal sent', 'info', 'Cancelling');
    } catch (e) { /* ignore */ }
  };

  useEffect(() => {
    checkHealth();
    checkCampaignStatus();
    checkInternshipBatchStatus();
    fetchResponderStatus();
    fetchResponderHistory();
    fetchSalesStatus();
    fetchLastSession();

    const interval = setInterval(() => {
      checkHealth();
      fetchResponderStatus();
      fetchResponderHistory();
      checkInternshipBatchStatus();
      fetchSalesStatus();
    }, 8000);
    return () => clearInterval(interval);
  }, []);

  const checkInternshipBatchStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/internship/status`);
      if (res.ok) {
        const data = await res.json();
        setInternBatchStatus(data);
        setIsInternBatchRunning(data.status === 'running');
      }
    } catch (e) {
      console.error('Failed to fetch internship status', e);
    }
  };

  const fetchResponderStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/responder/status`);
      if (res.ok) {
        const data = await res.json();
        setResponderStatus(data);
      }
    } catch (e) {
      console.error('Failed to fetch responder status', e);
    }
  };

  const fetchResponderHistory = async () => {
    try {
      const res = await fetch(`${API_BASE}/responder/history`);
      if (res.ok) {
        const data = await res.json();
        setResponderHistory(data);
      }
    } catch (e) {
      console.error('Failed to fetch responder history', e);
    }
  };

  const handleToggleResponder = async () => {
    setIsTogglingResponder(true);
    try {
      const res = await fetch(`${API_BASE}/responder/toggle`, { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setResponderStatus(prev => ({ ...prev, active: data.active, status: data.status }));
        addToast(
          `Auto-Responder is now ${data.active ? 'active and monitoring inbox' : 'stopped'}`,
          data.active ? 'success' : 'info',
          data.active ? 'Agent Started' : 'Agent Stopped'
        );
      } else {
        addToast('Could not toggle the responder. Is the backend running?', 'error', 'Toggle Failed');
      }
    } catch (e) {
      addToast('Cannot reach the backend server.', 'error', 'Network Error');
    } finally {
      setIsTogglingResponder(false);
    }
  };

  const handleCheckResponder = async () => {
    setIsCheckingResponder(true);
    try {
      const res = await fetch(`${API_BASE}/responder/check`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        if (data.status === 'ok') {
          addToast(
            `Processed: ${data.processed} emails · Replied: ${data.replied}`,
            'success',
            'Inbox Scan Complete'
          );
        } else {
          // IMAP not yet enabled — show as a soft warning, not an error popup
          const msg = data.message || 'Unknown error';
          if (msg.includes('IMAP') || msg.includes('enable')) {
            addToast(
              'Zoho IMAP is not enabled yet. Enable it in Zoho Mail settings under Mail Accounts → IMAP Access.',
              'warning',
              'IMAP Not Enabled'
            );
          } else {
            addToast(msg, 'warning', 'Scan Warning');
          }
        }
        fetchResponderStatus();
        fetchResponderHistory();
      } else {
        addToast('Failed to trigger inbox scan.', 'error', 'Scan Error');
      }
    } catch (e) {
      addToast('Cannot reach the backend server.', 'error', 'Network Error');
    } finally {
      setIsCheckingResponder(false);
    }
  };

  const checkHealth = async () => {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (res.ok) {
        const data = await res.json();
        setHealth({ api: 'online', smtp: data.smtp, gemini: data.gemini_key_set });
      } else {
        setHealth({ api: 'offline', smtp: false, gemini: false });
      }
    } catch (e) {
      setHealth({ api: 'offline', smtp: false, gemini: false });
    }
  };

  // Campaign Status Polling useEffect
  useEffect(() => {
    let pollInterval;
    if (isCampaignRunning) {
      pollInterval = setInterval(() => {
        checkCampaignStatus();
      }, 2000);
    } else {
      // Periodically check (every 10s) just in case
      pollInterval = setInterval(() => {
        checkCampaignStatus();
      }, 10000);
    }
    return () => clearInterval(pollInterval);
  }, [isCampaignRunning]);

  const checkCampaignStatus = async () => {
    try {
      const res = await fetch(`${API_BASE}/campaign/status`);
      if (res.ok) {
        const data = await res.json();
        setCampaignStatus(data);
        const running = data.status === 'running';
        setIsCampaignRunning(running);
        
        // If the campaign finished/was cancelled, set campaign stats for rendering
        if (data.status === 'completed' || data.status === 'cancelled' || data.status === 'failed') {
          setCampaignStats(data);
        }
      }
    } catch (e) {
      console.error('Failed to fetch campaign status', e);
    }
  };

  const handleVerifySingleEmail = async () => {
    if (!verifyEmailInput.trim()) {
      addToast('Please enter an email address to verify.', 'warning', 'Missing Email');
      return;
    }
    setIsVerifyingSingle(true);
    setSingleVerifyResult(null);
    try {
      const res = await fetch(`${API_BASE}/email/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: verifyEmailInput.trim() })
      });
      const data = await res.json();
      if (res.ok) {
        setSingleVerifyResult(data);
        if (data.is_valid) {
          addToast(
            `Email exists and is deliverable!`,
            'success',
            'Verification Success'
          );
        } else {
          addToast(
            `Email is undeliverable: ${data.reason}`,
            'error',
            'Verification Failed'
          );
        }
      } else {
        addToast(data.detail || 'Verification request failed.', 'error', 'Error');
      }
    } catch (e) {
      addToast('Could not connect to the backend server.', 'error', 'Network Error');
    } finally {
      setIsVerifyingSingle(false);
    }
  };

  const handleCancelCampaign = async () => {
    try {
      const res = await fetch(`${API_BASE}/campaign/cancel`, {
        method: 'POST'
      });
      const data = await res.json();
      if (res.ok) {
        addToast('Cancellation request sent to server.', 'info', 'Stopping Campaign');
        checkCampaignStatus();
      } else {
        addToast(data.detail || 'Failed to cancel campaign.', 'error', 'Error');
      }
    } catch (e) {
      addToast('Could not reach backend.', 'error', 'Network Error');
    }
  };

  // ── Internship Handlers ───────────────────────────────────────────────────
  const handleUploadInternCSV = async () => {
    if (!selectedInternFile) {
      addToast('Please select an intern CSV file first.', 'warning', 'No File Selected');
      return;
    }

    setIsUploadingInterns(true);
    const formData = new FormData();
    formData.append('file', selectedInternFile);

    try {
      const res = await fetch(`${API_BASE}/internship/upload-csv`, {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();
      if (res.ok) {
        if (!data.interns || data.interns.length === 0) {
          addToast(
            `Uploaded ${selectedInternFile.name}, but 0 valid intern records were found.`,
            'warning',
            'No Interns Found'
          );
        } else {
          setInternsList(data.interns);
          setSelectedInternIdx(0);
          addToast(
            `Loaded ${data.total_interns} interns from ${selectedInternFile.name}!`,
            'success',
            'CSV Uploaded'
          );
        }
      } else {
        addToast(data.detail || 'Upload failed.', 'error', 'Upload Error');
      }
    } catch (e) {
      addToast('Could not reach backend. Is the server running?', 'error', 'Network Error');
    } finally {
      setIsUploadingInterns(false);
    }
  };

  const handlePreviewIntern = async (internObj) => {
    const targetIntern = internObj || (internSubTab === 'single' ? singleInternForm : internsList[selectedInternIdx]);
    if (!targetIntern) return;

    setIsPreviewLoading(true);
    try {
      const res = await fetch(`${API_BASE}/internship/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          intern: targetIntern,
          config: internConfig,
          mode: 'dry_run'
        })
      });

      const data = await res.json();
      if (res.ok) {
        setInternPreviewData(data);
      } else {
        addToast(data.detail || 'Failed to generate preview.', 'error', 'Preview Error');
      }
    } catch (e) {
      addToast('Could not connect to backend.', 'error', 'Network Error');
    } finally {
      setIsPreviewLoading(false);
    }
  };

  const handleSendSingleIntern = async (mode) => {
    const targetIntern = internSubTab === 'single' ? singleInternForm : internsList[selectedInternIdx];
    if (!targetIntern || !targetIntern.name || !targetIntern.email) {
      addToast('Intern Name and Email are required.', 'warning', 'Missing Fields');
      return;
    }

    setIsSendingSingleIntern(true);
    try {
      const res = await fetch(`${API_BASE}/internship/send-single`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          intern: targetIntern,
          config: internConfig,
          mode: mode
        })
      });

      const data = await res.json();
      if (res.ok) {
        if (data.status === 'sent') {
          addToast(
            `Offer letter and Intern ID card successfully emailed to ${targetIntern.email}!`,
            'success',
            'Offer Email Sent!'
          );
        } else if (data.status === 'previewed') {
          addToast(
            `Dry run successful for ${targetIntern.name}!`,
            'info',
            'Dry Run Complete'
          );
        } else {
          addToast(
            `Dispatch failed: ${data.error}`,
            'error',
            'Send Failed'
          );
        }
      } else {
        addToast(data.detail || 'Send failed.', 'error', 'Error');
      }
    } catch (e) {
      addToast('Could not reach backend.', 'error', 'Network Error');
    } finally {
      setIsSendingSingleIntern(false);
    }
  };

  const handleRunInternshipBatch = async (mode) => {
    if (internsList.length === 0) {
      addToast('No interns loaded in the list. Please upload a CSV first.', 'warning', 'List Empty');
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/internship/run-batch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          interns: internsList,
          config: internConfig,
          mode: mode,
          delay_seconds: 5
        })
      });

      const data = await res.json();
      if (res.ok) {
        setIsInternBatchRunning(true);
        addToast(
          `Internship email campaign launched in ${mode.toUpperCase()} mode for ${internsList.length} interns!`,
          'success',
          'Campaign Launched'
        );
        checkInternshipBatchStatus();
      } else {
        addToast(data.detail || 'Failed to launch internship campaign.', 'error', 'Launch Error');
      }
    } catch (e) {
      addToast('Could not reach backend.', 'error', 'Network Error');
    }
  };

  const handleCancelInternshipBatch = async () => {
    try {
      const res = await fetch(`${API_BASE}/internship/cancel`, { method: 'POST' });
      if (res.ok) {
        addToast('Cancelling internship dispatch campaign...', 'info', 'Cancellation Requested');
        checkInternshipBatchStatus();
      }
    } catch (e) {
      addToast('Could not cancel campaign.', 'error', 'Network Error');
    }
  };

  const handleSingleAnalyze = async (mode) => {
    if (!clientForm.name || !clientForm.email) {
      addToast('Name and Email are required to generate a pitch.', 'warning', 'Missing Fields');
      return;
    }

    if (mode === 'live') setIsSending(true);
    else setIsGenerating(true);
    setSingleResult(null);

    try {
      const res = await fetch(`${API_BASE}/client/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ client: clientForm, mode })
      });

      const data = await res.json();
      if (res.ok) {
        setSingleResult(data);
        addToast(
          mode === 'live' ? `Email sent to ${clientForm.email}` : 'Email preview generated successfully',
          'success',
          mode === 'live' ? 'Email Sent!' : 'Preview Ready'
        );
      } else {
        addToast(data.detail || 'Something went wrong.', 'error', 'Generation Failed');
      }
    } catch (e) {
      addToast('Could not reach backend. Is the server running?', 'error', 'Network Error');
    } finally {
      setIsGenerating(false);
      setIsSending(false);
    }
  };

  const handleRunBatch = async (mode) => {
    if (isCampaignRunning) {
      addToast('A campaign is already running.', 'warning', 'Campaign Active');
      return;
    }
    setRunningCampaignMode(mode);
    try {
      const res = await fetch(`${API_BASE}/campaign/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode, delay_seconds: 60, sort_by_score: true })
      });

      const data = await res.json();
      if (res.ok) {
        setCampaignStatus(data);
        setIsCampaignRunning(true);
        addToast(
          `Campaign started in background (${mode === 'live' ? 'Live' : 'Dry Run'}).`,
          'success',
          'Campaign Launched'
        );
      } else {
        addToast(data.detail || 'Campaign failed to launch.', 'error', 'Campaign Error');
      }
    } catch (e) {
      addToast('Could not reach backend. Is the server running?', 'error', 'Network Error');
    } finally {
      setRunningCampaignMode(null);
    }
  };

  const handleUploadCSV = async () => {
    if (!selectedFile) {
      addToast('Please select a CSV file first.', 'warning', 'No File Selected');
      return;
    }

    setIsUploading(true);
    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const res = await fetch(`${API_BASE}/campaign/upload`, {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();
      if (res.ok) {
        if (data.total_leads === 0) {
          addToast(
            `Uploaded ${selectedFile.name}, but 0 valid leads were found. Make sure your CSV contains populated email addresses.`,
            'warning',
            'No Leads Found'
          );
        } else {
          addToast(
            `Successfully uploaded ${selectedFile.name} (${data.total_leads} valid leads found).`,
            'success',
            'Upload Complete'
          );
        }
        setSelectedFile(null); // Reset file input implicitly
      } else {
        addToast(data.detail || 'Upload failed.', 'error', 'Upload Error');
      }
    } catch (e) {
      addToast('Could not reach backend. Is the server running?', 'error', 'Network Error');
    } finally {
      setIsUploading(false);
    }
  };

  const handleValidateCSV = async () => {
    if (!validatorFile) {
      addToast('Please select a CSV file first.', 'warning', 'No File Selected');
      return;
    }

    setIsValidating(true);
    const formData = new FormData();
    formData.append('file', validatorFile);

    try {
      const res = await fetch(`${API_BASE}/campaign/validate-csv`, {
        method: 'POST',
        body: formData,
      });

      const data = await res.json();
      if (res.ok) {
        setValidationResults(data);
        addToast(
          `Checked ${data.total_checked} leads. ${data.valid_count} valid, ${data.invalid_count} invalid.`,
          data.invalid_count > 0 ? 'warning' : 'success',
          'Validation Complete'
        );
      } else {
        addToast(data.detail || 'Validation failed.', 'error', 'Validation Error');
      }
    } catch (e) {
      addToast('Could not reach backend. Is the server running?', 'error', 'Network Error');
    } finally {
      setIsValidating(false);
    }
  };

  const handleDownloadCleanedCSV = () => {
    if (!validationResults) return;
    
    const validRows = validationResults.results.filter(r => r.is_valid).map(r => r.original_row);
    if (validRows.length === 0) {
      addToast('No valid emails to download.', 'warning', 'Empty Result');
      return;
    }
    
    const headers = Object.keys(validRows[0]);
    const csvContent = [
      headers.join(','),
      ...validRows.map(row => headers.map(h => `"${(row[h] || '').replace(/"/g, '""')}"`).join(','))
    ].join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', 'cleaned_clients.csv');
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // SMTP status helper
  const smtpOk = health.smtp?.status === 'ok';

  return (
    <div className="app-container">
      {/* Toast Overlay */}
      <Toast toasts={toasts} removeToast={removeToast} />

      <header className="header">
        <h1>Nexariza AI Outreach & Internship Agent</h1>
        <p>Automate cold email campaigns, issue official internship offer letters, and send futuristic intern ID cards.</p>

        <div className="status-indicator">
          <span className={`badge ${health.api === 'online' ? 'badge-success' : 'badge-error'}`}>
            API: {health.api.toUpperCase()}
          </span>
          <span className={`badge ${smtpOk ? 'badge-info' : 'badge-warning'}`}>
            SMTP: {smtpOk ? 'CONNECTED' : 'DISCONNECTED'}
          </span>
          <span className={`badge ${health.gemini ? 'badge-success' : 'badge-error'}`}>
            GROQ: {health.gemini ? 'READY' : 'MISSING KEY'}
          </span>
        </div>
      </header>

      {/* Top Navigation Tab Bar */}
      <div className="top-nav-tabs">
        <button
          className={`nav-tab-btn ${activeNavTab === 'outreach' ? 'active' : ''}`}
          onClick={() => setActiveNavTab('outreach')}
        >
          📊 Cold Email Outreach
        </button>
        <button
          className={`nav-tab-btn ${activeNavTab === 'internship' ? 'active' : ''}`}
          onClick={() => {
            setActiveNavTab('internship');
            if (internsList.length > 0 && !internPreviewData) {
              handlePreviewIntern(internsList[0]);
            }
          }}
        >
          🎓 Intern Offer & ID Cards
        </button>
        <button
          className={`nav-tab-btn ${activeNavTab === 'verifier' ? 'active' : ''}`}
          onClick={() => setActiveNavTab('verifier')}
        >
          🔍 Email Verifier
        </button>
        <button
          className={`nav-tab-btn ${activeNavTab === 'responder' ? 'active' : ''}`}
          onClick={() => setActiveNavTab('responder')}
        >
          🤖 Auto-Responder
        </button>
        <button
          className={`nav-tab-btn ${activeNavTab === 'sales' ? 'active' : ''}`}
          onClick={() => { setActiveNavTab('sales'); fetchSalesStatus(); fetchSalesHistory(); }}
          style={activeNavTab === 'sales' ? {} : { borderColor: 'rgba(250,179,135,0.4)', color: '#fab387' }}
        >
          💼 Sales Campaign
        </button>
        <button
          className={`nav-tab-btn ${activeNavTab === 'sheets' ? 'active' : ''}`}
          onClick={() => { setActiveNavTab('sheets'); fetchLastSession(); checkCampaignStatus(); }}
          style={activeNavTab === 'sheets' ? {} : { borderColor: 'rgba(137,220,235,0.4)', color: '#89dceb' }}
        >
          📊 Sheets Campaign
        </button>
      </div>

      {/* 📊 COLD EMAIL OUTREACH TAB */}
      {activeNavTab === 'outreach' && (
      <div className="dashboard-grid" style={{ animation: 'fadeIn 0.4s ease' }}>
        {/* Single Client Section */}
        <section className="glass-panel" style={{ padding: '32px' }}>
          <div className="card-header">
            <h2>Single Client Test</h2>
            <p>Generate a pitch for a single prospect to test the AI.</p>
          </div>

          <div className="form-group">
            <label>Prospect Name</label>
            <input
              type="text"
              placeholder="e.g. John Doe"
              value={clientForm.name}
              onChange={e => setClientForm({...clientForm, name: e.target.value})}
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Email Address</label>
              <input
                type="email"
                placeholder="john@example.com"
                value={clientForm.email}
                onChange={e => setClientForm({...clientForm, email: e.target.value})}
              />
            </div>
            <div className="form-group">
              <label>Website (Optional)</label>
              <input
                type="url"
                placeholder="https://example.com"
                value={clientForm.website}
                onChange={e => setClientForm({...clientForm, website: e.target.value})}
              />
            </div>
          </div>

          <div style={{ display: 'flex', gap: '16px', marginTop: '16px' }}>
            <button
              className="btn btn-primary"
              style={{ flex: 1 }}
              onClick={() => handleSingleAnalyze('dry_run')}
              disabled={isGenerating || isSending || health.api !== 'online'}
            >
              {isGenerating ? <span className="loader"></span> : '✨ Generate & Preview'}
            </button>
            <button
              className="btn btn-accent"
              onClick={() => handleSingleAnalyze('live')}
              disabled={isGenerating || isSending || health.api !== 'online' || !smtpOk}
            >
              {isSending ? <span className="loader"></span> : '🚀 Send Live'}
            </button>
          </div>

          {singleResult && (
            <div className="email-preview">
              <div className="email-preview-header">
                <span className={`badge ${singleResult.status === 'sent' ? 'badge-success' : (singleResult.status === 'failed' ? 'badge-error' : 'badge-info')}`}>
                  {singleResult.status.toUpperCase()}
                </span>
                <div className="email-preview-subject" style={{ marginTop: '12px' }}>
                  Subject: {singleResult.generated_subject}
                </div>
              </div>
              <div className="email-preview-body">
                {singleResult.generated_body}
              </div>
            </div>
          )}
        </section>

        {/* Batch Campaign Section */}
        <section className="glass-panel" style={{ padding: '32px' }}>
          <div className="card-header">
            <h2>Batch Campaign</h2>
            <p>Run a campaign from <code>clients.csv</code> — sorted by Lead Score &amp; Priority automatically.</p>
          </div>

          <div className="form-group" style={{ marginBottom: '24px', background: 'rgba(255, 255, 255, 0.03)', padding: '16px', borderRadius: '12px', border: '1px dashed rgba(255, 255, 255, 0.1)' }}>
            <label style={{ display: 'block', marginBottom: '8px', fontSize: '0.9rem', color: 'var(--text-main)' }}>Upload Custom Clients Data</label>
            <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
              <input 
                type="file" 
                accept=".csv"
                onChange={(e) => setSelectedFile(e.target.files[0])}
                style={{ flex: 1, padding: '8px', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'var(--text-sub)' }}
              />
              <button 
                className="btn btn-secondary"
                onClick={handleUploadCSV}
                disabled={!selectedFile || isUploading || health.api !== 'online'}
                style={{ padding: '10px 20px', whiteSpace: 'nowrap' }}
              >
                {isUploading ? 'Uploading...' : 'Upload CSV'}
              </button>
            </div>
          </div>

          {isCampaignRunning && campaignStatus && (
            <div style={{ background: 'rgba(255,255,255,0.03)', padding: '20px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.08)', marginBottom: '24px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                <span style={{ fontWeight: 'bold', color: 'var(--primary-light)', fontSize: '0.95rem' }}>
                  ⚡ Status: {campaignStatus.status.toUpperCase()} ({campaignStatus.mode?.toUpperCase()})
                </span>
                <span style={{ fontSize: '0.88rem', color: 'var(--text-sub)' }}>
                  {campaignStatus.processed} / {campaignStatus.total} Leads
                </span>
              </div>
              
              <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden', marginBottom: '16px' }}>
                <div style={{ 
                  width: `${(campaignStatus.processed / (campaignStatus.total || 1)) * 100}%`, 
                  height: '100%', 
                  background: 'linear-gradient(90deg, var(--primary) 0%, var(--secondary) 100%)',
                  transition: 'width 0.5s ease-in-out'
                }}></div>
              </div>

              {campaignStatus.current_lead && (
                <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginBottom: '16px' }}>
                  👉 Processing: <span style={{ color: 'var(--text-main)', fontWeight: 'bold' }}>{campaignStatus.current_lead}</span>
                </div>
              )}

              <div style={{ display: 'flex', gap: '16px', fontSize: '0.85rem', marginBottom: '16px' }}>
                <div style={{ color: 'var(--secondary)' }}>✅ Sent: {campaignStatus.sent}</div>
                <div style={{ color: 'var(--accent)' }}>❌ Failed: {campaignStatus.failed}</div>
                <div style={{ color: 'var(--text-muted)' }}>⏭️ Skipped: {campaignStatus.skipped}</div>
              </div>

              <button 
                className="btn btn-secondary" 
                onClick={handleCancelCampaign}
                style={{ width: '100%', background: 'rgba(243,139,168,0.15)', color: '#f38ba8', border: '1px solid rgba(243,139,168,0.3)', padding: '10px 14px', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }}
              >
                🛑 Cancel Campaign
              </button>
            </div>
          )}

          {!isCampaignRunning && campaignStats && (
            <>
              <div className="stats-grid">
                <div className="stat-box">
                  <div className="stat-value stat-info">{campaignStats.total}</div>
                  <div className="stat-label">Total</div>
                </div>
                <div className="stat-box">
                  <div className="stat-value stat-success">{campaignStats.sent}</div>
                  <div className="stat-label">{campaignStats.mode === 'live' ? 'Sent' : 'Previewed'}</div>
                </div>
                <div className="stat-box">
                  <div className="stat-value stat-error">{campaignStats.failed}</div>
                  <div className="stat-label">Failed</div>
                </div>
              </div>
              <div style={{ marginBottom: '24px', fontSize: '0.9rem', color: 'var(--text-muted)' }}>
                <strong>Last Run Mode:</strong> {campaignStats.mode ? campaignStats.mode.toUpperCase() : 'UNKNOWN'} 
                {campaignStats.status === 'cancelled' && <span style={{ color: '#f38ba8', marginLeft: '8px' }}>[CANCELLED]</span>}
              </div>
            </>
          )}

          {!isCampaignRunning && !campaignStats && (
            <div style={{ marginBottom: '24px', color: 'var(--text-muted)' }}>
              No campaigns run yet. Ensure <code>clients.csv</code> is in the root directory.
            </div>
          )}

          <div style={{ display: 'flex', gap: '16px' }}>
            <button
              className="btn btn-secondary"
              style={{ flex: 1 }}
              onClick={() => handleRunBatch('dry_run')}
              disabled={isCampaignRunning || runningCampaignMode !== null || health.api !== 'online'}
            >
              {runningCampaignMode === 'dry_run' ? 'Running...' : '👀 Dry Run CSV'}
            </button>
            <button
              className="btn btn-accent"
              style={{ flex: 1 }}
              onClick={() => handleRunBatch('live')}
              disabled={isCampaignRunning || runningCampaignMode !== null || health.api !== 'online' || !smtpOk}
            >
              {runningCampaignMode === 'live' ? 'Sending...' : '🔥 Launch Campaign'}
            </button>
          </div>
        </section>
      </div>
      )}

      {/* 📊 GOOGLE SHEETS CAMPAIGN TAB */}
      {activeNavTab === 'sheets' && (
        <div style={{ animation: 'fadeIn 0.4s ease', maxWidth: '800px', margin: '0 auto', padding: '0 16px' }}>

          {/* ── Last Session Memory Card ───────────────────────────────── */}
          {lastSession && lastSession.has_session && (
            <div style={{
              background: 'linear-gradient(135deg, rgba(137,220,235,0.08) 0%, rgba(116,199,236,0.05) 100%)',
              border: '1px solid rgba(137,220,235,0.25)',
              borderRadius: '16px',
              padding: '20px 24px',
              marginBottom: '24px',
              display: 'flex',
              alignItems: 'center',
              gap: '20px',
            }}>
              <div style={{ fontSize: '2rem' }}>🕐</div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: '700', color: '#89dceb', fontSize: '1rem', marginBottom: '4px' }}>
                  Last Campaign Remembered
                </div>
                <div style={{ fontSize: '0.88rem', color: 'var(--text-sub)', lineHeight: 1.6 }}>
                  <strong style={{ color: 'var(--text-main)' }}>{lastSession.sent_count}</strong> emails sent
                  {' '}({lastSession.mode?.toUpperCase()}) on{' '}
                  <strong style={{ color: 'var(--text-main)' }}>
                    {lastSession.timestamp ? new Date(lastSession.timestamp).toLocaleString() : 'unknown date'}
                  </strong>
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '4px', wordBreak: 'break-all' }}>
                  📄 {lastSession.sheet_url?.substring(0, 80)}{lastSession.sheet_url?.length > 80 ? '...' : ''}
                </div>
              </div>
              <div style={{
                textAlign: 'center',
                background: 'rgba(137,220,235,0.1)',
                borderRadius: '12px',
                padding: '12px 16px',
                minWidth: '80px',
              }}>
                <div style={{ fontSize: '1.8rem', fontWeight: '800', color: '#89dceb' }}>{lastSession.sent_count}</div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '2px' }}>SENT LAST TIME</div>
              </div>
            </div>
          )}

          {/* ── Main Panel ──────────────────────────────────────────── */}
          <section className="glass-panel" style={{ padding: '32px' }}>
            <div className="card-header">
              <h2>📊 Google Sheets Campaign</h2>
              <p>
                Paste a Google Sheets link, choose how many contacts to email, and launch.
                All emails are sent from <code>contact@nexariza.com</code> using the same AI pipeline — already-emailed contacts are automatically skipped.
              </p>
            </div>

            {/* Sheet URL */}
            <div className="form-group" style={{ marginBottom: '20px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                🔗 Google Sheets URL
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 'normal' }}>
                  (must be shared publicly: "Anyone with link can view")
                </span>
              </label>
              <input
                id="sheet-url-input"
                type="url"
                placeholder="https://docs.google.com/spreadsheets/d/YOUR_SHEET_ID/edit..."
                value={sheetUrl}
                onChange={e => setSheetUrl(e.target.value)}
                style={{
                  width: '100%',
                  padding: '12px 16px',
                  fontSize: '0.9rem',
                  background: 'rgba(137,220,235,0.05)',
                  border: '1px solid rgba(137,220,235,0.2)',
                  borderRadius: '10px',
                  color: 'var(--text-main)',
                  boxSizing: 'border-box',
                }}
              />
            </div>

            {/* How many to send + Mode */}
            <div className="form-row" style={{ marginBottom: '24px' }}>
              <div className="form-group">
                <label style={{ marginBottom: '8px', display: 'block' }}>
                  📬 How Many People to Email?
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 'normal', marginLeft: '6px' }}>
                    (blank = all new contacts)
                  </span>
                </label>
                <input
                  id="sheet-limit-input"
                  type="number"
                  min="1"
                  placeholder={lastSession?.has_session ? `Last time: ${lastSession.sent_count}` : 'e.g. 50'}
                  value={sheetLimit}
                  onChange={e => setSheetLimit(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    fontSize: '0.9rem',
                    background: 'rgba(255,255,255,0.04)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: '10px',
                    color: 'var(--text-main)',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
              <div className="form-group">
                <label style={{ marginBottom: '8px', display: 'block' }}>⚙️ Campaign Mode</label>
                <div style={{ display: 'flex', gap: '12px', height: '46px' }}>
                  <button
                    id="sheet-mode-dry"
                    onClick={() => setSheetMode('dry_run')}
                    style={{
                      flex: 1,
                      borderRadius: '10px',
                      border: `1px solid ${sheetMode === 'dry_run' ? 'rgba(137,180,250,0.6)' : 'rgba(255,255,255,0.1)'}`,
                      background: sheetMode === 'dry_run' ? 'rgba(137,180,250,0.15)' : 'rgba(255,255,255,0.03)',
                      color: sheetMode === 'dry_run' ? '#89b4fa' : 'var(--text-muted)',
                      fontWeight: sheetMode === 'dry_run' ? '700' : '400',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      fontSize: '0.85rem',
                    }}
                  >
                    👀 Dry Run
                  </button>
                  <button
                    id="sheet-mode-live"
                    onClick={() => setSheetMode('live')}
                    style={{
                      flex: 1,
                      borderRadius: '10px',
                      border: `1px solid ${sheetMode === 'live' ? 'rgba(166,227,161,0.6)' : 'rgba(255,255,255,0.1)'}`,
                      background: sheetMode === 'live' ? 'rgba(166,227,161,0.15)' : 'rgba(255,255,255,0.03)',
                      color: sheetMode === 'live' ? '#a6e3a1' : 'var(--text-muted)',
                      fontWeight: sheetMode === 'live' ? '700' : '400',
                      cursor: 'pointer',
                      transition: 'all 0.2s',
                      fontSize: '0.85rem',
                    }}
                  >
                    🔥 Live Send
                  </button>
                </div>
              </div>
            </div>

            {/* Sender info pill */}
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              padding: '10px 16px',
              background: 'rgba(166,227,161,0.07)',
              border: '1px solid rgba(166,227,161,0.15)',
              borderRadius: '10px',
              marginBottom: '24px',
              fontSize: '0.85rem',
              color: 'var(--text-sub)',
            }}>
              <span style={{ fontSize: '1.1rem' }}>✉️</span>
              Emails will be sent from{' '}
              <strong style={{ color: '#a6e3a1' }}>contact@nexariza.com</strong>
              {' '}· Already-emailed contacts are automatically skipped.
            </div>

            {/* Launch / Cancel */}
            <div style={{ display: 'flex', gap: '14px' }}>
              <button
                id="sheet-launch-btn"
                style={{
                  flex: 1,
                  background: isSheetLaunching || isCampaignRunning
                    ? 'rgba(137,220,235,0.2)'
                    : 'linear-gradient(135deg, #89dceb, #74c7ec)',
                  color: isSheetLaunching || isCampaignRunning ? '#89dceb' : '#11111b',
                  fontWeight: '700',
                  fontSize: '1rem',
                  padding: '14px',
                  border: 'none',
                  borderRadius: '10px',
                  cursor: isSheetLaunching || isCampaignRunning || !sheetUrl.trim() ? 'not-allowed' : 'pointer',
                  transition: 'all 0.2s',
                }}
                onClick={handleSheetCampaign}
                disabled={isSheetLaunching || isCampaignRunning || health.api !== 'online' || !sheetUrl.trim()}
              >
                {isSheetLaunching ? (
                  <span style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px' }}>
                    <span className="loader" />
                    Fetching Sheet...
                  </span>
                ) : isCampaignRunning ? (
                  '⚡ Campaign Running...'
                ) : (
                  `🚀 Launch ${sheetMode === 'live' ? 'Live' : 'Dry Run'} Campaign`
                )}
              </button>
              {isCampaignRunning && (
                <button
                  id="sheet-cancel-btn"
                  onClick={handleCancelCampaign}
                  style={{
                    padding: '14px 20px',
                    borderRadius: '10px',
                    border: '1px solid rgba(243,139,168,0.4)',
                    background: 'rgba(243,139,168,0.1)',
                    color: '#f38ba8',
                    cursor: 'pointer',
                    fontWeight: '700',
                  }}
                >
                  🛑 Stop
                </button>
              )}
            </div>

            {/* Launch result summary */}
            {sheetLaunchResult && (
              <div style={{
                marginTop: '20px',
                padding: '16px 20px',
                background: 'rgba(166,227,161,0.08)',
                border: '1px solid rgba(166,227,161,0.2)',
                borderRadius: '12px',
                fontSize: '0.88rem',
              }}>
                <div style={{ fontWeight: '700', color: '#a6e3a1', marginBottom: '12px' }}>✅ Campaign Queued Successfully</div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px', textAlign: 'center' }}>
                  <div>
                    <div style={{ fontSize: '1.5rem', fontWeight: '800', color: 'var(--text-main)' }}>{sheetLaunchResult.total_in_sheet}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>In Sheet</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '1.5rem', fontWeight: '800', color: '#a6e3a1' }}>{sheetLaunchResult.queued_for_sending}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>Queued to Send</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '1.5rem', fontWeight: '800', color: '#f9e2af' }}>{sheetLaunchResult.already_emailed}</div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '2px' }}>Already Emailed (skipped)</div>
                  </div>
                </div>
              </div>
            )}
          </section>

          {/* ── Live Progress (shared campaign state) ─────────────────────── */}
          {(isCampaignRunning || (campaignStats && campaignStats.total > 0)) && (
            <section className="glass-panel" style={{ padding: '28px', marginTop: '20px' }}>
              <h3 style={{ margin: '0 0 16px 0', fontSize: '1rem', color: 'var(--primary-light)' }}>⚡ Campaign Progress</h3>

              {isCampaignRunning && campaignStatus && (
                <>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.88rem' }}>
                    <span style={{ color: 'var(--text-sub)' }}>Processing leads...</span>
                    <span style={{ color: 'var(--text-main)', fontWeight: '700' }}>{campaignStatus.processed}/{campaignStatus.total}</span>
                  </div>
                  <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden', marginBottom: '16px' }}>
                    <div style={{
                      width: `${(campaignStatus.processed / (campaignStatus.total || 1)) * 100}%`,
                      height: '100%',
                      background: 'linear-gradient(90deg, #89dceb, #74c7ec)',
                      transition: 'width 0.5s ease-in-out',
                      borderRadius: '4px',
                    }} />
                  </div>
                  {campaignStatus.current_lead && (
                    <div style={{ fontSize: '0.83rem', color: 'var(--text-muted)', marginBottom: '12px' }}>
                      👉 Now: <strong style={{ color: 'var(--text-main)' }}>{campaignStatus.current_lead}</strong>
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '20px', fontSize: '0.85rem' }}>
                    <span style={{ color: '#a6e3a1' }}>✅ Sent: {campaignStatus.sent}</span>
                    <span style={{ color: '#f38ba8' }}>❌ Failed: {campaignStatus.failed}</span>
                    <span style={{ color: 'var(--text-muted)' }}>⏭️ Skipped: {campaignStatus.skipped}</span>
                  </div>
                </>
              )}

              {!isCampaignRunning && campaignStats && campaignStats.total > 0 && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
                  {[
                    ['Total', campaignStats.total, 'var(--primary)'],
                    [campaignStats.mode === 'live' ? 'Sent' : 'Previewed', campaignStats.sent, '#a6e3a1'],
                    ['Failed', campaignStats.failed, '#f38ba8'],
                    ['Skipped', campaignStats.skipped, '#f9e2af'],
                  ].map(([label, val, color]) => (
                    <div key={label} style={{ textAlign: 'center', background: 'rgba(255,255,255,0.03)', borderRadius: '10px', padding: '14px' }}>
                      <div style={{ fontSize: '1.6rem', fontWeight: '800', color }}>{val}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>{label}</div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* Quick Setup Guide */}
          <section className="glass-panel" style={{ padding: '24px', marginTop: '20px', background: 'rgba(255,255,255,0.02)' }}>
            <h3 style={{ fontSize: '0.95rem', margin: '0 0 14px 0', color: 'var(--text-sub)' }}>📋 Quick Setup Guide</h3>
            <ol style={{ margin: 0, paddingLeft: '20px', fontSize: '0.85rem', color: 'var(--text-muted)', lineHeight: 2 }}>
              <li>Open your Google Sheet and click <strong style={{ color: 'var(--text-main)' }}>Share</strong></li>
              <li>Set access to <strong style={{ color: 'var(--text-main)' }}>"Anyone with the link"</strong> → Viewer</li>
              <li>Copy the link and paste it in the URL field above</li>
              <li>Your sheet columns should match <code style={{ background: 'rgba(255,255,255,0.08)', padding: '1px 6px', borderRadius: '4px' }}>clients.csv</code> structure — e.g. <em>Direct Email</em>, <em>Decision Maker</em>, <em>Website</em></li>
              <li>Enter how many contacts to email (or leave blank to email all new ones)</li>
              <li>Start with <strong style={{ color: '#89b4fa' }}>Dry Run</strong> to preview emails — then switch to <strong style={{ color: '#a6e3a1' }}>Live Send</strong></li>
            </ol>
          </section>

        </div>
      )}

      {/* 🎓 INTERNSHIP OFFER & ID CARDS TAB */}
      {activeNavTab === 'internship' && (
        <div style={{ animation: 'fadeIn 0.4s ease' }}>
          <div className="dashboard-grid">
            {/* Left Column: Form/Upload & Interns List */}
            <section className="glass-panel" style={{ padding: '32px' }}>
              <div className="card-header">
                <h2>🎓 Intern Management</h2>
                <p>Generate official Offer Letters and modern Intern ID Cards.</p>
              </div>

              {/* Tab Selection */}
              <div style={{ display: 'flex', gap: '12px', marginBottom: '24px', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '12px' }}>
                <button 
                  className={`btn ${internSubTab === 'single' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => { setInternSubTab('single'); handlePreviewIntern(singleInternForm); }}
                  style={{ padding: '8px 16px', fontSize: '0.85rem' }}
                >
                  👤 Single Intern
                </button>
                <button 
                  className={`btn ${internSubTab === 'bulk' ? 'btn-primary' : 'btn-secondary'}`}
                  onClick={() => { setInternSubTab('bulk'); if (internsList.length > 0) handlePreviewIntern(internsList[selectedInternIdx]); }}
                  style={{ padding: '8px 16px', fontSize: '0.85rem' }}
                >
                  📂 Bulk CSV Upload
                </button>
              </div>

              {/* Company & HR Config (Moved up) */}
              <div style={{ background: 'rgba(0,0,0,0.2)', padding: '20px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)', marginBottom: '24px' }}>
                <h3 style={{ fontSize: '1rem', margin: '0 0 12px 0', color: 'var(--primary-light)' }}>⚙️ Offer Letter Settings</h3>
                <div className="form-row">
                  <div className="form-group">
                    <label>Company Name</label>
                    <input type="text" value={internConfig.company_name} onChange={(e) => setInternConfig({ ...internConfig, company_name: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label>Signatory Name</label>
                    <input type="text" value={internConfig.hr_name} onChange={(e) => setInternConfig({ ...internConfig, hr_name: e.target.value })} />
                  </div>
                </div>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label>Signatory Title</label>
                  <input type="text" value={internConfig.hr_title} onChange={(e) => setInternConfig({ ...internConfig, hr_title: e.target.value })} />
                </div>
              </div>

              {internSubTab === 'single' ? (
                <div>
                  <h3 style={{ fontSize: '1rem', margin: '0 0 16px 0', color: 'var(--primary-light)' }}>Single Intern Details</h3>
                  <div className="form-row">
                    <div className="form-group"><label>Name</label><input type="text" value={singleInternForm.name} onChange={e => setSingleInternForm({...singleInternForm, name: e.target.value})} /></div>
                    <div className="form-group"><label>Email</label><input type="email" value={singleInternForm.email} onChange={e => setSingleInternForm({...singleInternForm, email: e.target.value})} /></div>
                  </div>
                  <div className="form-row">
                    <div className="form-group"><label>Role</label><input type="text" value={singleInternForm.role} onChange={e => setSingleInternForm({...singleInternForm, role: e.target.value})} /></div>
                    <div className="form-group"><label>Department</label><input type="text" value={singleInternForm.department} onChange={e => setSingleInternForm({...singleInternForm, department: e.target.value})} /></div>
                  </div>
                  <div className="form-row">
                    <div className="form-group"><label>Start Date</label><input type="text" value={singleInternForm.start_date} onChange={e => setSingleInternForm({...singleInternForm, start_date: e.target.value})} /></div>
                    <div className="form-group"><label>Duration</label><input type="text" value={singleInternForm.duration} onChange={e => setSingleInternForm({...singleInternForm, duration: e.target.value})} /></div>
                  </div>
                  <div className="form-row">
                    <div className="form-group"><label>Location</label><input type="text" value={singleInternForm.location} onChange={e => setSingleInternForm({...singleInternForm, location: e.target.value})} /></div>
                    <div className="form-group"><label>Intern ID</label><input type="text" value={singleInternForm.intern_id} onChange={e => setSingleInternForm({...singleInternForm, intern_id: e.target.value})} /></div>
                  </div>
                </div>
              ) : (
                <div>
                  {/* Upload CSV */}
                  <div className="form-group" style={{ background: 'rgba(255, 255, 255, 0.03)', padding: '16px', borderRadius: '12px', border: '1px dashed rgba(255, 255, 255, 0.1)' }}>
                <label style={{ display: 'block', marginBottom: '8px', fontSize: '0.9rem', color: 'var(--text-main)' }}>
                  Upload Interns CSV File
                </label>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                  <input
                    type="file"
                    accept=".csv"
                    onChange={(e) => setSelectedInternFile(e.target.files[0])}
                    style={{ flex: 1, padding: '8px', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'var(--text-sub)' }}
                  />
                  <button
                    className="btn btn-primary"
                    onClick={handleUploadInternCSV}
                    disabled={!selectedInternFile || isUploadingInterns || health.api !== 'online'}
                    style={{ padding: '10px 18px', whiteSpace: 'nowrap' }}
                  >
                    {isUploadingInterns ? 'Uploading...' : 'Upload CSV'}
                  </button>
                </div>
                <div style={{ marginTop: '8px', fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                  Accepted columns: <code>name</code>, <code>email</code>, <code>role / domain / track / position</code>, <code>department</code>, <code>start_date</code>, <code>duration</code>
                </div>
              </div>

              {/* (Company & HR Config moved above) */}

              {/* Interns Data Table */}
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <h3 style={{ fontSize: '1rem', margin: 0, color: 'var(--text-main)' }}>
                    Loaded Interns ({internsList.length})
                  </h3>
                  <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                    Click an intern row to preview their ID Card
                  </span>
                </div>

                <div className="intern-table-container">
                  <table className="intern-table">
                    <thead>
                      <tr>
                        <th>#</th>
                        <th>Name</th>
                        <th>Role</th>
                        <th>Department</th>
                        <th>Stipend</th>
                      </tr>
                    </thead>
                    <tbody>
                      {internsList.map((intern, idx) => (
                        <tr
                          key={idx}
                          onClick={() => {
                            setSelectedInternIdx(idx);
                            handlePreviewIntern(intern);
                          }}
                          style={{
                            cursor: 'pointer',
                            background: selectedInternIdx === idx ? 'rgba(139, 92, 246, 0.15)' : 'transparent',
                            borderLeft: selectedInternIdx === idx ? '3px solid #8b5cf6' : 'none'
                          }}
                        >
                          <td>{idx + 1}</td>
                          <td style={{ fontWeight: '600' }}>{intern.name}</td>
                          <td style={{ color: 'var(--text-sub)' }}>{intern.role}</td>
                          <td style={{ color: 'var(--text-sub)' }}>{intern.department}</td>
                          <td style={{ color: '#4ade80' }}>{intern.stipend}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Dispatch Controls */}
              <div style={{ marginTop: '24px', display: 'flex', gap: '12px' }}>
                <button
                  className="btn btn-secondary"
                  style={{ flex: 1 }}
                  onClick={() => handleRunInternshipBatch('dry_run')}
                  disabled={isInternBatchRunning || internsList.length === 0}
                >
                  👀 Dry Run Batch ({internsList.length})
                </button>
                <button
                  className="btn btn-accent"
                  style={{ flex: 1 }}
                  onClick={() => handleRunInternshipBatch('live')}
                  disabled={isInternBatchRunning || internsList.length === 0 || !smtpOk}
                >
                  🚀 Send All Offers ({internsList.length})
                </button>
              </div>
              </div>)}

              {/* Campaign Progress Monitor */}
              {isInternBatchRunning && internBatchStatus && (
                <div style={{ marginTop: '24px', background: 'rgba(255,255,255,0.03)', padding: '16px', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.08)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.88rem' }}>
                    <span style={{ fontWeight: 'bold', color: 'var(--primary-light)' }}>
                      ⚡ Dispatching: {internBatchStatus.processed} / {internBatchStatus.total}
                    </span>
                    <span style={{ color: 'var(--text-sub)' }}>{internBatchStatus.status.toUpperCase()}</span>
                  </div>
                  <div style={{ width: '100%', height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden', marginBottom: '12px' }}>
                    <div style={{ width: `${(internBatchStatus.processed / (internBatchStatus.total || 1)) * 100}%`, height: '100%', background: 'linear-gradient(90deg, #6366f1, #a855f7)' }}></div>
                  </div>
                  {internBatchStatus.current_intern && (
                    <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: '12px' }}>
                      Processing: {internBatchStatus.current_intern}
                    </div>
                  )}
                  <button
                    className="btn btn-secondary"
                    onClick={handleCancelInternshipBatch}
                    style={{ width: '100%', background: 'rgba(243,139,168,0.15)', color: '#f38ba8' }}
                  >
                    🛑 Cancel Batch Dispatch
                  </button>
                </div>
              )}
            </section>

            {/* Right Column: Live Visual ID Card & Offer Preview */}
            <section className="glass-panel" style={{ padding: '32px' }}>
              <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div>
                  <h2>✨ Live Offer Email Preview</h2>
                  <p>Preview what {internSubTab === 'single' ? singleInternForm.name : (internsList[selectedInternIdx]?.name || 'the intern')} will receive in their inbox.</p>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    className={`btn ${previewTabMode === 'card' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setPreviewTabMode('card')}
                    style={{ padding: '6px 12px', fontSize: '0.8rem' }}
                  >
                    🎴 ID Card
                  </button>
                  <button
                    className={`btn ${previewTabMode === 'full_email' ? 'btn-primary' : 'btn-secondary'}`}
                    onClick={() => setPreviewTabMode('full_email')}
                    style={{ padding: '6px 12px', fontSize: '0.8rem' }}
                  >
                    📄 Full Offer
                  </button>
                </div>
              </div>

              {/* Single Intern Controls */}
              <div style={{ display: 'flex', gap: '12px', marginBottom: '20px' }}>
                <button
                  className="btn btn-primary"
                  style={{ flex: 1, padding: '10px 16px', fontSize: '0.88rem' }}
                  onClick={() => handlePreviewIntern(internSubTab === 'single' ? singleInternForm : internsList[selectedInternIdx])}
                  disabled={isPreviewLoading}
                >
                  {isPreviewLoading ? <span className="loader"></span> : '🔄 Refresh Preview'}
                </button>
                <button
                  className="btn btn-accent"
                  style={{ flex: 1, padding: '10px 16px', fontSize: '0.88rem' }}
                  onClick={() => handleSendSingleIntern('live')}
                  disabled={isSendingSingleIntern || !smtpOk}
                >
                  {isSendingSingleIntern ? <span className="loader"></span> : '📧 Send Test Email to Intern'}
                </button>
              </div>

              {/* Live Render */}
              {previewTabMode === 'card' ? (
                <div style={{ padding: '20px', background: 'rgba(0,0,0,0.3)', borderRadius: '16px', border: '1px solid rgba(255,255,255,0.05)' }}>
                  <div className="intern-card-wrapper">
                    <div className="intern-card-header">
                      <div className="intern-card-title">⚡ {internConfig.company_name}</div>
                      <div className="intern-badge-pill">VERIFIED INTERN</div>
                    </div>
                    <div className="intern-card-body">
                      <div className="intern-avatar">
                        {(internSubTab === 'single' ? singleInternForm.name || 'IN' : internsList[selectedInternIdx]?.name || 'IN').split(' ').map(n => n[0]).join('').toUpperCase()}
                      </div>
                      <div className="intern-info">
                        <div className="intern-name">{internSubTab === 'single' ? singleInternForm.name : internsList[selectedInternIdx]?.name || 'Intern Name'}</div>
                        <div className="intern-role">{internSubTab === 'single' ? singleInternForm.role : internsList[selectedInternIdx]?.role || 'Software Engineering Intern'}</div>
                        <div className="intern-meta-grid">
                          <div>
                            <span className="intern-meta-label">Department</span>
                            <strong style={{ color: '#e2e8f0' }}>{internSubTab === 'single' ? singleInternForm.department : internsList[selectedInternIdx]?.department || 'Engineering'}</strong>
                          </div>
                          <div>
                            <span className="intern-meta-label">Intern ID</span>
                            <strong style={{ color: '#38bdf8' }}>{internSubTab === 'single' ? singleInternForm.intern_id : internsList[selectedInternIdx]?.intern_id || 'NEX-001'}</strong>
                          </div>
                        </div>
                      </div>
                    </div>
                    <div className="intern-card-footer">
                      <span>STATUS: <strong style={{ color: '#4ade80' }}>ACTIVE 2026</strong></span>
                      <span style={{ letterSpacing: '3px', fontFamily: 'monospace', color: '#94a3b8' }}>||| | |||| | ||| |||| |</span>
                      <span>NEXARIZA AI ID</span>
                    </div>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', height: '520px' }}>
                  {internPreviewData && (
                    <div style={{ 
                      padding: '8px 12px', 
                      marginBottom: '10px', 
                      borderRadius: '8px', 
                      fontSize: '0.82rem', 
                      fontWeight: '600',
                      background: internPreviewData.application_type === 'job_response' ? 'rgba(234, 179, 8, 0.15)' : 'rgba(99, 102, 241, 0.15)',
                      color: internPreviewData.application_type === 'job_response' ? '#facc15' : '#818cf8',
                      border: `1px solid ${internPreviewData.application_type === 'job_response' ? 'rgba(234, 179, 8, 0.3)' : 'rgba(99, 102, 241, 0.3)'}`
                    }}>
                      {internPreviewData.application_type === 'job_response' 
                        ? '💼 Job Application Detected — Sending Internship Opportunities Response' 
                        : '🎓 Internship Application Detected — Sending Formal Offer Letter'}
                    </div>
                  )}
                  <div style={{ flex: 1, overflowY: 'auto', background: '#ffffff', borderRadius: '12px', padding: '16px' }}>
                    {internPreviewData ? (
                      <iframe
                        title="Offer Letter Preview"
                        srcDoc={internPreviewData.email_html}
                        style={{ width: '100%', height: '100%', border: 'none' }}
                      />
                    ) : (
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#64748b' }}>
                        Click 'Refresh Preview' to render full email HTML document
                      </div>
                    )}
                  </div>
                </div>
              )}
            </section>
          </div>
        </div>
      )}

      {/* 🔍 EMAIL VERIFIER TAB */}
      {activeNavTab === 'verifier' && (
        <div style={{ animation: 'fadeIn 0.4s ease' }}>
          <section className="glass-panel" style={{ padding: '32px' }}>
            <div className="card-header">
              <h2>Email Validator & Deliverability Checker</h2>
              <p>Verify if email addresses actually exist and are safe to contact to prevent bounces on Zoho Mail.</p>
            </div>

          {/* Tab Selection */}
          <div style={{ display: 'flex', gap: '12px', marginBottom: '24px', borderBottom: '1px solid rgba(255,255,255,0.08)', paddingBottom: '12px' }}>
            <button 
              className={`btn ${validatorTab === 'single' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setValidatorTab('single')}
              style={{ padding: '8px 16px', fontSize: '0.85rem' }}
            >
              🔍 Single Email Verifier
            </button>
            <button 
              className={`btn ${validatorTab === 'bulk' ? 'btn-primary' : 'btn-secondary'}`}
              onClick={() => setValidatorTab('bulk')}
              style={{ padding: '8px 16px', fontSize: '0.85rem' }}
            >
              📂 Bulk CSV Verifier
            </button>
          </div>

          {validatorTab === 'single' && (
            <div>
              <p style={{ marginTop: 0, marginBottom: '20px', color: 'var(--text-sub)' }}>
                Runs syntax standards check, DNS mail records verification, disposable domain blocking, role-based generic checking, and direct SMTP handshake connection.
              </p>
              <div style={{ display: 'flex', gap: '12px', alignItems: 'center', marginBottom: '24px' }}>
                <input 
                  type="email" 
                  placeholder="e.g. hello@nexariza.com"
                  value={verifyEmailInput}
                  onChange={(e) => setVerifyEmailInput(e.target.value)}
                  style={{ flex: 1, padding: '12px 16px', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: 'var(--text-main)', fontSize: '0.95rem' }}
                  onKeyDown={(e) => e.key === 'Enter' && handleVerifySingleEmail()}
                />
                <button 
                  className="btn btn-primary"
                  onClick={handleVerifySingleEmail}
                  disabled={isVerifyingSingle || health.api !== 'online'}
                  style={{ padding: '12px 24px', whiteSpace: 'nowrap' }}
                >
                  {isVerifyingSingle ? <span className="loader"></span> : 'Verify Email'}
                </button>
              </div>

              {singleVerifyResult && (
                <div style={{ 
                  animation: 'fadeIn 0.3s ease',
                  background: 'rgba(22, 24, 30, 0.4)', 
                  border: `1px solid ${singleVerifyResult.is_valid ? 'rgba(166,227,161,0.2)' : 'rgba(243,139,168,0.2)'}`,
                  borderRadius: '12px', 
                  padding: '24px', 
                  marginTop: '16px' 
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px', marginBottom: '20px', borderBottom: '1px solid rgba(255,255,255,0.05)', paddingBottom: '16px' }}>
                    <div>
                      <h3 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--text-main)' }}>Result for {singleVerifyResult.email}</h3>
                      <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--text-muted)' }}>{singleVerifyResult.reason}</p>
                    </div>
                    <div>
                      <span className={`badge ${
                        singleVerifyResult.status === 'deliverable' ? 'badge-success' :
                        singleVerifyResult.status === 'catch_all' ? 'badge-warning' :
                        singleVerifyResult.status === 'unknown' ? 'badge-info' : 'badge-error'
                      }`} style={{ padding: '6px 12px', fontSize: '0.8rem', fontWeight: 'bold' }}>
                        {singleVerifyResult.status.toUpperCase()}
                      </span>
                    </div>
                  </div>

                  {/* Checklist grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px' }}>
                    <div className="checklist-item" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontSize: '1.25rem' }}>{singleVerifyResult.syntax_valid ? '✅' : '❌'}</span>
                      <div>
                        <div style={{ fontWeight: '600', fontSize: '0.88rem' }}>Syntax Check</div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-sub)' }}>{singleVerifyResult.syntax_valid ? 'Valid format' : 'Syntax error'}</div>
                      </div>
                    </div>

                    <div className="checklist-item" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontSize: '1.25rem' }}>{singleVerifyResult.dns_valid ? '✅' : '❌'}</span>
                      <div>
                        <div style={{ fontWeight: '600', fontSize: '0.88rem' }}>DNS & MX Records</div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-sub)' }}>{singleVerifyResult.dns_valid ? `${singleVerifyResult.mx_records.length} servers found` : 'No MX records'}</div>
                      </div>
                    </div>

                    <div className="checklist-item" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontSize: '1.25rem' }}>{!singleVerifyResult.is_disposable ? '✅' : '❌'}</span>
                      <div>
                        <div style={{ fontWeight: '600', fontSize: '0.88rem' }}>Disposable Check</div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-sub)' }}>{singleVerifyResult.is_disposable ? 'Disposable address' : 'Safe domain'}</div>
                      </div>
                    </div>

                    <div className="checklist-item" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontSize: '1.25rem' }}>{singleVerifyResult.smtp_checked ? (singleVerifyResult.mailbox_exists ? '✅' : '❌') : '⚠️'}</span>
                      <div>
                        <div style={{ fontWeight: '600', fontSize: '0.88rem' }}>
                          SMTP Handshake
                          {singleVerifyResult.smtp_checked && singleVerifyResult.smtp_port_used && (
                            <span style={{
                              marginLeft: '6px',
                              fontSize: '0.72rem',
                              padding: '2px 7px',
                              borderRadius: '99px',
                              background: singleVerifyResult.smtp_port_used === 25
                                ? 'rgba(166,227,161,0.15)'
                                : 'rgba(137,180,250,0.15)',
                              border: singleVerifyResult.smtp_port_used === 25
                                ? '1px solid rgba(166,227,161,0.35)'
                                : '1px solid rgba(137,180,250,0.35)',
                              color: singleVerifyResult.smtp_port_used === 25 ? '#a6e3a1' : '#89b4fa',
                              fontWeight: 600,
                            }}>
                              {singleVerifyResult.smtp_port_used === 25 ? 'Port 25' : 'Port 587 STARTTLS'}
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-sub)' }}>
                          {!singleVerifyResult.smtp_checked
                            ? 'Skipped — both port 25 & 587 unreachable'
                            : singleVerifyResult.mailbox_exists
                              ? 'Mailbox confirmed'
                              : 'Mailbox rejected by server'}
                        </div>
                      </div>
                    </div>


                    <div className="checklist-item" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontSize: '1.25rem' }}>{!singleVerifyResult.is_catch_all ? '✅' : '🔔'}</span>
                      <div>
                        <div style={{ fontWeight: '600', fontSize: '0.88rem' }}>Catch-all Check</div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-sub)' }}>{singleVerifyResult.is_catch_all ? 'Accepts all mail' : 'Safe (non-catch-all)'}</div>
                      </div>
                    </div>

                    <div className="checklist-item" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <span style={{ fontSize: '1.25rem' }}>{singleVerifyResult.is_role_based ? '🔔' : '✅'}</span>
                      <div>
                        <div style={{ fontWeight: '600', fontSize: '0.88rem' }}>Role-based Check</div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-sub)' }}>{singleVerifyResult.is_role_based ? 'Generic/Role contact' : 'Personal contact'}</div>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {validatorTab === 'bulk' && (
            <div>
              <p style={{ marginTop: 0, marginBottom: '20px', color: 'var(--text-sub)' }}>
                Upload a clients CSV to validate all list emails in bulk using syntax, DNS, and deep validation.
              </p>
              <div className="form-group" style={{ marginBottom: '24px', background: 'rgba(255, 255, 255, 0.03)', padding: '16px', borderRadius: '12px', border: '1px dashed rgba(255, 255, 255, 0.1)' }}>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                  <input 
                    type="file" 
                    accept=".csv"
                    onChange={(e) => setValidatorFile(e.target.files[0])}
                    style={{ flex: 1, padding: '8px', background: 'rgba(0,0,0,0.2)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '6px', color: 'var(--text-sub)' }}
                  />
                  <button 
                    className="btn btn-primary"
                    onClick={handleValidateCSV}
                    disabled={!validatorFile || isValidating || health.api !== 'online'}
                    style={{ padding: '10px 20px', whiteSpace: 'nowrap' }}
                  >
                    {isValidating ? 'Validating...' : 'Verify Emails'}
                  </button>
                </div>
              </div>

              {validationResults && (
                <div style={{ marginTop: '24px' }}>
                  <div className="stats-grid">
                    <div className="stat-box">
                      <div className="stat-value stat-info">{validationResults.total_checked}</div>
                      <div className="stat-label">Checked</div>
                    </div>
                    <div className="stat-box">
                      <div className="stat-value stat-success">{validationResults.valid_count}</div>
                      <div className="stat-label">Valid</div>
                    </div>
                    <div className="stat-box">
                      <div className="stat-value stat-error">{validationResults.invalid_count}</div>
                      <div className="stat-label">Invalid</div>
                    </div>
                  </div>

                  <div style={{ marginTop: '24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <h3 style={{ fontSize: '1.2rem', margin: 0 }}>Detailed Results</h3>
                    <button 
                      className="btn btn-secondary" 
                      onClick={handleDownloadCleanedCSV}
                      disabled={validationResults.valid_count === 0}
                    >
                      📥 Download Cleaned CSV
                    </button>
                  </div>

                  <div style={{ marginTop: '16px', maxHeight: '300px', overflowY: 'auto', background: 'rgba(0,0,0,0.2)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.05)' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.9rem' }}>
                      <thead style={{ position: 'sticky', top: 0, background: '#181825' }}>
                        <tr>
                          <th style={{ padding: '12px 16px', textAlign: 'left', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-sub)' }}>Email</th>
                          <th style={{ padding: '12px 16px', textAlign: 'left', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-sub)' }}>Status</th>
                          <th style={{ padding: '12px 16px', textAlign: 'left', borderBottom: '1px solid rgba(255,255,255,0.1)', color: 'var(--text-sub)' }}>Reason</th>
                        </tr>
                      </thead>
                      <tbody>
                        {validationResults.results.slice(0, 100).map((r, i) => (
                          <tr key={i} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                            <td style={{ padding: '12px 16px', color: 'var(--text-main)' }}>{r.email}</td>
                            <td style={{ padding: '12px 16px' }}>
                              <span className={`badge ${r.is_valid ? 'badge-success' : 'badge-error'}`} style={{ padding: '4px 8px', fontSize: '0.75rem' }}>
                                {r.is_valid ? 'VALID' : 'INVALID'}
                              </span>
                            </td>
                            <td style={{ padding: '12px 16px', color: 'var(--text-sub)', fontSize: '0.85rem' }}>{r.reason}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {validationResults.results.length > 100 && (
                      <div style={{ padding: '12px', textAlign: 'center', color: 'var(--text-sub)', fontSize: '0.85rem' }}>
                        Showing first 100 results. Download to see all.
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </section>
        </div>
      )}

      {/* 🤖 AUTONOMOUS AGENT RESPONDER TAB */}
      {activeNavTab === 'responder' && (
        <div style={{ animation: 'fadeIn 0.4s ease' }}>
      <section className="glass-panel" style={{ padding: '32px' }}>
        <div className="card-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '16px' }}>
          <div>
            <h2>🤖 Autonomous Agent Mail Responder</h2>
            <p>Monitors inbox for replies from your outreach list and responds automatically using AI.</p>
            {!smtpOk && (
              <div style={{
                marginTop: '8px', padding: '8px 14px', borderRadius: '8px',
                background: 'rgba(249,226,175,0.1)', border: '1px solid rgba(249,226,175,0.3)',
                fontSize: '0.82rem', color: '#f9e2af', display: 'inline-flex', gap: '6px'
              }}>
                ⚠️ Enable IMAP in Zoho Mail settings to activate inbox scanning
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
            <span className={`badge ${responderStatus.active ? 'badge-success pulse-badge' : 'badge-error'}`}>
              Responder: {responderStatus.active ? 'ACTIVE' : 'INACTIVE'}
            </span>
            <button
              className={`btn ${responderStatus.active ? 'btn-secondary' : 'btn-primary'}`}
              onClick={handleToggleResponder}
              disabled={isTogglingResponder || health.api !== 'online'}
              style={{ padding: '10px 20px', fontSize: '0.9rem' }}
            >
              {isTogglingResponder ? 'Toggling...' : responderStatus.active ? 'Stop Agent' : 'Start Agent'}
            </button>
            <button
              className="btn btn-accent"
              onClick={handleCheckResponder}
              disabled={isCheckingResponder || health.api !== 'online'}
              style={{ padding: '10px 20px', fontSize: '0.9rem' }}
            >
              {isCheckingResponder ? 'Scanning...' : '📥 Scan Inbox Now'}
            </button>
          </div>
        </div>

        <div style={{ marginTop: '24px' }}>
          <h3 style={{ fontSize: '1.25rem', marginBottom: '16px' }}>Recent Auto-Replies Sent ({responderHistory.length})</h3>

          {responderHistory.length === 0 ? (
            <div style={{ padding: '32px', textAlign: 'center', color: 'var(--text-muted)', background: 'rgba(0,0,0,0.15)', borderRadius: '12px', marginTop: '16px', border: '1px dashed var(--border-subtle)' }}>
              No auto-replies have been sent yet. When a lead replies, the agent's automated response will show up here.
            </div>
          ) : (
            <div className="history-timeline" style={{ marginTop: '16px', display: 'flex', flexDirection: 'column', gap: '20px' }}>
              {responderHistory.slice().reverse().map((item, idx) => (
                <div key={idx} className="history-card" style={{ background: 'rgba(22, 24, 30, 0.4)', border: '1px solid var(--border-subtle)', borderRadius: '12px', padding: '20px', transition: 'all 0.3s ease' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '16px', fontSize: '0.85rem', flexWrap: 'wrap', gap: '8px' }}>
                    <div>
                      <strong style={{ color: 'var(--primary-light)', fontSize: '0.95rem' }}>Lead: {item.recipient}</strong>
                    </div>
                    <div style={{ color: 'var(--text-muted)' }}>
                      {new Date(item.sent_at).toLocaleString()}
                    </div>
                  </div>

                  <div style={{ marginBottom: '14px', padding: '12px 16px', background: 'rgba(243, 139, 168, 0.04)', borderRadius: '8px', borderLeft: '4px solid var(--accent)' }}>
                    <div style={{ fontWeight: '700', fontSize: '0.85rem', color: 'var(--accent)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                      Incoming Reply: "{item.incoming_subject}"
                    </div>
                    <div style={{ fontSize: '0.95rem', color: 'var(--text-main)', fontStyle: 'italic', lineHeight: '1.5' }}>
                      "{item.incoming_snippet}"
                    </div>
                  </div>

                  <div style={{ padding: '12px 16px', background: 'rgba(166, 227, 161, 0.04)', borderRadius: '8px', borderLeft: '4px solid var(--secondary)' }}>
                    <div style={{ fontWeight: '700', fontSize: '0.85rem', color: 'var(--secondary)', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                      Agent AI Response: "{item.reply_subject}"
                    </div>
                    <div style={{ fontSize: '0.95rem', color: 'var(--text-main)', whiteSpace: 'pre-wrap', lineHeight: '1.6' }}>
                      {item.reply_body}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </section>
        </div>
      )}

      {/* 💼 SALES CAMPAIGN TAB */}
      {activeNavTab === 'sales' && (
        <div style={{ animation: 'fadeIn 0.4s ease', display: 'flex', flexDirection: 'column', gap: '24px', padding: '0 4px' }}>

          {/* Header card */}
          <section className="glass-panel" style={{ padding: '32px', background: 'linear-gradient(135deg, rgba(250,179,135,0.08), rgba(243,139,168,0.06))' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '20px' }}>
              <div>
                <h2 style={{ margin: 0, fontSize: '1.5rem', background: 'linear-gradient(90deg,#fab387,#f38ba8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
                  💼 Sales Campaign
                </h2>
                <p style={{ margin: '8px 0 0', color: 'var(--text-sub)', fontSize: '0.95rem' }}>
                  Send fresh outreach from <strong style={{color:'#fab387'}}>sales@nexariza.com</strong> to contacts in sent_history.csv.
                  Emails are AI-generated, non-spammy, and moved to sale_sent_history.csv after sending.
                </p>
              </div>
              <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
                <span style={{
                  background: salesRunning ? 'rgba(166,227,161,0.15)' : salesStatus?.status === 'completed' ? 'rgba(137,180,250,0.15)' : 'rgba(250,179,135,0.1)',
                  border: `1px solid ${salesRunning ? 'rgba(166,227,161,0.4)' : salesStatus?.status === 'completed' ? 'rgba(137,180,250,0.4)' : 'rgba(250,179,135,0.3)'}`,
                  borderRadius: '99px', padding: '6px 16px', fontSize: '0.82rem', fontWeight: 700,
                  color: salesRunning ? '#a6e3a1' : salesStatus?.status === 'completed' ? '#89b4fa' : '#fab387',
                  textTransform: 'uppercase', letterSpacing: '0.5px',
                }}>
                  {salesRunning ? '⚡ Running' : salesStatus?.status === 'completed' ? '✓ Completed' : salesStatus?.status === 'cancelled' ? '⊘ Cancelled' : salesStatus?.status === 'failed' ? '✗ Failed' : '● Idle'}
                </span>
              </div>
            </div>

            {/* Stats row */}
            <div style={{ display: 'flex', gap: '16px', marginTop: '28px', flexWrap: 'wrap' }}>
              {[
                { label: 'Available', value: salesStatus?.prospects_available ?? '—', color: '#cba6f7' },
                { label: 'Sent',      value: salesStatus?.sent    ?? 0,  color: '#a6e3a1' },
                { label: 'Failed',    value: salesStatus?.failed  ?? 0,  color: '#f38ba8' },
                { label: 'Skipped',   value: salesStatus?.skipped ?? 0,  color: '#f9e2af' },
                { label: 'History',   value: salesHistTotal,              color: '#89b4fa' },
              ].map(s => (
                <div key={s.label} style={{
                  flex: '1 1 100px', minWidth: '90px',
                  background: 'rgba(22,24,30,0.5)', borderRadius: '12px',
                  border: '1px solid var(--border-subtle)', padding: '16px 20px', textAlign: 'center',
                }}>
                  <div style={{ fontSize: '1.7rem', fontWeight: 800, color: s.color, lineHeight: 1 }}>{s.value}</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '6px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>{s.label}</div>
                </div>
              ))}
            </div>
          </section>

          {/* Launch controls */}
          <section className="glass-panel" style={{ padding: '28px 32px' }}>
            <h3 style={{ margin: '0 0 20px', fontSize: '1.1rem', color: 'var(--text-main)' }}>Launch Settings</h3>

            <div style={{ display: 'flex', alignItems: 'center', gap: '24px', flexWrap: 'wrap', marginBottom: '24px' }}>
              <div style={{ flex: 1, minWidth: '260px' }}>
                <label style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '10px', fontSize: '0.9rem', color: 'var(--text-sub)' }}>
                  <span>Emails to send</span>
                  <span style={{ color: '#fab387', fontWeight: 700, fontSize: '1.1rem' }}>{salesCount}</span>
                </label>
                <input
                  type="range" min={1} max={Math.min(200, salesStatus?.prospects_available || 200)}
                  value={salesCount}
                  onChange={e => setSalesCount(Number(e.target.value))}
                  disabled={salesRunning}
                  style={{ width: '100%', accentColor: '#fab387', cursor: salesRunning ? 'not-allowed' : 'pointer' }}
                />
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '4px' }}>
                  <span>1</span>
                  <span style={{ color: 'var(--text-sub)', fontSize: '0.8rem' }}>
                    {salesStatus?.prospects_available ?? '…'} prospects available in sent_history.csv
                  </span>
                  <span>200</span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '12px', flexShrink: 0 }}>
                <button
                  id="sales-launch-btn"
                  onClick={handleStartSales}
                  disabled={salesRunning || (salesStatus?.prospects_available === 0)}
                  style={{
                    padding: '12px 28px', borderRadius: '10px', border: 'none', cursor: salesRunning ? 'not-allowed' : 'pointer',
                    background: salesRunning ? 'rgba(250,179,135,0.2)' : 'linear-gradient(135deg,#fab387,#f38ba8)',
                    color: salesRunning ? '#fab387' : '#11111b', fontWeight: 700, fontSize: '0.95rem',
                    boxShadow: salesRunning ? 'none' : '0 6px 20px rgba(250,179,135,0.35)',
                    transition: 'all 0.3s ease', opacity: salesRunning ? 0.7 : 1,
                  }}
                >
                  {salesRunning ? '⚡ Running…' : '🚀 Launch Sales Campaign'}
                </button>
                {salesRunning && (
                  <button
                    id="sales-cancel-btn"
                    onClick={handleCancelSales}
                    style={{
                      padding: '12px 20px', borderRadius: '10px', border: '1px solid rgba(243,139,168,0.4)',
                      background: 'rgba(243,139,168,0.1)', color: '#f38ba8', fontWeight: 600,
                      cursor: 'pointer', fontSize: '0.9rem',
                    }}
                  >
                    ✕ Cancel
                  </button>
                )}
              </div>
            </div>

            {/* Info pills */}
            <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
              {[
                '🤖 AI-generated fresh email per person',
                '🛡️ Spam score gate before sending',
                '⏱ 45–120s humanized delays',
                '📂 Auto-moved to sale_sent_history.csv',
              ].map(t => (
                <span key={t} style={{
                  background: 'rgba(250,179,135,0.08)', border: '1px solid rgba(250,179,135,0.2)',
                  borderRadius: '99px', padding: '5px 14px', fontSize: '0.8rem', color: 'var(--text-sub)',
                }}>{t}</span>
              ))}
            </div>
          </section>

          {/* Live Log */}
          {(salesRunning || (salesStatus?.log && salesStatus.log.length > 0)) && (
            <section className="glass-panel" style={{ padding: '24px 28px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ margin: 0, fontSize: '1.05rem', color: 'var(--text-main)' }}>Live Log</h3>
                {salesRunning && salesStatus?.current_lead && (
                  <span style={{ fontSize: '0.82rem', color: '#fab387', animation: 'pulse 1.5s infinite' }}>
                    ⚡ {salesStatus.current_lead}
                  </span>
                )}
              </div>
              <div style={{
                background: 'rgba(10,10,15,0.6)', borderRadius: '10px', border: '1px solid var(--border-subtle)',
                padding: '16px', fontFamily: 'monospace', fontSize: '0.82rem',
                color: 'var(--text-sub)', maxHeight: '320px', overflowY: 'auto',
                lineHeight: '1.7',
              }}>
                {(salesStatus?.log || []).slice().reverse().map((line, i) => (
                  <div key={i} style={{
                    color: line.includes('✓') ? '#a6e3a1' : line.includes('✗') ? '#f38ba8' : line.includes('⏱') ? '#f9e2af' : line.includes('→') ? '#89b4fa' : 'var(--text-sub)',
                  }}>{line}</div>
                ))}
                {salesStatus?.log?.length === 0 && <div style={{ color: 'var(--text-muted)' }}>No log entries yet.</div>}
              </div>

              {/* Progress bar */}
              {salesStatus && salesStatus.total > 0 && (
                <div style={{ marginTop: '16px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
                    <span>{salesStatus.sent + salesStatus.failed + salesStatus.skipped} / {salesStatus.total} processed</span>
                    <span style={{ color: '#a6e3a1' }}>{salesStatus.sent} sent</span>
                  </div>
                  <div style={{ background: 'rgba(22,24,30,0.8)', borderRadius: '99px', height: '6px', overflow: 'hidden' }}>
                    <div style={{
                      height: '100%', borderRadius: '99px',
                      background: 'linear-gradient(90deg,#fab387,#f38ba8)',
                      width: `${Math.round(((salesStatus.sent + salesStatus.failed + salesStatus.skipped) / salesStatus.total) * 100)}%`,
                      transition: 'width 1s ease',
                    }} />
                  </div>
                </div>
              )}
            </section>
          )}

          {/* Sent History */}
          <section className="glass-panel" style={{ padding: '24px 28px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
              <h3 style={{ margin: 0, fontSize: '1.05rem', color: 'var(--text-main)' }}>
                Sale Sent History
                <span style={{ marginLeft: '10px', fontSize: '0.82rem', color: 'var(--text-muted)', fontWeight: 400 }}>
                  ({salesHistTotal} records in sale_sent_history.csv)
                </span>
              </h3>
              <button
                id="sales-refresh-hist-btn"
                onClick={fetchSalesHistory}
                disabled={isFetchingSalesHistory}
                style={{
                  padding: '8px 18px', borderRadius: '8px', border: '1px solid var(--border-subtle)',
                  background: 'rgba(137,180,250,0.08)', color: '#89b4fa',
                  cursor: 'pointer', fontSize: '0.85rem', fontWeight: 600,
                }}
              >
                {isFetchingSalesHistory ? '⟳ Loading…' : '⟳ Refresh'}
              </button>
            </div>

            {salesHistory.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '40px 20px', color: 'var(--text-muted)', fontSize: '0.95rem' }}>
                No sent records yet. Launch the campaign to start filling this table.
              </div>
            ) : (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                      {['Email', 'Name', 'Sales Subject', 'Sent At'].map(h => (
                        <th key={h} style={{ padding: '10px 14px', textAlign: 'left', color: 'var(--text-muted)', fontWeight: 600, fontSize: '0.78rem', textTransform: 'uppercase', letterSpacing: '0.5px', whiteSpace: 'nowrap' }}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {salesHistory.slice().reverse().map((row, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.03)', transition: 'background 0.2s' }}
                        onMouseEnter={e => e.currentTarget.style.background='rgba(250,179,135,0.04)'}
                        onMouseLeave={e => e.currentTarget.style.background='transparent'}
                      >
                        <td style={{ padding: '10px 14px', color: '#fab387', fontFamily: 'monospace', fontSize: '0.82rem' }}>{row['Email']}</td>
                        <td style={{ padding: '10px 14px', color: 'var(--text-main)' }}>{row['Name'] || '—'}</td>
                        <td style={{ padding: '10px 14px', color: 'var(--text-sub)', maxWidth: '260px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={row['Sales Subject']}>{row['Sales Subject']}</td>
                        <td style={{ padding: '10px 14px', color: 'var(--text-muted)', whiteSpace: 'nowrap', fontSize: '0.78rem' }}>
                          {row['Sales Sent At'] ? new Date(row['Sales Sent At']).toLocaleString() : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

        </div>
      )}
    </div>
  );
}

export default App;
