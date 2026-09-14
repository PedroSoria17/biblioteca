1.- Dentro del directorio /apps/web-monolitico, Desarrolla una aplicacion web monolitica en el directorio backend-node y utiliza 
Node.js que gestione una libreria en linea mediante acceso directo a el esquema de base de datos recien creado. La solucion debera renderizar HTML del lado del servidor, administrar usuarios registrados,
implementar CRUD del modelo normalizado (en todas las tablas), manejar imagenes y conservar
definiciones de conceptos asociadas a cada libro

2.- Restriccion arquitectonica: no se desarrollaran APIs REST, GraphQL, SOAP ni otros servicios. No
se utilizaran JSON o XML como formato de intercambio de datos. El archivo package.json 
existe unicamente porque npm lo requiere para administrar el proyecto Node.js

3.- Para el desarrollo de esta solucion aplica la macroarquitectura Monolitica

4.- Aplica el patron de diseno MVC (modelo vista controlador) para la UI del sistema

5.- Aplica el enfoque de organizacion de codigo por modulos 

6.- Utiliza el esquema de base de datos disponible en /sql/schema.sql para el desarrollo de la aplicacion en NodeJS