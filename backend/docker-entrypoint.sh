#!/bin/sh
# With DATA_DIR set (a persistent disk), uploads and training/ live on the disk
# so documents, extractions and analyses survive restarts and redeploys. The
# image's training/ (models, catalog, datasets from git) seeds the disk; files
# already on the disk change only through `python -m services.asset_sync apply`. Without DATA_DIR the image copy is
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
  # Shipped assets (services/asset_sync.py): adds files the disk lacks, records
  # what is applied, reports newer versions waiting for an explicit `apply`,
  # and stops here when the disk's assets are newer than this image reads.
  (cd /app && as_app python -m services.asset_sync startup)
  ln -sfn "$DATA_DIR/training" /app/training
  ln -sfn "$DATA_DIR/uploads" /app/uploads
elif [ ! -e /app/training ]; then
  ln -s /app/training.image /app/training
fi

if [ "$(id -u)" = 0 ]; then
  exec setpriv --reuid=appuser --regid=appuser --init-groups "$@"
fi
exec "$@"
