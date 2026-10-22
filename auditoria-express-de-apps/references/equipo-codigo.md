# Equipo A · Código

Lee el repositorio sin ejecutar nada que lo modifique. En la auditoría
rápida un solo agente (A) cubre A1-A4; en la completa, uno por sección.

Comandos útiles (todos de solo lectura):

```bash
git ls-files | head -200                       # qué está versionado
git log --oneline -20                          # contexto de los cambios recientes
git log --all -p -S "service_role" --oneline   # ¿un secreto pasó por el historial?
grep -rn --include='*.ts' --include='*.tsx' "use server" src | head
npm audit --omit=dev --json                    # vulnerabilidades en dependencias de producción
npx tsc --noEmit                               # tipos (si no tarda demasiado)
```

## A1 · Secretos y configuración

- [ ] Ningún `.env*` versionado salvo `.env.example` (y este sin valores reales).
      Si alguno pasó por el historial (`git log --all -- .env.local`), es
      **crítico aunque ya no exista**: el valor hay que rotarlo.
- [ ] **Historial completo**: `auditar.py escanear` revisa el contenido de
      todos los commits (no solo los nombres de `.env`). Si están
      instalados, confírmalo con `gitleaks git --redact` o
      `trufflehog git file://. --only-verified` (no imprimen los valores con
      esas opciones). Un secreto en un commit viejo es **crítico**: se rota.
- [ ] `.gitignore` cubre `.env*`, `.vercel`, `supabase/.temp`, `supabase/.branches`.
- [ ] Ninguna variable `NEXT_PUBLIC_*` con nombre o valor de secreto. Solo
      son públicas: URL de Supabase, clave `anon`/`publishable`, claves
      públicas de pasarela (`pk_…`, `pub_…`) e IDs de analítica.
- [ ] La `service_role` / `sb_secret_…` solo se lee en archivos de servidor
      que importan `server-only` (Route Handlers, Server Actions, Edge Functions).
      Nunca en un archivo con `"use client"` ni en código compartido que un
      componente cliente pueda importar.
- [ ] Llaves de IA, correo, pasarela y webhooks: solo en servidor, con
      versión de prueba en preview y de producción solo en producción.
- [ ] `next.config.*`: sin `productionBrowserSourceMaps: true`, sin
      `ignoreBuildErrors` / `ignoreDuringBuilds`; `images.remotePatterns`
      acotado (no `hostname: '**'`).
- [ ] Logs: nada de `console.log` con tokens, sesiones, cuerpos de webhook
      completos ni datos personales.

## A2 · Datos y RLS (Supabase)

Lee **todas** las migraciones en orden (`supabase/migrations/*.sql`). Una
política vale por lo que queda al final, no por la primera versión.

- [ ] Cada tabla del esquema `public` tiene `enable row level security` en
      **la misma migración que la crea** (regla del método). Sin RLS, la
      clave pública — que está en el navegador — lee y escribe la tabla.
- [ ] Ningún `disable row level security`, ni "temporal".
- [ ] Hay políticas para cada operación que la app usa (select, insert,
      update, delete). RLS activado sin política = tabla bloqueada (falla
      funcional, no de seguridad: regístrala como `buenas-practicas`).
- [ ] Ninguna política `using (true)` / `with check (true)` salvo catálogos
      públicos explícitos y documentados en `04-conceptual.md`.
- [ ] `update`: la fila **nueva** también debe cumplir la regla. Si la
      política no tiene `with check`, Postgres reutiliza el `using`; si lo
      tiene, que no sea más permisivo (un `with check` flojo deja mover una
      fila a otra organización).
- [ ] Ninguna política usa `user_metadata` / `raw_user_meta_data`: el
      usuario puede editarlo. Los roles salen de `membresias` o de
      `app_metadata`.
- [ ] Funciones `security definer` con `set search_path = ''` (o un esquema
      fijo) y, si están en `public`, revisa que no sean invocables por
      `anon` vía RPC cuando no deben.
