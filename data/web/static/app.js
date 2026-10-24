// data/web/static/app.js
// Modern Mobile-Friendly UI Control Logic - Refactored for Separate Upload Flows

document.addEventListener('DOMContentLoaded', () => {

  function getCookie(name) {
    const prefix = `${name}=`;
    const cookie = document.cookie.split('; ').find(value => value.startsWith(prefix));
    return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null;
  }

  async function apiFetch(url, options = {}) {
    const request = { ...options, credentials: 'include', headers: { ...(options.headers || {}) } };
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes((request.method || 'GET').toUpperCase())) {
      const csrf = getCookie('resume_csrf');
      if (csrf && !request.headers['X-CSRF-Token']) request.headers['X-CSRF-Token'] = csrf;
    }
    const response = await fetch(url, request);
    if (response.status === 401) {
      setAuthState(null, 'Please sign in to continue.');
      throw new Error('Please sign in to continue.');
    }
    if (response.status === 403) throw new Error('Not authorized or request expired.');
    return response;
  }

  // File Inputs
  const fileInputResumes = document.getElementById('file_input_resumes');
  const fileInputZip = document.getElementById('file_input_zip');

  // File Summaries
  const fileSummaryResumes = document.getElementById('file-summary-resumes');
  const fileCountTextResumes = document.getElementById('file-count-resumes');
  const clearResumesBtn = document.getElementById('clear-resumes-btn');

  const fileSummaryZip = document.getElementById('file-summary-zip');
  const fileCountTextZip = document.getElementById('file-count-zip');
  const clearZipBtn = document.getElementById('clear-zip-btn');

  const analyzeBtn = document.getElementById('analyzeBtn');

  // States
  const loadingState = document.getElementById('loading-state');
  const loadingMessage = document.getElementById('loading-message');
  const resultsContainer = document.getElementById('results-container');
  const resultsList = document.getElementById('results-list');

  let currentSessionId = null;
  const authStatus = document.getElementById('auth-status');
  const logoutBtn = document.getElementById('logout-btn');

  function setAuthState(user, message) {
    const identity = user && (user.email || user.user);
    if (authStatus) authStatus.textContent = message || (user ? `Signed in as ${identity} (${user.role})` : 'Anonymous development mode');
    if (logoutBtn) logoutBtn.classList.toggle('hidden', !user);
  }

  async function loadCurrentUser() {
    try {
      const response = await fetch('/api/auth/me', { credentials: 'include' });
      if (response.ok) setAuthState(await response.json());
      else setAuthState(null, 'Anonymous development mode');
    } catch (_) {
      setAuthState(null, 'Unable to check sign-in status.');
    }
  }

  async function submitAuth(endpoint, body) {
    const response = await apiFetch(endpoint, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || data.error || 'Authentication request failed');
    setAuthState(data);
    showToast('Authentication successful', 'success');
  }

  document.getElementById('login-btn').addEventListener('click', async () => {
    try {
      await submitAuth('/api/auth/login', {
        email: document.getElementById('auth-email').value,
        password: document.getElementById('auth-password').value
      });
    } catch (err) { showToast(err.message, 'error'); }
  });

  document.getElementById('register-btn').addEventListener('click', async () => {
    try {
      await submitAuth('/api/auth/register', {
        email: document.getElementById('auth-email').value,
        password: document.getElementById('auth-password').value,
        agency_name: document.getElementById('auth-agency').value
      });
    } catch (err) { showToast(err.message, 'error'); }
  });

  logoutBtn.addEventListener('click', async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' });
      setAuthState(null, 'Signed out. Anonymous development mode remains available when enabled.');
    } catch (err) { showToast(err.message, 'error'); }
  });

  loadCurrentUser();

  // --- UI feedback: Toast Notifications ---
  function showToast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    requestAnimationFrame(() => toast.classList.add('show'));
    setTimeout(() => {
      toast.classList.remove('show');
      toast.addEventListener('transitionend', () => toast.remove());
    }, 3500);
  }

  // --- Dynamic Loading Messages ---
  let loadInterval;
  function startLoadingAnimations(isMultiple) {
    loadingState.classList.remove('hidden');
    resultsContainer.classList.add('hidden');
    analyzeBtn.disabled = true;

    // Customize messages based on single/multiple
    const messages = isMultiple
      ? ["Uploading batch archive...", "Extracting multiple files...", "Analyzing all resumes...", "Matching skills...", "Ranking candidates..."]
      : ["Uploading document...", "Reading document text...", "Analyzing keywords...", "Generating score..."];

    let i = 0;
    loadingMessage.textContent = messages[0];

    loadInterval = setInterval(() => {
      i = (i + 1) % messages.length;
      loadingMessage.textContent = messages[i];
    }, 1500);
  }

  function stopLoadingAnimations() {
    loadingState.classList.add('hidden');
    clearInterval(loadInterval);
    analyzeBtn.disabled = false;
  }

  // --- Update File Selection UI and Validation ---

  fileInputResumes.addEventListener('change', () => {
    if (fileInputResumes.files && fileInputResumes.files.length > 0) {
      fileCountTextResumes.textContent = fileInputResumes.files.length;
      fileSummaryResumes.classList.remove('hidden');

      // Auto-clear the other input to prevent mix-ups natively
      if (fileInputZip.files.length > 0) {
        fileInputZip.value = '';
        fileSummaryZip.classList.add('hidden');
        showToast("Switched to individual resume upload", "info");
      }
    } else {
      fileSummaryResumes.classList.add('hidden');
    }
  });

  fileInputZip.addEventListener('change', () => {
    if (fileInputZip.files && fileInputZip.files.length > 0) {
      fileCountTextZip.textContent = fileInputZip.files.length;
      fileSummaryZip.classList.remove('hidden');

      // Auto-clear the other input to prevent mix-ups natively
      if (fileInputResumes.files.length > 0) {
        fileInputResumes.value = '';
        fileSummaryResumes.classList.add('hidden');
        showToast("Switched to ZIP batch upload", "info");
      }
    } else {
      fileSummaryZip.classList.add('hidden');
    }
  });

  // Clear Buttons
  clearResumesBtn.addEventListener('click', (e) => {
    e.preventDefault();
    fileInputResumes.value = '';
    fileSummaryResumes.classList.add('hidden');
  });

  clearZipBtn.addEventListener('click', (e) => {
    e.preventDefault();
    fileInputZip.value = '';
    fileSummaryZip.classList.add('hidden');
  });

  // --- Main Analyze Flow ---
  analyzeBtn.addEventListener('click', async () => {
    const jobTitle = document.getElementById('job-title').value.trim();
    const skills = document.getElementById('skills').value.trim();
    const topN = parseInt(document.getElementById('top-n').value) || 5;

    if (!jobTitle && !skills) {
      showToast('Please enter a Target Role or Skills', 'error');
      return;
    }

    const hasResumes = fileInputResumes.files && fileInputResumes.files.length > 0;
    const hasZip = fileInputZip.files && fileInputZip.files.length > 0;

    // Validation Rules
    if (!hasResumes && !hasZip) {
      showToast('Error: Please select either a Resume or a ZIP file to proceed.', 'error');
      return;
    }

    if (hasResumes && hasZip) {
      showToast('Conflict: Please upload EITHER individual resumes OR a ZIP file, not both.', 'error');
      return;
    }

    const isMultiple = hasZip || (hasResumes && fileInputResumes.files.length > 1);
    startLoadingAnimations(isMultiple);

    try {
      // Step 1: Upload Files
      const formData = new FormData();
      let uploadEndpoint = '';

      if (hasZip) {
        uploadEndpoint = '/api/upload-zip';
        formData.append('file', fileInputZip.files[0]);
      } else {
        uploadEndpoint = '/api/upload';
        for (let i = 0; i < fileInputResumes.files.length; i++) {
          formData.append('files', fileInputResumes.files[i]);
        }
      }

      const uploadRes = await apiFetch(uploadEndpoint, { method: 'POST', body: formData });
      const uploadData = await uploadRes.json();

      if (!uploadRes.ok) throw new Error(uploadData.error || 'Upload failed');

      currentSessionId = uploadData.session_id;

      // Step 2: Score Resumes
      const scoreRes = await apiFetch('/api/score', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          job_title: jobTitle,
          skills: skills,
          top_n: topN,
          session_id: currentSessionId
        })
      });

      const scoreData = await scoreRes.json();

      if (!scoreRes.ok) throw new Error(scoreData.error || 'Scoring failed');

      // Step 3: Render Results
      renderResults(scoreData.results || [], skills);

    } catch (err) {
      showToast(err.message, 'error');
      stopLoadingAnimations();
    }
  });

  // --- Render Result Cards ---
  function renderResults(records, targetSkills) {
    stopLoadingAnimations();
    resultsList.innerHTML = '';

    if (records.length === 0) {
      showToast('No matching resumes found.', 'info');
      // Show empty state inside results
      resultsList.innerHTML = '<p style="text-align: center; color: var(--text-muted); padding: 20px;">No exact matches met the minimum threshold.</p>';
      resultsContainer.classList.remove('hidden');
      return;
    }

    records.forEach((rec, index) => {
      // Explicit float handling / 100 normalization
      let displayPct = 0;
      let rawScore = parseFloat(rec.score) || 0;

      if (rawScore <= 1.0 && rawScore > 0) {
        displayPct = Math.round(rawScore * 100);
      } else {
        displayPct = Math.round(rawScore);
      }
      displayPct = Math.max(0, Math.min(100, displayPct)); // Clamp 0-100

      // Cleanup filename for display
      const filename = rec.file || rec.filename || 'Unknown';
      let cleanName = filename.replace(/\.(pdf|docx)$/i, '').replace(/_/g, ' ');

      // Subtitle suggestion helper based on score
      let suggestion = "Review Details";
      let colorClass = "score-yellow";
      let textClass = "text-yellow";

      if (displayPct >= 71) {
        suggestion = "Strong Match";
        colorClass = "score-green";
        textClass = "text-green";
      } else if (displayPct >= 41) {
        suggestion = "Potential Match";
        colorClass = "score-yellow";
        textClass = "text-yellow";
      } else {
        suggestion = "Low Relevance";
        colorClass = "score-red";
        textClass = "text-red";
      }

      // Whitelist of common skills
      const COMMON_SKILLS = new Set(["html", "css", "js", "javascript", "react", "node", "python", "java", "sql", "c++", "c#", "ruby", "php", "aws", "docker", "kubernetes", "git", "linux"]);

      let suggestionBox = "";
      if (rec.missing_skills && rec.missing_skills.length > 0) {
        let suggestions = [];
        rec.missing_skills.forEach(skill => {
          if (COMMON_SKILLS.has(skill.toLowerCase())) {
            suggestions.push(`Consider adding ${skill.toUpperCase()} projects or experience.`);
          }
        });
        if (suggestions.length > 0) {
          suggestionBox = `<div class="suggestion-box">💡 <strong>Suggestions:</strong><br>${suggestions.join('<br>')}</div>`;
        }
      }

      let skillsHtml = "";
      if (rec.matched_skills && rec.matched_skills.length > 0) {
        skillsHtml += `<div class="pill-group"><span class="pill-header">Matched:</span>`;
        rec.matched_skills.forEach(s => skillsHtml += `<span class="skill-pill-match">✔ ${s}</span>`);
        skillsHtml += `</div>`;
      }
      if (rec.missing_skills && rec.missing_skills.length > 0) {
        skillsHtml += `<div class="pill-group"><span class="pill-header">Missing:</span>`;
        rec.missing_skills.forEach(s => skillsHtml += `<span class="skill-pill-miss">❌ ${s}</span>`);
        skillsHtml += `</div>`;
      }
      if (skillsHtml) {
        skillsHtml = `<div class="skills-block">${skillsHtml}</div>`;
      }

      const card = document.createElement('div');
      card.className = 'result-card';
      card.innerHTML = `
        <div class="card-top">
          <div class="score-circle ${colorClass}" style="border: 2px solid;">
            ${displayPct}%
          </div>
          <div class="result-info">
            <h3 class="candidate-name">${cleanName}</h3>
            <p class="candidate-skills ${textClass}" style="font-weight: 500;">${suggestion}</p>
          </div>
          <button class="view-btn">View</button>
        </div>
        ${skillsHtml}
        ${suggestionBox}
      `;

      card.querySelector('.view-btn').addEventListener('click', () => {
        window.open(`/view/${encodeURIComponent(currentSessionId)}/${encodeURIComponent(filename)}`, '_blank');
      });

      resultsList.appendChild(card);
    });

    resultsContainer.classList.remove('hidden');

    // Smooth scroll down to results
    setTimeout(() => {
      resultsContainer.scrollIntoView({ behavior: 'smooth', block: 'start' });
      showToast('Analysis successfully completed!', 'success');
    }, 100);
  }

});
