# Construcción con Next.js + Supabase + Vercel

Guía para que el agente construya la app con un usuario que no programa.
El usuario solo crea cuentas, inicia sesión cuando el CLI lo pida y aprueba
cada etapa. Todo lo demás lo hace el agente y lo explica en una frase.

Si tu entorno tiene skills de Vercel/Next.js/shadcn/Supabase, úsalas para
el detalle de cada herramienta; esta guía fija el orden y las convenciones.

## Cuentas que necesita el usuario (gratuitas para empezar)

1. **GitHub** — guarda el código. 2. **Supabase** — base de datos y login.
3. **Vercel** — publica la app (entrar con GitHub simplifica todo).

Pídele que las cree él; nunca escribas contraseñas por él.

## E0 · Día uno: app desplegada con login

```bash
npx create-next-app@latest NOMBRE --ts --tailwind --eslint --app --src-dir --import-alias "@/*" --use-npm
cd NOMBRE
npx shadcn@latest init
npx shadcn@latest add button card input label form table badge dialog dropdown-menu sonner
npm install @supabase/supabase-js @supabase/ssr
```

Luego:
1. Copia los tokens de `docs/03-diseno-visual.md` a `src/app/globals.css`
   (variables de shadcn) y la tipografía a `layout.tsx` con `next/font`.
2. Repositorio: `git init` (si hace falta), primer commit y
   `gh repo create NOMBRE --private --source . --push`.
3. Supabase: el usuario crea el proyecto (región más cercana a sus
   usuarios, p. ej. `sa-east-1` para Sudamérica) — o, más simple, se crea
   desde Vercel Marketplace (integración Supabase), que deja las variables
   de entorno conectadas solas.
4. Vercel: `vercel login`, `vercel link`, conecta el repo de GitHub
   (dashboard o `vercel git connect`) y `vercel env pull .env.local`.
5. Clientes de Supabase en `src/lib/supabase/` (`client.ts` con
   `createBrowserClient`, `server.ts` con `createServerClient` y cookies) y
   refresco de sesión en `src/proxy.ts` (Next 16; en versiones anteriores
   `middleware.ts`). Sigue la guía oficial de `@supabase/ssr` para Next.js.
6. Login por correo (enlace mágico o contraseña) y página protegida.
7. En Supabase → Authentication → URL Configuration: agrega la URL de
   Vercel y `http://localhost:3000` como redirecciones permitidas (error
   más común: el enlace del correo vuelve a localhost).
8. Push a `main` → Vercel despliega. **Muestra la URL al usuario.**

## Base de datos: migraciones + RLS

Sin Docker ni Supabase local para usuarios no técnicos: trabaja contra el
proyecto de Supabase en la nube con el CLI.

```bash
npx supabase login
npx supabase init
npx supabase link --project-ref REF
npx supabase migration new e0_cimientos
# escribir SQL en supabase/migrations/<fecha>_e0_cimientos.sql
npx supabase db push
npx supabase gen types typescript --linked > src/lib/database.types.ts
```

Convenciones:
- Tablas en español, `snake_case`, plural; `id uuid default gen_random_uuid()`,
  `creado_en timestamptz default now()`, `creado_por uuid references auth.users`.
- `perfiles` (1:1 con `auth.users`, creado por trigger al registrarse),
  `organizaciones`/`equipos` y `membresias (usuario, contexto, rol)` si
  los roles dependen del contexto.
- **`alter table … enable row level security` en cada tabla, en la misma
  migración que la crea.** Políticas derivadas de la columna "qué NO puede
  hacer" de los actores. Funciones `security definer` tipo
  `tiene_rol(contexto_id, rol)` para no repetir lógica.
- `bitacora (actor, accion, entidad, entidad_id, antes jsonb, despues jsonb, fecha)`
  alimentada por triggers en tablas sensibles. Sin `update`/`delete` sobre ella.
- Estados como `text` con `check` o enum; transiciones validadas en el servidor.
- La `service_role key` solo en el servidor (Route Handlers, Server
  Actions, Edge Functions). Nunca con prefijo `NEXT_PUBLIC_`.

## Bucle por etapa

Para cada etapa de `docs/05-casos-de-uso.md`:

1. Lista los casos de la etapa por prioridad (🟥 → 🟨 → 🟩) y explícale al
   usuario qué vas a construir hoy.
2. Por cada caso: migración (si cambia datos) → Server Actions / Route
   Handlers → pantallas (según `03-diseno-visual.md`) → prueba manual del
   criterio de aceptación → marca 🔄 y luego ✅.
3. `npm run build` sin errores antes de cada push (Vercel fallaría igual).
4. Trabaja en una rama `etapa-eN`; Vercel crea una URL de preview por
   push. Comparte esa URL al cerrar cada bloque de casos.
5. Al cerrar la etapa: demuestra el **criterio de salida** en la preview;
   si el usuario lo aprueba, merge a `main` (producción) **solo con su
   confirmación**.
6. `expres.py estado` para el resumen.

## Servicios frecuentes dentro del stack

| Necesidad | Solución recomendada |
|---|---|
| Archivos/adjuntos | Supabase Storage con políticas por bucket |
| Tiempo real (tablero, votación en vivo) | Supabase Realtime |
| Tareas programadas (cortes semanales, alertas) | Vercel Cron → Route Handler, o `pg_cron` |
| Correo transaccional | Resend (o SMTP propio en Supabase Auth) |
| IA (redacción, resúmenes) | AI SDK + API de Claude; la IA propone, un humano aprueba |
| Pagos | Pasarela autorizada (Stripe; en Colombia/LatAm Mercado Pago o Wompi). Checkout alojado + webhook → tabla `transacciones`; webhooks idempotentes y verificados por firma |
| Exportar PDF/Word | Generación en servidor desde los datos |
| Métricas de uso | Vercel Analytics |

## Explicar al usuario

Una línea por acción, sin jerga: "Creé la tabla de equipos y una regla
para que cada persona solo vea los equipos donde está". Si algo falla,
explica qué pasó y qué vas a intentar; no le pidas que depure.
