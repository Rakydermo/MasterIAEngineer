# Tasks

## 1. Entorno reproducible

- [x] 1.1 Ejecutar `uv lock` y verificar que `uv.lock` resuelve el proyecto `estimador-cag` y ya no menciona `mi-proyecto`
- [x] 1.2 Ejecutar `uv sync --group dev` y verificar con `uv run python -c "import structlog, pytest, fastapi"` que no hay `ModuleNotFoundError`
- [x] 1.3 Arrancar `uv run uvicorn app.main:app --reload` y verificar que `GET /health` responde 200

## 2. Configuración y entorno

- [x] 2.1 Actualizar `.env.example` con `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `LLM_PROVIDER`, `LLM_MODEL`, `APP_ENV` y `LOG_LEVEL`, y verificar que `Settings()` carga sin errores
- [x] 2.2 Migrar el `.env` local (`API_KEY` → `ANTHROPIC_API_KEY`, `MODEL_NAME` → `LLM_MODEL`, eliminar `GEMINI_API_KEY`) y verificar que la app arranca
- [x] 2.3 Añadir `extra="ignore"` a `SettingsConfigDict` y verificar que una clave ajena ya no rompe el arranque

## 3. Código

- [x] 3.1 Cambiar `create_estimation` a `def` y verificar que `POST /api/v1/estimate` sigue devolviendo el contrato esperado con el LLM mockeado
- [x] 3.2 Corregir CORS (`allow_credentials=False` con orígenes `*`) y verificar la cabecera `access-control-allow-origin` en una petición preflight
- [x] 3.3 Aplicar `LOG_LEVEL` en `configure_logging` y verificar que el nivel configurado filtra los logs
- [x] 3.4 Corregir el encoding de `app/context/examples.py` (sustituir `�?"` por `—`) y verificar que el prompt no contiene caracteres de reemplazo
- [x] 3.5 Renombrar el proyecto en `pyproject.toml` a `estimador-cag` y verificar con `uv lock --check`

## 4. Tests

- [x] 4.1 Crear `tests/conftest.py` con `ANTHROPIC_API_KEY=test` y limpieza de la caché de `get_settings`; verificar que `uv run pytest` colecta sin errores
- [x] 4.2 Añadir test de `GET /health` (200 y campos `status`, `version`, `environment`) y verificar que pasa
- [x] 4.3 Añadir test de `POST /api/v1/estimate` con `generate_estimation` mockeado (200 y contrato) y de transcripción corta (422); verificar que ambos pasan

## 5. Documentación y verificación final

- [x] 5.1 Actualizar `README.md` (arranque con `uv sync --group dev`, variables, endpoints y ejemplo) y verificar que no menciona `requirements.txt`
- [x] 5.2 Actualizar `AGENTS.md` (retirar el aviso obsoleto sobre `uv run` y reflejar el estado real del código) y verificar que las instrucciones coinciden con el repo
- [x] 5.3 Ejecutar `uv run pytest` y el arranque con `GET /health`; verificar que todo queda en verde
