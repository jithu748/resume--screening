// web/static/app.js - updated to support inline upload + numbered filenames + dark mode
document.addEventListener('DOMContentLoaded', () => {
  // Elements (matching IDs from the template)
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

  // RUN button (calls /api/score)
  if (runBtn) {
    runBtn.addEventListener('click', async () => {
      const job_title = document.getElementById('job-title')?.value.trim() || '';
      const skills = document.getElementById('skills')?.value.trim() || '';
      const top_n = parseInt(document.getElementById('top-n')?.value || '5', 10) || 5;
      if (!skills && !job_title) { alert('Please add job title or skills'); return; }

      runBtn.disabled = true;
      runBtn.textContent = 'Running…';
      resultsEl.innerHTML = '<p class="muted">Running... please wait.</p>';
      try {
        const resp = await fetch('/api/score', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ job_title, skills, top_n })
        });
        const data = await resp.json();
        if (!resp.ok) {
          resultsEl.innerHTML = `<p class="muted">Error: ${data.error || data.message || 'server'}</p>`;
          return;
        }
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

  // Reset button (clear form UI only)
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      document.getElementById('job-title').value = '';
      document.getElementById('skills').value = '';
      document.getElementById('top-n').value = 5;
      fileInput.value = '';
      resumeFake.innerHTML = '<em>No file selected</em>';
      zipInput.value = '';
      zipFake.innerHTML = '<em>No file selected</em>';
      resultsEl.innerHTML = '';
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

  // Inline upload handler (uploads files selected in file_input to /api/upload)
  if (inlineUploadBtn) {
    inlineUploadBtn.addEventListener('click', async () => {
      if (!fileInput.files || fileInput.files.length === 0) { alert('No files selected'); return; }
      const form = new FormData();
      for (let i=0;i<fileInput.files.length;i++) form.append('files', fileInput.files[i]);
      inlineUploadBtn.disabled = true;
      inlineUploadBtn.textContent = 'Uploading…';
      try {
        const resp = await fetch('/api/upload', { method: 'POST', body: form });
        const data = await resp.json().catch(()=>({}));
        if (!resp.ok) {
          alert('Upload failed: ' + (data?.error || data?.message || 'server'));
        } else {
          alert(`Uploaded ${data.count ?? data.saved?.length ?? 0} files`);
          fileInput.value = '';
          resumeFake.innerHTML = '<em>Uploaded ✓</em>';
          // hide inline upload again
          const inline = document.getElementById('inline-upload');
          if (inline) inline.setAttribute('aria-hidden','true');
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

  // ---------------------------
  // Dark mode toggle (persistent)
  // ---------------------------
  (function () {
    const storageKey = 'theme-preference';
    const htmlEl = document.documentElement;
    const btn = document.getElementById('themeToggle');
    const iconSun = document.getElementById('iconSun');
    const iconMoon = document.getElementById('iconMoon');

    function applyTheme(theme) {
      if (theme === 'dark') {
        htmlEl.classList.add('dark');
        if (iconMoon) iconMoon.style.display = 'inline-block';
        if (iconSun) iconSun.style.display = 'none';
      } else {
        htmlEl.classList.remove('dark');
        if (iconMoon) iconMoon.style.display = 'none';
        if (iconSun) iconSun.style.display = 'inline-block';
      }
    }

    // initial: saved > system > light
    const saved = localStorage.getItem(storageKey);
    if (saved === 'dark' || saved === 'light') {
      applyTheme(saved);
    } else {
      const preferDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      applyTheme(preferDark ? 'dark' : 'light');
    }

    if (!btn) return;

    btn.addEventListener('click', () => {
      const isDark = htmlEl.classList.contains('dark');
      const newTheme = isDark ? 'light' : 'dark';
      applyTheme(newTheme);
      localStorage.setItem(storageKey, newTheme);
    });

    // listen to system changes if user hasn't explicitly chosen
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        const saved = localStorage.getItem(storageKey);
        if (saved) return;
        applyTheme(e.matches ? 'dark' : 'light');
      });
    }
  })();

});
