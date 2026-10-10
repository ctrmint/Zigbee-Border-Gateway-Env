#!/usr/bin/env python3
"""Create a clean source archive from tracked files (no secrets/build outputs/.git)."""
from pathlib import Path
import subprocess
import zipfile
root=Path(__file__).resolve().parents[1]
files=subprocess.check_output(['git','ls-files','-z'],cwd=root).decode().split('\0')
out=root.parent/(root.name+'.zip')
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for name in files:
        if name and (root/name).is_file():z.write(root/name,root.name+'/'+name)
print(out)
