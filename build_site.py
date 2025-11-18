# -*- coding: utf-8 -*-
"""
build_site.py

Genera:
- /index.html                      (portada)
- /ZonasEscolares/index.html       (listado de excels y mapas + filtros)
- /Intersecciones/index.html       (listado de excels y mapas + filtros, con UBIGEO desde catálogo)
- /EstablecimientoSalud/index.html (listado de excels y mapas + filtros, con UBIGEO desde catálogo)

Lee:
- content/home_title.txt,  content/home_body.txt
- content/zonas_title.txt, content/zonas_body.txt
- content/inter_title.txt, content/inter_body.txt
- content/estab_title.txt, content/estab_body.txt
- assets/img/logo.jpg, assets/img/home.jpg, assets/img/zonas.jpg, assets/img/inter.jpg, assets/img/estab.jpg
- data/municipalidades_catalog.csv (para Zonas y para mapear UBIGEO en Inter/Estab)

Reglas:
- En Zonas/Intersecciones/Establecimientos: botón ← Regresar; Excel descarga; Mapa abre en nueva pestaña.
- Zonas: usa catálogo y SOLO lista filas cuyo Excel exista.
- Intersecciones y Establecimientos: escanean /<sección>/excels y buscan UBIGEO en el catálogo por slug (y fallback por componentes).
- Si el mapa no existe, el botón aparece deshabilitado.
- Filtros: Departamento + Provincia + Distrito + UBIGEO (AND). Comparación ignora espacios y guiones bajos.
"""

from pathlib import Path
import pandas as pd
import html

# ---------- Config ----------
ROOT = Path(".")
ASSETS_IMG = ROOT / "assets" / "img"
CONTENT = ROOT / "content"
DATA = ROOT / "data"

LOGO_PATH  = ASSETS_IMG / "logo.jpg"
HOME_IMG   = ASSETS_IMG / "home.jpg"
ZONAS_IMG  = ASSETS_IMG / "zonas.jpg"
INTER_IMG  = ASSETS_IMG / "inter.jpg"
ESTAB_IMG  = ASSETS_IMG / "estab.jpg"  # opcional

CATALOG_CSV = DATA / "municipalidades_catalog.csv"

ZONAS_DIR = ROOT / "ZonasEscolares"
INTER_DIR = ROOT / "Intersecciones"
ESTAB_DIR = ROOT / "EstablecimientoSalud"

HOME_HTML  = ROOT / "index.html"
ZONAS_HTML = ZONAS_DIR / "index.html"
INTER_HTML = INTER_DIR / "index.html"
ESTAB_HTML = ESTAB_DIR / "index.html"

# ---------- Util ----------
def read_txt(path: Path, default: str = "") -> str:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    return default

def esc(s: str) -> str:
    return html.escape(s or "")

def ensure_dirs():
    ZONAS_DIR.mkdir(parents=True, exist_ok=True)
    INTER_DIR.mkdir(parents=True, exist_ok=True)
    ESTAB_DIR.mkdir(parents=True, exist_ok=True)

