FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN python -m pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Download NLTK data
RUN python -c "import nltk; nltk.download('punkt'); nltk.download('stopwords'); nltk.download('wordnet'); nltk.download('omw-1.4')"

# Copy application
COPY . .

# Create necessary directories
RUN mkdir -p data/resume_uploads data/shortlisted

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "data.src.webapp:app", "--host", "0.0.0.0", "--port", "8000"]
