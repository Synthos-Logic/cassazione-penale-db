#!/usr/bin/env python3
"""
radar_merito.py — Radar della giurisprudenza di merito (cassazione-penale-db)

Monitora fonti open access che segnalano provvedimenti di MERITO penale e ne
raccoglie SOLO I FATTI: data, fonte, titolo, link. Nessun contenuto redazionale
viene copiato (i contributi delle riviste restano degli editori; Sistema Penale
e' CC BY-NC-ND). Output: SEGNALATE/RADAR/RADAR_MERITO.md — materiale informativo,
MAI citabile come fonte negli atti: per citare un provvedimento del radar si
scarica il PDF dalla fonte e lo si ingerisce in KB (recupero assistito).

Fonti v3:
  1. Sistema Penale — Osservatorio della giurisprudenza di merito (HTML, pagina 1)
  2. Giurisprudenza Penale — feed RSS, filtrato sui provvedimenti di merito
  3. Diritto di Difesa (UCPI) — feed RSS, tutte le voci
  4. La Legislazione Penale — feed RSS, tutte le voci
  5. DisCrimen — feed RSS, tutte le voci
  6. Penale Diritto e Procedura — feed RSS, tutte le voci
  7. Archivio Penale — parser HTML dedicato: sezioni giurisprudenza (legittimita,
     costituzionale, merito, europea) + articoli open access dalla home

Regole: dedup per URL (visti.json); fonte irraggiungibile o struttura cambiata ->
log e prosegue con le altre; mai inventare. Uso: radar_merito.py [--dry-run]
"""
import argparse, datetime, json, os, re, sys, time
from html import unescape
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
        "luglio":7,"agosto":8,"settembre":9,"ottobre":10,"novembre":11,"dicembre":12,
        # il CMS di Archivio Penale usa i mesi inglesi ("Pubblicato il 10 July 2026")
        "january":1,"february":2,"march":3,"april":4,"may":5,"june":6,
        "july":7,"august":8,"september":9,"october":10,"november":11,"december":12}

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
    """La struttura della pagina cambia nel tempo (7/2026: i titoli non sono
    piu heading h2/h3 con <a> interno). Strategia robusta: si scandiscono TUTTI i
    link della pagina che puntano a contenuti (/it/scheda|notizie|opinioni|...),
    tenendo solo quelli con un titolo vero (>= 15 caratteri: esclude icone e menu)."""
    url = "https://www.sistemapenale.it/it/osservatorio-giurisprudenza-di-merito"
    html = fetch(url).text
    soup = BeautifulSoup(html, "html.parser")
    voci, gia = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.search(r"/it/(scheda|notizie|opinioni|articolo|documenti)/", href):
            continue
        titolo = a.get_text(" ", strip=True)
        if not titolo or len(titolo) < 15:
            continue
        if not href.startswith("http"):
            href = "https://www.sistemapenale.it" + href
        if href in gia:
            continue
        gia.add(href)
        # data: cerca all'indietro nel testo che precede il link
        prev = a.find_previous(string=re.compile(r"\d{1,2}\s+\w+\s+\d{4}"))
        data = data_it(str(prev)) if prev else None
        voci.append({"data": data or "s.d.", "fonte": "Sistema Penale · Osservatorio merito",
                     "titolo": titolo, "url": href})
    if not voci:
        n_link = len(soup.find_all("a", href=True))
        raise ValueError(f"nessuna voce estratta ({len(html)} byte, {n_link} link totali): "
                         "struttura pagina cambiata o blocco anti-bot verso il runner?")
    return voci

# ---------------------------------------------------------------- fonti RSS (riviste)
MESI_EN = {"Jan":1,"Feb":2,"Mar":3,"Apr":4,"May":5,"Jun":6,"Jul":7,"Aug":8,"Sep":9,"Oct":10,"Nov":11,"Dec":12}

def _items_da_regex(testo):
    """Fallback tollerante per feed con XML sporco (entita non dichiarate, tag
    non chiusi): estrae gli <item> a regex. Copre i feed WordPress reali."""
    def campo(blocco, tag):
        m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", blocco, re.S | re.I)
        if not m:
            return ""
        v = m.group(1).strip()
        v = re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", v, flags=re.S).strip()
        return unescape(v)
    items = []
    for blocco in re.findall(r"<item>(.*?)</item>", testo, re.S | re.I):
        cats = " ".join(re.findall(
            r"<category[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</category>", blocco, re.S | re.I))
        items.append({"title": campo(blocco, "title"), "link": campo(blocco, "link"),
                      "cats": unescape(cats), "pub": campo(blocco, "pubDate")})
    return items

