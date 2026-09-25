# Uso de DSPy en TRAMA

**Estado:** guía para un piloto; DSPy todavía no está integrado en el runtime.
**Verificado:** 2026-09-25.

## Para qué sirve aquí

DSPy permite expresar una tarea de modelo como módulos Python con entradas y
salidas tipadas, medir su calidad y optimizar instrucciones o ejemplos contra
una métrica. No sirve como servidor de modelos ni sustituye Hermes, MCP, CCCC,
el Gateway Go o las políticas del control plane.

El primer caso que vale la pena evaluar es la **descomposición de un requisito
en un borrador de fases, tareas, dependencias, criterios y preguntas abiertas**.
El modelo propone contenido; TRAMA asigna IDs y contexto de organización/proyecto,
valida los contratos y mantiene la aprobación humana antes de habilitar tareas
para CCCC.

Hoy Hermes propone y registra planes por la API/MCP. El contrato
[`PlanProposal`](../src/trama_platform/contracts.py) y el runtime ya validan
que requisito, organización, proyecto, fases y tareas correspondan entre sí y
requieren un aprobador para ejecutar el plan ([flujo](ARQUITECTURA.md)). Sin
embargo, `pyproject.toml` no declara DSPy y `trama model list` informa que aún
no hay un `ModelGatewayPort` configurado. Por eso el ejemplo de abajo es para
un experimento local aislado; no conecta DSPy al flujo de producción.

## Piloto local

Usa el entorno Python propio de TRAMA y fija la versión principal del paquete:

```powershell
uv pip install --python .venv/Scripts/python.exe "dspy==3.4.0"
```

Esta instalación de laboratorio no cambia `pyproject.toml` ni `uv.lock`, así
que no fija las dependencias transitivas. No añadas DSPy a las dependencias base
hasta que una evaluación demuestre una mejora útil. Si se adopta en un servicio,
decláralo como extra opcional y vuelve a generar el lock.

DSPy puede llamar el endpoint compatible con OpenAI de Colibri. Este ejemplo
usa `TramaSettings` y es únicamente para una ejecución de laboratorio; al llamar
directamente al proveedor, omite el control de producción del Model Gateway.

```python
import dspy

from trama_platform.settings import TramaSettings

settings = TramaSettings.from_env()
lm = dspy.LM(
    f"openai/{settings.colibri_model}",
    api_base=f"{settings.colibri_url.rstrip('/')}/v1",
    api_key="local",
    engine="litellm",
)
dspy.configure(lm=lm)


class DraftPlan(dspy.Signature):
    """Propón un borrador basado solo en el requisito y contexto entregados."""

    requirement: str = dspy.InputField()
    context: str = dspy.InputField()
    phase_drafts: list[str] = dspy.OutputField()
    task_drafts: list[str] = dspy.OutputField()
    dependency_proposals: list[str] = dspy.OutputField()
    acceptance_criteria: list[str] = dspy.OutputField()
    open_questions: list[str] = dspy.OutputField()


draft_plan = dspy.Predict(DraftPlan)
draft = draft_plan(requirement="...", context="...")
```

La salida es texto de trabajo, no un `PlanProposal` listo para registrar. El
adaptador de aplicación debe convertir y validar el borrador, crear las fases y
tareas con sus IDs, y completar `organization_id`, `project_id`, `requirement_id`
y `correlation_id` desde el contexto confiable de TRAMA. No tomes esos valores
del texto generado por el modelo.

`dspy.configure` deja un modelo global para el proceso y aquí se usa por
simplicidad en una ejecución local de un solo perfil. En un servicio concurrente
con perfiles distintos por solicitud, selecciona el modelo con `dspy.context`
por invocación y no cambies la configuración global entre tenants.

## Evaluación y optimización

Antes de optimizar, conserva una línea base y arma conjuntos separados de
ejemplos revisados para entrenamiento, validación y prueba. Si se comparan
varios proyectos, separa los ejemplos por proyecto y organización para evitar
mezclar datos entre tenants.

La métrica debe comprobar, como mínimo:

- que la salida respete los campos y límites del borrador esperado;
- que las tareas tengan objetivos y criterios accionables;
- que las dependencias formen un grafo válido y sin ciclos;
- que los vacíos de contexto aparezcan como preguntas, no como hechos inventados;
- que la revisión humana valore el plan como completo y ejecutable.

Usa validaciones deterministas para contrato y alcance; la revisión semántica
puede añadir una rúbrica humana o un juez de modelo, pero no debe ser la única
medida. Ejecuta `dspy.Evaluate` sobre el conjunto de prueba y compara la
puntuación contra la línea base. Para un candidato inicial, prueba `dspy.GEPA`
con un `max_metric_calls` explícito y una métrica que devuelva
`dspy.Prediction(score=..., feedback=...)` con comentarios concretos para cada
error. GEPA llama varias veces al modelo: ejecuta
la optimización fuera de las solicitudes de usuario y controla su presupuesto.

Guarda únicamente el estado JSON del programa (`save_program=False`) y carga ese
estado sobre la misma definición Python. Los ejemplos optimizados pueden quedar
incluidos en el artefacto; trátalo como dato del proyecto, mantenlo fuera de Git
y almacénalo solo en una ubicación con permisos acordes a su organización.
Evita los formatos pickle y cargar programas serializados de fuentes no
confiables.

## Límites para una integración futura

- No permitir que DSPy apruebe planes, despache tareas, escriba conocimiento
  canónico o invoque herramientas con autoridad propia.
- Mantener aprobación manual y el linaje requisito → fase → tarea, con un
  `correlation_id` común.
- Mantener la identidad de organización y proyecto en el contexto autenticado;
  validar todo antes de persistir y volver a validar el namespace en el runtime.
- No enviar secretos, `.env`, credenciales ni contexto de otro proyecto al
  modelo o al conjunto de optimización.
- No conectar el programa directamente desde el Gateway Go. Una integración
  requiere un servicio Python acotado que use la ruta aprobada del Model Gateway
  y conserve la redacción, auditoría y referencias de salida de TRAMA.
- No esperar que el programa optimizado modifique el prompt de Hermes: Hermes
  es externo. Para usar DSPy en ejecución, habrá que exponer explícitamente el
  módulo Python al flujo API/MCP y conservar el paso de aprobación actual.

## Cuándo promover el piloto

Promuévelo solo si mejora resultados en ejemplos de prueba no vistos durante
la optimización, mantiene los límites por tenant y su costo/latencia son
aceptables. Si no hay ejemplos revisados o una métrica útil, mantén la generación
actual y no incorpores la dependencia.

## Referencias

- [Código y documentación de DSPy](https://github.com/stanfordnlp/dspy)
- [Modelos locales y endpoints compatibles](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/learn/programming/language_models.md)
- [Módulos](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/learn/programming/modules.md)
- [Métricas y evaluación](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/diving-deeper/metrics-and-evaluation.md)
- [Optimizadores y métricas](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/learn/optimization/optimizers.md)
- [Guardar y cargar programas](https://github.com/stanfordnlp/dspy/blob/main/docs/docs/tutorials/saving/index.md)
- [Versión 3.4.0 y notas de migración](https://github.com/stanfordnlp/dspy/releases)
- [Paquete, licencia y versiones de Python](https://pypi.org/project/dspy/)
