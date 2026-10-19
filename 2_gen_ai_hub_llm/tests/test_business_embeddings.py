from __future__ import annotations

import sys
from pathlib import Path
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "shared"))
sys.path.insert(0, str(ROOT / "2_gen_ai_hub_llm"))

from src.business_embedding.lab_core import BusinessEmbeddingAdapter, kmeans_cluster


class BusinessEmbeddingTests(unittest.TestCase):
    def test_kmeans_groups_separated_vectors(self):
        vectors = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9]])
        result = kmeans_cluster(vectors, n_clusters=2)
        self.assertEqual(result.assignments[0], result.assignments[1])
        self.assertEqual(result.assignments[2], result.assignments[3])
        self.assertNotEqual(result.assignments[0], result.assignments[2])
        self.assertGreaterEqual(result.inertia, 0.0)

    def test_adapter_predicts_held_out_business_label(self):
        vectors = np.array([[1.0, 0.0], [0.9, 0.1], [0.0, 1.0], [0.1, 0.9]])
        adapter = BusinessEmbeddingAdapter().fit(
            vectors, ["payment", "payment", "logistics", "logistics"]
        )
        self.assertEqual(adapter.predict([[0.8, 0.2]]), ["payment"])
        self.assertEqual(adapter.predict([[0.2, 0.8]]), ["logistics"])

    def test_adapter_rejects_transform_before_fit(self):
        with self.assertRaises(RuntimeError):
            BusinessEmbeddingAdapter().transform([[1.0, 0.0]])


if __name__ == "__main__":
    unittest.main()
