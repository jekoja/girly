# Girly 🌸 — Python app image.
#
# The app is stdlib-only, so there is nothing to pip install. The service on
# Render is configured with rootDir: girly-app and dockerfilePath: Dockerfile,
# which makes this directory the build context.
FROM python:3.12-slim

WORKDIR /app

COPY . .

# server.py creates data/ itself; this just makes the intent explicit.
RUN mkdir -p /app/data

# server.py honors $PORT and binds 0.0.0.0 (see parse_addr), so Render's
# injected port is picked up at runtime. 8080 is the local default.
EXPOSE 8080

CMD ["python3", "server.py"]
