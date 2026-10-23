#!/usr/bin/env python3
"""R13 - preservação transitória de um PDF oficial publicamente acessível.

Captura única de ID 601667, sem credenciais, sem redirecionar a outros domínios.
O PDF não é commitado ao GitHub; o artefato expira em 1 dia.
"""
import hashlib
import json
import sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.error import HTTPError,URLError
from urllib.parse import urlparse
from urllib.request import Request,HTTPRedirectHandler,build_opener

HOST="consulta.limeira.sp.leg.br"
ID="601667"
URL="https://consulta.limeira.sp.leg.br/arquivo?Id=601667"
MAX_BYTES=8_000_000

class SameOrigin(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        u=urlparse(newurl)
        if u.scheme!="https" or u.hostname!=HOST or u.port is not None:
            raise ValueError("REDIRECT_FORA_HOST")
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def capture(out):
    out.mkdir(parents=True,exist_ok=True)
    req=Request(URL,headers={"User-Agent":"LOA-Limeira-2027-R13-Custodia-Publica/1.0",
                             "Accept":"application/pdf,application/octet-stream,*/*;q=0.2"},
                method="GET")
    with build_opener(SameOrigin()).open(req,timeout=30) as response:
        u=urlparse(response.geturl())
        if (response.getcode()!=200 or u.scheme!="https" or u.hostname!=HOST or u.port is not None):
            raise ValueError("URL_FINAL_OU_STATUS_INVALIDO")
        mime=response.headers.get("Content-Type","").split(";",1)[0].strip().lower()
        content=response.read(MAX_BYTES+1)
    if not (10000<len(content)<=MAX_BYTES and content.startswith(b"%PDF-")):
        raise ValueError(f"NAO_PDF_INTEGRO_DENTRO_LIMITE: bytes={len(content)} mime={mime} assinatura_pdf={content.startswith(bytes.fromhex('255044462d'))}")
    digest=hashlib.sha256(content).hexdigest()
    name="PL144_EMENDA_066_ID601667_ORIGINAL.pdf"
    (out/name).write_bytes(content)
    manifest={"id":ID,"url":URL,"emenda":66,"mime_observado":mime,
              "tipo":"PDF","tamanho_bytes":len(content),"sha256":digest,
              "prova":"HTTP_200_PDF_SIGNATURE_TRANSFERENCIA_INTEGRAL_HASH",
              "limite":"Assinatura digital e mérito documental não examinados; arquivo público"}
    (out/"manifesto.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("R13_OK ID",ID,"BYTES",len(content),"SHA256",digest)
if __name__=="__main__":
    try: capture(Path(sys.argv[1] if len(sys.argv)>1 else "r13_output"))
    except (ValueError,HTTPError,URLError,TimeoutError,OSError) as exc:
        print("R13_FALHOU",type(exc).__name__, str(exc) if isinstance(exc,ValueError) else "")
        raise SystemExit(1)
