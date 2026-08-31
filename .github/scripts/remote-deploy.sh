#!/usr/bin/env bash
set -Eeuo pipefail

deploy_root="${1:?deployment root is required}"
release_id="${2:?release id is required}"
archive_path="${3:?archive path is required}"

case "$deploy_root" in
  /*) ;;
  *) echo "Deployment root must be an absolute path" >&2; exit 1 ;;
esac

case "$release_id" in
  *[!0-9a-fA-F]*) echo "Release id must be a Git commit SHA" >&2; exit 1 ;;
esac

case "$archive_path" in
  /tmp/suanpan-*.tar.gz) ;;
  *) echo "Unexpected deployment archive path" >&2; exit 1 ;;
esac

release_dir="$deploy_root/releases/$release_id"
cleanup() {
  rm -f -- "$archive_path"
}
trap cleanup EXIT

mkdir -p -- "$release_dir"
tar -xzf "$archive_path" -C "$release_dir"
cd "$release_dir"

docker compose config --quiet
docker compose build --pull
docker compose up -d --remove-orphans --wait --wait-timeout 120

# Keep an easy-to-find pointer to the release currently running.
ln -sfn "$release_dir" "$deploy_root/current.new"
mv -Tf "$deploy_root/current.new" "$deploy_root/current"

curl --fail --silent --show-error http://127.0.0.1:8000/healthcheck
echo
docker compose ps
