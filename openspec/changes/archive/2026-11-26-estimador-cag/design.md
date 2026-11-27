# Design

## Context

Ver `proposal.md` - Why para la motivación. El estado actual que condiciona el enfoque:

- `app/config.py` ya define `Settings` con `lru_cache` y valida la API key del proveedor.
- `app/main.py` configura `structlog` en el `lifespan` y monta el router en `/api/v1`.
- `app/services/llm_service.py` usa los SDKs síncronos de OpenAI y Anthropic, y `app/context/examples.py` aporta tres ejemplos few-shot.
- `pyproject.toml` ya es PEP 621, pero `uv.lock` resuelve un proyecto ajeno (`mi-proyecto`) y `.venv` no tiene `structlog`.

## Goals / Non-Goals

**Goals:**

- Dejar el repositorio reproducible con `uv lock` + `uv sync --group dev`.
- Un único contrato de configuración, documentado y validado al arrancar.
- Mantener CAG puro: sin base de datos, retrieval ni persistencia.
- Tests de humo sin red que cubran los dos endpoints.

**Non-Goals:**

- Streaming de respuestas, caché de estimaciones o autenticación de la API.
- Migrar a clientes async de los SDKs (se valora en otra iteración).
- Cambiar el formato de la estimación (markdown con tabla, equipo y duración).

## Decisions

### D1. `config.py` es la fuente de verdad del entorno

Se mantienen `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`, `APP_ENV` y `LOG_LEVEL`. Alternativa descartada: `API_KEY`/`MODEL_NAME`, porque una sola clave no distingue proveedor y obliga a tocar código ya probado.

- `.env` y `.env.example` se actualizan a estos nombres.
- `extra="ignore"` en `SettingsConfigDict` para tolerar claves ajenas (`GEMINI_API_KEY`) sin desactivar la validación de la clave del proveedor. Alternativa descartada: `extra="forbid"` + limpiar `.env`, más frágil ante ficheros locales reutilizados.

### D2. Endpoint síncrono en threadpool

`create_estimation` pasa de `async def` a `def`: FastAPI lo ejecuta en threadpool y evita bloquear el event loop con SDKs síncronos. Alternativas: `run_in_threadpool` (equivalente pero más ruido) o clientes async (`AsyncOpenAI`/`AsyncAnthropic`), que se posponen para no ampliar el alcance.

### D3. Lock y venv se regeneran desde `pyproject.toml`

`uv lock` + `uv sync --group dev`. El lock actual se descarta porque su raíz es `mi-proyecto`. Se renombra el proyecto a `estimador-cag` para que coincida con la carpeta. Alternativa descartada: mantener `estimator`, que perpetúa la ambigüedad.

### D4. CORS sin credenciales

Se mantiene `allow_origins=["*"]` para desarrollo con `allow_credentials=False`. Alternativa: lista blanca de orígenes, que se pospone hasta que exista un frontend conocido.

### D5. Tests de humo con `TestClient` y monkeypatch

`tests/test_health.py` y `tests/test_estimate.py`. Se parchea `generate_estimation` para no llamar al LLM, se define `ANTHROPIC_API_KEY=test` en `tests/conftest.py` antes de importar la app y se limpia la caché de `get_settings`. `pytest`, `pytest-asyncio` y `httpx` ya están en el grupo `dev`.

### D6. `LOG_LEVEL` se aplica a structlog

`configure_logging` usa `settings.LOG_LEVEL` para filtrar el nivel mínimo. Alternativa descartada: eliminar el campo, porque el nivel es útil en producción.

## Risks / Trade-offs

- [El lock regenerado resuelve versiones mayores que las instaladas (anthropic 2.x, openai 3.x) y la API puede haber cambiado] → Verificar con tests mockeados y, si falla, fijar versiones en `pyproject.toml`.
- [Sin timeouts, una llamada lenta ocupa un worker del threadpool] → Añadir timeout explícito en los clientes como tarea de hardening posterior.
- [Sin `max_length` en `transcription`, una entrada enorme dispara coste y contexto] → Añadir límite en una tarea de hardening posterior.
- [Se asume que el valor actual de `API_KEY` es de Anthropic] → Confirmar antes de migrar; si no lo es, no renombrar y pedir la clave correcta.
- [La sesión original puede seguir editando `app/`] → Comprobar `git status` y timestamps justo antes de aplicar.

## Migration Plan

1. `uv lock` y `uv sync --group dev`.
2. Migrar `.env` local: `API_KEY` → `ANTHROPIC_API_KEY`, `MODEL_NAME` → `LLM_MODEL`, eliminar `GEMINI_API_KEY`.
3. Aplicar cambios de código y documentación.
4. `uv run pytest` y `uv run uvicorn app.main:app --reload` con `GET /health`.

Rollback: restaurar `.env` y `uv.lock` previos. No hay cambios de contrato externo ni migraciones de datos.

## Open Questions

- ¿El límite de tamaño de transcripción y los timeouts entran en esta iteración o en una tarea de hardening separada?
