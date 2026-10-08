#!/bin/sh
# With DATA_DIR set (a persistent disk), uploads and training/ live on the disk
# so documents, extractions and analyses survive restarts and redeploys. The
# image's training/ (models, catalog, datasets from git) seeds the disk; files
# already on the disk are never overwritten. Without DATA_DIR the image copy is
# used (docker-compose bind-mounts its own training/ instead).
set -e

# The app runs unprivileged; hosts start the container as root to mount disks.
as_app() {
  if [ "$(id -u)" = 0 ]; then
    setpriv --reuid=appuser --regid=appuser --init-groups "$@"
  else
    "$@"
  fi
}

if [ -n "$DATA_DIR" ]; then
  # A freshly mounted disk is root-owned: hand it over once, not on every start.
  if [ "$(id -u)" = 0 ] && [ "$(stat -c %U "$DATA_DIR")" != appuser ]; then
    chown -R appuser:appuser "$DATA_DIR"
  fi
  as_app mkdir -p "$DATA_DIR/uploads" "$DATA_DIR/training"
  as_app cp -Rn /app/training.image/. "$DATA_DIR/training/"
  # Which image seeded this disk: a later image adds new files only, so say so
  # when its models / catalog may differ from the ones already on the disk.
  seeded="$DATA_DIR/.seeded-from"
  [ -e "$seeded" ] || echo "${APP_SOURCE_REVISION:-unknown}" | as_app tee "$seeded" >/dev/null
  if [ "$(cat "$seeded")" != "${APP_SOURCE_REVISION:-unknown}" ]; then
    echo "entrypoint: data seeded from $(cat "$seeded"), image is ${APP_SOURCE_REVISION:-unknown};" \
      "changed files in /app/training.image are not applied (docs/DOCKER.md, Updating)." >&2
  fi
  ln -sfn "$DATA_DIR/training" /app/training
  ln -sfn "$DATA_DIR/uploads" /app/uploads
elif [ ! -e /app/training ]; then
  ln -s /app/training.image /app/training
fi

if [ "$(id -u)" = 0 ]; then
  exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
fi
exec "$@"
