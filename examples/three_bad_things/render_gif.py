#!/usr/bin/env python3
"""Render three-bad-things.gif from _anim.html — needs only Chrome + Pillow.

No vhs/ttyd/ffmpeg required. Chrome screenshots each reveal step; Pillow stitches
them into an optimized looping GIF.

    python3 render_gif.py
"""
import glob
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
STEPS = 9
DURATIONS = {1: 900, 2: 800, 3: 750, 4: 750, 5: 1400, 6: 800, 7: 1600, 8: 1100, 9: 3000}

chrome = next((c for c in ("google-chrome", "google-chrome-stable", "chromium",
                           "chromium-browser") if shutil.which(c)), None)
if not chrome:
    sys.exit("need Chrome/Chromium on PATH")

frames_dir = tempfile.mkdtemp(prefix="tbt_frames_")
for n in range(1, STEPS + 1):
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    "--force-device-scale-factor=1", "--window-size=1020,760",
                    f"--screenshot={frames_dir}/f{n}.png",
                    f"file://{HERE}/_anim.html?n={n}"],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

files = sorted(glob.glob(f"{frames_dir}/f*.png"),
               key=lambda p: int("".join(filter(str.isdigit, os.path.basename(p)))))
frames = [Image.open(f).convert("RGB") for f in files]
durs = [DURATIONS[i + 1] for i in range(len(frames))]
pal = frames[-1].quantize(colors=200, method=Image.MEDIANCUT)
q = [f.quantize(palette=pal, dither=Image.NONE) for f in frames]
out = os.path.join(HERE, "three-bad-things.gif")
q[0].save(out, save_all=True, append_images=q[1:], duration=durs, loop=0,
          optimize=True, disposal=2)
shutil.rmtree(frames_dir, ignore_errors=True)
print(f"wrote {out}  ({len(frames)} frames, {os.path.getsize(out)/1024:.0f} KB)")
