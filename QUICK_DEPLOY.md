# Quick Deployment to Render

Follow these steps to deploy your app to the web in ~10 minutes:

## Step 1: Commit and Push to GitHub

```powershell
# Add all files
git add .

# Commit changes
git commit -m "Add deployment configuration"

# Push to GitHub (make sure you're on main/master branch)
git push origin main
```

## Step 2: Sign Up for Render

1. Go to: **https://render.com**
2. Click **"Get Started for Free"**
3. Sign up with your **GitHub account**

## Step 3: Deploy Your App

1. After logging in, click **"New +"** → **"Web Service"**

2. Click **"Connect GitHub"** and authorize Render

3. Find your `resume_screening` repository and click **"Connect"**

4. Fill in the configuration:
   - **Name**: `resume-screening` (or any name you like)
   - **Region**: Choose the closest to you (e.g., Oregon, Frankfurt, Singapore)
   - **Branch**: `main` (or your current branch)
   - **Root Directory**: (leave blank)
   - **Runtime**: `Python 3`
   - **Build Command**:
     ```
     pip install -r requirements.txt && python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet'); nltk.download('omw-1.4')"
     ```
   - **Start Command**:
     ```
     uvicorn data.src.webapp:app --host 0.0.0.0 --port $PORT
     ```

5. Scroll down to **Instance Type** and select **"Free"**

6. Click **"Create Web Service"**

## Step 4: Wait for Deployment

- Render will start building your app (5-10 minutes)
- You'll see build logs in real-time
- Once complete, you'll see "Your service is live 🎉"

## Step 5: Access Your Live App

Your app will be available at:
```
https://resume-screening.onrender.com
```
(or whatever name you chose)

---

## Important Notes

### Free Tier Limitations:
- ✅ Free forever
- ✅ 750 hours/month (usually enough)
- ⚠️ App sleeps after 15 minutes of inactivity
- ⚠️ First request after sleep takes ~30 seconds (cold start)

### To Prevent Sleeping (Optional):
- Upgrade to paid tier: $7/month for always-on
- Or use a service like UptimeRobot to ping your app every 10 minutes

### For Production Use:
Consider upgrading if:
- You need fast response times always
- You have users in different timezones
- You can't afford 30-second cold starts

---

## Troubleshooting

**Build fails?**
- Check that all files are committed and pushed
- Verify requirements.txt is in root directory
- Check build logs for specific errors

**App crashes on startup?**
- Check that runtime.txt has correct Python version
- Verify Procfile is correct
- Check logs in Render dashboard

**Slow first load?**
- Normal for free tier (cold start)
- Subsequent requests will be fast
- Consider paid tier or UptimeRobot pinging

---

## Alternative: Deploy with Docker (Optional)

If you prefer Docker:

```powershell
# Test locally first
docker build -t resume-screening .
docker run -p 8000:8000 resume-screening

# Deploy to any container platform:
# - Google Cloud Run
# - AWS ECS
# - Azure Container Apps
```

---

## Next Steps After Deployment

1. **Share your live URL** with users
2. **Monitor** usage in Render dashboard
3. **Set up custom domain** (optional, paid feature)
4. **Add analytics** (Google Analytics, Plausible, etc.)
5. **Add authentication** if needed for privacy

---

## Cost Summary

| Tier | Cost | Features |
|------|------|----------|
| **Free** | $0/month | 750hrs, sleeps after 15min inactivity |
| **Starter** | $7/month | Always-on, no sleeping, custom domains |
| **Standard** | $25/month | More resources, faster performance |

**Recommendation**: Start with free tier, upgrade if needed!
