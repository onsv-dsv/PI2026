# -*- coding: utf-8 -*-
"""
maps_establecimientos.py  (Establecimientos de Salud + siniestros + contorno + buscador)
- Normaliza encabezados a minúscula al leer cada Excel.
- Buffer de 100 m para establecimientos (no interactivo).
- Título del mapa = nombre del archivo .xlsx (sin extensión).
- Buscador por nombre_establecimiento y codigo_unico (case-insensitive, contains, OR).
"""

import argparse
from pathlib import Path
import json
import pandas as pd
import folium
from html import escape
from branca.element import Template

COLOR_EST    = "#1d4ed8"  # azul establecimientos
COLOR_FATAL  = "#d90429"  # rojo siniestros
COLOR_HILITE = "#f59e0b"  # amarillo resaltado

# ---------------- util ----------------
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

def title_from_filename(xlsx_path: Path) -> str:
    return xlsx_path.stem

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
            <span style="display:inline-block; width:14px; height:14px; background:{COLOR_EST}; border-radius:50%;"></span>
            <span>Azul: Establecimiento de salud priorizado</span>
        </div>
        <div style="display:flex; align-items:center; gap:8px;">
            <span style="display:inline-block; width:14px; height:14px; background:{COLOR_FATAL}; border-radius:50%;"></span>
            <span>Rojo: Siniestro fatal</span>
        </div>
        <div style="display:flex; align-items:center; gap:8px; margin-top:6px;">
            <span style="display:inline-block; width:14px; height:14px; background:{COLOR_HILITE}; border-radius:50%;"></span>
            <span>Amarillo: Coincidencia de búsqueda</span>
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(html))

# ---------- helpers geometrías (contornos) ----------
def features_distrito_por_ubigeo(distritos_gj: dict, target_ubi6: str):
    feats = []
    for feat in distritos_gj.get("features", []):
        props = feat.get("properties") or {}
        iddist = props.get("IDDIST")
        if to_ubigeo6(iddist) == target_ubi6:
            feats.append(feat)
    return feats

def features_provincia_por_ubigeo(prov_gj_list: list, target_ubi6: str):
    target4 = target_ubi6[:4] if target_ubi6 else None
    feats = []
    for prov_gj in prov_gj_list:
        for feat in prov_gj.get("features", []):
            props = feat.get("properties") or {}
            matched = False
            for k, v in props.items():
                if "ubigeo" in str(k).lower():
                    if to_ubigeo6(v) == target_ubi6:
                        feats.append(feat); matched = True
                        break
            if matched:
                continue
            idprov = props.get("IDPROV")
            if idprov is not None and target4 is not None:
                v = "".join(ch for ch in str(idprov) if ch.isdigit())
                v = v.zfill(4)[:4]
                if v == target4:
                    feats.append(feat)
    return feats

# ---------- punto en polígono ----------
def _point_in_ring(lon, lat, ring):
    inside = False
    if not ring: return False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0], ring[i][1]
        x2, y2 = ring[(i + 1) % n][0], ring[(i + 1) % n][1]
        if ((y1 > lat) != (y2 > lat)):
            x_inter = (x2 - x1) * (lat - y1) / (y2 - y1 + 1e-15) + x1
            if x_inter > lon:
                inside = not inside
    return inside

def point_in_polygon(lon, lat, polygon_coords):
    if not polygon_coords: return False
    exterior = polygon_coords[0]
    if not _point_in_ring(lon, lat, exterior):
        return False
    for hole in polygon_coords[1:]:
        if _point_in_ring(lon, lat, hole):
            return False
    return True

def point_in_features(lon, lat, feats):
    for feat in feats:
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates")
        if not coords:
            continue
        if gtype == "Polygon":
            if point_in_polygon(lon, lat, coords):
                return True
        elif gtype == "MultiPolygon":
            for poly in coords:
                if point_in_polygon(lon, lat, poly):
                    return True
    return False

# ---------- siniestros ----------
def load_siniestros_csv(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "cp1252", "latin-1", "utf-16", "utf-8"]
    last_err = None
    for enc in encodings:
        try:
            df = pd.read_csv(path, dtype=str, sep=None, engine="python", encoding=enc)
            break
        except UnicodeDecodeError as e:
            last_err = e
            continue
    else:
        raise UnicodeDecodeError(f"No se pudo decodificar {path}. Último error: {last_err}")

    def pick_col(columns, *cands):
        cols = {str(c).strip().lower(): c for c in columns}
        for k in cands:
            lk = str(k).strip().lower()
            if lk in cols:
                return cols[lk]
        return None

    col_lat = pick_col(df.columns, "latitud","latitude","lat","y")
    col_lon = pick_col(df.columns, "longitud","longitude","lon","long","x")
    if not col_lat or not col_lon:
        raise KeyError(f"Siniestros: no encuentro columnas lat/lon. Encabezados={list(df.columns)}")

    df = df.copy()
    df["__lat__"] = pd.to_numeric(df[col_lat], errors="coerce")
    df["__lon__"] = pd.to_numeric(df[col_lon], errors="coerce")
    df = df.dropna(subset=["__lat__","__lon__"])
    return df

