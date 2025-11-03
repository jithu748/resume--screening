# Project-root launcher: run the main script in data/src
import runpy
import os
import sys


if __name__ == '__main__':
    # Ensure data/src is on sys.path so imports like `from extract_text import ...` work
    base = os.path.dirname(__file__)
    src_dir = os.path.abspath(os.path.join(base, 'data', 'src'))
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    runpy.run_path(os.path.join(src_dir, 'main.py'), run_name='__main__')
