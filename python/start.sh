#!/bin/bash
set -e

REPO_URL=${GITHUB_REPO_URL:-"https://github.com/anshadanchu368/GhostEngine"}
BRANCH=${GITHUB_BRANCH:-"main"}

echo "Pulling latest code from $REPO_URL ($BRANCH)..."

if [ -d "/app/app" ]; then
    cd /app && git pull origin "$BRANCH"
else
    cd /app && git clone --branch "$BRANCH" "$REPO_URL" repo && cp -r repo/python/app ./app
fi

echo "Starting uvicorn..."
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
