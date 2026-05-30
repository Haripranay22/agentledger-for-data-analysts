#!/bin/bash
# Creates the separate langfuse database on first Postgres boot.
# Runs after init_db.sql (alphabetical order in docker-entrypoint-initdb.d).
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    CREATE DATABASE langfuse;
EOSQL