def css_block():
    # Parche: imágenes hero SIN recorte + estilos del filtro y botones.
    return """
    <style>
      :root {
        --blue:#1d4ed8; --sky:#7dd3fc; --bg:#f7f7fb; --fg:#111827;
        --green:#16a34a; --orange:#f97316; --dark:#111827;
      }
      * { box-sizing:border-box; }
      body { margin:0; font-family: system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; background:var(--bg); color:var(--fg); }
      header { position:relative; padding:18px 20px; background:#fff; box-shadow:0 2px 8px rgba(0,0,0,0.06); }
      .logo { position:absolute; right:20px; top:12px; height:48px; width:auto; border-radius:6px; object-fit:contain; }
      .container { max-width:1100px; margin:0 auto; padding:24px 16px; }
      h1 { margin-top:8px; font-size: clamp(22px, 3.2vw, 34px); }
      p  { font-size: clamp(14px, 2vw, 16px); line-height:1.6; }

      /* >>> Parche hero sin recorte <<< */
      .hero {
        display:block;
        width:100%;
        height:auto;
        max-height:80vh;
        border-radius:14px;
        box-shadow:0 6px 16px rgba(0,0,0,0.08);
        object-fit:contain;
      }

      .buttons { display:flex; flex-wrap:wrap; gap:12px; margin:18px 0 6px; }
      .btn {
        display:inline-block; padding:12px 16px; border-radius:12px;
        text-decoration:none; color:#fff; font-weight:600;
        transition: transform .08s ease, box-shadow .2s ease;
      }
      .btn:hover { transform: translateY(-1px); }
      .btn.zonas { background: var(--green); box-shadow:0 4px 12px rgba(22,163,74,0.30); }
      .btn.zonas:hover { box-shadow:0 8px 18px rgba(22,163,74,0.35); }
      .btn.inter { background: var(--orange); box-shadow:0 4px 12px rgba(249,115,22,0.30); }
      .btn.inter:hover { box-shadow:0 8px 18px rgba(249,115,22,0.35); }
      .btn.estab { background: var(--blue); box-shadow:0 4px 12px rgba(29,78,216,0.30); }
      .btn.estab:hover { box-shadow:0 8px 18px rgba(29,78,216,0.35); }

      .disabled { opacity:.5; pointer-events:none; filter:grayscale(0.3); }
      .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap:14px; margin-top:14px; }
      .card {
        background:#fff; border-radius:14px; padding:14px;
        box-shadow:0 4px 12px rgba(0,0,0,0.06);
      }
      .card h3 { margin:4px 0 10px; font-size:18px; }
      .card .row { display:flex; gap:10px; }
      .card a, .card span.btn-like {
        flex:1; text-align:center; font-weight:600; padding:10px;
        border-radius:10px; text-decoration:none; display:inline-block;
      }
      .dl { background:var(--dark); color:#fff; }
      .map { background:#ffffff; color:var(--blue); border:1px solid var(--blue); }
      .btn-like { background:#e5e7eb; color:#6b7280; border:1px solid #e5e7eb; }
      .back {
        position: fixed; top: 14px; left: 14px; z-index: 9999;
        background:#fff; border:1px solid #e5e7eb; border-radius:10px; padding:8px 12px;
        text-decoration:none; font-weight:600; color:#111827;
        box-shadow:0 2px 8px rgba(0,0,0,0.08);
      }
      .muted { color:#6b7280; font-size:13px; margin-top:4px; }
      footer { padding:18px; text-align:center; color:#6b7280; font-size:13px; }

      /* ----- Barra de filtros ----- */
      .filters {
        display:flex; flex-wrap:wrap; gap:8px; align-items:center;
        background:#fff; border:1px solid #e5e7eb; border-radius:12px; padding:10px;
        box-shadow:0 2px 8px rgba(0,0,0,0.06); margin:12px 0;
      }
      .filters label { font-size:13px; color:#374151; }
      .filters input {
        flex: 1 1 200px;
        border:1px solid #e5e7eb; border-radius:8px; padding:8px 10px; font-size:14px;
      }
      .filters .actions { display:flex; gap:8px; margin-left:auto; }
      .filters .actions button {
        border:0; border-radius:10px; padding:8px 12px; font-weight:700; cursor:pointer;
      }
      .filters .actions .primary { background: var(--dark); color:#fff; }
      .filters .actions .accent  { background: var(--blue); color:#fff; }
      .filters .actions .secondary { background:#e5e7eb; color:#111827; }

      @media (max-width: 700px) {
        .filters { gap:10px; }
        .filters .actions { width:100%; justify-content:flex-end; flex-wrap:wrap; }
      }
      @media (max-width: 480px) {
        .logo { height:40px; top:10px; }
      }
    </style>
    """

