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

  // Background Campaign execution state
  const [campaignStatus, setCampaignStatus] = useState(null);
  const [isCampaignRunning, setIsCampaignRunning] = useState(false);

  useEffect(() => {
    checkHealth();
    checkCampaignStatus();
    fetchResponderStatus();
    fetchResponderHistory();

    const interval = setInterval(() => {
      fetchResponderStatus();
      fetchResponderHistory();
    }, 15000);
    return () => clearInterval(interval);
  }, []);

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
        addToast(
          `Successfully uploaded ${selectedFile.name} (${data.total_leads} valid leads found).`,
          'success',
          'Upload Complete'
        );
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
        <h1>Nexariza AI Outreach</h1>
        <p>Automate your cold email campaigns with intelligent scraping and Groq-powered personalization.</p>

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

      <div className="dashboard-grid">
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

        {/* Email Validator Section */}
        <section className="glass-panel" style={{ padding: '32px', marginTop: '32px' }}>
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
                        <div style={{ fontWeight: '600', fontSize: '0.88rem' }}>SMTP Handshake</div>
                        <div style={{ fontSize: '0.78rem', color: 'var(--text-sub)' }}>
                          {!singleVerifyResult.smtp_checked ? 'Skipped (Port 25 blocked)' : (singleVerifyResult.mailbox_exists ? 'Mailbox exists' : 'Mailbox rejected')}
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

      {/* Auto-Responder Section */}
      <section className="glass-panel" style={{ padding: '32px', marginTop: '32px' }}>
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
  );
}

export default App;
