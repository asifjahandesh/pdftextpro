const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function request(path, options = {}, token = null) {
  const headers = { ...(options.headers || {}) };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const data = await res.json();
      if (data.detail) detail = data.detail;
    } catch {}
    throw new Error(detail);
  }
  return res.json();
}

export function registerUser(email, password) {
  return request("/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function loginUser(email, password) {
  return request("/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
}

export function listDocuments(token) {
  return request("/documents", {}, token);
}

export function getDocument(id, token) {
  return request(`/documents/${id}`, {}, token);
}

export function getDocumentText(id, token, page = null) {
  const qs = page !== null ? `?page=${page}` : "";
  return request(`/documents/${id}/text${qs}`, {}, token);
}

export function deleteDocument(id, token) {
  return request(`/documents/${id}`, { method: "DELETE" }, token);
}

export function resumeDocument(id, token) {
  return request(`/documents/${id}/resume`, { method: "POST" }, token);
}

export function retryFailedPages(id, token) {
  return request(`/documents/${id}/retry-failed`, { method: "POST" }, token);
}

export async function downloadDocumentTxt(id, filename, token) {
  const res = await fetch(`${API_BASE}/documents/${id}/download`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(`Download failed (${res.status})`);
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${filename.replace(/\.pdf$/i, "")}.txt`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function uploadDocument(file, language, token, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/documents?language=${encodeURIComponent(language)}`);
    xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    };
    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText || "{}");
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(data);
        } else {
          reject(new Error(data.detail || `Upload failed (${xhr.status})`));
        }
      } catch {
        reject(new Error(`Upload failed (${xhr.status})`));
      }
    };
    xhr.onerror = () => reject(new Error("Network error during upload."));
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
