#!/usr/bin/env bash
# Publish missing release assets while refusing to overwrite anything on a rerun.
set -euo pipefail

tag=${RELEASE_TAG:?RELEASE_TAG is required}
if [[ ! "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Expected RELEASE_TAG in vMAJOR.MINOR.PATCH form." >&2
  exit 1
fi
version=${tag#v}
expected_commit=$(git rev-parse "refs/tags/${tag}^{commit}")
current_commit=$(git rev-parse HEAD)
if [[ "$expected_commit" != "$current_commit" ]]; then
  echo "Tag ${tag} does not point to the tested checkout." >&2
  exit 1
fi

assets=("dist/bible-search-${version}.tar.gz" dist/install.sh dist/SHA256SUMS)
if gh release view "$tag" >/dev/null 2>&1; then
  release_tmp=$(mktemp -d -t bible-search-release.XXXXXXXX)
  trap 'rm -rf -- "$release_tmp"' EXIT
  for asset in "${assets[@]}"; do
    name=${asset##*/}
    if gh release view "$tag" --json assets --jq '.assets[].name' | grep -Fxq "$name"; then
      asset_tmp="$release_tmp/$name"
      mkdir -p "$asset_tmp"
      gh release download "$tag" --pattern "$name" --dir "$asset_tmp"
      if ! cmp --silent "$asset" "$asset_tmp/$name"; then
        echo "Existing ${tag} asset differs: ${name}; refusing to overwrite it." >&2
        exit 1
      fi
      echo "Existing release asset verified: $name"
    else
      gh release upload "$tag" "$asset"
      echo "Uploaded missing release asset: $name"
    fi
  done
  echo "Existing release preserved: $tag"
else
  gh release create "$tag" "${assets[@]}" --verify-tag \
    --title "Bible Search $tag" --notes-file dist/release-notes.md
fi
