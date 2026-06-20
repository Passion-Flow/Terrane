-- PoC R16: 自研双时态时序层（修正版）
LOAD 'age'; SET search_path = ag_catalog, "$user", public;
SELECT create_graph('mem_poc');

SELECT * FROM cypher('mem_poc', $$
  MERGE (u:Fact {fact_id:'pref-coffee', statement:'咖啡加糖'})
  MERGE (e:Episode {episode_id:'ep1'})
  MERGE (e)-[:ASSERTS {t_valid:1000, t_invalid:-1}]->(u)
$$) AS (x agtype);

-- 矛盾消解：旧边失效（不删）+ 新事实生效
SELECT * FROM cypher('mem_poc', $$
  MATCH (:Episode {episode_id:'ep1'})-[r:ASSERTS]->(:Fact {fact_id:'pref-coffee'})
  SET r.t_invalid = 2000
$$) AS (x agtype);
SELECT * FROM cypher('mem_poc', $$
  MERGE (u2:Fact {fact_id:'pref-coffee-v2', statement:'咖啡不加糖'})
  MERGE (e2:Episode {episode_id:'ep2'})
  MERGE (e2)-[:ASSERTS {t_valid:2000, t_invalid:-1}]->(u2)
$$) AS (x agtype);

-- as-of 查询（断言 T=1500→加糖 / T=2500→不加糖）
SELECT 'ASOF_1500' AS marker, st::text AS stmt FROM cypher('mem_poc', $$
  MATCH ()-[r:ASSERTS]->(u:Fact)
  WHERE r.t_valid <= 1500 AND (r.t_invalid = -1 OR r.t_invalid > 1500)
  RETURN u.statement $$) AS (st agtype);
SELECT 'ASOF_2500' AS marker, st::text AS stmt FROM cypher('mem_poc', $$
  MATCH ()-[r:ASSERTS]->(u:Fact)
  WHERE r.t_valid <= 2500 AND (r.t_invalid = -1 OR r.t_invalid > 2500)
  RETURN u.statement $$) AS (st agtype);

-- 历史可回溯（2 条 ASSERTS 边都在）
SELECT 'HISTORY' AS marker, count(*) AS edges FROM cypher('mem_poc', $$
  MATCH ()-[r:ASSERTS]->() RETURN r $$) AS (r agtype);

-- 用户硬删除（DETACH DELETE）
SELECT * FROM cypher('mem_poc', $$
  MATCH (u:Fact {fact_id:'pref-coffee'}) DETACH DELETE u $$) AS (x agtype);
SELECT 'AFTER_HARD_DELETE' AS marker, count(*) AS facts FROM cypher('mem_poc', $$
  MATCH (u:Fact) RETURN u $$) AS (u agtype);
