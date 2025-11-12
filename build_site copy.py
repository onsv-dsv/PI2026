# -*- coding: utf-8 -*-
"""
build_site.py

Genera:
- /index.html                    (portada)
- /ZonasEscolares/index.html     (listado de excels y mapas)
- /Intersecciones/index.html     (listado de excels y mapas)
- /Hospitales/index.html         (placeholder)

Lee:
- content/home_title.txt,  content/home_body.txt
- content/zonas_title.txt, content/zonas_body.txt
- content/inter_title.txt, content/inter_body.txt
- assets/img/logo.jpg, assets/img/home.jpg, assets/img/zonas.jpg, assets/img/inter.jpg
- data/municipalidades_catalog.csv (para Zonas)

Reglas:
- En Zonas/Intersecciones: botón ← Regresar; Excel descarga; Mapa abre en nueva pestaña.
- Zonas: usa catálogo y SOLO lista filas cuyo Excel exista.
- Intersecciones: NO requiere catálogo; ESCANEA /Intersecciones/excels y muestra solo los que existan.
- Si el mapa no existe, el botón aparece deshabilitado.
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

CATALOG_CSV = DATA / "municipalidades_catalog.csv"

ZONAS_DIR = ROOT / "ZonasEscolares"
INTER_DIR = ROOT / "Intersecciones"
HOSP_DIR  = ROOT / "Hospitales"

HOME_HTML  = ROOT / "index.html"
ZONAS_HTML = ZONAS_DIR / "index.html"
INTER_HTML = INTER_DIR / "index.html"
HOSP_HTML  = HOSP_DIR  / "index.html"

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
    HOSP_DIR.mkdir(parents=True, exist_ok=True)

def css_block():
    return """
    <style>
      :root { --blue:#1d4ed8; --sky:#7dd3fc; --bg:#f7f7fb; --fg:#111827; }
      * { box-sizing:border-box; }
      body { margin:0; font-family: system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif; background:var(--bg); color:var(--fg); }
      header { position:relative; padding:18px 20px; background:#fff; box-shadow:0 2px 8px rgba(0,0,0,0.06); }
      .logo { position:absolute; right:20px; top:12px; height:48px; width:auto; border-radius:6px; object-fit:contain; }
      .container { max-width:1100px; margin:0 auto; padding:24px 16px; }
      h1 { margin-top:8px; font-size: clamp(22px, 3.2vw, 34px); }
      p  { font-size: clamp(14px, 2vw, 16px); line-height:1.6; }
      .hero { width:100%; max-height:420px; object-fit:cover; border-radius:14px; box-shadow:0 6px 16px rgba(0,0,0,0.08); }
      .buttons { display:flex; flex-wrap:wrap; gap:12px; margin:18px 0 6px; }
      .btn {
        display:inline-block; padding:12px 16px; border-radius:12px;
        text-decoration:none; color:#fff; background:var(--blue); font-weight:600;
        box-shadow:0 4px 12px rgba(29,78,216,0.3);
        transition: transform .08s ease, box-shadow .2s ease;
      }
      .btn:hover { transform: translateY(-1px); box-shadow:0 8px 18px rgba(29,78,216,0.35); }
      .btn.secondary { background:var(--sky); color:#033154; }
      .disabled { opacity:.5; pointer-events:none; filter:grayscale(0.3); }
      .grid { display:grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap:14px; margin-top:14px; }
      .card {
        background:#fff; border-radius:14px; padding:14px;
        box-shadow:0 4px 12px rgba(0,0,0,0.06);
      }
      .card h3 { margin:4px 0 10px; font-size:18px; }
      .card .row { display:flex; gap:10px; }
      .card a, .card span.btn-like { flex:1; text-align:center; font-weight:600; padding:10px; border-radius:10px; text-decoration:none; display:inline-block; }
      .dl { background:#111827; color:#fff; }
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

def home_html(title_text: str, body_text: str) -> str:
    base = ""  # raíz
    hero_html = f'<img class="hero" src="{base}{HOME_IMG.as_posix()}" alt="imagen">' if HOME_IMG.exists() else ""
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
          <a class="btn" href="ZonasEscolares/index.html">Zonas Escolares</a>
          <a class="btn secondary" href="Intersecciones/index.html">Intersecciones</a>
          <a class="btn secondary" href="Hospitales/index.html">Hospitales</a>
        </div>
      </div>
      <footer>PI 2026 · Dirección de Seguridad Vial — Generado automáticamente</footer>
    </body></html>
    """

def placeholder_html(section_title: str, back_href: str = "../index.html") -> str:
    base = "../"  # subcarpeta
    return f"""
    <!doctype html><html lang="es"><head>
      <meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{esc(section_title)}</title>
      {css_block()}
    </head><body>
      <a class="back" href="{back_href}">← Regresar</a>
      {header_block(section_title, base_prefix=base)}
      <div class="container">
        <p style="font-weight:600;">En mantenimiento…</p>
        <p class="muted">Esta sección estará disponible próximamente.</p>
      </div>
      <footer>PI 2026 · Dirección de Seguridad Vial</footer>
    </body></html>
    """

def zonas_html(title_text: str, body_text: str, items: list) -> str:
    base = "../"  # /ZonasEscolares/
    hero_html = f'<img class="hero" src="{base}{ZONAS_IMG.as_posix()}" alt="zonas">' if ZONAS_IMG.exists() else ""
    cards = []
    for it in items:
        titulo    = esc(it.get("titulo") or it.get("slug") or it.get("ubigeo") or "")
        excel_rel = it.get("excel_rel") or "#"
        mapa_rel  = it.get("mapa_rel")  or "#"
        has_excel = bool(it.get("has_excel"))
        has_map   = bool(it.get("has_map"))

        excel_btn = (f'<a class="dl" href="{excel_rel}" download>Descargar Excel</a>'
                     if has_excel else '<span class="btn-like disabled">Sin Excel</span>')
        map_btn   = (f'<a class="map" href="{mapa_rel}" target="_blank" rel="noopener">Abrir mapa</a>'
                     if has_map else '<span class="btn-like disabled">Mapa no disponible</span>')

        cards.append(f"""
          <div class="card">
            <h3>{titulo}</h3>
            <div class="row">
              {excel_btn}
              {map_btn}
            </div>
            <div class="muted">{esc(it.get("detalle") or "")}</div>
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
        <div class="grid">
          {cards_html}
        </div>
      </div>
      <footer>PI 2026 · Dirección de Seguridad Vial — Generado automáticamente</footer>
    </body></html>
    """

def inter_html(title_text: str, body_text: str, items: list) -> str:
    """Página de Intersecciones: escanea excels y muestra tarjetas."""
    base = "../"  # /Intersecciones/
    hero_html = f'<img class="hero" src="{base}{INTER_IMG.as_posix()}" alt="intersecciones">' if INTER_IMG.exists() else ""
    cards = []
    for it in items:
        titulo    = esc(it.get("titulo") or it.get("slug") or it.get("ubigeo") or it.get("name") or "")
        excel_rel = it.get("excel_rel") or "#"
        mapa_rel  = it.get("mapa_rel")  or "#"
        has_excel = bool(it.get("has_excel"))
        has_map   = bool(it.get("has_map"))

        excel_btn = (f'<a class="dl" href="{excel_rel}" download>Descargar Excel</a>'
                     if has_excel else '<span class="btn-like disabled">Sin Excel</span>')
        map_btn   = (f'<a class="map" href="{mapa_rel}" target="_blank" rel="noopener">Abrir mapa</a>'
                     if has_map else '<span class="btn-like disabled">Mapa no disponible</span>')

        cards.append(f"""
          <div class="card">
            <h3>{titulo}</h3>
            <div class="row">
              {excel_btn}
              {map_btn}
            </div>
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
        <div class="grid">
          {cards_html}
        </div>
      </div>
      <footer>PI 2026 · Dirección de Seguridad Vial — Generado automáticamente</footer>
    </body></html>
    """

# ---------- Carga catálogo & prepara items ----------
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
        if row.get("slug"): return row["slug"]
        return row.get("ubigeo", "")
    df["title"] = df.apply(mk_title, axis=1)

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
        items.append({
            "titulo": r["title"],
            "slug": r["slug"],
            "ubigeo": r["ubigeo"],
            "excel_rel": excel_rel,
            "mapa_rel": mapa_rel,
            "has_excel": bool(r["has_excel"]),
            "has_map":   bool(r["has_map"]),
            "detalle": f"UBIGEO: {r['ubigeo']}" if r["ubigeo"] else ""
        })
    return items

def load_items_inter():
    """Escanea /Intersecciones/excels y arma items; deshabilita mapa si no existe."""
    excels_dir = INTER_DIR / "excels"
    maps_dir   = INTER_DIR / "maps"
    items = []
    if excels_dir.exists():
        for x in sorted(excels_dir.glob("*.xlsx")):
            name = x.stem  # p.ej. UCAYALI-CORONEL_PORTILLO-MANANTAY
            excel_rel = f"../Intersecciones/excels/{x.name}"
            mapa_rel  = f"../Intersecciones/maps/{name}.html"
            has_excel = True
            has_map   = (ROOT / "Intersecciones" / "maps" / f"{name}.html").exists()
            # Título legible desde el nombre del archivo
            titulo = name.replace("_", " ")
            items.append({
                "titulo": titulo,
                "name": name,
                "excel_rel": excel_rel,
                "mapa_rel":  mapa_rel,
                "has_excel": has_excel,
                "has_map":   has_map,
            })
    return items

# ---------- Build ----------
def build_home():
    title = read_txt(CONTENT / "home_title.txt", "Programa de Incentivos 2026 — Observatorio de Seguridad Vial")
    body  = read_txt(CONTENT / "home_body.txt", "Bienvenido/a. Navega a las implementaciones y explora los recursos.")
    HOME_HTML.write_text(home_html(title, body), encoding="utf-8")
    print(f"[OK] {HOME_HTML.resolve()}")

def build_hospitales_placeholder():
    HOSP_HTML.write_text(placeholder_html("Hospitales"), encoding="utf-8")
    print(f"[OK] {HOSP_HTML.resolve()}")

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
    INTER_HTML.write_text(inter_html(title, body, items), encoding="utf-8")
    print(f"[OK] {INTER_HTML.resolve()} (items: {len(items)})")

def main():
    ensure_dirs()
    build_home()
    build_zonas()
    build_inter()
    build_hospitales_placeholder()

if __name__ == "__main__":
    main()
