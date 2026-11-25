-- Solo lectura. Selecciona la base correcta en DBeaver antes de ejecutar.
-- Local: opticas_amaru. Hosting académico: opticaamaru_amaru_demo.
-- No usar la antigua base del túnel sin comprobar sus migraciones.
SELECT DATABASE() AS base_seleccionada;

SELECT a.id, a.name, i.id AS solicitud, i.kind, i.origin,
       i.name AS persona_ficticia, i.verification_state, i.status,
       i.client_id, i.union_membership_id, i.created_at
FROM gestion_inquiry i
JOIN gestion_agreement a ON a.id=i.agreement_id
WHERE a.name LIKE 'DEMO%' AND i.origin IN ('qr_worker','qr_inquiry')
ORDER BY i.id DESC;

SELECT a.name AS sindicato, m.id AS vinculacion, m.name AS persona_ficticia,
       m.role, m.state, m.origin, m.client_id,
       i.id AS solicitud, i.verification_state, m.created_at
FROM gestion_unionmembership m
JOIN gestion_union u ON u.id=m.union_id
JOIN gestion_agreement a ON a.id=u.agreement_id
LEFT JOIN gestion_inquiry i ON i.union_membership_id=m.id
WHERE a.name LIKE 'DEMO%' AND m.origin='qr_worker'
ORDER BY m.id DESC;

-- Los identificadores QR son enlaces compartibles, no credenciales personales.
-- No mostrar contactos ni contraseñas durante una presentación pública.
SELECT a.id, a.name, a.worker_qr_enabled, a.inquiry_qr_enabled,
       COUNT(i.id) AS entradas_desde_qr
FROM gestion_agreement a
LEFT JOIN gestion_inquiry i ON i.agreement_id=a.id
  AND i.origin IN ('qr_worker','qr_inquiry')
WHERE a.name LIKE 'DEMO%'
GROUP BY a.id,a.name,a.worker_qr_enabled,a.inquiry_qr_enabled;

SELECT table_name,column_name,referenced_table_name,referenced_column_name
FROM information_schema.key_column_usage
WHERE table_schema=DATABASE() AND table_name IN
 ('gestion_inquiry','gestion_unionmembership','gestion_union')
 AND referenced_table_name IS NOT NULL
ORDER BY table_name,column_name;
