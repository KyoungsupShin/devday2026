#!/bin/sh
set -eu

# Print the running local LiteLLM Proxy master key for Codex's custom-provider
# auth command. The key is never written to disk by this script.
for container in genaihub-litellm-test-litellm-1 litellm-proxy; do
  token=$(docker inspect "$container" --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null \
    | awk -F= '$1 == "LITELLM_MASTER_KEY" {print substr($0, index($0, "=") + 1); exit}')
  if [ -n "$token" ]; then
    printf '%s\n' "$token"
    exit 0
  fi
done

echo "No running LiteLLM Proxy with LITELLM_MASTER_KEY was found." >&2
exit 1
