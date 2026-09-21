# Implementación del microservicio de Login y Autenticación

## Contexto del proyecto

Este repositorio corresponde a una plataforma de librería en línea que actualmente contiene diferentes aplicaciones y servicios.

Antes de realizar cualquier modificación, inspecciona la estructura actual completa del repositorio y entiende cómo funcionan sus componentes.

La estructura relevante es aproximadamente:

```text
/
├── apps/
│   ├── Electron-app/
│   ├── web-monolito01/
│   └── services/
│       └── soap/
├── data/
├── docs/
└── ...
```

Actualmente existen tres componentes funcionales que **NO deben modificarse**:

```text
apps/Electron-app/
apps/web-monolito01/
apps/services/soap/
```

Estos componentes deben continuar funcionando exactamente como funcionan actualmente.

La tarea consiste exclusivamente en desarrollar un nuevo microservicio independiente de autenticación y gestión básica de usuarios.

---

# REGLA CRÍTICA

## NO modificar las aplicaciones existentes

No debes modificar, mover, eliminar, renombrar ni refactorizar ningún archivo dentro de:

```text
apps/Electron-app/
apps/web-monolito01/
apps/services/soap/
```

Tampoco debes modificar sus:

* dependencias;
* configuraciones;
* rutas;
* controladores;
* modelos;
* vistas;
* variables de entorno;
* Dockerfiles;
* package.json;
* requirements;
* código fuente.

El nuevo microservicio debe desarrollarse de manera independiente.

En esta etapa **NO se debe integrar el nuevo microservicio con el monolito web, Electron ni SOAP**.

Primero debemos poder ejecutar y probar el microservicio de manera aislada mediante sus endpoints.

---

# Objetivo

Desarrollar un microservicio independiente de autenticación y gestión básica de usuarios utilizando:

* Python;
* Flask;
* Psycopg 3;
* PostgreSQL;
* bcrypt;
* sesiones de Flask;
* XML;
* JSON;
* SMTP/Postfix para verificación de correo electrónico.

Debe utilizar la base de datos PostgreSQL actual del proyecto.

La base de datos se encuentra actualmente desplegada en una máquina virtual de Google Cloud Platform.

No crear una nueva base de datos independiente.

---

# Nueva ubicación del microservicio

Crear:

```text
apps/services/login/
```

Todo el código correspondiente al nuevo microservicio debe permanecer dentro de esta carpeta, excepto los scripts SQL relacionados con cambios de estructura de la base de datos, los cuales deberán almacenarse dentro de:

```text
data/
```

La estructura propuesta para el microservicio puede ser:

```text
apps/
└── services/
    ├── soap/
    │   └── ...
    │
    └── login/
        ├── app.py
        ├── config.py
        ├── requirements.txt
        ├── .env.example
        ├── README.md
        │
        ├── routes/
        │   ├── __init__.py
        │   ├── auth.py
        │   └── health.py
        │
        ├── services/
        │   ├── __init__.py
        │   ├── auth_service.py
        │   └── email_service.py
        │
        ├── repositories/
        │   ├── __init__.py
        │   └── user_repository.py
        │
        ├── utils/
        │   ├── __init__.py
        │   ├── responses.py
        │   ├── validators.py
        │   └── tokens.py
        │
        └── tests/
            └── ...
```

Puedes realizar pequeños ajustes a esta organización si son técnicamente necesarios, pero mantén una arquitectura clara por responsabilidades.

No conviertas todo el microservicio en un único archivo grande.

---

# Requerimientos funcionales obligatorios

El microservicio debe implementar como mínimo:

| Método | Endpoint    | Función                                |
| ------ | ----------- | -------------------------------------- |
| POST   | `/register` | Registrar un nuevo usuario             |
| POST   | `/login`    | Autenticar al usuario e iniciar sesión |
| POST   | `/logout`   | Cerrar la sesión                       |
| GET    | `/session`  | Consultar la sesión actual             |
| GET    | `/health`   | Verificar Flask y PostgreSQL           |

Además, para implementar la verificación del correo electrónico, agregar:

| Método | Endpoint        | Función                                        |
| ------ | --------------- | ---------------------------------------------- |
| GET    | `/verify-email` | Validar el token enviado al correo del usuario |

No elimines ni sustituyas ninguno de los cinco endpoints obligatorios.

