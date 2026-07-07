#!/usr/bin/env python3
"""
radar_merito.py — Radar della giurisprudenza di merito (cassazione-penale-db)

Monitora fonti open access che segnalano provvedimenti di MERITO penale e ne
raccoglie SOLO I FATTI: data, fonte, titolo, link. Nessun contenuto redazionale
viene copiato (i contributi delle riviste restano degli editori; Sistema Penale
e' CC BY-NC-ND). Output: SEGNALATE/RADAR/RADAR_MERITO.md — materiale informativo,
MAI citabile come fonte negli atti: per citare un provvedimento del radar si
scarica il PDF dalla fonte e lo si ingerisce in KB (recupero assistito).

Fonti v1:
  1. Sistema Penale — Osservatorio della giurisprudenza di merito (HTML, pagina 1)
  2. Giurisprudenza Penale — feed RSS, filtrato sui provvedimenti di merito

Regole: dedup per URL (visti.json); fonte irraggiungibile o struttura cambiata ->
log e prosegue con le altre; mai inventare. Uso: radar_merito.py [--dry-run]
"""
import argparse, datetime, json, os, re, sys, time
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RADAR = os.path.join(ROOT, "SEGNALATE", "RADAR")
MD = os.path.join(RADAR, "RADAR_MERITO.md")
VISTI = os.path.join(RADAR, "visti.json")
LOG = os.path.join(ROOT, "SEGNALATE", "LOG_ERRORI.md")
UA = ("cassazione-penale-db/1.0 radar "
      "(+https://github.com/Synthos-Logic/cassazione-penale-db)")
OGGI = datetime.date.today().isoformat()

MESI = {"gennaio":1,"febbraio":2,"marzo":3,"aprile":4,"maggio":5,"giugno":6,
        "luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12}

RE_MERITO = re.compile(
    r"(tribunale|trib\.|corte d.appello|corte d.assise|g\.?i\.?p\.?\b|g\.?u\.?p\.?\b|"
    r"giudice di pace|riesame|corte di appello|procura|merito|sorveglianza)", re.I)

ERRORI = []

def log_err(msg):
    ERRORI.append(f"- {datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} — [radar] {msg}")
    print(f"[radar][ERRORE] {msg}", file=sys.stderr)

HDRS = {"User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9"}

def fetch(url, tentativi=3):
    ultimo = None
    for i in range(tentativi):
        try:
            r = requests.get(url, headers=HDRS, timeout=60)
            r.raise_for_status()
            time.sleep(2)
            return r
        except Exception as e:
            ultimo = e
            time.sleep(8 * (i + 1))  # backoff gentile
    raise ultimo

def data_it(t):
    m = re.search(r"(\d{1,2})\s+([A-Za-zà]+)\s+(\d{4})", t or "")
    if m and m.group(2).lower() in MESI:
        return f"{int(m.group(3)):04d}-{MESI[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None

# ---------------------------------------------------------------- fonte 1: Sistema Penale
def voci_sistemapenale():
    url = "https://www.sistemapenale.it/it/osservatorio-giurisprudenza-di-merito"
    html = fetch(url).text
    soup = BeautifulSoup(html, "html.parser")
    testo = soup.get_text("\n")
    voci = []
    for h in soup.find_all(["h3", "h2"]):
        a = h.find("a", href=True)
        if not a:
            continue
        href = a["href"]
        if not re.search(r"/it/(scheda|notizie|opinioni|articolo|documenti)/", href):
            continue
        titolo = a.get_text(" ", strip=True)
        if not titolo or len(titolo) < 15:
            continue
        # data: cerca all'indietro nel testo precedente l'heading
        prev = h.find_previous(string=re.compile(r"\d{1,2}\s+\w+\s+\d{4}"))
        data = data_it(str(prev)) if prev else None
        if not href.startswith("http"):
            href = "https://www.sistemapenale.it" + href
        voci.append({"data": data or "s.d.", "fonte": "Sistema Penale · Osservatorio merito",
                     "titolo": titolo, "url": href})
    if not voci:
        raise ValueError("nessuna voce estratta: struttura pagina cambiata?")
    return voci

# ---------------------------------------------------------------- fonte 2: Giurisprudenza Penale (RSS)
def voci_giurisprudenzapenale():
    xml = fetch("https://www.giurisprudenzapenale.com/feed/").content
    root = ET.fromstring(xml)
    voci = []
    for item in root.iter("item"):
        titolo = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        cats = " ".join(c.text or "" for c in item.findall("category"))
        pub = item.findtext("pubDate") or ""
        if not titolo or not link:
            continue
        # solo merito: match su titolo o categorie
        if not (RE_MERITO.search(titolo) or RE_MERITO.search(cats)):
            continue
        # pubDate RFC822 -> ISO (best effort)
        m = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", pub)
        mesi_en = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}
        data = (f"{int(m.group(3)):04d}-{mesi_en.get(m.group(2),0):02d}-{int(m.group(1)):02d}"
                if m and m.group(2) in mesi_en else "s.d.")
        voci.append({"data": data, "fonte": "Giurisprudenza Penale",
                     "titolo": titolo, "url": link})
    return voci

