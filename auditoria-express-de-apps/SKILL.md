---
name: auditoria-express-de-apps
description: Audita una aplicación construida con el método diseno-express-de-apps (Next.js + Supabase + Vercel) con cuatro equipos de agentes en paralelo — uno lee el código (secretos también en el historial de git, RLS, Realtime, Storage, autenticación, entradas, abuso y costos, lógica de negocio, metodología y buenas prácticas), otro verifica el despliegue con Vercel CLI y Supabase CLI en modo solo lectura, otro recorre la interfaz y las peticiones del navegador, y otro revisa cuentas (2FA, miembros, tokens), operación (copias, monitoreo, dominio, incidentes) y los permisos del propio agente — para encontrar secretos expuestos, accesos indebidos a datos y violaciones de las reglas de los proveedores de nube. Clasifica los hallazgos por severidad y confianza, propone los cambios, los convierte en casos de uso de endurecimiento para docs/05-casos-de-uso.md alimenta las lecciones aprendidas del proyecto y del método, y genera pruebas pgTAP de RLS, un workflow de GitHub Actions y Dependabot para que esas lecciones se cumplan solas. Úsala cuando alguien diga "audita mi app", "revisa la seguridad de la plataforma", "¿estoy exponiendo secretos?", "revisa el despliegue en Vercel/Supabase", "revisa las políticas RLS", "auditoría antes de salir a producción", "cierre de etapa", "configura CI de seguridad", "pruebas de RLS", "se filtró una llave", "buenas prácticas del proyecto" o "qué aprendimos de este proyecto", aunque no mencione agentes ni la palabra auditoría.
---

# Auditoría express de apps

Revisa una app hecha con [`diseno-express-de-apps`](../diseno-express-de-apps/SKILL.md)
desde cuatro ángulos a la vez — **lo que dice el código, lo que está
desplegado, lo que ve el navegador y quién controla las cuentas** — porque cada uno esconde fallas que
los otros no ven: una política RLS correcta en la migración que nunca se
aplicó, una variable `NEXT_PUBLIC_` inocente en el código que en Vercel
contiene la `service_role`, un endpoint protegido que devuelve columnas de
más, una cuenta de Supabase sin 2FA. Termina en cambios concretos, casos de uso y lecciones que el proyecto
lee en cada sesión.

`SKILL_DIR` = carpeta de este archivo. Script: `SKILL_DIR/scripts/auditar.py`
(Python 3, sin dependencias). `RUTA` = raíz del proyecto auditado.

## Reglas fijas (no se negocian)

- **Solo lectura.** Ningún agente modifica código, base de datos, variables
  de entorno ni despliegues durante la auditoría. Los cambios se proponen y
  se aplican después, **con aprobación del dueño**, uno por caso de uso.
- **Solo lo propio.** Se audita el proyecto del usuario, en las URL que él
  indique (local, preview o producción que él nombre). Nada de terceros,
  nada de pruebas de carga, fuerza bruta, fuzzing masivo ni evasión de
  protecciones. Ver [references/restricciones-proveedores.md](references/restricciones-proveedores.md).
- **Los secretos no se copian.** Si aparece un secreto se registra
  **enmascarado** (`sk_l…9X`, longitud y ubicación), nunca completo: ni en
  el chat, ni en `docs/`, ni en el resumen de un subagente. Nunca uses
  `vercel env pull` ni leas `.env*` para mostrar valores; para saber *qué*
  variables hay basta con los nombres.
- **Credenciales de prueba solo en entornos de prueba** (local o un
  `staging`/`preview` que el usuario nombre), con cuentas de prueba del
  propio proyecto. Nunca contraseñas reales del usuario.
- **Un secreto expuesto se rota, no solo se borra**: borrar el archivo no lo
  saca del historial de git ni de los despliegues anteriores. Dile al
  usuario qué rotar y dónde; la rotación la hace él.

## 0. Preparar

```bash
python3 SKILL_DIR/scripts/auditar.py iniciar --proyecto RUTA
```

Crea `docs/auditoria/AAAA-MM-DD/plan.md`, `docs/06-lecciones-aprendidas.md`
(si no existe) y añade al `CLAUDE.md` del proyecto la regla de leer las
lecciones antes de cada etapa. No sobrescribe nada.

Llena el `plan.md` con el usuario — **máximo 3 preguntas**, propone tú las
respuestas: (1) qué URL se revisan (local / preview / producción) y si hay
cuentas de prueba; (2) si el CLI de Vercel y el de Supabase tienen sesión
iniciada y el proyecto vinculado (si no, pídele que haga `vercel login` /
`npx supabase login`; tú no escribes credenciales); (3) profundidad:
**rápida** (3 agentes: A, B y C; más D en la primera auditoría o si cambió
el equipo) o **completa** (10 agentes, por defecto antes de producción). Si el repositorio es público, añade
`docs/auditoria/` a `.gitignore`: los informes describen vulnerabilidades.

Luego el barrido determinístico, que es la base de todos los equipos:

```bash
python3 SKILL_DIR/scripts/auditar.py escanear --proyecto RUTA [--incluir-build]
```