---

# XML y JSON

TODOS los endpoints deben ser capaces de devolver respuestas tanto en XML como en JSON.

El formato se controla mediante:

```text
?format=xml
?format=json
```

## Comportamiento obligatorio

Estas solicitudes:

```text
POST /login
POST /login?format=xml
```

deben responder en XML.

Esta solicitud:

```text
POST /login?format=json
```

debe responder en JSON.

Por lo tanto:

```text
XML = formato predeterminado
```

si no existe el parámetro `format`.

Este comportamiento debe aplicarse también a:

* respuestas exitosas;
* errores de validación;
* credenciales incorrectas;
* recursos inexistentes;
* errores de autenticación;
* errores controlados del servidor.

No permitir que Flask devuelva una página HTML como respuesta de error para estos endpoints.

Crear una capa/utilidad centralizada para serializar la misma estructura de datos como XML o JSON y evitar duplicar lógica.

---

# Ejemplo de respuesta JSON

Una autenticación correcta podría generar:

```json
{
    "success": true,
    "message": "Login successful",
    "user": {
        "id": 1,
        "email": "usuario@example.com"
    }
}
```

Una autenticación incorrecta podría generar:

```json
{
    "success": false,
    "message": "Invalid credentials"
}
```

---

# Ejemplo XML

La misma respuesta exitosa debería poder representarse conceptualmente como:

```xml
<response>
    <success>true</success>
    <message>Login successful</message>
    <user>
        <id>1</id>
        <email>usuario@example.com</email>
    </user>
</response>
```

Mantén una estructura coherente entre XML y JSON.

---

# Base de datos existente

Antes de implementar la capa de persistencia, revisa los scripts actuales existentes dentro de:

```text
data/
```

para conocer la estructura real de PostgreSQL.

No supongas nombres de columnas o restricciones si puedes verificarlas primero en esos archivos.

Actualmente existe una tabla de usuarios utilizada por el monolito.

Conceptualmente contiene información equivalente a:

```text
usuarios
--------------------------------
usuario_id
nombre_completo
email
password_hash
es_administrador
activo
fecha_registro
```

La estructura exacta debe verificarse antes de escribir los nuevos scripts.

---

# Compatibilidad con el sistema actual

La tabla existente `usuarios` NO debe sufrir cambios incompatibles.

En particular:

* NO eliminar `nombre_completo`;
* NO renombrar columnas existentes;
* NO eliminar campos existentes;
* NO cambiar tipos de datos actuales sin necesidad;
* NO eliminar restricciones utilizadas por el monolito;
* NO modificar registros actuales;
* NO hacer que los usuarios existentes dejen de funcionar.

El objetivo es EXTENDER la estructura actual, no reemplazarla.

---

# Información adicional requerida por el nuevo registro

El nuevo endpoint `/register` deberá solicitar:

```text
nombre
apellido_paterno
apellido_materno
email
password
```

Como la tabla actual utiliza `nombre_completo`, debemos mantener compatibilidad con ella.

Al registrar:

```text
nombre = Pedro
apellido_paterno = Soria
apellido_materno = Gonzalez
```

construir:

```text
nombre_completo = Pedro Soria Gonzalez
```

y almacenar ese valor en la tabla actual `usuarios`.

---

# Nueva tabla de información del usuario

Crear mediante un NUEVO script SQL una tabla relacionada 1:1 con `usuarios`.

Puede llamarse, por ejemplo:

```text
usuario_detalle
```

y contener al menos:

```text
usuario_id
nombre
apellido_paterno
apellido_materno
email_verificado
fecha_creacion
fecha_actualizacion
```

`usuario_id` deberá relacionarse mediante una clave foránea con el usuario existente.

Debe existir una relación 1:1.

No duplicar el email en esta tabla si no es necesario, ya que el correo ya pertenece al recurso `usuarios`.

Utilizar restricciones apropiadas.

---

# Tabla para verificación del correo

Crear también una estructura para administrar tokens de verificación.

Puede llamarse:

```text
usuario_verificacion_email
```

y contener conceptualmente:

```text
verificacion_id
usuario_id
token_hash
fecha_expiracion
fecha_verificacion
fecha_creacion
```

Aplicar:

* claves primarias;
* claves foráneas;
* índices pertinentes;
* restricciones apropiadas.

