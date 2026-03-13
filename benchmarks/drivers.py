import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Callable, Optional

from neo4j import GraphDatabase, Driver as Neo4jDriver
from neo4j.exceptions import ConstraintError
from nebula3.gclient.net import ConnectionPool
from nebula3.Config import Config as NebulaConfig

try:
    from nebula3.Exception import (
        AuthFailedException,
        NoValidSessionException,
        SessionException,
    )
except ImportError:
    AuthFailedException = type("AuthFailedException", (Exception,), {})
    NoValidSessionException = type("NoValidSessionException", (Exception,), {})
    SessionException = type("SessionException", (Exception,), {})

def _is_session_related_error(e: Exception) -> bool:
    return (
        isinstance(e, (AuthFailedException, NoValidSessionException, SessionException))
        or "session" in str(e).lower()
        or "cache" in str(e).lower()
    )


@dataclass
class Neo4jConfig:
    uri: str
    user: str
    password: str


@dataclass
class NebulaGraphConfig:
    host: str
    port: int
    user: str
    password: str
    space: str


class Neo4jClient:
    def __init__(self, config: Neo4jConfig):
        self._driver: Neo4jDriver = GraphDatabase.driver(
            config.uri,
            auth=(config.user, config.password),
        )

    def close(self) -> None:
        self._driver.close()

    def run_read(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        with self._driver.session() as session:
            result = session.run(cypher, params or {})
            return [r.data() for r in result]

    def run_write(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> None:
        with self._driver.session() as session:
            try:
                session.run(cypher, params or {})
            except ConstraintError:
                # 在基准测试场景下，随机 ID 可能违反唯一约束，这里直接忽略以保证测试继续进行
                pass


class NebulaGraphClient:
    def __init__(self, config: NebulaGraphConfig, max_connection_pool_size: int = 150):
        nebula_conf = NebulaConfig()
        nebula_conf.max_connection_pool_size = max_connection_pool_size
        self._pool = ConnectionPool()
        if not self._pool.init([(config.host, config.port)], nebula_conf):
            raise RuntimeError("Failed to initialize NebulaGraph connection pool")
        self._config = config
        self._lock = threading.Lock()

    def close(self) -> None:
        self._pool.close()

    @contextmanager
    def _session(self):
        session = None
        last_error = None
        for attempt in range(5):
            try:
                session = self._pool.get_session(self._config.user, self._config.password)
                break
            except Exception as e:
                last_error = e
                if attempt < 4 and _is_session_related_error(e):
                    time.sleep(0.5 * (attempt + 1))
                    continue
                raise
        if session is None:
            raise last_error or RuntimeError("Failed to get session")
        try:
            session.execute(f"USE {self._config.space}")
            yield session
        finally:
            session.release()

    def run_read(self, nql: str) -> List[Dict[str, Any]]:
        with self._session() as session:
            res = session.execute(nql)
            if not res.is_succeeded():
                raise RuntimeError(f"NebulaGraph query failed: {res.error_msg()}")
            # 这里简单返回列表，对实验来说主要关心延迟而不是内容
            col_names = res.keys()
            rows = []
            for row in res.rows():
                rows.append({name: row.values[i] for i, name in enumerate(col_names)})
            return rows

    def run_write(self, nql: str) -> None:
        with self._session() as session:
            res = session.execute(nql)
            if not res.is_succeeded():
                msg = res.error_msg()
                err = msg.decode() if isinstance(msg, bytes) else str(msg)
                # 基准测试中 UPDATE 可能作用在不存在的点上，忽略此类错误以继续压测
                if "not found" in err.lower():
                    return
                raise RuntimeError(f"NebulaGraph write failed: {msg}")


def warmup(client: Any, query_fn: Callable[[], None], times: int = 100) -> None:
    """
    简单预热，避免首次连接和 JIT 等影响正式测试。
    """
    for _ in range(times):
        query_fn()

