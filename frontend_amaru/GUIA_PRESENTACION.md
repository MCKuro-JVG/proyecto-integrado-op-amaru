# Ópticas Amaru · Guía de la demostración actualizada

La versión vigente es el frontend interactivo de esta carpeta. Comparte datos ficticios entre las experiencias pública y de personal, conservados solo en este navegador. El proyecto anterior en Django permanece separado.

## Abrir desde Windows

Haz doble clic en `../Abrir_Opticas_Amaru.cmd`. Inicia el servidor estático de Python y abre **http://127.0.0.1:8000/** en Google Chrome si está instalado. Si el servidor correcto ya está activo, reutiliza su dirección. Requiere Python 3; no necesita PostgreSQL ni Django.

Alternativa desde la carpeta principal:

```powershell
python servidor_amaru.py --port 8000
```

Mantén esa terminal abierta. Luego abre http://127.0.0.1:8000/ en el navegador. Usa siempre esa misma dirección y navegador para conservar el escenario. El puerto, nombre de host y perfil del navegador forman parte del origen de almacenamiento: `localhost` y `127.0.0.1` no comparten los datos locales.

Utiliza HTTP local con `servidor_amaru.py`: sirve los archivos actuales sin caché de desarrollo. Los scripts y estilos también llevan versiones calculadas desde su contenido para evitar mezclar archivos antiguos y nuevos. Abrir los HTML directamente como archivos no garantiza que los datos se compartan entre pantallas. No hay dependencias externas de fuentes, imágenes, API ni servicios de red. Todo el diseño usa archivos locales.

## Recorrido 1: visitante → personal

1. Desde Inicio, abre Productos y servicios y filtra una referencia.
2. Pulsa Consultar esta opción o Agendar / contactar.
3. Ingresa un nombre, teléfono, correo y motivo **ficticios**. Para agenda selecciona fecha y horario demostrativos.
4. Acepta el guardado de los datos DEMO y registra la solicitud. Se muestra un folio propio, no una reserva real.
5. Abre Personal DEMO → Agendamientos y contactos. Busca al visitante y pulsa Revisar.
6. Consulta sus datos y cambia su estado a En revisión, Contactada, Cerrada o Cancelada. No se envía ningún mensaje.

El formulario también conserva el recorrido de Solicitud de lentes, con selección de lentes, cristal, color, convenio y referencia de receta ficticia opcional. Solo se almacena el nombre del archivo.

## Recorrido 2: retiro de lentes completo

1. En Personal → Entrega de lentes, busca **Elena** y abre **OT-DEMO-025**, inicialmente disponible para retiro.
2. Verifica nombre, RUT ficticio, descripción y disponibilidad. Agrega observaciones, marca la verificación y genera el documento.
3. Revisa el borrador con nombre, RUT, pedido, producto, condiciones pendientes y observaciones.
4. Puedes continuar en el mismo equipo con el cliente. Para mostrar su experiencia separada, abre Vista del cliente → Mis pedidos → Entrar como Elena DEMO. Allí solo aparecen sus pedidos; abre Revisar y confirmar recepción.
5. Dibuja un trazo ficticio con mouse o dedo. Limpiar firma elimina el trazo y vuelve a exigirlo. Marca la conformidad y confirma.
6. El documento muestra Confirmado con fecha y hora; el pedido pasa a Entregado. Recargar mantiene el resultado.
7. Pulsa Imprimir / Guardar PDF y elige el destino PDF en la ventana de impresión del navegador. Esto crea un archivo local, sin envío a terceros.
8. En Personal → Documentos o en la ficha del cliente, consulta el documento conservado.

Si se intenta retirar OT-DEMO-024 mientras está En fabricación, no se permite generar el documento. No se puede marcar Entregado mediante el selector de estado.

En Documentos se configura el texto de garantía y el mecanismo propuesto: firma dibujada + aceptación, o solo aceptación mediante casilla y botón. Los documentos que ya fueron preparados conservan su versión. Para probar otra configuración, usa otro pedido disponible o descarta explícitamente un borrador sin confirmar.

## Rutas

| Archivo | Uso |
|---|---|
| index.html | Entrada pública, productos, atención y acceso diferenciado al personal DEMO. |
| catalogo.html | Productos y servicios, ilustraciones y búsqueda. |
| formulario_remoto.html | Agenda, contacto y solicitud de lentes en una sola pantalla. |
| consulta.html | Perfil ficticio de Elena, pedidos propios y acceso a documentos. |
| dashboard.html | Resumen calculado desde los datos locales y accesos rápidos. |
| clientes.html | Directorio, búsqueda y registro de clientes ficticios. |
| detalle_cliente.html | Ficha del cliente seleccionado, pedidos, recetas y documentos. |
| recetas.html | Registro de referencias ficticias y vigencia. |
| cotizaciones.html | Selección de producto, resumen calculado, borrador y creación de pedido. |
| ordenes.html | Tablero/listado, filtros, avance e historial. |
| recepcion.html | Retiro, documento, firma/conformidad, confirmación e impresión. |
| documentos.html | Historial, garantía y mecanismo de conformidad configurables. |
| solicitudes.html | Agenda/contactos/solicitudes recibidos y cambios de estado. |
| garantias.html | Revisiones de posventa vinculadas al pedido. |
| inventario.html | Búsqueda de referencias y ajuste demostrativo de cantidades. |

## Qué explicar durante la presentación

Los dos recorridos comparten `localStorage` en el navegador. Las pestañas avisan si hay cambios y permiten actualizar, pero teléfonos, navegadores y perfiles distintos no comparten automáticamente los datos. No hay autenticación real, comunicaciones externas ni reservas comerciales. Utiliza únicamente personas, teléfonos, correos, recetas y trazos ficticios.

La empresa confirmó integrar el retiro y crear el documento, pero todavía debe proporcionar la garantía oficial y elegir el mecanismo de firma. La firma simple propuesta no es una firma electrónica avanzada ni tiene validez legal certificada por el prototipo. OptiClick no forma parte del alcance.

Los datos se conservan al cerrar y abrir la página. Las estructuras antiguas reconocibles se adaptan automáticamente, guardando primero una copia original en otra clave del mismo sitio. El aviso permite descargar esos originales. Si los datos están dañados o Chrome bloquea el almacenamiento, el contenido sigue disponible en un escenario temporal de solo lectura; los formularios no muestran éxito ni guardan operaciones ficticias. No hace falta borrar el historial ni el almacenamiento para recuperar una vista.

Para reiniciar voluntariamente un escenario de prueba, descarga primero su respaldo y elimina únicamente la clave `opticas-amaru.demo.v2` desde las herramientas de almacenamiento del sitio. Esto elimina ese escenario: no es un paso de reparación obligatorio. La próxima carga crea los registros iniciales. Usar modo privado o borrar los datos del sitio puede perder los cambios de demostración.

La copia anterior está en `../respaldos/frontend_amaru_antes_actualizacion_2026-10-19.zip`. Consulta `ACTUALIZACION_2026-10-19.md` para alcance, requerimientos, limitaciones y decisiones pendientes.
