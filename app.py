from flask import Flask, request, send_file, render_template, Response, jsonify
import yt_dlp
import os
import threading
import uuid
import json
import logging

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# In-memory "database" to store job progress and final file path.
jobs = {}

def run_download(url, file_type, quality, abitrate, job_id):
    """The actual download logic that will run in a separate thread."""
    
    def progress_hook(d):
        if d['status'] == 'downloading':
            total_bytes = d.get('total_bytes') or d.get('total_bytes_est')
            downloaded_bytes = d.get('downloaded_bytes')
            
            if total_bytes and downloaded_bytes is not None:
                percent = (downloaded_bytes / total_bytes) * 100
                
                # Logic to identify the current stream based on video codec
                info_dict = d.get('info_dict', {})
                stream_type = 'video' if info_dict.get('vcodec') != 'none' else 'audio'
                
                jobs[job_id]['progress'] = percent
                jobs[job_id]['status'] = 'downloading'
                jobs[job_id]['current_stream_type'] = stream_type


        elif d['status'] == 'finished':
            # have to use logging here
            logging.info(f"Job {job_id} finished a stream, now processing or downloading next...")
            jobs[job_id]['progress'] = 100
            # jobs[job_id]['last_printed_percent'] = -1

    output_dir = os.path.join(os.getcwd(), 'downloads')
    os.makedirs(output_dir, exist_ok=True)
    outtmpl = os.path.join(output_dir, f"{job_id}.%(ext)s")

    if file_type == "audio":
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": abitrate,
            }],
            "progress_hooks": [progress_hook],
        }
    else:
        format_str = "bestvideo+bestaudio/best" if quality == "best" else f"bestvideo[height={quality}]+bestaudio/best"
        ydl_opts = {
            "format": format_str,
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
        }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            jobs[job_id]['status'] = 'processing'
            info = ydl.extract_info(url, download=True)
            final_ext = "mp3" if file_type == "audio" else "mp4"
            final_filename = os.path.join(output_dir, f"{job_id}.{final_ext}")
            
            jobs[job_id]['status'] = 'complete'
            jobs[job_id]['filepath'] = final_filename
            jobs[job_id]['filename'] = ydl.prepare_filename(info).rsplit(os.sep, 1)[-1].rsplit('.', 1)[0] + f'.{final_ext}'
    except Exception as e:
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['error'] = str(e)

@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

@app.route("/download", methods=["POST"])
def download():
    """Starts the download in a background thread and returns a job ID."""
    url = request.form["url"]
    file_type = request.form["type"]
    quality = request.form["quality"]
    abitrate = request.form.get("abitrate", "128")
    
    job_id = str(uuid.uuid4())
    jobs[job_id] = {'status': 'starting', 'progress': 0, 'type': file_type}

    thread = threading.Thread(target=run_download, args=(url, file_type, quality, abitrate, job_id))
    thread.start()

    return jsonify({"job_id": job_id})

@app.route("/progress/<job_id>")
def progress(job_id):
    """Streams progress updates to the client."""
    def generate():
        while True:
            job = jobs.get(job_id, {})
            status = job.get('status', 'unknown')
            progress = job.get('progress', 0)
            
            stream_type = job.get('current_stream_type', job.get('type', 'file'))
            data = {'status': status, 'progress': progress, 'stream_type': stream_type}
            
            is_job_finished = False
            if status == 'complete':
                data['filename'] = job.get('filename')
                is_job_finished = True
            elif status == 'error':
                data['error'] = job.get('error')
                is_job_finished = True
            
            yield f"data: {json.dumps(data)}\n\n"
            
            if is_job_finished:
                break

            threading.Event().wait(0.1)

    return Response(generate(), mimetype='text/event-stream')

# Replace your entire @app.route("/get-file/<job_id>") function with this

from flask import after_this_request

@app.route("/get-file/<job_id>")
def get_file(job_id):
    """Serves the final downloaded file and schedules it for cleanup."""
    job = jobs.get(job_id)
    if job and job.get('status') == 'complete':
        filepath = job.get('filepath')
        filename = job.get('filename')
        mimetype = "audio/mpeg" if filename.endswith('.mp3') else "video/mp4"

        @after_this_request
        def cleanup(response):
            """This function runs after the request is fully served."""
            try:
                if job_id in jobs:
                    del jobs[job_id]
                    logging.info(f"Cleaned up job {job_id}.")
                if os.path.exists(filepath):
                    os.remove(filepath)
                    logging.info(f"Deleted file {filepath}.")
            except Exception as e:
                logging.error(f"Error during cleanup for job {job_id}: {e}")
            return response

        return send_file(filepath, as_attachment=True, download_name=filename, mimetype=mimetype)
    
    return "File not found or download not complete.", 404

if __name__ == "__main__":
    app.run(debug=True)