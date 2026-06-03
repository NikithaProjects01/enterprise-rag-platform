import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { Activity, Database, Eye, EyeOff, FileText, KeyRound, Lock, MessageSquare, Shield, Trash2, Upload, Users } from "lucide-react";
import "./styles.css";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8001";

function App() {
  const [token, setToken] = useState(localStorage.getItem("token") || "");
  const [user, setUser] = useState(null);
  const [analytics, setAnalytics] = useState(null);
  const [docs, setDocs] = useState([]);
  const [logs, setLogs] = useState([]);
  const [users, setUsers] = useState([]);
  const [feedbackRows, setFeedbackRows] = useState([]);
  const [evaluations, setEvaluations] = useState([]);
  const [answer, setAnswer] = useState(null);
  const [error, setError] = useState("");

  const headers = token ? { Authorization: `Bearer ${token}` } : {};

  async function api(path, options = {}) {
    const response = await fetch(`${API}${path}`, {
      ...options,
      headers: { ...headers, ...(options.headers || {}) },
    });
    if (!response.ok) throw new Error((await response.json()).detail || "Request failed");
    return response.json();
  }

  async function load() {
    if (!token) return;
    try {
      const me = await api("/me");
      setUser(me);
      setDocs(await api("/documents"));
      if (me.role === "admin") {
        setAnalytics(await api("/admin/analytics"));
        setLogs(await api("/admin/logs"));
        setUsers(await api("/admin/users"));
        setFeedbackRows(await api("/admin/feedback"));
        setEvaluations(await api("/admin/evaluations"));
      }
    } catch {
      localStorage.removeItem("token");
      setToken("");
    }
  }

  useEffect(() => {
    load();
  }, [token]);

  async function login(email, password) {
    setError("");
    try {
      const data = await api("/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      localStorage.setItem("token", data.token);
      setToken(data.token);
      setUser(data.user);
    } catch (err) {
      setError(err.message);
    }
  }

  async function deleteDoc(id) {
    if (!window.confirm("Are you sure you want to delete this document and all its chunks?")) {
      return;
    }
    setError("");
    try {
      await api(`/documents/${id}`, { method: "DELETE" });
      await load();
    } catch (err) {
      setError("Delete failed: " + err.message);
    }
  }

  if (!token) return <Login onLogin={login} error={error} />;

  return (
    <div className="shell">
      <aside>
        <div className="brand"><Database size={24} /> Enterprise RAG</div>
        <div className="profile">
          <strong>{user?.name}</strong>
          <span>{user?.role}</span>
        </div>
        <ChangePassword api={api} setError={setError} />
        <button onClick={() => { localStorage.removeItem("token"); setToken(""); }}>
          <Lock size={16} /> Sign out
        </button>
      </aside>
      <main>
        <section className="topbar">
          <div>
            <h1>RAG Operations Dashboard</h1>
            <p>Retrieval, evaluation, security, and usage monitoring in one workspace.</p>
          </div>
          <span className="status"><Shield size={16} /> RBAC enabled</span>
        </section>

        {user?.role === "admin" && analytics && <Analytics data={analytics} />}

        <div className="grid two">
          {user?.role === "admin" && <UploadPanel onDone={load} setError={setError} />}
          <AskPanel api={api} answer={answer} setAnswer={setAnswer} setError={setError} />
        </div>

        <div className="grid two">
          <Documents docs={docs} isAdmin={user?.role === "admin"} onDelete={deleteDoc} />
          {user?.role === "admin" && <Logs logs={logs} />}
        </div>
        {user?.role === "admin" && (
          <div className="grid three">
            <UsersTable users={users} />
            <FeedbackTable rows={feedbackRows} />
            <EvaluationsTable rows={evaluations} />
          </div>
        )}
        {error && <div className="toast">{error}</div>}
      </main>
    </div>
  );
}

function Login({ onLogin, error }) {
  const [email, setEmail] = useState("admin@rag.com");
  const [password, setPassword] = useState("admin123");
  const [showPassword, setShowPassword] = useState(false);
  return (
    <div className="login">
      <form onSubmit={(e) => { e.preventDefault(); onLogin(email, password); }}>
        <h1>Enterprise RAG Platform</h1>
        <p>Login as admin or user to access document intelligence workflows.</p>
        <label>Email</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} />
        <label>Password</label>
        <div className="passwordField">
          <input type={showPassword ? "text" : "password"} value={password} onChange={(e) => setPassword(e.target.value)} />
          <button type="button" className="iconBtn" onClick={() => setShowPassword(!showPassword)} aria-label={showPassword ? "Hide password" : "Show password"}>
            {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        </div>
        <button>Login</button>
        <div className="hint">Admin: admin@rag.com / admin123<br />User: user@rag.com / user123</div>
        {error && <div className="error">{error}</div>}
      </form>
    </div>
  );
}

function ChangePassword({ api, setError }) {
  const [open, setOpen] = useState(false);
  const [show, setShow] = useState(false);
  const [saved, setSaved] = useState("");

  async function submit(e) {
    e.preventDefault();
    setError("");
    setSaved("");
    const form = new FormData(e.currentTarget);
    try {
      await api("/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: form.get("current_password"),
          new_password: form.get("new_password"),
        }),
      });
      e.currentTarget.reset();
      setSaved("Password changed");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="passwordBox">
      <button type="button" className="secondaryBtn" onClick={() => setOpen(!open)}>
        <KeyRound size={16} /> Change password
      </button>
      {open && (
        <form onSubmit={submit}>
          <input name="current_password" type={show ? "text" : "password"} placeholder="Current password" required />
          <input name="new_password" type={show ? "text" : "password"} placeholder="New password" required />
          <label className="checkline">
            <input type="checkbox" checked={show} onChange={(e) => setShow(e.target.checked)} />
            Show passwords
          </label>
          <button>Save password</button>
          {saved && <span className="saved">{saved}</span>}
        </form>
      )}
    </div>
  );
}

