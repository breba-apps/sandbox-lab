FROM docker.io/cloudflare/sandbox:0.12.3-python

# bubblewrap: codex's preferred sandbox backend (avoids the bundled-fallback warning).
RUN apt-get update \
  && apt-get install -y --no-install-recommends bubblewrap \
  && rm -rf /var/lib/apt/lists/*

# Install agent CLIs globally.
RUN npm install -g @openai/codex @anthropic-ai/claude-code

ENV COMMAND_TIMEOUT_MS=3600000

# Local attach runs agent commands as this non-root user.
RUN useradd -m -s /bin/bash appuser \
  && chown -R appuser:appuser /workspace

# Expose the WebSocket port used by codex app-server
EXPOSE 4500
