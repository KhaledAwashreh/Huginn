#!/bin/sh
set -eu

resolver="${HUGINN_ACME_ENVIRONMENT:-production}"
case "$resolver" in
  production) authority=https://acme-v02.api.letsencrypt.org/directory ;;
  staging) authority=https://acme-staging-v02.api.letsencrypt.org/directory ;;
  *) echo 'HUGINN_ACME_ENVIRONMENT must be production or staging' >&2; exit 1 ;;
esac

# Only the selected resolver may load certificates into Traefik's shared TLS store.
exec traefik "$@" \
  "--certificatesresolvers.$resolver.acme.email=${HUGINN_ACME_EMAIL:?HUGINN_ACME_EMAIL is required}" \
  "--certificatesresolvers.$resolver.acme.storage=/certificates/$resolver/acme.json" \
  "--certificatesresolvers.$resolver.acme.caserver=$authority" \
  "--certificatesresolvers.$resolver.acme.httpchallenge.entrypoint=web"
