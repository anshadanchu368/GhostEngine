#!/bin/bash
set -e

REPO_URL=${GITHUB_REPO_URL:-"https://github.com/anshadanchu368/GhostEngine"}
BRANCH=${GITHUB_BRANCH:-"main"}

echo "Pulling latest code from $REPO_URL ($BRANCH)..."

if [ -d "/app/repo/.git" ]; then
    cd /app/repo && git pull origin "$BRANCH" && cp -r python/app/. /app/app/
else
    cd /app && git clone --branch "$BRANCH" "$REPO_URL" repo && cp -r repo/python/app ./app
fi

# Install TripoSR module (not pip-installable; clone and copy tsr/ package)
if [ ! -d "/app/tsr" ]; then
    echo "Cloning TripoSR..."
    git clone --depth 1 https://github.com/VAST-AI-Research/TripoSR.git /tmp/triposr
    cp -r /tmp/triposr/tsr /app/tsr
    rm -rf /tmp/triposr
fi

if [ -n "$HF_TOKEN" ]; then
    echo "Logging into Hugging Face..."
    python3 -c "from huggingface_hub import login; login(token='$HF_TOKEN')"
fi

echo "Starting uvicorn..."
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
