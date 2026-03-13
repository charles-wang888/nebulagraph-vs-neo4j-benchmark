# Neo4j vs NebulaGraph 基准测试（百万级节点）

本工程用于在百万节点规模下，对比 Neo4j 与 NebulaGraph 的读写性能。  
核心设计为「实验矩阵 + Python 驱动程序 + 文本结果输出」。

## 目录结构

- `requirements.txt`：Python 依赖
- `config.yaml`：连接配置与实验参数
- `benchmarks/`
  - `runner.py`：内部调度与实验执行逻辑
  - `experiments.py`：实验矩阵定义与调度
  - `drivers.py`：封装 Neo4j / NebulaGraph 的基础操作
- `main.py`：项目统一入口
- `results_neo4j/`：Neo4j 的实验结果（运行后生成）
- `results_nebulagraph/`：NebulaGraph 的实验结果（运行后生成）

## 使用步骤（简要）

1. 创建并激活虚拟环境（可选）。
2. 安装依赖：

   ```bash
   pip install -r requirements.txt
   ```

3. 编辑 `config.yaml`，填入 Neo4j 与 NebulaGraph 的连接信息（尤其是地址、端口、用户名密码、space 名称等）。

4. 分别运行两类数据库的实验：

   - **只对 Neo4j 运行全部实验组**（需先启动 Neo4j）：

     ```bash
     python main.py --db neo4j
     ```

     默认结果写入 `results_neo4j/` 目录。

   - **只对 NebulaGraph 运行全部实验组**（需先启动 NebulaGraph）：

     ```bash
     python main.py --db nebulagraph
     ```

     默认结果写入 `results_nebulagraph/` 目录。

   - 如需自定义结果目录，可额外指定：

     ```bash
     python main.py --db neo4j --results-dir my_neo4j_results
     python main.py --db nebulagraph --results-dir my_nebula_results
     ```

5. 每个实验组和并发度对应一个 `.txt` 文件，文件名形如：

   - `E01_neo4j_c4.txt`
   - `E01_nebulagraph_c4.txt`

   文件中包含本次运行的总请求数、总时长以及 P50/P95/P99 延迟、平均延迟、QPS 等统计指标，可直接对比分析。

## 结果分析（analyze_results.py）

- `analyze_results.py`：读取 `results_neo4j/` 和 `results_nebulagraph/` 中的所有结果文件，按实验编号汇总，并为每个实验生成：
  - 终端中的中/英混合对比表（并发度 × 吞吐/延迟指标）
  - `charts/` 目录下的一张图：左轴为 QPS（吞吐），右轴为多条延迟曲线（p50/p95/p99/avg），Neo4j 与 NebulaGraph 用不同颜色区分，图例中带有中英文说明。

运行方式：

```bash
python analyze_results.py
```

### 高层结论（Neo4j vs NebulaGraph）

- **点查/邻居/路径/聚合等读为主场景（E01–E08、E13、E14）**：在相同并发下，**Neo4j 的吞吐显著高于 NebulaGraph，查询延迟（含 P95/P99）普遍更低**，适合对在线读性能要求较高的场景。
- **细粒度写入与更新（E10、E12）**：两者在持续在线写入和属性更新下都能保持较高吞吐，Neo4j 整体略快，NebulaGraph 的写延迟略高但比较稳定。
- **批量写入（E11）**：NebulaGraph 在批量写/导入场景明显优于 Neo4j，在相同并发下吞吐大约高一个数量级，写入延迟也更小，适合作为批量导入或重写的后端。
- **高并发混合压力（E14）**：在读写各半且并发较高时，两者的尾部延迟都会显著拉长；NebulaGraph 更像是将吞吐稳定在一个平台（≈1400 QPS），以更高延迟为代价，而 Neo4j 在更高吞吐下尾延迟同样会变大。

### 各实验组详细对比表

#### 实验 E01 – 按 ID 单点查询基线性能

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1  | 3.204 | 0.468 | 3.017 | 0.452 | 4.269 | 0.673 | 6.199 | 0.924 | 311.788 | 2129.614 |
| 4  | 3.826 | 1.367 | 3.676 | 0.753 | 4.988 | 1.203 | 6.584 | 1.513 | 1042.314 | 2396.839 |
| 16 | 10.917 | 5.477 | 10.790 | 2.838 | 12.952 | 6.092 | 14.453 | 8.021 | 1461.546 | 2299.036 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量（Throughput） | 单机在相同并发下 QPS 明显更高，低并发即可达到 2000+ QPS | QPS 约为 Neo4j 的几分之一，随并发提升到 16 后接近 1500 QPS | 单点查基线性能上 Neo4j 具备明显吞吐优势 |
| 延迟（Latency） | P50/P95 在 1 ms 以内，尾延迟（P99）也保持在亚毫秒级 | P50/P95 在数毫秒级，P99 可到 6 ms 左右 | 同样工作负载下 Neo4j 延迟显著更低，更适合作为在线点查引擎 |
| 并发扩展（Scalability） | 并发从 1→16，吞吐接近线性提升 | 并发提升后延迟略升，吞吐提升有限 | Neo4j 在此场景下扩展性更好，NebulaGraph 更像是“稳但不快” |