El token de verificación NO debe almacenarse en texto plano.

Guardar solamente un hash del token.

---

# Script SQL

Crear un nuevo archivo dentro de:

```text
data/
```

por ejemplo:

```text
data/login_microservice.sql
```

Este script debe contener únicamente los cambios nuevos necesarios para soportar el microservicio.

Debe ser seguro respecto a la estructura existente.

NO reemplazar los scripts actuales.

NO eliminar tablas actuales.

NO recrear desde cero toda la base de datos.

Antes de escribir este SQL, inspecciona los scripts existentes de `data/`.

---

# Registro de usuario

Implementar:

```text
POST /register
```

El cuerpo principal de las pruebas será JSON.

Ejemplo:

```json
{
    "nombre": "Pedro",
    "apellido_paterno": "Soria",
    "apellido_materno": "Gonzalez",
    "email": "usuario@example.com",
    "password": "PasswordSeguro123!"
}
```

El endpoint debe:

1. Verificar que los campos obligatorios existan.
2. Normalizar los campos cuando corresponda.
3. Eliminar espacios accidentales al inicio/final.
4. Normalizar el email.
5. Validar el formato del email.
6. Verificar que el email no exista actualmente.
7. Validar mínimamente la contraseña.
8. Generar un hash seguro mediante bcrypt.
9. Construir `nombre_completo`.
10. Crear el usuario en `usuarios`.
11. Crear su registro correspondiente en `usuario_detalle`.
12. Generar un token criptográficamente seguro de verificación.
13. Guardar solamente el hash del token.
14. Definir una fecha de expiración.
15. Enviar el token al usuario mediante correo electrónico.
16. Devolver una respuesta adecuada en XML o JSON.

---

# Transacciones

El proceso de registro involucra varias operaciones relacionadas.

Utilizar una transacción PostgreSQL.

Si falla cualquiera de las operaciones esenciales de creación:

```text
INSERT usuarios
INSERT usuario_detalle
INSERT token de verificación
```

no debe quedar un usuario parcialmente registrado.

Utilizar correctamente las transacciones proporcionadas por Psycopg 3.

No concatenar valores directamente dentro de consultas SQL.

Utilizar parámetros SQL para prevenir SQL Injection.

---

# Seguridad de contraseña

La contraseña:

```text
NUNCA
```

debe almacenarse en texto plano.

Utilizar:

```text
bcrypt
```

para crear y validar hashes.

Esto es especialmente importante porque el monolito existente actualmente utiliza hashes bcrypt mediante `bcryptjs`.

El nuevo servicio Python debe mantener compatibilidad con dichos hashes.

NO reemplazar los hashes existentes.

NO migrar las contraseñas existentes.

NO guardar contraseñas en logs.

NO devolver hashes en las respuestas.

---

# Login

Implementar:

```text
POST /login
```

Entrada esperada:

```json
{
    "email": "usuario@example.com",
    "password": "PasswordSeguro123!"
}
```

El endpoint debe:

1. Validar entrada.
2. Normalizar el email.
3. Buscar al usuario en PostgreSQL.
4. Comprobar que el usuario exista.
5. Comprobar que esté activo.
6. Validar la contraseña con bcrypt.
7. Crear una sesión utilizando Flask.
8. Devolver información pública mínima del usuario.

Nunca indicar de manera diferente:

```text
"email does not exist"
```

y:

```text
"wrong password"
```

Utilizar una respuesta genérica como:

```text
Invalid credentials
```

para ambos casos.

---

# Compatibilidad con usuarios antiguos

Actualmente existen usuarios creados por el sistema anterior que probablemente NO tengan un registro en:

```text
usuario_detalle
```

No romper el login de esos usuarios.

Los usuarios existentes deben poder autenticarse mediante:

```text
usuarios.email
usuarios.password_hash
```

si se encuentran activos.

Para usuarios creados mediante el NUEVO microservicio, la verificación del correo deberá poder determinarse mediante `usuario_detalle.email_verificado`.

Si decides impedir que una cuenta nueva inicie sesión antes de verificar el correo, aplica esa regla solamente a usuarios creados mediante el nuevo flujo.

Un usuario legado sin fila en `usuario_detalle` no debe quedar bloqueado únicamente por no poseer esa fila.

Documenta claramente el comportamiento elegido.

---

# Sesiones

