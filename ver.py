# -*- coding: utf-8 -*-
"""
Exporta una capa de un GeoPackage (GPKG) a Excel.
- Intenta con GeoPandas + pyogrio (incluye opciones de geometría).
- Si no están disponibles, usa sqlite3 (atributos sin geometría).

Uso típico:
  python export_gpkg_to_excel.py ^
    --gpkg ./Datos/PROVINCIA.gpkg ^
    --layer ig_provincia ^
    --out ./Mapas/ig_provincia.xlsx ^
    --geom wkt --centroid

Flags de geometría:
  --geom none     -> no exporta geometría
  --geom wkt      -> añade columna 'geometry_wkt'
  --geom xy       -> si la geometría es polígono/línea/punto, añade centroid_x, centroid_y
  (puedes combinar --geom wkt con --centroid para tener ambas cosas)
"""
import argparse
from pathlib import Path
import sys

def main():
    ap = argparse.ArgumentParser(description="Exportar capa GPKG a Excel")
    ap.add_argument("--gpkg", default="./Data/PROVINCIA.gpkg")
    ap.add_argument("--layer", default="ig_provincia")
    ap.add_argument("--out", default="./Mapas/ig_provincia.xlsx")
    ap.add_argument("--geom", choices=["none","wkt","xy"], default="none",
                    help="Cómo exportar geometría (none, wkt, xy[centroid])")
    ap.add_argument("--centroid", action="store_true",
                    help="(Solo con GeoPandas) agrega centroid_x, centroid_y")
    args = ap.parse_args()

    gpkg_path = Path(args.gpkg)
    out_path  = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    assert gpkg_path.exists(), f"No existe: {gpkg_path}"

    # ----------- Intento 1: GeoPandas + pyogrio -----------
    try:
        import geopandas as gpd
        import pyogrio
        engine = "pyogrio"

        # Cargar capa
        gdf = gpd.read_file(gpkg_path, layer=args.layer, engine=engine)

        # Opciones de geometría
        df = gdf.drop(columns=gdf.geometry.name, errors="ignore").copy()
        if args.geom in ("wkt",):
            df["geometry_wkt"] = gdf.geometry.to_wkt()  # WKT
        if args.geom in ("xy",) or args.centroid:
            # centroid_x, centroid_y (en el CRS de la capa)
            cent = gdf.geometry.centroid
            df["centroid_x"] = cent.x
            df["centroid_y"] = cent.y

        # Exportar a Excel
        df.to_excel(out_path, index=False)
        print(f"Exportado con GeoPandas → {out_path}")
        return

    except Exception as e:
        print(f"[Aviso] GeoPandas/pyogrio no disponible o falló ({e}). Probando con sqlite3 (atributos sin geometría)...")

    # ----------- Intento 2: sqlite3 (atributos sin geom) -----------
    import sqlite3
    import pandas as pd

    con = sqlite3.connect(gpkg_path)
    cur = con.cursor()

    # Nombre de columna geométrica
    geom_row = cur.execute(
        "SELECT column_name FROM gpkg_geometry_columns WHERE table_name = ?",
        (args.layer,)
    ).fetchone()
    geom_col = geom_row[0] if geom_row else None

    # Listar columnas con PRAGMA
    pragma = cur.execute(f"PRAGMA table_info('{args.layer}')").fetchall()
    # c[1] = nombre de la columna
    headers = [c[1] for c in pragma]

    # Excluir geometría si existe
    attrs = [h for h in headers if h != geom_col] if geom_col else headers
    select_cols = ", ".join(f'"{c}"' for c in attrs)

    # Leer atributos
    df = pd.read_sql_query(f'SELECT {select_cols} FROM "{args.layer}"', con)
    con.close()

    # Exportar a Excel
    df.to_excel(out_path, index=False)
    print(f"Exportado con sqlite3 (sin geometría) → {out_path}")

if __name__ == "__main__":
    main()
