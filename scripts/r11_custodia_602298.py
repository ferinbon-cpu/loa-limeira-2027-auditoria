#!/usr/bin/env python3
"""R11: preserve one verified publicly served PDF temporarily as Actions artifact.

The original PDF is not committed to this public repository. Only one allowlisted
official URL is opened. Credentials, redirects to other hosts and bypasses are banned.
"""
import hashlib
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

HOST = "consulta.limeira.sp.leg.br"
ID = "602298"
URL = "https://consulta.limeira.sp.leg.br/arquivo?Id=602298"
EXPECTED_BYTES = 162477
EXPECTED_SHA256 = "b2e7acd2ffb0d827b2b0979d6b691b79fdabd1de61c374450c8fa63fdbf9f58d"
MAX_BYTES = 1_000_000

class SameOriginOnly(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlparse(newurl)
        if u.scheme != "https" or u.hostname != HOST or u.port is not None:
            raise ValueError("REDIRECT_NAO_PERMITIDO")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def capture(destination):
    destination.mkdir(parents=True, exist_ok=True)
    opener = build_opener(SameOriginOnly())
    req = Request(URL, headers={
        "User-Agent": "LOA-Limeira-2027-Auditoria-R11/1.0 (custodia publica sem login)",
        "Accept": "application/pdf,application/octet-stream,*/*;q=0.2"}, method="GET")
    with opener.open(req, timeout=25) as response:
        target = urlparse(response.geturl())
        if (response.getcode() != 200 or target.scheme != "https"
            or target.hostname != HOST or target.port is not None):
            raise ValueError("RESPOSTA_INVALIDA_OU_REDIRECT")
        ctype = response.headers.get("Content-Type","").split(";",1)[0].strip().lower()
        data = response.read(MAX_BYTES+1)
        if len(data)>MAX_BYTES or len(data)!=EXPECTED_BYTES or not data.startswith(b"%PDF-"):
            raise ValueError("TAMANHO_OU_ASSINATURA_INVALIDOS")
        digest = hashlib.sha256(data).hexdigest()
        if digest != EXPECTED_SHA256:
            raise ValueError("SHA256_DIVERGENTE")
    path = destination / "PL144_EMENDA90_ID602298_ORIGINAL.pdf"
    path.write_bytes(data)
    manifest = {
        "id":"602298", "url_oficial":URL, "tipo":"PDF",
        "bytes":len(data), "sha256":digest,"content_type":ctype,
        "prova":"GET_HTTP200_ASSINATURA_PDF_BYTES_INTEGROS_SHA256_IGUAL_R10",
        "limite":"Sem analise de teor; anexo associado a emenda 90 no HTML da Camara",
        "custodia":"Artefato efemero GitHub Actions; nao commitado no repositorio"
    }
    (destination/"manifesto.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n", encoding="utf-8")
    print("R11_CUSTODIA_PASS id=602298 bytes="+str(len(data))+" sha256="+digest+" status=PDF_VERIFICADO")

if __name__=="__main__":
    try:
        capture(Path(sys.argv[1] if len(sys.argv)>1 else "r11_output"))
    except (HTTPError,URLError,ValueError,TimeoutError,OSError) as e:
        print("R11_CUSTODIA_FAIL "+type(e).__name__+(" "+str(e) if isinstance(e,ValueError) else ""))
        raise SystemExit(1)