# ---------- popups ----------
_EXCLUDE_KEYS_EST = {"ubigeo_gestor","ubigeo","departamento","provincia","distrito"}

def _safe_str(v):
    try:
        if pd.api.types.is_scalar(v):
            return "" if pd.isna(v) else str(v)
        return str(v)
    except Exception:
        return str(v)

def build_popup_est(row: pd.Series) -> str:
    rows = []
    for col, val in row.items():
        if str(col).strip().lower() in _EXCLUDE_KEYS_EST:
            continue
        sval = _safe_str(val)
        rows.append(
            f"<tr>"
            f"<th style='text-align:left; padding:2px 8px 2px 0; white-space:nowrap;'>{escape(str(col))}</th>"
            f"<td style='padding:2px 0;'>{escape(sval)}</td>"
            f"</tr>"
        )
    table_html = (
        "<div style='font-size:12px;'>"
        "<div style='font-weight:700; margin-bottom:6px;'>Establecimiento de salud priorizado</div>"
        "<table style='border-collapse:collapse;'>"
        + "".join(rows) +
        "</table>"
        "</div>"
    )
    return table_html

def build_popup_siniestro(row: pd.Series) -> str:
    rows = []
    for col, val in row.items():
        if col in ("__lat__","__lon__"):
            continue
        sval = _safe_str(val)
        rows.append(
            f"<tr>"
            f"<th style='text-align:left; padding:2px 8px 2px 0; white-space:nowrap;'>{escape(str(col))}</th>"
            f"<td style='padding:2px 0;'>{escape(sval)}</td>"
            f"</tr>"
        )
    table_html = (
        "<div style='font-size:12px;'>"
        "<div style='font-weight:700; margin-bottom:6px;'>Siniestro fatal</div>"
        "<table style='border-collapse:collapse;'>"
        + "".join(rows) +
        "</table>"
        "</div>"
    )
    return table_html