def header_block(title_text: str, base_prefix: str = "") -> str:
    logo_html = f'<img class="logo" src="{base_prefix}{LOGO_PATH.as_posix()}" alt="logo">' if LOGO_PATH.exists() else ""
    return f"""
    <header>
      {logo_html}
      <div class="container">
        <h1>{esc(title_text)}</h1>
      </div>
    </header>
    """

def hero_img_html(base_prefix: str, path: Path, alt: str) -> str:
    return f'<img class="hero" src="{base_prefix}{path.as_posix()}" alt="{esc(alt)}">' if path.exists() else ""

# ---------- Filtros (UI + JS) ----------
def filters_block() -> str:
    # Script espera DOMContentLoaded y recoge tarjetas en cada acción.
    return """
    <div class="filters">
      <label>Departamento</label>
      <input id="f_dep" type="text" placeholder="Ejem: Lima">
      <label>Provincia</label>
      <input id="f_prov" type="text" placeholder="Ejem: Lima">
      <label>Distrito</label>
      <input id="f_dist" type="text" placeholder="Ejem: San Juan de Lurigancho">
      <label>UBIGEO</label>
      <input id="f_ubi" type="text" placeholder="Ejem: 060101">

      <div class="actions">
        <button id="f_apply" class="primary">Buscar</button>
        <button id="f_top" class="accent">Traer coincidencias arriba</button>
        <button id="f_clear" class="secondary">Limpiar</button>
      </div>
    </div>
    <script>
      (function(){
        function norm(s){
          return (s || '').toLowerCase().replace(/\\s+|_/g, '');
        }
        function getCards(){
          var grid = document.querySelector('.grid');
          return grid ? Array.from(grid.querySelectorAll('.card')) : [];
        }
        function ensureNormalizedAttrs(card){
          ['data-dep','data-prov','data-dist','data-ubi'].forEach(function(attr){
            var v = card.getAttribute(attr) || '';
            card.setAttribute(attr, norm(v));
          });
        }
        function matchCard(card, q){
          var d = card.getAttribute('data-dep')  || '';
          var p = card.getAttribute('data-prov') || '';
          var t = card.getAttribute('data-dist') || '';
          var u = card.getAttribute('data-ubi')  || '';
          var ok = true;
          if(q.dep  && d.indexOf(q.dep)  === -1) ok = false;
          if(q.prov && p.indexOf(q.prov) === -1) ok = false;
          if(q.dist && t.indexOf(q.dist) === -1) ok = false;
          if(q.ubi  && u.indexOf(q.ubi)  === -1) ok = false;
          return ok;
        }
        function queryValues(){
          var dep  = document.getElementById('f_dep');
          var prov = document.getElementById('f_prov');
          var dist = document.getElementById('f_dist');
          var ubi  = document.getElementById('f_ubi');
          return { dep: norm(dep.value), prov: norm(prov.value), dist: norm(dist.value), ubi: norm(ubi.value) };
        }

        document.addEventListener('DOMContentLoaded', function(){
          var applyBtn = document.getElementById('f_apply');
          var topBtn   = document.getElementById('f_top');
          var clearBtn = document.getElementById('f_clear');

          function applyHide(){
            var q = queryValues();
            var cards = getCards();
            cards.forEach(ensureNormalizedAttrs);
            cards.forEach(function(card){
              card.style.display = matchCard(card, q) ? '' : 'none';
            });
          }

          function bringTop(){
            var q = queryValues();
            var grid = document.querySelector('.grid');
            if(!grid) return;
            var cards = getCards();
            cards.forEach(ensureNormalizedAttrs);
            var matches = [], rest = [];
            cards.forEach(function(card){
              (matchCard(card, q) ? matches : rest).push(card);
              card.style.display = ''; // mostrar todos, solo reordenar
            });
            matches.concat(rest).forEach(function(card){ grid.appendChild(card); });
          }

          function clearAll(){
            var dep  = document.getElementById('f_dep');
            var prov = document.getElementById('f_prov');
            var dist = document.getElementById('f_dist');
            var ubi  = document.getElementById('f_ubi');
            dep.value = prov.value = dist.value = ubi.value = '';
            getCards().forEach(function(card){ card.style.display = ''; });
          }

          applyBtn.addEventListener('click', applyHide);
          topBtn.addEventListener('click', bringTop);
          clearBtn.addEventListener('click', clearAll);

          ['f_dep','f_prov','f_dist','f_ubi'].forEach(function(id){
            var el = document.getElementById(id);
            el.addEventListener('keydown', function(ev){ if(ev.key === 'Enter') applyHide(); });
          });
        });
      })();
    </script>
    """

