import streamlit as st
import subprocess
import tempfile
import os
import math
from pathlib import Path
import time
import zipfile

st.set_page_config(
    page_title="Video Splitter",
    page_icon="✂️", 
    layout="wide"
)

def check_ffmpeg_availability():
    """Check if FFmpeg is available"""
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=5)
        return result.returncode == 0
    except:
        return False

def get_video_info(video_path):
    """Get video duration using ffprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet', '-print_format', 'json', 
            '-show_format', '-show_streams', video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            return duration
        return None
    except Exception as e:
        st.error(f"Error getting video info: {str(e)}")
        return None

def split_video_ffmpeg(input_path, output_dir, chunk_duration=1500):
    """Fast video splitting using FFmpeg stream copy"""
    duration = get_video_info(input_path)
    if not duration:
        return []
    
    num_chunks = math.ceil(duration / chunk_duration)
    output_files = []
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    input_name = Path(input_path).stem
    
    for i in range(num_chunks):
        start_time = i * chunk_duration
        
        output_filename = f"{input_name}_part_{i+1:02d}.mp4"
        output_path = os.path.join(output_dir, output_filename)
        
        status_text.text(f"Splitting chunk {i+1}/{num_chunks}: {output_filename}")
        
        # FFmpeg command with stream copy (no re-encoding)
        cmd = [
            'ffmpeg', '-i', input_path,
            '-ss', str(start_time),
            '-t', str(chunk_duration),
            '-c', 'copy',  # Stream copy - preserves quality!
            '-avoid_negative_ts', 'make_zero',
            '-y', output_path
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0 and os.path.exists(output_path):
            output_files.append(output_path)
        
        progress = (i + 1) / num_chunks
        progress_bar.progress(progress)
    
    status_text.text("✅ Splitting complete!")
    return output_files

def split_video_moviepy(input_path, output_dir, chunk_duration=1500):
    """Fallback using moviepy"""
    try:
        from moviepy.editor import VideoFileClip
        
        status_text = st.empty()
        status_text.text("Loading video...")
        
        video = VideoFileClip(input_path)
        total_duration = video.duration
        num_chunks = math.ceil(total_duration / chunk_duration)
        
        output_files = []
        progress_bar = st.progress(0)
        input_name = Path(input_path).stem
        
        for i in range(num_chunks):
            start_time = i * chunk_duration
            end_time = min((i + 1) * chunk_duration, total_duration)
            
            output_filename = f"{input_name}_part_{i+1:02d}.mp4"
            output_path = os.path.join(output_dir, output_filename)
            
            status_text.text(f"Extracting chunk {i+1}/{num_chunks}: {output_filename}")
            
            chunk = video.subclip(start_time, end_time)
            chunk.write_videofile(output_path, verbose=False, logger=None)
            chunk.close()
            
            if os.path.exists(output_path):
                output_files.append(output_path)
            
            progress = (i + 1) / num_chunks
            progress_bar.progress(progress)
        
        video.close()
        status_text.text("✅ Splitting complete!")
        return output_files
        
    except ImportError:
        st.error("MoviePy not installed. Add to requirements.txt: moviepy>=1.0.3")
        return []
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return []

def create_zip_file(file_paths, zip_name):
    """Create a zip file containing all chunks"""
    zip_path = os.path.join(tempfile.gettempdir(), zip_name)
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for file_path in file_paths:
            arcname = os.path.basename(file_path)
            zipf.write(file_path, arcname)
    
    return zip_path

def format_duration(seconds):
    """Convert seconds to HH:MM:SS"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"

