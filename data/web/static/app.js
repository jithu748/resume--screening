// data/web/static/app.js
// Client JS with session-based upload support for privacy/security

document.addEventListener('DOMContentLoaded', () => {
  // Session storage for uploaded files
  let currentSessionId = null;
  let sessionStatusTimer = null;

  // Elements (matching IDs from the template)
  const runBtn = document.getElementById('runBtn');
  const resetBtn = document.getElementById('resetBtn');
  const resultsEl = document.getElementById('results');

  const fileInput = document.getElementById('file_input');
  const resumeFake = document.getElementById('resume-fake');
  const browseBtn = document.getElementById('browseBtn');
  const clearBtn = document.getElementById('clearBtn');
  const inlineUploadBtn = document.getElementById('inlineUploadBtn');

  const sessionIdEl = document.getElementById('session-id');
  const sessionFilesEl = document.getElementById('session-files');
  const endSessionBtn = document.getElementById('endSessionBtn');

  const zipInput = document.getElementById('zip_input');
  const zipFake = document.getElementById('zip-fake');
  const zipBrowse = document.getElementById('zipBrowse');
  const zipClear = document.getElementById('zipClear');

  // helper to format percent-like scores (keeps old behavior)
  function formatScore(s) {
    if (s === null || s === undefined) return '-';
    if (typeof s === 'string') return s;
    if (typeof s === 'number' && isFinite(s)) {
      if (s >= 0 && s <= 1) return (s * 100).toFixed(2) + '%';
      if (s > 1 && s <= 100) return s.toFixed(2) + '%';
      return s.toFixed(3);
    }
    return String(s);
  }

  // ---- refreshServerList: deprecated - now shows session status ----
  async function refreshServerList() {
    if (!currentSessionId) {
      resumeFake.innerHTML = '<em>No file selected</em>';
      if (sessionIdEl) sessionIdEl.textContent = 'No session';
      if (sessionFilesEl) sessionFilesEl.innerHTML = '<em>No files</em>';
      if (endSessionBtn) { endSessionBtn.disabled = true; }
      return;
    }
    try {
      const r = await fetch(`/api/session_status?session_id=${encodeURIComponent(currentSessionId)}`);
      const data = await r.json();
      if (!r.ok) {
        resumeFake.innerHTML = '<em>Session expired - please re-upload files</em>';
        currentSessionId = null;
        if (sessionIdEl) sessionIdEl.textContent = 'No session';
        if (sessionFilesEl) sessionFilesEl.innerHTML = '<em>No files</em>';
        if (endSessionBtn) { endSessionBtn.disabled = true; }
        return;
      }
      const files = data.files || [];
      const items = files.map((f,i) => `<li><strong>${i+1}.</strong> ${f}</li>`).join('');
      const ttl = typeof data.expires_in === 'number' ? Math.max(0, Math.floor(data.expires_in/60)) : null;
      const ttlMsg = ttl !== null ? ` (expires in ~${ttl} min)` : '';
      resumeFake.innerHTML = `<div style="color: green;">✓ ${files.length} files uploaded${ttlMsg}</div>` +
        `<ol style="margin:0;padding-left:20px">${items}</ol>`;
      if (sessionIdEl) sessionIdEl.textContent = `Session: ${currentSessionId.substring(0, 8)}`;
      if (sessionFilesEl) sessionFilesEl.innerHTML = `<strong>${files.length}</strong> file(s): <ul style="margin:6px 0 0 18px">${files.map(f=>`<li>${f}</li>`).join('')}</ul>`;
      if (endSessionBtn) { endSessionBtn.disabled = false; }
    } catch (e) {
      resumeFake.innerHTML = '<em>Unable to load session status</em>';
    }
  }

  // render results table (keeps old layout)
  function renderResults(rows) {
    resultsEl.innerHTML = '';
    if (!rows || rows.length === 0) {
      resultsEl.innerHTML = '<p class="muted">No matches found.</p>';
      return;
    }
    const table = document.createElement('table');
    table.className = 'table';
    const thead = document.createElement('thead');
    thead.innerHTML = '<tr><th>Use-case</th><th>File</th><th>Score</th></tr>';
    table.appendChild(thead);
    const tbody = document.createElement('tbody');
    rows.forEach(r => {
      const tr = document.createElement('tr');
      const useTd = document.createElement('td');
      useTd.textContent = r.usecase || 'For interview';
      const fileTd = document.createElement('td');
      fileTd.textContent = r.file || r.filename || '—';
      const scoreTd = document.createElement('td');
      scoreTd.className = 'score';
      const s = (typeof r.score === 'number' || typeof r.score === 'string') ? r.score : (r.score && r.score.value) || r.score;
      scoreTd.textContent = formatScore(s);
      tr.appendChild(useTd);
      tr.appendChild(fileTd);
      tr.appendChild(scoreTd);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    resultsEl.appendChild(table);
  }

  // RUN button (calls /api/score with session_id)
  if (runBtn) {
    runBtn.addEventListener('click', async () => {
      const job_title = document.getElementById('job-title')?.value.trim() || '';
      const skills = document.getElementById('skills')?.value.trim() || '';
      const top_n = parseInt(document.getElementById('top-n')?.value || '5', 10) || 5;
      
      if (!skills && !job_title) {
        alert('Please add job title or skills');
        return;
      }

      if (!currentSessionId) {
        alert('Please upload resumes first!');
        return;
      }

      runBtn.disabled = true;
      runBtn.textContent = 'Running…';
      resultsEl.innerHTML = '<p class="muted">Running... please wait.</p>';
      
      try {
        const resp = await fetch('/api/score', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            job_title,
            skills,
            top_n,
            session_id: currentSessionId
          })
        });
        const data = await resp.json();
        if (!resp.ok) {
          resultsEl.innerHTML = `<p class="muted">Error: ${data.error || data.message || 'server'}</p>`;
          // Session expired - clear it
          if (data.error && data.error.includes('session')) {
            currentSessionId = null;
            resumeFake.innerHTML = '<em>Session expired - please re-upload files</em>';
          }
          return;
        }
        
        // Success! Session remains active until TTL expiry (sliding)
        await refreshServerList();
        
        const rows = data.results ?? data.rows ?? [];
        const normalized = rows.map(r => ({
          file: r.file ?? r.filename ?? r.name,
          score: r.score ?? (Array.isArray(r) ? r[1] : null),
          usecase: r.usecase ?? 'For interview'
        }));
        renderResults(normalized);
      } catch (err) {
        resultsEl.innerHTML = `<p class="muted">Error: ${err.message || err}</p>`;
        console.error(err);
      } finally {
        runBtn.disabled = false;
        runBtn.textContent = 'Run';
      }
    });
  }

  // Reset button (clear form UI and session)
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      document.getElementById('job-title').value = '';
      document.getElementById('skills').value = '';
      document.getElementById('top-n').value = 5;
      fileInput.value = '';
      zipInput.value = '';
      resultsEl.innerHTML = '';
      currentSessionId = null;
      resumeFake.innerHTML = '<em>No file selected</em>';
      zipFake.innerHTML = '<em>No file selected</em>';
    });
  }

  // Show filenames (numbered) in fake box
  function showFilesList(input, fakeBox) {
    if (!input.files || input.files.length === 0) {
      fakeBox.innerHTML = '<em>No file selected</em>';
      return;
    }
    const items = Array.from(input.files).map((f,i) =>
      `<li><strong>${i+1}.</strong> ${f.name}</li>`).join('');
    fakeBox.innerHTML = `<ol style="margin:0;padding-left:20px">${items}</ol>`;
  }

  // File input handlers
  if (fileInput) {
    browseBtn?.addEventListener('click', () => fileInput.click());
    clearBtn?.addEventListener('click', () => {
      fileInput.value = '';
      showFilesList(fileInput, resumeFake);
    });
    fileInput.addEventListener('change', () => {
      showFilesList(fileInput, resumeFake);
      // show inline upload button (if present)
      const inlineUpload = document.getElementById('inline-upload');
      if (inlineUpload) inlineUpload.removeAttribute('aria-hidden');
    });
  }

  // Inline upload handler (uploads files and stores session_id)
  if (inlineUploadBtn) {
    inlineUploadBtn.addEventListener('click', async () => {
      if (!fileInput.files || fileInput.files.length === 0) {
        alert('No files selected');
        return;
      }
      
      const form = new FormData();
      for (let i = 0; i < fileInput.files.length; i++) {
        form.append('files', fileInput.files[i]);
      }
      if (currentSessionId) {
        form.append('session_id', currentSessionId);
      }
      
      inlineUploadBtn.disabled = true;
      inlineUploadBtn.textContent = 'Uploading…';
      
      try {
        const resp = await fetch('/api/upload', { method: 'POST', body: form });
        const data = await resp.json().catch(() => ({}));
        
        if (!resp.ok) {
          alert('Upload failed: ' + (data?.error || data?.message || 'server'));
        } else {
          // Store/refresh session ID and render list of uploaded files
          currentSessionId = data.session_id;
          const files = data.files ?? data.saved ?? [];
          const count = data.count ?? files.length ?? 0;
          alert(`Uploaded ${count} files. Session ${currentSessionId.substring(0, 8)} created/updated.`);
          fileInput.value = '';
          const items = files.map((f,i) => `<li><strong>${i+1}.</strong> ${f}</li>`).join('');
          resumeFake.innerHTML = `<div style=\"color: green;\">✓ ${count} files uploaded (session active)</div>` +
            `<ol style=\"margin:0;padding-left:20px\">${items}</ol>`;
          if (sessionIdEl) sessionIdEl.textContent = `Session: ${currentSessionId.substring(0, 8)}`;
          if (sessionFilesEl) sessionFilesEl.innerHTML = `<strong>${files.length}</strong> file(s): <ul style=\"margin:6px 0 0 18px\">${files.map(f=>`<li>${f}</li>`).join('')}</ul>`;
          if (endSessionBtn) { endSessionBtn.disabled = false; }
          
          // Hide inline upload button
          const inline = document.getElementById('inline-upload');
          if (inline) inline.setAttribute('aria-hidden', 'true');
        }
      } catch (err) {
        alert('Upload error: ' + err.message);
      } finally {
        inlineUploadBtn.disabled = false;
        inlineUploadBtn.textContent = 'Upload';
      }
    });
  }

  // ZIP controls
  if (zipInput) {
    zipBrowse?.addEventListener('click', () => zipInput.click());
    zipClear?.addEventListener('click', () => {
      zipInput.value = '';
      zipFake.innerHTML = '<em>No file selected</em>';
    });
    zipInput.addEventListener('change', () => showFilesList(zipInput, zipFake));
  }

  // Drag & drop UX for wrapper elements
  ['resume-wrapper','zip-wrapper'].forEach(id => {
    const el = document.getElementById(id);
    if (!el) return;
    el.addEventListener('dragover', e => { e.preventDefault(); el.classList.add('over'); });
    el.addEventListener('dragleave', e => { el.classList.remove('over'); });
    el.addEventListener('drop', e => {
      e.preventDefault(); el.classList.remove('over');
      const files = e.dataTransfer.files;
      if (!files || !files.length) return;
      if (id === 'resume-wrapper') {
        fileInput.files = files;
        showFilesList(fileInput, resumeFake);
        const inline = document.getElementById('inline-upload'); if (inline) inline.removeAttribute('aria-hidden');
      } else {
        zipInput.files = files;
        showFilesList(zipInput, zipFake);
      }
    });
  });

  // On load, show initial empty state
  refreshServerList();

  // End Session handler
  if (endSessionBtn) {
    endSessionBtn.addEventListener('click', async () => {
      if (!currentSessionId) return;
      endSessionBtn.disabled = true;
      try {
        // Prefer POST /api/end_session for manual end
        const resp = await fetch('/api/end_session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ session_id: currentSessionId })
        });
        if (!resp.ok) {
          // Fallback to DELETE endpoint if needed
          await fetch(`/api/session?session_id=${encodeURIComponent(currentSessionId)}`, { method: 'DELETE' });
        } else {
          await resp.json().catch(()=>({}));
        }
      } catch {}
      currentSessionId = null;
      resumeFake.innerHTML = '<em>Session ended. Please re-upload files.</em>';
      if (sessionIdEl) sessionIdEl.textContent = 'No session';
      if (sessionFilesEl) sessionFilesEl.innerHTML = '<em>No files</em>';
      endSessionBtn.disabled = true;
    });
  }
});
