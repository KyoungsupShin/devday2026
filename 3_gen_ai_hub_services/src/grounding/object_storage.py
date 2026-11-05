"""S3-compatible SAP BTP Object Storage adapter for grounding source files.

Object Storage keeps the original Markdown.  AI Core Document Grounding stores
text chunks separately, so this adapter deliberately uploads the same Markdown
to the selected vector repository after the object upload succeeds.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .lesson_support.config import Settings
from .lesson_support.grounding_repository import upload_text_document


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _binding_credentials() -> dict[str, Any]:
    """Find an S3-like credential object in a BTP ``VCAP_SERVICES`` binding."""
    raw = os.getenv("VCAP_SERVICES", "").strip()
    if not raw:
        return {}
    try:
        services = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(services, dict):
        return {}
    for label, bindings in services.items():
        if not any(term in label.lower() for term in ("object", "s3", "storage")):
            continue
        if not isinstance(bindings, list):
            continue
        for binding in bindings:
            credentials = binding.get("credentials", {}) if isinstance(binding, dict) else {}
            if isinstance(credentials, dict):
                return credentials
    return {}


def _credential(credentials: dict[str, Any], *names: str) -> str:
    for name in names:
        value = _clean(credentials.get(name))
        if value:
            return value
    return ""


@dataclass(frozen=True)
class ObjectStorageConfig:
    endpoint: str
    access_key_id: str
    secret_access_key: str
    bucket: str
    region: str = ""
    prefix: str = "grounding"

    @classmethod
    def from_environment(cls) -> "ObjectStorageConfig":
        credentials = _binding_credentials()
        endpoint = _clean(os.getenv("OBJECT_STORAGE_ENDPOINT")) or _credential(
            credentials, "endpoint", "s3_endpoint", "url"
        )
        access_key_id = _clean(os.getenv("OBJECT_STORAGE_ACCESS_KEY_ID")) or _credential(
            credentials, "access_key_id", "accessKeyId", "access_key", "accessKey"
        )
        secret_access_key = _clean(os.getenv("OBJECT_STORAGE_SECRET_ACCESS_KEY")) or _credential(
            credentials, "secret_access_key", "secretAccessKey", "secret_key", "secretKey"
        )
        bucket = _clean(os.getenv("OBJECT_STORAGE_BUCKET")) or _credential(credentials, "bucket", "bucket_name")
        region = _clean(os.getenv("OBJECT_STORAGE_REGION")) or _credential(credentials, "region")
        prefix = _clean(os.getenv("OBJECT_STORAGE_PREFIX")) or "grounding"
        if endpoint and "://" not in endpoint:
            endpoint = f"https://{endpoint}"
        return cls(endpoint, access_key_id, secret_access_key, bucket, region, prefix)

    def missing_fields(self) -> list[str]:
        fields = {
            "OBJECT_STORAGE_ENDPOINT": self.endpoint,
            "OBJECT_STORAGE_ACCESS_KEY_ID": self.access_key_id,
            "OBJECT_STORAGE_SECRET_ACCESS_KEY": self.secret_access_key,
            "OBJECT_STORAGE_BUCKET": self.bucket,
        }
        return [name for name, value in fields.items() if not value]

    def require_configured(self) -> None:
        missing = self.missing_fields()
        if missing:
            raise RuntimeError(
                "SAP BTP Object Storage 설정이 없습니다: " + ", ".join(missing) +
                ". .env 또는 VCAP_SERVICES service binding을 설정하세요."
            )

    def object_key(self, filename: str, requested_key: str = "") -> str:
        name = Path(filename).name
        requested = _clean(requested_key)
        if requested.startswith(("/", "\\")):
            raise ValueError("Object Storage key는 상대 경로여야 하며 '..'을 포함할 수 없습니다.")
        candidate = requested or str(PurePosixPath(self.prefix.strip("/")) / name)
        normalized = PurePosixPath(candidate.replace("\\", "/"))
        if not candidate or normalized.is_absolute() or ".." in normalized.parts or str(normalized) in {"", "."}:
            raise ValueError("Object Storage key는 상대 경로여야 하며 '..'을 포함할 수 없습니다.")
        if normalized.suffix.lower() != ".md":
            raise ValueError("Object Storage 업로드는 UTF-8 .md 파일만 지원합니다.")
        return normalized.as_posix()

    def client(self) -> Any:
        self.require_configured()
        try:
            import boto3
        except ImportError as error:
            raise RuntimeError("boto3가 없습니다. requirements.txt를 설치하세요.") from error
        options: dict[str, Any] = {
            "service_name": "s3",
            "endpoint_url": self.endpoint,
            "aws_access_key_id": self.access_key_id,
            "aws_secret_access_key": self.secret_access_key,
        }
        if self.region:
            options["region_name"] = self.region
        return boto3.client(**options)


@dataclass(frozen=True)
class ObjectStorageGroundingUpload:
    bucket: str
    object_key: str
    document_id: str
    etag: str


def upload_markdown_to_object_storage_and_grounding(
    settings: Settings,
    repository_id: str,
    *,
    file_path: str | Path,
    requested_key: str = "",
    storage: ObjectStorageConfig | None = None,
    storage_client: Any | None = None,
) -> ObjectStorageGroundingUpload:
    """Store a Markdown source object, then index its text in AI Core Grounding.

    If vector indexing fails, the object is intentionally retained.  The caller
    can retry indexing without losing the source document, and the exception
    makes this partial success explicit rather than silently claiming completion.
    """
    path = Path(file_path)
    if path.suffix.lower() != ".md":
        raise ValueError("SAP BTP Object Storage에는 UTF-8 .md 파일만 업로드할 수 있습니다.")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("비어 있는 문서는 업로드할 수 없습니다.")

    configuration = storage or ObjectStorageConfig.from_environment()
    configuration.require_configured()
    key = configuration.object_key(path.name, requested_key)
    response = (storage_client or configuration.client()).put_object(
        Bucket=configuration.bucket, Key=key, Body=text.encode("utf-8"), ContentType="text/markdown; charset=utf-8"
    )
    document_id = f"s3://{configuration.bucket}/{key}"
    try:
        upload_text_document(
            settings, repository_id, filename=path.name, text=text, document_id=document_id,
            metadata={
                "source_type": "sap_btp_object_storage",
                "object_storage_bucket": configuration.bucket,
                "object_storage_key": key,
                "object_storage_uri": document_id,
            },
        )
    except Exception as error:
        raise RuntimeError(
            f"Object Storage 업로드는 완료됐지만 Grounding 인덱싱에 실패했습니다. "
            f"재시도할 object: s3://{configuration.bucket}/{key}"
        ) from error
    return ObjectStorageGroundingUpload(
        bucket=configuration.bucket, object_key=key, document_id=document_id, etag=_clean(response.get("ETag"))
    )