Utilizar sesiones de Flask.

No implementar JWT para este ejercicio.

Después de una autenticación correcta debe existir una sesión que permita identificar al usuario en solicitudes posteriores.

Guardar únicamente datos mínimos necesarios, por ejemplo:

```python
session["user_id"]
session["email"]
```

No almacenar:

* contraseña;
* password hash;
* información sensible innecesaria.

La `SECRET_KEY` debe obtenerse mediante variable de entorno.

Nunca escribir una clave secreta real directamente en el repositorio.

Configurar de forma razonable:

```text
SESSION_COOKIE_HTTPONLY
SESSION_COOKIE_SAMESITE
SESSION_COOKIE_SECURE
```

Permitir una configuración apropiada para desarrollo local donde todavía no exista HTTPS.

---

# Endpoint de sesión

Implementar:

```text
GET /session
```

Si existe una sesión válida:

```json
{
    "success": true,
    "authenticated": true,
    "user": {
        "id": 1,
        "email": "usuario@example.com"
    }
}
```

Si no existe:

```json
{
    "success": true,
    "authenticated": false
}
```

Debe funcionar igualmente en XML.

---

# Logout

Implementar:

```text
POST /logout
```

Debe eliminar la sesión de Flask.

Después de ejecutar `/logout`, una petición posterior a `/session` deberá indicar:

```text
authenticated = false
```

No considerar logout como error si ya no existe una sesión.

---

# Health check

Implementar:

```text
GET /health
```

Este endpoint debe comprobar como mínimo:

1. que Flask está ejecutándose;
2. que existe comunicación con PostgreSQL.

Puede ejecutar una consulta pequeña como:

```sql
SELECT 1;
```

Una respuesta JSON exitosa podría ser:

```json
{
    "success": true,
    "service": "login",
    "status": "healthy",
    "database": "connected"
}
```

Crear también su representación XML.

No revelar:

* passwords;
* connection strings;
* secretos;
* información sensible del servidor.

---

# Verificación del correo electrónico

Implementar un flujo de verificación de correo electrónico para usuarios registrados mediante `/register`.

Generar el token utilizando una fuente criptográficamente segura, por ejemplo el módulo estándar:

```python
secrets
```

El token enviado por correo puede viajar en texto plano dentro de la URL.

En PostgreSQL almacenar únicamente:

```text
hash(token)
```

El token debe tener una fecha de expiración configurable.

---

# Endpoint de verificación

Implementar:

```text
GET /verify-email?token=TOKEN
```

También debe aceptar:

```text
GET /verify-email?token=TOKEN&format=json
GET /verify-email?token=TOKEN&format=xml
```

Debe:

1. comprobar que exista el token;
2. calcular su hash;
3. buscar el hash en PostgreSQL;
4. comprobar que no haya expirado;
5. comprobar que no haya sido usado;
6. marcar el correo como verificado;
7. marcar el token como utilizado/verificado;
8. devolver una respuesta XML o JSON.

La operación debe ser idempotente o manejar limpiamente intentos repetidos.

---

# Correo electrónico y Postfix

La máquina virtual del proyecto utiliza Linux/CentOS y se desea utilizar Postfix como parte de la infraestructura de correo.

El microservicio NO debe contener credenciales SMTP codificadas directamente.

Crear un servicio desacoplado:

```text
email_service.py
```

Utilizar la biblioteca estándar de Python cuando sea apropiado:

```text
smtplib
email.message
```

Configurar mediante variables de entorno valores equivalentes a:

```text
MAIL_HOST
MAIL_PORT
MAIL_USERNAME
MAIL_PASSWORD
MAIL_USE_TLS
MAIL_FROM
PUBLIC_BASE_URL
```

Permitir que el microservicio pueda utilizar un Postfix local, por ejemplo:

```text
MAIL_HOST=localhost
MAIL_PORT=25
```

No modificar automáticamente la configuración del sistema operativo desde el código del proyecto.

No ejecutar automáticamente:

```text
yum
dnf
systemctl
postconf
```

desde la aplicación.

La configuración del servidor Postfix pertenece a la infraestructura y debe explicarse por separado en el README.

---

# Consideración importante de Google Cloud

La aplicación se ejecutará eventualmente en una VM de Google Cloud.

La implementación debe permitir utilizar Postfix como MTA local y, si es necesario, configurar posteriormente un SMTP relay externo.

