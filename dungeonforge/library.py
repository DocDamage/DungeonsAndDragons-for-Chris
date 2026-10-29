"""Local campaign and rules library, with incremental, page-cited text search."""

import hashlib
from contextlib import contextmanager
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import zipfile


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FOLDERS = {
    "2e": {"directory": "2e", "title": "AD&D 2nd Edition", "edition": "2e", "kind": "rules"},
    "3.5e": {"directory": "3.5e", "title": "D&D 3.5 Edition", "edition": "3.5e", "kind": "rules"},
    "5e": {"directory": "5e", "title": "D&D 5th Edition", "edition": "5e", "kind": "rules"},
    "strahd": {"directory": "curse of straud", "title": "Curse of Strahd Reloaded", "edition": "5e", "kind": "campaign"},
    "marvel": {"directory": "marvel", "title": "Marvel 5e", "edition": "5e", "kind": "setting"},
    "minecraft": {"directory": "minecraft", "title": "Minecraft / Lightning Keep", "edition": "5e", "kind": "campaign"},
    "rick_and_morty": {"directory": "rick and morty", "title": "The Lost Dungeon of Rickedness", "edition": "5e", "kind": "campaign"},
    "star_wars": {"directory": "star wars", "title": "Star Wars WEG 2nd Edition (D6)", "edition": "weg_d6", "kind": "rules"},
}


