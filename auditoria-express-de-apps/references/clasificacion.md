# Clasificación de hallazgos

Todos los equipos escriben con el mismo esquema para que `auditar.py
consolidar` pueda fusionar, comparar con auditorías anteriores y generar
casos de uso y lecciones.

## Esquema (`hallazgos-<agente>.json` = lista de objetos)

```json
{
  "id": "A2-003",
  "equipo": "A2",
  "categoria": "rls",
  "severidad": "critica",
  "confianza": "confirmado",
  "estado": "abierto",
  "alcance": "proyecto",
  "titulo": "La tabla pagos no tiene RLS",
  "evidencia": {
    "archivo": "supabase/migrations/20260301_e2_pagos.sql",
    "linea": 4,
    "url": null,
    "comando": "curl … /rest/v1/pagos?select=*&limit=1 → 200, 1 fila",
    "extracto": "create table public.pagos ("
  },
  "impacto": "Cualquiera con la clave pública lee y modifica los pagos de todos los clientes.",
  "escenario": "Copiar la clave anon del bundle y pedir /rest/v1/pagos.",
  "propuesta": "Nueva migración: alter table public.pagos enable row level security; + políticas por organización (ver diff).",
  "esfuerzo": 3,
  "referencia": "OWASP A01:2021",
  "leccion": "Toda tabla nueva lleva enable row level security en la misma migración que la crea.",
  "relacionados": ["EST-002", "C2-001"]
}
```

Obligatorios: `id`, `equipo`, `categoria`, `severidad`, `confianza`,
`titulo`, `evidencia` (con al menos uno de `archivo`, `url`, `comando`) y
`propuesta`. Por defecto `estado: abierto`, `alcance: proyecto`.
`consolidar` agrega `huella`/`huellas` (para seguir el hallazgo entre
auditorías), `equipos`, `fusionados` e `historial` (`nuevo` /
`persistente` / `reincidente`). Opcionales útiles: `clave` (distingue dos
hallazgos de la misma regla en el mismo archivo, p. ej. el nombre de la
tabla), `nota` (motivo de un `descartado` o `aceptado`).

Para cambiar el estado de un hallazgo (descartado tras verificar, riesgo
aceptado por el dueño), edita el `hallazgos-<agente>.json` de origen y
vuelve a consolidar; un `aceptado` se hereda en la siguiente auditoría.

## Severidad (qué tan grave si se explota)

| Nivel | Criterio | Ejemplos | Qué se hace |
|---|---|---|---|
| `critica` | Cualquiera, sin cuenta, accede a datos o dinero de otros, o toma el control | `service_role` en el bundle; tabla sin RLS con datos; `.env` con secretos en el historial de un repo público | Avisar ya; rotar; corregir antes de cualquier otra cosa |
| `alta` | Un usuario con cuenta accede a lo ajeno, o un secreto queda a un paso | IDOR en una Server Action; `using (true)` en tabla privada; webhook sin firma; `user_metadata` en una política | Caso 🟥 en la etapa de endurecimiento |
| `media` | Debilidad que facilita un ataque o incumple una regla del proveedor | Sin CSP; previews sin protección; `getSession()` en el servidor; plan Hobby con uso comercial | Caso 🟨 |
| `baja` | Higiene, defensa en profundidad | `auth.uid()` sin `select`; falta `server-only`; logs ruidosos | Caso 🟩 |
| `info` | Contexto o algo que no se pudo verificar | CLI sin sesión; no hay cuentas de prueba | No genera caso; se anota en el informe |

Ajustes: **reincidente** (estaba `corregido` en la auditoría anterior, o
repite la regla o la huella de una lección registrada en
`docs/06-lecciones-aprendidas.md`) → `consolidar` sube un nivel, salvo a
los `posible`. Un hallazgo **persistente** (seguía abierto desde la
anterior) no sube: se cuenta aparte. Afecta solo a **local** y nunca a
un despliegue → baja un nivel. Datos personales sensibles o dinero → nunca
por debajo de `alta` si hay acceso indebido.

## Confianza (qué tan seguros estamos de que existe)

| Nivel | Significa |
|---|---|
| `confirmado` | Reproducido (petición, comando o lectura directa del despliegue) |
| `probable` | Leído en el código o la configuración, sin reproducir |
| `posible` | Patrón sospechoso; requiere revisión humana (típico del barrido estático) |

Los `posible` no generan casos de uso salvo con `casos --incluir-posibles`.

## Estado

`abierto` · `descartado` (falso positivo; motivo en `nota`) · `aceptado`
(el dueño acepta el riesgo; motivo y fecha en `nota`) · `corregido`
(verificado en una auditoría posterior).

## Categorías

| Categoría | Cubre | Caso |
|---|---|---|
| `secretos` | Llaves, tokens, contraseñas, `.env` | UC-SEC |
| `rls` | Políticas, acceso a datos, Storage, vistas, funciones | UC-SEC |
| `auth` | Sesión, autorización por recurso, IDOR, roles | UC-SEC |
| `entradas` | Validación, XSS, inyección, open redirect, SSRF, webhooks | UC-SEC |
| `configuracion` | `next.config`, `vercel.json`, cabeceras, source maps | UC-SEC |
| `despliegue` | Diferencias repo ↔ Vercel/Supabase, variables, protección de previews | UC-SEC |
| `navegador` | Bundle, red, cookies, respuestas con datos de más | UC-SEC |
| `abuso` | Límites de tasa, costos disparables, subidas sin tope | UC-SEC |
| `proveedor` | Reglas y límites de Vercel, Supabase, pasarelas, IA | UC-SEC |
| `dependencias` | `npm audit`, paquetes abandonados | UC-SEC |
| `privacidad` | Datos personales, consentimiento, residencia | UC-SEC |
| `cuentas` | 2FA, miembros, tokens, recuperación de cuentas de los proveedores | UC-SEC |
| `agente` | Permisos, conectores MCP y automatizaciones del agente que construye | UC-SEC |
| `metodologia` | Desviaciones del método diseno-express-de-apps | UC-CAL |
| `buenas-practicas` | Calidad, errores, tipos, pruebas | UC-CAL |
| `rendimiento` | Políticas lentas, consultas sin índice, bundle pesado | UC-CAL |
| `operacion` | Copias y restauración, monitoreo, alertas, incidentes, dominio | UC-CAL |
| `accesibilidad` | Nombres accesibles, contraste, teclado | UC-CAL |

Con `alcance: metodo`, cualquier categoría va a `UC-MET` (mejora a la skill).

## Referencias OWASP Top 10 (2021) más frecuentes en este stack

A01 Control de acceso roto (RLS, IDOR) · A02 Fallas criptográficas
(secretos expuestos) · A03 Inyección (incluye XSS) · A04 Diseño inseguro
(dinero sin idempotencia) · A05 Configuración insegura (cabeceras, previews
abiertas) · A06 Componentes vulnerables · A07 Fallas de autenticación
(`getSession()` en servidor) · A08 Integridad (webhooks sin firma) · A09
Registro y monitoreo (sin bitácora) · A10 SSRF.

## Esfuerzo

Puntos Fibonacci (1, 2, 3, 5, 8, 13), como en `docs/05`. Si un cambio da
más de 13, descompón la propuesta en varios hallazgos o pasos.

## La lección

Cada hallazgo propone una `leccion`: una regla corta, verificable y
general para el proyecto, redactada para que el agente la cumpla en la
próxima etapa. Mal: "faltó RLS". Bien: "Toda tabla nueva lleva `enable row
level security` en la misma migración que la crea".
