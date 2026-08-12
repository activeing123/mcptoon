FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir .

# mcptoon is a CLI the agent shells out to; make the subcommand pass-through
# so `docker run mcptoon manifest --toon` works the same as `mcptoon manifest --toon`.
ENTRYPOINT ["mcptoon"]
CMD ["help"]
