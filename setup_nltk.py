import nltk
import os
import sys

# Set NLTK data directory
nltk_data_dir = os.environ.get('NLTK_DATA', os.path.expanduser('~/nltk_data'))
nltk.data.path.insert(0, nltk_data_dir)

try:
    print(f"Setting up NLTK data in: {nltk_data_dir}")
    nltk.download('punkt', quiet=True)
    nltk.download('stopwords', quiet=True)
    nltk.download('wordnet', quiet=True)
    nltk.download('omw-1.4', quiet=True)
    print("✅ NLTK setup complete!")
except Exception as e:
    print(f"⚠️ NLTK setup encountered an issue: {e}", file=sys.stderr)
    print("Continuing anyway - may fail if these packages are needed", file=sys.stderr)