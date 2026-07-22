import tempfile
import unittest
from pathlib import Path

from app.services.storage import ImageStorage


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self):
        return b'{}'


class ImageStorageTests(unittest.TestCase):
    def test_local_fallback_writes_only_filename(self):
        storage = ImageStorage(supabase_url="", service_key="")
        with tempfile.TemporaryDirectory() as directory:
            result = storage.upload(
                content=b"image",
                content_type="image/png",
                object_path="barbearias/4/photo.png",
                local_directory=Path(directory),
            )
            self.assertEqual((Path(directory) / "photo.png").read_bytes(), b"image")
            self.assertEqual(result.public_url, "/uploads/photo.png")

    def test_supabase_upload_returns_public_url_and_authenticates(self):
        captured = {}

        def opener(request, timeout):
            captured["request"] = request
            captured["timeout"] = timeout
            return FakeResponse()

        storage = ImageStorage(
            supabase_url="https://project.supabase.co/",
            service_key="secret-service-role",
            bucket="cortaflow-images",
            opener=opener,
        )
        result = storage.upload(
            content=b"image",
            content_type="image/png",
            object_path="barbearias/4/photo name.png",
            local_directory=Path("unused"),
        )
        self.assertIn("photo%20name.png", captured["request"].full_url)
        self.assertEqual(captured["request"].get_header("Authorization"), "Bearer secret-service-role")
        self.assertEqual(
            result.public_url,
            "https://project.supabase.co/storage/v1/object/public/cortaflow-images/barbearias/4/photo%20name.png",
        )

    def test_rejects_parent_directory_path(self):
        storage = ImageStorage(supabase_url="", service_key="")
        with self.assertRaisesRegex(RuntimeError, "Caminho de imagem inválido"):
            storage.upload(
                content=b"x", content_type="image/png", object_path="../secret",
                local_directory=Path("unused"),
            )


if __name__ == "__main__":
    unittest.main()
