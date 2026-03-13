# Neo4j 查询语句集合

## 查看所有节点和边

### 1. 查看所有节点
```cypher
// 查看所有节点
MATCH (n) RETURN n LIMIT 100;

// 查看所有节点（只返回节点标签和属性）
MATCH (n) RETURN labels(n) as labels, properties(n) as properties LIMIT 100;

// 按节点类型分组查看
MATCH (n) RETURN labels(n) as node_type, count(n) as count ORDER BY count DESC;
```

### 2. 查看所有边（关系）
```cypher
// 查看所有边
MATCH ()-[r]->() RETURN r LIMIT 100;

// 查看所有边（只返回关系类型和属性）
MATCH ()-[r]->() RETURN type(r) as relationship_type, properties(r) as properties LIMIT 100;

// 按关系类型分组查看
MATCH ()-[r]->() RETURN type(r) as relationship_type, count(r) as count ORDER BY count DESC;
```

### 3. 查看节点和边的基本统计
```cypher
// 统计节点数量
MATCH (n) RETURN count(n) as total_nodes;

// 统计边数量
MATCH ()-[r]->() RETURN count(r) as total_relationships;

// 查看所有节点标签
MATCH (n) RETURN DISTINCT labels(n) as node_labels;

// 查看所有关系类型
MATCH ()-[r]->() RETURN DISTINCT type(r) as relationship_types;
```

### 4. 查看完整的图结构
```cypher
// 查看所有节点和它们的关系（限制数量避免过多数据）
MATCH (n)-[r]->(m) RETURN n, r, m LIMIT 50;

// 查看特定类型的节点和关系
MATCH (n:Person)-[r]->(m) RETURN n, r, m LIMIT 20;
```

### 5. 查看节点的详细信息
```cypher
// 查看所有Person节点的详细信息
MATCH (n:Person) RETURN n.name, n.position, n.company, n.department, n.experience, n.skills;

// 查看所有节点的属性
MATCH (n) RETURN n.name, properties(n) as all_properties LIMIT 20;
```

### 6. 查看关系的详细信息
```cypher
// 查看所有关系的详细信息
MATCH ()-[r]->() RETURN type(r), properties(r) as relationship_properties LIMIT 20;

// 查看特定类型的关系
MATCH ()-[r:WORKS_FOR]->() RETURN r LIMIT 10;
```

### 7. 查看图的拓扑结构
```cypher
// 查看节点的度（连接数）
MATCH (n) RETURN n.name, size((n)--()) as degree ORDER BY degree DESC LIMIT 10;

// 查看最连接的节点
MATCH (n) WITH n, size((n)--()) as degree WHERE degree > 0 RETURN n.name, degree ORDER BY degree DESC LIMIT 10;
```

### 8. 查看特定模式的查询
```cypher
// 查看员工和公司的关系
MATCH (p:Person)-[r:WORKS_FOR]->(c:Company) RETURN p.name, r, c.name;

// 查看技能关系
MATCH (p:Person)-[r:HAS_SKILL]->(s:Skill) RETURN p.name, r, s.name;

// 查看项目关系
MATCH (p:Person)-[r:WORKS_ON]->(pr:Project) RETURN p.name, r, pr.name;
```

### 9. 清理和重置数据库
```cypher
// 删除所有节点和关系（谨慎使用！）
MATCH (n) DETACH DELETE n;

// 删除特定类型的节点
MATCH (n:Person) DETACH DELETE n;

// 删除特定类型的关系
MATCH ()-[r:WORKS_FOR]->() DELETE r;
```

### 10. 性能优化查询
```cypher
// 查看数据库统计信息
CALL db.stats();

// 查看索引信息
SHOW INDEXES;

// 查看约束信息
SHOW CONSTRAINTS;
```

## 在Python中使用这些查询

如果您想在Python代码中使用这些查询，可以这样做：

```python
from neo4j import GraphDatabase

class Neo4jQueryHelper:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
    
    def close(self):
        self.driver.close()
    
    def get_all_nodes(self):
        with self.driver.session() as session:
            result = session.run("MATCH (n) RETURN n LIMIT 100")
            return [record["n"] for record in result]
    
    def get_all_relationships(self):
        with self.driver.session() as session:
            result = session.run("MATCH ()-[r]->() RETURN r LIMIT 100")
            return [record["r"] for record in result]
    
    def get_node_count(self):
        with self.driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) as count")
            return result.single()["count"]
    
    def get_relationship_count(self):
        with self.driver.session() as session:
            result = session.run("MATCH ()-[r]->() RETURN count(r) as count")
            return result.single()["count"]
    
    def get_node_labels(self):
        with self.driver.session() as session:
            result = session.run("MATCH (n) RETURN DISTINCT labels(n) as labels")
            return [record["labels"] for record in result]
    
    def get_relationship_types(self):
        with self.driver.session() as session:
            result = session.run("MATCH ()-[r]->() RETURN DISTINCT type(r) as types")
            return [record["types"] for record in result]

# 使用示例
if __name__ == "__main__":
    helper = Neo4jQueryHelper("bolt://localhost:7687", "neo4j", "password")
    
    print(f"节点数量: {helper.get_node_count()}")
    print(f"关系数量: {helper.get_relationship_count()}")
    print(f"节点标签: {helper.get_node_labels()}")
    print(f"关系类型: {helper.get_relationship_types()}")
    
    helper.close()
```

## 注意事项

1. **LIMIT子句**: 在生产环境中，始终使用LIMIT来限制返回的结果数量，避免查询过多数据导致性能问题。

2. **索引**: 对于大型图数据库，确保在经常查询的属性上创建索引。

3. **权限**: 确保数据库用户有足够的权限执行这些查询。

4. **备份**: 在执行删除操作前，确保有数据库备份。

5. **性能**: 对于大型图，某些查询可能需要较长时间，请耐心等待。 