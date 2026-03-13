import random
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import yaml
from tqdm.auto import tqdm

from .drivers import Neo4jClient, NebulaGraphClient, Neo4jConfig, NebulaGraphConfig, warmup
from .experiments import (
    default_experiment_matrix,
    run_concurrent,
    write_result_to_file,
)


def load_config() -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    root = Path(__file__).resolve().parents[1]
    cfg_path = root / "config.yaml"
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["neo4j"], cfg["nebulagraph"], cfg.get("benchmark", {}), cfg.get("results", {})


def build_neo4j_client(neo4j_cfg: Dict[str, Any]) -> Neo4jClient:
    return Neo4jClient(
        Neo4jConfig(
            uri=neo4j_cfg["uri"],
            user=neo4j_cfg["user"],
            password=neo4j_cfg["password"],
        )
    )


def build_nebula_client(nebula_cfg: Dict[str, Any]) -> NebulaGraphClient:
    return NebulaGraphClient(
        NebulaGraphConfig(
            host=nebula_cfg["host"],
            port=nebula_cfg["port"],
            user=nebula_cfg["user"],
            password=nebula_cfg["password"],
            space=nebula_cfg["space"],
        ),
        max_connection_pool_size=int(nebula_cfg.get("max_connection_pool_size", 150)),
    )