# ---------- core ----------
def map_for_excel(xlsx_path: Path, out_dir: Path, distritos_gj: dict, provincias_gj_list: list, siniestros_df: pd.DataFrame) -> Path:
    df = pd.read_excel(xlsx_path, dtype=str)
    df.columns = [str(c).strip().lower() for c in df.columns]

    missing = [c for c in ("latitud","longitud") if c not in df.columns]
    if missing:
        raise KeyError(f"{xlsx_path.name}: faltan columnas {missing}")

    df = df.copy()
    df["latitud"]  = pd.to_numeric(df["latitud"], errors="coerce")
    df["longitud"] = pd.to_numeric(df["longitud"], errors="coerce")
    df = df.dropna(subset=["latitud","longitud"])
    if df.empty:
        raise ValueError(f"{xlsx_path.name}: no hay filas con lat/lon válidas")

    lat0 = float(df["latitud"].mean())
    lon0 = float(df["longitud"].mean())
    m = folium.Map(location=[lat0, lon0], tiles="OpenStreetMap", zoom_start=14, control_scale=True)

    # CSS (incluye barra de búsqueda)
    m.get_root().html.add_child(folium.Element("""
    <style>
      .leaflet-interactive.zs-buffer { pointer-events: none !important; }
      .searchbar-wrap{
        position: fixed; top: 64px; left: 50%; transform: translateX(-50%);
        z-index: 10000; background: rgba(255,255,255,0.95);
        padding: 8px 10px; border-radius: 10px; box-shadow: 0 2px 8px rgba(0,0,0,0.12);
        font-family: system-ui,-apple-system,'Segoe UI',Roboto,Arial,sans-serif; display:flex; gap:8px; align-items:center;
      }
      .searchbar-wrap input{
        border:1px solid #e5e7eb; border-radius:8px; padding:6px 8px; min-width:220px;
        font-size:13px;
      }
      .searchbar-wrap button{
        border:0; border-radius:8px; padding:6px 10px; font-weight:600; cursor:pointer;
        background:#111827; color:#fff;
      }
    </style>
    """))

    add_title(m, title_from_filename(xlsx_path))
    add_legend(m)

    fg_contorno   = folium.FeatureGroup(name="contorno", show=True)
    fg_buffers    = folium.FeatureGroup(name="establecimientos: buffers (100m)", show=True)
    fg_puntos     = folium.FeatureGroup(name="establecimientos: puntos", show=True)
    fg_siniestros = folium.FeatureGroup(name="siniestros fatales", show=True)

    m.add_child(fg_contorno)
    m.add_child(fg_buffers)
    m.add_child(fg_puntos)
    m.add_child(fg_siniestros)

    target_ubi = to_ubigeo6(df["ubigeo_gestor"].dropna().iloc[0]) if "ubigeo_gestor" in df.columns and df["ubigeo_gestor"].notna().any() else None
    feats = []
    if target_ubi:
        if target_ubi.endswith("01"):
            feats = features_provincia_por_ubigeo(provincias_gj_list, target_ubi)
        else:
            feats = features_distrito_por_ubigeo(distritos_gj, target_ubi)
        if feats:
            gj_filtrado = {"type": "FeatureCollection", "features": feats}
            folium.GeoJson(
                data=gj_filtrado,
                name="Contorno territorial",
                style_function=lambda feat: {
                    "color": "#222222",
                    "weight": 2.5,
                    "opacity": 1.0,
                    "fill": True,
                    "fillColor": "#FFA500",
                    "fillOpacity": 0.6
                }
            ).add_to(fg_contorno)

    bounds = []
    for _, row in df.iterrows():
        lat = float(row["latitud"]); lon = float(row["longitud"])
        name_raw = _safe_str(row.get("nombre_establecimiento", ""))
        code_raw = _safe_str(row.get("codigo_unico", ""))

        folium.Circle(
            location=(lat, lon),
            radius=100,
            color=COLOR_EST,
            weight=2,
            fill=True,
            fill_color=COLOR_EST,
            fill_opacity=0.5,
            interactive=False,
            class_name="zs-buffer"
        ).add_to(fg_buffers)

        marker = folium.CircleMarker(
            location=(lat, lon),
            radius=5,
            color=COLOR_EST,
            weight=2,
            fill=True,
            fill_color=COLOR_EST,
            fill_opacity=1.0,
            popup=folium.Popup(build_popup_est(row), max_width=480),
        )
        tooltip_text = f"{name_raw}".lower() + " | " + f"{code_raw}".lower()
        folium.Tooltip(tooltip_text, sticky=False, opacity=0).add_to(marker)
        marker.add_to(fg_puntos)

        bounds.append((lat, lon))

    if feats and not siniestros_df.empty:
        for _, r in siniestros_df.iterrows():
            slat = float(r["__lat__"]); slon = float(r["__lon__"])
            if point_in_features(slon, slat, feats):
                folium.CircleMarker(
                    location=(slat, slon),
                    radius=5,
                    color=COLOR_FATAL,
                    weight=2,
                    fill=True,
                    fill_color=COLOR_FATAL,
                    fill_opacity=1.0,
                    popup=folium.Popup(build_popup_siniestro(r), max_width=500),
                ).add_to(fg_siniestros)

    tpl_front = Template(f"""
    {{% macro script(this, kwargs) %}}
        {fg_puntos.get_name()}.bringToFront();
        {fg_siniestros.get_name()}.bringToFront();
    {{% endmacro %}}
    """)
    m.get_root().add_child(tpl_front)

    if len(bounds) >= 2:
        m.fit_bounds(bounds)

    folium.LayerControl(collapsed=True).add_to(m)

    # ---------- Buscadores (JS puro, case-insensitive, OR) ----------
    search_ui = Template(f"""
    {{% macro html(this, kwargs) %}}
      <div class="searchbar-wrap">
        <input id="q_name" type="text" placeholder="Buscar por nombre_establecimiento…">
        <input id="q_code" type="text" placeholder="Buscar por codigo_unico…">
        <button id="btn_search">Buscar</button>
        <button id="btn_clear" style="background:#6b7280;">Limpiar</button>
      </div>
    {{% endmacro %}}

    {{% macro script(this, kwargs) %}}
      (function() {{
        var puntosLayer = {fg_puntos.get_name()};
        var defaultColor = "{COLOR_EST}";
        var hiliteColor  = "{COLOR_HILITE}";

        function eachMarker(fn) {{
          if (!puntosLayer || !puntosLayer._layers) return;
          Object.values(puntosLayer._layers).forEach(function(ly) {{
            if (ly && typeof ly.setStyle === 'function') fn(ly);
          }});
        }}

        function getTooltipText(ly) {{
          try {{
            var t = ly.getTooltip();
            return t ? String(t.getContent() || "").toLowerCase() : "";
          }} catch(e) {{
            return "";
          }}
        }}

        function clearHighlights() {{
          eachMarker(function(ly) {{ ly.setStyle({{ color: defaultColor, fillColor: defaultColor }}); }});
        }}

        function searchAndHighlight() {{
          var qn = (document.getElementById('q_name').value || "").toLowerCase().trim();
          var qc = (document.getElementById('q_code').value || "").toLowerCase().trim();

          clearHighlights();

          var matchedLatLngs = [];

          eachMarker(function(ly) {{
            var txt = getTooltipText(ly);
            var ok_name = !qn || (txt.indexOf(qn) !== -1);
            var ok_code = !qc || (txt.indexOf(qc) !== -1);
            if (ok_name || ok_code) {{
              ly.setStyle({{ color: hiliteColor, fillColor: hiliteColor }});
              if (ly.getLatLng) matchedLatLngs.push(ly.getLatLng());
            }}
          }});

          if (matchedLatLngs.length > 0) {{
            var group = L.featureGroup(matchedLatLngs.map(function(ll) {{ return L.marker(ll); }}));
            try {{ ly_map.fitBounds(group.getBounds().pad(0.2)); }} catch(e) {{}}
          }}
        }}

        var ly_map = (function() {{
          var _m = null;
          try {{
            _m = puntosLayer._map || null;
          }} catch(e) {{}}
          return _m;
        }})();

        document.getElementById('btn_search').addEventListener('click', searchAndHighlight);
        document.getElementById('btn_clear').addEventListener('click', function() {{
          document.getElementById('q_name').value = "";
          document.getElementById('q_code').value = "";
          clearHighlights();
        }});

        ['q_name','q_code'].forEach(function(id) {{
          var el = document.getElementById(id);
          el.addEventListener('keydown', function(ev) {{
            if (ev.key === 'Enter') searchAndHighlight();
          }});
        }});
      }})();
    {{% endmacro %}}
    """)
    m.get_root().add_child(search_ui)

    out_dir.mkdir(parents=True, exist_ok=True)
    html_name = xlsx_path.with_suffix(".html").name
    out_path = out_dir / html_name
    m.save(str(out_path))
    return out_path

