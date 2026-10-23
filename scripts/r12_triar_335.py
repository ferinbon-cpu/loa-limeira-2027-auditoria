#!/usr/bin/env python3
"""R12: triagem pública incremental de 335 IDs observados; sem salvar anexos.

Só lê até 8192 bytes de cada resposta, exclusivamente no host HTTPS oficial.
Não tenta abrir os 977 originais nem os 30 IDs antes identificados.
A correspondência com os 336 históricos NÃO é inferida por estes resultados.
"""
import argparse
import csv
import json
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, HTTPRedirectHandler, build_opener

HOST = "consulta.limeira.sp.leg.br"
ROOT = Path("data/r12")
LIST = ROOT / "ids_335_publicos.txt"
STATE = ROOT / "estado.json"
CAP = 8192
MAX_PER_RUN = 15
MIN_DELAY_SECONDS = 2

class SameOrigin(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        u = urlparse(newurl)
        if u.scheme != "https" or u.hostname != HOST or u.port is not None:
            raise ValueError("REDIRECT_FORA_HOST")
        return super().redirect_request(req, fp, code, msg, headers, newurl)

def now():
    return datetime.now(timezone.utc)

def stamp():
    return now().isoformat(timespec="seconds")

def ids():
    raw = LIST.read_text(encoding="utf-8").splitlines()
    values = [s.strip() for s in raw if s.strip() and not s.lstrip().startswith("#")]
    if (len(values)!=335 or len(set(values))!=335 or "602298" in values
            or not all(re.fullmatch(r"[0-9]{6}",v) for v in values)):
        raise ValueError("UNIVERSO_335_INVALIDO")
    return values

def classify(buf):
    if buf.startswith(b"%PDF-"): return "PDF_ASSINATURA"
    if buf.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")): return "ZIP_OOXML_POSSIVEL"
    if buf.startswith(b"\xff\xd8\xff"): return "JPEG_ASSINATURA"
    if buf.startswith(b"\x89PNG\r\n\x1a\n"): return "PNG_ASSINATURA"
    if buf.startswith(b"GIF87a") or buf.startswith(b"GIF89a"): return "GIF_ASSINATURA"
    if buf.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"): return "OLE_LEGADO_POSSIVEL"
    if buf.lstrip().lower().startswith((b"<html",b"<!doctype html")):
        return "HTML_NAO_ARQUIVO"
    return "NAO_DETERMINADA"

def state_load(identifiers):
    if not STATE.exists():
        return {"schema":1,"criado_utc":stamp(),"pausa_ate_utc":"",
                "ids":{i:{"situacao":"PENDENTE","tentativas":0} for i in identifiers}}
    data=json.loads(STATE.read_text(encoding="utf-8"))
    if data.get("schema")!=1 or set(data.get("ids",{}))!=set(identifiers):
        raise ValueError("ESTADO_ALTERADO_OU_UNIVERSO_DIVERGENTE")
    return data

def eligible(row, instant):
    if row["situacao"] in ("ARQUIVO_ASSINATURA","HTML_NAO_ARQUIVO","BLOQUEADO_401_403",
                             "NAO_ENCONTRADO_404_410","REDIRECT_FORA_HOST","OUTRA_RESPOSTA"):
        return False
    if row["tentativas"]>=2:
        return False
    t=row.get("proxima_tentativa_utc","")
    return not t or datetime.fromisoformat(t)<=instant

def attempt(identifier):
    url=f"https://{HOST}/arquivo?Id={identifier}"
    row={"url":url,"status_http":None,"mime_observado":None,
         "assinatura":"", "bytes_amostrados":0,"avaliacao":"","erro":""}
    opener=build_opener(SameOrigin())
    req=Request(url,headers={
        "User-Agent":"LOA-Limeira-2027-R12-Auditoria-Publica/1.0 (amostra de 8 KiB por ID)",
        "Accept":"application/pdf,image/*,application/octet-stream,*/*;q=0.2"},
        method="GET")
    try:
        with opener.open(req,timeout=20) as response:
            final=urlparse(response.geturl())
            if final.scheme!="https" or final.hostname!=HOST or final.port is not None:
                raise ValueError("REDIRECT_FORA_HOST")
            row["status_http"]=response.getcode()
            row["mime_observado"]=response.headers.get("Content-Type","").split(";",1)[0].strip().lower()[:90]
            preview=response.read(CAP)
            row["bytes_amostrados"]=len(preview)
            row["assinatura"]=classify(preview)
            if row["assinatura"]=="HTML_NAO_ARQUIVO":
                row["avaliacao"]="HTML_NAO_ARQUIVO"
            elif row["assinatura"].endswith(("_ASSINATURA","_POSSIVEL")):
                row["avaliacao"]="ARQUIVO_ASSINATURA"
            else:
                row["avaliacao"]="OUTRA_RESPOSTA"
    except HTTPError as e:
        row["status_http"]=e.code
        row["erro"]="HTTP_"+str(e.code)
        row["avaliacao"]=("BLOQUEADO_401_403" if e.code in (401,403)
                          else "PAUSA_HTTP_429" if e.code==429
                          else "NAO_ENCONTRADO_404_410" if e.code in (404,410)
                          else "FALHA_TEMPORARIA")
    except (URLError, ValueError, TimeoutError, OSError) as e:
        row["erro"]=("REDIRECT_FORA_HOST" if isinstance(e,ValueError) and str(e)=="REDIRECT_FORA_HOST"
                     else type(e).__name__)
        row["avaliacao"]=("REDIRECT_FORA_HOST" if row["erro"]=="REDIRECT_FORA_HOST"
                          else "FALHA_TEMPORARIA")
    return row

def save(data, selected):
    ROOT.mkdir(parents=True,exist_ok=True)
    data["atualizado_utc"]=stamp()
    STATE.write_text(json.dumps(data,ensure_ascii=False,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    fields=["id","situacao","tentativas","status_http","mime_observado","assinatura",
            "bytes_amostrados","ultima_tentativa_utc","proxima_tentativa_utc","erro","url"]
    with (ROOT/"status_335.csv").open("w",newline="",encoding="utf-8-sig") as out:
        w=csv.DictWriter(out,fieldnames=fields,extrasaction="ignore")
        w.writeheader()
        for ident,row in sorted(data["ids"].items(),key=lambda pair:int(pair[0])):
            w.writerow({"id":ident,**row})
    count=Counter(row["situacao"] for row in data["ids"].values())
    report=["# R12 — Triagem incremental de 335 candidatos públicos","",
            "Corte UTC: "+stamp(), "","**Amostra máxima por resposta: 8192 bytes.**",
            "**Nenhum PDF, DOCX ou outro anexo é salvo.**",
            "**A lista não é prova de equivalência com os 336 IDs históricos.**","",
            "## Estados cumulativos"]
    for key in sorted(count):
        report.append(f"- {key}: {count[key]}")
    report += ["","## Esta execução"]
    for ident,row in selected:
        report.append(f"- ID {ident}: {row['situacao']} / HTTP {row.get('status_http') or '—'} / {row.get('assinatura') or '—'}")
    (ROOT/"STATUS.md").write_text("\n".join(report)+"\n",encoding="utf-8")
    (ROOT/"ULTIMA_RODADA.json").write_text(json.dumps({
        "corte_utc":stamp(),"consultados":len(selected),
        "estados":dict(count),"resultados":[{"id":i,"situacao":r["situacao"],"http":r.get("status_http")} for i,r in selected]
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--limit",type=int,default=MAX_PER_RUN)
    args=parser.parse_args()
    if not (1<=args.limit<=MAX_PER_RUN): raise ValueError("LIMITE_INVALIDO")
    identifiers=ids()
    data=state_load(identifiers)
    instant=now()
    pause=data.get("pausa_ate_utc","")
    if pause and datetime.fromisoformat(pause)>instant:
        print("R12_GLOBAL_PAUSE_ATIVA",pause)
        save(data,[])
        return
    due=[i for i in identifiers if eligible(data["ids"][i],instant)]
    selected=[]
    for n,i in enumerate(due[:args.limit]):
        if n: time.sleep(MIN_DELAY_SECONDS)
        result=attempt(i)
        row=data["ids"][i]
        row.update({"situacao":result["avaliacao"],"tentativas":row["tentativas"]+1,
                    "status_http":result["status_http"],"mime_observado":result["mime_observado"],
                    "assinatura":result["assinatura"],"bytes_amostrados":result["bytes_amostrados"],
                    "url":result["url"],"erro":result["erro"],"ultima_tentativa_utc":stamp()})
        if result["avaliacao"]=="FALHA_TEMPORARIA":
            row["proxima_tentativa_utc"]=(now()+timedelta(hours=24)).isoformat()
        selected.append((i,row.copy()))
        print(i,row["situacao"],"HTTP",row["status_http"])
        if result["avaliacao"]=="PAUSA_HTTP_429":
            data["pausa_ate_utc"]=(now()+timedelta(hours=24)).isoformat()
            break
    save(data,selected)
    print(json.dumps({"candidatos":len(identifiers),"consultas":len(selected)},ensure_ascii=False))

if __name__=="__main__":
    main()
