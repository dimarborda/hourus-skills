# {{PROYECTO}} · Procedimiento: se filtró una llave

Úsalo si una llave apareció en el repositorio, el bundle, un log, un chat,
una captura o el historial de git. **Rotar primero, investigar después.**
Borrar el archivo no basta: la llave sigue en el historial y en los
despliegues anteriores.

## 1. Rotar (en este orden; lo hace el dueño)

| Llave | Dónde se rota | Después |
|---|---|---|
| Supabase `service_role` / `sb_secret_…` | Supabase → Settings → API keys | Actualizar la variable en Vercel (todos los entornos) y redesplegar |
| Contraseña de la base de datos | Supabase → Settings → Database | Actualizar cadenas de conexión que la usen |
| Llave secreta de la pasarela | Panel del proveedor (Stripe, Mercado Pago, Wompi…) | Variable en Vercel + redespliegue; revisar transacciones recientes |
| Secreto de webhooks | Panel del proveedor | Variable en Vercel + redespliegue |
| Llave de IA | Consola del proveedor | Variable en Vercel + redespliegue; revisar consumo |
| Llave de correo | Panel del proveedor | Variable en Vercel + redespliegue |
| Tokens de GitHub / Vercel / Supabase CLI | Configuración de la cuenta | Volver a iniciar sesión en los CLI |
| `CRON_SECRET` y otros secretos propios | Generar uno nuevo | Variable en Vercel + redespliegue |

## 2. Contener

- [ ] Confirmar que la llave vieja ya no funciona (una petición de prueba debe fallar).
- [ ] Revisar logs y facturación del proveedor desde la fecha de la filtración.
- [ ] Si se expusieron datos personales: evaluar el aviso a los titulares y a la
      autoridad según la ley aplicable (en Colombia, la SIC).

## 3. Corregir y aprender

- [ ] Quitar la llave del código; si el repositorio es público, considerar
      reescribir el historial (no sustituye la rotación).
- [ ] Correr `auditar.py escanear` y una auditoría rápida.
- [ ] Registrar la causa en `docs/06-lecciones-aprendidas.md` (Notas del equipo).

## Contactos

| Rol | Persona | Medio |
|---|---|---|
| Dueño del proyecto | | |
| Quien tiene acceso a Vercel y Supabase | | |