def write_index(index_path: Path, items):
    index_path.parent.mkdir(parents=True, exist_ok=True)
    lis = "\n".join(f'<li><a href="{p.name}" target="_blank">{p.name}</a></li>' for p in items)
    html = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Mapas de Establecimientos de Salud</title></head>
<body>
<h1>Mapas generados</h1>
<ul>{lis}</ul>
</body></html>"""
    index_path.write_text(html, encoding="utf-8")

# ---------------- main ----------------
def main():
    ap = argparse.ArgumentParser(description="Generar mapas de Establecimientos (HTML) con contorno, siniestros y buscador.")
    ap.add_argument("--excels-dir",        default="./EstablecimientoSalud/excels")
    ap.add_argument("--out-dir",           default="./EstablecimientoSalud/maps")
    ap.add_argument("--distritos-geojson", default="./Data/Distritos.geojson",
                    help="GeoJSON de distritos (usa clave IDDIST).")
    ap.add_argument("--provincias-geojson", nargs="+",
                    default=["./Data/Provincias1.geojson", "./Data/Provincias2.geojson"],
                    help="Uno o más GeoJSON de provincias (propiedad con 'ubigeo' o IDPROV).")
    ap.add_argument("--siniestros-csv",    default="./Data/Siniestros.csv",
                    help="CSV de siniestros con columnas lat/lon (latitud/longitud, etc.).")
    args = ap.parse_args()

    excels_root = Path(args.excels_dir)
    out_root    = Path(args.out_dir)

    # GeoJSON distritos
    distritos_path = Path(args.distritos_geojson)
    assert distritos_path.exists(), f"No existe: {distritos_path}"
    with distritos_path.open("r", encoding="utf-8") as f:
        distritos_gj = json.load(f)

    # GeoJSON provincias
    provincias_gj_list = []
    for p in args.provincias_geojson:
        pp = Path(p)
        assert pp.exists(), f"No existe: {pp}"
        with pp.open("r", encoding="utf-8") as f:
            provincias_gj_list.append(json.load(f))

    # Siniestros
    siniestros_path = Path(args.siniestros_csv)
    assert siniestros_path.exists(), f"No existe: {siniestros_path}"
    siniestros_df = load_siniestros_csv(siniestros_path)

    excel_files = scan_excels(excels_root)
    if not excel_files:
        print(f"No se encontraron .xlsx en {excels_root.resolve()}")
        return

    generated = []
    for x in excel_files:
        try:
            out_html = map_for_excel(x, out_root, distritos_gj, provincias_gj_list, siniestros_df)
            print(f"[OK] {x.name} -> {out_html}")
            generated.append(out_html)
        except Exception as e:
            print(f"[ERROR] {x}: {e}")

    if generated:
        write_index(out_root / "_index_maps.html", generated)
        print(f"\nIndex de mapas: { (out_root / '_index_maps.html').resolve() }")

if __name__ == "__main__":
    main()
