# Design

## Context

Ver `proposal.md` - Why. El estado que condiciona el enfoque:

- `app/services/llm_service.py` decide el proveedor con `if settings.LLM_PROVIDER == "openai"`, instancia un cliente por petición y no fija `timeout` ni `max_retries`. Devuelve un `dict` que el router convierte en `EstimationResponse`.
- `openai` se importa de forma perezosa pero **no está declarado** en `pyproject.toml`; solo está `anthropic`.
- `robustez-llm` (0/17, sin implementar) ya diseñó timeouts, reintentos, semáforo, jerarquía de errores y `X-Request-ID` sobre los SDKs nativos. Este change lo absorbe: lo que LiteLLM ya resuelve no se reimplementa.
- El endpoint es `def` y corre en el threadpool de anyio; los clientes de los SDKs son síncronos y seguros entre hilos. `Router.completion` también es síncrono, así que encaja sin migrar el camino.
- `openspec/specs/` está vacío: `estimador-cag` sigue sin archivar, así que el delta `MODIFIED` de `estimations` necesita ese archivo antes de archivar este change.
- `structlog` ya tiene `merge_contextvars` configurado en `app/main.py`.

## Goals / Non-Goals

**Goals:**

- Que el código de negocio pida `estimator` y no sepa qué proveedor responde.
- Que un proveedor caído o saturado no tumbe el endpoint si hay un segundo configurado.
- Que el peor caso de latencia y el de coste sean acotados y conocidos.
- Que la robustez ya diseñada en `robustez-llm` se conserve sin duplicar código.
- Poder añadir un proveedor cambiando solo `.env`.

**Non-Goals:**

- Routing por complejidad, presupuestos por usuario, cuotas y métricas: pertenecen a `producto-multiusuario`.
- Proxy de LiteLLM como servicio aparte: un solo servicio, un solo proceso.
- Cache de respuestas, cache semántica o streaming.
- Reintentos con cola propia más allá del `num_retries` del Router.
- Migrar el endpoint a `async`.

## Decisions

### D1. Router en proceso, no proxy

Se usa la librería `litellm` con `Router` en el mismo proceso. El modo proxy añadiría un despliegue, un salto de red y una superficie de autenticación para un único consumidor; solo tendría sentido con varios servicios llamando al mismo gateway.

Consecuencia: el estado de salud y los cooldowns del Router viven en memoria del proceso y no se comparten entre workers. Se acepta: con varios workers cada uno aprende por su cuenta y el fallback sigue funcionando.

### D2. Un nombre lógico con `order`, no dos grupos con `fallbacks`

El código llama siempre a `model="estimator"`. El `model_list` se construye desde `Settings`:

```
model_list = [
  {"model_name": "estimator",
   "litellm_params": {"model": "anthropic/claude-haiku-4-5",
                      "api_key": ..., "order": 1, "timeout": <httpx.Timeout>}},
  {"model_name": "estimator",              # solo si LLM_FALLBACK_MODEL está definido
   "litellm_params": {"model": "openai/gpt-4o-mini",
                      "api_key": ..., "order": 2, "timeout": <httpx.Timeout>}},
]
```

Se elige `order` sobre la alternativa `fallbacks=[{"primario": ["secundario"]}]` porque mantiene **un único nombre lógico** en el código y en los logs de negocio, y porque LiteLLM documenta que al fallar un despliegue `order: 1` pasa al `order: 2`. La variante de dos grupos se descarta por filtrar dos nombres internos a la capa de aplicación.

Corrección respecto al ejemplo de la sesión: dos entradas con el mismo `model_name` **sin** `order` no son un fallback, son un grupo de balanceo (simple-shuffle). Sin `order`, el secundario recibiría tráfico en caliente y el fallback no sería determinista.

### D3. `num_retries=0`: el fallback es el reintento

Se fija `num_retries=0` en el Router y `RetryPolicy(DefaultRetries=0)`. Un error transitorio no se reintenta contra el mismo proveedor: se escala directamente al siguiente despliegue. El peor caso queda en `2 × timeout` en lugar de `(1 + N)² × timeout`.

Alternativas descartadas:

- `num_retries=1` (lo que proponía `robustez-llm`): con fallback, el peor caso pasa a ~8 minutos, incompatible con un producto público.
- `RetryPolicy` granular por tipo de error: se deja como palanca de configuración futura; añadirla ahora sin datos de producción es optimización prematura.

