import streamlit as st
import subprocess, tempfile, os, math, time, zipfile, re
from pathlib import Path
import requests
import gdown
from moviepy.editor import VideoFileClip

st.set_page_config("Video Splitter", "✂️", layout="centered")
st.title("✂️ Video Splitter")

# Slider for chunk length (max 25 mins)
chunk_mins = st.slider("Chunk length (minutes)", 5, 25, 25)
url = st.text_input("Video URL (Drive or direct)")

def is_ffmpeg_available():
    return subprocess.run(['ffmpeg','-version'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0

def get_duration(path):
    cmd = ['ffprobe','-v','quiet','-print_format','json','-show_format',path]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode==0:
        import json
        return float(json.loads(res.stdout)['format']['duration'])
    return None

def download_video(src_url, dest):
    if "drive.google.com" in src_url:
        m = re.search(r'(?:/d/|id=)([A-Za-z0-9_-]+)', src_url)
        if not m: raise ValueError("Invalid Drive link")
        file_id = m.group(1)
        drive_url = f"https://drive.google.com/uc?export=download&id={file_id}"
        gdown.download(drive_url, dest, quiet=False)
    else:
        with requests.get(src_url, stream=True) as r:
            r.raise_for_status()
            with open(dest,'wb') as f:
                for chunk in r.iter_content(8192):
                    f.write(chunk)
    return dest

def split_ffmpeg(inp, outdir, cdur):
    dur = get_duration(inp)
    parts = []
    for i in range(math.ceil(dur/cdur)):
        start = i*cdur
        out = outdir / f"{inp.stem}_part_{i+1:02d}.mp4"
        cmd = [
            'ffmpeg','-ss',str(start),'-i',str(inp),
            '-t',str(cdur),'-c','copy','-avoid_negative_ts','make_zero','-y',str(out)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if out.exists(): parts.append(out)
    return parts

def split_moviepy(inp, outdir, cdur):
    clip = VideoFileClip(str(inp))
    parts = []
    for i in range(math.ceil(clip.duration/cdur)):
        s, e = i*cdur, min((i+1)*cdur, clip.duration)
        out = outdir / f"{inp.stem}_part_{i+1:02d}.mp4"
        clip.subclip(s,e).write_videofile(str(out), codec="libx264", audio_codec="aac")
        parts.append(out)
    clip.close()
    return parts

def make_zip(files, name="chunks.zip"):
    zp = Path(tempfile.gettempdir())/name
    with zipfile.ZipFile(zp,'w') as z:
        for f in files: z.write(f, f.name)
    return zp

if st.button("Split Video"):
    if not url:
        st.error("Please paste a URL."); st.stop()
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        dest = tmpdir/(Path(url).name or "video.mp4")
        st.info("⬇️ Downloading…")
        try:
            in_path = download_video(url, dest)
        except Exception as e:
            st.error(f"Download failed: {e}"); st.stop()

        st.info("🔄 Splitting…")
        cdur = chunk_mins * 60
        if is_ffmpeg_available():
            chunks = split_ffmpeg(Path(in_path), tmpdir, cdur)
        else:
            chunks = split_moviepy(Path(in_path), tmpdir, cdur)

        if not chunks:
            st.error("No chunks created."); st.stop()

        st.success(f"Done—{len(chunks)} files!")
        if len(chunks)>1:
            zipf = make_zip(chunks)
            with open(zipf,'rb') as zf:
                st.download_button("📦 Download All", zf.read(), "chunks.zip", "application/zip")
        for c in chunks:
            with open(c,'rb') as f:
                st.download_button(f"⬇️ {c.name}", f.read(), c.name, "video/mp4")

if __name__ == "__main__":
    main()
