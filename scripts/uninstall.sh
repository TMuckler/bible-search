#!/usr/bin/env bash
set -euo pipefail
exec /usr/bin/python "$(dirname -- "$(readlink -f -- "$0")")/manage.py" uninstall "$@"
