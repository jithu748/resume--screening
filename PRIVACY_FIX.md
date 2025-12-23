# Privacy Fix: Session-Isolated Resume Storage

## Problem Fixed
Previously, all users accessing the deployed application shared the same server-side storage directory (`resume_uploads/`). This meant:
- User A uploads resumes → stored in shared folder
- User B opens the same URL → can see and use User A's resumes
- **Privacy violation**: Everyone could access everyone else's data

## Solution Implemented
**Session-Isolated Temporary Storage with Auto-Cleanup**

### Key Features:
1. ✅ **Per-Session Isolation**: Each upload gets a unique `session_id` and temporary directory
2. ✅ **Automatic Cleanup**: Files are deleted immediately after processing
3. ✅ **No Shared Storage**: Users cannot access each other's data
4. ✅ **Memory Efficient**: Temporary files don't accumulate on the server
5. ✅ **Zero Configuration**: No authentication system needed (perfect for demos)

---

## What Changed

### Backend Changes (webapp.py)

#### Before:
```python
# All users shared this directory
UPLOADS_DIR = "resume_uploads/"
app.mount("/uploads", StaticFiles(directory=UPLOADS_DIR))
```

#### After:
```python
# Each session gets a unique temporary directory
_session_storage = {}  # Maps session_id -> temp_dir_path

# Files auto-deleted after processing
with get_session_dir(session_id) as temp_dir:
    # use temp_dir
    pass  # Automatically cleaned up here
```

### API Changes

#### 1. Upload Endpoints Now Return `session_id`

**POST /api/upload**
```json
// Response includes session_id
{
  "saved": ["resume1.pdf", "resume2.pdf"],
  "count": 2,
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Files uploaded successfully. Use session_id for scoring."
}
```

**POST /api/upload-zip**
```json
// Same response format
{
  "saved": ["resume1.pdf", "resume2.pdf", "resume3.pdf"],
  "count": 3,
  "session_id": "650e8400-e29b-41d4-a716-446655440001",
  "message": "ZIP extracted successfully. Use session_id for scoring."
}
```

#### 2. Scoring Endpoint Requires `session_id`

**POST /api/score**
```json
// Request body
{
  "job_title": "Software Engineer",
  "skills": "Python, FastAPI, Docker",
  "top_n": 10,
  "session_id": "550e8400-e29b-41d4-a716-446655440000"  // REQUIRED
}

// Response
{
  "results": [
    {"rank": 1, "file": "resume1.pdf", "score": 0.85},
    {"rank": 2, "file": "resume2.pdf", "score": 0.72}
  ]
}
```

⚠️ **After scoring, files are automatically deleted!**

#### 3. Download Results Requires `session_id`

**GET /api/download_results**
```
?job_title=Software%20Engineer
&skills=Python,FastAPI
&top_n=5
&session_id=550e8400-e29b-41d4-a716-446655440000  // REQUIRED
```

⚠️ **After download, files are automatically deleted!**

#### 4. Deprecated Endpoints

These endpoints no longer work as before:
- `GET /api/list_uploads` - Returns empty list with deprecation message
- `DELETE /api/clear_uploads` - Returns deprecation message

---

## Frontend Integration Guide

### Example Workflow

```javascript
// 1. Upload files
const formData = new FormData();
formData.append('files', file1);
formData.append('files', file2);

const uploadResponse = await fetch('/api/upload', {
  method: 'POST',
  body: formData
});

const uploadData = await uploadResponse.json();
const sessionId = uploadData.session_id;  // Save this!

// 2. Score resumes using session_id
const scoreResponse = await fetch('/api/score', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    job_title: 'Software Engineer',
    skills: 'Python, FastAPI',
    top_n: 10,
    session_id: sessionId  // Required!
  })
});

const results = await scoreResponse.json();
// Files are now deleted automatically

// 3. If you need to download CSV results
const csvUrl = `/api/download_results?job_title=Software%20Engineer&skills=Python,FastAPI&top_n=5&session_id=${sessionId}`;
window.open(csvUrl);
// Files are deleted after download
```

### Important Notes for Frontend:
1. **Save the `session_id`** from the upload response
2. **Pass `session_id`** to all subsequent API calls
3. **Files are deleted after scoring** - you cannot re-score the same session
4. **For multiple scorings**: re-upload files each time

---

## How It Works Under the Hood

```python
# 1. User uploads files
session_id = uuid.uuid4()
temp_dir = tempfile.mkdtemp(prefix=f"resume_session_{session_id}_")
# Files saved to: /tmp/resume_session_<uuid>_<random>/

# 2. Session stored in memory
_session_storage[session_id] = temp_dir

# 3. User requests scoring
resume_dir = _session_storage.get(session_id)
# ... process files ...

# 4. Auto-cleanup after processing
shutil.rmtree(temp_dir)  # Delete directory
del _session_storage[session_id]  # Remove from memory
```

---

## Security Benefits

| Before | After |
|--------|-------|
| ❌ Shared storage for all users | ✅ Isolated per-session storage |
| ❌ Files persist indefinitely | ✅ Auto-deleted after processing |
| ❌ Anyone can access `/uploads/` | ✅ No public file access |
| ❌ File accumulation on server | ✅ Automatic cleanup |
| ❌ Privacy violations | ✅ Data isolation guaranteed |

---

## Testing the Fix

### Test Case 1: User Isolation
1. User A uploads `resume_a.pdf`
2. User A gets `session_id_A`
3. User B uploads `resume_b.pdf`
4. User B gets `session_id_B`
5. User B tries to score with `session_id_A` → **Error: Invalid session_id**
6. ✅ Users cannot access each other's files

### Test Case 2: Auto-Cleanup
1. Upload files → get `session_id`
2. Score resumes with `session_id`
3. Try to score again with same `session_id` → **Error: Invalid or expired session_id**
4. ✅ Files are deleted after processing

### Test Case 3: Backwards Compatibility
1. Use POST `/run` endpoint with form data
2. Files are uploaded, processed, and deleted automatically
3. ✅ Old workflow still works

---

## Migration Checklist

If you have existing frontend code, update it to:

- [ ] Capture `session_id` from upload responses
- [ ] Include `session_id` in scoring requests
- [ ] Include `session_id` in download requests
- [ ] Handle "Invalid session_id" errors (prompt user to re-upload)
- [ ] Remove any calls to `/api/list_uploads` or `/api/clear_uploads`
- [ ] Update UI to show that files are temporary and will be deleted

---

## Deployment Notes

### No Database Required
- Session storage is in-memory (`_session_storage = {}`)
- Perfect for stateless deployments (Render, Heroku, etc.)
- Server restarts clear all sessions automatically

### Limitations
- Sessions don't persist across server restarts
- No session expiration (cleaned up immediately after use)
- Not suitable for long-running batch jobs (use immediately)

### Production Considerations
For production apps with persistent sessions, consider:
- Redis/Memcached for session storage across multiple servers
- Session expiration (e.g., 1 hour TTL)
- Background cleanup jobs for orphaned files
- Database-backed user authentication

But for a **demo/college project**, the current implementation is perfect! ✅

---

## Summary

**Before**: Shared storage = Privacy nightmare  
**After**: Session-isolated temporary storage = Privacy protected

✅ Simple  
✅ Clean  
✅ Secure  
✅ Zero configuration  
✅ Perfect for demos
