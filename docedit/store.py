"""Stockage des documents ouverts et historique des modifications (annuler / rétablir).

Le fichier importé est copié une fois dans un dossier de travail et n'est JAMAIS modifié :
chaque affichage et chaque export sont recalculés à partir de l'original + la liste des modifications.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid

DATA_DIR = os.environ.get("DOCEDIT_DATA", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
SESSIONS_DIR = os.path.join(DATA_DIR, "documents")
MAX_AGE_S = 3 * 24 * 3600

_docs: dict[str, "Doc"] = {}
_docs_lock = threading.Lock()


class Doc:
    def __init__(self, meta: dict, folder: str):
        self.meta = meta
        self.folder = folder
        self.lock = threading.RLock()
        self.cache: dict = {}

    # --- accès pratiques -------------------------------------------------
    @property
    def id(self) -> str:
        return self.meta["id"]

    @property
    def kind(self) -> str:
        return self.meta["kind"]

    @property
    def pages(self) -> list[dict]:
        return self.meta["pages"]

    @property
    def items(self) -> dict[str, dict]:
        return self.meta["items"]

    def path(self, name: str) -> str:
        return os.path.join(self.folder, name)

    @property
    def original_path(self) -> str:
        return self.path(self.meta["original_name"])

    def page_items(self, page: int) -> list[dict]:
        return [self.items[i] for i in self.meta["order"] if self.items[i]["page"] == page]

    # --- état et historique ----------------------------------------------
    def state(self) -> dict[str, str]:
        """Textes modifiés : {id: texte actuel} (seulement ceux différents de l'original)."""
        st: dict[str, str] = {}
        for op in self.meta["history"][: self.meta["pos"]]:
            for iid, (_old, new) in op.items():
                st[iid] = new
        return {k: v for k, v in st.items() if k in self.items and v != self.items[k]["orig"]}

    def text(self, iid: str, state: dict | None = None) -> str:
        st = self.state() if state is None else state
        return st.get(iid, self.items[iid]["orig"])

    def page_state(self, page: int, state: dict | None = None) -> dict[str, str]:
        st = self.state() if state is None else state
        return {k: v for k, v in st.items() if self.items[k]["page"] == page}

    def page_version(self, page: int, state: dict | None = None) -> str:
        ps = self.page_state(page, state)
        if not ps:
            return "0"
        overrides = sorted((k, self.items[k].get("bold_override")) for k in ps
                           if self.items[k].get("bold_override") is not None)
        raw = json.dumps([sorted(ps.items()), overrides], ensure_ascii=False).encode()
        return hashlib.sha1(raw).hexdigest()[:10]

    def apply(self, changes: dict[str, str]) -> list[str]:
        st = self.state()
        op = {}
        for iid, new in changes.items():
            if iid not in self.items:
                continue
            old = st.get(iid, self.items[iid]["orig"])
            if new != old:
                op[iid] = [old, new]
        if not op:
            return []
        del self.meta["history"][self.meta["pos"]:]
        self.meta["history"].append(op)
        self.meta["pos"] += 1
        self.save()
        return list(op)

    def undo(self) -> list[str]:
        if self.meta["pos"] == 0:
            return []
        self.meta["pos"] -= 1
        self.save()
        return list(self.meta["history"][self.meta["pos"]])

    def redo(self) -> list[str]:
        if self.meta["pos"] >= len(self.meta["history"]):
            return []
        self.meta["pos"] += 1
        self.save()
        return list(self.meta["history"][self.meta["pos"] - 1])

    @property
    def can_undo(self) -> bool:
        return self.meta["pos"] > 0

    @property
    def can_redo(self) -> bool:
        return self.meta["pos"] < len(self.meta["history"])

    def save(self):
        self.meta["updated"] = time.time()
        tmp = self.path("meta.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.meta, f, ensure_ascii=False)
        os.replace(tmp, self.path("meta.json"))


def safe_name(name: str) -> str:
    base = os.path.basename(name or "document")
    base = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "_", base).strip(" .") or "document"
    return base[:120]


def create(filename: str, data: bytes | None, kind: str, ext: str) -> Doc:
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    doc_id = uuid.uuid4().hex[:16]
    folder = os.path.join(SESSIONS_DIR, doc_id)
    os.makedirs(folder)
    original_name = "original" + ext
    if data is not None:
        with open(os.path.join(folder, original_name), "wb") as f:
            f.write(data)
        try:
            os.chmod(os.path.join(folder, original_name), 0o444)  # copie de l'original en lecture seule
        except OSError:
            pass
    meta = {
        "id": doc_id, "filename": safe_name(filename), "kind": kind, "ext": ext,
        "original_name": original_name, "created": time.time(), "updated": time.time(),
        "pages": [], "items": {}, "order": [], "history": [], "pos": 0, "warnings": [], "lang": None,
    }
    doc = Doc(meta, folder)
    with _docs_lock:
        _docs[doc_id] = doc
    return doc


def get(doc_id: str) -> Doc | None:
    if not re.fullmatch(r"[0-9a-f]{16}", doc_id or ""):
        return None
    with _docs_lock:
        if doc_id in _docs:
            return _docs[doc_id]
        folder = os.path.join(SESSIONS_DIR, doc_id)
        meta_path = os.path.join(folder, "meta.json")
        if not os.path.isfile(meta_path):
            return None
        with open(meta_path, encoding="utf-8") as f:
            doc = Doc(json.load(f), folder)
        _docs[doc_id] = doc
        return doc


def _rmtree(folder: str):
    for root, _dirs, files in os.walk(folder):
        for fn in files:
            try:
                os.chmod(os.path.join(root, fn), 0o644)
            except OSError:
                pass
    shutil.rmtree(folder, ignore_errors=True)


def discard(doc: Doc):
    with _docs_lock:
        _docs.pop(doc.id, None)
    _rmtree(doc.folder)


def cleanup_old():
    if not os.path.isdir(SESSIONS_DIR):
        return
    now = time.time()
    for name in os.listdir(SESSIONS_DIR):
        folder = os.path.join(SESSIONS_DIR, name)
        try:
            meta = os.path.join(folder, "meta.json")
            ref = meta if os.path.exists(meta) else folder
            if now - os.path.getmtime(ref) > MAX_AGE_S:
                _rmtree(folder)
        except OSError:
            pass