function Analytics({ data }) {
  const cards = [
    ["Users", data.users, Users],
    ["Documents", data.documents, FileText],
    ["Questions", data.questions, MessageSquare],
    ["Latency", `${data.avg_latency_ms} ms`, Activity],
    ["Accuracy", data.accuracy, Shield],
    ["Hallucination", data.hallucination_rate, Shield],
    ["Cost", `$${data.cost_usd}`, Activity],
    ["Feedback", data.feedback_score, MessageSquare],
  ];
  return <section className="metrics">{cards.map(([label, value, Icon]) => <div className="metric" key={label}><Icon size={18} /><span>{label}</span><strong>{value}</strong></div>)}</section>;
}

function UploadPanel({ onDone, setError }) {
  const [strategy, setStrategy] = useState("recursive");
  const [message, setMessage] = useState("");
  async function upload(e) {
    e.preventDefault();
    const formElement = e.currentTarget;
    setError("");
    setMessage("");
    const form = new FormData(formElement);
    try {
      const response = await fetch(`${API}/documents/upload`, {
        method: "POST",
        headers: { Authorization: `Bearer ${localStorage.getItem("token")}` },
        body: form,
      });
      if (!response.ok) throw new Error((await response.json()).detail);
      const result = await response.json();
      formElement.reset();
      setMessage(`${result.filename} uploaded and indexed into ${result.chunks} chunks`);
      onDone();
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <section className="panel">
      <h2><Upload size={18} /> Document Ingestion</h2>
      <form onSubmit={upload}>
        <input type="file" name="file" required />
        <select name="chunking_strategy" value={strategy} onChange={(e) => setStrategy(e.target.value)}>
          <option value="fixed">Fixed chunking</option>
          <option value="recursive">Recursive chunking</option>
          <option value="semantic">Semantic-lite chunking</option>
        </select>
        <button>Upload and Index</button>
        {message && <div className="success">{message}</div>}
      </form>
    </section>
  );
}

function AskPanel({ api, answer, setAnswer, setError }) {
  const [question, setQuestion] = useState("What are the main points in the uploaded documents?");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  async function ask(e) {
    e.preventDefault();
    setError("");
    setFeedbackMessage("");
    try {
      setAnswer(await api("/rag/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      }));
    } catch (err) {
      setError(err.message);
    }
  }
  async function feedback(score) {
    if (!answer) return;
    setError("");
    setFeedbackMessage("");
    try {
      await api("/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query_id: answer.query_id, score }),
      });
      setFeedbackMessage(score === 1 ? "Marked as good" : "Marked as wrong");
    } catch (err) {
      setError(err.message);
    }
  }
  return (
    <section className="panel">
      <h2><MessageSquare size={18} /> RAG Q&A</h2>
      <form onSubmit={ask}>
        <textarea value={question} onChange={(e) => setQuestion(e.target.value)} />
        <button>Ask Documents</button>
      </form>
      {answer && <div className="answer">
        <p>{answer.answer}</p>
        <div className="chips">{answer.citations.map((c) => <span key={c.source}>{c.source} · {c.score.toFixed(2)}</span>)}</div>
        <div className="eval">Relevance {answer.metrics.relevance} · Faithfulness {answer.metrics.faithfulness} · Latency {answer.metrics.latency_ms}ms</div>
        <div className="actions"><button onClick={() => feedback(1)}>Good</button><button onClick={() => feedback(-1)}>Wrong</button></div>
        {feedbackMessage && <div className="success compact">{feedbackMessage}</div>}
      </div>}
    </section>
  );
}

function Documents({ docs, isAdmin, onDelete }) {
  return (
    <section className="panel">
      <h2><FileText size={18} /> Documents</h2>
      {docs.length === 0 ? (
        <div className="empty" style={{ color: "#697775", textAlign: "center", padding: "20px 0" }}>No documents uploaded yet.</div>
      ) : (
        docs.map((doc) => (
          <div className="row" key={doc.id} style={{ alignItems: "center" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>
              <strong>{doc.filename}</strong>
              <span style={{ fontSize: "12px", color: "#697775" }}>Strategy: {doc.chunking_strategy}</span>
            </div>
            {isAdmin && (
              <button
                type="button"
                className="deleteBtn"
                onClick={() => onDelete(doc.id)}
                aria-label={`Delete ${doc.filename}`}
              >
                <Trash2 size={16} />
              </button>
            )}
          </div>
        ))
      )}
    </section>
  );
}

function Logs({ logs }) {
  return <section className="panel"><h2><Activity size={18} /> Audit Logs</h2>{logs.map((log) => <div className="row" key={log.id}><strong>{log.action}</strong><span>{log.detail}</span></div>)}</section>;
}

function UsersTable({ users }) {
  return (
    <section className="panel">
      <h2><Users size={18} /> Users</h2>
      {users.map((item) => (
        <div className="dataRow" key={item.id}>
          <strong>{item.name}</strong>
          <span>{item.email}</span>
          <b>{item.role}</b>
        </div>
      ))}
    </section>
  );
}

function FeedbackTable({ rows }) {
  return (
    <section className="panel">
      <h2><MessageSquare size={18} /> Feedback</h2>
      {rows.length === 0 ? <p className="muted">No feedback submitted yet.</p> : rows.map((item) => (
        <div className="dataRow" key={item.id}>
          <strong>{item.label}</strong>
          <span>{item.question}</span>
          <b>{item.user_email}</b>
        </div>
      ))}
    </section>
  );
}

function EvaluationsTable({ rows }) {
  return (
    <section className="panel">
      <h2><Shield size={18} /> Evaluations</h2>
      {rows.length === 0 ? <p className="muted">No questions evaluated yet.</p> : rows.map((item) => (
        <div className="dataRow" key={item.id}>
          <strong>{item.question}</strong>
          <span>Rel {item.relevance} · Faith {item.faithfulness} · Hall {item.hallucination_rate}</span>
          <b>{Math.round(item.latency_ms)} ms</b>
        </div>
      ))}
    </section>
  );
}

createRoot(document.getElementById("root")).render(<App />);
