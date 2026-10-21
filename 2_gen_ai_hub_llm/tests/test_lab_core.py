from __future__ import annotations

import sys
from pathlib import Path
import unittest
import json

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "1_gen_ai_hub" / "src"))
sys.path.insert(0, str(ROOT / "2_gen_ai_hub_llm"))

from lab_common.config import Settings
from src.prompt_model.lab_core import (
    DEFAULT_COMPARISON_SYSTEM_PROMPT,
    compare_prompts,
    run_chat,
    run_chat_stream,
)
from src.embeddings.lab_core import (
    append_embedding_cluster_point,
    compare_and_append_embedding_clusters,
    compare_embeddings,
    cosine_similarity,
    retrieve_similar_texts,
)
from src.business_embedding.lab_core import (
    holdout_indices_by_label,
    recommend_business_queue,
    run_business_embedding_lab,
    run_business_embedding_workflow,
)


def settings() -> Settings:
    return Settings("", "", "", "", "default", "test", "", "", "test", False)


class LabCoreTests(unittest.TestCase):
    def test_compare_prompts_returns_json_friendly_pair_from_one_sdk_boundary(self):
        calls: list[tuple[list[dict[str, str]], str | None]] = []

        def fake_chat(_settings, messages, model):
            calls.append((messages, model))
            return "baseline answer" if len(messages) == 1 else "constrained answer"

        outcome = compare_prompts(
            "  LLM이 무엇인가요?  ", settings(), chat_caller=fake_chat
        )

        self.assertEqual(
            outcome,
            {
                "question": "LLM이 무엇인가요?",
                "baseline": "baseline answer",
                "constrained": "constrained answer",
            },
        )
        self.assertEqual(
            calls[0][0], [{"role": "user", "content": "LLM이 무엇인가요?"}]
        )
        self.assertEqual(calls[1][0][0]["role"], "system")
        self.assertEqual(calls[1][0][0]["content"], DEFAULT_COMPARISON_SYSTEM_PROMPT)
        self.assertEqual(calls[1][0][1]["role"], "user")
        self.assertIsNone(calls[0][1])
        json.dumps(outcome)

    def test_compare_prompts_rejects_blank_question_without_calling_sdk(self):
        with self.assertRaisesRegex(ValueError, "질문을 입력하세요"):
            compare_prompts(
                "   ",
                settings(),
                chat_caller=lambda *_: self.fail("SDK should not be called"),
            )

    def test_compare_prompts_uses_a_user_supplied_system_prompt(self):
        calls: list[tuple[list[dict[str, str]], str | None]] = []

        def fake_chat(_settings, messages, model):
            calls.append((messages, model))
            return "answer"

        compare_prompts(
            "질문",
            settings(),
            chat_caller=fake_chat,
            system_prompt="반드시 JSON 객체만 반환한다.",
        )

        self.assertEqual(
            calls[1][0][0],
            {"role": "system", "content": "반드시 JSON 객체만 반환한다."},
        )
        with self.assertRaisesRegex(ValueError, "system prompt"):
            compare_prompts("질문", settings(), chat_caller=fake_chat, system_prompt="   ")
        self.assertEqual(len(calls), 2)

    def test_run_chat_builds_history_in_core_and_returns_json_friendly_result(self):
        calls: list[tuple[list[dict[str, str]], str | None]] = []

        def fake_chat(_settings, messages, model):
            calls.append((messages, model))
            return "안녕하세요."

        outcome = run_chat(
            "  다음 질문입니다.  ",
            settings(),
            history=[
                {"role": "user", "content": "이전 질문"},
                {"role": "assistant", "content": "이전 답변"},
            ],
            system_prompt="  한국어로 답해.  ",
            model="chat-model",
            chat_caller=fake_chat,
        )

        self.assertEqual(
            outcome,
            {
                "message": "다음 질문입니다.",
                "model": "chat-model",
                "reply": "안녕하세요.",
            },
        )
        self.assertEqual(
            calls,
            [
                (
                    [
                        {"role": "system", "content": "한국어로 답해."},
                        {"role": "user", "content": "이전 질문"},
                        {"role": "assistant", "content": "이전 답변"},
                        {"role": "user", "content": "다음 질문입니다."},
                    ],
                    "chat-model",
                )
            ],
        )
        json.dumps(outcome)

    def test_run_chat_rejects_blank_message_and_invalid_history_without_calling_sdk(
        self,
    ):
        with self.assertRaisesRegex(ValueError, "질문을 입력하세요"):
            run_chat(
                " ",
                settings(),
                chat_caller=lambda *_: self.fail("SDK should not be called"),
            )
        with self.assertRaisesRegex(ValueError, "history"):
            run_chat(
                "질문",
                settings(),
                history=[{"role": "system", "content": "bad"}],
                chat_caller=lambda *_: self.fail("SDK should not be called"),
            )

    def test_run_chat_stream_yields_deltas_and_bounds_history(self):
        calls: list[tuple[list[dict[str, str]], str | None]] = []

        def fake_stream(_settings, messages, model):
            calls.append((messages, model))
            yield "안녕"
            yield "하세요"

        history = [{"role": "user", "content": str(index)} for index in range(15)]
        reply = list(
            run_chat_stream(
                "질문",
                settings(),
                history=history,
                model="chat-model",
                chat_stream_caller=fake_stream,
            )
        )

        self.assertEqual(reply, ["안녕", "하세요"])
        self.assertEqual(calls[0][1], "chat-model")
        self.assertEqual(
            [item["content"] for item in calls[0][0]],
            [str(index) for index in range(3, 15)] + ["질문"],
        )

    def test_cosine_similarity_rejects_zero_vector(self):
        self.assertAlmostEqual(cosine_similarity([1, 0], [0, 1]), 0.0)
        with self.assertRaises(ValueError):
            cosine_similarity([0, 0], [1, 0])

    def test_compare_embeddings_calls_one_injected_sdk_boundary_and_returns_json(self):
        calls: list[tuple[list[str], str | None]] = []

        def fake_embedder(texts, _settings, model):
            calls.append((list(texts), model))
            return np.asarray([[1, 0], [0.8, 0.2], [0, 1]], dtype=float)

        outcome = compare_embeddings(
            [" apple ", "orange", "phone"],
            settings(),
            model="embedding-test",
            embedder=fake_embedder,
        )

        self.assertEqual(calls, [(["apple", "orange", "phone"], "embedding-test")])
        self.assertEqual(outcome["model"], "embedding-test")
        self.assertEqual(outcome["dimensions"], 2)
        self.assertEqual(outcome["texts"], ["apple", "orange", "phone"])
        self.assertEqual(len(outcome["comparisons"]), 3)
        self.assertEqual(outcome["comparisons"][0]["left"], "apple")
        self.assertEqual(outcome["comparisons"][0]["right"], "orange")
        json.dumps(outcome)

    def test_compare_embeddings_rejects_invalid_input_without_sdk_call(self):
        no_call = lambda *_: self.fail("SDK should not be called")
        with self.assertRaisesRegex(ValueError, "두 개 이상"):
            compare_embeddings(["one"], settings(), embedder=no_call)
        with self.assertRaisesRegex(ValueError, "빈 값"):
            compare_embeddings(["one", "  "], settings(), embedder=no_call)

    def test_compare_embeddings_rejects_malformed_embedder_result(self):
        with self.assertRaisesRegex(ValueError, "2D vector"):
            compare_embeddings(
                ["one", "two"], settings(), embedder=lambda *_: np.asarray([1, 2])
            )
        with self.assertRaisesRegex(ValueError, "결과 수"):
            compare_embeddings(
                ["one", "two"], settings(), embedder=lambda *_: np.asarray([[1, 0]])
            )

    def test_append_embedding_cluster_point_embeds_only_new_text_and_reuses_state(self):
        calls: list[tuple[list[str], str | None]] = []
        vectors = {
            "apple": [1, 0, 0],
            "orange": [0.9, 0.1, 0],
            "phone": [0, 1, 0],
        }

        def fake_embedder(texts, _settings, model):
            calls.append((list(texts), model))
            return np.asarray([vectors[text] for text in texts], dtype=float)

        first = append_embedding_cluster_point(
            " apple ", None, settings(), model="embedding-test", embedder=fake_embedder
        )
        second = append_embedding_cluster_point(
            "orange", first, settings(), model="embedding-test", embedder=fake_embedder
        )
        outcome = append_embedding_cluster_point(
            "phone", second, settings(), model="embedding-test", embedder=fake_embedder
        )

        self.assertEqual(
            calls,
            [
                (["apple"], "embedding-test"),
                (["orange"], "embedding-test"),
                (["phone"], "embedding-test"),
            ],
        )
        self.assertEqual(outcome["model"], "embedding-test")
        self.assertEqual(outcome["dimensions"], 3)
        self.assertEqual(outcome["cluster_count"], 2)
        self.assertEqual([item["text"] for item in outcome["entries"]], ["apple", "orange", "phone"])
        self.assertEqual([item["index"] for item in outcome["entries"]], [1, 2, 3])
        self.assertTrue(all(len(item["vector"]) == 3 for item in outcome["entries"]))
        self.assertTrue(all(isinstance(item["x"], float) for item in outcome["entries"]))
        json.dumps(outcome)

    def test_compare_and_append_embedding_clusters_reuses_one_comparison_batch(self):
        calls: list[tuple[list[str], str | None]] = []

        def fake_embedder(texts, _settings, model):
            calls.append((list(texts), model))
            return np.asarray([[1, 0], [0, 1]], dtype=float)

        outcome = compare_and_append_embedding_clusters(
            " apple ",
            " orange ",
            None,
            settings(),
            model="embedding-test",
            embedder=fake_embedder,
        )

        self.assertEqual(calls, [(["apple", "orange"], "embedding-test")])
        self.assertEqual(outcome["comparison"]["texts"], ["apple", "orange"])
        self.assertAlmostEqual(
            outcome["comparison"]["comparisons"][0]["cosine_similarity"], 0.0
        )
        self.assertEqual(
            [item["text"] for item in outcome["cluster"]["entries"]],
            ["apple", "orange"],
        )
        self.assertEqual(outcome["cluster"]["cluster_count"], 2)
        json.dumps(outcome)

    def test_compare_and_append_embedding_clusters_keeps_each_text_once(self):
        calls: list[tuple[list[str], str | None]] = []

        def fake_embedder(texts, _settings, model):
            calls.append((list(texts), model))
            return np.asarray([[1, 0], [0, 1]], dtype=float)

        first = compare_and_append_embedding_clusters(
            "apple", "orange", None, settings(), model="embedding-test", embedder=fake_embedder
        )
        repeated = compare_and_append_embedding_clusters(
            "orange", "apple", first["cluster"], settings(), model="embedding-test", embedder=fake_embedder
        )

        self.assertEqual(calls, [(["apple", "orange"], "embedding-test"), (["orange", "apple"], "embedding-test")])
        self.assertEqual(repeated["added_texts"], [])
        self.assertEqual([entry["text"] for entry in repeated["cluster"]["entries"]], ["apple", "orange"])

    def test_append_embedding_cluster_point_validates_state_before_sdk_call(self):
        no_call = lambda *_: self.fail("SDK should not be called")
        with self.assertRaisesRegex(ValueError, "키워드"):
            append_embedding_cluster_point(" ", None, settings(), embedder=no_call)
        with self.assertRaisesRegex(ValueError, "상태 형식"):
            append_embedding_cluster_point("new", [], settings(), embedder=no_call)
        with self.assertRaisesRegex(ValueError, "모델이 변경"):
            append_embedding_cluster_point(
                "new",
                {"model": "old-model", "dimensions": 2, "entries": [{"text": "old", "vector": [1, 0]}]},
                settings(),
                model="new-model",
                embedder=no_call,
            )

    def test_append_embedding_cluster_point_rejects_dimension_change_without_mutating_state(self):
        original = {
            "model": "embedding-test",
            "dimensions": 2,
            "entries": [{"index": 1, "text": "old", "vector": [1.0, 0.0], "cluster": 0, "x": 0.0, "y": 0.0}],
        }
        before = json.loads(json.dumps(original))
        with self.assertRaisesRegex(ValueError, "차원이 변경"):
            append_embedding_cluster_point(
                "new",
                original,
                settings(),
                model="embedding-test",
                embedder=lambda *_: np.asarray([[1, 0, 0]], dtype=float),
            )
        self.assertEqual(original, before)

    def test_append_embedding_cluster_point_uses_one_cluster_then_caps_at_five(self):
        state = None
        for index in range(25):
            state = append_embedding_cluster_point(
                f"item-{index}",
                state,
                settings(),
                model="embedding-test",
                embedder=lambda texts, *_: np.asarray(
                    [[float(index), 1.0, float(index % 3)] for _ in texts]
                ),
            )
            if index == 0:
                self.assertEqual(state["cluster_count"], 1)
                self.assertEqual(state["entries"][0]["cluster"], 0)
        self.assertEqual(state["cluster_count"], 5)
        self.assertEqual(len(state["entries"]), 25)

    def test_retrieve_similar_texts_ranks_query_documents_in_one_batch(self):
        calls: list[tuple[list[str], str | None]] = []

        def fake_embedder(texts, _settings, model):
            calls.append((list(texts), model))
            return np.asarray([[1, 0], [0.9, 0.1], [0.2, 0.8], [0.8, 0.2]])

        outcome = retrieve_similar_texts(
            " 환불 요청 ",
            ["환불 절차", "배송 조회", "환불 상태"],
            settings(),
            model="embedding-test",
            top_k=2,
            embedder=fake_embedder,
        )

        self.assertEqual(
            calls,
            [(["환불 요청", "환불 절차", "배송 조회", "환불 상태"], "embedding-test")],
        )
        self.assertEqual(outcome["candidate_count"], 3)
        self.assertEqual(
            [item["document_index"] for item in outcome["results"]], [0, 2]
        )
        self.assertEqual([item["rank"] for item in outcome["results"]], [1, 2])
        json.dumps(outcome)

    def test_retrieve_similar_texts_applies_threshold_and_validates_input(self):
        outcome = retrieve_similar_texts(
            "q",
            ["near", "far"],
            settings(),
            min_similarity=0.5,
            embedder=lambda *_: np.asarray([[1, 0], [0.8, 0.2], [0, 1]]),
        )
        self.assertEqual([item["document"] for item in outcome["results"]], ["near"])

        no_call = lambda *_: self.fail("SDK should not be called")
        with self.assertRaisesRegex(ValueError, "검색 질문"):
            retrieve_similar_texts(" ", ["doc"], settings(), embedder=no_call)
        with self.assertRaisesRegex(ValueError, "top_k"):
            retrieve_similar_texts("q", ["doc"], settings(), top_k=0, embedder=no_call)
        with self.assertRaisesRegex(ValueError, "min_similarity"):
            retrieve_similar_texts("q", ["doc"], settings(), min_similarity=2, embedder=no_call)

    def test_workflow_keeps_one_holdout_per_label(self):
        cases = [
            {"id": "a1", "text": "a", "label": "payment"},
            {"id": "a2", "text": "aa", "label": "payment"},
            {"id": "b1", "text": "b", "label": "logistics"},
            {"id": "b2", "text": "bb", "label": "logistics"},
        ]
        vectors = np.asarray([[1, 0], [0.9, 0.1], [0, 1], [0.1, 0.9]], dtype=float)
        self.assertEqual(
            holdout_indices_by_label([case["label"] for case in cases]).tolist(), [3, 1]
        )
        outcome = run_business_embedding_workflow(cases, vectors, n_clusters=2)
        self.assertEqual(set(outcome["holdout_ids"]), {"a2", "b2"})
        self.assertGreaterEqual(outcome["holdout_accuracy"], 0.0)

    def test_queue_recommendation_accepts_injected_embedder(self):
        cases = [
            {"id": "a1", "text": "a", "label": "payment"},
            {"id": "a2", "text": "aa", "label": "payment"},
            {"id": "b1", "text": "b", "label": "logistics"},
            {"id": "b2", "text": "bb", "label": "logistics"},
        ]
        outcome = run_business_embedding_workflow(
            cases, [[1, 0], [0.9, 0.1], [0, 1], [0.1, 0.9]], n_clusters=2
        )
        result = recommend_business_queue(
            "new payment",
            outcome["adapter"],
            settings(),
            embedder=lambda *_: np.asarray([[1, 0]]),
        )
        self.assertEqual(result["recommended_queue"], "payment")

    def test_business_embedding_lab_returns_json_from_one_embedding_batch(self):
        cases = [
            {"id": "a1", "text": "payment one", "label": "payment"},
            {"id": "a2", "text": "payment two", "label": "payment"},
            {"id": "b1", "text": "logistics one", "label": "logistics"},
            {"id": "b2", "text": "logistics two", "label": "logistics"},
        ]
        calls = []

        def fake_embedder(texts, _settings, model):
            calls.append((list(texts), model))
            return np.asarray(
                [[1, 0], [0.9, 0.1], [0, 1], [0.1, 0.9], [0.8, 0.2]], dtype=float
            )

        outcome = run_business_embedding_lab(
            "  새 결제 문의  ",
            cases,
            settings(),
            n_clusters=2,
            model="embedding-test",
            embedder=fake_embedder,
        )

        self.assertEqual(
            calls,
            [
                (
                    [
                        "payment one",
                        "payment two",
                        "logistics one",
                        "logistics two",
                        "새 결제 문의",
                    ],
                    "embedding-test",
                )
            ],
        )
        self.assertEqual(outcome["model"], "embedding-test")
        self.assertEqual(outcome["embedding_dimensions"], 2)
        self.assertEqual(len(outcome["clusters"]), 4)
        self.assertEqual(outcome["recommendation"]["recommended_queue"], "payment")
        self.assertNotIn("adapter", outcome)
        self.assertIn("상태는 변경하지 않았습니다", outcome["action"])
        json.dumps(outcome)

    def test_business_embedding_lab_rejects_bad_input_without_embedding(self):
        no_call = lambda *_: self.fail("embedder should not be called")
        cases = [{"id": "a", "text": "case", "label": "payment"}]
        with self.assertRaisesRegex(ValueError, "업무 문의"):
            run_business_embedding_lab("  ", cases, settings(), embedder=no_call)
        with self.assertRaisesRegex(ValueError, "비어 있습니다"):
            run_business_embedding_lab("ticket", [], settings(), embedder=no_call)
        with self.assertRaisesRegex(ValueError, "id, text, label"):
            run_business_embedding_lab(
                "ticket", [{"id": "a", "text": "case"}], settings(), embedder=no_call
            )


if __name__ == "__main__":
    unittest.main()
