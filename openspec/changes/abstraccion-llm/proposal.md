# Proposal

## Why

La elección de proveedor LLM está cableada en el código (`if settings.LLM_PROVIDER == "openai"`), cada petición instancia su propio cliente sin timeout y no existe failover: si el proveedor elegido está caído o saturado, el producto entero falla. El change `robustez-llm`, aún sin implementar, resuelve la robustez construyendo esa fontanería a mano sobre los SDKs nativos; adoptar el `Router` de LiteLLM como capa de transporte da lo mismo (timeouts, reintentos, fallback, coste) con menos código y sin rehacerlo al añadir proveedores. Este change absorbe `robustez-llm` para no construir dos veces la misma capa.

## What Changes

- **BREAKING** `LLM_MODEL` pasa a exigir prefijo de proveedor (`openai/gpt-4o-mini`, `anthropic/claude-haiku-4-5`) y `LLM_PROVIDER` desaparece: el proveedor se deriva del modelo configurado.
- Añadir `litellm` con versión exacta y declarar `openai`, que hoy se importa pero no está en `pyproject.toml`.
- Sustituir `_call_openai` / `_call_anthropic` y el `if` de proveedor por un único `Router` de LiteLLM por proceso, construido desde `Settings`.
- Un solo nombre lógico (`estimator`) con failover ordenado: despliegue primario (`order: 1`) y, si está configurado, secundario (`order: 2`).
- Timeouts por despliegue y `num_retries` en el Router; los clientes de los SDKs quedan con `max_retries: 0`, que es lo que LiteLLM impone.
- Mantener el semáforo fail-fast: `max_parallel_requests` del Router es asíncrono y responde `429`, mientras el contrato del endpoint exige `503`.
- Traducir `litellm.exceptions` a la jerarquía `LLMTimeoutError` / `LLMRateLimitError` / `LLMUpstreamError` / `LLMConfigError` / `LLMCapacityError`.
- Registrar tokens y coste por llamada (`litellm.completion_cost`), sin cachear respuestas.
- Absorber el resto de `robustez-llm` sin cambios de alcance: límite de entrada, contrato HTTP de errores y logs con identificador de petición.
- Retirar el change `robustez-llm` una vez absorbido y actualizar `AGENTS.md`.

## Capabilities

### New Capabilities

- `llm-abstraction`: llamada al proveedor por nombre lógico, failover ordenado entre proveedores, presupuesto de tiempo, concurrencia acotada, errores normalizados y registro de coste.

### Modified Capabilities

- `estimations`: límite máximo de transcripción, contrato de errores del LLM e identificador de petición.

> Nota: `openspec/specs/` sigue vacío porque el change `estimador-cag` no se ha archivado. La línea base de `estimations` está en `openspec/changes/estimador-cag/specs/estimations/spec.md`; hay que archivar ese change antes que este para que el delta MODIFIED se aplique sobre una spec real.

## Impact

- Código: `app/services/llm_service.py` (reescrito), `app/routers/estimations.py`, `app/schemas/estimation.py`, `app/config.py`, `app/main.py`.
- Dependencias: `litellm` (arrastra `boto3`, `tokenizers`, `huggingface-hub`, `tiktoken`, `aiohttp`) y `openai`; impacto directo en tamaño de imagen y tiempo de arranque.
- API: `POST /api/v1/estimate` mantiene el cuerpo de éxito; cambian los códigos de error y se añade `X-Request-ID`.
- Configuración: nuevas variables de timeouts, reintentos, concurrencia y modelo de respaldo; `LLM_PROVIDER` desaparece.
- Tests: los mocks se mueven a la frontera del Router; se mantiene el test de contrato existente.
- Sin persistencia, sin cache de respuestas y sin proxy externo: sigue siendo CAG puro.
- No incluye autenticación, cuotas por usuario, métricas ni streaming.
