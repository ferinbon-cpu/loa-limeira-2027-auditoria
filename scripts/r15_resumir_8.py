#!/usr/bin/env python3
"""Triagem de valores e codigos em 8 anexos oficiais DOCX, sem guardar os originais."""
import io
import json
import re
import time
import hashlib
import zipfile
import subprocess
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError

HOST = "consulta.limeira.sp.leg.br"
CAP = 6 * 1024 * 1024
# Apenas as duas emendas educacionais; as outras seis ja foram triadas na R14.
ANEXOS = ((346,603330,"APAE"),(347,603332,"ARIL"),(348,603340,"CAMPL"),(349,603346,"FT RAMATIS"),(350,603352,"SANTA CASA"),(351,603361,"EMEC"),(352,603363,"PLAYGROUNDS"),(353,603365,"MISS E MISTER"))
CURRENCY = re.compile(r"(?<![\d.])(?:R\$\s*)?(?:\d{1,3}(?:\.\d{3})+|\d+),\d{2}(?!\d)")
ACTION = re.compile(r"(?<!\d)\d{2}\.\d{3}\.\d{4}\.\d{4}(?!\d)")
TEXT_TAG = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"

def analyze(number, file_id, category):
    uri = f"https://{HOST}/arquivo?Id={file_id}"
    request = Request(uri, headers={"User-Agent":"LOA-Limeira-Auditoria-Metadados/1.0",
                                    "Accept":"application/octet-stream,*/*"})
    with urlopen(request, timeout=30) as response:
        if urlparse(response.geturl()).hostname != HOST:
            raise ValueError("HOST_REDIRECT_NAO_PERMITIDO")
        if int(response.headers.get("Content-Length", "0")) > CAP:
            raise ValueError("SUPERIOR_A_6M")
        payload = response.read(CAP+1)
    entry = {"emenda":number,"arquivo":file_id,"categoria":category,
             "bytes":len(payload),"sha256":hashlib.sha256(payload).hexdigest()}
    if len(payload)>CAP:
        entry["situacao"]="EXCEDE_CAP"
        return entry
    if payload.startswith(b"%PDF"):
        entry["formato_recebido"]="PDF"
        from pypdf import PdfReader
        reader=PdfReader(io.BytesIO(payload),strict=False)
        content="\n".join(page.extract_text() or "" for page in reader.pages[:12])
        entry["paginas_pdf"]=len(reader.pages)
        if not content.strip():
            entry["situacao"]="PDF_SEM_TEXTO_EXTRAIVEL"
            return entry
        entry["situacao"]="PDF_TEXTO_LIDO"
        entry["montantes_observados"]=sorted({s.replace("R$","").replace(" ","") for s in CURRENCY.findall(content)})[:30]
        entry["codigos_observados"]=sorted(set(ACTION.findall(content)))[:20]
        return entry
    if not payload.startswith(bytes([80,75,3,4])):
        entry["situacao"]="HTML_NAO_ARQUIVO" if b"<html" in payload[:1000].lower() else "ASSINATURA_OUTRA"
        entry["magic_hex"]=payload[:8].hex()
        return entry
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if "word/document.xml" not in archive.namelist():
            raise ValueError("DOCX_SEM_XML")
        root=ET.fromstring(archive.read("word/document.xml"))
    text=" ".join((elem.text or "") for elem in root.iter(TEXT_TAG))
    entry["situacao"]="DOCX_LIDO"
    entry["montantes_observados"]=sorted({s.replace("R$","").replace(" ","") for s in CURRENCY.findall(text)})[:30]
    entry["codigos_observados"]=sorted(set(ACTION.findall(text)))[:20]
    return entry

def main():
    result={"aviso":"Valores observados em arquivos: nao sao necessariamente valores de acrescimo, nem aprovacao.",
            "anexos":[]}
    for i,(n,file_id,cat) in enumerate(ANEXOS):
        if i: time.sleep(1.5)
        try:
            item=analyze(n,file_id,cat)
        except HTTPError as e:
            item={"emenda":n,"arquivo":file_id,"categoria":cat,"situacao":"HTTP_"+str(e.code)}
        except Exception as e:
            item={"emenda":n,"arquivo":file_id,"categoria":cat,"situacao":type(e).__name__}
        result["anexos"].append(item)
        if item["situacao"]=="HTTP_429":
            result["pausa_portal"]=True
            break
    path=Path("data/r15/montantes_8_emendas.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(path.read_text(encoding="utf-8"))

if __name__=="__main__":
    main()
