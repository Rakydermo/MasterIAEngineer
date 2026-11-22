# Proposal

## Why

El proyecto `estimador-cag` ya tiene código, pero su entorno no es reproducible: `pyproject.toml` no coincide con `uv.lock` (que resuelve un proyecto ajeno llamado `mi-proyecto`), `.venv` no tiene `structlog` y `.env` no cumple el contrato de `config.py`. Por eso el comando del enunciado, `uv run uvicorn app.main:app --reload`, no arranca. Reconciliar estas piezas es lo que permite que el servicio sea ejecutable y verificable.

## What Changes

- Regenerar `uv.lock` y sincronizar `.venv` desde el `pyproject.toml` vigente, incluyendo `structlog` y el grupo `dev`.
- Alinear `.env` y `.env.example` con `Settings`: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`, `APP_ENV`, `LOG_LEVEL`; tolerar claves ajenas en el fichero.
- **BREAKING** (entorno local): `API_KEY` y `MODEL_NAME` dejan de ser válidas; hay que migrarlas a `ANTHROPIC_API_KEY` y `LLM_MODEL`.
- Convertir el endpoint de estimación a `def` para no bloquear el event loop con los SDKs síncronos.
- Corregir CORS (wildcard con credenciales), aplicar `LOG_LEVEL` y arreglar el encoding de los ejemplos del prompt.
- Renombrar el proyecto en `pyproject.toml` a `estimador-cag` para que coincida con la carpeta.
- Añadir tests de humo sin red para `/health` y `/api/v1/estimate`.
- Actualizar `README.md` y `AGENTS.md` para que dejen de describir un estado inexistente.

## Capabilities

### New Capabilities

- `estimations`: API HTTP que recibe transcripciones de reuniones y devuelve estimaciones de software generadas por un LLM, con health check, selección de proveedor y sin persistencia ni retrieval (CAG).

### Modified Capabilities

- Ninguna: no existen specs previas en `openspec/specs/`.

## Impact

- Código: `app/config.py`, `app/main.py`, `app/routers/estimations.py`, `app/context/examples.py`, `pyproject.toml`, `README.md`, `AGENTS.md`, `.env.example`.
- Entorno: `uv.lock`, `.venv`, `.env` local.
- API: `GET /health` y `POST /api/v1/estimate`.
- Sin infraestructura nueva: no hay base de datos, caché ni retrieval; la única dependencia externa es el proveedor LLM.