Busca secretos por patrón (y decodifica JWT para distinguir `anon` de
`service_role`), `.env` versionados o no ignorados, `NEXT_PUBLIC_` con
nombre de secreto, tablas sin RLS o con RLS en otra migración, políticas
`using (true)`, `user_metadata` en políticas, funciones `security definer`
sin `search_path`, `getSession()` en el servidor, Server Actions sin
verificación de sesión visible, webhooks sin verificación de firma, source
maps públicos, canales Realtime públicos, subidas sin validar, endpoints de
IA o correo sin límite de tasa, permisos amplios del agente
(`.claude/settings*.json`), tokens en `.mcp.json`, falta de CI, pruebas de
RLS, Dependabot o procedimiento de incidentes, y la estructura del método.
También busca secretos en el **contenido de todos los commits** (los que ya
no están en los archivos actuales; `--sin-historial` lo omite).
`--incluir-build` revisa `.next/static` (lo que de verdad descarga el
navegador; requiere `npm run build` previo). Escribe `hallazgos-estatico.json`.

## 1. Los cuatro equipos (en paralelo)

Roster, prompts, contrato de salida y cómo lanzarlos en
[references/orquestacion.md](references/orquestacion.md). Resumen:

| Equipo | Agentes (completa) | Mira | Guía |
|---|---|---|---|
| **A · Código** | A1 secretos y configuración · A2 datos y RLS · A3 autenticación, servidor y entradas · A4 metodología y buenas prácticas | Repositorio, migraciones, `docs/` | [equipo-codigo.md](references/equipo-codigo.md) |
| **B · Despliegue** | B1 Vercel CLI · B2 Supabase CLI | Lo que está publicado y configurado, y su diferencia con el repo | [equipo-despliegue.md](references/equipo-despliegue.md) |
| **C · Navegador** | C1 interfaz, cabeceras y peticiones · C2 acceso a datos desde fuera | La URL real, la red, el bundle y la API de Supabase con la clave pública | [equipo-navegador.md](references/equipo-navegador.md) |
| **D · Cuentas y operación** | D1 cuentas y accesos · D2 operación, continuidad y dominio (D3, seguridad del agente, lo hace D2) | 2FA, miembros, tokens, copias, monitoreo, DNS, incidentes, permisos y conectores del agente | [equipo-cuentas-operacion.md](references/equipo-cuentas-operacion.md) |

- Lanza todos los agentes de la profundidad elegida **en un solo mensaje**
  para que corran a la vez. Cada uno recibe la ruta, la fecha de la
  auditoría, su lista de verificación y el resumen de `hallazgos-estatico.json`
  — no tu hipótesis — y escribe `docs/auditoria/FECHA/hallazgos-<agente>.json`.
- Sin herramienta de subagentes, haz los equipos tú en orden A → B → C → D.
- El equipo D depende sobre todo de **respuestas del dueño** (paneles que
  solo él ve): junta sus preguntas en un solo bloque de máximo 3, de sí/no.
- Sin navegador, C1 se reduce a `curl -sI` y al barrido de `.next/static`;
  sin sesión en un CLI, el agente B lo reporta como hallazgo `info` y sigue.

## 2. Verificar y clasificar

```bash
python3 SKILL_DIR/scripts/auditar.py consolidar --proyecto RUTA
```

Valida cada JSON contra el esquema, fusiona duplicados entre equipos (el
mismo problema visto por dos equipos sube un nivel de confianza), compara
con la auditoría anterior y con las lecciones — **nuevo**, **persistente**
(sigue abierto; hereda el `aceptado` del dueño), **reincidente** (se había
corregido o ya era lección y volvió: sube un nivel de severidad) y **no
reaparece** — y genera `hallazgos.json` e `informe.md`.

Antes de mostrar nada: **verificación adversarial** de todo hallazgo
`critica` o `alta` que no esté `confirmado` — un agente distinto (o tú, si
no hay subagentes) intenta refutarlo con evidencia; si lo logra, `estado:
descartado` con el motivo; si lo reproduce, `confianza: confirmado`. Vuelve
a correr `consolidar`.

Escala, categorías, OWASP y esquema en
[references/clasificacion.md](references/clasificacion.md). En una frase:
**severidad** = qué tan grave si se explota; **confianza** = qué tan
seguros estamos de que existe; un hallazgo `critica` + `confirmado` se le
cuenta al usuario **de inmediato**, sin esperar al informe.

## 3. Proponer cambios

Por cada hallazgo abierto (de mayor a menor severidad) el informe trae:
qué pasa, cómo se explotaría (en lenguaje llano), el **cambio propuesto**
(diff o pasos concretos: migración SQL, mover una llave al servidor, una
cabecera, una regla en `vercel.json`) y su esfuerzo en puntos Fibonacci.

Presenta al usuario un resumen de una pantalla: cuántos hallazgos por
severidad, los críticos y altos con su cambio, qué tiene que hacer **él**
(rotar llaves, activar Deployment Protection, aceptar un riesgo) y tu
recomendación. Él decide qué se corrige ya, qué se agenda y qué riesgo se
acepta (`estado: aceptado`, con su motivo).

