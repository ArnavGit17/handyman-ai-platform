import { useEffect, useState } from 'react';
import { Activity, AlertTriangle, ArrowRight, BadgeCheck, BarChart3, Bell, BriefcaseBusiness, Check, ChevronRight, Clock3, CreditCard, Hammer, IndianRupee, LayoutDashboard, Lock, LogOut, MapPin, Phone, QrCode, ReceiptText, ShieldCheck, Sparkles, Star, Target, Users, UserRound, Wrench, Zap } from 'lucide-react';
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { QRCodeSVG } from 'qrcode.react';
import EvaluationDashboard from './EvaluationDashboard';
const API = 'http://localhost:8000';
const nav = [{id:'customer', label:'Customer', icon: Wrench}, {id:'worker', label:'Worker desk', icon: BriefcaseBusiness}, {id:'cooperative', label:'Cooperative', icon: LayoutDashboard}];

const formatCurrency = (value) => new Intl.NumberFormat('en-IN', { style:'currency', currency:'INR', maximumFractionDigits:0 }).format(Number(value || 0));
const formatDate = (value) => value ? new Date(value).toLocaleDateString('en-IN', { day:'2-digit', month:'short', year:'numeric' }) : 'Pending';

function App() {
  const [auth, setAuth] = useState(() => {
    try {
      const token = localStorage.getItem('handyman-token');
      const rawUser = localStorage.getItem('handyman-user');
      return { token, user: rawUser ? JSON.parse(rawUser) : null };
    } catch {
      return { token: null, user: null };
    }
  });
  const [view, setView] = useState('customer');
  const [match, setMatch] = useState(null);
  const [job, setJob] = useState(null);
  const [loading, setLoading] = useState(false);
  const [dashboard, setDashboard] = useState(null);
  const [workerProfile, setWorkerProfile] = useState(null);
  const [customerRequests, setCustomerRequests] = useState([]);
  const [workerRequests, setWorkerRequests] = useState([]);
  const [paymentHistory, setPaymentHistory] = useState([]);
  const [paymentDetails, setPaymentDetails] = useState(null);
  const [paymentJobId, setPaymentJobId] = useState(null);
  const [paymentReference, setPaymentReference] = useState('');
  const [paymentSaving, setPaymentSaving] = useState(false);
  const [availabilitySaving, setAvailabilitySaving] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [selectedWorkerId, setSelectedWorkerId] = useState(null);
  const [expandedWorkerId, setExpandedWorkerId] = useState(null);
  const [request, setRequest] = useState({ service_type:null, description:'', area:'Area A', latitude:12.9716, longitude:77.5946, urgency:null });
  const [authMessage, setAuthMessage] = useState({type:'', text:''});
  const [sosConfirmJobId, setSosConfirmJobId] = useState(null);
  const [sosLoading, setSosLoading] = useState(false);

  const apiFetch = async (path, options={}) => {
    const headers = new Headers(options.headers || {});
    if (auth.token) {
      headers.set('Authorization', `Bearer ${auth.token}`);
    }
    if (options.body && !headers.has('Content-Type')) {
      headers.set('Content-Type', 'application/json');
    }
    const response = await fetch(`${API}${path}`, { ...options, headers });
    if (response.status === 401) {
      localStorage.removeItem('handyman-token');
      localStorage.removeItem('handyman-user');
      setAuth({ token: null, user: null });
      setView('auth');
      throw new Error('Your session expired. Please log in again.');
    }
    return response;
  };

  useEffect(() => {
    if (!auth.token) {
      setWorkerProfile(null);
      setCustomerRequests([]);
      setWorkerRequests([]);
      setPaymentHistory([]);
      setPaymentDetails(null);
      setPaymentJobId(null);
      return;
    }
    const syncUser = async () => {
      try {
        const response = await apiFetch('/auth/me');
        if (!response.ok) throw new Error('Unable to load user');
        const user = await response.json();
        setAuth(prev => ({ ...prev, user }));
        localStorage.setItem('handyman-user', JSON.stringify(user));

        if (user.role === 'worker') {
          const workerResponse = await apiFetch('/workers/me');
          if (!workerResponse.ok) throw new Error('Worker profile unavailable');
          const profile = await workerResponse.json();
          setWorkerProfile(profile);
        } else {
          setWorkerProfile(null);
        }
      } catch {
        localStorage.removeItem('handyman-token');
        localStorage.removeItem('handyman-user');
        setAuth({ token: null, user: null });
        setWorkerProfile(null);
      }
    };
    syncUser();
  }, [auth.token]);

  useEffect(() => {
    if (!auth.user) return;
    setView(auth.user.role === 'worker' ? 'worker' : auth.user.role === 'admin' ? 'cooperative' : 'customer');
  }, [auth.user]);

  useEffect(() => {
    if (!auth.token || !auth.user) return;
    fetch(`${API}/cooperative/dashboard`).then(r => r.json()).then(setDashboard).catch(() => {});
  }, [job, auth.token, auth.user]);

  useEffect(() => {
    if (!auth.token || !auth.user) return;
    if (auth.user.role === 'customer') {
      apiFetch('/service-requests/me?current_only=true')
        .then(response => response.ok ? response.json() : [])
        .then(setCustomerRequests)
        .catch(() => setCustomerRequests([]));
      apiFetch('/payments/me')
        .then(response => response.ok ? response.json() : [])
        .then(setPaymentHistory)
        .catch(() => setPaymentHistory([]));
    } else if (auth.user.role === 'worker') {
      apiFetch('/workers/me/requests')
        .then(response => response.ok ? response.json() : [])
        .then(setWorkerRequests)
        .catch(() => setWorkerRequests([]));
    } else {
      setCustomerRequests([]);
      setWorkerRequests([]);
      setPaymentHistory([]);
    }
  }, [auth.token, auth.user, job]);

  useEffect(() => {
    if (!auth.token || !auth.user) return undefined;
    const refreshRequests = async () => {
      const endpoint = auth.user.role === 'worker' ? '/workers/me/requests' : auth.user.role === 'customer' ? '/service-requests/me?current_only=true' : null;
      if (!endpoint) return;
      const response = await apiFetch(endpoint);
      if (!response.ok) return;
      const data = await response.json();
      if (auth.user.role === 'worker') setWorkerRequests(data);
      if (auth.user.role === 'customer') {
        setCustomerRequests(data);
        const payments = await apiFetch('/payments/me');
        if (payments.ok) setPaymentHistory(await payments.json());
      }
    };
    const timer = window.setInterval(() => { refreshRequests().catch(() => {}); }, 5000);
    return () => window.clearInterval(timer);
  }, [auth.token, auth.user]);

  const runMatch = async (event) => {
    event?.preventDefault();
    setLoading(true);
    try {
      const response = await apiFetch('/service-request', { method:'POST', body: JSON.stringify(request) });
      const nextMatch = await response.json();
      setMatch(nextMatch);
      setSelectedWorkerId(null);
      setExpandedWorkerId(null);
    } catch (error) {
      setAuthMessage({ type:'error', text: error.message });
    }
    setLoading(false);
  };

  const accept = async (workerId = match?.best_match?.worker_id) => {
    if (!match || !workerId || confirming) return;
    setConfirming(true);
    try {
      const response = await apiFetch(`/accept-job/${match.request_id}?selected_worker_id=${workerId}`, { method:'POST' });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Unable to assign this worker.');
      if (auth.user?.role === 'customer') {
        setAuthMessage({ type:'success', text:`${payload.worker_name} has been assigned. Waiting for worker acceptance.` });
        setMatch(null);
        const refreshed = await apiFetch('/service-requests/me?current_only=true');
        if (refreshed.ok) setCustomerRequests(await refreshed.json());
      } else {
        setJob(payload);
      }
    } catch (error) {
      setAuthMessage({ type:'error', text:error.message || 'Unable to assign this worker.' });
    } finally {
      setConfirming(false);
    }
  };

  const advance = async () => {
    if (!job) return;
    const endpoint = job.status === 'assigned' ? 'start-job' : 'complete-job';
    const response = await apiFetch(`/${endpoint}/${job.job_id}`, { method:'POST' });
    setJob(await response.json());
  };

  const handleWorkerAction = async (action, requestItem) => {
    if (!requestItem || !requestItem.job_id) return;
    const endpoints = {
      accept: `/jobs/${requestItem.job_id}/accept`,
      reject: `/jobs/${requestItem.job_id}/reject`,
      start: `/jobs/${requestItem.job_id}/start`,
      complete: `/jobs/${requestItem.job_id}/complete`,
    };
    const response = await apiFetch(endpoints[action], { method:'POST' });
    const payload = await response.json();
    if (!response.ok) {
      setAuthMessage({ type:'error', text: payload.detail || 'Unable to update this job.' });
      return;
    }
    setJob(payload);
    const refreshed = await apiFetch('/workers/me/requests');
    setWorkerRequests(refreshed.ok ? await refreshed.json() : []);
    setAuthMessage({ type:'success', text: `Job ${action}d successfully.` });
  };

  const updateWorkerAvailability = async () => {
    if (!workerProfile || availabilitySaving) return;
    const nextStatus = workerProfile.availability_status === 'Available' ? 'Unavailable' : 'Available';
    setAvailabilitySaving(true);
    try {
      const response = await apiFetch('/workers/me/availability', {
        method: 'PATCH',
        body: JSON.stringify({ availability_status: nextStatus }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Unable to update availability.');
      setWorkerProfile(previous => ({ ...previous, ...payload }));
      setAuthMessage({ type:'success', text:'Availability updated.' });
    } catch (error) {
      setAuthMessage({ type:'error', text:error.message || 'Unable to update availability.' });
    } finally {
      setAvailabilitySaving(false);
    }
  };

  const loadPayment = async (jobId) => {
    if (!jobId) return;
    setPaymentJobId(jobId);
    setPaymentReference('');
    try {
      const response = await apiFetch(`/jobs/${jobId}/payment`);
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Unable to load payment.');
      setPaymentDetails(payload);
    } catch (error) {
      setPaymentDetails(null);
      setAuthMessage({ type:'error', text:error.message || 'Unable to load payment.' });
    }
  };

  const confirmPayment = async () => {
    if (!paymentDetails || paymentSaving) return;
    const reference = paymentReference.trim();
    if (!reference) {
      setAuthMessage({ type:'error', text:'Enter the transaction reference before confirming payment.' });
      return;
    }
    setPaymentSaving(true);
    try {
      const response = await apiFetch(`/payments/${paymentDetails.payment_id}/confirm`, {
        method:'POST',
        body: JSON.stringify({ transaction_reference: reference }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Unable to confirm payment.');
      setPaymentDetails(payload);
      setPaymentReference('');
      setAuthMessage({ type:'success', text:'Demo payment submitted.' });
      const requests = await apiFetch('/service-requests/me?current_only=true');
      if (requests.ok) setCustomerRequests(await requests.json());
      const payments = await apiFetch('/payments/me');
      if (payments.ok) setPaymentHistory(await payments.json());
    } catch (error) {
      setAuthMessage({ type:'error', text:error.message || 'Unable to confirm payment.' });
    } finally {
      setPaymentSaving(false);
    }
  };

  const reportCashPayment = async () => {
    if (!paymentDetails || paymentSaving) return;
    setPaymentSaving(true);
    try {
      const response = await apiFetch(`/payments/${paymentDetails.payment_id}/cash-report`, {
        method:'POST'
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Unable to report cash payment.');
      setPaymentDetails(payload);
      setPaymentReference('');
      setAuthMessage({ type:'success', text:'Cash payment reported.' });
      const requests = await apiFetch('/service-requests/me?current_only=true');
      if (requests.ok) setCustomerRequests(await requests.json());
      const payments = await apiFetch('/payments/me');
      if (payments.ok) setPaymentHistory(await payments.json());
    } catch (error) {
      setAuthMessage({ type:'error', text:error.message || 'Unable to report cash payment.' });
    } finally {
      setPaymentSaving(false);
    }
  };

  const confirmCashPayment = async (paymentId) => {
    if (!paymentId) return;
    try {
      const response = await apiFetch(`/payments/${paymentId}/cash-confirm`, {
        method:'POST'
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || 'Unable to confirm cash payment.');
      setAuthMessage({ type:'success', text:'Cash payment confirmed.' });
      const refreshed = await apiFetch('/workers/me/requests');
      setWorkerRequests(refreshed.ok ? await refreshed.json() : []);
    } catch (error) {
      setAuthMessage({ type:'error', text:error.message || 'Unable to confirm cash payment.' });
    }
  };

  const activateSOS = async (jobId) => {
    setSosLoading(true);
    try {
      const response = await apiFetch(`/jobs/${jobId}/sos`, { method: 'POST' });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Unable to activate SOS');
      setAuthMessage({ type: 'error', text: '🚨 SOS alert activated. Please stay calm and wait for assistance.' });
      // Refresh request lists so the SOS banner appears
      const endpoint = auth.user?.role === 'worker' ? '/workers/me/requests' : '/service-requests/me?current_only=true';
      const refreshed = await apiFetch(endpoint);
      if (refreshed.ok) {
        const data2 = await refreshed.json();
        if (auth.user?.role === 'worker') setWorkerRequests(data2);
        else setCustomerRequests(data2);
      }
    } catch (err) {
      setAuthMessage({ type: 'error', text: err.message || 'SOS failed. Please call emergency services directly.' });
    } finally {
      setSosLoading(false);
      setSosConfirmJobId(null);
    }
  };

  const acknowledgeSOS = async (sosId) => {
    try {
      const response = await apiFetch(`/sos/${sosId}/acknowledge`, { method: 'POST' });
      if (!response.ok) {
        const d = await response.json();
        throw new Error(d.detail || 'Unable to acknowledge SOS');
      }
      const endpoint = auth.user?.role === 'worker' ? '/workers/me/requests' : '/service-requests/me?current_only=true';
      const refreshed = await apiFetch(endpoint);
      if (refreshed.ok) {
        const data = await refreshed.json();
        if (auth.user?.role === 'worker') setWorkerRequests(data);
        else setCustomerRequests(data);
      }
    } catch (err) {
      setAuthMessage({ type: 'error', text: err.message });
    }
  };

  const resolveSOS = async (sosId) => {
    try {
      const response = await apiFetch(`/sos/${sosId}/resolve`, { method: 'POST' });
      if (!response.ok) {
        const d = await response.json();
        throw new Error(d.detail || 'Unable to resolve SOS');
      }
      setAuthMessage({ type: 'success', text: 'SOS alert resolved. Everyone is safe.' });
      const endpoint = auth.user?.role === 'worker' ? '/workers/me/requests' : '/service-requests/me?current_only=true';
      const refreshed = await apiFetch(endpoint);
      if (refreshed.ok) {
        const data = await refreshed.json();
        if (auth.user?.role === 'worker') setWorkerRequests(data);
        else setCustomerRequests(data);
      }
    } catch (err) {
      setAuthMessage({ type: 'error', text: err.message });
    }
  };

  const cancelSOS = async (sosId) => {
    try {
      const response = await apiFetch(`/sos/${sosId}/cancel`, { method: 'POST' });
      if (!response.ok) {
        const d = await response.json();
        throw new Error(d.detail || 'Unable to cancel SOS');
      }
      setAuthMessage({ type: 'success', text: 'SOS alert cancelled.' });
      const endpoint = auth.user?.role === 'worker' ? '/workers/me/requests' : '/service-requests/me?current_only=true';
      const refreshed = await apiFetch(endpoint);
      if (refreshed.ok) {
        const data = await refreshed.json();
        if (auth.user?.role === 'worker') setWorkerRequests(data);
        else setCustomerRequests(data);
      }
    } catch (err) {
      setAuthMessage({ type: 'error', text: err.message });
    }
  };

  const handleAuth = async (mode, payload) => {
    setAuthMessage({ type:'info', text: mode === 'login' ? 'Signing you in…' : 'Creating your account…' });
    const response = await fetch(`${API}/auth/${mode === 'login' ? 'login' : 'register'}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json();
    if (!response.ok) {
      setAuthMessage({ type:'error', text: data.detail || 'Authentication failed.' });
      return;
    }
    if (mode === 'login') {
      localStorage.setItem('handyman-token', data.access_token);
      localStorage.setItem('handyman-user', JSON.stringify(data.user));
      setAuth({ token: data.access_token, user: data.user });
      setAuthMessage({ type:'success', text: 'Welcome back. Redirecting…' });
    } else {
      setAuthMessage({ type:'success', text: 'Account created. Please log in.' });
      setView('auth');
    }
  };

  const logout = () => {
    localStorage.removeItem('handyman-token');
    localStorage.removeItem('handyman-user');
    setAuth({ token: null, user: null });
    setView('auth');
    setAuthMessage({ type:'success', text: 'You have been logged out.' });
  };

  if (!auth.user) {
    return <AuthScreen onSubmit={handleAuth} message={authMessage} />;
  }

  const visibleNav = auth.user.role === 'worker' ? [{id:'worker', label:'Worker desk', icon: BriefcaseBusiness}, {id:'cooperative', label:'Cooperative', icon: LayoutDashboard}, {id:'evaluation', label:'AI Evaluation', icon: Target}] : [{id:'customer', label:'Customer', icon: Wrench}, {id:'cooperative', label:'Cooperative', icon: LayoutDashboard}, {id:'evaluation', label:'AI Evaluation', icon: Target}];

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark"><Hammer size={20}/></div>
        <div><strong>HANDYMAN</strong><span>COOPERATIVE NETWORK</span></div>
      </div>
      <div className="side-label">Workspace</div>
      <nav>
        {visibleNav.map(({id,label,icon:Icon}) => <button className={view===id?'nav-item active':'nav-item'} onClick={() => setView(id)} key={id}><Icon size={18}/>{label}<ChevronRight size={15}/></button>)}
      </nav>
      <div className="sidebar-bottom">
        <div className="status-dot"><span/> System operational</div>
        <small>Smart work. Fair opportunities.<br/>Stronger communities.</small>
      </div>
    </aside>
    <main className="main">
      <header className="topbar">
        <div>
          <span className="eyebrow">HANDYMAN / {auth.user.role.toUpperCase()}</span>
          <h1>{view === 'customer' ? 'Request a helping hand' : view === 'worker' ? 'Worker command centre' : view === 'evaluation' ? 'AI Evaluation & Telemetry' : 'Cooperative intelligence'}</h1>
        </div>
        <div className="top-actions">
          <button className="icon-button"><Bell size={18}/><i/></button>
          <div className="profile">
            <div className="avatar soft">{(auth.user.name || 'U').slice(0,2).toUpperCase()}</div>
            <span>{auth.user.name}</span>
            <button className="logout-button" onClick={logout}><LogOut size={16}/> Logout</button>
          </div>
        </div>
      </header>
      {view === 'customer' && <Customer request={request} setRequest={setRequest} runMatch={runMatch} loading={loading} match={match} accept={accept} confirming={confirming} selectedWorkerId={selectedWorkerId} setSelectedWorkerId={setSelectedWorkerId} expandedWorkerId={expandedWorkerId} setExpandedWorkerId={setExpandedWorkerId} authMessage={authMessage} customerRequests={customerRequests} paymentDetails={paymentDetails} paymentJobId={paymentJobId} paymentReference={paymentReference} setPaymentReference={setPaymentReference} paymentSaving={paymentSaving} onLoadPayment={loadPayment} onConfirmPayment={confirmPayment} onReportCashPayment={reportCashPayment} sosConfirmJobId={sosConfirmJobId} setSosConfirmJobId={setSosConfirmJobId} onActivateSOS={activateSOS} onAcknowledgeSOS={acknowledgeSOS} onResolveSOS={resolveSOS} onCancelSOS={cancelSOS} sosLoading={sosLoading} />}
      {view === 'worker' && <Worker job={job} advance={advance} workerProfile={workerProfile} user={auth.user} incomingRequests={workerRequests} onWorkerAction={handleWorkerAction} onAvailabilityToggle={updateWorkerAvailability} availabilitySaving={availabilitySaving} onConfirmCashPayment={confirmCashPayment} sosConfirmJobId={sosConfirmJobId} setSosConfirmJobId={setSosConfirmJobId} onActivateSOS={activateSOS} onAcknowledgeSOS={acknowledgeSOS} onResolveSOS={resolveSOS} onCancelSOS={cancelSOS} sosLoading={sosLoading} />}
      {view === 'cooperative' && <Cooperative dashboard={dashboard} />}
      {view === 'evaluation' && <EvaluationDashboard apiFetch={apiFetch} />}
    </main>
  </div>;
}

function AuthScreen({ onSubmit, message }) {
  const [mode, setMode] = useState('login');
  const [form, setForm] = useState({ name:'', email:'', phone:'', password:'', confirmPassword:'', role:'customer', skills:'', certifications:'', service_area:'Area A', experience:'3', rate:'700', availability:true });

  const submit = async (event) => {
    event.preventDefault();
    if (form.password && form.confirmPassword && form.password !== form.confirmPassword) {
      alert('Passwords do not match.');
      return;
    }

    const payload = {
      name: form.name,
      email: form.email,
      phone: form.phone,
      password: form.password,
      role: form.role,
      skills: form.skills || undefined,
      certifications: form.certifications || undefined,
      service_areas: form.service_area ? [form.service_area] : ['Area A'],
      area: form.service_area || 'Area A',
      experience: Number(form.experience) || 1,
      rate: Number(form.rate) || 700,
      availability: form.availability,
      location: { latitude: 12.9716, longitude: 77.5946 },
    };

    if (mode === 'login') {
      onSubmit('login', { email: form.email, password: form.password });
    } else {
      onSubmit('register', payload);
    }
  };

  return <div className="auth-shell">
    <div className="auth-panel">
      <div className="auth-brand">
        <div className="brand-mark"><Hammer size={20}/></div>
        <div>
          <strong>HANDYMAN</strong>
          <span>AI-powered cooperative home services</span>
        </div>
      </div>

      <div className="auth-toggle">
        <button className={mode === 'login' ? 'toggle active' : 'toggle'} onClick={() => setMode('login')} type="button">Login</button>
        <button className={mode === 'register' ? 'toggle active' : 'toggle'} onClick={() => setMode('register')} type="button">Create Account</button>
      </div>

      <form className="auth-form" onSubmit={submit}>
        {mode === 'register' && <>
          <div className="field-row">
            <label>Name<input value={form.name} onChange={e => setForm({ ...form, name:e.target.value })} placeholder="Full name" /></label>
            <label>Role<select value={form.role} onChange={e => setForm({ ...form, role:e.target.value })}><option value="customer">Customer</option><option value="worker">Worker</option></select></label>
          </div>
          {form.role === 'worker' && <div className="field-row">
            <label>Skills<input value={form.skills} onChange={e => setForm({ ...form, skills:e.target.value })} placeholder="Electrical" /></label>
            <label>Certificates<input value={form.certifications} onChange={e => setForm({ ...form, certifications:e.target.value })} placeholder="Electrical Safety" /></label>
          </div>}
          {form.role === 'worker' && <div className="field-row">
            <label>Service area<select value={form.service_area} onChange={e => setForm({ ...form, service_area:e.target.value })}><option value="Area A">Area A</option><option value="Area B">Area B</option><option value="Area C">Area C</option><option value="Area D">Area D</option><option value="Area E">Area E</option></select></label>
            <label>Experience<input type="number" min="1" value={form.experience} onChange={e => setForm({ ...form, experience:e.target.value })} /></label>
          </div>}
          {form.role === 'worker' && <div className="field-row">
            <label>Rate<input type="number" min="300" value={form.rate} onChange={e => setForm({ ...form, rate:e.target.value })} /></label>
          </div>}
        </>}

        <label>Email<input type="email" value={form.email} onChange={e => setForm({ ...form, email:e.target.value })} placeholder="you@example.com" required /></label>
        <label>Phone<input value={form.phone} onChange={e => setForm({ ...form, phone:e.target.value })} placeholder="Phone number" required /></label>
        <label>Password<input type="password" value={form.password} onChange={e => setForm({ ...form, password:e.target.value })} placeholder="Password" required /></label>
        {mode === 'register' && <label>Confirm Password<input type="password" value={form.confirmPassword} onChange={e => setForm({ ...form, confirmPassword:e.target.value })} placeholder="Confirm password" required /></label>}
        {mode === 'register' && form.role === 'worker' && <label className="checkbox-row"><input type="checkbox" checked={form.availability} onChange={e => setForm({ ...form, availability:e.target.checked })} /> Available for jobs</label>}
        {message.text && <div className={`message ${message.type}`}>{message.text}</div>}
        <button className="primary auth-submit" type="submit">{mode === 'login' ? 'Login' : 'Create account'}</button>
      </form>
    </div>
  </div>;
}

function Customer({request,setRequest,runMatch,loading,match,accept,confirming,selectedWorkerId,setSelectedWorkerId,expandedWorkerId,setExpandedWorkerId,authMessage,customerRequests=[],paymentDetails=null,paymentJobId=null,paymentReference='',setPaymentReference, paymentSaving=false,onLoadPayment,onConfirmPayment,onReportCashPayment,sosConfirmJobId,setSosConfirmJobId,onActivateSOS,onAcknowledgeSOS,onResolveSOS,onCancelSOS,sosLoading}) {
  const [paymentMethodUI, setPaymentMethodUI] = useState('upi');
  const statusLabel = {
    matching: 'Searching',
    matched: 'Worker selected',
    assigned: 'Waiting for worker acceptance',
    accepted: 'Worker accepted',
    in_progress: 'Job in progress',
    completed: 'Completed',
    rejected: 'Cancelled',
  };
  const paymentStatusLabel = (status) => {
    if (status === 'paid') return 'PAID';
    if (status === 'pending') return 'Pending';
    if (status === 'awaiting_cash_confirmation') return '⏳ Awaiting worker confirmation';
    if (status === 'awaiting_worker_confirmation') return '⏳ Awaiting worker confirmation';
    return 'Not due';
  };

  return <div className="content-grid">
    <section className="hero-panel">
      <div className="hero-copy">
        <span className="pill accent"><Sparkles size={14}/> Offline AI request understanding</span>
        <h2>Household help,<br/><em>cooperatively delivered.</em></h2>
        <p>Describe the problem naturally. Handyman understands the request, searches the worker pool, and explains the allocation.</p>
        <div className="metric-row">
          <div><strong>50</strong><span>workers searched</span></div>
          <div><strong>6</strong><span>service categories</span></div>
          <div><strong>100%</strong><span>explainable scores</span></div>
        </div>
      </div>
      <div className="hero-visual">
        <div className="orbit orbit-one"/>
        <div className="orbit orbit-two"/>
        <div className="visual-card"><Sparkles size={28}/><strong>Intelligent<br/>allocation</strong><span>Local fallback always ready</span></div>
        <div className="visual-tag"><Activity size={15}/> Live worker search</div>
      </div>
    </section>

    <section className="request-card">
      <div className="section-heading">
        <div><span className="eyebrow">NEW SERVICE REQUEST</span><h3>What do you need help with?</h3></div>
        <span className="step">01 / 03</span>
      </div>
      <form onSubmit={runMatch}>
        <label>Describe the problem in your own words</label>
        <textarea required placeholder="My bathroom pipe is leaking urgently" value={request.description} onChange={e => setRequest({...request, description:e.target.value})} />
        <label>Optional service hint</label>
        <div className="service-grid">
          {['Plumbing','Electrical','Carpentry','Cleaning','Painting','Appliance Repair'].map(item => <button type="button" className={request.service_type===item?'service-option selected':'service-option'} onClick={() => setRequest({...request, service_type:item})} key={item}><Wrench size={17}/><span>{item}</span>{request.service_type===item && <Check size={15}/>}</button>)}
        </div>
        <div className="form-row">
          <div>
            <label>Service area</label>
            <select value={request.area} onChange={e => setRequest({...request, area:e.target.value})}>
              {['Area A','Area B','Area C','Area D','Area E'].map(area => <option key={area} value={area}>{area}</option>)}
            </select>
          </div>
          <div>
            <label>Urgency</label>
            <select value={request.urgency || 'normal'} onChange={e => setRequest({...request, urgency:e.target.value})}>
              <option value="normal">Normal</option>
              <option value="emergency">Emergency</option>
            </select>
          </div>
        </div>
        {authMessage.text && <div className={`message ${authMessage.type}`}>{authMessage.text}</div>}
        <button className="primary submit-button" type="submit" disabled={loading}>{loading ? 'Finding the best worker…' : 'Find my best match'}</button>
      </form>
    </section>

    {match ? <MatchCard match={match} accept={accept} confirming={confirming} selectedWorkerId={selectedWorkerId} setSelectedWorkerId={setSelectedWorkerId} expandedWorkerId={expandedWorkerId} setExpandedWorkerId={setExpandedWorkerId} /> : <section className="empty-state-card"><Sparkles size={20}/> Match results will appear here after the request is submitted.</section>}

    <section className="request-card">
      <div className="section-heading">
        <div><span className="eyebrow">MY REQUESTS</span><h3>Live service status</h3></div>
      </div>
      {customerRequests.length === 0 ? (
        <div className="empty-state"><BriefcaseBusiness size={28}/><p>No requests yet. Create one to track the journey.</p></div>
      ) : (
        <div className="request-list">
          {customerRequests.map((item) => {
            const isCompleted = item.job_status === 'completed';
            const showPaymentPanel = paymentJobId === item.job_id && paymentDetails;
            const paymentStatus = showPaymentPanel ? paymentDetails.status : item.payment_status;
            return (
              <div className={isCompleted ? 'request-row request-row-completed' : 'request-row'} key={item.id}>
                <div>
                  <strong>{item.service}</strong>
                  <small>{item.description}</small>
                </div>
                <div className="request-meta">
                  <span>{item.area}</span>
                  <span>{statusLabel[item.job_status || item.status] || item.job_status || item.status}</span>
                </div>
                {item.assigned_worker && <small className="request-worker">Worker: {item.assigned_worker}</small>}
                {/* SOS button for active jobs */}
                {item.job_id && ['assigned','accepted','in_progress'].includes(item.job_status) && (
                  <button
                    type="button"
                    className="sos-trigger-btn"
                    onClick={() => setSosConfirmJobId(item.job_id)}
                    disabled={sosLoading}
                  >
                    <AlertTriangle size={15}/> SOS / Safety
                  </button>
                )}
                {/* SOS Panel */}
                {item.sos_alert && (
                  <SOSPanel
                    sos={item.sos_alert}
                    onAcknowledge={onAcknowledgeSOS}
                    onResolve={onResolveSOS}
                    onCancel={onCancelSOS}
                    callerRole="customer"
                  />
                )}
                {isCompleted && (
                  <div className="completion-panel">
                    <div className="completion-badge"><BadgeCheck size={15}/> SERVICE COMPLETED</div>
                    <div className="completion-grid">
                      <div><span>Worker</span><strong>{item.assigned_worker || 'Assigned worker'}</strong></div>
                      <div><span>Service</span><strong>{item.service}</strong></div>
                      <div><span>Amount</span><strong>{formatCurrency(item.job_amount)}</strong></div>
                      <div><span>Payment</span><strong className={paymentStatus === 'paid' ? 'payment-paid' : 'payment-pending'}>{paymentStatusLabel(paymentStatus)}</strong></div>
                    </div>
                    {paymentStatus !== 'paid'
                      && paymentStatus !== 'awaiting_cash_confirmation'
                      && paymentStatus !== 'awaiting_worker_confirmation'
                      && item.job_id && (
                      <button type="button" className="primary payment-button" onClick={() => onLoadPayment(item.job_id)}>
                        <CreditCard size={16}/> PAY NOW
                      </button>
                    )}
                    {paymentStatus === 'paid' && (item.payment_transaction_reference || paymentDetails?.transaction_reference) && (
                      <div className="payment-success-inline">
                        <Check size={15}/> Payment confirmed · Ref: {item.payment_transaction_reference || paymentDetails?.transaction_reference}
                      </div>
                    )}
                    {showPaymentPanel && (
                      <div className="payment-panel">
                        <div className="payment-panel-heading"><QrCode size={18}/> PAYMENT</div>
                        {paymentDetails.demo_notice && <p className="payment-demo-notice">{paymentDetails.demo_notice}</p>}
                        <div className="payment-amount-row">
                          <span>Amount</span>
                          <strong>{formatCurrency(paymentDetails.amount)}</strong>
                        </div>
                        {paymentDetails.status === 'paid' ? (
                          <div className="payment-success">
                            <BadgeCheck size={22}/>
                            <strong>Payment Successful / Confirmed</strong>
                            <div className="payment-success-grid">
                              <div><span>Amount</span><strong>{formatCurrency(paymentDetails.amount)}</strong></div>
                              <div><span>Method</span><strong>{paymentDetails.payment_method === 'Cash' ? 'Cash' : 'UPI'}</strong></div>
                              <div><span>Status</span><strong className="payment-paid">PAID</strong></div>
                            </div>
                          </div>
                        ) : (paymentDetails.status === 'awaiting_cash_confirmation' || paymentDetails.status === 'awaiting_worker_confirmation') ? (
                          <div className="payment-success">
                            <Clock3 size={22}/>
                            <strong>Awaiting Worker Confirmation</strong>
                            <div className="payment-success-grid">
                              <div><span>Amount</span><strong>{formatCurrency(paymentDetails.amount)}</strong></div>
                              <div><span>Method</span><strong>{paymentDetails.status === 'awaiting_cash_confirmation' ? 'Cash' : 'UPI'}</strong></div>
                              <div><span>Status</span><strong>Submitted — worker to confirm</strong></div>
                            </div>
                          </div>
                        ) : (
                          <>
                            <div className="payment-method-toggle" style={{display: 'flex', gap: '8px', marginBottom: '16px'}}>
                              <button type="button" className={paymentMethodUI === 'upi' ? 'primary' : 'ghost-button'} onClick={() => setPaymentMethodUI('upi')} style={{flex: 1}}>📱 Pay via QR / UPI</button>
                              <button type="button" className={paymentMethodUI === 'cash' ? 'primary' : 'ghost-button'} onClick={() => setPaymentMethodUI('cash')} style={{flex: 1}}>💵 Paid in Cash</button>
                            </div>

                            {paymentMethodUI === 'upi' && <>
                              <div className="payment-qr-block">
                                <span className="eyebrow">Scan to Pay</span>
                                {paymentDetails.qr_payload ? (
                                  <div className="payment-qr-image" style={{padding: '16px', background: 'white', display: 'inline-block', borderRadius: '8px', border: '1px solid #e2e8f0'}}>
                                    <QRCodeSVG value={paymentDetails.qr_payload} size={150} level={"M"} />
                                  </div>
                                ) : paymentDetails.qr_image ? (
                                  <img className="payment-qr-image" src={paymentDetails.qr_image} alt="UPI payment QR code" />
                                ) : (
                                  <div className="payment-qr-fallback"><QrCode size={48}/><small>QR unavailable</small></div>
                                )}
                                <div className="payment-upi-id"><span>UPI ID</span><strong>{paymentDetails.upi_id}</strong></div>
                              </div>
                              <label className="payment-reference-field">
                                Transaction / UPI Reference ID
                                <input
                                  value={paymentReference}
                                  onChange={(event) => setPaymentReference(event.target.value)}
                                  placeholder="Enter UPI transaction reference"
                                />
                              </label>
                              <button type="button" className="primary payment-button" onClick={onConfirmPayment} disabled={paymentSaving}>
                                {paymentSaving ? 'Confirming…' : 'Confirm UPI Payment'}
                              </button>
                            </>}

                            {paymentMethodUI === 'cash' && <>
                              <div className="cash-payment-info" style={{padding: '16px', background: '#f8fafc', borderRadius: '8px', marginBottom: '16px', border: '1px solid #e2e8f0'}}>
                                <p style={{margin: 0, fontSize: '14px'}}>You are confirming that you paid <strong>{formatCurrency(paymentDetails.amount)}</strong> in cash to the worker.</p>
                              </div>
                              <button type="button" className="primary payment-button" onClick={onReportCashPayment} disabled={paymentSaving}>
                                {paymentSaving ? 'Confirming…' : 'Confirm Cash Payment'}
                              </button>
                            </>}
                          </>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>

    {/* SOS Confirmation Modal */}
    {sosConfirmJobId && (
      <div className="sos-modal-overlay" role="dialog" aria-modal="true">
        <div className="sos-modal">
          <div className="sos-modal-icon"><AlertTriangle size={36}/></div>
          <h3>Activate SOS Alert?</h3>
          <p>This will notify your assigned worker and flag this job as an emergency. Emergency services are <strong>not</strong> automatically called — this is a demo safety system.</p>
          <p>If there is a real emergency, please call <a href="tel:112" className="sos-emergency-link"><Phone size={13}/> 112</a> immediately.</p>
          <div className="sos-modal-actions">
            <button type="button" className="sos-modal-cancel" onClick={() => setSosConfirmJobId(null)} disabled={sosLoading}>Cancel</button>
            <button type="button" className="sos-modal-confirm" onClick={() => onActivateSOS(sosConfirmJobId)} disabled={sosLoading}>
              {sosLoading ? 'Activating…' : '🚨 Activate SOS'}
            </button>
          </div>
        </div>
      </div>
    )}
  </div>;
}

function SOSPanel({ sos, onAcknowledge, onResolve, onCancel, callerRole }) {
  if (!sos || sos.status === 'RESOLVED' || sos.status === 'CANCELLED') return null;
  const isActive = sos.status === 'ACTIVE';
  const isAcknowledged = sos.status === 'ACKNOWLEDGED';
  return (
    <div className={`sos-banner ${isActive ? 'sos-active' : 'sos-acknowledged'}`}>
      <div className="sos-banner-heading">
        <AlertTriangle size={18} />
        <strong>{isActive ? '🚨 SOS ALERT ACTIVE' : '✅ SOS ACKNOWLEDGED'}</strong>
        <span>Activated by {sos.activated_by_role}</span>
      </div>
      <div className="sos-timeline">
        <div className="sos-timeline-item done">✔ Alert sent · {new Date(sos.created_at).toLocaleTimeString('en-IN', {hour:'2-digit',minute:'2-digit'})}</div>
        {sos.acknowledged_at && <div className="sos-timeline-item done">✔ Acknowledged · {new Date(sos.acknowledged_at).toLocaleTimeString('en-IN', {hour:'2-digit',minute:'2-digit'})}</div>}
        {!sos.acknowledged_at && <div className="sos-timeline-item pending">⏳ Waiting for acknowledgement…</div>}
      </div>
      <div className="sos-actions">
        <a href="tel:112" className="sos-call-btn"><Phone size={15}/> Call Emergency (112)</a>
        {isActive && <button type="button" className="sos-ack-btn" onClick={() => onAcknowledge(sos.id)}>Acknowledge</button>}
        <button type="button" className="sos-resolve-btn" onClick={() => onResolve(sos.id)}>Resolved — We're Safe</button>
        {isActive && sos.activated_by_role === callerRole && <button type="button" className="sos-cancel-btn" onClick={() => onCancel(sos.id)}>Cancel Alert</button>}
      </div>
    </div>
  );
}

function MatchCard({match,accept,confirming,selectedWorkerId,setSelectedWorkerId,expandedWorkerId,setExpandedWorkerId}) {
  const best = match?.best_match;
  const rankedCandidates = Array.isArray(match?.ranked_candidates) ? match.ranked_candidates : [];
  const alternatives = rankedCandidates.length > 1 ? rankedCandidates.slice(1) : [];
  const [workerDetails, setWorkerDetails] = useState({});

  if (!best) {
    return <section className="match-card"><h3>No eligible worker found</h3><p>{match?.message || 'No qualified worker is currently available.'}</p></section>;
  }

  const candidateLabels = {
    skill_match: 'Skill Match',
    availability: 'Availability',
    distance: 'Distance',
    urgency: 'Urgency',
    workload_balance: 'Workload',
    fair_opportunity: 'Fair Opportunity',
  };

  const handleDetailToggle = async (workerId) => {
    const isOpen = expandedWorkerId === workerId;
    setExpandedWorkerId(isOpen ? null : workerId);
    if (!workerDetails[workerId]) {
      const response = await fetch(`${API}/workers/${workerId}`);
      const detail = await response.json();
      setWorkerDetails(prev => ({...prev, [workerId]: detail}));
    }
  };

  const selectedCandidate = rankedCandidates.find(candidate => candidate.worker_id === selectedWorkerId) || best;
  const selectedName = selectedCandidate?.name || 'AI recommendation';
  const confirmButtonLabel = selectedWorkerId ? 'Confirm selected worker' : 'Confirm AI recommendation';
  const confirmWorkerId = selectedWorkerId ?? best.worker_id;

  return <section className="match-card">
    <div className="recommendation-header">
      <div className="ai-badge"><Star size={14} fill="currentColor"/> AI RECOMMENDED</div>
      <span className="eyebrow">{match.eligible_count} ELIGIBLE CANDIDATES EVALUATED</span>
    </div>

    <div className="match-top">
      <div>
        <h3>{best.name}</h3>
        <div className="rating-row"><Star size={16} fill="currentColor"/> {best.rating} <span>·</span><BadgeCheck size={16}/> Verified member</div>
      </div>
      <div className="score-box">
        <strong>{best.score}</strong>
        <span>/ 100 match</span>
      </div>
    </div>

    <div className="match-meta">
      <span><Clock3 size={16}/><strong>{best.eta_minutes} min</strong> ETA</span>
      <span><MapPin size={16}/>{best.distance_km} km away</span>
      <span><Users size={16}/>{best.workload_score < 60 ? 'High workload' : 'Healthy workload'}</span>
    </div>

    <div className="why-panel">
      <div className="why-title"><Sparkles size={16}/> WHY {best.name.split(' ')[0].toUpperCase()}?</div>
      <div className="reason-list">
        {best.reasons.map(reason => <div className="reason" key={reason}><Check size={15}/>{reason}</div>)}
      </div>
      <div className="score-breakdown">
        {Object.entries({skill_match: best.skill_score, availability: best.availability_score, distance: best.distance_score, urgency: best.urgency_score, workload_balance: best.workload_score, fair_opportunity: best.fair_opportunity_score}).map(([key, value]) => <span key={key}><b>{value}</b><small>{candidateLabels[key]}</small></span>)}
      </div>
    </div>

    <div className="alternatives-wrapper">
      <div className="alt-header">
        <div>
          <span className="eyebrow">OTHER QUALIFIED WORKERS</span>
          <h4>Ranked alternatives</h4>
        </div>
      </div>
      <p className="alt-helper">AI recommends the best overall match, but you remain in control. Compare qualified workers and choose who you prefer.</p>

      {rankedCandidates.length === 0 && <div className="empty-message">No qualified worker is currently available.</div>}
      {rankedCandidates.length === 1 && <div className="empty-message">Only one qualified worker is currently available.</div>}

      {alternatives.length > 0 && <div className="alt-grid">
        {alternatives.map((candidate, index) => {
          const isSelected = selectedWorkerId === candidate.worker_id;
          const isExpanded = expandedWorkerId === candidate.worker_id;
          const detail = workerDetails[candidate.worker_id];

          return <article className={isSelected ? 'alt-card selected' : 'alt-card'} key={candidate.worker_id}>
            <div className="alt-rank">Rank #{index + 2}</div>
            <h5>{candidate.name}</h5>
            <div className="alt-metric"><strong>{candidate.score}/100</strong> Match</div>
            <div className="alt-rating"><Star size={15} fill="currentColor"/> {candidate.rating}</div>
            <div className="alt-stats">
              <span><MapPin size={14}/>{candidate.distance_km} km away</span>
              <span><Clock3 size={14}/>{candidate.eta_minutes} min ETA</span>
              <span><Users size={14}/>{candidate.workload_balance < 60 ? 'High workload' : 'Healthy workload'}</span>
              <span><Activity size={14}/>{candidate.availability > 60 ? 'Available' : 'Limited availability'}</span>
            </div>
            <div className="alt-actions">
              <button type="button" className="ghost-button" onClick={() => handleDetailToggle(candidate.worker_id)}>{isExpanded ? 'Hide details' : 'View details'}</button>
              <button type="button" className={isSelected ? 'secondary-button selected' : 'primary-button'} onClick={() => setSelectedWorkerId(candidate.worker_id)}>{isSelected ? '✓ SELECTED' : 'Select this worker'}</button>
            </div>

            {isExpanded && <div className="detail-panel">
              <div className="detail-heading">WORKER PROFILE</div>
              <div className="detail-grid">
                <div><span>Name</span><strong>{detail?.name || candidate.name}</strong></div>
                <div><span>Rating</span><strong>{detail?.rating ?? candidate.rating}</strong></div>
                <div><span>Verified status</span><strong>{detail?.verification_status || 'Verified'}</strong></div>
                <div><span>Experience</span><strong>{detail?.experience_years ?? 'N/A'} years</strong></div>
                <div><span>Completed jobs</span><strong>{detail?.jobs_completed ?? 'N/A'}</strong></div>
                <div><span>Skills</span><strong>{detail?.skills || 'Available in ranked match data'}</strong></div>
                <div><span>Availability</span><strong>{detail?.availability ? 'Available' : 'Unavailable'}</strong></div>
                <div><span>Current workload</span><strong>{detail?.current_workload ?? 'N/A'}</strong></div>
                <div><span>Distance</span><strong>{candidate.distance_km} km</strong></div>
                <div><span>ETA</span><strong>{candidate.eta_minutes} min</strong></div>
              </div>

              <div className="detail-heading">WHY THIS WORKER?</div>
              <div className="component-list">
                {Object.entries(candidate.components || {}).map(([key, value]) => <div className="component-row" key={key}><span>{candidateLabels[key] || key}</span><strong>{value}</strong></div>)}
              </div>
              <div className="match-score-row"><span>Match Score</span><strong>{candidate.score}/100</strong></div>
            </div>}
          </article>;
        })}
      </div>}
    </div>

    <div className="selection-summary">
      <div>
        <span className="eyebrow">SELECTED WORKER</span>
        <strong>{selectedName}</strong>
      </div>
      <button type="button" className="primary confirm-button" onClick={() => accept(confirmWorkerId)} disabled={confirming}>{confirming ? 'Assigning worker...' : confirmButtonLabel}</button>
    </div>
  </section>;
}

function Worker({job, advance, workerProfile, user, incomingRequests = [], onWorkerAction, onAvailabilityToggle, availabilitySaving, onConfirmCashPayment, sosConfirmJobId, setSosConfirmJobId, onActivateSOS, onAcknowledgeSOS, onResolveSOS, onCancelSOS, sosLoading}) {
  const profile = workerProfile || {};
  const workerName = profile.name || user?.name || 'Selected worker';
  const firstName = workerName.split(' ')[0];
  const primarySkills = profile.skills || 'Not set';
  const certificates = profile.certifications || 'Not provided';
  const experience = profile.experience_years ? `${profile.experience_years} years` : 'Not provided';
  const area = profile.area || 'Not set';
  const isAvailable = profile.availability_status === 'Available';
  const availability = isAvailable ? 'Available for work' : 'Currently unavailable';
  const rating = profile.rating ? `${profile.rating}/5` : 'No rating yet';
  const workload = profile.current_workload ?? 0;
  const earnings = typeof profile.earnings === 'number' ? `₹${profile.earnings.toLocaleString('en-IN')}` : '₹0';
  const completedJobs = profile.jobs_completed ?? 0;
  const statusLabel = {
    assigned: 'Assigned',
    accepted: 'Accepted',
    in_progress: 'In progress',
    completed: 'Completed',
    rejected: 'Cancelled',
  };

  return <div className="workspace">
    <div className="welcome-row">
      <div>
        <span className="eyebrow">{workerName.toUpperCase()} / COOPERATIVE MEMBER</span>
        <h2>{job ? `Good morning, ${firstName}.` : 'Worker command centre'}</h2>
        <p>{job ? 'The confirmed customer request is ready for your action.' : 'Your real worker profile is loaded from the database and stays synced across refreshes.'}</p>
      </div>
      <div className="availability-stack">
        <div className="availability-control">
          <div className={isAvailable ? 'availability available' : 'availability unavailable'}>
            <span className="live-dot"/> {availability}
          </div>
          <button
            type="button"
            className={isAvailable ? 'availability-toggle on' : 'availability-toggle'}
            onClick={onAvailabilityToggle}
            disabled={availabilitySaving || !workerProfile}
            aria-pressed={isAvailable}
          >
            {availabilitySaving ? 'Updating availability...' : isAvailable ? 'ON' : 'OFF'}
          </button>
        </div>
        <div className={isAvailable ? 'availability-note available-note' : 'availability-note'}>
          <strong>{isAvailable ? 'Available for work' : 'Currently unavailable'}</strong>
          <span>{isAvailable ? 'You can now receive new assignments.' : 'You are hidden from new AI assignments until you become available.'}</span>
        </div>
      </div>
    </div>

    <div className="stat-grid">
      <Stat label="Today’s earnings" value={earnings} trend="Live profile value" icon={IndianRupee}/>
      <Stat label="Completed jobs" value={String(completedJobs)} trend="Skill passport active" icon={Check}/>
      <Stat label="Current workload" value={String(workload)} trend="Capacity-aware allocation" icon={Activity}/>
    </div>

    <div className="two-col">
      <section className="panel job-panel">
        <div className="panel-heading">
          <div><span className="eyebrow">INCOMING ASSIGNMENT</span><h3>{job ? `${job.service_type} request` : 'No active job yet'}</h3></div>
          {job ? <span className="pill danger">{job.urgency}</span> : <span className="pill success">Listening</span>}
        </div>
        {job ? <>
          <div className="job-location"><MapPin size={19}/><div><strong>{job.area} · {job.description}</strong><span>Request #{job.request_id} · customer assignment</span></div></div>
          <div className="job-actions"><button className="primary" onClick={advance}>{job.status === 'assigned' ? 'Accept & start service' : job.status === 'in_progress' ? 'Complete service' : 'Service completed'} <ArrowRight size={16}/></button><span className="job-status"><Check size={14}/> {job.status.replace('_', ' ')}</span></div>
        </> : <div className="empty-state"><BriefcaseBusiness size={28}/><p>When a customer confirms a match, their job appears here.</p></div>}
      </section>

      <section className="panel passport">
        <div className="panel-heading">
          <div><span className="eyebrow">INCOMING REQUESTS</span><h3>Assigned jobs</h3></div>
        </div>
        <div className="request-list">
          {incomingRequests.length === 0 ? (
            <div className="empty-state"><BriefcaseBusiness size={28}/><p>No assigned jobs yet.</p></div>
          ) : incomingRequests.map((item) => (
            <div className="request-row" key={item.job_id}>
              <div>
                <strong>{item.service}</strong>
                <small>{item.description}</small>
                {item.customer_name && <small className="request-worker">Customer: {item.customer_name}</small>}
              </div>
              <div className="request-meta">
                <span>{item.area}</span>
                <span>{statusLabel[item.status] || item.status}</span>
              </div>
              {/* SOS button for active jobs */}
              {item.job_id && ['assigned','accepted','in_progress'].includes(item.status) && (
                <button
                  type="button"
                  className="sos-trigger-btn"
                  onClick={() => setSosConfirmJobId(item.job_id)}
                  disabled={sosLoading}
                >
                  <AlertTriangle size={15}/> SOS / Safety
                </button>
              )}
              {/* SOS Panel */}
              {item.sos_alert && (
                <SOSPanel
                  sos={item.sos_alert}
                  onAcknowledge={onAcknowledgeSOS}
                  onResolve={onResolveSOS}
                  onCancel={onCancelSOS}
                  callerRole="worker"
                />
              )}
              {item.status === 'completed' && (
                <div className="worker-payment-summary">
                  <div><span>Amount</span><strong>{formatCurrency(item.job_amount)}</strong></div>
                  <div><span>Worker Earnings</span><strong>{formatCurrency(item.worker_earning)}</strong></div>
                  <div><span>Payment</span><strong className={item.payment_status === 'paid' ? 'payment-paid' : 'payment-pending'}>
                    {item.payment_status === 'paid'
                      ? 'PAID'
                      : item.payment_status === 'awaiting_cash_confirmation'
                        ? '⏳ Customer paid cash — confirm receipt'
                        : item.payment_status === 'awaiting_worker_confirmation'
                          ? '⏳ Customer paid via UPI — confirm receipt'
                          : 'Awaiting Customer Payment'}
                  </strong></div>
                </div>
              )}
              <div className="job-actions">
                {item.status === 'assigned' && <button className="primary" type="button" onClick={() => onWorkerAction('accept', item)}>Accept</button>}
                {item.status === 'assigned' && <button className="ghost-button" type="button" onClick={() => onWorkerAction('reject', item)}>Reject</button>}
                {item.status === 'accepted' && <button className="primary" type="button" onClick={() => onWorkerAction('start', item)}>Start Job</button>}
                {item.status === 'in_progress' && <button className="primary" type="button" onClick={() => onWorkerAction('complete', item)}>Complete Job</button>}
                {item.status === 'completed' && (item.payment_status === 'awaiting_cash_confirmation' || item.payment_status === 'awaiting_worker_confirmation') && (
                  <button className="primary" type="button" onClick={() => onConfirmCashPayment(item.payment_id)}>
                    {item.payment_status === 'awaiting_cash_confirmation' ? '✓ Confirm Cash Received' : '✓ Confirm Payment Received'}
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      <section className="panel passport">
        <div className="panel-heading">
          <div><span className="eyebrow">SKILL PASSPORT</span><h3>Verified capability</h3></div>
          <ShieldCheck size={20}/>
        </div>
        <div className="passport-list">
          <div><span>Worker name</span><strong>{workerName}</strong></div>
          <div><span>Primary skills</span><strong>{primarySkills}</strong></div>
          <div><span>Certificates</span><strong>{certificates}</strong></div>
          <div><span>Experience</span><strong>{experience}</strong></div>
          <div><span>Service area</span><strong>{area}</strong></div>
          <div><span>Availability</span><strong>{availability}</strong></div>
          <div><span>Rating</span><strong>{rating}</strong></div>
        </div>
      </section>
    </div>

    {/* SOS Confirmation Modal */}
    {sosConfirmJobId && (
      <div className="sos-modal-overlay" role="dialog" aria-modal="true">
        <div className="sos-modal">
          <div className="sos-modal-icon"><AlertTriangle size={36}/></div>
          <h3>Activate SOS Alert?</h3>
          <p>This will notify the customer and flag this job as an emergency. Emergency services are <strong>not</strong> automatically called — this is a demo safety system.</p>
          <p>If there is a real emergency, please call <a href="tel:112" className="sos-emergency-link"><Phone size={13}/> 112</a> immediately.</p>
          <div className="sos-modal-actions">
            <button type="button" className="sos-modal-cancel" onClick={() => setSosConfirmJobId(null)} disabled={sosLoading}>Cancel</button>
            <button type="button" className="sos-modal-confirm" onClick={() => onActivateSOS(sosConfirmJobId)} disabled={sosLoading}>
              {sosLoading ? 'Activating…' : '🚨 Activate SOS'}
            </button>
          </div>
        </div>
      </div>
    )}
  </div>;
}

function Stat({label,value,trend,icon:Icon}) {
  return <div className="stat-card"><div className="stat-icon"><Icon size={18}/></div><span>{label}</span><strong>{value}</strong><small>{trend}</small></div>;
}

function Cooperative({dashboard}) {
  if (!dashboard) return <div className="loading-state">Loading cooperative intelligence...</div>;
  const bars = dashboard.demand;
  return <div className="workspace">
    <div className="welcome-row">
      <div>
        <span className="eyebrow">LIVE NETWORK OVERVIEW</span>
        <h2>See the whole system.</h2>
        <p>Allocation, capacity and fairness in one cooperative view.</p>
      </div>
      <button className="secondary"><Activity size={16}/> Live operations</button>
    </div>

    <div className="stat-grid">
      <Stat label="Total workers" value={dashboard.workforce.total} trend={`${dashboard.workforce.available} available now`} icon={Users}/>
      <Stat label="Jobs today" value={dashboard.jobs.today} trend={`${dashboard.jobs.completed} completed`} icon={BriefcaseBusiness}/>
      <Stat label="Emergency jobs" value={dashboard.jobs.emergency} trend="Rapid response active" icon={Zap}/>
      <Stat label="Overloaded" value={dashboard.workforce.overloaded} trend="Needs balancing" icon={Activity}/>
    </div>

    <div className="dashboard-grid">
      <section className="panel chart-panel">
        <div className="panel-heading">
          <div><span className="eyebrow">SERVICE DEMAND</span><h3>Requests by category</h3></div>
          <BarChart3 size={21}/>
        </div>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={bars}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e8e5df"/>
            <XAxis dataKey="service" tick={{fontSize:11}} axisLine={false} tickLine={false}/>
            <YAxis axisLine={false} tickLine={false} tick={{fontSize:11}}/>
            <Tooltip/>
            <Bar dataKey="requests" fill="#e76f51" radius={[5,5,0,0]}/>
          </BarChart>
        </ResponsiveContainer>
      </section>

      <section className="panel fairness-panel">
        <div className="panel-heading">
          <div><span className="eyebrow">WORKLOAD FAIRNESS</span><h3>Opportunity distribution</h3></div>
          <Users size={21}/>
        </div>
        {dashboard.workload.slice(0,5).map((item,index) => <div className="fair-row" key={item.name}><div className="fair-name"><span className={`rank rank-${index+1}`}>{index+1}</span><b>{item.name}</b><small>{item.area}</small></div><div className="fair-value"><strong>{item.jobs}</strong><span>jobs</span></div></div>)}
      </section>
    </div>
  </div>;
}

export default App;