El código del microservicio debe depender únicamente de las variables de entorno mencionadas y no asumir un proveedor específico.

Documenta en el README cómo comprobar:

```text
Postfix activo
puerto SMTP configurado
correo enviado
correo recibido
enlace de verificación
```

pero no realices cambios destructivos sobre la VM.

---

# Desarrollo local para correo

Debe ser posible desarrollar y probar el servicio aun cuando todavía no esté configurado Postfix.

Agregar una variable equivalente a:

```text
MAIL_ENABLED=true/false
```

Cuando:

```text
MAIL_ENABLED=false
```

el registro deberá poder completarse para desarrollo, pero el sistema debe:

* indicar claramente que el envío de correo está deshabilitado;
* registrar únicamente información segura para poder realizar pruebas;
* nunca imprimir contraseñas;
* nunca imprimir hashes de contraseñas.

Si resulta útil durante desarrollo, puede mostrarse en consola la URL de verificación SOLO cuando se encuentre explícitamente habilitado un modo de desarrollo.

No hacer esto en producción.

La configuración de desarrollo debe estar claramente separada de producción.

---

# Psycopg 3

Utilizar específicamente:

```text
psycopg
```

versión 3.

NO utilizar:

```text
psycopg2
```

NO utilizar un ORM para sustituir Psycopg.

Crear una capa de acceso a datos clara.

La conexión a PostgreSQL debe configurarse mediante variables de entorno.

Por ejemplo:

```text
DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASSWORD
```

No incluir valores reales ni secretos en Git.

---

# Variables de entorno

Crear:

```text
apps/services/login/.env.example
```

con variables de ejemplo, nunca credenciales reales.

Debe incluir al menos:

```text
FLASK_ENV
FLASK_HOST
FLASK_PORT
SECRET_KEY

DB_HOST
DB_PORT
DB_NAME
DB_USER
DB_PASSWORD

MAIL_ENABLED
MAIL_HOST
MAIL_PORT
MAIL_USERNAME
MAIL_PASSWORD
MAIL_USE_TLS
MAIL_FROM

PUBLIC_BASE_URL
EMAIL_TOKEN_EXPIRATION_MINUTES
```

Si se necesitan variables adicionales, documentarlas.

No copiar credenciales actuales del proyecto a `.env.example`.

---

# Configuración

Crear una clase o módulo central de configuración.

Evitar utilizar `os.getenv()` de forma dispersa por toda la aplicación.

La configuración debe validar las variables críticas.

Si faltan variables indispensables para ejecutar el servicio, generar un error entendible.

---

# Validación del email

Validar que el correo tenga una estructura válida antes de intentar crear el usuario.

Normalizar:

```text
email.lower().strip()
```

No confiar únicamente en validaciones del cliente.

PostgreSQL debe seguir garantizando la unicidad del correo.

El código debe manejar correctamente una posible condición de carrera donde dos solicitudes intenten registrar simultáneamente el mismo correo.

---

# Manejo de errores

Crear respuestas consistentes.

Ejemplo:

```json
{
    "success": false,
    "message": "Email already registered"
}
```

Usar códigos HTTP adecuados, por ejemplo:

```text
200 OK
201 Created
400 Bad Request
401 Unauthorized
409 Conflict
500 Internal Server Error
503 Service Unavailable
```

Selecciona el código más apropiado según cada caso.

No devolver:

* stack traces;
* consultas SQL;
* claves;
* connection strings;
* variables sensibles.

Registrar internamente los errores necesarios.

---

# Requirements

Crear:

```text
apps/services/login/requirements.txt
```

Incluyendo únicamente dependencias necesarias.

Se espera utilizar al menos equivalentes a:

```text
Flask
psycopg[binary]
bcrypt
python-dotenv
```

Puedes añadir una biblioteca pequeña de validación de email si consideras que aporta valor, pero evita dependencias innecesarias.

---

# Inicialización del servicio

Debe existir una forma clara de ejecutar:

```text
python app.py
```

desde:

```text
apps/services/login/
```

y obtener un servidor Flask funcional.

El puerto debe ser configurable mediante variable de entorno y no debe entrar en conflicto innecesariamente con el servicio SOAP o el monolito.

---

# README

Crear:

```text
apps/services/login/README.md
```

