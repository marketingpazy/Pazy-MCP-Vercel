# rag_store.py
from __future__ import annotations

import os
import json
import yaml
import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
import google.generativeai as genai
from langchain_core.embeddings import Embeddings


class GeminiEmbeddings(Embeddings):
    """Thin wrapper sobre google-generativeai usando el endpoint v1 estable."""

    def __init__(self, model: str = "models/text-embedding-004"):
        self.model = model
        api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            genai.configure(api_key=api_key)

    def embed_documents(self, texts: list) -> list:
        result = genai.embed_content(
            model=self.model,
            content=texts,
            task_type="retrieval_document",
        )
        return result["embedding"]

    def embed_query(self, text: str) -> list:
        result = genai.embed_content(
            model=self.model,
            content=text,
            task_type="retrieval_query",
        )
        return result["embedding"]
from langchain_community.vectorstores import FAISS

from dev.aux_functions import cfg


# Writable directory for serverless environments (Vercel uses /tmp)
FAISS_WRITABLE_DIR = os.environ.get("FAISS_WRITABLE_DIR", "/tmp/pazy_faiss")

# Module-level cache to avoid rebuilding on every request
_cached_vectorstore: FAISS | None = None
_cached_fingerprint: dict | None = None


@dataclass
class RagSettings:
    faqs_path: str = cfg("FAQS_PATH")
    marca_path: str = cfg("MARCA_PATH")
    faiss_dir: str = cfg("FAISS_DIR")
    faiss_meta_path: str = cfg("FAISS_META_PATH")
    embedding_model: str = cfg(
        "EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )

    chunk_size: int = 900
    chunk_overlap: int = 150


SEMANTIC_KEYS = {
    "pregunta",
    "aliases",
    "respuesta",
    "politica",
    "descripcion",
    "resumen",
    "datos",
    "nota",
    "notas_de_seguridad",
}


def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


def _fingerprint(s: RagSettings) -> dict:
    fp = {
        "faqs_path": os.path.abspath(s.faqs_path),
        "faqs_sha256": _file_sha256(s.faqs_path),
        "chunk_size": s.chunk_size,
        "chunk_overlap": s.chunk_overlap,
        "embedding_model": s.embedding_model,
        "pipeline_version": 3,
    }
    # marca_path is optional — only include if the file exists
    if s.marca_path and os.path.isfile(s.marca_path):
        fp["marca_path"] = os.path.abspath(s.marca_path)
        fp["marca_sha256"] = _file_sha256(s.marca_path)
    return fp


def _meta_matches_at(meta_path: str, fp: dict) -> bool:
    if not os.path.isfile(meta_path):
        return False
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            saved = json.load(f)
        return saved.get("fingerprint") == fp
    except Exception:
        return False


def _meta_matches(s: RagSettings, fp: dict) -> bool:
    return _meta_matches_at(s.faiss_meta_path, fp)


def _save_meta_at(meta_path: str, fp: dict) -> None:
    os.makedirs(os.path.dirname(meta_path), exist_ok=True)
    meta = {"fingerprint": fp, "built_at": datetime.utcnow().isoformat() + "Z"}
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def _save_meta(s: RagSettings, fp: dict) -> None:
    _save_meta_at(s.faiss_meta_path, fp)


def load_marca_yaml_text(s: RagSettings) -> str:
    if not s.marca_path or not os.path.isfile(s.marca_path):
        return ""
    with open(s.marca_path, "r", encoding="utf-8") as f:
        obj = yaml.safe_load(f) or {}
    return yaml.safe_dump(obj, allow_unicode=True, sort_keys=False)


def _is_scalar_list(value: Any) -> bool:
    return isinstance(value, list) and all(not isinstance(x, (dict, list)) for x in value)


def _normalize_scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return " ".join(value.split())
    return str(value)


def _node_has_semantic_content(node: Any) -> bool:
    return isinstance(node, dict) and any(k in node for k in SEMANTIC_KEYS)


def _node_to_text(path: list[str], node: dict) -> str:
    parts: list[str] = []

    if path:
        parts.append(f"Ruta: {' > '.join(path)}")

    # campos principales
    if "pregunta" in node:
        parts.append(f"Pregunta: {_normalize_scalar(node['pregunta'])}")

    if "aliases" in node:
        aliases = node["aliases"]
        if isinstance(aliases, list):
            alias_text = "; ".join(_normalize_scalar(a) for a in aliases if _normalize_scalar(a))
            if alias_text:
                parts.append(f"Aliases: {alias_text}")
        else:
            alias_text = _normalize_scalar(aliases)
            if alias_text:
                parts.append(f"Aliases: {alias_text}")

    if "respuesta" in node:
        parts.append(f"Respuesta: {_normalize_scalar(node['respuesta'])}")

    if "politica" in node:
        parts.append(f"Política: {_normalize_scalar(node['politica'])}")

    if "descripcion" in node:
        parts.append(f"Descripción: {_normalize_scalar(node['descripcion'])}")

    if "resumen" in node:
        parts.append(f"Resumen: {_normalize_scalar(node['resumen'])}")

    if "datos" in node:
        parts.append(f"Datos: {_normalize_scalar(node['datos'])}")

    if "nota" in node:
        parts.append(f"Nota: {_normalize_scalar(node['nota'])}")

    if "notas_de_seguridad" in node:
        parts.append(f"Notas de seguridad: {_normalize_scalar(node['notas_de_seguridad'])}")

    # listas simples adicionales
    for key, value in node.items():
        if key in SEMANTIC_KEYS:
            continue

        if _is_scalar_list(value):
            joined = "; ".join(_normalize_scalar(v) for v in value if _normalize_scalar(v))
            if joined:
                parts.append(f"{key}: {joined}")

        # caso especial de listas de dicts tipo referencias
        elif isinstance(value, list) and value and all(isinstance(x, dict) for x in value):
            rendered_items: list[str] = []
            for item in value:
                bits = []
                for k, v in item.items():
                    vv = _normalize_scalar(v)
                    if vv:
                        bits.append(f"{k}: {vv}")
                if bits:
                    rendered_items.append(", ".join(bits))
            if rendered_items:
                parts.append(f"{key}: " + " | ".join(rendered_items))

    return "\n".join(parts).strip()


def _collect_leaf_docs(tree: dict, prefix: str, doc_type: str) -> list[Document]:
    docs: list[Document] = []

    def walk(node: Any, path: list[str]) -> None:
        if isinstance(node, dict):
            # si este nodo ya tiene contenido semántico, lo indexamos
            if _node_has_semantic_content(node):
                source = f"{prefix}:" + ":".join(path)
                docs.append(
                    Document(
                        page_content=_node_to_text(path, node),
                        metadata={
                            "source": source,
                            "doc_type": doc_type,
                            "path": " > ".join(path),
                        },
                    )
                )

            # seguimos descendiendo por subdicts
            for key, value in node.items():
                if isinstance(value, dict):
                    walk(value, path + [key])

                # si una lista contiene dicts, también puede haber contenido semántico útil
                elif isinstance(value, list):
                    for idx, item in enumerate(value):
                        if isinstance(item, dict):
                            walk(item, path + [key, str(idx)])

    walk(tree, [])
    return docs


def _build_documents_from_yaml_root(root: dict, prefix: str, doc_type: str) -> list[Document]:
    if not isinstance(root, dict):
        return []

    docs = _collect_leaf_docs(root, prefix=prefix, doc_type=doc_type)
    return docs


def build_or_load_vectorstore(s: RagSettings) -> FAISS:
    global _cached_vectorstore, _cached_fingerprint

    fp = _fingerprint(s)

    # Return cached if fingerprint matches
    if _cached_vectorstore is not None and _cached_fingerprint == fp:
        return _cached_vectorstore

    embeddings = GeminiEmbeddings(model=s.embedding_model)

    # Try loading from writable dir (/tmp on Vercel)
    writable_meta = os.path.join(FAISS_WRITABLE_DIR, "faq_hash.json")
    if os.path.isdir(FAISS_WRITABLE_DIR) and _meta_matches_at(writable_meta, fp):
        try:
            vs = FAISS.load_local(
                FAISS_WRITABLE_DIR,
                embeddings,
                allow_dangerous_deserialization=True,
            )
            _cached_vectorstore = vs
            _cached_fingerprint = fp
            return vs
        except Exception:
            pass

    # Try loading from original dir (local dev)
    if os.path.isdir(s.faiss_dir) and _meta_matches(s, fp):
        try:
            vs = FAISS.load_local(
                s.faiss_dir,
                embeddings,
                allow_dangerous_deserialization=True,
            )
            _cached_vectorstore = vs
            _cached_fingerprint = fp
            return vs
        except Exception:
            pass

    # Rebuild index from source YAML files
    docs: list[Document] = []

    # ---------- FAQ ----------
    with open(s.faqs_path, "r", encoding="utf-8") as f:
        faq_yaml = yaml.safe_load(f) or {}

    if "faq_pazy" in faq_yaml and isinstance(faq_yaml["faq_pazy"], dict):
        faq_yaml = faq_yaml["faq_pazy"]

    docs.extend(_build_documents_from_yaml_root(faq_yaml, prefix="faq", doc_type="faq"))

    # ---------- MANUAL DE MARCA (optional) ----------
    if s.marca_path and os.path.isfile(s.marca_path):
        with open(s.marca_path, "r", encoding="utf-8") as f:
            marca_yaml = yaml.safe_load(f) or {}

        if "marca_pazy" in marca_yaml and isinstance(marca_yaml["marca_pazy"], dict):
            marca_yaml = marca_yaml["marca_pazy"]

        docs.extend(_build_documents_from_yaml_root(marca_yaml, prefix="brand", doc_type="brand"))

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=s.chunk_size,
        chunk_overlap=s.chunk_overlap,
    )
    chunks = splitter.split_documents(docs)

    print(f"Rebuilding FAISS index (data changed). Docs: {len(docs)} | Chunks: {len(chunks)}")

    vs = FAISS.from_documents(chunks, embeddings)

    # Save to writable dir (works on Vercel /tmp)
    try:
        os.makedirs(FAISS_WRITABLE_DIR, exist_ok=True)
        vs.save_local(FAISS_WRITABLE_DIR)
        _save_meta_at(writable_meta, fp)
    except Exception as e:
        print(f"Could not save FAISS to writable dir: {e}")

    # Also try original dir (for local dev)
    try:
        os.makedirs(s.faiss_dir, exist_ok=True)
        vs.save_local(s.faiss_dir)
        _save_meta(s, fp)
    except Exception:
        pass

    _cached_vectorstore = vs
    _cached_fingerprint = fp
    return vs


def retrieve_faq_rag(vs: FAISS, query: str, k: int = 3) -> list[dict]:
    docs = vs.similarity_search(
        query,
        k=k,
        filter={"doc_type": "faq"},
    )
    out: list[dict] = []
    for d in docs:
        meta = d.metadata or {}
        out.append(
            {
                "source": meta.get("source", ""),
                "path": meta.get("path", ""),
                "content": d.page_content,
            }
        )
    return out


def retrieve_brand_rag(vs: FAISS, query: str, k: int = 3) -> list[dict]:
    docs = vs.similarity_search(
        query,
        k=k,
        filter={"doc_type": "brand"},
    )
    out: list[dict] = []
    for d in docs:
        meta = d.metadata or {}
        out.append(
            {
                "source": meta.get("source", ""),
                "path": meta.get("path", ""),
                "content": d.page_content,
            }
        )
    return out