def build_query_functions(
    experiment_type: str,
    neo4j_client: Optional[Neo4jClient],
    nebula_client: Optional[NebulaGraphClient],
):
    """
    根据 experiment.query_type 返回两套闭包：Neo4j 的 read/write 和 NebulaGraph 的 read/write。
    这里用占位的 Cypher / nGQL 模板，你可以根据自己的 schema 修改。
    """

    # 以下假设：
    # - 点标签为 Person，主键字段 id
    # - 关系类型为 KNOWS
    # - 一个属性 name 建了索引，属性 age 没有索引（示例）

    # 为了支持“只跑一个数据库”，先给出默认的空操作
    neo4j_read = lambda: None
    neo4j_write = lambda: None
    nebula_read = lambda: None
    nebula_write = lambda: None

    if experiment_type == "point_lookup_id":
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
                "MATCH (n:Person {id: $id}) RETURN n", {"id": random.randint(1, 1_000_000)}
            )
            # 写操作在纯读实验中基本不会被调用，给一个非常轻量的占位
            neo4j_write = lambda: neo4j_client.run_write(
                "CREATE (n:Person {id: $id, name: $name})",
                {"id": random.randint(1_000_001, 2_000_000), "name": "test"},
            )
        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read(
                f"FETCH PROP ON person {random.randint(1, 1_000_000)} YIELD properties(vertex);"
            )
            nebula_write = lambda: nebula_client.run_write(
                f"INSERT VERTEX person(name) VALUES {random.randint(1_000_001, 2_000_000)}:(\"test\");"
            )

    elif experiment_type == "point_lookup_indexed_property":
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
            "MATCH (n:Person) WHERE n.name = $name RETURN n LIMIT 10",
            {"name": f"user_{random.randint(1, 1_000_000)}"},
        )
        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read(
                f"LOOKUP ON person WHERE person.name == \"user_{random.randint(1, 1_000_000)}\" "
                "YIELD person.name, person.age;"
            )
            nebula_write = lambda: nebula_client.run_write(
                f"INSERT VERTEX person(name) VALUES "
                f"{random.randint(1_000_001, 2_000_000)}:(\"user_{random.randint(1, 1_000_000)}\");"
            )

    elif experiment_type == "point_lookup_non_indexed_property":
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
                "MATCH (n:Person) WHERE n.age = $age RETURN n LIMIT 10",
                {"age": random.randint(18, 80)},
            )
            neo4j_write = lambda: neo4j_client.run_write(
                "CREATE (n:Person {id: $id, age: $age})",
                {"id": random.randint(1_000_001, 2_000_000), "age": random.randint(18, 80)},
            )
        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read(
                f"LOOKUP ON person WHERE person.age == {random.randint(18, 80)} "
                "YIELD person.age;"
            )
            nebula_write = lambda: nebula_client.run_write(
                f"INSERT VERTEX person(age) VALUES "
                f"{random.randint(1_000_001, 2_000_000)}:({random.randint(18, 80)});"
            )

    elif experiment_type == "one_hop_neighbors_normal":
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
                "MATCH (n:Person {id: $id})-[:KNOWS]->(m) RETURN m LIMIT 100",
                {"id": random.randint(1, 1_000_000)},
            )
            neo4j_write = lambda: neo4j_client.run_write(
                "MATCH (a:Person {id: $id1}), (b:Person {id: $id2}) CREATE (a)-[:KNOWS]->(b)",
                {"id1": random.randint(1, 1_000_000), "id2": random.randint(1, 1_000_000)},
            )
        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read(
                f"GO 1 STEPS FROM {random.randint(1, 1_000_000)} OVER knows YIELD dst(edge) | LIMIT 100;"
            )
            nebula_write = lambda: nebula_client.run_write(
                f"INSERT EDGE knows() VALUES "
                f"{random.randint(1, 1_000_000)}->{random.randint(1, 1_000_000)}:();"
            )

    elif experiment_type == "one_hop_neighbors_super":
        # 假设 1~100 是超级节点
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
                "MATCH (n:Person {id: $id})-[:KNOWS]->(m) RETURN m LIMIT 1000",
                {"id": random.randint(1, 100)},
            )
            neo4j_write = lambda: neo4j_client.run_write(
                "MATCH (a:Person {id: $id1}), (b:Person {id: $id2}) CREATE (a)-[:KNOWS]->(b)",
                {"id1": random.randint(1, 100), "id2": random.randint(1, 1_000_000)},
            )
        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read(
                f"GO 1 STEPS FROM {random.randint(1, 100)} OVER knows YIELD dst(edge) | LIMIT 1000;"
            )
            nebula_write = lambda: nebula_client.run_write(
                f"INSERT EDGE knows() VALUES "
                f"{random.randint(1, 100)}->{random.randint(1, 1_000_000)}:();"
            )

    elif experiment_type == "multi_hop_neighbors":
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
                "MATCH (n:Person {id: $id})-[:KNOWS*1..3]->(m) RETURN m LIMIT 200",
                {"id": random.randint(1, 1_000_000)},
            )
            neo4j_write = lambda: neo4j_client.run_write(
                "CREATE (n:Person {id: $id})",
                {"id": random.randint(2_000_001, 3_000_000)},
            )
        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read(
                f"GO 3 STEPS FROM {random.randint(1, 1_000_000)} OVER knows YIELD dst(edge) | LIMIT 200;"
            )
            nebula_write = lambda: nebula_client.run_write(
                f"INSERT VERTEX person() VALUES {random.randint(2_000_001, 3_000_000)}:();"
            )

    elif experiment_type == "shortest_path":
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
                "MATCH (a:Person {id: $id1}), (b:Person {id: $id2}), "
                "p = shortestPath((a)-[:KNOWS*..5]-(b)) "
                "RETURN p LIMIT 1",
                {"id1": random.randint(1, 1_000_000), "id2": random.randint(1, 1_000_000)},
            )
            neo4j_write = lambda: neo4j_client.run_write(
                "MATCH (a:Person {id: $id1}), (b:Person {id: $id2}) "
                "MERGE (a)-[:KNOWS]->(b)",
                {"id1": random.randint(1, 1_000_000), "id2": random.randint(1, 1_000_000)},
            )
        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read(
                f"FIND SHORTEST PATH FROM {random.randint(1, 1_000_000)} "
                f"TO {random.randint(1, 1_000_000)} OVER knows UPTO 5 STEPS YIELD path AS p;"
            )
            nebula_write = lambda: nebula_client.run_write(
                f"INSERT EDGE knows() VALUES "
                f"{random.randint(1, 1_000_000)}->{random.randint(1, 1_000_000)}:();"
            )

    elif experiment_type == "aggregation":
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
                "MATCH (n:Person) WHERE n.age >= $min_age "
                "RETURN n.age AS age, count(*) AS cnt",
                {"min_age": 30},
            )
            neo4j_write = lambda: neo4j_client.run_write(
                "CREATE (n:Person {id: $id, age: $age})",
                {"id": random.randint(3_000_001, 4_000_000), "age": random.randint(18, 80)},
            )
        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read(
                "LOOKUP ON person WHERE person.age >= 30 YIELD person.age AS age | "
                "GROUP BY $-.age YIELD $-.age AS age, count(*) AS cnt;"
            )
            nebula_write = lambda: nebula_client.run_write(
                f"INSERT VERTEX person(age) VALUES "
                f"{random.randint(3_000_001, 4_000_000)}:({random.randint(18, 80)});"
            )

    elif experiment_type == "insert_nodes_edges":
        # 纯写：插入点 + 边
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
                "MATCH (n:Person) RETURN n LIMIT 1"
            )
            neo4j_write = lambda: neo4j_client.run_write(
                "CREATE (a:Person {id: $id1})-[:KNOWS]->(b:Person {id: $id2})",
                {"id1": random.randint(4_000_001, 5_000_000), "id2": random.randint(4_000_001, 5_000_000)},
            )
        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read("SHOW HOSTS;")
            nebula_write = lambda: nebula_client.run_write(
                f"INSERT VERTEX person() VALUES {random.randint(4_000_001, 5_000_000)}:(); "
                f"INSERT EDGE knows() VALUES "
                f"{random.randint(4_000_001, 5_000_000)}->{random.randint(4_000_001, 5_000_000)}:();"
            )

    elif experiment_type == "batch_insert_nodes_edges":
        if neo4j_client is not None:
            def neo4j_batch_write():
                ids = [
                    (random.randint(5_000_001, 6_000_000), random.randint(5_000_001, 6_000_000))
                    for _ in range(100)
                ]
                for id1, id2 in ids:
                    neo4j_client.run_write(
                        "CREATE (a:Person {id: $id1})-[:KNOWS]->(b:Person {id: $id2})",
                        {"id1": id1, "id2": id2},
                    )

            neo4j_write = neo4j_batch_write
            neo4j_read = lambda: neo4j_client.run_read("MATCH (n:Person) RETURN n LIMIT 1")

        if nebula_client is not None:
            def nebula_batch_write():
                values_v = []
                values_e = []
                for _ in range(100):
                    id1 = random.randint(5_000_001, 6_000_000)
                    id2 = random.randint(5_000_001, 6_000_000)
                    values_v.append(f"{id1}:()")
                    values_e.append(f"{id1}->{id2}:()")
                nebula_client.run_write(
                    "INSERT VERTEX person() VALUES " + ", ".join(values_v) + ";"
                )
                nebula_client.run_write(
                    "INSERT EDGE knows() VALUES " + ", ".join(values_e) + ";"
                )

            nebula_write = nebula_batch_write
            nebula_read = lambda: nebula_client.run_read("SHOW HOSTS;")

    elif experiment_type == "update_delete":
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
                "MATCH (n:Person {id: $id}) RETURN n",
                {"id": random.randint(1, 1_000_000)},
            )
            neo4j_write = lambda: neo4j_client.run_write(
                "MATCH (n:Person {id: $id}) SET n.age = $age",
                {"id": random.randint(1, 1_000_000), "age": random.randint(18, 80)},
            )
        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read(
                f"FETCH PROP ON person {random.randint(1, 1_000_000)} YIELD properties(vertex);"
            )
            nebula_write = lambda: nebula_client.run_write(
                f"UPDATE VERTEX ON person {random.randint(1, 1_000_000)} "
                f"SET person.age = {random.randint(18, 80)};"
            )

    elif experiment_type == "mixed_read_heavy":
        # 读多写少：使用一跳邻居 + 点查作为读操作，插入小量边作为写
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
                "MATCH (n:Person {id: $id})-[:KNOWS]->(m) RETURN m LIMIT 50",
                {"id": random.randint(1, 1_000_000)},
            )
            neo4j_write = lambda: neo4j_client.run_write(
                "MATCH (a:Person {id: $id1}), (b:Person {id: $id2}) "
                "MERGE (a)-[:KNOWS]->(b)",
                {"id1": random.randint(1, 1_000_000), "id2": random.randint(1, 1_000_000)},
            )
        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read(
                f"GO 1 STEPS FROM {random.randint(1, 1_000_000)} OVER knows "
                "YIELD dst(edge) | LIMIT 50;"
            )
            nebula_write = lambda: nebula_client.run_write(
                f"INSERT EDGE knows() VALUES "
                f"{random.randint(1, 1_000_000)}->{random.randint(1, 1_000_000)}:();"
            )

    elif experiment_type == "mixed_stress":
        # 读写各半：读用多跳/最短路径，写用插入+更新
        if neo4j_client is not None:
            neo4j_read = lambda: neo4j_client.run_read(
                "MATCH (a:Person {id: $id1}), (b:Person {id: $id2}), "
                "p = shortestPath((a)-[:KNOWS*..4]-(b)) "
                "RETURN p LIMIT 1",
                {"id1": random.randint(1, 1_000_000), "id2": random.randint(1, 1_000_000)},
            )

            def neo4j_write():
                if random.random() < 0.5:
                    neo4j_client.run_write(
                        "CREATE (n:Person {id: $id, age: $age})",
                        {"id": random.randint(6_000_001, 7_000_000), "age": random.randint(18, 80)},
                    )
                else:
                    neo4j_client.run_write(
                        "MATCH (n:Person {id: $id}) SET n.age = $age",
                        {"id": random.randint(1, 1_000_000), "age": random.randint(18, 80)},
                    )

            neo4j_write = neo4j_write

        if nebula_client is not None:
            nebula_read = lambda: nebula_client.run_read(
                f"FIND SHORTEST PATH FROM {random.randint(1, 1_000_000)} "
                f"TO {random.randint(1, 1_000_000)} OVER knows UPTO 4 STEPS YIELD path AS p;"
            )

            def nebula_write():
                if random.random() < 0.5:
                    nebula_client.run_write(
                        f"INSERT VERTEX person(age) VALUES "
                        f"{random.randint(6_000_001, 7_000_000)}:({random.randint(18, 80)});"
                    )
                else:
                    nebula_client.run_write(
                        f"UPDATE VERTEX ON person {random.randint(1, 1_000_000)} "
                        f"SET person.age = {random.randint(18, 80)};"
                    )

            nebula_write = nebula_write

    else:
        raise ValueError(f"Unknown experiment type: {experiment_type}")

    return (neo4j_read, neo4j_write), (nebula_read, nebula_write)


