import os


def is_vercel() -> bool:
    return os.getenv("VERCEL", "").strip() == "1"


def should_run_migrations() -> bool:
    configured = os.getenv("RUN_DB_MIGRATIONS")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return not is_vercel()


def should_start_worker() -> bool:
    configured = os.getenv("ENABLE_BACKGROUND_WORKER")
    if configured is not None:
        return configured.strip().lower() in {"1", "true", "yes", "on"}
    return not is_vercel()
