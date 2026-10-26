import re
from pathlib import Path
from django.core.exceptions import ValidationError
from PIL import Image
from pypdf import PdfReader
def normalize_rut(value):
    value=value.replace('.','').replace(' ','').upper().strip()
    if not re.fullmatch(r'\d{7,8}-[0-9K]',value): raise ValidationError('Ingrese un RUT chileno válido, por ejemplo 12.345.678-5.')
    body,dv=value.split('-')
    s=sum(int(n)*(2+i%6) for i,n in enumerate(reversed(body)))
    check=11-s%11
    if dv != ('0' if check==11 else 'K' if check==10 else str(check)): raise ValidationError('El dígito verificador del RUT es incorrecto.')
    return str(int(body))+'-'+dv
def validate_rut(value): normalize_rut(value)
def validate_document(file):
    if file.size>10*1024*1024: raise ValidationError('El archivo supera el máximo de 10 MB.')
    ext=Path(file.name).suffix.lower()
    try:
        if ext in ('.jpg','.jpeg','.png'):
            image=Image.open(file); expected='PNG' if ext=='.png' else 'JPEG'
            if image.format!=expected: raise ValueError()
            image.verify()
        elif ext=='.pdf':
            if file.read(5)!=b'%PDF-': raise ValueError()
            file.seek(0); pdf=PdfReader(file,strict=True)
            if pdf.is_encrypted or not len(pdf.pages): raise ValueError()
        else: raise ValueError()
    except Exception: raise ValidationError('Adjunte un JPG, PNG o PDF válido y sin cifrar.')
    finally: file.seek(0)