def run_for_db(target_db: str, result_subdir: Optional[str] = None) -> None:
    """
    只针对指定数据库运行一轮完整实验。
    target_db: "neo4j" 或 "nebulagraph"
    result_subdir: 若提供，则结果写入该目录；否则默认使用 results_neo4j / results_nebulagraph
    """
    neo4j_cfg, nebula_cfg, bench_cfg, results_cfg = load_config()
    total_requests = int(bench_cfg.get("requests_per_experiment", 10000))
    random_seed = int(bench_cfg.get("random_seed", 42))
    random.seed(random_seed)

    base_dir_name = results_cfg.get("dir", "results")
    if result_subdir:
        result_dir = Path(result_subdir)
    else:
        result_dir = Path(f"{base_dir_name}_{target_db}")

    experiments = default_experiment_matrix()

    if target_db == "neo4j":
        client = build_neo4j_client(neo4j_cfg)
        try:
            # 初始化一次 Person 标签和 KNOWS 关系类型，避免 UnknownLabel / UnknownRelationshipType 警告
            try:
                client.run_write(
                    "MERGE (a:Person {id: 1}) "
                    "ON CREATE SET a.name = 'user_1', a.age = 30"
                )
                client.run_write(
                    "MERGE (b:Person {id: 2}) "
                    "ON CREATE SET b.name = 'user_2', b.age = 31"
                )
                client.run_write(
                    "MATCH (a:Person {id: 1}), (b:Person {id: 2}) "
                    "MERGE (a)-[:KNOWS]->(b)"
                )
            except Exception:
                # 初始化失败不影响后续基准测试，简单忽略
                pass

            for exp in tqdm(experiments, desc="neo4j experiments"):
                (neo4j_read, neo4j_write), _ = build_query_functions(
                    exp.query_type, client, None
                )
                warmup(client, neo4j_read)
                for conc in exp.concurrency_levels:
                    neo4j_result = run_concurrent(
                        experiment=exp,
                        db_name="neo4j",
                        concurrency=conc,
                        total_requests=total_requests,
                        read_op=neo4j_read,
                        write_op=neo4j_write,
                    )
                    write_result_to_file(neo4j_result, result_dir)
        finally:
            client.close()

    elif target_db == "nebulagraph":
        client = build_nebula_client(nebula_cfg)
        try:
            # 初始化 schema：创建 person 标签、knows 边类型，以及 LOOKUP 所需的属性索引
            client.run_write("CREATE TAG IF NOT EXISTS person(name string, age int);")
            client.run_write("CREATE EDGE IF NOT EXISTS knows();")
            time.sleep(3)
            # LOOKUP 按 name/age 查询需要对应 tag index，否则报 "There is no index to use at runtime"
            try:
                client.run_write("CREATE TAG INDEX IF NOT EXISTS person_name_index ON person(name(255));")
                client.run_write("CREATE TAG INDEX IF NOT EXISTS person_age_index ON person(age);")
                time.sleep(5)
                client.run_write("REBUILD TAG INDEX person_name_index;")
                client.run_write("REBUILD TAG INDEX person_age_index;")
                time.sleep(5)
            except Exception:
                pass
            # schema 异步生效，再等一会再跑查询
            time.sleep(5)

            for exp in tqdm(experiments, desc="nebulagraph experiments"):
                _, (nebula_read, nebula_write) = build_query_functions(
                    exp.query_type, None, client
                )
                warmup(client, nebula_read)
                for conc in exp.concurrency_levels:
                    nebula_result = run_concurrent(
                        experiment=exp,
                        db_name="nebulagraph",
                        concurrency=conc,
                        total_requests=total_requests,
                        read_op=nebula_read,
                        write_op=nebula_write,
                    )
                    write_result_to_file(nebula_result, result_dir)
        finally:
            client.close()

    else:
        raise ValueError("target_db must be 'neo4j' or 'nebulagraph'")


def main() -> None:
    """
    保留原 main 以兼容直接运行 runner.py，但建议使用项目根目录的 main.py。
    这里简单依次跑 Neo4j 和 NebulaGraph，两者结果写入不同目录。
    """
    run_for_db("neo4j")
    run_for_db("nebulagraph")


if __name__ == "__main__":
    main()
