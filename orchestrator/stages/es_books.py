"""Книги как источник для испанского канала (владелец 13.10.2026: «я сам буду закидывать книги»).

Папка data/books/<ТИКЕР>/ (тикер темы из stories_es.txt, например GOOGL-ES): PDF или EPUB. Текст книги режется на куски ~10 тыс. слов,
из каждого модель выписывает факты истории компании — даты, события, люди, числа, живые сцены — СВОИМИ СЛОВАМИ (цитаты не длиннее
15 слов, с автором). Факты получают id B1, B2… и источник «book: Название — Автор» и идут в ресёрч вместе с интернет-источниками.
Текст книг в сценарий не копируется; в описании ролика книги указываются как источники."""
import json, re, hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from .. import config, llm

CHUNK_WORDS = 10000

ASK = """Это фрагмент книги «{title}». Выпиши факты об истории компании {company} и её основателей, которые пригодятся для документального
рассказа: даты, события, решения, люди, числа, конкретные живые сцены и детали (где, кто, что сделал, что сказал).
Пиши факты по-английски СВОИМИ СЛОВАМИ (не копируй предложения книги); прямая цитата — только короткая (до 15 слов) и с тем, кто сказал.
Не выписывай рассуждения автора и оценки — только то, что произошло. 10–40 фактов, по одному событию на факт.
Фрагмент:
{text}

Верни JSON: {{"facts": [{{"date": "1998-09", "claim": "...", "quote": "", "number": "", "people": ["..."]}}]}}"""


def _text(path: Path) -> str:
    cache = path.with_suffix(path.suffix + ".txt")
    if cache.exists(): return cache.read_text(encoding="utf-8")
    if path.suffix.lower() == ".pdf":
        import pypdf
        r = pypdf.PdfReader(str(path)); t = "\n".join((pg.extract_text() or "") for pg in r.pages)
    elif path.suffix.lower() == ".epub":
        import zipfile, html
        with zipfile.ZipFile(path) as z:
            parts = [z.read(n).decode("utf-8", "ignore") for n in sorted(z.namelist()) if n.endswith((".xhtml", ".html", ".htm"))]
        t = "\n".join(html.unescape(re.sub(r"<[^>]+>", " ", p)) for p in parts)
    else: t = path.read_text(encoding="utf-8", errors="ignore")
    t = re.sub(r"(OceanofPDF\.com|http://yanko\.lib\.ru|\|\|)", " ", t)   # служебные приписки файлов
    cache.write_text(t, encoding="utf-8"); return t


def books(ticker: str) -> list[Path]:
    d = config.DATA / "books" / ticker
    return sorted(p for p in d.glob("*") if p.suffix.lower() in (".pdf", ".epub", ".txt") and not p.name.endswith(".pdf.txt") and not p.name.endswith(".epub.txt")) if d.exists() else []


def facts(ticker: str, company: str, vid: str = "") -> tuple[list[dict], list[str]]:
    """Факты всех книг темы (с кэшем на диске рядом с книгой) и список названий для описания."""
    out, titles = [], []
    for p in books(ticker):
        title = p.stem; titles.append(title)
        cache = p.with_suffix(".facts.json")
        words = _text(p).split()
        key = hashlib.sha1(f"{len(words)}|{company}|v1".encode()).hexdigest()[:12]
        got = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
        if got.get("key") != key:
            chunks = [" ".join(words[k:k + CHUNK_WORDS]) for k in range(0, len(words), CHUNK_WORDS)]
            def one(i):
                try:
                    return llm.ask_json(ASK.format(title=title, company=company, text=chunks[i]), heavy=True, max_tokens=8000,
                                        tag=f"es_book_{ticker}_{i}").get("facts") or []
                except Exception as e:
                    print(f"[books] {title} кусок {i + 1}: {str(e)[:100]}", flush=True); return []
            with ThreadPoolExecutor(6) as ex: res = [f for part in ex.map(one, range(len(chunks))) for f in part]
            got = {"key": key, "facts": res}; cache.write_text(json.dumps(got, ensure_ascii=False, indent=1), encoding="utf-8")
            print(f"[books] {title}: {len(words)} слов, кусков {len(chunks)}, фактов {len(res)}", flush=True)
        for f in got["facts"]:
            if isinstance(f, dict) and f.get("claim"):
                out.append({**f, "source_url": f"book: {title}", "source": title})
    for i, f in enumerate(out, 1): f["id"] = f"B{i}"
    return out, titles
