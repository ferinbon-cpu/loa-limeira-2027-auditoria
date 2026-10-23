#!/usr/bin/env python3
"""R10: diagnosticar acesso GET a três URLs públicas explicitamente vinculadas.

Não usar login/cookies, não contornar proteções, nem reter bytes de anexos.
Registra somente status, tipo, tamanho lido e SHA-256 se completo.
"""
import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

HOST = "consulta.limeira.sp.leg.br"
IDS = ("602182", "602184", "602298")
LIMIT = 16 * 1024 * 1024
TIMEOUT = 25

class OfficialRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlparse(newurl)
        if u.scheme != "https" or u.hostname != HOST or u.port is not None:
            raise ValueError("REDIRECIONAMENTO_FORA_DOMINIO_OFICIAL")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def official_url(identifier):
    if identifier not in IDS:
        raise ValueError("ID_NAO_PERMITIDO")
    return f"https://{HOST}/arquivo?Id={identifier}"

def valid_url(url):
    u = urlparse(url)
    q = parse_qs(u.query)
    return (u.scheme == "https" and u.hostname == HOST and u.port is None
            and u.path.lower() == "/arquivo" and len(q) == 1
            and q.get("Id") in [[i] for i in IDS] and not u.fragment
            and not u.username and not u.password)

def valid_final_url(url):
    """Same-origin public redirect is permitted; final content is still inspected."""
    u = urlparse(url)
    return (u.scheme == "https" and u.hostname == HOST and u.port is None
            and not u.username and not u.password)

def magic(b):
    if b.startswith(b"%PDF-"):
        return "PDF"
    if b.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return "ZIP_OOXML_POSSIVEL"
    if b.startswith(b"\xff\xd8\xff"):
        return "JPEG"
    if b.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG"
    if b.lstrip().lower().startswith((b"<!doctype html", b"<html")):
        return "HTML_NAO_DOCUMENTO"
    return "NAO_IDENTIFICADO"

def probe(identifier, opener=None):
    url = official_url(identifier)
    row = dict(id=identifier, url=url, resultado="NAO_ACESSADO", http=None,
               content_type=None, bytes_lidos=0, sha256_completo=None,
               arquivo_completo=False, assinatura=None, erro=None)
    opener = opener or build_opener(OfficialRedirect())
    req = Request(url, headers={
        "User-Agent": "LOA-Limeira-2027-Auditoria-R10/1.0 (tres links publicos; sem autenticacao)",
        "Accept": "application/pdf,application/octet-stream,application/vnd.openxmlformats-officedocument.wordprocessingml.document,*/*;q=0.2"}, method="GET")
    try:
        with opener.open(req, timeout=TIMEOUT) as response:
            if not valid_final_url(response.geturl()):
                raise ValueError("URL_FINAL_NAO_PERMITIDA")
            row["http"] = int(response.getcode())
            row["content_type"] = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()[:85]
            if row["http"] != 200:
                row["resultado"] = "HTTP_INESPERADO"
                return row
            h = hashlib.sha256()
            first = b""
            complete = False
            total = 0
            while total <= LIMIT:
                chunk = response.read(min(65536, LIMIT + 1 - total))
                if not chunk:
                    complete = True
                    break
                if not first:
                    first = chunk[:128]
                total += len(chunk)
                h.update(chunk)
            row["bytes_lidos"] = total
            row["arquivo_completo"] = complete
            row["assinatura"] = magic(first)
            if total > LIMIT:
                row["resultado"] = "MAIOR_QUE_LIMITE"
            elif row["assinatura"] == "HTML_NAO_DOCUMENTO":
                row["resultado"] = "HTML_NAO_ARQUIVO"
            elif row["assinatura"] in ("PDF", "ZIP_OOXML_POSSIVEL", "JPEG", "PNG") and complete:
                row["resultado"] = "ARQUIVO_PUBLICO_ACESSIVEL"
                row["sha256_completo"] = h.hexdigest()
            else:
                row["resultado"] = "ASSINATURA_NAO_CONFIRMADA"
    except HTTPError as exc:
        row["http"] = exc.code
        row["resultado"] = ("ACESSO_RESTRITO" if exc.code in (401, 403)
                            else "LIMITE_HTTP_429" if exc.code == 429 else "HTTP_ERRO")
        row["erro"] = f"HTTP_{exc.code}"
    except (URLError, ValueError, TimeoutError, OSError) as exc:
        row["resultado"] = "ERRO_DE_ACESSO"
        row["erro"] = (str(exc) if isinstance(exc, ValueError)
                       and str(exc) in ("URL_FINAL_NAO_PERMITIDA",
                                        "REDIRECIONAMENTO_FORA_DOMINIO_OFICIAL")
                       else type(exc).__name__)
    return row

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", default="r10_output")
    parser.add_argument("--ids", nargs="+", choices=IDS, default=list(IDS))
    args = parser.parse_args()
    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for n, identifier in enumerate(args.ids):
        if n:
            time.sleep(2)
        row = probe(identifier)
        rows.append(row)
        print(identifier, row["resultado"], "HTTP", row["http"],
              "assinatura", row["assinatura"])
        if row["http"] == 429:
            rows += [{"id": i, "resultado": "NAO_TENTADO_APOS_HTTP_429"} for i in args.ids[n+1:]]
            break
    data = {"data_utc": datetime.now(timezone.utc).isoformat(),
            "tipo": "R10_TRES_LINKS_PUBLICOS_SEM_RETENCAO_DE_BYTES",
            "limite_por_arquivo": LIMIT, "resultados": rows}
    (out / "resultado.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = ["# R10 — verificação pública de acesso", "",
              "Data UTC: " + data["data_utc"], "",
              "| ID | HTTP | Resultado | Assinatura | Bytes lidos | SHA-256 completo |",
              "|---|---:|---|---|---:|---|"]
    for row in rows:
        report.append("| {} | {} | {} | {} | {} | {} |".format(
            row["id"], row.get("http") or "—", row["resultado"],
            row.get("assinatura") or "—", row.get("bytes_lidos", 0),
            row.get("sha256_completo") or "—"))
    report += ["", "Somente diagnóstico. Sem retenção de documento, cookies, login ou bypass.",
               "URL encontrada em HTML não prova acesso a bytes nem inclusão no universo histórico."]
    (out / "STATUS.md").write_text("\n".join(report) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
