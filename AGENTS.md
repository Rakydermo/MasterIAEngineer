# AGENTS.md

> Responde siempre en castellano.

## Estructura / git

- La raíz `C:\Repo\MasterIAEngineer` **no** es un repositorio git. `estimador-cag/` es su propio repositorio git (sin commits, sin remoto) con su propio `.gitignore` y `.venv`. Ejecuta los comandos git dentro de `estimador-cag/`.
- `estimador-cag/` es el único código: un servicio FastAPI. Punto de entrada `app/main.py`; rutas en `/api/v1`; health en `GET /health`.
- `openspec/` (raíz) es la fuente de planificación. Las skills/comandos `openspec-*` en `.agents/`, `.claude/`, `.gemini/`, `.github/`, `.opencode/`, `.vibe/` y `.zcode/` son copias generadas. Edita `openspec/` o regenera con `openspec update`; nunca parchees una sola copia.

## Entorno de Python

- Python 3.11 + `uv` (0.12.5). El entorno real es `estimador-cag/.venv`, gestionado por `pyproject.toml` (PEP 621) y `uv.lock` (raíz `estimador-cag`).
- `uv sync --group dev` instala todo; `uv run ...` ejecuta. El lock está sincronizado, así que `uv run` es seguro.
- Dependencias: fastapi 0.162.5, pydantic 2.14.3, uvicorn 0.54.0, anthropic, openai, structlog. El grupo `dev` añade pytest, pytest-asyncio, httpx y ruff.
- Hay configuración de ruff en `pyproject.toml`, pero no CI ni pre-commit. El único workflow es `.github/workflows/copilot-setup-steps.yml` (instala el CLI de OpenSpec).

## Ejecutar y verificar

- Ejecuta desde `estimador-cag/`: `app/config.py` carga `.env` por ruta relativa.
- Arranque: `uv run uvicorn app.main:app --reload`.
- Tests: `uv run pytest` (mockean el LLM; no requieren red ni clave real).
- La app exige una API key no vacía para el proveedor elegido; `.env` debe tener `ANTHROPIC_API_KEY` u `OPENAI_API_KEY`. Los tests inyectan `ANTHROPIC_API_KEY=test` desde `tests/conftest.py`.
- En Windows, `Start-Process uv ...` falla por el trampoline de uv. Para arrancar en segundo plano usa `.venv\Scripts\python.exe -m uvicorn app.main:app`.

## Contrato de configuración

- `LLM_PROVIDER` (`anthropic`|`openai`), `LLM_MODEL`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `APP_ENV`, `LOG_LEVEL`.
- `Settings` usa `extra="ignore"`: claves ajenas en `.env` no rompen el arranque.
- Un `LLM_PROVIDER` inválido o la falta de la clave del proveedor hacen fallar el arranque.

## Estado del código

- Implementado: `/health`, `POST /api/v1/estimate`, clientes OpenAI/Anthropic, prompt con ejemplos few-shot y tests.
- CAG puro: sin BD, retrieval ni persistencia; no añadas estado entre peticiones.
- El endpoint de estimación es `def` (threadpool) porque los SDKs son síncronos. No lo cambies a `async def` sin migrar a clientes async.

## OpenSpec

- CLI v1.13.1. Valida con `openspec validate --all`.
- El change `estimador-cag` está completo y validado; se puede archivar con `/opsx-archive`.