# ---------------------------------------------------------------- output
TESTATA = """# RADAR — Giurisprudenza di merito e segnalazioni dalle riviste

> **Materiale informativo, NON citabile negli atti.** Queste sono segnalazioni di
> provvedimenti e contributi pubblicati da riviste scientifiche open access: qui
> compaiono solo data, fonte, titolo e link (i contenuti restano degli editori —
> Sistema Penale è CC BY-NC-ND). Per usare un provvedimento in un atto: apri il
> link, scarica il PDF del provvedimento e ingeriscilo in KB con penalista-archivio
> (da quel momento è citabile col protocollo quote-then-claim).
> Aggiornamento automatico settimanale. Dedup per URL.
"""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-voci", type=int, default=30)
    args = ap.parse_args()

    os.makedirs(RADAR, exist_ok=True)
    visti = set(json.load(open(VISTI))) if os.path.exists(VISTI) else set()
    print(f"== radar merito · {OGGI} · dry_run={args.dry_run} · visti: {len(visti)} ==")

    raccolte = []
    for nome, fn in [("Sistema Penale", voci_sistemapenale),
                     ("Giurisprudenza Penale", voci_giurisprudenzapenale)]:
        try:
            v = fn()
            print(f"[radar] {nome}: {len(v)} voci lette")
            raccolte += v
        except Exception as e:
            log_err(f"{nome}: {e}")

    nuove = [v for v in raccolte if v["url"] not in visti][: args.max_voci]
    for v in nuove:
        print(f"[NUOVA] {v['data']} · {v['fonte']} — {v['titolo'][:80]}")

    if not args.dry_run:
        if nuove:
            corpo = open(MD, encoding="utf-8").read() if os.path.exists(MD) else TESTATA
            blocco = [f"\n## Aggiornamento del {OGGI}\n"]
            for v in sorted(nuove, key=lambda x: x["data"], reverse=True):
                blocco.append(f"- **{v['data']}** · {v['fonte']} — [{v['titolo']}]({v['url']})")
            # inserisce il blocco subito dopo la testata (voci recenti in alto)
            if "\n## " in corpo:
                testa, resto = corpo.split("\n## ", 1)
                corpo = testa + "\n".join(blocco) + "\n\n## " + resto
            else:
                corpo = corpo.rstrip() + "\n" + "\n".join(blocco) + "\n"
            open(MD, "w", encoding="utf-8").write(corpo)
            visti |= {v["url"] for v in nuove}
            json.dump(sorted(visti), open(VISTI, "w", encoding="utf-8"),
                      ensure_ascii=False, indent=0)
        if ERRORI and os.path.exists(LOG):
            t = open(LOG, encoding="utf-8").read().replace("*Nessun errore registrato.*", "").rstrip()
            open(LOG, "w", encoding="utf-8").write(t + "\n\n" + "\n".join(ERRORI) + "\n")

    print(f"\n== RADAR: nuove {len(nuove)} | già viste {len(raccolte)-len(nuove)} | errori {len(ERRORI)} ==")
    if args.dry_run:
        print("(dry-run: nessun file scritto)")

if __name__ == "__main__":
    main()
