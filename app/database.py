import os
from contextlib import contextmanager
from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor

_pool = None

def pool():
    global _pool
    if _pool is None:
        url = os.getenv("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL não configurada. Use a conexão do Supabase no arquivo .env")
        minimum = int(os.getenv("DB_POOL_MIN", "1"))
        maximum = int(os.getenv("DB_POOL_MAX", "5"))
        if minimum < 1 or maximum < minimum:
            raise RuntimeError("DB_POOL_MIN e DB_POOL_MAX possuem valores inválidos")
        _pool = ThreadedConnectionPool(minimum, maximum, url)
    return _pool

@contextmanager
def db():
    conn = pool().getconn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        pool().putconn(conn)

def one(sql, params=()):
    with db() as cur:
        cur.execute(sql, params)
        return cur.fetchone()

def all_rows(sql, params=()):
    with db() as cur:
        cur.execute(sql, params)
        return cur.fetchall()
