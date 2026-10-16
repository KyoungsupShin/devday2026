"""Business embedding workflows: clustering and supervised metric adaptation.

Hosted embedding models generally expose inference, not weight-level fine-tuning.
``BusinessEmbeddingAdapter`` therefore keeps the encoder frozen and learns a
small, auditable diagonal metric from labelled business examples.  It is a
useful production baseline before considering a separately trained embedding
model.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np

from lab_common.ai_core import apply_ai_core_environment
from lab_common.config import Settings


@dataclass(frozen=True)
class BusinessRecord:
    id: str
    text: str
    label: str | None = None


@dataclass(frozen=True)
class ClusterResult:
    assignments: np.ndarray
    centroids: np.ndarray
    inertia: float


def _as_matrix(vectors: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    matrix = np.asarray(vectors, dtype=np.float64)
    if matrix.ndim != 2 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        raise ValueError("vectors must be a non-empty 2D matrix.")
    if not np.isfinite(matrix).all():
        raise ValueError("vectors must contain only finite values.")
    return matrix


def l2_normalize(vectors: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
    """Return row-wise normalized vectors, preserving zero rows."""
    matrix = _as_matrix(vectors)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return np.divide(matrix, norms, out=np.zeros_like(matrix), where=norms > 0)


def embed_texts(texts: Sequence[str], settings: Settings, model: str | None = None) -> np.ndarray:
    """Embed a batch through AI Core; imports stay delayed for local tests."""
    if not texts:
        raise ValueError("texts must not be empty.")
    apply_ai_core_environment(settings)
    try:
        from gen_ai_hub.proxy.native.openai import embeddings
    except ImportError as error:
        raise RuntimeError("sap-ai-sdk-gen이 없습니다. pip install -r requirements.txt를 실행하세요.") from error

    response = embeddings.create(input=list(texts), model_name=model or os.getenv("EMBED_MODEL", "text-embedding-3-small"))
    # API results have an index, but sorting also makes the expected input order explicit.
    ordered = sorted(response.data, key=lambda item: getattr(item, "index", 0))
    return _as_matrix([item.embedding for item in ordered])


def kmeans_cluster(
    vectors: Sequence[Sequence[float]] | np.ndarray,
    n_clusters: int,
    max_iterations: int = 100,
) -> ClusterResult:
    """Deterministic k-means over normalized embeddings for a small business corpus."""
    matrix = l2_normalize(vectors)
    n_rows = matrix.shape[0]
    if not 1 <= n_clusters <= n_rows:
        raise ValueError("n_clusters must be between 1 and the number of vectors.")
    if max_iterations < 1:
        raise ValueError("max_iterations must be positive.")

    # Farthest-first seeds make classroom runs reproducible without a random seed.
    selected = [0]
    closest_distance = np.sum((matrix - matrix[0]) ** 2, axis=1)
    for _ in range(1, n_clusters):
        next_index = int(np.argmax(closest_distance))
        selected.append(next_index)
        distance = np.sum((matrix - matrix[next_index]) ** 2, axis=1)
        closest_distance = np.minimum(closest_distance, distance)
    centroids = matrix[selected].copy()

    assignments = np.zeros(n_rows, dtype=int)
    for _ in range(max_iterations):
        distances = np.sum((matrix[:, None, :] - centroids[None, :, :]) ** 2, axis=2)
        updated_assignments = np.argmin(distances, axis=1)
        updated_centroids = centroids.copy()
        for cluster_id in range(n_clusters):
            members = matrix[updated_assignments == cluster_id]
            if len(members):
                updated_centroids[cluster_id] = members.mean(axis=0)
        if np.array_equal(updated_assignments, assignments) and np.allclose(updated_centroids, centroids):
            assignments, centroids = updated_assignments, updated_centroids
            break
        assignments, centroids = updated_assignments, updated_centroids

    distances = np.sum((matrix - centroids[assignments]) ** 2, axis=1)
    return ClusterResult(assignments=assignments, centroids=centroids, inertia=float(distances.sum()))


class BusinessEmbeddingAdapter:
    """Label-aware diagonal metric adapter for frozen embedding vectors.

    Dimensions with high between-label variance and low within-label variance get
    more weight.  This is supervised metric learning, not encoder weight tuning.
    Keep a held-out evaluation set; never judge it on the same labels used here.
    """

    def __init__(self, regularization: float = 1e-6, max_weight: float = 20.0):
        if regularization <= 0 or max_weight <= 0:
            raise ValueError("regularization and max_weight must be positive.")
        self.regularization = regularization
        self.max_weight = max_weight
        self.weights: np.ndarray | None = None
        self.labels: tuple[str, ...] = ()
        self.centroids: np.ndarray | None = None

    def fit(self, vectors: Sequence[Sequence[float]] | np.ndarray, labels: Iterable[str]) -> "BusinessEmbeddingAdapter":
        matrix = l2_normalize(vectors)
        label_array = np.asarray(list(labels), dtype=str)
        if len(label_array) != len(matrix):
            raise ValueError("labels must have one entry per vector.")
        classes = tuple(sorted(set(label_array.tolist())))
        if len(classes) < 2:
            raise ValueError("At least two distinct business labels are required.")

        global_mean = matrix.mean(axis=0)
        between = np.zeros(matrix.shape[1])
        within = np.zeros(matrix.shape[1])
        class_means: list[np.ndarray] = []
        for label in classes:
            members = matrix[label_array == label]
            class_mean = members.mean(axis=0)
            class_means.append(class_mean)
            between += len(members) * (class_mean - global_mean) ** 2
            within += ((members - class_mean) ** 2).sum(axis=0)
        between /= len(matrix)
        within /= len(matrix)
        weights = between / (within + self.regularization)
        weights /= max(float(weights.mean()), self.regularization)
        self.weights = np.clip(weights, 1 / self.max_weight, self.max_weight)
        self.labels = classes
        self.centroids = l2_normalize(np.asarray(class_means) * np.sqrt(self.weights))
        return self

    def transform(self, vectors: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
        if self.weights is None:
            raise RuntimeError("Call fit before transform.")
        matrix = _as_matrix(vectors)
        if matrix.shape[1] != len(self.weights):
            raise ValueError("vector dimension does not match fitted adapter.")
        return l2_normalize(matrix * np.sqrt(self.weights))

    def predict(self, vectors: Sequence[Sequence[float]] | np.ndarray) -> list[str]:
        if self.centroids is None:
            raise RuntimeError("Call fit before predict.")
        scores = self.transform(vectors) @ self.centroids.T
        return [self.labels[index] for index in np.argmax(scores, axis=1)]

    def similarity(self, left: Sequence[Sequence[float]] | np.ndarray, right: Sequence[Sequence[float]] | np.ndarray) -> np.ndarray:
        """Pairwise cosine matrix in the adapted embedding space."""
        return self.transform(left) @ self.transform(right).T
