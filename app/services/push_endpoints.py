from urllib.parse import urlsplit


def validate_push_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    host = (parsed.hostname or "").lower()
    allowed = host in {
        "fcm.googleapis.com", "updates.push.services.mozilla.com", "web.push.apple.com",
    } or host.endswith(".notify.windows.com")
    if (parsed.scheme != "https" or not allowed or parsed.username or parsed.password
            or parsed.port not in (None, 443) or parsed.fragment
            or any(character.isspace() for character in value)):
        raise ValueError("Endpoint de notificacao invalido")
    return value
