from flask import Flask, request, send_file, render_template
import yt_dlp
from io import BytesIO
import tempfile
import os

app = Flask(__name__)  # No need to override folders now

# Serve the homepage
@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")

# Handle downloads
@app.route("/download", methods=["POST"])
def download():
    url = request.form["url"]
    file_type = request.form["type"]
    quality = request.form["quality"]
    abitrate = request.form.get("abitrate", "128")

    with tempfile.TemporaryDirectory() as tmpdir:
        outtmpl = os.path.join(tmpdir, "output.%(ext)s")

        if file_type == "audio":
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": abitrate,
                    }
                ],
                "quiet": True,
            }
        else:
            if quality == "best":
                format_str = "bestvideo+bestaudio/best"
            else:
                format_str = f"bestvideo[height={quality}]+bestaudio/best"

            ydl_opts = {
                "format": format_str,
                "outtmpl": outtmpl,
                "merge_output_format": "mp4",
                "quiet": True,
            }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if file_type == "audio":
                final_filename = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp3"
            else:
                final_filename = ydl.prepare_filename(info).rsplit(".", 1)[0] + ".mp4"

        buffer = BytesIO()
        with open(final_filename, "rb") as f:
            buffer.write(f.read())
        buffer.seek(0)

    download_name = os.path.basename(final_filename)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=download_name,
        mimetype="audio/mpeg" if file_type == "audio" else "video/mp4"
    )

if __name__ == "__main__":
    app.run(debug=True)
