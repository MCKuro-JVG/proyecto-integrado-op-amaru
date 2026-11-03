-- Solo lectura. Seleccionar la conexión de demostración en DBeaver.
SELECT id,name,rut,active,created_at FROM opticas_amaru_qr_demo.gestion_client ORDER BY id DESC;
SELECT id,name,kind,source,status,client_id,created_at FROM opticas_amaru_qr_demo.gestion_inquiry ORDER BY id DESC;
SHOW CREATE TABLE opticas_amaru_qr_demo.gestion_inquiry;
-- Esquema real de las relaciones, sin datos de personas.
SELECT table_name,column_name,referenced_table_name,referenced_column_name
FROM information_schema.key_column_usage
WHERE table_schema='opticas_amaru_qr_demo' AND referenced_table_name IS NOT NULL;

-- Relación entre solicitudes, fichas y horarios; no confundir agenda con registro.
SELECT i.id,i.kind,i.source,i.status,i.client_id,c.active AS cliente_activo,
       a.id AS solicitud_de_horario
FROM opticas_amaru_qr_demo.gestion_inquiry i
LEFT JOIN opticas_amaru_qr_demo.gestion_client c ON c.id=i.client_id
LEFT JOIN opticas_amaru_qr_demo.gestion_appointmentreservation a ON a.inquiry_id=i.id
ORDER BY i.id DESC;
-- Para una búsqueda personal, utilizar un archivo local privado o parámetros de DBeaver.
-- No escribir nombres, RUT o contactos de personas en este archivo versionado.
