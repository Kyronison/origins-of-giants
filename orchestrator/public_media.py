"""A temporary Remotion public directory containing only referenced assets."""
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def public_view(source, props, temp_root):
    source = Path(source).resolve()
    temp_root = Path(temp_root).resolve()
    temp_root.mkdir(parents=True, exist_ok=True)
    public = Path(tempfile.mkdtemp(prefix='media-public-', dir=temp_root)).resolve()
    if public.parent != temp_root:
        raise RuntimeError('Public directory escaped its temporary root')
    references = {'words.json'}
    timeline = props.get('timeline', {})
    if timeline and timeline.get('voice') is not False:
        references.add(timeline.get('voice_src') or 'voice.mp3')
    suffixes = {'.png', '.jpg', '.jpeg', '.webp', '.gif', '.svg', '.avif',
                '.mp4', '.mov', '.webm', '.mp3', '.wav', '.m4a', '.aac',
                '.ogg', '.json', '.ttf', '.woff', '.woff2', '.srt', '.vtt'}
    def walk(value):
        if isinstance(value, dict):
            for item in value.values(): walk(item)
        elif isinstance(value, list):
            for item in value: walk(item)
        elif isinstance(value, str) and len(value) < 512 and '://' not in value:
            if Path(value).suffix.lower() in suffixes: references.add(value)
    walk(props)
    try:
        for reference in references:
            rel = Path(reference)
            if rel.is_absolute() or any(x.startswith('.') for x in rel.parts): continue
            src = (source / rel).resolve()
            if not src.is_relative_to(source): raise RuntimeError('Media escaped its source directory')
            if not src.is_file(): continue  # Missing media is handled by render guards.
            dest = public / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        yield public
    finally:
        if public.parent != temp_root or not public.name.startswith('media-public-'):
            raise RuntimeError('Unsafe public-directory cleanup target')
        shutil.rmtree(public, ignore_errors=True)
