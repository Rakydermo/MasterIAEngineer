# AGENTS.md

> Responde siempre en castellano.

## Estructura / git

- **Un único repositorio git en la raíz** `C:\Repo\MasterIAEngineer`. `estimador-cag/` es un subdirectorio del mismo repo, no un repo propio: no tiene `.git` ni `.gitignore` independientes. Ejecuta los comandos git desde la raíz.
- `estimador-cag/` es el único código: un servicio FastAPI. Punto de entrada `app/main.py`; rutas en `/api/v1`; health en `GET /health`.
- `openspec/` (raíz) es la fuente de planificación. Las skills/comandos `openspec-*` en `.agents/`, `.claude/`, `.gemini/`, `.github/`, `.opencode/`, `.vibe/` y `.zcode/` son copias generadas. Edita `openspec/` o regenera con `openspec update`; nunca parchees una sola copia.

## Entorno de Python

- Python 3.11 + `uv` (0.12.5). El entorno real es `estimador-cag/.venv`, gestionado por `pyproject.toml` (PEP 621) y `uv.lock` (raíz `estimador-cag`).
- `uv sync --group dev` instala todo; `uv run ...` ejecuta. El lock está sincronizado, así que `uv run` es seguro.
- Dependencias: fastapi 0.162.5, pydantic 2.14.3, uvicorn 0.54.0, **litellm 1.111.0** (fijada con `==`, no `>=`), openai 3.x, pydantic-settings, python-dotenv, structlog. El grupo `dev` añade pytest, pytest-asyncio, httpx y ruff.
- `litellm` es la capa de transporte hacia los proveedores: no añadas SDKs de proveedor ni clientes propios. Arrastra `boto3`, `tokenizers`, `huggingface-hub`, `tiktoken` y `aiohttp`; el tamaño del entorno no es el de un servicio ligero.
- Hay configuración de ruff en `pyproject.toml`, pero no CI ni pre-commit. El único workflow es `.github/workflows/copilot-setup-steps.yml` (instala el CLI de OpenSpec).

## Ejecutar y verificar

- Ejecuta desde `estimador-cag/`: `app/config.py` carga `.env` por ruta relativa.
- Arranque: `uv run uvicorn app.main:app --reload`.
- Tests: `uv run pytest` (mockean el LLM; no requieren red ni clave real).
- La app exige una API key no vacía para **cada proveedor** que aparezca en `LLM_MODEL` o `LLM_FALLBACK_MODEL`; `.env` debe tener `ANTHROPIC_API_KEY` y/o `OPENAI_API_KEY`. Los tests inyectan `ANTHROPIC_API_KEY=test` desde `tests/conftest.py`.
- En Windows, `Start-Process uv ...` falla por el trampoline de uv. Para arrancar en segundo plano usa `.venv\Scripts\python.exe -m uvicorn app.main:app`.

## Contrato de configuración

- `LLM_MODEL` (con prefijo de proveedor obligatorio, `anthropic/...` u `openai/...`), `LLM_FALLBACK_MODEL` (opcional, mismo formato), `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `APP_ENV`, `LOG_LEVEL`.
- Presupuesto del LLM: `LLM_CONNECT_TIMEOUT_S` (5), `LLM_READ_TIMEOUT_S` (120), `LLM_WRITE_TIMEOUT_S` (10), `LLM_POOL_TIMEOUT_S` (5), `LLM_MAX_RETRIES` (0), `LLM_MAX_CONCURRENCY` (8).
- **`LLM_PROVIDER` ya no existe**: el proveedor se deriva del prefijo del modelo. Un `.env` antiguo con `LLM_PROVIDER` y `LLM_MODEL` sin prefijo no arranca.
- `Settings` usa `extra="ignore"`: claves ajenas en `.env` no rompen el arranque.
- Un modelo sin prefijo soportado, la falta de la clave de un proveedor configurado o un valor no positivo en timeouts/concurrencia hacen fallar el arranque.

## Estado del código

- Implementado: `/health`, `POST /api/v1/estimate`, wrapper LLM sobre `litellm.Router` con fallback ordenado (`order` 1/2), semáforo fail-fast, taxonomía de errores, `X-Request-ID` y logs con coste.
- CAG puro: sin BD, retrieval ni persistencia; no añadas estado entre peticiones. **Tampoco cache de respuestas** (`cache_responses=False`): dos peticiones idénticas deben llamar dos veces al proveedor.
- El endpoint de estimación es `def` (threadpool) porque `Router.completion` es síncrono. No lo cambies a `async def` sin migrar a `acompletion` y revisar el semáforo.

## OpenSpec

- CLI v1.13.1. Valida con `openspec validate --all`.
- `estimador-cag` está archivado (2026-11-26) y su spec vive en `openspec/specs/estimations/`. El change activo es `abstraccion-llm`.