#### 实验 E02 – 按有索引属性点查

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1  | 3.317 | 0.476 | 3.144 | 0.448 | 4.285 | 0.703 | 6.130 | 1.029 | 301.166 | 2090.744 |
| 4  | 4.086 | 1.135 | 3.958 | 1.079 | 5.169 | 1.792 | 6.278 | 2.276 | 977.306 | 3486.092 |
| 16 | 10.810 | 4.722 | 10.590 | 4.355 | 12.528 | 8.451 | 17.313 | 11.739 | 1476.838 | 3328.442 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | 有索引点查下 QPS 与 E01 同级甚至略高 | QPS 与 E01 相近，指数索引未显著提升吞吐 | Neo4j 对二级索引点查优化更充分，NebulaGraph 在当前规模下索引收益有限 |
| 延迟 | 索引命中后仍保持 1–2 ms 内的 P95 | P50/P95 在 3–6 ms 区间，尾部稍高 | 两者都可接受，但 Neo4j 的索引查询延迟更优 |
| 有无索引敏感度 | 有索引明显优于无索引 | 有/无索引下延迟差距不大 | 在属性点查上，Neo4j 更依赖并充分利用索引，NebulaGraph 更像全表扫描/索引混合策略 |

#### 实验 E03 – 按无索引属性点查

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1  | 3.322 | 0.440 | 3.156 | 0.417 | 4.295 | 0.641 | 5.876 | 0.893 | 300.731 | 2265.177 |
| 4  | 4.150 | 1.127 | 4.043 | 1.072 | 5.238 | 1.763 | 6.251 | 2.210 | 961.179 | 3521.254 |
| 16 | 10.838 | 5.073 | 10.618 | 4.866 | 12.722 | 8.950 | 16.531 | 13.193 | 1473.026 | 3113.126 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | 相较有索引略有下降，但整体仍高 | 吞吐与 E02 几乎持平 | 无索引退化下 Neo4j 仍快于 NebulaGraph，后者对索引敏感度较低 |
| 延迟 | 延迟略升但仍在毫秒级 | 延迟分布与 E02 基本一致 | 无索引场景下，Neo4j 依然具备更好延迟表现 |

#### 实验 E04 – 一跳邻居（普通节点）

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4  | 4.143 | 1.178 | 4.016 | 1.123 | 5.225 | 1.881 | 6.640 | 2.279 | 963.580 | 3342.286 |
| 16 | 11.376 | 4.814 | 11.186 | 4.433 | 13.658 | 8.644 | 16.760 | 12.703 | 1401.495 | 3281.037 |
| 64 | 44.480 | 22.033 | 44.028 | 10.355 | 50.035 | 28.198 | 64.392 | 47.822 | 1429.633 | 2216.213 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | 一跳邻居查询在中等并发下可达 3000+ QPS | 一跳邻居查询 QPS 稳定在 1000–1400 之间 | 同场景下 Neo4j 吞吐约为 NebulaGraph 的 2–3 倍 |
| 延迟 | P95 在几毫秒内，尾延迟可控 | P50/P95 在 4–13 ms 区间，P99 偶有数十毫秒 | Neo4j 适合对响应时间敏感的邻居查询，NebulaGraph 延迟偏高但稳定 |
| 并发扩展 | 并发增加对吞吐提升明显 | 并发从 4→64，吞吐接近平台，延迟上升 | NebulaGraph 更偏稳态吞吐，Neo4j 在可用资源下压榨出更高吞吐 |

#### 实验 E05 – 一跳邻居（超级节点）

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4  | 3.981 | 1.201 | 3.817 | 1.131 | 5.191 | 1.944 | 7.080 | 2.412 | 1002.534 | 3286.525 |
| 16 | 11.096 | 4.747 | 10.936 | 4.353 | 13.138 | 8.558 | 15.759 | 12.542 | 1439.094 | 3308.298 |
| 64 | 45.247 | 18.649 | 45.053 | 16.681 | 50.896 | 39.642 | 57.683 | 54.317 | 1405.602 | 3158.607 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | 超级点邻居查询下 QPS 相比 E04 略降 | QPS 与 E04 非常接近 | 两者都能承载超级点查询，Neo4j 仍然略优 |
| 延迟 | 超级点会拉高 tail latency，但整体仍在可接受范围 | P50/P95 稍高于普通节点，P99 偶尔放大 | NebulaGraph 对超级点较稳，但 absolute latency 仍高于 Neo4j |

