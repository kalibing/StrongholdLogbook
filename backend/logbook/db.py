from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .config import settings


def connection_pool() -> ConnectionPool:
    return ConnectionPool(
        kwargs={**settings.connect_kwargs, "row_factory": dict_row},
        min_size=1,
        max_size=8,
        timeout=5,
        open=False,
    )
