#!/usr/bin/env bash
# Install the exact release this script ships with.
set -euo pipefail

version='1.0.2'
archive="bible-search-${version}.tar.gz"
release_url="https://github.com/TMuckler/bible-search/releases/download/v${version}"

if [[ "${1:-}" == '--help' || "${1:-}" == '-h' ]]; then
  echo "Download, verify, and install Bible Search ${version}."
  echo 'Usage: bash install.sh [--bible /absolute/path/to/bible]'
  exit 0
fi
for dependency in curl sha256sum tar awk; do
  if ! command -v "$dependency" >/dev/null; then
    echo "Missing dependency: $dependency" >&2
    exit 1
  fi
done

release_tmp=$(mktemp -d -t bible-search-install.XXXXXXXX)
trap 'rm -rf -- "$release_tmp"' EXIT
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 3 \
  --output "$release_tmp/$archive" "$release_url/$archive"
curl --fail --silent --show-error --location --proto '=https' --tlsv1.2 --retry 3 \
  --output "$release_tmp/SHA256SUMS" "$release_url/SHA256SUMS"

expected_checksum=$(awk -v name="$archive" '$2 == name {print $1}' "$release_tmp/SHA256SUMS")
if [[ ! "$expected_checksum" =~ ^[a-f0-9]{64}$ ]]; then
  echo 'Release checksum is missing or invalid.' >&2
  exit 1
fi
if ! (cd "$release_tmp" && printf '%s  %s\n' "$expected_checksum" "$archive" | sha256sum --check --status); then
  echo 'Release checksum verification failed; installation stopped.' >&2
  exit 1
fi

tar --extract --gzip --file "$release_tmp/$archive" --directory "$release_tmp" --no-same-owner
bash "$release_tmp/bible-search-${version}/scripts/install.sh" "$@"