# ---------- HTML pages ----------
def home_html(title_text: str, body_text: str) -> str:
    base = ""  # raíz
    hero_html = hero_img_html(base, HOME_IMG, "imagen")
    return f"""
    <!doctype html><html lang="es"><head>
      <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{esc(title_text)}</title>
      {css_block()}
    </head><body>
      {header_block(title_text, base_prefix=base)}
      <div class="container">
        <p>{esc(body_text)}</p>
        <div style="margin:14px 0 18px;">{hero_html}</div>
        <div class="buttons">
          <a class="btn zonas" href="ZonasEscolares/index.html">Zonas Escolares</a>
          <a class="btn inter" href="Intersecciones/index.html">Intersecciones</a>
          <a class="btn estab" href="EstablecimientoSalud/index.html">Establecimientos de Salud</a>
        </div>
      </div>
      <footer>PI 2026 · Dirección de Seguridad Vial — Generado automáticamente</footer>
    </body></html>
    """

def zonas_html(title_text: str, body_text: str, items: list) -> str:
    base = "../"  # /ZonasEscolares/
    hero_html = hero_img_html(base, ZONAS_IMG, "zonas")
    cards = []
    for it in items:
        titulo    = esc(it.get("titulo") or it.get("slug") or it.get("ubigeo") or "")
        excel_rel = it.get("excel_rel") or "#"
        mapa_rel  = it.get("mapa_rel")  or "#"
        has_excel = bool(it.get("has_excel"))
        has_map   = bool(it.get("has_map"))

        data_dep  = esc(it.get("data_dep",""))
        data_prov = esc(it.get("data_prov",""))
        data_dist = esc(it.get("data_dist",""))
        data_ubi  = esc(it.get("data_ubi",""))

        excel_btn = (f'<a class="dl" href="{excel_rel}" download>Descargar Excel</a>'
                     if has_excel else '<span class="btn-like disabled">Sin Excel</span>')
        map_btn   = (f'<a class="map" href="{mapa_rel}" target="_blank" rel="noopener">Abrir mapa</a>'
                     if has_map else '<span class="btn-like disabled">Mapa no disponible</span>')

        detail_html = f'<div class="muted">UBIGEO: {data_ubi}</div>' if data_ubi else ''

        cards.append(f"""
          <div class="card" data-dep="{data_dep}" data-prov="{data_prov}" data-dist="{data_dist}" data-ubi="{data_ubi}">
            <h3>{titulo}</h3>
            <div class="row">
              {excel_btn}
              {map_btn}
            </div>
            {detail_html}
          </div>
        """)
    cards_html = "\n".join(cards)
    return f"""
    <!doctype html><html lang="es"><head>
      <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{esc(title_text)}</title>
      {css_block()}
    </head><body>
      <a class="back" href="../index.html">← Regresar</a>
      {header_block(title_text, base_prefix=base)}
      <div class="container">
        <p>{esc(body_text)}</p>
        <div style="margin:14px 0 18px;">{hero_html}</div>

        {filters_block()}

        <div class="grid">
          {cards_html}
        </div>
      </div>
      <footer>PI 2026 · Dirección de Seguridad Vial — Generado automáticamente</footer>
    </body></html>
    """

