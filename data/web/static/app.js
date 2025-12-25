// data/web/static/app.js
// Client JS with session-based upload support for privacy/security

document.addEventListener('DOMContentLoaded', () => {

  /* =========================
     DARK MODE TOGGLE
  ========================== */
  const themeToggle = document.getElementById('themeToggle');
  const iconLabel = document.getElementById('iconLabel');
  const htmlElement = document.documentElement;

  function applyTheme(isDark) {
    if (isDark) {
      htmlElement.classList.add('dark');
      if (iconLabel) iconLabel.textContent = '☀️';
    } else {
      htmlElement.classList.remove('dark');
      if (iconLabel) iconLabel.textContent = '🌙';
    }
    localStorage.setItem('theme-preference', isDark ? 'dark' : 'light');
  }

  function initTheme() {
    const saved = localStorage.getItem('theme-preference');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(saved ? saved === 'dark' : prefersDark);
  }

  themeToggle?.addEventListener('click', () => {
    applyTheme(!htmlElement.classList.contains('dark'));
  });

  initTheme();

  /* =========================
     STATE
  ========================== */
  let currentSessionId = null;

  /* =========================
     ELEMENTS
  ========================== */
  const runBtn = document.getElementById('runBtn');
  const resetBtn = document.getElementById('resetBtn');
  const resultsEl = document.getElementById('results');

  const fileInput = document.getElementById('file_input');
  const resumeFake = document.getElementById('resume-fake');
  const browseBtn = document.getElementById('browseBtn');
  const clearBtn = document.getElementById('clearBtn');
  const inlineUploadBtn = document.getElementById('inlineUploadBtn');

  const zipInput = document.getElementById('zip_input');
  const zipFake = document.getElementById('zip-fake');
  const zipBrowse = document.getElementById('zipBrowse');
  const zipClear = document.getElementById('zipClear');

  /* =========================
     HELPERS
  ========================== */
  function formatScore(s) {
    if (s === null || s === undefined) return '-';
    if (typeof s === 'number') return (s <= 1 ? s * 100 : s).toFixed(2) + '%';
    return s;
  }

  function showFilesList(input, fakeBox) {
    if (!input.files || input.files.length === 0) {
      fakeBox.innerHTML = '<em>No file selected</em>';
      return;
    }
    const items = Array.from(input.files)
      .map((f, i) => `<li><strong>${i + 1}.</strong> ${f.name}</li>`)
      .join('');
    fakeBox.innerHTML = `<ol style="margin:0;padding-left:20px">${items}</ol>`;
  }

  /* =========================
     RESULTS RENDER (FIXED)
  ========================== */
  function renderResults(rows) {
    resultsEl.innerHTML = '';

    if (!rows || rows.length === 0) {
      resultsEl.innerHTML = '<p class="muted">No matches found.</p>';
      return;
    }

    const table = document.createElement('table');
    table.className = 'table';

    table.innerHTML = `
      <thead>
        <tr>
          <th>Use-case</th>
          <th>File</th>
          <th>Score</th>
          <th>Action</th>
        </tr>
      </thead>
    `;

    const tbody = document.createElement('tbody');

    rows.forEach(r => {
      const tr = document.createElement('tr');
      const filename = r.file || r.filename || '—';

      /* Use-case */
      const tdUse = document.createElement('td');
      tdUse.textContent = r.usecase || 'For interview';

      /* File (CLICKABLE LINK) */
      const tdFile = document.createElement('td');
      const fileLink = document.createElement('a');
      fileLink.textContent = filename;
      fileLink.href = `/view/${encodeURIComponent(currentSessionId)}/${encodeURIComponent(filename)}`;
      fileLink.target = '_blank';
      fileLink.className = 'result-file-link';
      tdFile.appendChild(fileLink);

      /* Score */
      const tdScore = document.createElement('td');
      tdScore.textContent = formatScore(r.score);

      /* Action (VIEW BUTTON) */
      const tdAction = document.createElement('td');
      const viewBtn = document.createElement('a');
      viewBtn.textContent = 'View';
      viewBtn.href = fileLink.href;
      viewBtn.target = '_blank';
      viewBtn.className = 'view-btn';
      tdAction.appendChild(viewBtn);

      tr.appendChild(tdUse);
      tr.appendChild(tdFile);
      tr.appendChild(tdScore);
      tr.appendChild(tdAction);

      tbody.appendChild(tr);
    });

    table.appendChild(tbody);
    resultsEl.appendChild(table);
  }

  /* =========================
     RUN SCORING
  ========================== */
  runBtn?.addEventListener('click', async () => {
    const job_title = document.getElementById('job-title').value.trim();
    const skills = document.getElementById('skills').value.trim();
    const top_n = parseInt(document.getElementById('top-n').value, 10) || 5;

    if (!job_title && !skills) {
      alert('Please add job title or skills');
      return;
    }
    if (!currentSessionId) {
      alert('Please upload resumes first');
      return;
    }

    runBtn.disabled = true;
    runBtn.textContent = 'Running…';
    resultsEl.innerHTML = '<p class="muted">Running… please wait.</p>';

    try {
      const res = await fetch('/api/score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_title, skills, top_n, session_id: currentSessionId })
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Server error');

      const rows = (data.results || []).map(r => ({
        file: r.file || r.filename,
        score: r.score,
        usecase: r.usecase || 'For interview'
      }));

      renderResults(rows);

    } catch (e) {
      resultsEl.innerHTML = `<p class="muted">Error: ${e.message}</p>`;
    } finally {
      runBtn.disabled = false;
      runBtn.textContent = 'Run';
    }
  });

  /* =========================
     RESET
  ========================== */
  resetBtn?.addEventListener('click', () => {
    document.getElementById('job-title').value = '';
    document.getElementById('skills').value = '';
    document.getElementById('top-n').value = 5;
    fileInput.value = '';
    zipInput.value = '';
    resultsEl.innerHTML = '';
    resumeFake.innerHTML = '<em>No file selected</em>';
    zipFake.innerHTML = '<em>No file selected</em>';
    currentSessionId = null;
  });

  /* =========================
     FILE UPLOAD
  ========================== */
  browseBtn?.addEventListener('click', () => fileInput.click());
  clearBtn?.addEventListener('click', () => {
    fileInput.value = '';
    showFilesList(fileInput, resumeFake);
  });

  fileInput?.addEventListener('change', () => {
    showFilesList(fileInput, resumeFake);
    document.getElementById('inline-upload')?.removeAttribute('aria-hidden');
  });

  inlineUploadBtn?.addEventListener('click', async () => {
    if (!fileInput.files.length) return alert('No files selected');

    const form = new FormData();
    Array.from(fileInput.files).forEach(f => form.append('files', f));

    inlineUploadBtn.disabled = true;
    inlineUploadBtn.textContent = 'Uploading…';

    try {
      const res = await fetch('/api/upload', { method: 'POST', body: form });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Upload failed');

      currentSessionId = data.session_id;
      const files = data.files || [];
      const list = files.map((f, i) => `<li><strong>${i + 1}.</strong> ${f}</li>`).join('');

      resumeFake.innerHTML =
        `<div style="color:green;">✓ ${files.length} files uploaded</div>` +
        `<ol style="margin:0;padding-left:20px">${list}</ol>`;

      document.getElementById('inline-upload')?.setAttribute('aria-hidden', 'true');
      fileInput.value = '';

    } catch (e) {
      alert(e.message);
    } finally {
      inlineUploadBtn.disabled = false;
      inlineUploadBtn.textContent = 'Upload';
    }
  });

  /* =========================
     ZIP
  ========================== */
  zipBrowse?.addEventListener('click', () => zipInput.click());
  zipClear?.addEventListener('click', () => {
    zipInput.value = '';
    zipFake.innerHTML = '<em>No file selected</em>';
  });
  zipInput?.addEventListener('change', () => showFilesList(zipInput, zipFake));

});
