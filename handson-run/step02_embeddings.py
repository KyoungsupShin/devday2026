# -*- coding: utf-8 -*-
"""Step 2 · 임베딩 & 코사인 유사도 (실습자용 모듈 2)
  1) 임베딩 생성 (1536차원 확인)
  2) 버그 함수 vs 수정 함수 비교 (교재의 '직접 고쳐보기')
  3) 의미 유사도 비교
실행: .venv/bin/python step02_embeddings.py
"""
import _env
_env.load()

from scipy import spatial
from gen_ai_hub.proxy.native.openai import embeddings

EMBED_MODEL = "text-embedding-3-small"

print("=" * 56)
print("Step 2 · 임베딩 & 코사인 유사도")
print("=" * 56)


def get_embedding(text):
    return embeddings.create(input=text, model_name=EMBED_MODEL).data[0].embedding


# 1) 임베딩 생성
print("\n[1] 임베딩 생성")
apple = get_embedding("apple")
orange = get_embedding("orange")
phone = get_embedding("phone")
dog = get_embedding("I love dogs")
animals = get_embedding("I love animals")
cat = get_embedding("I hate cats")
print(f"  'apple' → {len(apple)}차원 벡터")

# 2) 버그 함수 vs 수정 함수
print("\n[2] 버그 함수 vs 수정 함수")


def cosine_buggy(v1, v2):
    return 1 - spatial.distance.cosine(v1, v1)   # ← 버그: v1 두 번


def cosine_fixed(v1, v2):
    return 1 - spatial.distance.cosine(v1, v2)   # ← 정답


print(f"  버그 cosine(apple, orange) = {cosine_buggy(apple, orange):.3f}  (항상 1.0)")
print(f"  수정 cosine(apple, orange) = {cosine_fixed(apple, orange):.3f}")

# 3) 의미 유사도 비교
print("\n[3] 의미 유사도 비교 (수정 함수)")
print(f"  apple-orange : {cosine_fixed(apple, orange):.3f}")
print(f"  apple-phone  : {cosine_fixed(apple, phone):.3f}")
print(f"  dog-animals  : {cosine_fixed(dog, animals):.3f}")
print(f"  dog-cat(hate): {cosine_fixed(dog, cat):.3f}")

ok1 = cosine_fixed(apple, orange) > cosine_fixed(apple, phone)
ok2 = cosine_fixed(dog, animals) > cosine_fixed(dog, cat)
print(f"\n  apple-orange > apple-phone ? {ok1}")
print(f"  dog-animals  > dog-cat     ? {ok2}")
print("\n✅ Step 2 완료 — 의미가 가까운 쌍이 더 높은 유사도.")
