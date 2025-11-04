"""
Quick helper to copy resume files from a local folder into the project's data/resume_uploads directory.
Usage (PowerShell):
    .\.venv\Scripts\python.exe scripts\import_folder.py "C:\path\to\resumes"

It copies only .pdf and .docx files and preserves filenames. Use this when you already have hundreds of resumes in a local folder.
"""
import os
import shutil
import sys

VALID_EXT = {'.pdf', '.docx'}

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python scripts/import_folder.py <source_folder>")
        sys.exit(1)

    src = sys.argv[1]
    if not os.path.isdir(src):
        print(f"Source folder not found: {src}")
        sys.exit(1)

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    dest_dir = os.path.join(repo_root, 'data', 'resume_uploads')
    os.makedirs(dest_dir, exist_ok=True)

    count = 0
    copied = []
    for root, dirs, files in os.walk(src):
        for f in files:
            if os.path.splitext(f)[1].lower() in VALID_EXT:
                src_path = os.path.join(root, f)
                dest_path = os.path.join(dest_dir, f)
                try:
                    shutil.copy2(src_path, dest_path)
                    copied.append(f)
                    count += 1
                except Exception as e:
                    print(f"Failed to copy {src_path}: {e}")
    print(f"Copied {count} resume files to {dest_dir}")
    if count < 100:
        print('Tip: you can copy larger batches, but monitor disk and memory when running the webapp for scoring.')