`max_retries` de los SDKs no se toca: el Router lo fija a `0` por diseño, así que configurarlo sería engañoso.

### D4. Timeout por despliegue con `httpx.Timeout`

Se conserva el reparto de `robustez-llm` (D1): `connect=5 s`, `write=10 s`, `read=120 s`, `pool=5 s`, pasado como `httpx.Timeout` en los `litellm_params` del despliegue. Un escalar único aplicaría 120 s también a la conexión, que es justo el caso que se quiere cortar rápido.

`read=120 s` cubre 4.000 tokens de salida a ~50 tok/s (~80 s) con margen. Verificación obligatoria en la implementación: comprobar que la versión fijada propaga el objeto a los clientes de los SDKs; si no lo hace, se degrada a escalar `timeout=LLM_READ_TIMEOUT_S` y se anota la pérdida.

### D5. El semáforo fail-fast se queda

`max_parallel_requests` del Router está documentado como límite **asíncrono** y rechaza con `429`, no con `503 + Retry-After`. El contrato del endpoint exige lo segundo y el endpoint es síncrono, así que se mantiene el `threading.BoundedSemaphore` de `robustez-llm` (D4) envolviendo la llamada completa al Router, incluidos los saltos de fallback. Se libera en `finally`.

Esto además acota el recurso más escaso: los 40 hilos del threadpool.

### D6. Jerarquía propia, traducción desde `litellm.exceptions`

Se mantiene la jerarquía de `robustez-llm` (D5) y cambia solo el origen de la traducción:

```
  LLMServiceError
    +-- LLMTimeoutError      <- litellm.Timeout, httpx.TimeoutException
    +-- LLMRateLimitError    <- litellm.RateLimitError
    +-- LLMUpstreamError     <- APIConnectionError, InternalServerError,
    |                           ServiceUnavailableError, BadGatewayError, resto
    +-- LLMConfigError       <- AuthenticationError, PermissionDeniedError,
    |                           BadRequestError, ContextWindowExceededError
    +-- LLMCapacityError     <- semáforo local
```

Las cláusulas `except` van de la más específica a la más general porque las excepciones de LiteLLM heredan de `openai` y comparten base. `BadRequestError` y `ContextWindowExceededError` se clasifican como configuración: con el límite de 50.000 caracteres no deberían ocurrir, y si ocurren el fallo es nuestro, no del proveedor.

El router HTTP solo mapea clase a código (`504`, `503 + Retry-After`, `502`, `500`) y compone un mensaje fijo; nunca usa `str(exc)`.

### D7. `provider` es el que respondió, resuelto sin API privada

La respuesta mantiene `{estimation, model, provider, usage}`. `model` es el modelo físico que devuelve LiteLLM. `provider` se resuelve con una tabla `{modelo_físico: proveedor}` construida al montar el Router desde la propia configuración (ya conocemos el prefijo de cada despliegue), en lugar de leer `_hidden_params` (API privada) o adivinar con `get_llm_provider`.

La coincidencia no puede ser exacta: los proveedores responden con snapshots fechados (`claude-haiku-4-5-20251001`, `gpt-4o-mini-2024-07-18`), como confirmó la prueba manual del 2026-11-27. Se resuelve primero por igualdad y, si no, por el nombre configurado más largo que sea prefijo del devuelto (`modelo + "-"`), para que `gpt-4o-mini` gane a `gpt-4o`. Si nada coincide, se registra un warning y se usa el proveedor del despliegue primario. Un test con `mock_response` fija el comportamiento.

### D8. Coste desde la tabla de precios de LiteLLM

`litellm.completion_cost(completion_response=response)` da el coste de la llamada. Se registra junto a tokens y proveedor y se expone en la respuesta como `usage.cost_usd` (en USD, que es la unidad de la tabla de LiteLLM), porque el cliente que recibe la estimación quiere saber lo que ha costado generarla sin leer los logs. Es un coste **estimado** con la tabla de precios local, no una factura.

Si devuelve `None` (modelo desconocido para la tabla), se registra `cost_usd=None` y la respuesta lleva `cost_usd: null`; la petición no falla: el coste es observabilidad y contrato, pero nunca una condición de error.

### D9. Sin cache