def list_page_html(title_text: str, body_text: str, items: list, hero_img_path: Path, base="../"):
    hero_html = hero_img_html(base, hero_img_path, "imagen")
    cards = []
    for it in items:
        titulo    = esc(it.get("titulo") or it.get("slug") or it.get("ubigeo") or it.get("name") or "")
        excel_rel = it.get("excel_rel") or "#"
        mapa_rel  = it.get("mapa_rel")  or "#"
        has_excel = bool(it.get("has_excel"))
        has_map   = bool(it.get("has_map"))

        data_dep  = esc(it.get("data_dep",""))
        data_prov = esc(it.get("data_prov",""))
        data_dist = esc(it.get("data_dist",""))
        data_ubi  = esc(it.get("data_ubi",""))  # ahora poblado desde catálogo

        excel_btn = (f'<a class="dl" href="{excel_rel}" download>Descargar Excel</a>'
                     if has_excel else '<span class="btn-like disabled">Sin Excel</span>')
        map_btn   = (f'<a class="map" href="{mapa_rel}" target="_blank" rel="noopener">Abrir mapa</a>'
                     if has_map else '<span class="btn-like disabled">Mapa no disponible</span>')

        # << NUEVO >> Mostrar UBIGEO en la tarjeta (igual que Zonas)
        detail_html = f'<div class="muted">UBIGEO: {data_ubi}</div>' if data_ubi else ''

        cards.append(f"""
          <div class="card" data-dep="{data_dep}" data-prov="{data_prov}" data-dist="{data_dist}" data-ubi="{data_ubi}">
            <h3>{titulo}</h3>
            <div class="row">
              {excel_btn}
              {map_btn}
            </div>
            {detail_html}
          </div>
        """)
    cards_html = "\n".join(cards)
    return f"""
    <!doctype html><html lang="es"><head>
      <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{esc(title_text)}</title>
      {css_block()}
    </head><body>
      <a class="back" href="../index.html">← Regresar</a>
      {header_block(title_text, base_prefix=base)}
      <div class="container">
        <p>{esc(body_text)}</p>
        <div style="margin:14px 0 18px;">{hero_html}</div>

        {filters_block()}

        <div class="grid">
          {cards_html}
        </div>
      </div>
      <footer>PI 2026 · Dirección de Seguridad Vial — Generado automáticamente</footer>
    </body></html>
    """

# ---------- Normalización / helpers ----------
def _split_slug(name: str):
    # name tipo "DEPARTAMENTO-PROVINCIA-DISTRITO" (puede traer _ en el distrito)
    parts = (name or "").split("-")
    dep  = parts[0] if len(parts) > 0 else ""
    prov = parts[1] if len(parts) > 1 else ""
    dist = parts[2] if len(parts) > 2 else ""
    return dep, prov, dist

def _norm_for_key(s: str) -> str:
    # minúsculas y sin espacios/guiones bajos para comparación robusta
    return (s or "").lower().replace(" ", "").replace("_", "")

def _key_from_parts(dep: str, prov: str, dist: str) -> str:
    return "|".join([_norm_for_key(dep), _norm_for_key(prov), _norm_for_key(dist)])

# ---------- Índices de catálogo para UBIGEO ----------
def _load_catalog_index():
    """
    Devuelve dos índices:
      - idx_slug:   { slug_lower : ubigeo }
      - idx_parts:  { "dep|prov|dist" (normalizado) : ubigeo }
    """
    if not CATALOG_CSV.exists():
        return {}, {}
    df = pd.read_csv(CATALOG_CSV, dtype=str).fillna("")
    if "slug" not in df.columns:
        df["slug"] = ""
    if "ubigeo" not in df.columns:
        df["ubigeo"] = ""

    idx_slug = {}
    idx_parts = {}
    for _, r in df.iterrows():
        slug = (r.get("slug") or "").strip()
        ubi  = (r.get("ubigeo") or "").strip()
        if slug:
            idx_slug[slug.lower()] = ubi
            dep, prov, dist = _split_slug(slug)
            key = _key_from_parts(dep, prov, dist)
            idx_parts[key] = ubi
        else:
            # Si no hay slug, intenta con columnas depart/prov/dist si existen
            dep = (r.get("departamento") or "").strip()
            prov = (r.get("provincia") or "").strip()
            dist = (r.get("distrito") or "").strip()
            if any([dep, prov, dist]):
                key = _key_from_parts(dep, prov, dist)
                idx_parts[key] = ubi
    return idx_slug, idx_parts

