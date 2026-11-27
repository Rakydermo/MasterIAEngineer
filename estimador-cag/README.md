# Estimador CAG

API FastAPI que recibe la transcripción de una reunión y devuelve una estimación de software generada por un LLM. Usa arquitectura CAG (Cache-Augmented Generation): sin base de datos, sin retrieval y sin persistencia; el contexto son ejemplos estáticos incluidos en el prompt.

La invocación al proveedor pasa por `litellm.Router` bajo un nombre lógico de modelo (`estimator`), con failover ordenado, tiempo acotado por intento y concurrencia limitada.

## Requisitos

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- Una API key por cada proveedor que aparezca en `LLM_MODEL` o `LLM_FALLBACK_MODEL`

## Puesta en marcha

1. Instala dependencias (incluye el grupo de desarrollo):

   ```bash
   uv sync --group dev
   ```

2. Crea el fichero de entorno:

   ```bash
   cp .env.example .env
   ```

3. Rellena `ANTHROPIC_API_KEY` y/o `OPENAI_API_KEY` en `.env` y ajusta `LLM_MODEL`.

4. Arranca el servidor:

   ```bash
   uv run uvicorn app.main:app --reload
   ```

La documentación interactiva queda en `http://127.0.0.1:8000/docs`.

## Variables de entorno

| Variable | Obligatoria | Por defecto | Descripción |
|---|---|---|---|
| `LLM_MODEL` | no | `anthropic/claude-haiku-4-5` | Modelo principal con prefijo de proveedor obligatorio: `anthropic/...` u `openai/...` |
| `LLM_FALLBACK_MODEL` | no | vacío | Modelo de respaldo, mismo formato `proveedor/modelo` |
| `ANTHROPIC_API_KEY` | si hay un modelo `anthropic/...` | — | Clave de Anthropic |
| `OPENAI_API_KEY` | si hay un modelo `openai/...` | — | Clave de OpenAI |
| `LLM_CONNECT_TIMEOUT_S` | no | `5` | Timeout de conexión por intento |
| `LLM_READ_TIMEOUT_S` | no | `120` | Timeout de lectura por intento |
| `LLM_WRITE_TIMEOUT_S` | no | `10` | Timeout de escritura por intento |
| `LLM_POOL_TIMEOUT_S` | no | `5` | Timeout de espera de conexión del pool |
| `LLM_MAX_RETRIES` | no | `0` | Reintentos contra el mismo despliegue; con `0` el fallback es el reintento |
| `LLM_MAX_CONCURRENCY` | no | `8` | Llamadas simultáneas al proveedor; al superarlo se responde `503` |
| `APP_ENV` | no | `development` | `development`, `staging` o `production` |
| `LOG_LEVEL` | no | `DEBUG` | `DEBUG`, `INFO`, `WARNING` o `ERROR` |

`LLM_PROVIDER` ya no existe: el proveedor se deriva del prefijo del modelo. Un `.env` antiguo con `LLM_PROVIDER` y `LLM_MODEL` sin prefijo no arranca.

El servicio valida al arrancar el prefijo de cada modelo, la clave de cada proveedor configurado y que los timeouts, reintentos y concurrencia tengan valores válidos.

## Endpoints

Toda respuesta incluye la cabecera `X-Request-ID`, un identificador generado por el servicio y presente en todas las líneas de log de esa petición. El identificador enviado por el cliente se ignora.

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

La transcripción debe tener entre 50 y 50.000 caracteres y contener al menos un carácter no blanco. La respuesta incluye `estimation` (markdown), `model` (modelo físico que respondió), `provider` y `usage` con los tokens de entrada, salida y total, más `cost_usd`, el coste estimado en USD de esa llamada (`null` si el modelo no está en la tabla de precios).

```json
{
  "estimation": "## Plataforma de inventario\n\n| Tarea | Horas | Coste (EUR) |\n...",
  "model": "claude-haiku-4-5-20251001",
  "provider": "anthropic",
  "usage": {
    "input_tokens": 1754,
    "output_tokens": 959,
    "total_tokens": 2713,
    "cost_usd": 0.006555
  }
}
```

### Errores

El campo `detail` es un mensaje fijo: nunca incluye el texto original del proveedor, secretos ni fragmentos de la petición. El detalle completo queda en el log, junto con `X-Request-ID`, proveedor y modelo.

| Código | Causa | `Retry-After` |
|---|---|---|
| `422` | Cuerpo inválido o transcripción fuera de rango | no |
| `500` | Credenciales o configuración rechazadas, o fallo no clasificado | no |
| `502` | El proveedor falla o no se puede conectar | no |
| `503` | El proveedor limita la tasa o se agota la concurrencia local | sí, `5` |
| `504` | El proveedor no responde dentro del presupuesto de tiempo | no |

## Tests

```bash
uv run pytest
uv run ruff check .
```

Los tests no llaman a ningún proveedor real: mockean el Router y usan `mock_response` para verificar el failover por `order`. Cubren `/health`, el contrato de estimación, la validación 422, el mapeo de errores, el semáforo, la resolución de proveedor, los logs y `X-Request-ID`.

## Estructura

```
estimador-cag/
├── app/
│   ├── main.py          # FastAPI, CORS, middleware de request id, logging y /health
│   ├── middleware.py    # X-Request-ID por petición
│   ├── config.py        # Settings (.env)
│   ├── routers/         # /api/v1/estimate y mapeo de errores HTTP
│   ├── services/        # Router de LiteLLM, semáforo y normalización
│   ├── schemas/         # modelos Pydantic
│   └── context/         # ejemplos few-shot (CAG)
├── tests/
└── pyproject.toml
```