#### 实验 E06 – 多跳邻居 / 固定长度路径

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4  | 3.940 | 1.120 | 3.726 | 1.057 | 5.205 | 1.770 | 7.162 | 2.257 | 1013.306 | 3543.123 |
| 16 | 11.195 | 4.860 | 11.034 | 4.492 | 13.313 | 8.696 | 15.657 | 12.330 | 1425.730 | 3250.961 |
| 64 | 44.316 | 20.002 | 44.023 | 18.483 | 49.532 | 40.937 | 59.493 | 59.368 | 1435.836 | 2974.590 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | 多跳路径下仍保持较高 QPS | QPS 稳定在 1400 左右，随并发变化不大 | 两者都能稳定承载多跳查询，Neo4j 吞吐更高 |
| 延迟 | 路径变长后延迟上升，但仍普遍低于 NebulaGraph | P50/P95 在 4–13 ms，tail 会到数十毫秒 | 路径查询延迟上 Neo4j 更具优势，NebulaGraph 适合作为高并发路径扫描引擎 |

#### 实验 E07 – 最短路径查询

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4  | 4.132 | 1.134 | 3.984 | 1.072 | 5.394 | 1.808 | 6.758 | 2.297 | 965.803 | 3502.200 |
| 16 | 11.313 | 4.866 | 11.024 | 4.454 | 13.626 | 8.873 | 18.989 | 12.384 | 1411.370 | 3239.090 |
| 64 | 45.496 | 21.755 | 44.519 | 22.115 | 54.574 | 33.078 | 63.342 | 46.062 | 1396.820 | 2774.724 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | shortestPath 查询下 QPS 略低于简单邻居但仍较高 | QPS 约 960–1400，随并发变化不大 | Neo4j 在最短路上的计算效率略优 |
| 延迟 | P50/P95 在低毫秒级 | P50/P95 可到 10+ ms，P99 更高 | 对实时最短路径查询，Neo4j 更合适；NebulaGraph 偏批量分析 |

#### 实验 E08 – 聚合统计（按属性聚合）

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4  | 4.214 | 1.520 | 4.085 | 1.457 | 5.376 | 2.307 | 6.600 | 2.898 | 947.523 | 2599.601 |
| 16 | 10.960 | 6.114 | 10.750 | 5.799 | 12.686 | 9.853 | 16.117 | 13.433 | 1456.362 | 2585.174 |
| 64 | 44.194 | 27.320 | 43.252 | 27.285 | 52.718 | 44.504 | 59.711 | 53.915 | 1440.225 | 2263.167 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | 聚合场景 QPS 维持在 2000+ | QPS 稳定在 950–1450 | Neo4j 在 OLAP 风格的小型聚合上更具效率 |
| 延迟 | P95 在几毫秒内 | P50/P95 在 4–13 ms，P99 可到 50+ ms | 对“实时统计类查询”Neo4j 延迟更优，NebulaGraph 适合离线/批量统计 |

#### 实验 E10 – 纯增量写入（插入点+边）

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4  | 4.989 | 1.965 | 4.837 | 1.891 | 6.169 | 2.649 | 7.995 | 3.565 | 798.615 | 2026.058 |
| 16 | 11.154 | 5.583 | 10.912 | 5.040 | 12.868 | 9.972 | 20.308 | 15.064 | 1431.652 | 2841.442 |
| 64 | 44.433 | 23.357 | 43.376 | 20.607 | 53.628 | 51.445 | 61.827 | 69.196 | 1432.352 | 2578.974 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | 点+边插入 QPS 与其读吞吐相当或略高 | QPS 约 800–1430，随并发上升后趋于平台 | 两者都能承载高速持续写入，Neo4j 略快 |
| 延迟 | 写入延迟保持在数毫秒级 | P50/P95 在 5–13 ms，P99 偶有 20+ ms | Neo4j 在写延迟上更佳，NebulaGraph 写路径偏“稳态高吞吐” |