# ---------- Carga catálogo & prepara items (ZONAS) ----------
def load_catalog_zonas():
    if not CATALOG_CSV.exists():
        raise FileNotFoundError(f"No se encuentra {CATALOG_CSV}")
    df = pd.read_csv(CATALOG_CSV, dtype=str).fillna("")
    for c in ["ubigeo", "slug", "excel_relpath", "departamento", "provincia", "distrito"]:
        if c not in df.columns: df[c] = ""

    def guess_excel(row):
        if row["excel_relpath"]:
            return row["excel_relpath"]
        name = row["slug"] or row["ubigeo"] or "SIN_NOMBRE"
        return f"ZonasEscolares/excels/{name}.xlsx"
    df["excel_relpath"] = df.apply(guess_excel, axis=1)

    def to_map(p):
        if not p: return ""
        return p.replace("/excels/", "/maps/").replace("\\excels\\", "\\maps\\").replace(".xlsx", ".html")
    df["map_relpath"] = df["excel_relpath"].map(to_map)

    def exists_rel(relpath: str) -> bool:
        if not relpath: return False
        return (ROOT / Path(relpath)).exists()

    df["has_excel"] = df["excel_relpath"].map(exists_rel)
    df["has_map"]   = df["map_relpath"].map(exists_rel)

    df = df[df["has_excel"]].copy()

    def mk_title(row):
        parts = [row.get("departamento","").strip(), row.get("provincia","").strip(), row.get("distrito","").strip()]
        parts = [p for p in parts if p]
        if parts: return " - ".join(parts)
        if row.get("slug"): return row["slug"].replace("_", " ")
        return row.get("ubigeo", "")
    df["title"] = df.apply(mk_title, axis=1)

    # Ordenamiento
    df["_dep"]  = df["departamento"].str.normalize('NFKD')
    df["_prov"] = df["provincia"].str.normalize('NFKD')
    df["_dist"] = df["distrito"].str.normalize('NFKD')
    df["_slug"] = df["slug"].str.normalize('NFKD')
    df = df.sort_values(["_dep","_prov","_dist","_slug","ubigeo"])

    items = []
    for _, r in df.iterrows():
        excel_rel = Path(r["excel_relpath"]).as_posix()
        mapa_rel  = Path(r["map_relpath"]).as_posix()
        if not excel_rel.startswith("../"):
            excel_rel = f"../{excel_rel}"
        if not mapa_rel.startswith("../"):
            mapa_rel = f"../{mapa_rel}"

        sugg = r.get("slug") or f"{r.get('departamento','')}-{r.get('provincia','')}-{r.get('distrito','')}"
        dep, prov, dist = _split_slug(sugg)

        items.append({
            "titulo": r["title"],
            "slug": r["slug"],
            "ubigeo": r["ubigeo"],
            "excel_rel": excel_rel,
            "mapa_rel": mapa_rel,
            "has_excel": bool(r["has_excel"]),
            "has_map":   bool(r["has_map"]),
            "detalle": f"UBIGEO: {r['ubigeo']}" if r["ubigeo"] else "",
            "data_dep":  dep,
            "data_prov": prov,
            "data_dist": dist,
            "data_ubi":  r.get("ubigeo","") or "",
        })
    return items

