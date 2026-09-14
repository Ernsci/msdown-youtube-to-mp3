import os
import json
import time
import uuid
import zipfile
import threading
import subprocess
from flask import Flask, render_template, request, jsonify, send_file, abort, send_from_directory
from downloader import fetch_complete_info, normalize_url, detect_source

app = Flask(__name__, static_folder='web', template_folder='web')

JOB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'jobs')
os.makedirs(JOB_DIR, exist_ok=True)

jobs = {}

@app.route('/')
def index():
    return send_from_directory('web', 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    return send_from_directory('web', path)

@app.route('/api/info', methods=['POST'])
def api_info():
    url = request.json.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    url = normalize_url(url)
    info = fetch_complete_info(url)
    if info:
        return jsonify({
            'title': info.get('title', 'Unknown'),
            'channel': info.get('channel', ''),
            'upload_date': info.get('upload_date', ''),
            'duration': info.get('duration'),
            'view_count': info.get('view_count'),
            'like_count': info.get('like_count'),
            'comment_count': info.get('comment_count'),
            'category': info.get('category', ''),
            'tags': info.get('tags', []),
            'description': info.get('description', ''),
            'is_playlist': info.get('is_playlist', False),
            'playlist_count': info.get('playlist_count', 0) if info.get('is_playlist') else 1,
            'source': info.get('source', 'Unknown'),
            'entries': info.get('entries', []) if info.get('is_playlist') else [],
        })
    return jsonify({'error': 'Could not fetch info'}), 400

@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.json
    url = normalize_url(data.get('url', '').strip())
    if not url:
        return jsonify({'error': 'No URL provided'}), 400

    job_id = str(uuid.uuid4())
    job_path = os.path.join(JOB_DIR, job_id)
    os.makedirs(job_path, exist_ok=True)

    job = {
        'id': job_id,
        'url': url,
        'status': 'queued',
        'progress': 0,
        'message': 'Queued',
        'output_dir': job_path,
        'zip_path': None,
        'created_at': time.time(),
    }
    jobs[job_id] = job

    thread = threading.Thread(
        target=_process_job,
        args=(job_id, url, job_path),
        daemon=True
    )
    thread.start()

    return jsonify({'job_id': job_id, 'status': 'queued'})

@app.route('/api/status/<job_id>')
def api_status(job_id):
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify({
        'id': job['id'],
        'status': job['status'],
        'progress': job['progress'],
        'message': job['message'],
        'zip_path': job.get('zip_path'),
    })

@app.route('/api/download/<job_id>')
def api_download_zip(job_id):
    job = jobs.get(job_id)
    if not job:
        abort(404)
    zip_path = job.get('zip_path')
    if not zip_path or not os.path.exists(zip_path):
        abort(404)
    return send_file(
        zip_path,
        as_attachment=True,
        download_name=f'{os.path.basename(zip_path)}.zip',
        mimetype='application/zip'
    )

@app.route('/api/cleanup/<job_id>', methods=['DELETE'])
def api_cleanup(job_id):
    job = jobs.get(job_id)
    if job:
        job_dir = job.get('output_dir')
        if job_dir and os.path.exists(job_dir):
            import shutil
            shutil.rmtree(job_dir, ignore_errors=True)
        zip_path = job.get('zip_path')
        if zip_path and os.path.exists(zip_path):
            os.remove(zip_path)
        del jobs[job_id]
    return jsonify({'success': True})

def _process_job(job_id, url, job_path):
    job = jobs[job_id]
    job['status'] = 'downloading'
    job['progress'] = 0
    job['message'] = 'Fetching playlist info...'

    from downloader import YouTubeDownloader, format_number

    downloader = YouTubeDownloader()
    downloader.progress_callback = lambda d, t: _update_progress(job, d, t)
    downloader.status_callback = lambda m: _update_status(job, m)

    try:
        output_dir = os.path.join(job_path, 'mp3s')
        os.makedirs(output_dir, exist_ok=True)

        downloader.download_playlist(url, output_dir)

        if job['status'] == 'cancelled':
            return

        mp3_files = [f for f in os.listdir(output_dir) if f.endswith('.mp3')]
        if not mp3_files:
            job['status'] = 'failed'
            job['message'] = 'No MP3 files were created'
            return

        zip_path = os.path.join(job_path, 'download.zip')
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for mp3_file in mp3_files:
                zf.write(os.path.join(output_dir, mp3_file), mp3_file)

        job['zip_path'] = zip_path
        job['status'] = 'complete'
        job['progress'] = 100
        job['message'] = f'Complete! {len(mp3_files)} MP3 files zipped.'
    except Exception as e:
        job['status'] = 'failed'
        job['message'] = f'Error: {str(e)}'
        job['progress'] = 0

def _update_progress(job, downloaded, total):
    if total > 0:
        pct = int(min(downloaded / total * 100, 100))
        job['progress'] = pct
        job['message'] = f'Downloading... {pct}%'

def _update_status(job, message):
    job['message'] = message

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
