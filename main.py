import argparse

from benchmarks.runner import run_for_db


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Neo4j / NebulaGraph benchmark experiments."
    )
    parser.add_argument(
        "--db",
        required=True,
        choices=["neo4j", "nebulagraph"],
        help="要运行基准测试的数据库类型：neo4j 或 nebulagraph",
    )
    parser.add_argument(
        "--results-dir",
        help="结果输出目录（可选，不填则默认使用 results_neo4j / results_nebulagraph）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_for_db(args.db, args.results_dir)


if __name__ == "__main__":
    main()