- [ ] Las políticas coinciden con la columna **"qué NO puede hacer"** de
      los actores en `docs/05-casos-de-uso.md`. Cada fila de esa columna
      debería poder señalarse en una política.
- [ ] `bitacora` sin políticas de `update`/`delete`.
- [ ] Storage: buckets privados por defecto; políticas sobre
      `storage.objects` que filtren por carpeta del usuario u organización.
- [ ] **Subidas de archivos**: el servidor (o la política del bucket)
      limita tipo MIME y tamaño; las rutas llevan el ID del usuario u
      organización (`{org_id}/{uuid}.ext`), no nombres adivinables; las URL
      firmadas vencen en minutos, no en días; nada de SVG/HTML subido por
      usuarios servido desde el dominio propio.
- [ ] **Realtime**: si la app usa canales (`.channel(`), los de broadcast y
      presence son privados (`private: true`) y hay políticas sobre
      `realtime.messages`; los cambios de tablas (`postgres_changes`)
      respetan RLS, pero solo si la tabla lo tiene.
- [ ] **Procesos internos**: `pg_cron`, `pg_net` y webhooks de base de
      datos no llevan llaves escritas en el SQL (van en Supabase Vault);
      `pg_net` solo llama URL fijas.
- [ ] **Auth**: inicios de sesión anónimos desactivados si el modelo no
      los pide; MFA disponible (y exigido) para administradores; cambiar el
      correo exige confirmar el nuevo y el viejo; tokens de invitación con
      vencimiento y de un solo uso.
- [ ] **Pruebas de RLS**: existen `supabase/tests/*.sql` (pgTAP) y cubren
      al menos "todas las tablas tienen RLS" y "A no ve lo de B". Si no
      existen, `auditar.py automatizar` genera la base.
- [ ] Vistas en `public`: con `security_invoker = true` (si no, saltan RLS).
- [ ] Rendimiento: `(select auth.uid())` en vez de `auth.uid()` directo e
      índices en las columnas que usan las políticas.

## A3 · Autenticación, servidor y entradas

- [ ] En el servidor la identidad sale de `supabase.auth.getUser()` (o
      `getClaims()`), no de `getSession()`, que no valida el token.
- [ ] Cada Server Action y Route Handler que lee o escribe datos privados
      verifica la sesión **dentro de sí mismo**. Una Server Action es un
      endpoint público aunque la página que la usa esté protegida; el
      `proxy.ts`/`middleware.ts` no basta como única barrera.
- [ ] Autorización por recurso: tras verificar sesión, se comprueba que el
      recurso pertenece al usuario/organización (IDOR). Si se usa el
      cliente con `service_role`, esa comprobación es **obligatoria**.
- [ ] Entradas validadas en el servidor (zod o equivalente); nada se
      confía al formulario.
- [ ] Sin SQL armado con cadenas; sin `eval`/`new Function`.
- [ ] `dangerouslySetInnerHTML` solo con HTML sanitizado.
- [ ] Redirecciones: `next`/`redirectTo` validados contra rutas propias
      (open redirect).
- [ ] `fetch` a URL que vienen del usuario: lista blanca (SSRF).
- [ ] Webhooks: verificación de firma con el secreto del proveedor sobre el
      cuerpo **crudo**, idempotencia por ID de evento y respuesta rápida.
- [ ] Rutas de Cron: exigen `Authorization: Bearer ${CRON_SECRET}`.
- [ ] IA: la llave nunca en el cliente; límite de uso por usuario; la
      salida del modelo no se ejecuta ni se inserta como HTML sin sanitizar;
      un humano aprueba lo que mueve dinero o reputación (RG-02 del método).
- [ ] **IA con herramientas**: si el modelo puede ejecutar acciones (tool
      calling), cada herramienta valida permisos del usuario que pidió, no
      del sistema; el contenido externo (documentos, correos, páginas) que
      entra al prompt se trata como no confiable (inyección de
      instrucciones); las acciones irreversibles piden confirmación humana.
