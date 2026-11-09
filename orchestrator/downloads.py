"""Verified, resumable range downloads for the fal CDN's small-response route."""
import hashlib
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor

import requests
from . import config

_slots = threading.BoundedSemaphore(8)
STEP = 16384

def fal_ranges(url, timeout=30):
    cache = config.DATA / 'cache/downloads' / hashlib.sha256(url.encode()).hexdigest()
    cache.mkdir(parents=True, exist_ok=True)
    meta_path = cache / 'meta.json'
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else None

    def fetch(start, end, total=None, etag=None):
        path = cache / f'{start}.bin'
        if total is not None and path.exists() and path.stat().st_size == end-start+1:
            return path.read_bytes(), None
        for attempt in range(3):
            try:
                headers = {'Range': f'bytes={start}-{end}'}
                if etag: headers['If-Range'] = etag
                with _slots:
                    r = requests.get(url, headers=headers, timeout=(20, min(timeout, 30)))
                r.raise_for_status()
                if r.status_code == 200 and start == 0:
                    return r.content, {'whole': True}
                span = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', r.headers.get('Content-Range', ''))
                if r.status_code != 206 or not span:
                    raise RuntimeError('CDN did not provide a valid byte range')
                a, b, size = map(int, span.groups())
                if a != start or b != min(end,size-1) or len(r.content) != b-a+1:
                    raise RuntimeError('CDN returned an incomplete or wrong byte range')
                if total is not None and size != total: raise RuntimeError('CDN resource changed size')
                if etag and r.headers.get('ETag') != etag: raise RuntimeError('CDN resource changed ETag')
                path.write_bytes(r.content)
                return r.content, {'size': size, 'etag': r.headers.get('ETag')}
            except Exception:
                if attempt == 2: raise

    if meta is None:
        first, meta = fetch(0, STEP-1)
        if meta.get('whole'): return first
        meta_path.write_text(json.dumps(meta))
    else:
        first, _ = fetch(0, min(STEP-1,meta['size']-1), meta['size'], meta.get('etag'))
    size = meta['size']
    def piece(start):
        return fetch(start, min(size-1,start+STEP-1), size, meta.get('etag'))[0]
    with ThreadPoolExecutor(8) as pool:
        body = first + b''.join(pool.map(piece, range(STEP,size,STEP)))
    if len(body) != size: raise RuntimeError('Incomplete fal CDN download')
    return body
