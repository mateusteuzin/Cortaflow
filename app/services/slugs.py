import re
import unicodedata


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    return slug[:140].rstrip("-") or "barbearia"


def unique_shop_slug(cursor, name: str) -> str:
    base = slugify(name)
    candidate = base
    suffix = 2
    while True:
        cursor.execute("SELECT 1 FROM barbearias WHERE slug=%s", (candidate,))
        if not cursor.fetchone():
            return candidate
        candidate = f"{base[:140-len(str(suffix))-1]}-{suffix}"
        suffix += 1
