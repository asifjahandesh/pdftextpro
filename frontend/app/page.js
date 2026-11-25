"use client";

import { useEffect, useRef, useState } from "react";
import {
  deleteDocument,
  downloadDocumentTxt,
  getDocument,
  getDocumentText,
  listDocuments,
  loginUser,
  registerUser,
  resumeDocument,
  retryFailedPages,
  uploadDocument,
} from "../lib/api";

const LANGUAGES = [
  { value: "auto", label: "Auto (Bengali, English, Hindi, Arabic, Spanish)" },
  { value: "english", label: "English (eng)" },
  { value: "bangla", label: "Bengali / Bangla (ben)" },
  { value: "hindi", label: "Hindi (hin)" },
  { value: "arabic", label: "Arabic (ara)" },
  { value: "spanish", label: "Spanish (spa)" },
  { value: "ben+eng", label: "Bengali + English" },
];

export default function HomePage() {
  const [theme, setTheme] = useState("light");
  const [token, setToken] = useState(null);
  const [userEmail, setUserEmail] = useState("");
  const [authTab, setAuthTab] = useState("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authError, setAuthError] = useState("");
  const [authLoading, setAuthLoading] = useState(false);

  const [docs, setDocs] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [pages, setPages] = useState([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [language, setLanguage] = useState("auto");
  const [dragging, setDragging] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [dashError, setDashError] = useState("");
  const [loadingDocs, setLoadingDocs] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    const savedTheme = localStorage.getItem("pdftext_theme") || "light";
    setTheme(savedTheme);
    document.documentElement.setAttribute("data-theme", savedTheme);

    const savedToken = localStorage.getItem("pdftext_token");
    const savedEmail = localStorage.getItem("pdftext_email") || "";
    if (savedToken) {
      setToken(savedToken);
      setUserEmail(savedEmail);
    }
  }, []);

  const toggleTheme = () => {
    const next = theme === "light" ? "dark" : "light";
    setTheme(next);
    localStorage.setItem("pdftext_theme", next);
    document.documentElement.setAttribute("data-theme", next);
  };

  const refreshDocuments = async (activeToken = token) => {
    if (!activeToken) return;
    setLoadingDocs(true);
    try {
      const data = await listDocuments(activeToken);
      setDocs(data.documents || []);
      setDashError("");
    } catch (err) {
      if (err.message.toLowerCase().includes("token") || err.message.includes("401")) {
        handleLogout();
      } else {
        setDashError(err.message);
      }
    } finally {
      setLoadingDocs(false);
    }
  };

  useEffect(() => {
    if (token) {
      refreshDocuments(token);
    }
  }, [token]);

  // Poll active documents while queued or processing
  useEffect(() => {
    if (!token) return;
    const active = docs.filter((d) => d.status === "queued" || d.status === "processing");
    if (active.length === 0) return;

    const timer = setInterval(async () => {
      try {
        const updates = await Promise.all(active.map((d) => getDocument(d.id, token)));
        setDocs((prev) =>
          prev.map((d) => updates.find((u) => u.id === d.id) || d)
        );
        if (selectedId && updates.some((u) => u.id === selectedId && u.status === "completed")) {
          loadText(selectedId);
        }
      } catch {}
    }, 1500);
    return () => clearInterval(timer);
  }, [docs, token, selectedId]);

  const loadText = async (docId) => {
    if (!token) return;
    try {
      const data = await getDocumentText(docId, token);
      setPages(data.pages || []);
      setCurrentPage(1);
    } catch (err) {
      setDashError(err.message);
    }
  };

  const handleSelectDoc = (doc) => {
    setSelectedId(doc.id);
    setPages([]);
    setCurrentPage(1);
    loadText(doc.id);
  };

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    setAuthError("");
    setAuthLoading(true);
    try {
      if (authTab === "register") {
        await registerUser(email, password);
      }
      const res = await loginUser(email, password);
      localStorage.setItem("pdftext_token", res.access_token);
      localStorage.setItem("pdftext_email", email);
      setToken(res.access_token);
      setUserEmail(email);
      setPassword("");
    } catch (err) {
      setAuthError(err.message);
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    localStorage.removeItem("pdftext_token");
    localStorage.removeItem("pdftext_email");
    setToken(null);
    setUserEmail("");
    setDocs([]);
    setSelectedId(null);
    setPages([]);
  };

  const handleFiles = async (fileList) => {
    const file = fileList?.[0];
    if (!file || !token) return;
    setDashError("");
    setUploadProgress(0);
    try {
      const res = await uploadDocument(file, language, token, setUploadProgress);
      await refreshDocuments(token);
      setSelectedId(res.id);
      loadText(res.id);
    } catch (err) {
      setDashError(err.message);
    } finally {
      setUploadProgress(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (docId) => {
    try {
      await deleteDocument(docId, token);
      setDocs((prev) => prev.filter((d) => d.id !== docId));
      if (selectedId === docId) {
        setSelectedId(null);
        setPages([]);
      }
    } catch (err) {
      setDashError(err.message);
    }
  };

  const selectedDoc = docs.find((d) => d.id === selectedId) || null;
  const activePageObj = pages.find((p) => p.page === currentPage) || pages[0] || null;

  return (
    <>
      <header className="topbar">
        <div className="container topbar-inner">
          <span className="brand">PDFText Pro</span>
          <div className="row">
            <button className="btn btn-sm" onClick={toggleTheme} type="button">
              {theme === "light" ? "Dark Mode" : "Light Mode"}
            </button>
            {token && (
              <>
                <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                  {userEmail}
                </span>
                <button className="btn btn-sm" onClick={handleLogout} type="button">
                  Logout
                </button>
              </>
            )}
          </div>
        </div>
      </header>

      <main className="container">
        {!token ? (
          <section className="landing-grid">
            <div>
              <h1 className="hero-title">
                Extract text from digital and scanned multilingual PDFs.
              </h1>
              <p className="hero-sub">
                Built for large documents (1,000–10,000+ pages) with automatic OCR
                fallback, batch checkpointing, and Unicode preservation.
              </p>
              <ul className="feature-list">
                <li>
                  <strong>Multilingual OCR:</strong> Bengali, English, Hindi, Arabic, and Spanish.
                </li>
                <li>
                  <strong>Hybrid Extraction:</strong> Fast digital text extraction with automatic Tesseract OCR on scanned pages.
                </li>
                <li>
                  <strong>Resilient Processing:</strong> Batch checkpoints, resume support, and per-page error recovery.
                </li>
                <li>
                  <strong>Private Workspace:</strong> Authenticated access, SHA-256 deduplication, and clean TXT export.
                </li>
              </ul>
            </div>

            <div className="panel">
              <div className="tabs">
                <button
                  type="button"
                  className={`tab ${authTab === "login" ? "active" : ""}`}
                  onClick={() => { setAuthTab("login"); setAuthError(""); }}
                >
                  Sign In
                </button>
                <button
                  type="button"
                  className={`tab ${authTab === "register" ? "active" : ""}`}
                  onClick={() => { setAuthTab("register"); setAuthError(""); }}
                >
                  Create Account
                </button>
              </div>

              {authError && <div className="alert">{authError}</div>}

              <form onSubmit={handleAuthSubmit} className="form-stack">
                <div>
                  <label className="label" htmlFor="email">Email</label>
                  <input
                    id="email"
                    type="email"
                    className="input"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
                <div>
                  <label className="label" htmlFor="password">Password</label>
                  <input
                    id="password"
                    type="password"
                    className="input"
                    minLength={8}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
                <button
                  type="submit"
                  className="btn btn-primary"
                  disabled={authLoading}
                >
                  {authLoading
                    ? "Please wait..."
                    : authTab === "login"
                    ? "Sign In"
                    : "Create Account"}
                </button>
              </form>
            </div>
          </section>
        ) : (
          <section className="dashboard">
            {dashError && <div className="alert">{dashError}</div>}

            <div className="panel">
              <div
                className={`dropzone ${dragging ? "dragging" : ""}`}
                onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
                onDragLeave={() => setDragging(false)}
                onDrop={(e) => {
                  e.preventDefault();
                  setDragging(false);
                  handleFiles(e.dataTransfer.files);
                }}
                onClick={() => fileInputRef.current?.click()}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,application/pdf"
                  style={{ display: "none" }}
                  onChange={(e) => handleFiles(e.target.files)}
                />
                <p style={{ fontWeight: 500 }}>
                  Drop a PDF here or click to browse
                </p>
                <p style={{ fontSize: "0.82rem", color: "var(--text-muted)", marginTop: 4 }}>
                  Supports digital and scanned PDFs
                </p>
              </div>

              <div className="upload-controls">
                <div style={{ minWidth: 200, flex: 1 }}>
                  <label className="label" htmlFor="ocr-lang">OCR Language</label>
                  <select
                    id="ocr-lang"
                    className="select"
                    value={language}
                    onChange={(e) => setLanguage(e.target.value)}
                  >
                    {LANGUAGES.map((l) => (
                      <option key={l.value} value={l.value}>{l.label}</option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  className="btn"
                  onClick={() => refreshDocuments()}
                  disabled={loadingDocs}
                >
                  {loadingDocs ? "Refreshing..." : "Refresh"}
                </button>
              </div>

              {uploadProgress !== null && (
                <div style={{ marginTop: 12 }}>
                  <div style={{ fontSize: "0.82rem", color: "var(--text-muted)" }}>
                    Uploading... {uploadProgress}%
                  </div>
                  <div className="progress-track">
                    <div className="progress-fill" style={{ width: `${uploadProgress}%` }} />
                  </div>
                </div>
              )}
            </div>

            <div className="workspace">
              <div className="panel">
                <h2 style={{ fontSize: "1rem", marginBottom: 12 }}>
                  Documents ({docs.length})
                </h2>
                {docs.length === 0 ? (
                  <p style={{ fontSize: "0.88rem", color: "var(--text-muted)" }}>
                    No documents uploaded yet.
                  </p>
                ) : (
                  <div className="doc-list">
                    {docs.map((doc) => (
                      <div
                        key={doc.id}
                        className={`doc-item ${selectedId === doc.id ? "selected" : ""}`}
                        onClick={() => handleSelectDoc(doc)}
                      >
                        <div className="row" style={{ justifyContent: "space-between" }}>
                          <span className="doc-title">{doc.filename}</span>
                          <span className={`badge ${doc.status}`}>{doc.status}</span>
                        </div>
                        <div className="doc-meta">
                          <span>
                            {doc.completed_pages}/{doc.total_pages || "?"} pages ({Math.round(doc.progress || 0)}%)
                          </span>
                          <span>{doc.language}</span>
                        </div>
                        {(doc.status === "queued" || doc.status === "processing") && (
                          <div className="progress-track">
                            <div
                              className="progress-fill"
                              style={{ width: `${Math.round(doc.progress || 0)}%` }}
                            />
                          </div>
                        )}
                        <div className="row" style={{ marginTop: 10 }}>
                          {doc.status === "failed" && (
                            <button
                              type="button"
                              className="btn btn-sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                resumeDocument(doc.id, token).then(() => refreshDocuments());
                              }}
                            >
                              Resume
                            </button>
                          )}
                          {doc.status === "completed_with_errors" && (
                            <button
                              type="button"
                              className="btn btn-sm"
                              onClick={(e) => {
                                e.stopPropagation();
                                retryFailedPages(doc.id, token).then(() => refreshDocuments());
                              }}
                            >
                              Retry Failed
                            </button>
                          )}
                          <button
                            type="button"
                            className="btn btn-sm btn-danger"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleDelete(doc.id);
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="panel">
                {!selectedDoc ? (
                  <p style={{ color: "var(--text-muted)", fontSize: "0.92rem" }}>
                    Select a document to view extracted text.
                  </p>
                ) : (
                  <>
                    <div
                      className="row"
                      style={{ justifyContent: "space-between", flexWrap: "wrap", marginBottom: 14 }}
                    >
                      <div>
                        <h2 style={{ fontSize: "1.05rem" }}>{selectedDoc.filename}</h2>
                        <p style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                          Status: {selectedDoc.status} · {selectedDoc.completed_pages}/{selectedDoc.total_pages} pages
                        </p>
                      </div>
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        disabled={pages.length === 0}
                        onClick={async () => {
                          setDashError("");
                          try {
                            await downloadDocumentTxt(selectedDoc.id, selectedDoc.filename, token);
                          } catch (err) {
                            setDashError(err.message);
                          }
                        }}
                      >
                        Download .TXT
                      </button>
                    </div>

                    {selectedDoc.error && (
                      <div className="alert">{selectedDoc.error}</div>
                    )}

                    {pages.length > 0 && (
                      <div
                        className="row"
                        style={{ justifyContent: "space-between", marginBottom: 10 }}
                      >
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={currentPage <= 1}
                          onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                        >
                          Previous
                        </button>
                        <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>
                          Page {activePageObj?.page || 1} of {pages.length}
                        </span>
                        <button
                          type="button"
                          className="btn btn-sm"
                          disabled={currentPage >= pages.length}
                          onClick={() => setCurrentPage((p) => Math.min(pages.length, p + 1))}
                        >
                          Next
                        </button>
                      </div>
                    )}

                    <div className="viewer-text" dir="auto">
                      {activePageObj
                        ? activePageObj.text || "(No text extracted on this page)"
                        : selectedDoc.status === "queued" || selectedDoc.status === "processing"
                        ? "Processing document..."
                        : "No extracted text available."}
                    </div>
                  </>
                )}
              </div>
            </div>
          </section>
        )}
      </main>
    </>
  );
}
