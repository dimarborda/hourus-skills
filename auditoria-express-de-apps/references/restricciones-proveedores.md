# Restricciones de proveedores y límites de la auditoría

Dos cosas distintas: (1) qué **no puede hacer la auditoría** para no violar
las reglas de los proveedores, y (2) qué **no puede hacer la app** para no
incumplir los términos del plan o las políticas del proveedor.

> Las condiciones de los proveedores cambian. Lo de abajo es la lista de
> qué revisar, no el texto legal: antes de registrar un hallazgo
> `proveedor`, confirma en la documentación o los términos vigentes y cita
> la URL y la fecha en `referencia`.

## 1. Lo que la auditoría no hace

- Solo se prueba **el proyecto del usuario** en sus propias URL. Un
  `*.vercel.app` o `*.supabase.co` ajeno está fuera de alcance aunque sea
  "del mismo stack".
- Sin pruebas de carga, denegación de servicio, fuerza bruta de
  contraseñas o tokens, fuzzing masivo, escaneo de puertos de la
  infraestructura del proveedor ni intentos de saltar el WAF o la
  Deployment Protection. Los proveedores permiten, con matices, que
  pruebes tu propia aplicación; **ninguno** permite atacar su plataforma.
  Si el usuario quiere un pentest formal, recomiéndale revisar la política
  de pruebas de seguridad de cada proveedor y, si aplica, avisar antes.
- Peticiones manuales y pocas: una por tabla, una por ruta. Si una prueba
  necesita repetirse cientos de veces, no es para esta auditoría.
- No se crean cuentas ni datos en **producción**. Las pruebas que escriben
  van en local o en un entorno de prueba que el usuario nombró.
- No se descargan datos reales: si una petición anónima devuelve filas,
  basta con el código de estado y el tamaño; corta en la primera fila.

## 2. Vercel

- [ ] **Plan Hobby = uso personal y no comercial.** Si la app cobra, tiene
      clientes o es de una empresa, debe estar en un plan de pago (Pro o
      superior). Severidad `media`; `alta` si ya hay clientes pagando.
- [ ] Las variables `NEXT_PUBLIC_*` se incrustan en el JavaScript durante
      el build: son públicas por diseño. Cambiar el valor exige un nuevo
      despliegue; borrar la variable no limpia los despliegues anteriores.
- [ ] Los despliegues antiguos siguen accesibles por su URL: un secreto
      expuesto en uno viejo sigue expuesto hasta que se **rota** (o se
      borra ese despliegue, cosa que decide el usuario).
- [ ] Previews: con Deployment Protection activa; sin datos reales de
      producción.
- [ ] Límites por plan: duración de funciones, frecuencia de Cron, tamaño
      total de variables de entorno, ancho de banda y ejecuciones. Una app
      que depende de un Cron cada minuto en un plan que no lo permite
      falla en silencio.
- [ ] Política de uso aceptable: nada de proxys abiertos, minería,
      redistribución de contenido ajeno ni almacenamiento de archivos
      grandes como si fuera un CDN de terceros.

## 3. Supabase

- [ ] La `service_role` y las llaves secretas (`sb_secret_…`) **saltan
      RLS**. Solo en el servidor. Las versiones recientes de Supabase
      rechazan las llaves secretas cuando llegan desde un navegador, pero
      la `service_role` heredada (JWT) no tiene esa protección.
- [ ] La clave `anon`/`publishable` es pública: la seguridad la da RLS,
      no esconder la clave.
- [ ] Plan gratuito: proyectos inactivos se pausan y hay límite de
      proyectos activos; sin copias que cubran una app con usuarios reales.
      Una app en producción con clientes en plan gratuito → `media`.
- [ ] SMTP integrado de Auth: pensado para pruebas, con límites muy bajos
      (y, según la versión, solo envía a correos del equipo). Producción
      necesita SMTP propio (Resend, etc.).
- [ ] Límites de tasa de Auth (registro, OTP, recuperación) configurados;
      CAPTCHA en registro si el registro es abierto.
- [ ] Región del proyecto coherente con lo prometido a los usuarios sobre
      dónde viven sus datos.

## 4. GitHub

- [ ] Repositorio privado (regla del método). Si es público, todo lo que
      pasó por el historial es público: secretos, `docs/auditoria/`, datos
      de prueba.
- [ ] Secret scanning y push protection activos si el plan lo permite:
      bloquean el push de llaves conocidas antes de que salgan.
- [ ] Algunos proveedores revocan automáticamente llaves detectadas en
      repos públicos: si una integración "dejó de funcionar sola", revisa
      si su llave se filtró.

## 5. Pagos (Stripe, Mercado Pago, Wompi…)

- [ ] La app **nunca** recibe ni guarda números de tarjeta: checkout
      alojado o componentes del proveedor (fuera del alcance PCI propio).
- [ ] Llaves de prueba en preview, reales solo en producción; la secreta
      solo en servidor.
- [ ] Webhooks con verificación de firma, idempotentes y que no confían en
      montos enviados por el cliente (el monto sale de la base de datos).
- [ ] Si la app recauda para terceros, usar el modelo de marketplace del
      proveedor (Stripe Connect o equivalente), no custodiar fondos.

## 6. IA (Claude u otros)

- [ ] Llave solo en servidor; límite de uso por usuario y por día para
      que nadie convierta la app en un proxy gratuito del modelo.
- [ ] Respetar las políticas de uso del proveedor; no enviar datos
      personales sensibles sin necesidad ni base legal.
- [ ] La salida del modelo se trata como entrada no confiable (no se
      ejecuta, se sanitiza antes de mostrarla como HTML).

## 7. Datos personales

- [ ] Colombia: Ley 1581 de 2012 y su reglamentación — autorización previa
      del titular, política de tratamiento publicada, canal para consultas
      y reclamos y, si la organización está obligada, registro de bases
      de datos ante la SIC. En otros países, la ley equivalente
      (GDPR, LGPD, etc.).
- [ ] Datos sensibles (salud, biometría, menores) con acceso mínimo y
      bitácora; nunca en `user_metadata` ni en logs.
- [ ] Borrado o anonimización a solicitud del titular cuando la ley lo exige.
