# -*- coding: utf-8 -*-
"""
maps_from_excels.py

Genera mapas interactivos por cada Excel individual en ZonasEscolares/excels/.
- Título = "DEPARTAMENTO-PROVINCIA-DISTRITO" (desde columnas del Excel)
- Fondo OpenStreetMap
- Para cada colegio:
    - Círculo ~100 m (fill_opacity=0.5), color según 'mantenimiento'
    - Punto (CircleMarker) sin transparencia, mismo color
- Leyenda: Azul = Nuevas, Celeste = Mantenimiento
- Contorno del distrito (IDDIST == ubigeo_gestor) con relleno naranja (0.6 de opacidad)

Uso:
  python maps_from_excels.py \
    --excels-dir ./ZonasEscolares/excels \
    --out-dir    ./ZonasEscolares/maps \
    --distritos-geojson ./Data/Distritos.geojson
"""

import argparse
from pathlib import Path
import json
import pandas as pd
import folium
from html import escape

TRUE_SET = {"true","1","si","sí","x","t","y","s","verdadero","yes"}
FALSE_SET = {"false","0","no","n","f","flase","falso","not"}

COLOR_TRUE  = "#7dd3fc"  # celeste = Mantenimiento (True)
COLOR_FALSE = "#1d4ed8"  # azul    = Nuevas (False)

# ---------------- utilitarios ----------------
def to_bool_soft(x) -> bool:
    if isinstance(x, bool):
        return x
    if pd.isna(x):
        return False
    s = str(x).strip().lower()
    return True if s in TRUE_SET else (False if s in FALSE_SET else bool(s))

def to_ubigeo6(x):
    if x is None:
        return None
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    s = "".join(ch for ch in s if ch.isdigit())
    return s.zfill(6)[:6] if s else None

def scan_excels(excels_root: Path):
    return sorted(excels_root.rglob("*.xlsx"))

def build_popup(row: pd.Series) -> str:
    def fmt(name):
        v = row.get(name)
        return "" if pd.isna(v) else str(v)
    parts = []
    parts.append(f"<b>{escape(fmt('descripcion') or '(sin descripción)')}</b>")
    if 'codigo_ce' in row and pd.notna(row.get('codigo_ce')):
        parts.append(f"Código CE: {escape(fmt('codigo_ce'))}")
    if 'ubigeo_gestor' in row and pd.notna(row.get('ubigeo_gestor')):
        parts.append(f"UBIGEO gestor: {escape(fmt('ubigeo_gestor'))}")
    for k,label in [("alumnos","Alumnos"),("docentes","Docentes"),("siniestros","Siniestros")]:
        if k in row and pd.notna(row[k]):
            parts.append(f"{label}: {escape(fmt(k))}")
    return "<br>".join(parts)

def title_from_row(df: pd.DataFrame) -> str:
    dep = str(df["departamento"].dropna().iloc[0]).strip() if "departamento" in df.columns and df["departamento"].notna().any() else ""
    prov= str(df["provincia"].dropna().iloc[0]).strip()     if "provincia" in df.columns and df["provincia"].notna().any() else ""
    dist= str(df["distrito"].dropna().iloc[0]).strip()      if "distrito" in df.columns and df["distrito"].notna().any() else ""
    parts = [p for p in (dep, prov, dist) if p]
    if parts:
        return "-".join(parts)
    if "ubigeo_gestor" in df.columns and df["ubigeo_gestor"].notna().any():
        return str(df["ubigeo_gestor"].dropna().iloc[0])
    return "Mapa de Zonas Escolares"

def add_title(m: folium.Map, text: str):
    html = f"""
    <div style="
        position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
        z-index: 9999; background: rgba(255,255,255,0.9);
        padding: 8px 14px; border-radius: 8px; font-weight: 600;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
        font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;">
        {escape(text)}
    </div>
    """
    m.get_root().html.add_child(folium.Element(html))

