# Desktop SOAP Client

Cliente de escritorio para el Ejercicio 03.

## Características

- GUI con Tkinter.
- No se conecta directamente a PostgreSQL.
- Consume únicamente `POST /soap`.
- Construye SOAP XML manualmente con `xml.etree.ElementTree`.
- Soporta:
  - `ObtenerConceptosPendientes`
  - `RegistrarClasificacion`
  - `ObtenerProgresoUsuario`
- Maneja `SOAP Fault`, incluido `DUPLICATE_CLASSIFICATION`.
- No requiere paquetes Python adicionales.

## Ubicación recomendada

```text
library_soap_service/
└── desktop_client/
    ├── desktop_app.py
    ├── soap_client.py
    └── README_DESKTOP.md
```

## Ejecución

Primero debe estar corriendo Flask:

```powershell
python app.py
```

En otra terminal:

```powershell
cd desktop_client
python desktop_app.py
```

El endpoint predeterminado es:

```text
http://127.0.0.1:5000/soap
```

## Flujo de prueba rápido

1. Completar nombre, apellidos y correo.
2. Presionar **Load pending concepts**.
3. Seleccionar un concepto.
4. Seleccionar IaaS/PaaS/SaaS/FaaS.
5. Presionar **Register classification**.
6. Verificar que desaparezca de pendientes.
7. Revisar **Progress**.

Para evidenciar un SOAP Fault por duplicado se puede mantener además la
prueba manual de PowerShell ya realizada, o volver a enviar el mismo
request por un cliente de prueba.
