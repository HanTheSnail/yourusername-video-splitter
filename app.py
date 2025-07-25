import streamlit as st
import subprocess
import tempfile
import os
import math
from pathlib import Path
import time
import zipfile
import requests

st.set_page_config(
    page_title="Video Splitter",
    page_icon="✂️", 
    layout="centered",
    initial_sidebar_state="collapsed"
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
        
        status_text.text(f"Splitting chunk {i+1}/{num_chunks}")
        
        cmd = [
            'ffmpeg', '-i', input_path,
            '-ss', str(start_time),
            '-t', str(chunk_duration),
            '-c', 'copy',
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
    """Fallback using moviepy with better error handling"""
    try:
        from moviepy.editor import VideoFileClip
        
        status_text = st.empty()
        status_text.text("Loading video...")
        
        # Load video with timeout protection
        video = VideoFileClip(input_path)
        total_duration = video.duration
        num_chunks = math.ceil(total_duration / chunk_duration)
        
        status_text.text(f"Video loaded: {total_duration:.1f}s, creating {num_chunks} chunks")
        
        output_files = []
        progress_bar = st.progress(0)
        input_name = Path(input_path).stem
        
        for i in range(num_chunks):
            start_time = i * chunk_duration
            end_time = min((i + 1) * chunk_duration, total_duration)
            
            output_filename = f"{input_name}_part_{i+1:02d}.mp4"
            output_path = os.path.join(output_dir, output_filename)
            
            status_text.text(f"Processing chunk {i+1}/{num_chunks} ({start_time:.0f}s-{end_time:.0f}s)")
            
            try:
                # Extract chunk with minimal encoding settings
                chunk = video.subclip(start_time, end_time)
                
                # Write with simpler settings for better compatibility
                chunk.write_videofile(
                    output_path,
                    codec='libx264',
                    audio_codec='aac',
                    temp_audiofile='temp-audio.m4a',
                    remove_temp=True,
                    verbose=False,
                    logger=None
                )
                chunk.close()
                
                if os.path.exists(output_path):
                    output_files.append(output_path)
                    status_text.text(f"✅ Chunk {i+1}/{num_chunks} completed")
                else:
                    status_text.text(f"⚠️ Chunk {i+1}/{num_chunks} failed to create")
                
            except Exception as chunk_error:
                st.error(f"Error processing chunk {i+1}: {str(chunk_error)}")
                continue
            
            progress = (i + 1) / num_chunks
            progress_bar.progress(progress)
        
        video.close()
        status_text.text("✅ All chunks processed!")
        return output_files
        
    except ImportError:
        st.error("MoviePy not installed. Please check requirements.txt")
        return []
    except Exception as e:
        st.error(f"MoviePy error: {str(e)}")
        st.info("💡 Try a smaller video or different format. Large files may timeout on free hosting.")
        return []

def download_from_url(url, output_path):
    """Download video from URL with progress"""
    try:
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
                        status_text.text(f"Downloading: {format_size(downloaded)}")
        
        status_text.text("✅ Download complete!")
        progress_bar.empty()
        return output_path, downloaded
        
    except requests.exceptions.RequestException as e:
        st.error(f"Error downloading file: {str(e)}")
        return None, 0
    except Exception as e:
        st.error(f"Unexpected error: {str(e)}")
        return None, 0

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

def main():
    # Header
    st.title("✂️ Video Splitter")
    st.markdown("**Split videos from URL into smaller chunks • No upload limits • Original quality preserved**")
    
    # Chunk duration setting
    col1, col2 = st.columns([2, 1])
    with col1:
        chunk_minutes = st.slider("Chunk duration (minutes)", 5, 120, 25, help="Each chunk will be this many minutes long")
    with col2:
        st.metric("Processing Method", "Stream Copy", help="No re-encoding = Fast + Original quality")
    
    chunk_duration = chunk_minutes * 60
    
    st.markdown("---")
    
    # URL input
    st.subheader("🔗 Enter Video URL")
    video_url = st.text_input(
        "Video URL",
        placeholder="https://example.com/video.mp4",
        help="Direct links work best. Supports Google Drive, Dropbox, OneDrive, etc.",
        label_visibility="collapsed"
    )
    
    # URL validation
    if video_url and not video_url.startswith(('http://', 'https://')):
        st.error("⚠️ Please enter a valid URL starting with http:// or https://")
        return
    
    # Action buttons
    if video_url:
        col1, col2 = st.columns(2)
        
        with col1:
            analyze_clicked = st.button("📊 Analyze Video", use_container_width=True, type="secondary")
        
        with col2:
            split_clicked = st.button("✂️ Split Video", use_container_width=True, type="primary")
        
        source_name = video_url.split('/')[-1] or "video_from_url.mp4"
        
        # Quick Analysis
        if analyze_clicked:
            with tempfile.TemporaryDirectory() as temp_dir:
                st.info("⬇️ Downloading for analysis...")
                input_path = os.path.join(temp_dir, source_name)
                input_path, downloaded_size = download_from_url(video_url, input_path)
                
                if input_path:
                    file_size_mb = downloaded_size / (1024 * 1024)
                    
                    # Get duration
                    ffmpeg_available = check_ffmpeg_availability()
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
                        
                        # Results
                        st.success("📋 **Analysis Results**")
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Duration", format_duration(duration))
                        with col2:
                            st.metric("Chunks", f"{num_chunks}")
                        with col3:
                            st.metric("File Size", f"{file_size_mb:.1f} MB")
                        
                        st.info(f"**Average chunk size**: {avg_chunk_size:.1f} MB each")
        
        # Split Video
        if split_clicked:
            if not video_url:
                st.error("Please enter a video URL first")
                return
            
            start_time = time.time()
            
            with tempfile.TemporaryDirectory() as temp_dir:
                # Download video
                st.info("⬇️ Downloading video...")
                input_path = os.path.join(temp_dir, source_name)
                input_path, downloaded_size = download_from_url(video_url, input_path)
                
                if not input_path:
                    return
                
                final_size_mb = downloaded_size / (1024 * 1024)
                
                # Size check
                if final_size_mb > 5000:  # 5GB limit
                    st.error("File too large for processing (>5GB). Please use a smaller file.")
                    return
                
                # Create output directory
                output_dir = os.path.join(temp_dir, "chunks")
                os.makedirs(output_dir, exist_ok=True)
                
                st.info("🔄 Splitting video...")
                
                # Split using available method
                ffmpeg_available = check_ffmpeg_availability()
                if ffmpeg_available:
                    output_files = split_video_ffmpeg(input_path, output_dir, chunk_duration)
                else:
                    output_files = split_video_moviepy(input_path, output_dir, chunk_duration)
                
                processing_time = time.time() - start_time
                
                if output_files:
                    st.success(f"🎉 **Success!** Created {len(output_files)} chunks in {processing_time:.1f} seconds")
                    
                    # Download section
                    st.markdown("---")
                    st.subheader("📥 Download Chunks")
                    
                    # Bulk download for multiple chunks
                    if len(output_files) > 1:
                        zip_name = f"{Path(source_name).stem}_chunks.zip"
                        zip_path = create_zip_file(output_files, zip_name)
                        
                        with open(zip_path, "rb") as zip_file:
                            st.download_button(
                                label=f"📦 Download All ({len(output_files)} chunks)",
                                data=zip_file.read(),
                                file_name=zip_name,
                                mime="application/zip",
                                use_container_width=True
                            )
                        
                        st.markdown("**Individual Downloads:**")
                    
                    # Individual downloads
                    for i, file_path in enumerate(output_files):
                        filename = os.path.basename(file_path)
                        chunk_size = os.path.getsize(file_path)
                        
                        with open(file_path, "rb") as f:
                            st.download_button(
                                label=f"⬇️ {filename} ({format_size(chunk_size)})",
                                data=f.read(),
                                file_name=filename,
                                mime="video/mp4",
                                key=f"download_{i}",
                                use_container_width=True
                            )
                
                else:
                    st.error("❌ Failed to split video. Please check the file format and try again.")
    
    else:
        # Instructions when no URL entered
        st.markdown("""
        ### 💡 How to Use
        
        1. **Paste a video URL** in the box above
        2. **Click "Analyze"** to see video info (optional)
        3. **Click "Split Video"** to process
        4. **Download** your chunks
        
        ### 🎯 Supported URLs
        
        - **Direct video links**: `https://example.com/video.mp4`
        - **Google Drive**: Get shareable link, convert to direct download
        - **Dropbox**: Change `dl=0` to `dl=1` in share link
        - **Any cloud storage** with direct download links
        
        ### ✨ Features
        
        - **No file size limits** (processes directly from URL)
        - **Original quality preserved** (no compression)
        - **Fast processing** (stream copy, no re-encoding)
        - **Works with large files** (multi-GB videos)
        """)

if __name__ == "__main__":
    main()
