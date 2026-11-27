# Tasks

## 1. Higiene del repositorio y documentación

- [x] 1.1 Archivar el change `estimador-cag` con `openspec archive estimador-cag --yes` para crear `openspec/specs/estimations/spec.md`; verificar con `openspec show estimations --type spec` que las tres requirements base existen
- [x] 1.2 Retirar el change `robustez-llm`, ya absorbido por este, y verificar con `openspec list --json` que `abstraccion-llm` es el único change activo y `openspec validate --all` sigue en verde
- [x] 1.3 Actualizar `AGENTS.md`: repo único en la raíz (sin `.git` en `estimador-cag/`), LiteLLM como capa de transporte, `LLM_PROVIDER` fuera del contrato, dependencias reales y estado del código; verificar que las variables listadas coinciden con `app/config.py` y `.env.example`

## 2. Dependencias y configuración

- [ ] 2.1 Añadir `litellm==1.111.0` y `openai>=2.20` a `pyproject.toml`, regenerar `uv.lock` y verificar con `uv sync --group dev` y `uv run python -c "import litellm, openai; print(litellm.__version__)"` que ambos importan
- [x] 2.2 Sustituir `LLM_PROVIDER` por `LLM_MODEL` con prefijo obligatorio, añadir `LLM_FALLBACK_MODEL`, `LLM_CONNECT_TIMEOUT_S`, `LLM_READ_TIMEOUT_S`, `LLM_WRITE_TIMEOUT_S`, `LLM_POOL_TIMEOUT_S`, `LLM_MAX_RETRIES` y `LLM_MAX_CONCURRENCY`, y validar en `Settings` el prefijo de cada modelo y la clave del proveedor de cada despliegue; verificar con tests que un modelo sin prefijo, una clave ausente y un valor no positivo impiden construir `Settings`
- [x] 2.3 Documentar las variables nuevas en `.env.example` con sus defaults y una línea de propósito; verificar que la app arranca sin definir las opcionales y que `LLM_MODEL` aparece con prefijo
- [ ] 2.4 Añadir `max_length=50_000` y un `field_validator` que rechace contenido vacío tras `strip()` en `EstimationRequest.transcription`; verificar con tests que 50 caracteres en blanco y 50.001 caracteres devuelven 422 y no invocan al proveedor

## 3. Router y wrapper

- [ ] 3.1 Implementar `_build_model_list()` desde `Settings` (nombre lógico `estimator`, `order` 1/2, `httpx.Timeout` por despliegue) y `_get_router()` como singleton perezoso con `num_retries=0`, `RetryPolicy(DefaultRetries=0)` y `cache_responses=False`; verificar con un test que dos llamadas devuelven la misma instancia y que el `model_list` contiene los despliegues y órdenes esperados
- [ ] 3.2 Fijar `litellm.telemetry = False`, `litellm.suppress_debug_info = True` y `litellm.drop_params = True` al importar el servicio; verificar con un test que los tres flags quedan desactivados y que el log de una petición no contiene líneas propias de LiteLLM
- [ ] 3.3 Reescribir `generate_estimation` para llamar a `router.completion(model="estimator", ...)` con el prompt de sistema y la transcripción como mensajes, sin ramas por proveedor; verificar con un test que el router falso recibe un único `model` lógico y el mensaje de sistema
- [ ] 3.4 Normalizar la respuesta a `{estimation, model, provider, usage}` resolviendo `provider` con la tabla modelo físico → proveedor construida desde la configuración, con warning y proveedor primario si no hay coincidencia; verificar con tests la respuesta del primario, la del secundario y el caso de modelo desconocido
- [ ] 3.5 Registrar tokens de entrada y salida, `provider`, `model` y coste con `litellm.completion_cost`, tolerando que devuelva `None`; verificar con un test que el log contiene las cinco claves y que un coste desconocido no hace fallar la petición
- [ ] 3.6 Envolver la llamada al Router en un `threading.BoundedSemaphore(LLM_MAX_CONCURRENCY)` con `acquire(blocking=False)`, lanzar `LLMCapacityError` sin hueco y liberar en `finally`; verificar con tests que con el semáforo lleno el proveedor no recibe la llamada y que tras un fallo el hueco vuelve a estar disponible

## 4. Errores

- [ ] 4.1 Traducir las excepciones de LiteLLM y de httpx a `LLMTimeoutError`, `LLMRateLimitError`, `LLMUpstreamError` y `LLMConfigError`, dejando `LLMServiceError` como base y ordenando las cláusulas `except` de específica a general; verificar con tests de servicio que un timeout, un 429, un 5xx, un 401 y una excepción desconocida producen la clase esperada
- [ ] 4.2 Mapear cada subclase a su código en el router: 504, 503 con `Retry-After`, 502 y 500, con un mensaje fijo por clase; verificar con un test parametrizado que cada excepción produce su código y su `detail`
- [ ] 4.3 Eliminar `detail=str(exc)` y registrar el detalle completo solo en el log, junto con proveedor, modelo y `request_id`; verificar con un test que un error del proveedor con un texto marcador no aparece en el cuerpo de la respuesta
- [ ] 4.4 Mantener el 200 y el cuerpo de éxito sin cambios; verificar que `tests/test_estimate.py` sigue pasando sin modificarlo

## 5. Logs y observabilidad

- [ ] 5.1 Añadir a los logs de la petición `duration_ms`, `outcome`, `provider`, `model`, tokens y coste; verificar con un test que captura la salida de structlog y comprueba que aparecen las seis claves
- [ ] 5.2 Generar `uuid4().hex` por petición en un middleware ASGI mínimo, ligarlo con `structlog.contextvars.bound_contextvars` y devolverlo en `X-Request-ID`, sin aceptar el identificador del cliente; verificar con tests que dos peticiones reciben identificadores distintos, que el `request_id` del log coincide con el de la respuesta y que un `X-Request-ID` enviado por el cliente se ignora. Apunte para el change de observabilidad: aceptar y validar el identificador entrante, `expose_headers` en CORS y trazas distribuidas

## 6. Verificación

- [ ] 6.1 Ejecutar `uv run pytest` completo y `uv run ruff check .`; verificar que ambos terminan sin errores
- [ ] 6.2 Medir el impacto de la dependencia con `uv run python -X importtime -c "import app.main"` y el tamaño del entorno; verificar que el arranque queda documentado y que no supera el presupuesto aceptado o, si lo supera, dejar constancia en el change
- [ ] 6.3 Actualizar `README.md` con la tabla de códigos de error, la cabecera `X-Request-ID`, las variables nuevas y el formato `proveedor/modelo`; verificar que los códigos documentados coinciden con los tests
- [ ] 6.4 Prueba manual con `uv run uvicorn app.main:app`: una transcripción válida devuelve 200 con `X-Request-ID`; con `LLM_MODEL` apuntando a una clave inválida y un `LLM_FALLBACK_MODEL` válido la petición responde 200 con el `provider` del secundario; con `LLM_MAX_CONCURRENCY=1` en paralelo devuelve 503 con `Retry-After`
