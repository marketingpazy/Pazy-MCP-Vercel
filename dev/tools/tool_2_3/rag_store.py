# rag_store.py
from __future__ import annotations

import os
import json
import yaml
import hashlib
from dataclasses import dataclass
from datetime import datetime

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from aux_functions import cfg

@dataclass
class RagSettings:
    faqs_path: str = cfg("FAQS_PATH")
    marca_path: str = cfg("MARCA_PATH")
    faiss_dir: str = cfg("FAISS_DIR")
    faiss_meta_path: str = cfg("FAISS_META_PATH")
    embedding_model: str = cfg("EMBEDDING_MODEL","sentence-transformers/all-MiniLM-L6-v2",)

    chunk_size: int = 900
    chunk_overlap: int = 150

def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def _fingerprint(s: RagSettings) -> dict:
    return {
        "faqs_path": os.path.abspath(s.faqs_path),
        "faqs_sha256": _file_sha256(s.faqs_path),
        "marca_path": os.path.abspath(s.marca_path),
        "marca_sha256": _file_sha256(s.marca_path),
        "chunk_size": s.chunk_size,
        "chunk_overlap": s.chunk_overlap,
        "embedding_model": s.embedding_model,
    }

def _meta_matches(s: RagSettings, fp: dict) -> bool:
    if not os.path.isfile(s.faiss_meta_path):
        return False
    try:
        with open(s.faiss_meta_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        return saved.get("fingerprint") == fp
    except Exception:
        return False


def _save_meta(s: RagSettings, fp: dict) -> None:
    os.makedirs(s.faiss_dir, exist_ok=True)
    meta = {"fingerprint": fp, "built_at": datetime.utcnow().isoformat() + "Z"}
    with open(s.faiss_meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def load_marca_yaml_text(s: RagSettings) -> str:
    with open(s.marca_path, "r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    # devolvemos como YAML legible
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False)


def build_or_load_vectorstore(s: RagSettings) -> FAISS:
    embeddings = HuggingFaceEmbeddings(model_name=s.embedding_model)
    fp = _fingerprint(s)

    if os.path.isdir(s.faiss_dir) and _meta_matches(s, fp):
        return FAISS.load_local(s.faiss_dir, embeddings, allow_dangerous_deserialization=True)

    os.makedirs(os.path.dirname(s.faiss_meta_path), exist_ok=True)

    docs: list[Document] = []

    # ---------- FAQ ----------
    with open(s.faqs_path, "r", encoding="utf-8") as f:
        faq_yaml = yaml.safe_load(f) or {}

    if "faq_pazy" in faq_yaml and isinstance(faq_yaml["faq_pazy"], dict):
        faq_yaml = faq_yaml["faq_pazy"]

    for section, content in faq_yaml.items():
        docs.append(
            Document(
                page_content=yaml.safe_dump(content, allow_unicode=True, sort_keys=False),
                metadata={"source": f"faq:{section}", "doc_type": "faq"},
            )
        )

    # ---------- MANUAL DE MARCA ----------
    with open(s.marca_path, "r", encoding="utf-8") as f:
        marca_yaml = yaml.safe_load(f) or {}

    if "marca_pazy" in marca_yaml and isinstance(marca_yaml["marca_pazy"], dict):
        marca_yaml = marca_yaml["marca_pazy"]

    for section, content in marca_yaml.items():
        docs.append(
            Document(
                page_content=yaml.safe_dump(content, allow_unicode=True, sort_keys=False),
                metadata={"source": f"brand:{section}", "doc_type": "brand"},
            )
        )

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=s.chunk_size,
        chunk_overlap=s.chunk_overlap,
    )
    chunks = splitter.split_documents(docs)

    print("Rebuilding FAISS index (data changed)")
    vs = FAISS.from_documents(chunks, embeddings)
    vs.save_local(s.faiss_dir)
    _save_meta(s, fp)
    return vs


def retrieve_faq_rag(vs: FAISS, query: str, k: int = 3) -> list[dict]:
    docs = vs.max_marginal_relevance_search(
        query,
        k=k,
        fetch_k=max(20, k * 5),
        filter={"doc_type": "faq"},
    )
    out: list[dict] = []
    for d in docs:
        meta = d.metadata or {}
        out.append(
            {
                "source": meta.get("source", ""),
                "content": d.page_content,
            }
        )
    return out


def retrieve_brand_rag(vs: FAISS, query: str, k: int = 3) -> list[dict]:
    docs = vs.max_marginal_relevance_search(
        query,
        k=k,
        fetch_k=max(20, k * 5),
        filter={"doc_type": "brand"},
    )
    out: list[dict] = []
    for d in docs:
        meta = d.metadata or {}
        out.append(
            {
                "source": meta.get("source", ""),
                "content": d.page_content,
            }
        )
    return out