# ---------- Escaneo genérico (Inter/Estab) con mapeo UBIGEO desde catálogo ----------
def _scan_items_generic(base_dir: Path, section: str, idx_slug: dict, idx_parts: dict):
    """
    Escanea /<section>/excels y arma items; deshabilita mapa si no existe.
    Deriva dep/prov/dist del nombre; intenta obtener UBIGEO desde catálogo:
      1) Búsqueda por slug exacto (minúsculas).
      2) Fallback por clave "dep|prov|dist" normalizada.
    """
    excels_dir = base_dir / "excels"
    items = []
    if excels_dir.exists():
        for x in sorted(excels_dir.glob("*.xlsx")):
            name = x.stem  # p.ej. DEPARTAMENTO-PROVINCIA-DISTRITO (con _ en el distrito)
            excel_rel = f"../{section}/excels/{x.name}"
            mapa_rel  = f"../{section}/maps/{name}.html"
            has_excel = True
            has_map   = (ROOT / section / "maps" / f"{name}.html").exists()
            titulo = name.replace("_", " ")

            dep, prov, dist = _split_slug(name)

            # UBIGEO desde catálogo
            ubi = ""
            slug_lower = name.lower()
            if slug_lower in idx_slug:
                ubi = idx_slug[slug_lower]
            else:
                key = _key_from_parts(dep, prov, dist)
                ubi = idx_parts.get(key, "")

            items.append({
                "titulo": titulo,
                "name": name,
                "excel_rel": excel_rel,
                "mapa_rel":  mapa_rel,
                "has_excel": has_excel,
                "has_map":   has_map,
                "data_dep":  dep,
                "data_prov": prov,
                "data_dist": dist,
                "data_ubi":  ubi,   # <- ahora poblado
            })
    return items

def load_items_inter():
    idx_slug, idx_parts = _load_catalog_index()
    return _scan_items_generic(INTER_DIR, "Intersecciones", idx_slug, idx_parts)

def load_items_estab():
    idx_slug, idx_parts = _load_catalog_index()
    return _scan_items_generic(ESTAB_DIR, "EstablecimientoSalud", idx_slug, idx_parts)

# ---------- Build ----------
def build_home():
    title = read_txt(CONTENT / "home_title.txt", "Programa de Incentivos 2026 — Observatorio de Seguridad Vial")
    body  = read_txt(CONTENT / "home_body.txt", "Bienvenido/a. Navega a las implementaciones y explora los recursos.")
    HOME_HTML.write_text(home_html(title, body), encoding="utf-8")
    print(f"[OK] {HOME_HTML.resolve()}")

def build_zonas():
    title = read_txt(CONTENT / "zonas_title.txt", "Zonas Escolares")
    body  = read_txt(CONTENT / "zonas_body.txt",  "Explora los recursos por municipalidad/distrito.")
    items = load_catalog_zonas()
    ZONAS_HTML.write_text(zonas_html(title, body, items), encoding="utf-8")
    print(f"[OK] {ZONAS_HTML.resolve()} (items: {len(items)})")

def build_inter():
    title = read_txt(CONTENT / "inter_title.txt", "Intersecciones priorizadas")
    body  = read_txt(CONTENT / "inter_body.txt",  "Explora los recursos por municipalidad/distrito.")
    items = load_items_inter()
    INTER_HTML.write_text(list_page_html(title, body, items, INTER_IMG), encoding="utf-8")
    print(f"[OK] {INTER_HTML.resolve()} (items: {len(items)})")

def build_estab():
    title = read_txt(CONTENT / "estab_title.txt", "Establecimientos de Salud priorizados")
    body  = read_txt(CONTENT / "estab_body.txt",  "Explora los recursos por municipalidad/distrito.")
    items = load_items_estab()
    ESTAB_HTML.write_text(list_page_html(title, body, items, ESTAB_IMG), encoding="utf-8")
    print(f"[OK] {ESTAB_HTML.resolve()} (items: {len(items)})")

def main():
    ensure_dirs()
    build_home()
    build_zonas()
    build_inter()
    build_estab()

if __name__ == "__main__":
    main()