Debe explicar claramente:

## Requisitos

* Python;
* PostgreSQL;
* acceso a la BD;
* variables de entorno;
* Postfix para pruebas reales de correo.

## Instalación

Por ejemplo:

```bash
python -m venv .venv
```

y los comandos apropiados para Windows/Linux según resulte útil.

Después:

```bash
pip install -r requirements.txt
```

## Configuración

Explicar cómo generar:

```text
.env
```

a partir de:

```text
.env.example
```

sin incluir secretos reales.

## Ejecución

Explicar:

```bash
python app.py
```

## Base de datos

Explicar qué script SQL nuevo debe aplicarse.

NO asumir que debe borrarse o recrearse la base de datos.

---

# Pruebas manuales obligatorias

El README debe incluir una sección específica:

```text
Manual API Test Flow
```

Debemos poder probar el microservicio sin utilizar:

* Electron;
* monolito web;
* SOAP;
* interfaces gráficas del proyecto.

Las pruebas podrán realizarse mediante Postman o curl.

---

# Flujo de prueba

Documentar paso a paso:

## 1. Health

```text
GET /health?format=json
```

Comprobar:

```text
Flask OK
PostgreSQL OK
```

Después probar:

```text
GET /health?format=xml
```

y:

```text
GET /health
```

La última debe devolver XML.

---

## 2. Register JSON

```text
POST /register?format=json
```

con un usuario de prueba.

Mostrar ejemplo completo de body JSON.

Comprobar:

* usuario creado;
* password almacenado como bcrypt;
* fila de `usuario_detalle`;
* fila de verificación;
* respuesta JSON.

---

## 3. Register XML response

Realizar otro registro mediante:

```text
POST /register?format=xml
```

y comprobar XML.

También probar:

```text
POST /register
```

para confirmar que XML sea el predeterminado.

---

## 4. Email duplicado

Intentar registrar dos veces el mismo email.

Debe obtenerse una respuesta controlada.

---

## 5. Email inválido

Intentar registrar:

```text
correo-invalido
```

y comprobar que el usuario NO se cree.

---

## 6. Verificación del correo

Comprobar que el correo de verificación llegue realmente cuando `MAIL_ENABLED=true`.

Abrir el enlace:

```text
/verify-email?token=...
```

Comprobar el cambio correspondiente en PostgreSQL.

También realizar la prueba en JSON.

---

## 7. Login incorrecto

Probar:

* correo inexistente;
* contraseña incorrecta.

Ambos deben devolver una respuesta genérica de credenciales inválidas.

---

## 8. Login correcto

```text
POST /login?format=json
```

Comprobar:

* status exitoso;
* creación de cookie de sesión;
* datos públicos del usuario.

---

## 9. Session

Utilizando la MISMA sesión/cookies:

```text
GET /session?format=json
```

Debe indicar:

```text
authenticated: true
```

En los ejemplos curl, utilizar correctamente cookie jar mediante opciones equivalentes a:

```bash
-c cookies.txt
-b cookies.txt
```

para demostrar que la sesión funciona entre diferentes solicitudes HTTP.

---

## 10. Logout

```text
POST /logout?format=json
```

Después:

```text
GET /session?format=json
```

debe devolver:

```text
authenticated: false
```

---

## 11. XML

Repetir las operaciones principales mediante XML:

```text
/register
/login
/logout
/session
/health
/verify-email
```

para comprobar que todas soporten:

```text
?format=xml
```

y que XML sea predeterminado.

---

# Pruebas automatizadas

Crear pruebas razonables dentro de:

```text
apps/services/login/tests/
```

como mínimo para:

* selección XML/JSON;
* formato predeterminado XML;
* validación de email;
* serialización de respuestas;
* hashing/verificación de contraseñas;
* generación y hashing de token.

Si las pruebas de integración necesitan acceso real a PostgreSQL, separarlas de las pruebas unitarias y documentar cómo ejecutarlas.

No modificar la base productiva de manera destructiva desde las pruebas.

---

# Calidad del código

Aplicar:

* separación de responsabilidades;
* nombres claros;
* funciones pequeñas;
* manejo adecuado de excepciones;
* consultas parametrizadas;
* comentarios únicamente donde aporten valor;
* configuración centralizada;
* reutilización de código.

Evitar sobrearquitectura innecesaria.

