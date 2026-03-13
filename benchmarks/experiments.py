import concurrent.futures
import statistics
import time
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Tuple


@dataclass
class ExperimentConfig:
    id: str
    description: str
    read_ratio: float  # 0.0 ~ 1.0
    write_ratio: float
    query_type: str
    complexity: str
    access_pattern: str
    concurrency_levels: List[int]


@dataclass
class RunResult:
    db_name: str
    experiment_id: str
    concurrency: int
    total_requests: int
    duration_sec: float
    latencies_ms: List[float]

    def summary(self) -> Dict[str, float]:
        if not self.latencies_ms:
            return {}
        return {
            "p50": statistics.quantiles(self.latencies_ms, n=2)[0],
            "p95": statistics.quantiles(self.latencies_ms, n=20)[18],
            "p99": statistics.quantiles(self.latencies_ms, n=100)[98],
            "avg": statistics.fmean(self.latencies_ms),
            "min": min(self.latencies_ms),
            "max": max(self.latencies_ms),
            "throughput_qps": self.total_requests / self.duration_sec if self.duration_sec > 0 else 0.0,
        }


def _time_one(op: Callable[[], None]) -> float:
    start = time.perf_counter()
    op()
    end = time.perf_counter()
    return (end - start) * 1000.0


def run_concurrent(
    experiment: ExperimentConfig,
    db_name: str,
    concurrency: int,
    total_requests: int,
    read_op: Callable[[], None],
    write_op: Callable[[], None],
) -> RunResult:
    latencies: List[float] = []
    latencies_lock = threading.Lock()

    def worker(n_requests: int) -> None:
        nonlocal latencies
        for _ in range(n_requests):
            # 简单按比例决定本次是读还是写
            is_read = (time.perf_counter_ns() % 1000) / 1000.0 < experiment.read_ratio
            op = read_op if is_read else write_op
            spent = _time_one(op)
            with latencies_lock:
                latencies.append(spent)

    per_worker = total_requests // concurrency
    extra = total_requests % concurrency

    start = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = []
        for i in range(concurrency):
            n = per_worker + (1 if i < extra else 0)
            if n <= 0:
                continue
            futures.append(executor.submit(worker, n))
        for f in futures:
            f.result()
    end = time.perf_counter()

    return RunResult(
        db_name=db_name,
        experiment_id=experiment.id,
        concurrency=concurrency,
        total_requests=total_requests,
        duration_sec=end - start,
        latencies_ms=latencies,
    )


def write_result_to_file(result: RunResult, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    filename = out_dir / f"{result.experiment_id}_{result.db_name}_c{result.concurrency}.txt"
    summary = result.summary()
    with filename.open("w", encoding="utf-8") as f:
        f.write(f"Experiment: {result.experiment_id}\n")
        f.write(f"DB: {result.db_name}\n")
        f.write(f"Concurrency: {result.concurrency}\n")
        f.write(f"Total Requests: {result.total_requests}\n")
        f.write(f"Duration (sec): {result.duration_sec:.4f}\n")
        if summary:
            for k, v in summary.items():
                f.write(f"{k}: {v:.4f}\n")


def default_experiment_matrix() -> List[ExperimentConfig]:
    """
    对应之前设计的 E01-E14 的一个简化版本。
    实际查询内容在 runner 中实现，这里只定义元信息。
    """
    return [
        ExperimentConfig(
            id="E01",
            description="单点查基线性能（ID 直查）",
            read_ratio=1.0,
            write_ratio=0.0,
            query_type="point_lookup_id",
            complexity="very_simple",
            access_pattern="uniform",
            concurrency_levels=[1, 4, 16],
        ),
        ExperimentConfig(
            id="E02",
            description="属性点查 + 索引效果",
            read_ratio=1.0,
            write_ratio=0.0,
            query_type="point_lookup_indexed_property",
            complexity="simple",
            access_pattern="uniform",
            concurrency_levels=[1, 4, 16],
        ),
        ExperimentConfig(
            id="E03",
            description="非索引属性点查对比",
            read_ratio=1.0,
            write_ratio=0.0,
            query_type="point_lookup_non_indexed_property",
            complexity="simple",
            access_pattern="uniform",
            concurrency_levels=[1, 4, 16],
        ),
        ExperimentConfig(
            id="E04",
            description="一跳邻居查询（普通节点）",
            read_ratio=1.0,
            write_ratio=0.0,
            query_type="one_hop_neighbors_normal",
            complexity="simple",
            access_pattern="uniform",
            concurrency_levels=[4, 16, 64],
        ),
        ExperimentConfig(
            id="E05",
            description="一跳邻居查询（超级节点）",
            read_ratio=1.0,
            write_ratio=0.0,
            query_type="one_hop_neighbors_super",
            complexity="simple",
            access_pattern="hotspot",
            concurrency_levels=[4, 16, 64],
        ),
        ExperimentConfig(
            id="E06",
            description="多跳邻居 / 路径查询",
            read_ratio=1.0,
            write_ratio=0.0,
            query_type="multi_hop_neighbors",
            complexity="medium",
            access_pattern="uniform",
            concurrency_levels=[4, 16, 64],
        ),
        ExperimentConfig(
            id="E07",
            description="可变长度路径 / 最短路径",
            read_ratio=1.0,
            write_ratio=0.0,
            query_type="shortest_path",
            complexity="complex",
            access_pattern="mixed",
            concurrency_levels=[4, 16, 64],
        ),
        ExperimentConfig(
            id="E08",
            description="聚合统计（度分布/按属性过滤）",
            read_ratio=1.0,
            write_ratio=0.0,
            query_type="aggregation",
            complexity="medium",
            access_pattern="global",
            concurrency_levels=[4, 16, 64],
        ),
        ExperimentConfig(
            id="E10",
            description="纯增量写入（插入点/边）",
            read_ratio=0.0,
            write_ratio=1.0,
            query_type="insert_nodes_edges",
            complexity="simple_write",
            access_pattern="uniform",
            concurrency_levels=[4, 16, 64],
        ),
        ExperimentConfig(
            id="E11",
            description="批量写入（批次插入）",
            read_ratio=0.0,
            write_ratio=1.0,
            query_type="batch_insert_nodes_edges",
            complexity="batch_write",
            access_pattern="uniform",
            concurrency_levels=[4, 16, 64],
        ),
        ExperimentConfig(
            id="E12",
            description="更新/删除操作性能",
            read_ratio=0.0,
            write_ratio=1.0,
            query_type="update_delete",
            complexity="simple_write",
            access_pattern="hotspot",
            concurrency_levels=[4, 16, 64],
        ),
        ExperimentConfig(
            id="E13",
            description="读写混合（读多写少）",
            read_ratio=0.7,
            write_ratio=0.3,
            query_type="mixed_read_heavy",
            complexity="medium",
            access_pattern="mixed",
            concurrency_levels=[4, 16, 64],
        ),
        ExperimentConfig(
            id="E14",
            description="读写混合（高并发压力测试）",
            read_ratio=0.5,
            write_ratio=0.5,
            query_type="mixed_stress",
            complexity="medium_complex",
            access_pattern="hotspot",
            concurrency_levels=[16, 64, 128],
        ),
    ]

