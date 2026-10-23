#!/usr/bin/env python3
"""Piloto conservador: somente metadados HTML públicos da Câmara de Limeira.

Não baixa anexos, não usa credenciais e não tenta contornar proteção.
Os IDs só são aceitos quando aparecem em URLs explícitas no HTML.
"""
from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


HOST = "consulta.limeira.sp.leg.br"
USER_AGENT = "LOA-Limeira-2027-Auditoria-Metadados/0.1 (piloto manual; 5 paginas)"
PAGES = (
    ("PL_144_2026", "https://consulta.limeira.sp.leg.br/Documentos/Documento/437627"),
    ("EMENDA_65", "https://consulta.limeira.sp.leg.br/Documentos/Documento/439497"),
    ("EMENDA_110", "https://consulta.limeira.sp.leg.br/Documentos/Documento/439564"),
    ("EMENDA_173", "https://consulta.limeira.sp.leg.br/Documentos/Documento/439673"),
    ("EMENDA_251", "https://consulta.limeira.sp.leg.br/Documentos/Documento/439792"),
)
MAX_HTML_BYTES = 2_000_000
REQUEST_TIMEOUT_SECONDS = 15


class RestrictRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme.lower() != "https" or parsed.hostname != HOST:
            raise ValueError("REDIRECT_FORA_DO_DOMINIO_OFICIAL")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Anchors(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.anchors = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "a":
            return
        data = dict(attrs)
        self.current = {
            "href": data.get("href") or data.get("data-href") or "",
            "title": data.get("title") or "",
            "parts": [],
        }

    def handle_data(self, data):
        if self.current is not None:
            self.current["parts"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            entry = self.current
            entry["text"] = " ".join(entry.pop("parts"))
            self.anchors.append(entry)
            self.current = None


def classify_observed_url(href, source_url):
    if not href or not isinstance(href, str):
        return None
    candidate = urljoin(source_url, html.unescape(href).strip())
    parsed = urlparse(candidate)
    if parsed.scheme.lower() != "https" or parsed.hostname != HOST:
        return None
    path = parsed.path.rstrip("/")
    if path.lower() == "/arquivo":
        queries = parse_qs(parsed.query)
        ids = [v for key, vals in queries.items() if key.lower() == "id" for v in vals]
        if len(ids) == 1 and re.fullmatch(r"[0-9]{1,12}", ids[0]):
            return ("arquivo", ids[0], candidate)
    match = re.fullmatch(r"/Documentos/Documento/([0-9]{1,12})", path, re.IGNORECASE)
    if match:
        return ("documento", match.group(1), candidate)
    return None


def clean_label(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()[:220]


def extract_links(page_html, source_url):
    parser = Anchors()
    parser.feed(page_html)
    rows = []
    seen = set()
    for anchor in parser.anchors:
        item = classify_observed_url(anchor["href"], source_url)
        if not item:
            continue
        kind, file_id, url = item
        key = (kind, file_id, url)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "tipo": kind,
            "id": file_id,
            "nome_exibido": clean_label(anchor["text"] or anchor["title"]),
            "url_oficial_observada": url,
            "fonte_pagina": source_url,
            "metodo": "LINK_HTML_EXPLICITO",
        })
    return rows


def fetch_public_html(url):
    parsed = urlparse(url)
    if parsed.hostname != HOST or parsed.scheme != "https":
        raise ValueError("URL_NAO_PERMITIDA")
    opener = build_opener(RestrictRedirect())
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    with opener.open(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        status = response.getcode()
        content_type = response.headers.get("Content-Type", "")
        if "text/html" not in content_type.lower():
            raise ValueError("RESPOSTA_NAO_HTML: " + content_type[:80])
        raw = response.read(MAX_HTML_BYTES + 1)
        if len(raw) > MAX_HTML_BYTES:
            raise ValueError("PAGINA_MAIOR_QUE_LIMITE")
        encoding = response.headers.get_content_charset() or "utf-8"
        try:
            decoded = raw.decode(encoding, errors="replace")
        except LookupError:
            decoded = raw.decode("utf-8", errors="replace")
        return status, decoded, len(raw)


def save_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = argparse.ArgumentParser(description="Metadados públicos, cinco páginas fixas.")
    args.add_argument("--outdir", default="pilot_output")
    opt = args.parse_args()
    output = Path(opt.outdir)
    output.mkdir(parents=True, exist_ok=True)

    page_results = []
    links = []
    for index, (label, url) in enumerate(PAGES):
        if index:
            time.sleep(1.5)
        result = {"pagina": label, "url": url, "status": "NAO_ACESSADO",
                  "http_status": "", "tamanho_html": 0, "links_arquivo": 0,
                  "links_documento": 0, "erro": ""}
        try:
            code, contents, size = fetch_public_html(url)
            result["http_status"] = code
            result["tamanho_html"] = size
            extracted = extract_links(contents, url)
            for entry in extracted:
                entry["pagina"] = label
            links.extend(extracted)
            result["links_arquivo"] = sum(x["tipo"] == "arquivo" for x in extracted)
            result["links_documento"] = sum(x["tipo"] == "documento" for x in extracted)
            result["status"] = "HTML_PUBLICO_LIDO"
        except HTTPError as exc:
            result["status"] = "HTTP_ERRO"
            result["http_status"] = exc.code
            result["erro"] = "HTTP_" + str(exc.code)
            # 403/429 não devem ser contornados ou retentados.
        except (URLError, ValueError, TimeoutError, OSError) as exc:
            result["status"] = "ERRO_DE_ACESSO"
            result["erro"] = clean_label(type(exc).__name__ + ": " + str(exc))
        page_results.append(result)
        print(label, result["status"], result["http_status"],
              "arquivos=", result["links_arquivo"], "documentos=", result["links_documento"])

    fields = ["pagina", "tipo", "id", "nome_exibido", "url_oficial_observada",
              "fonte_pagina", "metodo"]
    save_csv(output / "links_publicos.csv", links, fields)
    save_csv(output / "paginas_status.csv", page_results,
             ["pagina", "url", "status", "http_status", "tamanho_html",
              "links_arquivo", "links_documento", "erro"])
    files = [x for x in links if x["tipo"] == "arquivo"]
    unique_ids = sorted({x["id"] for x in files}, key=lambda x: int(x))
    manifest = {
        "data_utc": datetime.now(timezone.utc).isoformat(),
        "projeto": "PL 144/2026 — Limeira",
        "tipo": "PILOTO_METADADOS_PUBLICOS_SEM_DOWNLOAD",
        "paginas_planejadas": len(PAGES),
        "paginas_lidas": sum(x["status"] == "HTML_PUBLICO_LIDO" for x in page_results),
        "links_arquivo_observados": len(files),
        "ids_arquivo_distintos_observados": len(unique_ids),
        "ids_arquivo_explicitamente_observados": unique_ids,
        "novos_ids_de_336_pendentes": "NAO_AFERIDO: cruzar com Custodia977 e R03_PENDENTES_30",
        "paginas": page_results,
    }
    (output / "manifesto.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = [
        "# Piloto do portal da Câmara — PL 144/2026",
        "",
        "Tentativa em UTC: " + manifest["data_utc"],
        "Páginas públicas lidas: " + str(manifest["paginas_lidas"]) + "/5",
        "IDs de arquivo explícitos e distintos: " + str(len(unique_ids)),
        "Nenhum anexo foi baixado. Nenhum mecanismo de acesso foi contornado.",
        "Um ID observado aqui NÃO é automaticamente um dos 336 ausentes.",
        "Cruzar com os índices do Drive SME antes de atualizar o controle R04.",
        "",
        "## Páginas",
    ]
    for p in page_results:
        summary.append("- " + p["pagina"] + ": " + p["status"] +
                       ", HTTP=" + str(p["http_status"]) +
                       ", arquivos=" + str(p["links_arquivo"]) +
                       (", erro=" + p["erro"] if p["erro"] else ""))
    (output / "RESUMO.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(json.dumps({"paginas_lidas": manifest["paginas_lidas"],
                      "ids_distintos": len(unique_ids)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
