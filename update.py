"""Atualiza data.json com indicadores e manchetes. Roda no GitHub Actions."""
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; FarolBot/1.0)"}
MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

FEEDS = [
    ("g1", "https://g1.globo.com/rss/g1/economia/"),
    ("InfoMoney", "https://www.infomoney.com.br/feed/"),
    ("Agência Brasil", "https://agenciabrasil.ebc.com.br/rss/economia/feed.xml"),
]


def get(url, timeout=25):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def bcb(code, n=1):
    url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados/ultimos/{n}?formato=json"
    return json.loads(get(url))


def yahoo(symbol):
    """Retorna (preço atual, variação % sobre o fechamento anterior)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=5d&interval=1d"
    res = json.loads(get(url))["chart"]["result"][0]
    closes = [c for c in res["indicators"]["quote"][0]["close"] if c is not None]
    price = closes[-1]
    var = (price / closes[-2] - 1) * 100 if len(closes) >= 2 else None
    return price, var


def carregar_antigo():
    try:
        with open("data.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def coletar_indicadores(antigo):
    ind = dict(antigo.get("indicadores", {}))

    try:
        ind["selic"] = {"valor": float(bcb(432)[-1]["valor"])}
    except Exception as e:
        print("Selic falhou:", e)

    try:
        ultimo = bcb(13522)[-1]
        mes = int(ultimo["data"][3:5])
        ano = ultimo["data"][6:]
        ind["ipca12"] = {"valor": float(ultimo["valor"]), "mes": f"{MESES[mes - 1]}/{ano}"}
    except Exception as e:
        print("IPCA falhou:", e)

    try:
        preco, var = yahoo("BRL=X")
        ind["dolar"] = {"valor": round(preco, 4), "variacao": None if var is None else round(var, 2)}
    except Exception as e:
        print("Dólar (Yahoo) falhou:", e)
        try:
            serie = bcb(1, 2)
            preco = float(serie[-1]["valor"])
            var = (preco / float(serie[-2]["valor"]) - 1) * 100
            ind["dolar"] = {"valor": round(preco, 4), "variacao": round(var, 2)}
        except Exception as e2:
            print("Dólar (BCB) falhou:", e2)

    try:
        preco, var = yahoo("%5EBVSP")
        ind["ibov"] = {"valor": round(preco), "variacao": None if var is None else round(var, 2)}
    except Exception as e:
        print("Ibovespa falhou:", e)

    return ind


def humor(ind):
    movimentos = []
    for chave in ("ibov", "dolar"):
        v = (ind.get(chave) or {}).get("variacao")
        if v is not None:
            movimentos.append(abs(v))
    return "agitado" if movimentos and max(movimentos) >= 1.5 else "calmo"


def coletar_manchetes(antigo):
    itens = []
    for fonte, url in FEEDS:
        try:
            raiz = ET.fromstring(get(url))
            doados = 0
            for it in raiz.iter("item"):
                titulo = html.unescape((it.findtext("title") or "")).strip()
                titulo = re.sub(r"\s+", " ", titulo)
                link = (it.findtext("link") or "").strip()
                data = it.findtext("pubDate")
                if not titulo or not link.startswith("http"):
                    continue
                try:
                    quando = parsedate_to_datetime(data).astimezone(TZ)
                except Exception:
                    continue
                itens.append({"titulo": titulo, "fonte": fonte, "url": link, "hora": quando.isoformat()})
                doados += 1
                if doados >= 4:
                    break
        except Exception as e:
            print(f"Feed {fonte} falhou:", e)
    itens.sort(key=lambda x: x["hora"], reverse=True)
    vistos, final = set(), []
    for it in itens:
        chave = it["titulo"].lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        final.append(it)
        if len(final) >= 6:
            break
    return final or antigo.get("manchetes", [])


def main():
    antigo = carregar_antigo()
    ind = coletar_indicadores(antigo)
    dados = {
        "atualizadoEm": datetime.now(TZ).isoformat(timespec="minutes"),
        "humor": humor(ind),
        "indicadores": ind,
        "manchetes": coletar_manchetes(antigo),
    }
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(dados, f, ensure_ascii=False, indent=2)
    print("data.json atualizado em", dados["atualizadoEm"])


if __name__ == "__main__":
    main()
