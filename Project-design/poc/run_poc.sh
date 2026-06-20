#!/bin/zsh
set -e
docker rm -f terrane-pg-poc 2>/dev/null || true
docker run -d --name terrane-pg-poc -e POSTGRES_PASSWORD=poc -p 45433:5432 terrane-postgres:poc
echo "waiting for pg..."; for i in {1..30}; do docker exec terrane-pg-poc pg_isready -U postgres >/dev/null 2>&1 && break; sleep 1; done
for f in 01_d2_hybrid.sql 02_r1_projection.sql 03_r16_temporal.sql; do
  echo "===== $f ====="
  docker exec -i terrane-pg-poc psql -U postgres -v ON_ERROR_STOP=1 < $f
done
