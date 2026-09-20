# Commander Blitz: one image, one origin -- the API and the built client together.
#
# The client talks to same-origin `/api` and `/art` (frontend/src/api/client.ts),
# so splitting them across two hosts would mean inventing a base-URL setting and
# widening CORS. Serving both from `get_app()` avoids all of it.

# --- client ------------------------------------------------------------------
FROM node:22-alpine AS client

WORKDIR /build
# Lockfile first: this layer survives every change that is not a dependency bump.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# `build` is `tsc --noEmit && vite build`, so a type error fails the image build.
RUN npm run build


# --- server ------------------------------------------------------------------
FROM python:3.13-slim AS server

# PYTHONUNBUFFERED so `docker compose logs` shows a traceback as it happens
# rather than whenever the buffer flushes.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies before the source, keyed only on pyproject.toml, so editing a
# card or a rule does not re-download numpy. Read out of pyproject rather than
# duplicated into a requirements.txt: one source of truth for the dep list.
# Written to a file instead of inlined because the specifiers contain `>`, which
# a shell would read as a redirect.
COPY pyproject.toml README.md ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt

# `--no-deps`: everything is already installed above, and this keeps the layer
# cheap. No `[dev]` and no `[train]` -- torch is ~800MB and nothing serving a
# game imports it.
COPY src/ ./src/
RUN pip install --no-cache-dir --no-deps .

# The card pool, the art cache and the catalog index. `.dockerignore` keeps the
# 74MB Scryfall bulk dump out; `data/catalog/cards.sqlite` and `data/art` are
# both read at runtime and have to be here.
COPY data/ ./data/
COPY --from=client /build/dist ./frontend/dist

# Both default to a walk up from __file__ that only resolves in a checkout
# (registry.py CLIENT_DIR/DEFAULT_DATA_DIR use `parents[3]`). Installed into
# site-packages that walk lands nowhere, so both must be explicit here.
ENV AUTOMTG_DATA_DIR=/app/data \
    AUTOMTG_CLIENT_DIR=/app/frontend/dist

# Runtime writes, all of them, and all under one mount point: cards and decks
# from an import, and the art the store lazily fetches. Created before the chown
# so the volume mount point inherits app ownership -- a named volume seeds its
# contents *and* its permissions from the image.
#
# `/app/data/art` is deliberately left root-owned and outside the volume. It is
# the committed art, it ships with this image, and a process that cannot write
# it cannot let a stale copy outlive the illustration it replaced -- which is
# exactly what a volume mounted over it used to do.
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /app/data/generated/art \
    && chown -R app:app /app/data/generated
USER app

EXPOSE 8000

# urllib rather than curl, so the image does not carry a network tool it would
# otherwise never use.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()"

# `--workers 1` is not a default, it is a constraint: sessions.py keeps games in
# process memory, so a second worker would serve half the requests from a
# process that has never heard of the game being played.
CMD ["uvicorn", "automtg.server.app:get_app", "--factory", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