- [ ] Callback de Auth (`/auth/callback`): `redirectTo` restringido y URL
      permitidas en Supabase que no incluyan comodines amplios.

### Abuso y costos

- [ ] Endpoints costosos (IA, envío de correo/SMS, generación de PDF,
      registro, recuperación de contraseña, búsquedas pesadas) con **límite
      de tasa por usuario e IP** (p. ej. `@upstash/ratelimit`, reglas de
      Vercel Firewall o una tabla de cuotas) y tope diario por usuario.
- [ ] Nada que un visitante sin sesión pueda disparar en bucle y que
      cueste dinero (correo de invitación, IA en una landing).
- [ ] Respuestas paginadas con límite máximo; ninguna consulta sin `limit`
      que crezca con los datos.
- [ ] Subidas con tamaño máximo (cuidan Storage y el ancho de banda).

### Lógica de negocio

- [ ] Transiciones de estado validadas en el servidor (o en la base con
      `check`/trigger): no se puede pasar de `borrador` a `pagado` desde el
      cliente.
- [ ] Operaciones de dinero o cupos **idempotentes** y sin condiciones de
      carrera: dos clics rápidos no cobran dos veces ni dan dos cupos
      (restricción `unique`, `select … for update` o función transaccional).
- [ ] Montos, precios y descuentos se calculan en el servidor desde la base,
      nunca se reciben del cliente.

## A4 · Metodología y buenas prácticas

Contrasta el proyecto con las reglas de `diseno-express-de-apps`:

- [ ] Existen `docs/00`-`05` y `CLAUDE.md`; `expres.py validar` pasa.
- [ ] Los casos marcados ✅ en `docs/05` existen de verdad en el código
      (muestrea 3-5 y busca la pantalla y la acción). Un ✅ sin código es un
      hallazgo de `metodologia`.
- [ ] Migraciones en `supabase/migrations/` con nombres por etapa; tipos
      generados (`src/lib/database.types.ts`) al día con la última migración.
- [ ] Clientes en `src/lib/supabase/` (`client.ts`, `server.ts`) y refresco
      de sesión en `src/proxy.ts`/`middleware.ts`.
- [ ] Trabajo en ramas `etapa-eN`; `main` = producción.
- [ ] `npm run build` pasa y no hay errores de tipos ni de lint ignorados.
- [ ] Dependencias: `npm audit --omit=dev` sin altas/críticas sin plan;
      `package-lock.json` versionado.
- [ ] Manejo de errores: páginas `error.tsx` / `not-found.tsx`; los errores
      no muestran trazas ni mensajes de la base de datos al usuario.
- [ ] Datos personales: si `04-conceptual.md` dice que hay datos sensibles
      o dinero de terceros, existen política de privacidad, consentimiento
      y pasarela autorizada (no custodia de fondos).
- [ ] **Automatización**: hay un workflow de GitHub Actions que corre el
      barrido en cada PR y las pruebas de RLS, y Dependabot activo
      (`auditar.py automatizar` los crea). Sin CI, las lecciones dependen de
      que alguien se acuerde.
- [ ] **Privacidad visible**: aviso de cookies si hay analítica o
      publicidad de terceros; política de privacidad y términos enlazados
      desde el registro; opción de borrar la cuenta.
- [ ] **Accesibilidad** (buenas prácticas, `buenas-practicas`): imágenes
      con `alt`, campos con `label`, contraste suficiente, todo operable con
      teclado. Muestrea 3 pantallas del ciclo E1.
- [ ] **Rendimiento** (`rendimiento`): imágenes con `next/image`,
      fuentes con `next/font`, sin bibliotecas pesadas en componentes
      cliente que no las necesitan; consultas sin N+1.
- [ ] `docs/06-lecciones-aprendidas.md`: las lecciones previas se cumplen.
      **Una lección incumplida es un hallazgo reincidente** — súbele la
      severidad un nivel.

Si el problema nace del método (la plantilla no lo pide, la guía lo
induce), marca el hallazgo con `"alcance": "metodo"`.