## 4. Casos de uso de endurecimiento

```bash
python3 SKILL_DIR/scripts/auditar.py casos --proyecto RUTA [--anexar]
```

Convierte los hallazgos abiertos en casos con el formato de
`docs/05-casos-de-uso.md`: `UC-SEC-nn` (seguridad, proveedor, secretos) y
`UC-CAL-nn` (buenas prácticas, metodología), prioridad por severidad,
puntos por esfuerzo, ficha completa para los 🟥 con el criterio de
aceptación *"el hallazgo X ya no se reproduce"*. Van en una etapa nueva
**`E<n> · Endurecimiento (auditoría FECHA)`**: los 🟥 se construyen **antes
de seguir con la etapa en curso**, aunque el número sea mayor. `--anexar`
la agrega a `docs/05` (si no estaba); después corre
`python3 ../diseno-express-de-apps/scripts/expres.py validar --proyecto RUTA`.

Los hallazgos con `alcance: metodo` (el problema nace de la plantilla, la
guía o el checklist, no de este proyecto) salen como `UC-MET-nn` en
`casos-metodo.md`: son mejoras propuestas a `diseno-express-de-apps` y a
esta skill. Muéstraselas al usuario; aplicarlas en el repositorio de
skills es otra tarea y requiere su aprobación.

Corrección: sigue el bucle normal de construcción (rama `etapa-eN`, un caso
a la vez, `npm run build`, preview). Al terminar cada caso, vuelve a
ejecutar la prueba que lo encontró. Cierra con una **auditoría rápida** de
re-verificación.

## 5. Que las lecciones se cumplan solas (automatizar)

```bash
python3 SKILL_DIR/scripts/auditar.py automatizar --proyecto RUTA [--publicas t1,t2]   # vista previa
python3 SKILL_DIR/scripts/auditar.py automatizar --proyecto RUTA --escribir
```

Una lección que solo vive en un documento depende de que alguien la lea.
`automatizar` crea, sin sobrescribir lo que el usuario ya tenga:

- `supabase/tests/00_auditoria_rls.test.sql` (pgTAP): todas las tablas con
  RLS, `search_path` fijo, vistas con `security_invoker` — pruebas que
  cubren también las tablas **futuras** — y, por tabla, que ni `anon` ni un
  usuario ajeno vean filas (`--publicas` excluye catálogos públicos; se
  recuerda entre ejecuciones). Las de acceso solo valen si `supabase/seed.sql`
  inserta datos. Escribe tú, con el usuario, `01_aislamiento.test.sql`
  (A no ve lo de B) desde la columna "qué NO puede hacer" de `docs/05`.
- `.github/workflows/auditoria.yml`: en cada PR corre `escanear --ci` (falla
  con críticos/altos no `aceptado`), `npm audit` y `supabase test db`.
- `.github/dependabot.yml`, `docs/incidentes/llave-filtrada.md` (qué rotar
  y en qué orden) y una copia del script en `scripts/auditoria/`.

Propónlo al cerrar la primera auditoría y conviértelo en caso de uso si el
usuario lo aprueba; empujar el workflow es un cambio como cualquier otro
(rama, PR, aprobación del dueño).

## 6. Lecciones aprendidas (retroalimentación)

```bash
python3 SKILL_DIR/scripts/auditar.py lecciones --proyecto RUTA
```

Pasa el campo `leccion` de cada hallazgo no descartado a
`docs/06-lecciones-aprendidas.md` (sin duplicar; las que se repiten suman
reincidencias). Ese archivo lo lee el agente al empezar cada etapa — así lo
dice el `CLAUDE.md` del proyecto — para que el mismo error no se cometa
dos veces. Una lección buena es una **regla verificable** ("toda tabla nueva
lleva `enable row level security` en la misma migración"), no un lamento.

Si una lección vale para cualquier proyecto del método, propón llevarla a
[references/lecciones-aprendidas.md](references/lecciones-aprendidas.md) de
esta skill o a la guía correspondiente de `diseno-express-de-apps`.

`auditar.py estado --proyecto RUTA` resume el historial de auditorías y lo
que sigue abierto (útil al retomar una sesión).

## 7. Reporte al usuario

Sin jerga y en este orden: lo urgente (críticos, qué rotar), cuántos
hallazgos por severidad y qué cambió desde la auditoría anterior, qué se
convirtió en casos de uso y en qué etapa, qué lecciones nuevas quedaron y
el siguiente paso recomendado. Enlaza `docs/auditoria/FECHA/informe.md`.

## Cuándo usarla dentro del método

- Al **cerrar cada etapa** de `diseno-express-de-apps`, antes del merge a
  `main`: auditoría rápida.
- **Antes de la primera salida a producción** y antes de activar pagos o
  datos sensibles: auditoría completa.
- Cuando cambie el plan de Vercel/Supabase, se agregue un proveedor (pagos,
  correo, IA) o aparezca un incidente.

Lo que esta skill aprendió auditando proyectos reales está en
[references/lecciones-aprendidas.md](references/lecciones-aprendidas.md);
léelo antes de lanzar los equipos.
