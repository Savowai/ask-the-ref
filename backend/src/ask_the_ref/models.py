"""Pinned local models; token windows are internal, section chunks remain intact."""

import json
import os

import numpy as np

from .config import ROOT

os.environ.setdefault("HF_HOME", str(ROOT / "work/cache/huggingface"))
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
LOCK = json.loads((ROOT / "models.lock.json").read_text())


def model_id(kind):
    spec = LOCK[kind]
    return spec["name"] + "@" + spec["revision"]


def download_models():
    from huggingface_hub import snapshot_download

    for spec in LOCK.values():
        snapshot_download(
            spec["name"],
            revision=spec["revision"],
            allow_patterns=["*.json", "*.safetensors", "*.txt", "*.model"],
            ignore_patterns=["onnx/*", "openvino/*"],
        )


def windows(tokenizer, text, limit, overlap=32):
    ids = tokenizer.encode(text, add_special_tokens=False, verbose=False)
    if limit <= overlap:
        raise ValueError("Invalid token window")
    for start in range(0, max(1, len(ids)), limit - overlap):
        yield tokenizer.decode(ids[start : start + limit], skip_special_tokens=True)
        if start + limit >= len(ids):
            break


class Embedder:
    def __init__(self):
        import torch
        from sentence_transformers import SentenceTransformer

        torch.set_num_threads(min(4, os.cpu_count() or 1))
        spec = LOCK["embedding"]
        self.model = SentenceTransformer(
            spec["name"],
            revision=spec["revision"],
            local_files_only=True,
            trust_remote_code=False,
            device="cpu",
        )

    def encode(self, texts):
        pieces, owners = [], []
        for i, text in enumerate(texts):
            for window in windows(self.model.tokenizer, text, self.model.max_seq_length - 2):
                pieces.append(window)
                owners.append(i)
        vectors = self.model.encode(
            pieces,
            batch_size=32,
            normalize_embeddings=True,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
        pooled = np.stack([vectors[np.array(owners) == i].mean(axis=0) for i in range(len(texts))])
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        return (pooled / np.maximum(norms, 1e-12)).astype(np.float32)


class Reranker:
    def __init__(self):
        from sentence_transformers import CrossEncoder

        spec = LOCK["reranker"]
        self.model = CrossEncoder(
            spec["name"],
            revision=spec["revision"],
            local_files_only=True,
            trust_remote_code=False,
            device="cpu",
            max_length=512,
        )

    def scores(self, question, texts):
        tokenizer = self.model.tokenizer
        query_length = len(tokenizer.encode(question, add_special_tokens=False))
        if query_length > 128:
            raise ValueError("Phase 2 CLI accepts questions up to 128 model tokens")
        pairs, owners = [], []
        for i, text in enumerate(texts):
            for window in windows(tokenizer, text, 512 - query_length - 4):
                pairs.append((question, window))
                owners.append(i)
        scores = self.model.predict(pairs, batch_size=16, show_progress_bar=False)
        return [float(max(s for s, j in zip(scores, owners) if j == i)) for i in range(len(texts))]