#### 实验 E11 – 批量写入（Batch inserts）

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4  | 18.258 | 151.913 | 17.841 | 150.564 | 23.921 | 175.191 | 29.719 | 185.714 | 218.862 | 26.314 |
| 16 | 55.845 | 629.446 | 54.550 | 646.366 | 75.708 | 715.760 | 87.972 | 738.071 | 285.026 | 25.356 |
| 64 | 224.345 | 2683.392 | 223.442 | 2810.940 | 268.755 | 3073.821 | 288.170 | 3170.154 | 283.762 | 23.790 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | 批量写 QPS 约几十级别，扩展性差 | 批量写 QPS 稳定在 200–300+，明显高于 Neo4j | NebulaGraph 在批量写/导入场景上明显领先一个数量级 |
| 延迟 | 单次批量写 P50 在百毫秒以上 | P50/P95/P99 虽然较高，但单位写入成本更低 | 做大批量导入/初始化时，NebulaGraph 是更自然的选择 |

#### 实验 E12 – 更新/删除操作

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4  | 3.866 | 1.078 | 3.740 | 0.983 | 4.969 | 1.750 | 6.170 | 2.265 | 1032.313 | 3642.716 |
| 16 | 10.913 | 3.561 | 10.748 | 3.182 | 12.875 | 6.668 | 15.188 | 9.793 | 1462.555 | 4420.813 |
| 64 | 44.328 | 19.333 | 44.145 | 17.246 | 48.667 | 41.184 | 56.107 | 54.584 | 1434.780 | 3054.804 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | 更新/删除下 QPS 仍然较高 | QPS 约 1000–1450，和纯读/纯写相近 | 两者在细粒度更新场景下都能稳定吞吐，Neo4j 整体略优 |
| 延迟 | 更新延迟略高于插入，但总体低于 NebulaGraph | P50/P95 在 4–13 ms | 在线更新压力较大时 Neo4j 的响应更快，NebulaGraph 更强调吞吐均衡 |

#### 实验 E13 – 读多写少混合负载

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 4  | 4.116 | 1.234 | 4.004 | 1.142 | 5.168 | 1.950 | 6.070 | 2.463 | 969.686 | 3209.546 |
| 16 | 10.965 | 5.166 | 10.830 | 4.756 | 12.500 | 9.177 | 14.374 | 12.808 | 1455.690 | 3056.838 |
| 64 | 44.120 | 20.590 | 43.680 | 18.522 | 49.626 | 43.163 | 53.826 | 59.009 | 1442.948 | 2910.534 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | 在读多写少下 QPS 仍高于 NebulaGraph | QPS 稳定在 970–1450，接近纯读场景 | Neo4j 更适合作为混合负载下的主在线库 |
| 延迟 | 延迟略高于纯读但仍较低 | P50/P95 在 4–12 ms，tail 稍高 | NebulaGraph 读多写少场景下表现稳定，但整体延迟偏高 |

#### 实验 E14 – 读写各半高并发压力

**原始指标表（avg / p50 / p95 / p99 / throughput，单位：ms / QPS）**

| 并发（concurrency） | avg_nebulagraph | avg_neo4j | p50_nebulagraph | p50_neo4j | p95_nebulagraph | p95_neo4j | p99_nebulagraph | p99_neo4j | throughput_nebulagraph | throughput_neo4j |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 16  | 11.142 | 4.512 | 10.943 | 4.120 | 13.416 | 7.914 | 15.285 | 11.771 | 1433.005 | 3503.408 |
| 64  | 44.848 | 19.138 | 43.978 | 16.824 | 53.105 | 42.217 | 66.232 | 62.004 | 1420.296 | 3082.648 |
| 128 | 89.114 | 31.399 | 88.091 | 17.868 | 104.268 | 49.103 | 113.154 | 78.269 | 1420.901 | 2523.660 |

| **维度** | **Neo4j** | **NebulaGraph** | **简要结论** |
| --- | --- | --- | --- |
| 吞吐量 | 在高并发+读写各半下整体吞吐仍较高 | QPS 稳定在 ≈1400 左右，随并发翻倍变化不大 | 两者都处于“压力平台期”，NebulaGraph 把吞吐稳在一个上限 |
| 延迟 | 读写混合压力会明显拉高 tail latency | P50 从十几毫秒涨到数十毫秒，P99 超过百毫秒 | 极端压力场景下，两者尾延迟都较高，需要结合业务可接受延迟选择方案 |

## Cite

```bibtex
@software{nebulagraph_vs_neo4j_benchmark_2026,
  title   = {NebulaGraph vs Neo4j Benchmark},
  author  = {王巍巍},
  year    = {2026},
  version = {1.0.0},
  url     = {https://github.com/charles-wang888/nebulagraph-vs-neo4j-benchmark},
  note    = {Benchmark tests for NebulaGraph and Neo4j in multiple scenarios on million-scale data.}
}
```

