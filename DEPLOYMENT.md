# Deployment Guide

This guide covers deploying the Resume Screening application to various cloud platforms.

## Option 1: Deploy to Render (Recommended - Free Tier Available)

### Prerequisites
- GitHub account
- Push your code to a GitHub repository

### Steps

1. **Push to GitHub** (if not already done):
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/yourusername/resume-screening.git
git push -u origin main
```

2. **Sign up for Render**:
   - Go to https://render.com
   - Sign up with GitHub

3. **Create a new Web Service**:
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Configure:
     - **Name**: resume-screening (or your choice)
     - **Region**: Choose closest to you
     - **Branch**: main
     - **Root Directory**: (leave empty)
     - **Runtime**: Python 3
     - **Build Command**: `pip install -r requirements.txt && python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet'); nltk.download('omw-1.4')"`
     - **Start Command**: `uvicorn data.src.webapp:app --host 0.0.0.0 --port $PORT`
     - **Instance Type**: Free

4. **Deploy**:
   - Click "Create Web Service"
   - Wait 5-10 minutes for deployment
   - Your app will be live at: `https://your-app-name.onrender.com`

### Important Notes for Render:
- Free tier sleeps after 15 minutes of inactivity (cold starts take ~30 seconds)
- Free tier has 750 hours/month limit
- Upgrade to paid tier ($7/month) for always-on service

---

## Option 2: Deploy to Railway

### Prerequisites
- GitHub account
- Push your code to GitHub

### Steps

1. **Sign up for Railway**:
   - Go to https://railway.app
   - Sign up with GitHub

2. **Create New Project**:
   - Click "New Project"
   - Select "Deploy from GitHub repo"
   - Choose your repository
   - Railway auto-detects Python

3. **Configure**:
   - Add a start command in railway.json or use Procfile (already set up)
   - Railway will automatically use the Procfile
   - Set Python version in settings if needed

4. **Add Domain**:
   - Go to Settings → Generate Domain
   - Your app will be live at: `https://your-app.up.railway.app`

### Important Notes for Railway:
- Free tier: $5 credit/month (usually enough for a small app)
- Automatically scales
- Better performance than Render free tier

---

## Option 3: Deploy to Google Cloud Run

### Prerequisites
- Google Cloud account
- gcloud CLI installed

### Steps

1. **Create Dockerfile** (see below)

2. **Build and deploy**:
```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID

# Build container
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/resume-screening

# Deploy to Cloud Run
gcloud run deploy resume-screening \
  --image gcr.io/YOUR_PROJECT_ID/resume-screening \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --memory 2Gi
```

---

## Option 4: Deploy to AWS (Elastic Beanstalk)

### Prerequisites
- AWS account
- EB CLI installed: `pip install awsebcli`

### Steps

```bash
# Initialize EB
eb init -p python-3.10 resume-screening --region us-east-1

# Create environment and deploy
eb create resume-screening-env

# Open in browser
eb open
```

---

## Additional Files Needed

### Dockerfile (for containerized deployments)

```dockerfile
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet'); nltk.download('omw-1.4')"

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "data.src.webapp:app", "--host", "0.0.0.0", "--port", "8000"]
```

### .dockerignore

```
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
*.so
*.egg
*.egg-info/
dist/
build/
.venv/
venv/
.git/
.gitignore
*.md
.DS_Store
```

---

## Environment Variables

Most platforms support environment variables. If you need to configure anything:

- `PORT` - Automatically set by most platforms
- Add any API keys or secrets through platform UI

---

## Troubleshooting

### Large Model Download Issues
If using sentence-transformers, first deployment might time out:
- Pre-download models and include in repo, OR
- Use lighter models, OR
- Increase build timeout in platform settings

### Memory Issues
- Torch + sentence-transformers need ~2GB RAM
- Free tiers might struggle
- Consider upgrading to paid tier or using lighter alternatives

### Cold Starts
- Free tiers sleep after inactivity
- First request after sleep is slow (~30-60 seconds)
- Upgrade to paid tier for always-on service

---

## Cost Comparison (as of Dec 2024)

| Platform | Free Tier | Paid Tier | Notes |
|----------|-----------|-----------|-------|
| **Render** | 750hrs/month, sleeps | $7/month | Best for simple apps |
| **Railway** | $5 credit/month | $5-20/month | Good performance |
| **Google Cloud Run** | 2M requests/month | Pay per use | Best for variable traffic |
| **AWS EB** | 750hrs/month (1yr) | $15-50/month | More complex setup |
| **Heroku** | Removed free tier | $7/month | Classic choice |

---

## Quick Deploy - Render (Fastest)

1. Push code to GitHub
2. Go to https://render.com → Sign up
3. New Web Service → Connect repo
4. Use these settings:
   - Build: `pip install -r requirements.txt && python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet'); nltk.download('omw-1.4')"`
   - Start: `uvicorn data.src.webapp:app --host 0.0.0.0 --port $PORT`
5. Deploy!

Your app will be live in ~10 minutes!
