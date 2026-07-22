import json
import os
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from ..runtime import is_vercel


class StorageConfigurationError(RuntimeError):
    pass


class StorageUploadError(RuntimeError):
    pass


@dataclass(frozen=True)
class StoredImage:
    public_url: str
    object_path: str


class ImageStorage:
    def __init__(self, *, supabase_url=None, service_key=None, bucket=None, opener=urlopen):
        self.supabase_url = (supabase_url if supabase_url is not None else os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.service_key = service_key if service_key is not None else os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket = bucket or os.getenv("SUPABASE_STORAGE_BUCKET", "cortaflow-images")
        self.opener = opener

    @property
    def configured(self) -> bool:
        return bool(self.supabase_url and self.service_key and self.bucket)

    def upload(self, *, content: bytes, content_type: str, object_path: str, local_directory: Path) -> StoredImage:
        safe_path = object_path.strip("/")
        if not safe_path or ".." in safe_path.split("/"):
            raise StorageUploadError("Caminho de imagem inválido")
        if self.configured:
            return self._upload_supabase(content, content_type, safe_path)
        if is_vercel():
            raise StorageConfigurationError(
                "Supabase Storage não configurado. Defina SUPABASE_URL e SUPABASE_SERVICE_ROLE_KEY na Vercel"
            )
        local_directory.mkdir(parents=True, exist_ok=True)
        filename = safe_path.rsplit("/", 1)[-1]
        (local_directory / filename).write_bytes(content)
        return StoredImage(public_url=f"/uploads/{filename}", object_path=safe_path)

    def _upload_supabase(self, content: bytes, content_type: str, object_path: str) -> StoredImage:
        encoded_bucket = quote(self.bucket, safe="")
        encoded_path = quote(object_path, safe="/")
        request = Request(
            f"{self.supabase_url}/storage/v1/object/{encoded_bucket}/{encoded_path}",
            data=content,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.service_key}",
                "apikey": self.service_key,
                "Content-Type": content_type,
                "x-upsert": "false",
            },
        )
        try:
            with self.opener(request, timeout=20) as response:
                response.read()
        except HTTPError as error:
            detail = ""
            try:
                detail = json.loads(error.read().decode("utf-8")).get("message", "")
            except (ValueError, AttributeError):
                pass
            raise StorageUploadError(detail or f"Supabase Storage recusou a imagem ({error.code})") from error
        except (URLError, TimeoutError) as error:
            raise StorageUploadError("Não foi possível enviar a imagem ao Supabase Storage") from error
        public_url = f"{self.supabase_url}/storage/v1/object/public/{encoded_bucket}/{encoded_path}"
        return StoredImage(public_url=public_url, object_path=object_path)


image_storage = ImageStorage()
