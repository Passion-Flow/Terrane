-- PoC D2: AGE cypher + pgvector 同库同事务混合查询（修正版：properties() 移入 cypher RETURN）
CREATE EXTENSION IF NOT EXISTS age CASCADE;
CREATE EXTENSION IF NOT EXISTS vector;
LOAD 'age'; SET search_path = ag_catalog, "$user", public;

SELECT create_graph('kb_poc');
SELECT * FROM cypher('kb_poc', $$
  MERGE (a:Entity {entity_id:'llm-wiki', name:'LLM Wiki', etype:'concept', summary:'LLM 增量编译知识为持久 wiki'})
  MERGE (b:Entity {entity_id:'karpathy', name:'Karpathy', etype:'person', summary:'方法论提出者'})
  MERGE (c:Entity {entity_id:'terrane', name:'Terrane', etype:'product', summary:'私有化知识库产品'})
  MERGE (a)-[:REL {rtype:'proposed_by', confidence:0.9, human_verified:false}]->(b)
  MERGE (c)-[:REL {rtype:'implements', confidence:0.95, human_verified:false}]->(a)
$$) AS (x agtype);

CREATE TABLE poc_chunks (id int PRIMARY KEY, kb text, content text, embedding halfvec(4));
INSERT INTO poc_chunks VALUES
 (1,'kb_poc','karpathy 提出 llm-wiki 方法论','[0.9,0.1,0.0,0.1]'),
 (2,'kb_poc','terrane 是私有化部署产品','[0.1,0.9,0.1,0.0]'),
 (3,'kb_poc','无关内容','[0.0,0.0,1.0,0.9]');

BEGIN;
WITH graph_hits AS (
  SELECT (nm::text) AS name
  FROM cypher('kb_poc', $$
    MATCH (e:Entity {entity_id:'llm-wiki'})-[r:REL]-(n:Entity) RETURN n.name
  $$) AS (nm agtype)
), vec_hits AS (
  SELECT id, content, embedding <=> '[0.85,0.15,0.05,0.1]'::halfvec AS dist
  FROM poc_chunks WHERE kb='kb_poc' ORDER BY dist LIMIT 2
)
SELECT 'HYBRID_OK' AS marker, (SELECT count(*) FROM graph_hits) AS graph_n,
       (SELECT count(*) FROM vec_hits) AS vec_n,
       (SELECT string_agg(name,',' ORDER BY name) FROM graph_hits) AS neighbors;
COMMIT;
