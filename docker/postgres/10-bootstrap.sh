#!/bin/sh
# Only the official Postgres entrypoint runs this, on an empty data volume.
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 \
  -f /schema/00_extensions.sql \
  -f /schema/ops.sql \
  -f /schema/bronze.sql \
  -f /schema/kan-83-eu-startups-discovery.sql \
  -f /schema/silver.sql \
  -f /schema/gold.sql \
  -f /schema/operational.sql \
  -f /schema/operational-account-role.sql \
  -f /schema/ops-pipeline-control.sql \
  -f /schema/ops-matchmaking-control.sql \
  -f /schema/silver-source-currentness.sql \
  -f /schema/gold-current-source-evidence.sql \
  -f /schema/operational-recommendations.sql \
  -f /schema/operational-weekly-digest.sql
