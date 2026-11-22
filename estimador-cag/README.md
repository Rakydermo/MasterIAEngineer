# Estimador CAG

API FastAPI que recibe la transcripción de una reunión y devuelve una estimación de software generada por un LLM. Usa arquitectura CAG (Cache-Augmented Generation): sin base de datos, sin retrieval y sin persistencia; el contexto son ejemplos estáticos incluidos en el prompt.

## Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Una API key de Anthropic o OpenAI

## Puesta en marcha

1. Instala dependencias (incluye el grupo de desarrollo):

   ```bash
   uv sync --group dev
   ```

2. Crea el fichero de entorno:

   ```bash
   cp .env.example .env
   ```

3. Rellena `ANTHROPIC_API_KEY` (o `OPENAI_API_KEY`) en `.env`.

4. Arranca el servidor:

   ```bash
   uv run uvicorn app.main:app --reload
   ```

La documentación interactiva queda en `http://127.0.0.1:8000/docs`.

## Variables de entorno

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `LLM_PROVIDER` | no | `openai` | `anthropic` u `openai` |
| `LLM_MODEL` | no | `gpt-4o-mini` | Modelo del proveedor |
| `ANTHROPIC_API_KEY` | según proveedor | — | Obligatoria si `LLM_PROVIDER=anthropic` |
| `OPENAI_API_KEY` | según proveedor | — | Obligatoria si `LLM_PROVIDER=openai` |
| `APP_ENV` | no | `development` | `development`, `staging` o `production` |
| `LOG_LEVEL` | no | `DEBUG` | `DEBUG`, `INFO`, `WARNING` o `ERROR` |

El servicio valida al arrancar que exista la clave del proveedor seleccionado.

## Endpoints

### `GET /health`

```bash
curl http://127.0.0.1:8000/health
```

```json
{"status": "healthy", "version": "0.1.0", "environment": "development"}
```

### `POST /api/v1/estimate`

```bash
curl -X POST http://127.0.0.1:8000/api/v1/estimate \
  -H "Content-Type: application/json" \
  -d '{"transcription": "Reunión: el cliente necesita una plataforma web de inventario con alertas de reposición y panel de métricas."}'
```

La transcripción debe tener al menos 50 caracteres. La respuesta incluye `estimation` (markdown), `model`, `provider` y `usage` con los tokens de entrada, salida y total. Si el proveedor falla, responde 500; si la entrada no es válida, 422.

## Tests

```bash
uv run pytest
```

Los tests no llaman al LLM: mockean el servicio y cubren `/health`, el contrato de estimación y la validación 422.

## Estructura

```
estimador-cag/
├── app/
│   ├── main.py          # FastAPI, CORS, logging y /health
│   ├── config.py        # Settings (.env)
│   ├── routers/         # /api/v1/estimate
│   ├── services/        # clientes OpenAI/Anthropic
│   ├── schemas/         # modelos Pydantic
│   └── context/         # ejemplos few-shot (CAG)
├── tests/
└── pyproject.toml
```
