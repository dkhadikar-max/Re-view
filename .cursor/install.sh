#!/usr/bin/env bash
set -euo pipefail

# Verify this is a valid git checkout (idempotent repository bootstrap).
git rev-parse --is-inside-work-tree >/dev/null

echo "Re-view development environment ready."
