#!/bin/sh
set -eu

if [ -z "${BASIC_AUTH_USERNAME:-}" ]; then
    echo "BASIC_AUTH_USERNAME is required." >&2
    exit 1
fi

if [ -z "${BASIC_AUTH_PASSWORD:-}" ]; then
    echo "BASIC_AUTH_PASSWORD is required." >&2
    exit 1
fi

export BASIC_AUTH_REALM="${BASIC_AUTH_REALM:-Predict Strike}"
export BACKEND_UPSTREAM="${BACKEND_UPSTREAM:-http://backend:8000}"

htpasswd -bc /etc/nginx/.htpasswd "$BASIC_AUTH_USERNAME" "$BASIC_AUTH_PASSWORD"
envsubst '${BASIC_AUTH_REALM} ${BACKEND_UPSTREAM}' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf

exec nginx -g 'daemon off;'
