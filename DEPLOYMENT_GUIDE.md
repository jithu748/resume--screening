# Resume Screening - Session-Based Deployment Guide

## Overview
This application implements **session-based, isolated resume uploads** with a 10-minute sliding TTL (Time To Live). Each user gets a private session with its own temporary storage. Sessions auto-expire and clean up files automatically.

**Key Features:**
- ✅ Session isolation: No cross-user visibility
- ✅ 10-minute sliding TTL: Activity refreshes expiration
- ✅ Auto-cleanup: Expired/ended sessions delete files
- ✅ Manual end: "End Session" button for immediate cleanup
- ✅ No database or authentication required
- ✅ Dark/light mode toggle unchanged and functional
- ✅ Suitable for college demos and real multi-user apps

---

## Local Development

### Requirements
- Python 3.10+
- FastAPI, Uvicorn, and other deps in `requirements.txt`

### Setup & Run
```bash
# Activate virtual environment
D:/projects/resume_screening/.venv/Scripts/Activate.ps1

# Install dependencies (if needed)
pip install -r requirements.txt

# Start the server
D:/projects/resume_screening/.venv/Scripts/python.exe -m uvicorn data.src.webapp:app --reload --host 127.0.0.1 --port 8000
```

**Access the app:**
- http://127.0.0.1:8000

---

## Production Deployment (Render or Similar)

### Procfile (already configured)
```
web: uvicorn data.src.webapp:app --host 0.0.0.0 --port $PORT
```

### Deployment Steps

#### 1. Push to GitHub
```bash
git add .
git commit -m "Add session-based isolation with 10-min TTL"
git push origin main
```

#### 2. Connect to Render
1. Go to https://render.com
2. Create a new **Web Service**
3. Connect your GitHub repository
4. Set runtime to **Python 3.10** (or later)
5. Build command: `pip install -r requirements.txt`
6. Start command: `uvicorn data.src.webapp:app --host 0.0.0.0 --port $PORT`
7. Deploy

#### 3. Verify Deployment
- Open your Render URL
- Upload resumes → you'll see "Session: <first 8 chars>"
- Files are isolated to your session
- "End Session" button clears files immediately

---

## How It Works

### Session Lifecycle

1. **Upload Resumes**
   - User uploads files → app creates session with UUID
   - Files stored in temp directory: `/tmp/resume_session_<uuid>_<random>/`
   - UI shows: "Session: <first 8 chars>", file count, file names
   - Response includes `session_id`, `files`, `count`, `expires_in`

2. **Score Resumes**
   - User enters job title/skills and clicks "Run"
   - Session ID required; must match upload session
   - Scoring runs on isolated files
   - Session TTL refreshed (sliding)
   - Results displayed; session remains active

3. **End Session**
   - User clicks "End Session" button
   - Files deleted immediately
   - UI prompts to re-upload

4. **Auto-Expiry**
   - If idle for ~10 minutes, session expires
   - Background cleanup thread removes files
   - Next access shows "Session expired" message

### API Endpoints

| Endpoint | Method | Purpose | Notes |
|----------|--------|---------|-------|
| `/api/upload` | POST | Upload resumes | Form: `files[]`, optional `session_id` |
| `/api/upload-zip` | POST | Upload ZIP archive | Form: `file`, optional `session_id` |
| `/api/session_status` | GET | Check session info | Query: `session_id` → `{files, count, expires_in}` |
| `/api/score` | POST | Score resumes | JSON: `{job_title, skills, top_n, session_id}` |
| `/api/download_results` | GET | Download CSV | Query: `job_title, skills, top_n, session_id` |
| `/api/end_session` | POST | End session manually | JSON/form/query: `session_id` |
| `/api/session` | DELETE | Fallback end session | Query: `session_id` |

---

## Configuration

### Session TTL
Edit `data/src/webapp.py` line 31:
```python
SESSION_TTL_SECONDS = 10 * 60  # Change to 15*60 for 15 minutes, etc.
```

### Cleanup Interval
Edit `data/src/webapp.py` in `_cleanup_expired_sessions_loop()` function:
```python
time.sleep(60)  # Change to 120 for 2-minute checks, etc.
```

---

## File Structure

```
resume_screening/
├── data/
│   ├── src/
│   │   ├── webapp.py              ← FastAPI app with session TTL
│   │   ├── extract_text.py        ← Text extraction
│   │   ├── scorer.py              ← Resume scoring logic
│   │   ├── similarity.py          ← Cosine similarity
│   │   ├── vectorizer.py          ← TF-IDF vectorization
│   │   └── preprocess.py          ← Text preprocessing
│   ├── web/
│   │   ├── static/
│   │   │   ├── app.js             ← Frontend with session UI
│   │   │   └── style.css          ← Styles (dark/light theme)
│   │   └── templates/
│   │       └── index.html         ← HTML template with session section
│   ├── README.md
│   └── requirements.txt
├── Procfile                        ← Render deployment config
└── DEPLOYMENT_GUIDE.md            ← This file
```

---

## Security & Privacy

- **Session Isolation:** Each session has its own temp directory; files never mix
- **No Cross-User Access:** Session IDs are UUIDs; impossible to guess other users' sessions
- **Auto-Cleanup:** Files deleted after 10 minutes of inactivity or manual end
- **No Database:** Reduces complexity and eliminates data persistence concerns
- **No Authentication:** Suitable for demos; users are not tracked
- **Privacy Priority:** Designed so uploads are NOT visible to other users

---

## Troubleshooting

### "Session expired" message
- The session has been idle for ~10 minutes
- Solution: Click "End Session" and re-upload, or just upload fresh files

### "Please upload resumes first!"
- No active session or session ended
- Solution: Upload resumes to create a new session

### Files appearing in multiple sessions
- This should not happen; report as a bug
- Quick check: Each session should have a unique UUID in `_session_storage`

### Server logs show cleanup messages
```
[CLEANUP] Expired session abc12345... cleaned up
```
- This is expected; means the cleanup thread is running

---

## Performance Notes

- **Single-server deployment:** In-memory session storage (no network overhead)
- **Multi-instance deployment (Render Pro):** Each instance has its own in-memory sessions; not shared across instances (acceptable for demos)
- **Temp file storage:** Uses OS temp directory; auto-cleaned by OS if server crashes
- **Cleanup thread:** Runs every 60 seconds; very lightweight

---

## Future Enhancements (Optional)

1. **Redis/Memcached:** Share sessions across multiple server instances
2. **Database:** Persist user accounts and upload history
3. **Authentication:** JWT/OAuth for real multi-user SaaS
4. **TTL Countdown:** Show minutes remaining in UI
5. **Session Sharing:** Allow users to share a session via link
6. **Activity Logging:** Track who uploaded what and when

---

## Support

- **Local issues:** Check terminal logs and browser console (F12)
- **Render deployment issues:** Check Render logs in dashboard
- **API issues:** Verify session_id is passed in all subsequent requests after upload
- **Dark mode issues:** Clear browser cache; theme toggle should work automatically

---

## Summary

Your resume screening app now has:
- ✅ 10-minute sliding TTL sessions
- ✅ Session-isolated uploads (no cross-user visibility)
- ✅ Automatic cleanup on expiry or manual end
- ✅ Simple, database-free design
- ✅ Ready to deploy on Render (or any cloud provider)
- ✅ Suitable for college demos and real multi-user apps
- ✅ Dark/light mode toggle fully functional

**Deploy with confidence!** The app is production-ready for small-to-medium multi-user scenarios.
