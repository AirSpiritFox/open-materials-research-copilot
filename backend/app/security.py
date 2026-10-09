import os
import secrets
from collections import defaultdict, deque
from pathlib import Path
from time import monotonic
from urllib.parse import urlsplit
from cryptography.fernet import Fernet, InvalidToken
from app.db import Setting
SETTING_ENV = {
    "llm_provider": "LLM_PROVIDER", "openai_api_key": "OPENAI_API_KEY",
    "openai_model": "OPENAI_MODEL", "openalex_api_key": "OPENALEX_API_KEY",
    "semantic_scholar_api_key": "SEMANTIC_SCHOLAR_API_KEY",
    "unpaywall_email": "UNPAYWALL_EMAIL", "crossref_email": "CROSSREF_MAILTO",
}
SECRET_FIELDS = ("openai_api_key", "openalex_api_key", "semantic_scholar_api_key", "unpaywall_email", "crossref_email")
def cipher():
    raw = os.getenv("CREDENTIALS_KEY")
    if not raw:
        directory = Path(os.getenv("DATA_DIR", "./data"))
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = directory / ".credentials.key"
        if not path.exists():
            try:
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as output:
                    output.write(Fernet.generate_key())
            except FileExistsError:
                pass
        raw = path.read_bytes().strip()
    try:
        return Fernet(raw.encode() if isinstance(raw, str) else raw)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("CREDENTIALS_KEY must be a Fernet key; preserve it with database backups") from exc
def load_settings(session):
    config = {key: os.getenv(env, "") for key, env in SETTING_ENV.items()}
    rows = session.query(Setting).all()
    if rows:
        crypt = cipher()
        for row in rows:
            try:
                config[row.key] = crypt.decrypt(row.encrypted_value.encode()).decode()
            except InvalidToken as exc:
                raise RuntimeError("Stored credentials cannot be decrypted; restore the original CREDENTIALS_KEY") from exc
    config["llm_provider"] = config.get("llm_provider") or "none"
    config["llm_model"] = config.get("openai_model") or ""
    config["llm_api_key"] = config.get("openai_api_key") or ""
    if config["llm_provider"] == "ollama":
        config["llm_model"] = os.getenv("OLLAMA_MODEL", "llama3.2")
        config["llm_base_url"] = validate_base(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"), local=True)
    else:
        config["llm_base_url"] = validate_base(os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    return config
def validate_base(value, local=False):
    parsed = urlsplit(value)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or not parsed.hostname:
        raise RuntimeError("Model base URL must not contain credentials, query parameters or fragments")
    if local:
        if parsed.scheme not in ("http", "https"):
            raise RuntimeError("Ollama requires an HTTP(S) base URL")
    elif parsed.scheme != "https":
        raise RuntimeError("OpenAI-compatible remote APIs require HTTPS")
    return value.rstrip("/")
def safe_settings(config):
    return {
        "llm_provider": config.get("llm_provider", "none"),
        "model": config.get("llm_model", ""),
        "openai_model": config.get("openai_model", ""),
        "configured": {key: bool(config.get(key)) for key in SECRET_FIELDS},
        "ollama_model": os.getenv("OLLAMA_MODEL", "llama3.2"),
    }
def update_settings(session, update):
    crypt = cipher()
    for key, value in update.model_dump(exclude_none=True).items():
        row = session.get(Setting, key)
        encoded = crypt.encrypt(value.encode()).decode()
        if row:
            row.encrypted_value = encoded
        else:
            session.add(Setting(key=key, encrypted_value=encoded))
    session.commit()
    return safe_settings(load_settings(session))
class RateLimiter:
    def __init__(self, limit=60, period=60.0, clock=monotonic):
        self.limit, self.period, self.clock = limit, period, clock
        self.buckets = defaultdict(deque)
    def allowed(self, key):
        timestamp = self.clock()
        bucket = self.buckets[key]
        while bucket and bucket[0] <= timestamp - self.period:
            bucket.popleft()
        if len(bucket) >= self.limit:
            return False
        bucket.append(timestamp)
        if len(self.buckets) > 10000:
            stale = [name for name, hits in self.buckets.items() if not hits or hits[-1] <= timestamp - self.period]
            for name in stale:
                self.buckets.pop(name, None)
        return True
def authorized(header, expected):
    if not expected:
        return True
    supplied = header.removeprefix("Bearer ") if header.startswith("Bearer ") else ""
    return secrets.compare_digest(supplied, expected)