`cache_responses=False` y sin `Redis`. Dos peticiones idénticas deben producir dos llamadas: el servicio es CAG (contexto en el prompt), no un cache de respuestas, y cachear cambiaría el comportamiento observable y ocultaría coste real. El estado interno del Router (cooldowns, salud) es infraestructura y no se persiste.

### D10. Configuración: el modelo lleva el proveedor

`LLM_PROVIDER` desaparece y `LLM_MODEL` pasa a exigir prefijo (`openai/...`, `anthropic/...`). Es **BREAKING** para `.env`, pero elimina la posibilidad de configurar un proveedor y un modelo que no encajan.

```
LLM_MODEL=anthropic/claude-haiku-4-5      # obligatorio, con prefijo
LLM_FALLBACK_MODEL=openai/gpt-4o-mini     # opcional
LLM_CONNECT_TIMEOUT_S=5
LLM_READ_TIMEOUT_S=120
LLM_WRITE_TIMEOUT_S=10
LLM_POOL_TIMEOUT_S=5
LLM_MAX_RETRIES=0
LLM_MAX_CONCURRENCY=8
```

`Settings` valida: prefijo presente en ambos modelos, `ANTHROPIC_API_KEY`/`OPENAI_API_KEY` presentes según el prefijo de cada despliegue, y valores positivos (reintentos `>= 0`). `LLM_PROVIDER` se elimina de `AGENTS.md` y de `.env.example`.

### D11. Dependencia fijada y lock con hashes

`litellm==1.111.0` (versión exacta, no `>=`) y `openai>=2.20`, que LiteLLM exige y que hoy falta. `uv.lock` aporta los hashes; un `uv lock --upgrade` es una decisión deliberada, no un efecto colateral de un despliegue. Es la respuesta directa a la nota de supply chain de la sesión.

Coste asumido: LiteLLM arrastra `boto3`, `tokenizers`, `huggingface-hub`, `tiktoken` y `aiohttp`. Se medirá el tamaño de imagen y el tiempo de import; si el arranque se degrada de forma inaceptable, la alternativa es un wrapper propio de ~100 líneas sobre los SDKs, que es exactamente el trabajo que `robustez-llm` ya tenía diseñado.

### D12. Telemetría y ruido de LiteLLM desactivados

Al importar se fija `litellm.telemetry = False`, `litellm.suppress_debug_info = True` y `litellm.drop_params = True`. Sin esto, la librería emite telemetría anónima y logs propios que se mezclarían con los de `structlog` y romperían la correlación por `request_id`.

### D13. Tests en dos niveles

- **Unidad**: se monkeypatchea `_get_router()` por un falso con `completion()` controlado. Cubre normalización, mapeo de excepciones, semáforo y contrato HTTP sin importar LiteLLM en el camino rápido.
- **Integración del Router**: un test construye el `model_list` real con `mock_response` en los `litellm_params` y verifica que el fallback de `order` funciona y que `provider` refleja el despliegue que respondió. Es la única forma de comprobar que la configuración que escribimos es la que LiteLLM entiende.

Se conserva `tests/test_estimate.py` sin tocar (contrato de éxito).

### D14. Absorción explícita de `robustez-llm`

| `robustez-llm` | Destino |
|---|---|
| 1.1–1.3 (config, límites de entrada) | Se hereda; 1.1 cambia a los campos nuevos |
| 2.1 (singletons + timeouts + `max_retries`) | Se sustituye por D1–D4 |
| 2.2 (cerrar clientes en `lifespan`) | Se cae: el Router no expone `close()` |
| 2.3, 2.5 (semáforo y liberación) | Se hereda tal cual (D5) |
| 2.4 (taxonomía de errores) | Se hereda el diseño, cambia la traducción (D6) |
| 3.x (contrato HTTP) | Se hereda sin cambios |
| 4.x (identificador de petición, logs) | Se hereda reducido a D15; se añade `cost` al log |
| 5.x (verificación) | Se hereda y se amplía con el fallback |

### D15. Identificador de petición mínimo, sin validación de entrada

Se genera `uuid4().hex` por petición, se liga con `structlog.contextvars.bound_contextvars` y se devuelve en `X-Request-ID`. No se acepta el identificador del cliente: desaparece la validación, el riesgo de inyección en logs y el caso de cabeceras duplicadas.

Sigue siendo un middleware ASGI puro (~15 líneas) y no una dependencia de ruta, porque los `422` y los `404` se producen fuera de la resolución de dependencias y el requisito cubre toda respuesta. Se registra antes de `CORSMiddleware` para que CORS quede por fuera.

