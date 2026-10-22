from __future__ import annotations
import ipaddress, json, mimetypes, os, re, shutil, subprocess, threading, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import quote, unquote, urlparse

ROOT = Path(__file__).resolve().parent
STATIC, DOWNLOADS = ROOT / 'static', ROOT / 'downloads'
DOWNLOADS.mkdir(exist_ok=True)
JOBS, LOCK = {}, threading.Lock()

def valid_url(value):
    if not isinstance(value, str) or len(value) > 4096: raise ValueError('Enter a valid video URL.')
    value = value.strip(); parsed = urlparse(value)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname: raise ValueError('Use a full http:// or https:// video URL.')
    if parsed.username or parsed.password: raise ValueError('URLs containing embedded credentials are not supported.')
    host = parsed.hostname.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')): raise ValueError('Local network URLs are not supported.')
    try:
        addr = ipaddress.ip_address(host.strip('[]'))
        if not addr.is_global: raise ValueError('Private and local network addresses are not supported.')
    except ValueError as error:
        if 'not supported' in str(error): raise
    return value

def safe_name(name):
    return (re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(' .') or 'download')[:180]

def run_job(job_id, url, mode, quality):
    try:
        try: import yt_dlp
        except ImportError: raise RuntimeError('yt-dlp is not installed. Run: pip install -r requirements.txt')
        if mode == 'audio' and not shutil.which('ffmpeg'): raise RuntimeError('FFmpeg is required for MP3 conversion. Install FFmpeg and restart the app.')
        local_deno = ROOT / 'runtime' / 'node_modules' / 'deno' / 'deno.exe'
        if local_deno.is_file(): os.environ['PATH'] = str(local_deno.parent) + os.pathsep + os.environ.get('PATH', '')
        host = (urlparse(url).hostname or '').lower()
        is_youtube = host == 'youtu.be' or host.endswith(('youtube.com', 'youtube-nocookie.com'))
        node = shutil.which('node')
        node_22 = False
        if node:
            try: node_22 = int(subprocess.check_output([node, '--version'], text=True, timeout=3).strip().lstrip('v').split('.')[0]) >= 22
            except (OSError, ValueError, subprocess.SubprocessError): pass
        if is_youtube and not shutil.which('deno') and not node_22:
            raise RuntimeError('YouTube needs Deno or Node.js 22+. Install Deno or upgrade Node.js, then restart Local Media.')
        def hook(data):
            with LOCK:
                job = JOBS.get(job_id)
                if not job: return
                if data.get('status') == 'downloading':
                    total = data.get('total_bytes') or data.get('total_bytes_estimate') or 0
                    done = data.get('downloaded_bytes') or 0
                    job.update(state='downloading', percent=round(done * 100 / total, 1) if total else None, eta=data.get('eta'))
                elif data.get('status') == 'finished': job.update(state='processing', percent=100)
        options = {'noplaylist': True, 'outtmpl': str(DOWNLOADS / '%(title).180B [%(id)s].%(ext)s'), 'windowsfilenames': True,
                   'progress_hooks': [hook], 'quiet': True, 'no_warnings': True, 'socket_timeout': 30, 'retries': 2,
                   'max_filesize': 2 * 1024 * 1024 * 1024}
        if node_22 and not shutil.which('deno'): options['js_runtimes'] = {'node': {}}
        if mode == 'audio':
            options.update(format='bestaudio/best', postprocessors=[{'key':'FFmpegExtractAudio','preferredcodec':'mp3','preferredquality':quality}])
        else:
            options.update(format=f'best[ext=mp4][height<={quality}]/best[height<={quality}]/best', merge_output_format='mp4')
        before = set(DOWNLOADS.iterdir())
        with yt_dlp.YoutubeDL(options) as ydl: info = ydl.extract_info(url, download=True)
        changed = [p for p in DOWNLOADS.iterdir() if p.is_file() and (p not in before or p.stat().st_mtime > JOBS[job_id].get('started', 0))]
        if not changed: raise RuntimeError('The download finished without producing a file.')
        output = max(changed, key=lambda p:p.stat().st_mtime)
        with LOCK: JOBS[job_id].update(state='complete', percent=100, filename=output.name, title=safe_name(info.get('title') or 'download'), size=output.stat().st_size)
    except Exception as error:
        with LOCK:
            if job_id in JOBS: JOBS[job_id].update(state='error', error=(str(error).strip().splitlines()[0] or 'Download failed.')[:240])

class Handler(BaseHTTPRequestHandler):
    server_version = 'LocalMedia/1.0'
    def send_json(self, data, status=200):
        body=json.dumps(data).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(body))); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        path=urlparse(self.path).path
        if path == '/api/health':
            try: import yt_dlp; ready=True
            except ImportError: ready=False
            self.send_json({'ready':ready,'ffmpeg':bool(shutil.which('ffmpeg'))}); return
        if path.startswith('/api/jobs/'):
            with LOCK: job=dict(JOBS.get(path.rsplit('/',1)[-1],{}))
            self.send_json(job or {'error':'Job not found.'}, 200 if job else 404); return
        if path.startswith('/api/files/'):
            name=unquote(path.removeprefix('/api/files/')); target=(DOWNLOADS/name).resolve()
            if target.parent != DOWNLOADS.resolve() or not target.is_file(): self.send_error(404); return
            self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(name)[0] or 'application/octet-stream'); self.send_header('Content-Length',str(target.stat().st_size)); self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+quote(name)); self.end_headers()
            with target.open('rb') as file: shutil.copyfileobj(file,self.wfile)
            return
        target=STATIC/'index.html' if path in ('/','/index.html') else (STATIC/path.lstrip('/')).resolve()
        if target != STATIC.resolve() and STATIC.resolve() not in target.parents: self.send_error(404); return
        if not target.is_file(): self.send_error(404); return
        body=target.read_bytes(); self.send_response(200); self.send_header('Content-Type',mimetypes.guess_type(target.name)[0] or 'application/octet-stream'); self.send_header('Content-Length',str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        if urlparse(self.path).path != '/api/download': self.send_json({'error':'Not found.'},404); return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 8192: raise ValueError('Request is empty or too large.')
            payload=json.loads(self.rfile.read(length)); url=valid_url(payload.get('url')); mode=payload.get('mode'); quality=str(payload.get('quality','1080'))
            if mode not in ('video','audio'): raise ValueError('Choose video or MP3 audio.')
            if quality not in (('128','192','320') if mode=='audio' else ('720','1080','2160')): raise ValueError('Choose a supported quality.')
        except (ValueError,json.JSONDecodeError) as error: self.send_json({'error':str(error)},400); return
        with LOCK:
            if sum(j['state'] in ('queued','downloading','processing') for j in JOBS.values()) >= 2: self.send_json({'error':'Two downloads are already running. Try again shortly.'},429); return
            job_id=uuid.uuid4().hex; JOBS[job_id]={'id':job_id,'state':'queued','percent':0,'mode':mode,'started':__import__('time').time()}
        threading.Thread(target=run_job,args=(job_id,url,mode,quality),daemon=True).start(); self.send_json({'id':job_id},202)

if __name__ == '__main__':
    host=os.environ.get('HOST','127.0.0.1'); port=int(os.environ.get('PORT','8765'))
    print(f'Local media downloader: http://{host}:{port}')
    ThreadingHTTPServer((host,port),Handler).serve_forever()