def add_legend(m: folium.Map):
    html = f"""
    <div style="
        position: fixed; bottom: 20px; right: 20px; z-index: 9999;
        background: rgba(255,255,255,0.9); padding: 10px 12px; border-radius: 8px;
        font-family: system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif;
        box-shadow: 0 2px 6px rgba(0,0,0,0.15); line-height: 1.4;">
        <div style="font-weight: 600; margin-bottom: 6px;">Leyenda</div>
        <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
            <span style="display:inline-block; width:14px; height:14px; background:{COLOR_FALSE}; border-radius:50%;"></span>
            <span>Azul: Nuevas</span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
            <span style="display:inline-block; width:14px; height:14px; background:{COLOR_TRUE}; border-radius:50%;"></span>
            <span>Celeste: Mantenimiento</span>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(html))

# ---------------- núcleo de mapas ----------------
def map_for_excel(xlsx_path: Path, out_dir: Path, distritos_gj: dict) -> Path:
    df = pd.read_excel(xlsx_path, dtype={"ubigeo_gestor": str})

    # Validaciones mínimas
    missing = [c for c in ("latitud","longitud","mantenimiento") if c not in df.columns]
    if missing:
        raise KeyError(f"{xlsx_path.name}: faltan columnas {missing}")

    # Coordenadas válidas
    df = df.copy()
    df["latitud"]  = pd.to_numeric(df["latitud"], errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")
    df = df.dropna(subset=["latitud","longitud"])
    if df.empty:
        raise ValueError(f"{xlsx_path.name}: no hay filas con lat/lon válidas")

    # Centro inicial y mapa
    lat0 = float(df["latitud"].mean())
    lon0 = float(df["longitud"].mean())
    m = folium.Map(location=[lat0, lon0], tiles="OpenStreetMap", zoom_start=14, control_scale=True)

    # Título y leyenda
    add_title(m, title_from_row(df))
    add_legend(m)

    # UBIGEO objetivo (desde Excel) para contorno; se compara contra IDDIST del GeoJSON
    if "ubigeo_gestor" in df.columns and df["ubigeo_gestor"].notna().any():
        target_ubi = to_ubigeo6(df["ubigeo_gestor"].dropna().iloc[0])
    else:
        target_ubi = None

    if target_ubi:
        # Prefiltrar en memoria el GeoJSON de distritos: SOLO el que tenga IDDIST == ubigeo_gestor
        feats = []
        for feat in distritos_gj.get("features", []):
            props = feat.get("properties") or {}
            iddist = props.get("IDDIST")
            if to_ubigeo6(iddist) == target_ubi:
                feats.append(feat)

        if feats:
            gj_filtrado = {"type": "FeatureCollection", "features": feats}
            folium.GeoJson(
                data=gj_filtrado,
                name="Contorno distrito",
                style_function=lambda feat: {
                    "color": "#222222",     # borde
                    "weight": 2.5,
                    "opacity": 1.0,
                    "fill": True,           # <-- relleno activado
                    "fillColor": "#FFA500", # <-- naranja
                    "fillOpacity": 0.6      # <-- 60% (escala 0 a 1)
                }
            ).add_to(m)
            folium.LayerControl(collapsed=True).add_to(m)

    bounds = []
    for _, row in df.iterrows():
        lat = float(row["latitud"]); lon = float(row["longitud"])
        mant = to_bool_soft(row.get("mantenimiento"))
        color = COLOR_TRUE if mant else COLOR_FALSE

        # (1) Círculo de 100 m aprox (con relleno 50%)
        folium.Circle(
            location=(lat, lon),
            radius=100,
            color=color,
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=0.5,
        ).add_to(m)

        # (2) Punto exacto (sin transparencia)
        folium.CircleMarker(
            location=(lat, lon),
            radius=5,
            color=color,
            weight=2,
            fill=True,
            fill_color=color,
            fill_opacity=1.0,
            popup=folium.Popup(build_popup(row), max_width=400),
        ).add_to(m)

        bounds.append((lat, lon))

    if len(bounds) >= 2:
        m.fit_bounds(bounds)

    out_dir.mkdir(parents=True, exist_ok=True)
    html_name = xlsx_path.with_suffix(".html").name
    out_path = out_dir / html_name
    m.save(str(out_path))
    return out_path

def write_index(index_path: Path, items):
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lis = "\n".join(f'<li><a href="{p.name}" target="_blank">{p.name}</a></li>' for p in items)
    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Mapas de Zonas Escolares</title></head>
<body>
<h1>Mapas generados</h1>
<ul>{lis}</ul>
</body></html>"""
    index_path.write_text(html, encoding="utf-8")

# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser(description="Generar mapas interactivos (HTML) por Excel individual con título, leyenda y contorno distrital.")
    ap.add_argument("--excels-dir",        default="./ZonasEscolares/excels")
    ap.add_argument("--out-dir",           default="./ZonasEscolares/maps")
    ap.add_argument("--distritos-geojson", default="./Data/Distritos.geojson",
                    help="GeoJSON de distritos que contiene la clave IDDIST.")
    args = ap.parse_args()

    excels_root = Path(args.excels_dir)
    out_root    = Path(args.out_dir)

    # Cargar GeoJSON de distritos una sola vez
    distritos_path = Path(args.distritos_geojson)
    assert distritos_path.exists(), f"No existe: {distritos_path}"
    with distritos_path.open("r", encoding="utf-8") as f:
        distritos_gj = json.load(f)

    excel_files = scan_excels(excels_root)
    if not excel_files:
        print(f"No se encontraron .xlsx en {excels_root.resolve()}")
        return

    generated = []
    for x in excel_files:
        try:
            out_html = map_for_excel(x, out_root, distritos_gj)
            print(f"[OK] {x.name} -> {out_html}")
            generated.append(out_html)
        except Exception as e:
            print(f"[ERROR] {x}: {e}")

    if generated:
        write_index(out_root / "_index_maps.html", generated)
        print(f"\nIndex de mapas: { (out_root / '_index_maps.html').resolve() }")

if __name__ == "__main__":
    main()