Este es un proyecto académico, pero la implementación debe seguir buenas prácticas razonables.

---

# No utilizar

No introducir tecnologías que no forman parte del ejercicio sin necesidad.

En particular no utilizar:

```text
JWT
Redis
SQLAlchemy
Django
FastAPI
MongoDB
```

para este microservicio.

El stack solicitado es:

```text
Python
Flask
Psycopg 3
PostgreSQL
bcrypt
Flask Session
XML/JSON
Postfix/SMTP
```

---

# Criterio crítico de aislamiento

Al finalizar:

```text
apps/Electron-app/
apps/web-monolito01/
apps/services/soap/
```

deben permanecer funcionalmente intactos.

Ejecuta:

```bash
git diff
```

o el mecanismo equivalente disponible y revisa todos los archivos modificados.

No debe aparecer ninguna modificación dentro de esas tres ubicaciones.

Los cambios esperados deben concentrarse aproximadamente en:

```text
apps/services/login/
data/login_microservice.sql
```

No realices refactors generales del proyecto.

---

# Orden de trabajo

Realiza la implementación en este orden:

1. Inspecciona el repositorio actual.
2. Inspecciona la definición actual de PostgreSQL dentro de `data/`.
3. Inspecciona cómo `web-monolito01` trabaja actualmente con `usuarios` y bcrypt, solamente para entender compatibilidad.
4. NO modifiques el monolito.
5. Diseña las extensiones mínimas de BD.
6. Crea `data/login_microservice.sql`.
7. Crea `apps/services/login/`.
8. Implementa configuración y conexión PostgreSQL.
9. Implementa serializer XML/JSON.
10. Implementa `/health`.
11. Implementa `/register`.
12. Implementa verificación de email.
13. Implementa `/login`.
14. Implementa `/session`.
15. Implementa `/logout`.
16. Implementa pruebas.
17. Documenta ejecución y pruebas.
18. Revisa el diff completo.
19. Confirma que no se tocaron los demás componentes.

---

# IMPORTANTE SOBRE LA BASE DE DATOS REMOTA

No ejecutes automáticamente cambios destructivos sobre la base de datos remota.

Puedes preparar el script SQL requerido.

Si tienes acceso configurado y necesitas aplicar cambios para realizar pruebas:

* muestra primero claramente qué script será aplicado;
* limita la operación exclusivamente a las nuevas estructuras;
* no borres información;
* no elimines tablas;
* no hagas `DROP DATABASE`;
* no hagas `DROP TABLE`;
* no hagas `TRUNCATE`;
* no elimines usuarios existentes.

La prioridad absoluta es preservar la base actual.

---

# Resultado esperado

Al terminar debemos tener algo similar a:

```text
/
├── apps/
│   ├── Electron-app/                 ← intacto
│   ├── web-monolito01/               ← intacto
│   │
│   └── services/
│       ├── soap/                     ← intacto
│       │
│       └── login/
│           ├── app.py
│           ├── config.py
│           ├── requirements.txt
│           ├── .env.example
│           ├── README.md
│           ├── routes/
│           ├── services/
│           ├── repositories/
│           ├── utils/
│           └── tests/
│
├── data/
│   ├── [archivos existentes]
│   └── login_microservice.sql
│
└── ...
```

---

# Entrega final

Una vez terminada la implementación, NO continúes integrando este servicio con otras aplicaciones.

Detente después de dejar el microservicio independiente funcionando.

Al finalizar muéstrame:

1. un árbol simplificado de todos los archivos nuevos;
2. lista de archivos modificados;
3. explicación breve de la arquitectura;
4. cambios realizados en PostgreSQL;
5. variables de entorno necesarias;
6. endpoints disponibles;
7. ejemplos JSON;
8. ejemplos XML;
9. pasos exactos para instalar dependencias;
10. pasos exactos para ejecutar el microservicio;
11. pasos exactos para aplicar el nuevo SQL;
12. pasos exactos para probar cada endpoint;
13. pasos para probar la sesión manteniendo cookies;
14. pasos para probar el correo mediante Postfix;
15. cualquier configuración que todavía tenga que realizar manualmente en la VM;
16. resultado de la revisión final que confirme que:

```text
Electron-app
web-monolito01
services/soap
```

no fueron modificados.

No hagas todavía ninguna integración adicional.