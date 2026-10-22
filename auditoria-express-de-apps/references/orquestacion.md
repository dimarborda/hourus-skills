# Orquestación de los equipos de agentes

Cómo repartir la auditoría entre subagentes sin perder calidad. El agente
principal (tú) prepara, lanza, verifica y consolida; los subagentes solo
leen y escriben su archivo de hallazgos.

## Profundidad

| Profundidad | Agentes | Cuándo |
|---|---|---|
| **Rápida** | A (código completo), B (Vercel + Supabase), C (navegador completo); + D si es la primera auditoría o cambió el equipo | Cierre de cada etapa, re-verificación tras corregir |
| **Completa** | A1, A2, A3, A4, B1, B2, C1, C2, D1, D2 | Antes de producción, antes de pagos o datos sensibles, tras un incidente |

Más de 10 agentes rara vez encuentra más: duplica hallazgos y gasta tokens.
El equipo D pregunta más de lo que ejecuta: sus preguntas al dueño se
juntan en **un solo bloque** (máximo 3, de sí/no) que haces tú, no el
subagente; el subagente recibe las respuestas en el brief.
Si el proyecto es pequeño (< 30 archivos de código), la rápida basta.

## Cómo lanzarlos

1. Corre `auditar.py iniciar` y `auditar.py escanear` antes de lanzar nada:
   el barrido estático es el punto de partida común.
2. Lanza **todos** los agentes en **un solo mensaje** (varias llamadas a la
   herramienta de subagentes en paralelo). Los equipos no dependen entre sí.
3. Si tu entorno ofrece flujos multiagente (p. ej. un *Workflow*), úsalos
   solo si el usuario lo pidió explícitamente; si no, subagentes simples.
4. Sin subagentes: hazlo tú, equipo por equipo, con las mismas listas.
5. Mientras corren, no repitas su trabajo: espera sus resultados.

## Plantilla del encargo (brief) de cada subagente

El subagente no ve esta conversación: todo lo que necesita va en el brief.
Dale los datos, **no tu conclusión** (un agente al que le das una hipótesis
tiende a confirmarla).

```
Eres el agente <ID> (<nombre>) de una auditoría de solo lectura.

Proyecto: <RUTA absoluta>  ·  Auditoría: docs/auditoria/<FECHA>/
Stack: Next.js App Router + Supabase + Vercel (método diseno-express-de-apps).
URL autorizadas por el dueño: <lista o "ninguna">  ·  Entorno: <local|preview|producción>
Cuentas de prueba: <"ninguna" o dónde están (archivo de seed); nunca las escribas en el informe>

Lee y sigue tu lista de verificación: <SKILL_DIR>/references/<guía>.md, sección <ID>.
Esquema de hallazgos: <SKILL_DIR>/references/clasificacion.md.
Barrido estático previo (no lo repitas; confírmalo o descártalo si cae en tu área):
<pega aquí el resumen de `auditar.py escanear`: regla, archivo, severidad>

Reglas:
- Solo lectura: no edites archivos, no ejecutes migraciones, no cambies variables ni despliegues.
- No muestres secretos: enmascara (4 primeros + "…" + 2 últimos, y la longitud).
- Solo las URL autorizadas; nada de carga, fuerza bruta ni fuzzing.
- Cada hallazgo con evidencia reproducible (archivo:línea, comando o petición).
- Si no puedes verificar algo (sin sesión en el CLI, sin navegador), regístralo como
  hallazgo de severidad "info" con lo que faltó, y sigue.

Entrega: escribe docs/auditoria/<FECHA>/hallazgos-<id-en-minúsculas>.json
(una lista JSON con el esquema) y responde solo con: número de hallazgos por severidad
y los títulos de los críticos y altos.
```

## Contrato de salida

- Un archivo por agente: `hallazgos-a1.json`, `hallazgos-b2.json`,
  `hallazgos-c.json`… (en la rápida: `hallazgos-a.json`, `-b`, `-c`).
- IDs con el prefijo del agente: `A2-003`, `C1-001`.
- `auditar.py consolidar` rechaza archivos con campos faltantes o valores
  fuera del esquema: corrígelos (o pide al agente que lo haga) y repite.

## Verificación adversarial

Tras `consolidar`, por cada hallazgo `critica` o `alta` que no esté
`confirmado`:

```
Intenta refutar este hallazgo de una auditoría de solo lectura. No asumas que es real.
<título, evidencia, escenario>
Busca en <RUTA> lo que lo invalide (una política RLS en otra migración, una verificación
de sesión en el layout, la variable no existe en Vercel…). Responde con
VEREDICTO: confirmado | descartado | sin-cambio, y la evidencia.
```

Usa un agente distinto del que lo encontró. Actualiza `confianza` y
`estado` en el JSON de origen y vuelve a consolidar.

## Presupuesto y orden

- La auditoría completa toma 10 agentes + 1-3 verificadores. Díselo al
  usuario antes de lanzarla si su plan tiene límites de uso.
- Si un crítico confirmado aparece temprano (p. ej. `service_role` en el
  bundle), avísale al usuario en ese momento: rotar la llave no espera al
  informe.
