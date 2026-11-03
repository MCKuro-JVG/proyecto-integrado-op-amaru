-- Solo lectura. Seleccionar la conexión de demostración en DBeaver.
SELECT id,name,rut,active,created_at FROM opticas_amaru_qr_demo.gestion_client ORDER BY id DESC;
SELECT id,name,kind,source,status,client_id,created_at FROM opticas_amaru_qr_demo.gestion_inquiry ORDER BY id DESC;
SHOW CREATE TABLE opticas_amaru_qr_demo.gestion_inquiry;
-- Esquema real de las relaciones, sin datos de personas.
SELECT table_name,column_name,referenced_table_name,referenced_column_name
FROM information_schema.key_column_usage
WHERE table_schema='opticas_amaru_qr_demo' AND referenced_table_name IS NOT NULL;