class SourceLibrary:
    def __init__(self, root=None, db_path=None):
        self.root = Path(root or os.environ.get("DUNGEONFORGE_LIBRARY_DIR", PROJECT_ROOT.parent)).resolve()
        self.db_path = Path(db_path or PROJECT_ROOT / "library.sqlite3")
        self._job_lock = threading.Lock()
        self._job = {"running": False, "completed": 0, "total": 0, "current": "", "error": None}
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS sources (
                    id TEXT PRIMARY KEY, folder_id TEXT NOT NULL, title TEXT NOT NULL,
                    path TEXT NOT NULL, file_path TEXT NOT NULL, edition TEXT NOT NULL,
                    signature TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    pages INTEGER NOT NULL DEFAULT 0, chunks INTEGER NOT NULL DEFAULT 0,
                    error TEXT, indexed_at REAL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(
                    source_id UNINDEXED, section UNINDEXED, text,
                    tokenize='unicode61 remove_diacritics 2'
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def resolve(self, relative_path):
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Source must be inside the library folder.")
        return path

    @staticmethod
    def _book_key(path):
        stem = re.sub(r"(?:_djvu|_text)$", "", path.stem, flags=re.I)
        return re.sub(r"[^a-z0-9]", "", stem.lower())

    def discover(self, folder_id=None):
        if folder_id is not None and folder_id not in FOLDERS:
            raise ValueError("Unknown library folder.")
        sources = []
        for fid, info in FOLDERS.items():
            if folder_id is not None and fid != folder_id:
                continue
            directory = self.resolve(info["directory"])
            if not directory.is_dir():
                continue
            groups = {}
            for path in sorted(directory.rglob("*")):
                if not path.is_file() or not path.resolve().is_relative_to(self.root):
                    continue
                if any(part.startswith(".") for part in path.relative_to(directory).parts):
                    continue
                suffix = path.suffix.lower()
                if suffix not in {".pdf", ".txt", ".md", ".zip"}:
                    continue
                if suffix == ".zip" and any(marker in path.stem.lower() for marker in ("_jp2", "_daisy")):
                    continue
                groups.setdefault(self._book_key(path), []).append(path)
            for key, paths in sorted(groups.items()):
                # Existing OCR text is faster and usually cleaner than extracting a scan.
                selected = min(paths, key=lambda p: ({".txt": 0, ".md": 1, ".pdf": 2, ".zip": 3}[p.suffix.lower()], str(p)))
                view_path = next((p for p in paths if p.suffix.lower() == ".pdf"), selected)
                stat = selected.stat()
                sources.append({
                    "id": hashlib.sha256(f"{fid}/{key}".encode()).hexdigest()[:24],
                    "folder_id": fid,
                    "title": re.sub(r"(?:_djvu|_text)$", "", selected.stem, flags=re.I).replace("_", " "),
                    "path": selected.relative_to(self.root).as_posix(),
                    "file_path": view_path.relative_to(self.root).as_posix(),
                    "edition": info["edition"],
                    "signature": f"{selected.relative_to(self.root)}:{stat.st_size}:{stat.st_mtime_ns}",
                })
        return sources

    def catalog(self):
        discovered = self.discover()
        with self.connect() as db:
            stored = {row["id"]: dict(row) for row in db.execute("SELECT * FROM sources")}
        folders = []
        for folder_id, info in FOLDERS.items():
            docs = []
            for source in discovered:
                if source["folder_id"] != folder_id:
                    continue
                previous = stored.get(source["id"], {})
                fresh = previous.get("signature") == source["signature"]
                docs.append({
                    **source,
                    "status": previous.get("status", "pending") if fresh else "pending",
                    "pages": previous.get("pages", 0) if fresh else 0,
                    "chunks": previous.get("chunks", 0) if fresh else 0,
                    "error": previous.get("error") if fresh else None,
                    "file_url": f"/api/library/sources/{source['id']}/file",
                })
            folders.append({
                "id": folder_id, **info, "available": self.resolve(info["directory"]).is_dir(),
                "sources": docs, "source_count": len(docs),
                "indexed_count": sum(doc["status"] in {"indexed", "empty"} for doc in docs),
                "chunk_count": sum(doc["chunks"] for doc in docs),
            })
        with self._job_lock:
            job = dict(self._job)
        return {"root": str(self.root), "folders": folders, "job": job}

    @staticmethod
    def _chunks(text, size=1800):
        text = re.sub(r"[ \t]+", " ", text.replace("\x00", "")).strip()
        while text:
            if len(text) <= size:
                if len(text) >= 40:
                    yield text
                break
            end = max(text.rfind("\n", size // 2, size), text.rfind(". ", size // 2, size))
            if end < 0:
                end = size
            yield text[:end].strip()
            text = text[max(1, end - 180):].lstrip()

    def _read_sections(self, source):
        path = self.resolve(source["path"])
        if path.suffix.lower() == ".pdf":
            from pypdf import PdfReader
            with path.open("rb") as stream:
                reader = PdfReader(stream)
                for number, page in enumerate(reader.pages, 1):
                    yield f"Page {number}", page.extract_text() or ""
        elif path.suffix.lower() == ".zip":
            with zipfile.ZipFile(path) as archive:
                for info in sorted(archive.infolist(), key=lambda item: item.filename):
                    parts = Path(info.filename.replace("\\", "/")).parts
                    if info.filename.lower().endswith(".md") and not any(p.startswith(".") for p in parts):
                        if info.file_size > 10_000_000:
                            continue
                        yield info.filename, archive.read(info).decode("utf-8", errors="replace")
        else:
            content = path.read_text(encoding="utf-8", errors="replace")
            for number, section in enumerate(content.split("\f"), 1):
                yield f"Text section {number}", section

    def index_source(self, source, force=False):
        with self.connect() as db:
            previous = db.execute("SELECT signature, status FROM sources WHERE id=?", (source["id"],)).fetchone()
        if previous and previous["signature"] == source["signature"] and previous["status"] in {"indexed", "empty"} and not force:
            return "unchanged"
        passages, pages = [], 0
        try:
            for section, text in self._read_sections(source):
                pages += 1
                passages.extend((source["id"], section, chunk) for chunk in self._chunks(text))
            status = "indexed" if passages else "empty"
            error = None
        except Exception as exc:
            status, error, passages = "error", f"{type(exc).__name__}: {exc}", []
        with self.connect() as db:
            db.execute("DELETE FROM passages WHERE source_id=?", (source["id"],))
            db.execute("""INSERT OR REPLACE INTO sources
                (id,folder_id,title,path,file_path,edition,signature,status,pages,chunks,error,indexed_at)
                VALUES (:id,:folder_id,:title,:path,:file_path,:edition,:signature,:status,:pages,:chunks,:error,:indexed_at)
            """, {**source, "status": status, "pages": pages, "chunks": len(passages), "error": error, "indexed_at": time.time()})
            db.executemany("INSERT INTO passages(source_id,section,text) VALUES (?,?,?)", passages)
        return status

    def index(self, folder_id=None, force=False, progress=None):
        sources = self.discover(folder_id)
        for index, source in enumerate(sources):
            if progress:
                progress(index, len(sources), source["title"])
            self.index_source(source, force=force)
        # Removed files must no longer contribute passages to the DM context.
        valid = {source["id"] for source in sources}
        with self.connect() as db:
            query = "SELECT id FROM sources" + (" WHERE folder_id=?" if folder_id else "")
            for row in db.execute(query, (folder_id,) if folder_id else ()).fetchall():
                if row["id"] not in valid:
                    db.execute("DELETE FROM passages WHERE source_id=?", (row["id"],))
                    db.execute("DELETE FROM sources WHERE id=?", (row["id"],))
        if progress:
            progress(len(sources), len(sources), "Complete")

    def start_index(self, folder_id=None):
        if folder_id is not None and folder_id not in FOLDERS:
            raise ValueError("Unknown library folder.")
        with self._job_lock:
            if self._job["running"]:
                return dict(self._job)
            self._job = {"running": True, "completed": 0, "total": 0, "current": "Scanning sources", "error": None}

        def progress(completed, total, current):
            with self._job_lock:
                self._job.update(completed=completed, total=total, current=current)

        def run():
            try:
                self.index(folder_id, progress=progress)
            except Exception as exc:
                with self._job_lock:
                    self._job["error"] = str(exc)
            finally:
                with self._job_lock:
                    self._job["running"] = False

        threading.Thread(target=run, name="dungeonforge-library", daemon=True).start()
        with self._job_lock:
            return dict(self._job)

    def search(self, query, folder_id=None, edition=None, limit=8, campaign_folders=None):
        ignored = {"the", "and", "that", "this", "with", "from", "into", "what", "you", "your", "for", "how", "can", "does", "are", "use"}
        words = list(dict.fromkeys(w.lower() for w in re.findall(r"\w{3,}", query) if w.lower() not in ignored))[:16]
        if not words:
            return []
        filters, params = ["passages MATCH ?", "s.status='indexed'"], [" OR ".join('"' + w + '"' for w in words)]
        if folder_id:
            filters.append("s.folder_id=?")
            params.append(folder_id)
        if edition and campaign_folders is None:
            filters.append("s.edition=?")
            params.append(edition)
        if campaign_folders is not None:
            placeholders = ",".join("?" for _ in campaign_folders)
            filters.append(f"(s.folder_id IN ({placeholders or 'NULL'}) OR s.folder_id=?)")
            params.extend([*campaign_folders, edition or "5e"])
        params.append(max(1, min(limit, 30)))
        with self.connect() as db:
            rows = db.execute(f"""SELECT s.id AS source_id, s.title, s.folder_id, s.edition,
                passages.section, passages.text, bm25(passages) AS rank
                FROM passages JOIN sources s ON s.id=passages.source_id
                WHERE {' AND '.join(filters)} ORDER BY rank LIMIT ?""", params).fetchall()
        return [{**dict(row), "file_url": f"/api/library/sources/{row['source_id']}/file"} for row in rows]

    def source_file(self, source_id):
        source = next((source for source in self.discover() if source["id"] == source_id), None)
        if source is None:
            return None
        path = self.resolve(source["file_path"])
        return path if path.is_file() else None


_library = None
_library_lock = threading.Lock()


def get_library():
    global _library
    with _library_lock:
        if _library is None:
            _library = SourceLibrary()
    return _library


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--folder", choices=list(FOLDERS))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    library = get_library()
    library.index(args.folder, force=args.force, progress=lambda done, total, title: print(f"[{done}/{total}] {title}", flush=True))
    for folder in library.catalog()["folders"]:
        print(f"{folder['directory']}: {folder['indexed_count']}/{folder['source_count']} sources; {folder['chunk_count']} passages")
