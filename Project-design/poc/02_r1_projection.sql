-- PoC R1: wiki 物化投影 + 人工编辑回写（静态 SQL 版，properties 取值全在 cypher 内）
LOAD 'age'; SET search_path = ag_catalog, "$user", public;

-- 投影 V1：实体+1跳 → Markdown（人工事实优先排序）
SELECT 'RENDER_V1' AS marker, string_agg(
  '- ' || trim(both '"' from rt::text) || ' → [[' || trim(both '"' from mn::text) || ']]' ||
  CASE WHEN hv::text='true' THEN ' ✓人工' ELSE '' END,
  E'\n' ORDER BY hv::text DESC, rt::text) AS facts
FROM cypher('kb_poc', $$
  MATCH (e:Entity {entity_id:'llm-wiki'})-[r:REL]-(m:Entity)
  RETURN r.rtype, m.name, r.human_verified
$$) AS (rt agtype, mn agtype, hv agtype);

-- 人工接管编辑：断言新事实（human_verified=true）回写图
SELECT * FROM cypher('kb_poc', $$
  MATCH (a:Entity {entity_id:'llm-wiki'})
  MERGE (d:Entity {entity_id:'memex', name:'Memex', etype:'concept', summary:'Vannevar Bush 1945'})
  MERGE (a)-[:REL {rtype:'inspired_by', confidence:1.0, human_verified:true}]->(d)
$$) AS (x agtype);

-- 投影 V2：断言——含 '✓人工' 且 human_verified DESC 排首位
SELECT 'RENDER_V2' AS marker, string_agg(
  '- ' || trim(both '"' from rt::text) || ' → [[' || trim(both '"' from mn::text) || ']]' ||
  CASE WHEN hv::text='true' THEN ' ✓人工' ELSE '' END,
  E'\n' ORDER BY hv::text DESC, rt::text) AS facts
FROM cypher('kb_poc', $$
  MATCH (e:Entity {entity_id:'llm-wiki'})-[r:REL]-(m:Entity)
  RETURN r.rtype, m.name, r.human_verified
$$) AS (rt agtype, mn agtype, hv agtype);