def voci_rss(url, fonte, filtro=None):
    """Lettore generico di feed RSS (WordPress e simili). Prova il parser XML
    strict; su XML sporco ripiega sul fallback a regex. Se filtro (regex)
    presente, tiene solo le voci che lo soddisfano su titolo o categorie."""
    contenuto = fetch(url).content
    try:
        root = ET.fromstring(contenuto)
        items = [{"title": (i.findtext("title") or ""),
                  "link": (i.findtext("link") or ""),
                  "cats": " ".join(c.text or "" for c in i.findall("category")),
                  "pub": i.findtext("pubDate") or ""} for i in root.iter("item")]
    except ET.ParseError:
        items = _items_da_regex(contenuto.decode("utf-8", errors="replace"))
        if not items:
            raise ValueError(f"nessun item nel feed ({len(contenuto)} byte scaricati: "
                             "blocco anti-bot o struttura cambiata?)")
    voci = []
    for it in items:
        titolo, link, cats, pub = (it["title"].strip(), it["link"].strip(),
                                   it["cats"], it["pub"])
        if not titolo or not link:
            continue
        if filtro and not (filtro.search(titolo) or filtro.search(cats)):
            continue
        # pubDate RFC822 -> ISO (best effort)
        m = re.search(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", pub)
        data = (f"{int(m.group(3)):04d}-{MESI_EN.get(m.group(2),0):02d}-{int(m.group(1)):02d}"
                if m and m.group(2) in MESI_EN else "s.d.")
        voci.append({"data": data, "fonte": fonte, "titolo": titolo, "url": link})
    return voci

def voci_giurisprudenzapenale():
    # solo merito: GP pubblica moltissimo, senza filtro il radar si riempirebbe di rumore
    return voci_rss("https://www.giurisprudenzapenale.com/feed/",
                    "Giurisprudenza Penale", filtro=RE_MERITO)

# ---------------------------------------------------------------- fonte 7: Archivio Penale (HTML dedicato)
AP_BASE = "https://archiviopenale.it"
# pagine statiche del sito che vivono anch\u2019esse sotto /contenuti/ (menu, crediti):
AP_STATICI = re.compile(r"/(istruzioni-per-invio|norme-redazionali|codice-etico|"
                        r"peer-review|crediti|indicizzazione-e-diffusione)/contenuti/")

def _voci_ap_pagina(url, fonte, pattern, con_data=False):
    """Estrae da una pagina di Archivio Penale i link che rispettano `pattern`.
    I titoli delle voci di giurisprudenza contengono gia gli estremi del
    provvedimento; la data di pubblicazione compare solo per gli articoli
    (testo "Pubblicato il ..." dopo il link) -> `con_data`."""
    html = fetch(url).text
    soup = BeautifulSoup(html, "html.parser")
    voci, gia = [], set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.search(pattern, href) or AP_STATICI.search(href):
            continue
        titolo = a.get_text(" ", strip=True)
        if not titolo or len(titolo) < 20:
            continue
        if not href.startswith("http"):
            href = AP_BASE + href
        if href in gia:
            continue
        gia.add(href)
        data = None
        if con_data:
            nxt = a.find_next(string=re.compile(r"Pubblicato il\s+\d{1,2}\s+\w+\s+\d{4}"))
            data = data_it(str(nxt)) if nxt else None
        voci.append({"data": data or "s.d.", "fonte": fonte,
                     "titolo": titolo, "url": href})
    return voci

def voci_archiviopenale():
    sezioni = [
        (AP_BASE + "/giurisprudenza-di-legittimita/sezioni/15",
         "Archivio Penale · Legittimità"),
        (AP_BASE + "/giurisprudenza-costituzionale/sezioni/390",
         "Archivio Penale · Costituzionale"),
        (AP_BASE + "/giurisprudenza-di-merito/sezioni/405",
         "Archivio Penale · Merito"),
        (AP_BASE + "/giurisprudenza-europea/sezioni/400",
         "Archivio Penale · Europea"),
    ]
    voci = []
    for url, fonte in sezioni:
        try:
            v = _voci_ap_pagina(url, fonte, r"/contenuti/\d+$")
            print(f"[radar]   {fonte}: {len(v)} voci")
            voci += v
        except Exception as e:
            log_err(f"{fonte}: {e}")
    # articoli open access (dottrina) dalla home, con data di pubblicazione
    try:
        v = _voci_ap_pagina(AP_BASE + "/", "Archivio Penale · Articoli",
                            r"/articoli/\d+$", con_data=True)
        print(f"[radar]   Archivio Penale · Articoli: {len(v)} voci")
        voci += v
    except Exception as e:
        log_err(f"Archivio Penale · Articoli: {e}")
    if not voci:
        raise ValueError("nessuna voce estratta dalle sezioni: "
                         "struttura cambiata o blocco anti-bot verso il runner?")
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
    ap.add_argument("--max-voci", type=int, default=150)
    args = ap.parse_args()

    os.makedirs(RADAR, exist_ok=True)
    visti = set(json.load(open(VISTI))) if os.path.exists(VISTI) else set()
    print(f"== radar merito · {OGGI} · dry_run={args.dry_run} · visti: {len(visti)} ==")

    raccolte = []
    fonti = [
        ("Sistema Penale", voci_sistemapenale),
        ("Giurisprudenza Penale", voci_giurisprudenzapenale),
        ("Diritto di Difesa", lambda: voci_rss(
            "https://dirittodidifesa.eu/feed/", "Diritto di Difesa (UCPI)")),
        ("La Legislazione Penale", lambda: voci_rss(
            "https://www.lalegislazionepenale.eu/feed/", "La Legislazione Penale")),
        ("DisCrimen", lambda: voci_rss(
            "https://discrimen.it/feed/", "DisCrimen")),
        ("Penale Diritto e Procedura", lambda: voci_rss(
            "https://www.penaledp.it/feed/", "Penale Diritto e Procedura")),
        ("Archivio Penale", voci_archiviopenale),
    ]
    for nome, fn in fonti:
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
