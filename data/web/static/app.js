document.addEventListener('DOMContentLoaded', () => {
  const runBtn = document.getElementById('runBtn');
  const clearBtn = document.getElementById('clearBtn');
  const resultsEl = document.getElementById('results');

  runBtn.addEventListener('click', async () => {
    const job_title = document.getElementById('job_title').value.trim();
    const skills = document.getElementById('skills').value.trim();
    const top_n = document.getElementById('top_n').value || 5;

    resultsEl.innerHTML = '<p class="muted">Running... please wait.</p>';

    try {
      const resp = await fetch('/api/score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ job_title, skills, top_n })
      });

      const data = await resp.json();
      if (!resp.ok) {
        resultsEl.innerHTML = `<p class="muted">Error: ${data.error || 'Unknown'}</p>`;
        return;
      }

      const rows = data.results;
      if (!rows || rows.length === 0) {
        resultsEl.innerHTML = '<p class="muted">No matches found.</p>';
        return;
      }

      let html = '<table class="table"><thead><tr><th>Use-case</th><th>File</th><th>Score</th></tr></thead><tbody>';
      for (const r of rows) {
        // Use-case column shows a short professional label for interviewers
        html += `<tr><td>For interview</td><td>${r.file}</td><td class="score">${r.score.toFixed ? r.score.toFixed(3) : r.score}</td></tr>`;
      }
      html += '</tbody></table>';
      resultsEl.innerHTML = html;

    } catch (err) {
      resultsEl.innerHTML = `<p class="muted">Error: ${err.message}</p>`;
    }
  });

  clearBtn.addEventListener('click', () => {
    document.getElementById('job_title').value = '';
    document.getElementById('skills').value = '';
    document.getElementById('top_n').value = 5;
    document.getElementById('results').innerHTML = '';
  });

  // Upload handler
  const uploadBtn = document.getElementById('uploadBtn');
  const fileInput = document.getElementById('file_input');
  uploadBtn.addEventListener('click', async () => {
    const files = fileInput.files;
    if (!files || files.length === 0) {
      alert('Select one or more resume files to upload.');
      return;
    }
    const form = new FormData();
    for (let i = 0; i < files.length; i++) form.append('files', files[i]);
    uploadBtn.disabled = true;
    uploadBtn.textContent = 'Uploading...';
    try {
      const resp = await fetch('/api/upload', { method: 'POST', body: form });
      const data = await resp.json();
      if (!resp.ok) {
        alert('Upload failed: ' + (data.error || 'unknown'));
      } else {
        alert(`Uploaded ${data.count} files: ` + data.saved.join(', '));
      }
    } catch (err) {
      alert('Upload error: ' + err.message);
    } finally {
      uploadBtn.disabled = false;
      uploadBtn.textContent = 'Upload';
      fileInput.value = '';
    }
  });

  // ZIP upload handler (single large archive of resumes)
  const uploadZipBtn = document.getElementById('uploadZipBtn');
  const zipInput = document.getElementById('zip_input');
  uploadZipBtn.addEventListener('click', async () => {
    const f = zipInput.files && zipInput.files[0];
    if (!f) {
      alert('Select a ZIP file containing resumes.');
      return;
    }
    if (!f.name.toLowerCase().endsWith('.zip')) {
      alert('Please select a .zip file');
      return;
    }
    const form = new FormData();
    form.append('file', f);
    uploadZipBtn.disabled = true;
    uploadZipBtn.textContent = 'Uploading...';
    try {
      const resp = await fetch('/api/upload-zip', { method: 'POST', body: form });
      const data = await resp.json();
      if (!resp.ok) {
        alert('ZIP upload failed: ' + (data.error || 'unknown'));
      } else {
        alert(`Extracted ${data.count} files: ` + data.saved.join(', '));
      }
    } catch (err) {
      alert('Upload error: ' + err.message);
    } finally {
      uploadZipBtn.disabled = false;
      uploadZipBtn.textContent = 'Upload ZIP';
      zipInput.value = '';
    }
  });

});