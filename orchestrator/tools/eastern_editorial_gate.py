"""Feed exact independently rejected media into the normal replacement/preflight loop."""
import hashlib,json,copy

def install(work):
    from orchestrator.stages import preflight,archive
    def rejected_media():
        p=work/'editorial-source-findings.json'
        findings=json.loads(p.read_text(encoding='utf-8'))['findings'] if p.exists() else []
        return {f['media_sha256']:f['path']+': '+f['why'] for f in findings if f['decision']=='reject'}
    original=preflight._initial_bad
    def initial(pairs,d):
        bad=dict(original(pairs,d))
        rejected=rejected_media()
        hashes={}
        for n,(_,sl) in enumerate(pairs,1):
            for name in (sl.get('image'),sl.get('src')):
                if not name:continue
                path=d/name
                if path.is_file():
                    if name not in hashes:
                        with path.open('rb') as f:hashes[name]=hashlib.file_digest(f,'sha256').hexdigest()
                    sha=hashes[name]
                    if sha in rejected:bad[n]='Independent editorial review: '+rejected[sha]
        return bad
    preflight._initial_bad=initial
    apply_photo=archive._apply_photo
    def photo(slot,d,candidate,result):
        before=copy.deepcopy(slot)
        old_path=d/before['image'] if before.get('image') else None
        old_bytes=old_path.read_bytes() if old_path and old_path.is_file() else None
        ok=apply_photo(slot,d,candidate,result)
        if not ok or not slot.get('image'):return ok
        path=d/slot['image']
        with path.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
        if sha not in rejected_media():return True
        slot.clear();slot.update(before)
        slot.setdefault('_tried',[]).append(candidate['key'])
        if old_bytes is not None and old_path==path:old_path.write_bytes(old_bytes)
        print('[editorial-reject] '+slot.get('id','?')+': previously rejected exact source bytes',flush=True)
        return False
    archive._apply_photo=photo