Fuera de alcance, y apuntado para el change de observabilidad: aceptar y validar el `X-Request-ID` entrante (`re.fullmatch`, longitud 1-64), añadir `expose_headers=["X-Request-ID"]` a CORS para que un cliente JS pueda leerlo, y trazas distribuidas (`traceparent`). También se acepta y se documenta que un 500 no capturado sale de `ServerErrorMiddleware` —siempre el más externo— sin la cabecera.

### D16. Medición real de arranque y tamaño

Medido el 2026-11-27 en Windows con Python 3.11 y `litellm==1.111.0`:

| Métrica | Valor |
|---|---|
| `import app.main` | 13,6–17,0 s (dos ejecuciones) |
| `import litellm` | 11,5 s |
| `import openai` | 3,5 s |
| Tamaño de `.venv` | 305 MB |

LiteLLM aporta ~14 s de los ~17 s totales; el coste no es del código propio. Supera cualquier presupuesto razonable de arranque de un servicio pequeño, así que se deja constancia aquí: es el precio de la abstracción multi-proveedor elegida. La palanca de rollback sigue siendo el wrapper propio de ~100 líneas sobre los SDKs (el diseño de `robustez-llm`), que reduciría el arranque a ~4 s y el entorno a una fracción. No se cambia ahora porque el objetivo del change era precisamente no mantener ese wrapper.

Mitigación operativa mientras se mantenga LiteLLM: arrancar el proceso antes de abrir tráfico (readiness probe) y no usar `--reload` en producción, donde cada recarga paga los ~17 s.

## Risks / Trade-offs

- [Peor caso de latencia de ~4 min por petición (2 × 120 s)] → Documentarlo y fijar los timeouts de proxy y balanceador por encima; si el SLO exige menos, bajar `LLM_READ_TIMEOUT_S`, que es la única palanca.
- [Peso de la dependencia: `boto3`, `tokenizers`, `huggingface-hub`] → Medir imagen y arranque en la tarea de verificación; el rollback es el wrapper propio.
- [Supply chain: LiteLLM es un objetivo de alto valor] → Versión exacta, `uv.lock` con hashes, upgrades revisados y `uv sync` sin `--upgrade` en despliegue.
- [Resolver `provider` depende de qué devuelve `response.model`] → Tabla propia con igualdad y prefijo (snapshots fechados) + test con `mock_response`; el fallback es el proveedor del primario con warning.
- [Cooldowns en memoria: un despliegue en cooldown puede producir "No deployments available"] → Mapear ese error a `LLMUpstreamError`/`LLMRateLimitError` y cubrirlo con test; el mensaje al cliente sigue siendo genérico.
- [Un 401 en el primario rota al secundario] → Aceptado: es otra credencial y otro proveedor. Solo se considera no recuperable el fallo de configuración repetido en ambos, que acaba en `LLMConfigError`.
- [Telemetría o logs de LiteLLM filtrando datos] → D12 y revisión de que no se registran prompts.
- [El delta `MODIFIED` de `estimations` no se puede archivar hasta archivar `estimador-cag`] → Primera tarea del change.

## Migration Plan

1. Archivar `estimador-cag` para que exista `openspec/specs/estimations/spec.md`.
2. Retirar `robustez-llm` (absorbido) para que solo quede un change activo.
3. Añadir dependencias y `uv lock`; verificar `uv sync` e import.
4. Actualizar `Settings`, `.env.example` y `AGENTS.md` (repo único, contrato nuevo, LiteLLM como capa).
5. Implementar el Router y sustituir el `if` de proveedor.
6. Traducir errores, mantener el semáforo y el mapeo HTTP.
7. Añadir el identificador de petición mínimo y el logging con coste.
8. `uv run pytest` y prueba manual de fallback forzando un primario inválido.

Rollback: revertir el commit y restaurar `LLM_PROVIDER` + `LLM_MODEL` sin prefijo en `.env`. No hay migración de datos ni cambios en el cuerpo de éxito.

## Open Questions

- Valor definitivo de `LLM_MAX_CONCURRENCY`: depende del tier de RPM/TPM contratado.
- Si se quiere un secundario en producción desde el día uno: el default es vacío, y activarlo duplica el peor caso de latencia.
- Si el coste debe persistirse o agregarse por usuario: queda para `producto-multiusuario`.
