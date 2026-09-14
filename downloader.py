import os
import re
import threading
import yt_dlp
try:
    import imageio_ffmpeg
    IMAGEIO_FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
except ImportError:
    IMAGEIO_FFMPEG = None

def normalize_url(url):
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url

def detect_source(url):
    if 'music.youtube.com' in url:
        return 'YouTube Music'
    elif 'youtube.com' in url:
        return 'YouTube'
    return 'Unknown'

def format_number(n):
    if not n:
        return '0'
    n = int(n)
    if n >= 1_000_000:
        return f'{n/1_000_000:.1f}M'
    elif n >= 1_000:
        return f'{n/1_000:.1f}K'
    return str(n)

def format_duration(seconds):
    if not seconds:
        return 'N/A'
    s = int(seconds)
    h = s // 3600
    m = (s % 3600) // 60
    if h > 0:
        return f'{h}:{m:02d}:{s % 60:02d}'
    return f'{m}:{s % 60:02d}'

class YouTubeDownloader:
    def __init__(self):
        self._cancel_flag = False
        self._thread = None
        self.progress_callback = None
        self.status_callback = None
        self.complete_callback = None
        self.error_callback = None

    def _set_status(self, msg):
        if self.status_callback:
            self.status_callback(msg)

    def _set_progress(self, downloaded, total):
        if self.progress_callback:
            self.progress_callback(downloaded, total)

    def cancel(self):
        self._cancel_flag = True

    def _find_ffmpeg(self):
        if IMAGEIO_FFMPEG and os.path.exists(IMAGEIO_FFMPEG):
            return IMAGEIO_FFMPEG
        for path in [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg.exe'),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bin', 'ffmpeg.exe'),
        ]:
            if os.path.exists(path):
                return path
        for p in os.environ.get('PATH', '').split(os.pathsep):
            p = p.strip('"')
            f = os.path.join(p, 'ffmpeg.exe')
            if os.path.exists(f):
                return f
            f = os.path.join(p, 'bin', 'ffmpeg.exe')
            if os.path.exists(f):
                return f
        return None

    def download_playlist(self, url, output_dir, format_preference='bestaudio'):
        self._cancel_flag = False
        self._set_status('Fetching playlist info...')

        ffmpeg_path = self._find_ffmpeg()
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'forcejson': False,
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'format': format_preference,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'progress_hooks': [self._progress_hook],
            'noprogress': False,
            'writethumbnail': False,
        }
        if ffmpeg_path:
            ydl_opts['ffmpeg_location'] = os.path.dirname(ffmpeg_path)

        try:
            self._set_status('Downloading and converting...')
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                playlist_info = ydl.extract_info(url, download=True)

                if self._cancel_flag:
                    self._set_status('Cancelled.')
                    return

                if playlist_info and 'entries' in playlist_info:
                    video_count = len(playlist_info['entries'])
                    self._set_status(f'Playlist complete! {video_count} videos processed.')
                else:
                    self._set_status('Download complete!')

                if self.complete_callback:
                    self.complete_callback(output_dir)

        except yt_dlp.utils.DownloadError as e:
            self._set_status(f'Error: {str(e)}')
            if self.error_callback:
                self.error_callback(str(e))
        except Exception as e:
            self._set_status(f'Error: {str(e)}')
            if self.error_callback:
                self.error_callback(str(e))

    def _progress_hook(self, d):
        if self._cancel_flag:
            raise Exception('Download cancelled by user')

        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                self._set_progress(downloaded, total)
        elif d['status'] == 'finished':
            self._set_status('Finished downloading, converting to MP3...')

    def download_playlist_async(self, url, output_dir, format_preference='bestaudio'):
        self._thread = threading.Thread(
            target=self.download_playlist,
            args=(url, output_dir, format_preference),
            daemon=True
        )
        self._thread.start()
        return self._thread


def fetch_complete_info(url):
    url = normalize_url(url)
    source = detect_source(url)
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'writethumbnail': False,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None

            is_playlist = 'entries' in info and info.get('playlist_count', 0) > 0

            base = {
                'title': info.get('title', 'Unknown'),
                'description': info.get('description', ''),
                'channel': info.get('channel', info.get('uploader', 'Unknown')),
                'channel_url': info.get('channel_url', ''),
                'uploader_url': info.get('uploader_url', ''),
                'upload_date': info.get('upload_date', ''),
                'duration': info.get('duration'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'dislike_count': info.get('dislike_count'),
                'average_rating': info.get('average_rating'),
                'comment_count': info.get('comment_count'),
                'age_limit': info.get('age_limit', 0),
                'category': info.get('category', ''),
                'tags': info.get('tags', []),
                'thumbnail': info.get('thumbnail', ''),
                'extractor': info.get('extractor', ''),
                'extractor_key': info.get('extractor_key', ''),
                'webpage_url': info.get('webpage_url', url),
                'url': url,
                'source': source,
                'is_playlist': is_playlist,
                'is_single': not is_playlist,
            }

            if is_playlist:
                base['playlist_title'] = info.get('title', 'Unknown')
                base['playlist_description'] = info.get('description', '')
                base['playlist_count'] = info.get('playlist_count') or len(info.get('entries', []))
                base['playlist_uploader'] = info.get('playlist_uploader', '')
                base['playlist_uploader_url'] = info.get('playlist_uploader_url', '')
                base['entries'] = []
                entries = info.get('entries', [])
                for i, entry in enumerate(entries):
                    if entry:
                        base['entries'].append({
                            'title': entry.get('title', f'Video {i+1}'),
                            'duration': entry.get('duration'),
                            'view_count': entry.get('view_count'),
                            'upload_date': entry.get('upload_date', ''),
                            'channel': entry.get('channel', entry.get('uploader', '')),
                        })
            return base
    except Exception:
        pass
    return None