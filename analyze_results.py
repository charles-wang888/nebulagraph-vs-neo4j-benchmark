import re
from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib
import pandas as pd

# 全局中文字体配置，避免图中中文变成方块并消除字体警告
matplotlib.rcParams["font.family"] = ["Microsoft YaHei"]
matplotlib.rcParams["axes.unicode_minus"] = False


ROOT = Path(__file__).resolve().parent
NEO_DIR = ROOT / "results_neo4j"
NEB_DIR = ROOT / "results_nebulagraph"
OUT_DIR = ROOT / "charts"
OUT_DIR.mkdir(exist_ok=True)


EXPERIMENT_PURPOSE = {
    "E01": "Point lookup by ID (按ID单点查询基线性能)",
    "E02": "Point lookup by indexed property (按有索引属性点查)",
    "E03": "Point lookup by non-indexed property (按无索引属性点查)",
    "E04": "One-hop neighbors (normal degree nodes) (一跳邻居-普通节点)",
    "E05": "One-hop neighbors (high-degree hubs) (一跳邻居-超级节点)",
    "E06": "Multi-hop neighbors / fixed-length paths (多跳邻居/固定长度路径)",
    "E07": "Shortest path queries (最短路径查询)",
    "E08": "Aggregation on properties (按属性聚合统计)",
    "E10": "Pure incremental writes (node+edge inserts) (纯增量写入-点+边)",
    "E11": "Batch inserts (批量写入)",
    "E12": "Updates (and deletes) (更新/删除操作)",
    "E13": "Mixed workload, read-heavy (读多写少混合负载)",
    "E14": "Mixed workload, stress (读写各半高并发压力)",
}


# 结果文件命名模式，例如 E01_neo4j_c4.txt / E01_nebulagraph_c4.txt
FILE_RE = re.compile(r"^(E\d+)_([^_]+)_c(\d+)\.txt$")


def parse_result_file(path: Path) -> dict:
    data = {"experiment": None, "db": None, "concurrency": None}
    m = FILE_RE.match(path.name)
    if not m:
        return None
    data["experiment"], data["db"], conc = m.groups()
    data["concurrency"] = int(conc)

    metrics = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k in {"Experiment", "DB", "Concurrency", "Total Requests"}:
                continue
            try:
                metrics[k] = float(v)
            except ValueError:
                pass
    data.update(metrics)
    return data


def load_all_results() -> pd.DataFrame:
    rows = []
    for d in [NEO_DIR, NEB_DIR]:
        if not d.exists():
            continue
        for path in sorted(d.glob("*.txt")):
            r = parse_result_file(path)
            if r is not None:
                rows.append(r)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df.rename(columns={"throughput_qps": "throughput"}, inplace=True)
    return df


def describe_experiment(exp_id: str) -> str:
    return EXPERIMENT_PURPOSE.get(exp_id, "N/A")


def make_tables_and_charts(df: pd.DataFrame) -> None:
    cols = [
        "experiment",
        "db",
        "concurrency",
        "throughput",
        "p50",
        "p95",
        "p99",
        "avg",
    ]
    df = df[cols].sort_values(["experiment", "db", "concurrency"])

    for exp_id, grp in df.groupby("experiment"):
        purpose = describe_experiment(exp_id)

        print("-" * 40)
        print(f"实验编号: {exp_id}")
        print(f"实验目的: {purpose}")
        print("1. 对比结果表 (Results table, 中英文)：")

        pivot = grp.pivot_table(
            index="concurrency",
            columns="db",
            values=["throughput", "p50", "p95", "p99", "avg"],
        )
        print(pivot.round(3).to_string())
        print()

        fig, ax1 = plt.subplots(figsize=(8, 4.5))
        ax2 = ax1.twinx()

        for db_name, color in [("neo4j", "tab:blue"), ("nebulagraph", "tab:orange")]:
            sub = grp[grp["db"] == db_name].sort_values("concurrency")
            if sub.empty:
                continue
            ax1.plot(
                sub["concurrency"],
                sub["throughput"],
                marker="o",
                linestyle="-",
                color=color,
                label=f"{db_name} throughput QPS (吞吐)",
            )

        latency_metrics = [
            ("p50", "P50 latency (P50 延迟)"),
            ("p95", "P95 latency (P95 延迟)"),
            ("p99", "P99 latency (P99 延迟)"),
            ("avg", "Avg latency (平均延迟)"),
        ]
        latency_styles = {
            "p50": ":",
            "p95": "--",
            "p99": "-.",
            "avg": "-",
        }

        for db_name, base_color in [("neo4j", "tab:blue"), ("nebulagraph", "tab:orange")]:
            sub = grp[grp["db"] == db_name].sort_values("concurrency")
            if sub.empty:
                continue
            for metric, metric_label in latency_metrics:
                ax2.plot(
                    sub["concurrency"],
                    sub[metric],
                    marker="s",
                    linestyle=latency_styles[metric],
                    linewidth=1,
                    color=base_color,
                    alpha=0.6,
                    label=f"{db_name} {metric_label}",
                )

        ax1.set_xlabel("Concurrency (并发数)")
        ax1.set_ylabel("Throughput (QPS, 吞吐)")
        ax2.set_ylabel("Latency (ms, 延迟)")

        ax1.set_title(f"{exp_id} - {purpose}")

        lines1, labels1 = ax1.get_legend_handles_labels()
        lines2, labels2 = ax2.get_legend_handles_labels()
        fig.legend(
            lines1 + lines2,
            labels1 + labels2,
            loc="upper center",
            bbox_to_anchor=(0.5, -0.12),
            ncol=2,
            fontsize=8,
        )

        fig.tight_layout()
        out_path = OUT_DIR / f"{exp_id}_all_metrics.png"
        fig.savefig(out_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        print(
            f"2. 图表 (Chart): {out_path.name} 已生成，"
            "单图包含：吞吐 + p50/p95/p99/avg，多条曲线，中英文图例。"
        )
        print("-" * 40)
        print()


def main() -> None:
    df = load_all_results()
    if df.empty:
        print("No result files found in results_neo4j / results_nebulagraph.")
        return
    make_tables_and_charts(df)


if __name__ == "__main__":
    main()