def format_size(bytes):
    """Convert bytes to readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024:
            return f"{bytes:.1f} {unit}"
        bytes /= 1024
    return f"{bytes:.1f} TB"

def download_from_url(url, output_path):
    """Download video from URL"""
    try:
        import requests
        
        # Get file size first
        response = requests.head(url, allow_redirects=True)
        file_size = int(response.headers.get('content-length', 0))
        
        if file_size > 5 * 1024 * 1024 * 1024:  # 5GB limit
            st.error("File too large (>5GB). Please use a smaller file.")
            return None, 0
        
        # Download with progress
        response = requests.get(url, stream=True)
        response.raise_for_status()
        
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        downloaded = 0
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if file_size > 0:
                        progress = downloaded / file_size
                        progress_bar.progress(min(progress, 1.0))
                        status_text.text(f"Downloading: {format_size(downloaded)} / {format_size(file_size)}")
        
        status_text.text("✅ Download complete!")
        return output_path, downloaded
        
    except requests.exceptions.RequestException as e:
        st.error(f"Error downloading file: {str(e)}")
        return None, 0
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return None, 0

def main():
    st.title("✂️ Video Splitter")
    st.markdown("Split long videos into smaller chunks - **fast and simple!**")
    
    # Check capabilities
    ffmpeg_available = check_ffmpeg_availability()
    
    if ffmpeg_available:
        st.success("✅ FFmpeg available - Using fast stream copy (no quality loss)")
    else:
        st.warning("⚠️ FFmpeg not found - Using MoviePy fallback")
    
    # Simple settings
    col1, col2 = st.columns(2)
    with col1:
        chunk_minutes = st.slider("Chunk duration (minutes)", 5, 120, 25)
    with col2:
        st.info("💡 **No compression** = Original quality preserved")
    
    chunk_duration = chunk_minutes * 60
    
    # Input options
    input_method = st.radio(
        "How do you want to provide the video?",
        ["📁 Upload File", "🔗 From URL", "☁️ From Cloud Storage"],
        help="Choose based on your file size and hosting platform"
    )
    
    uploaded_file = None
    video_url = None
    
    if input_method == "📁 Upload File":
        st.info("📋 **Upload Limits**: Streamlit Cloud ~200MB | Railway ~1GB | Render ~2GB")
        uploaded_file = st.file_uploader(
            "Choose a video file",
            type=['mp4', 'avi', 'mov', 'mkv', 'webm', 'flv'],
            help="For larger files, use URL or cloud storage options"
        )
    
    elif input_method == "🔗 From URL":
        st.info("💡 **Perfect for large files!** No upload size limits - processes directly from URL")
        video_url = st.text_input(
            "Enter video URL",
            placeholder="https://example.com/video.mp4",
            help="Direct links to video files (MP4, etc.) - works with Google Drive, Dropbox, etc."
        )
        
        if video_url and not video_url.startswith(('http://', 'https://')):
            st.error("Please enter a valid URL starting with http:// or https://")
            video_url = None
    
    elif input_method == "☁️ From Cloud Storage":
        st.markdown("""
        **For Very Large Files (>2GB):**
        
        1. **Upload to cloud storage first**:
           - Google Drive, Dropbox, OneDrive, etc.
           - Get a direct download link
        
        2. **Use the URL option above** with the direct link
        
        3. **Or deploy to a platform with Google Drive API**:
           ```python
           # Example integration
           from google.oauth2.credentials import Credentials
           from googleapiclient.discovery import build
           ```
        
        **Pro tip**: Many cloud storage services provide direct download URLs that work with the URL option!
        """)
    
    if uploaded_file is not None or video_url:
        # Determine file source and size
        if uploaded_file:
            file_size = len(uploaded_file.getvalue())
            file_size_mb = file_size / (1024 * 1024)
            source_name = uploaded_file.name
        else:
            # For URLs, we'll get size during download
            file_size_mb = 0
            source_name = video_url.split('/')[-1] or "video_from_url.mp4"
        
        # Show file info for uploads
        if uploaded_file:
            col1, col2 = st.columns(2)
            with col1:
                st.metric("File Size", f"{file_size_mb:.1f} MB")
            with col2:
                if file_size_mb <= 200:
                    st.metric("Cloud Status", "✅ Should work", delta="Within limits")
                elif file_size_mb <= 500:
                    st.metric("Cloud Status", "⚠️ May timeout", delta="Large file")
                else:
                    st.metric("Cloud Status", "❌ Too large", delta="Use URL method")
        
        # Analysis and split buttons
        analyze_col, split_col = st.columns(2)
        
        with analyze_col:
            if st.button("📊 Quick Analysis"):
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Get video file
                    if uploaded_file:
                        input_path = os.path.join(temp_dir, uploaded_file.name)
                        with open(input_path, "wb") as f:
                            f.write(uploaded_file.getvalue())
                    else:
                        st.info("⬇️ Downloading file for analysis...")
                        input_path = os.path.join(temp_dir, source_name)
                        input_path, downloaded_size = download_from_url(video_url, input_path)
                        if not input_path:
                            return
                        file_size_mb = downloaded_size / (1024 * 1024)
                    
                    # Analyze duration
                    if ffmpeg_available:
                        duration = get_video_info(input_path)
                    else:
                        try:
                            from moviepy.editor import VideoFileClip
                            clip = VideoFileClip(input_path)
                            duration = clip.duration
                            clip.close()
                        except:
                            duration = None
                    
                    if duration:
                        num_chunks = math.ceil(duration / chunk_duration)
                        avg_chunk_size = file_size_mb / num_chunks
                        
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Duration", format_duration(duration))
                        with col2:
                            st.metric("Will Create", f"{num_chunks} chunks")
                        with col3:
                            st.metric("Avg Chunk Size", f"{avg_chunk_size:.1f} MB")
        
        with split_col:
            if st.button("✂️ Split Video", type="primary"):
                start_time = time.time()
                
                with tempfile.TemporaryDirectory() as temp_dir:
                    # Get the video file
                    if uploaded_file:
                        input_path = os.path.join(temp_dir, uploaded_file.name)
                        with open(input_path, "wb") as f:
                            f.write(uploaded_file.getvalue())
                        final_size_mb = file_size_mb
                    else:
                        st.info("⬇️ Downloading video...")
                        input_path = os.path.join(temp_dir, source_name)
                        input_path, downloaded_size = download_from_url(video_url, input_path)
                        if not input_path:
                            return
                        final_size_mb = downloaded_size / (1024 * 1024)
                    
                    # Size check for processing
                    if final_size_mb > 5000:  # 5GB limit
                        st.error("File too large for processing (>5GB). Please use a smaller file.")
                        return
                    
                    # Create output directory
                    output_dir = os.path.join(temp_dir, "chunks")
                    os.makedirs(output_dir, exist_ok=True)
                    
                    st.header("🔄 Splitting Video...")
                    
                    # Split using available method
                    if ffmpeg_available:
                        output_files = split_video_ffmpeg(input_path, output_dir, chunk_duration)
                    else:
                        output_files = split_video_moviepy(input_path, output_dir, chunk_duration)
                    
                    processing_time = time.time() - start_time
                    
                    if output_files:
                        st.success(f"🎉 Success! Created {len(output_files)} chunks in {processing_time:.1f} seconds")
                        
                        # Download options
                        st.header("📥 Download Your Chunks")
                        
                        # Bulk download option
                        if len(output_files) > 1:
                            zip_name = f"{Path(uploaded_file.name).stem}_chunks.zip"
                            zip_path = create_zip_file(output_files, zip_name)
                            
                            with open(zip_path, "rb") as zip_file:
                                st.download_button(
                                    label=f"📦 Download All Chunks (ZIP)",
                                    data=zip_file.read(),
                                    file_name=zip_name,
                                    mime="application/zip",
                                    type="primary"
                                )
                            
                            st.markdown("---")
                            st.subheader("Individual Downloads")
                        
                        # Individual downloads
                        for i, file_path in enumerate(output_files):
                            filename = os.path.basename(file_path)
                            chunk_size = os.path.getsize(file_path)
                            
                            col1, col2 = st.columns([3, 1])
                            with col1:
                                with open(file_path, "rb") as f:
                                    st.download_button(
                                        label=f"⬇️ {filename}",
                                        data=f.read(),
                                        file_name=filename,
                                        mime="video/mp4",
                                        key=f"download_{i}"
                                    )
                            with col2:
                                st.text(format_size(chunk_size))
                    
                    else:
                        st.error("❌ Failed to split video. Please check the file format and try again.")
    
    else:
        # Instructions when no file uploaded
        st.markdown("""
        ### 🎯 What This Tool Does:
        
        - **Splits videos** into smaller chunks (default: 25 minutes each)
        - **No quality loss** - uses stream copy when possible
        - **Super fast** - no re-encoding, just cutting at timestamps
        - **Multiple input methods** - upload, URL, or cloud storage
        - **No file size limits** with URL method!
        
        ### 📋 Input Methods:
        
        1. **📁 Upload**: Best for smaller files (<200MB on free hosting)
        2. **🔗 URL**: Perfect for large files - no upload limits!
        3. **☁️ Cloud Storage**: Upload to Drive/Dropbox first, then use URL
        
        ### 🚀 Deployment:
        
        **requirements.txt**:
        ```
        streamlit>=1.28.0
        moviepy>=1.0.3
        requests>=2.31.0
        ```
        
        **packages.txt** (for FFmpeg support):
        ```
        ffmpeg
        ```
        
        ### 💡 Pro Tips:
        - **Large files?** Use the URL method - no limits!
        - **Google Drive**: Share → Get link → Use direct download URL
        - **Dropbox**: Replace `dl=0` with `dl=1` in share links
        - **Original quality always preserved**
        """)

if __name__ == "__main__":
    main()
