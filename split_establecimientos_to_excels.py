# -*- coding: utf-8 -*-
"""
split_establecimientos_to_excels.py

Lee el CSV de establecimientos de salud priorizados (en ./EstablecimientoSalud/establecimientosalud.csv),
calcula ubigeo_gestor (provincial => XXYY01, según competencia de vía) y genera un Excel por cada
ubigeo_gestor en ./EstablecimientoSalud/excels/. Además crea un catálogo:
./EstablecimientoSalud/establecimientos_catalog.csv

- Usa ./data/municipalidades_catalog.csv para nombres oficiales (departamento, provincia, distrito) y slug.
- Excluye de los Excels estas columnas (insensible a mayúsculas/acentos):
  * competencia_vial / competencia_via
  * competencia_administrativa

Uso:
  python split_establecimientos_to_excels.py \
    --input ./EstablecimientoSalud/establecimientosalud.csv \
    --muni-catalog ./data/municipalidades_catalog.csv \
    --out-dir ./EstablecimientoSalud/excels \
    --out-catalog ./EstablecimientoSalud/establecimientos_catalog.csv
"""

from pathlib import Path
import argparse
import pandas as pd
import re

# ------------------------------- Config por defecto -------------------------------
DEFAULT_INPUT = "./EstablecimientoSalud/establecimientosalud.csv"
DEFAULT_MUNI  = "./data/municipalidades_catalog.csv"
DEFAULT_OUTD  = "./EstablecimientoSalud/excels"
DEFAULT_OUTC  = "./EstablecimientoSalud/establecimientos_catalog.csv"

# columnas a excluir (insensible a mayúsculas/acentos)
DROP_COLS = {"competencia_vial", "competencia_via", "competencia_administrativa","competencia administrativa"}

# ------------------------------- Utilitarios -------------------------------
def norm(s: str) -> str:
    s = str(s or "").strip().lower()
    return (s.replace("á","a").replace("é","e").replace("í","i")
             .replace("ó","o").replace("ú","u").replace("ñ","n"))

def to_ubigeo6(x):
    if pd.isna(x): return None
    s = "".join(ch for ch in str(x).strip() if ch.isdigit())
    return s.zfill(6)[:6] if s else None

def compute_gestor(ubigeo, competencia_text):
    """Si la competencia sugiere ámbito PROVINCIAL => XXYY01; caso contrario, XXYYZZ intacto."""
    u = to_ubigeo6(ubigeo)
    if not u: return None
    c = norm(competencia_text)
    if any(k in c for k in ("provincial","provincia","provinc", "prov")):
        return u[:4] + "01"
    return u

def pick_col(df: pd.DataFrame, *cands, required=False):
    colmap = {norm(c): c for c in df.columns}
    for k in cands:
        if norm(k) in colmap:
            return colmap[norm(k)]
    if required:
        raise KeyError(f"No encontré columnas {cands}. Encabezados: {list(df.columns)}")
    return None

def read_csv_smart(path: Path) -> pd.DataFrame:
    encodings = ["utf-8-sig", "cp1252", "latin-1", "utf-16", "utf-8"]
    last_err = None
    for enc in encodings:
        try:
            return pd.read_csv(path, dtype=str, sep=None, engine="python", encoding=enc)
        except UnicodeDecodeError as e:
            last_err = e
            continue
    raise UnicodeDecodeError(f"No pude decodificar {path}. Último error: {last_err}")

def sanitize_filename(name: str) -> str:
    # reemplaza espacios por _ y elimina caracteres problemáticos
    name = name.strip().replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_\-\.ÁÉÍÓÚáéíóúÑñ]", "", name)
    return name or "SIN_NOMBRE"

# ------------------------------- Core -------------------------------
def main():
    ap = argparse.ArgumentParser(description="Split de Establecimientos priorizados a Excels por ubigeo_gestor.")
    ap.add_argument("--input",       default=DEFAULT_INPUT, help="CSV de establecimientos priorizados.")
    ap.add_argument("--muni-catalog",default=DEFAULT_MUNI,  help="Catálogo de municipalidades (dep/prov/dist/slug).")
    ap.add_argument("--out-dir",     default=DEFAULT_OUTD,  help="Carpeta de salida de Excels individuales.")
    ap.add_argument("--out-catalog", default=DEFAULT_OUTC,  help="CSV catálogo resultante (para web).")
    args = ap.parse_args()

    input_path = Path(args.input)
    muni_path  = Path(args.muni_catalog)
    out_dir    = Path(args.out_dir)
    out_cat    = Path(args.out_catalog)

    assert input_path.exists(), f"No existe: {input_path}"
    assert muni_path.exists(),  f"No existe: {muni_path}"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_cat.parent.mkdir(parents=True, exist_ok=True)

    # 1) Leer establecimientos
    df = read_csv_smart(input_path)

    # 2) Detectar columnas base
    #    - ubigeo base: admite varias variantes
    col_ubi  = pick_col(df, "ubigeo","ubigeo_gestor","iddist","ubigeo_ie", required=True)
    #    - competencia para regla provincial
    col_comp = pick_col(df, "competencia_vial","competencia_via")  # opcional pero recomendado

    # 3) Calcular ubigeo_gestor
    df = df.copy()
    if col_comp:
        df["ubigeo_gestor"] = [
            compute_gestor(df.at[i, col_ubi], df.at[i, col_comp])
            for i in df.index
        ]
    else:
        df["ubigeo_gestor"] = df[col_ubi].map(to_ubigeo6)

    df["ubigeo_gestor"] = df["ubigeo_gestor"].astype(str)

    # 4) Cargar catálogo de municipalidades (para nombres y slug)
    muni = pd.read_csv(muni_path, dtype=str).fillna("")
    if "ubigeo_gestor" not in muni.columns:
        if "ubigeo" in muni.columns:
            muni = muni.rename(columns={"ubigeo": "ubigeo_gestor"})
        else:
            muni["ubigeo_gestor"] = ""
    for need in ["departamento","provincia","distrito","slug"]:
        if need not in muni.columns:
            muni[need] = ""

    # 5) Iterar por ubigeo_gestor y exportar Excel (dropeando columnas pedidas)
    keys = sorted(set(u for u in df["ubigeo_gestor"].dropna() if u))
    catalog_rows = []

    drop_norm = {norm(c) for c in DROP_COLS}

    for u6 in keys:
        sub = df[df["ubigeo_gestor"] == u6].copy()
        if sub.empty:
            continue

        # Eliminar columnas no deseadas (competencia_vial/via y competencia_administrativa)
        cols_keep = [c for c in sub.columns if norm(c) not in drop_norm]
        sub = sub[cols_keep]

        # Nombres oficiales desde catálogo
        row_m = muni[muni["ubigeo_gestor"].astype(str).str.zfill(6).str[:6] == u6]
        if not row_m.empty:
            dep  = row_m.iloc[0]["departamento"]
            prov = row_m.iloc[0]["provincia"]
            dist = row_m.iloc[0]["distrito"]
            slug = row_m.iloc[0]["slug"] or f"{dep}-{prov}-{dist}"
        else:
            dep = prov = dist = ""
            slug = u6

        safe_slug = sanitize_filename(slug)
        xlsx_name = f"{safe_slug}.xlsx"
        xlsx_path = out_dir / xlsx_name

        # Guardar Excel individual
        sub.to_excel(xlsx_path, index=False)

        # Registrar en catálogo
        catalog_rows.append({
            "ubigeo_gestor": u6,
            "slug": safe_slug,
            "excel_relpath": xlsx_path.as_posix(),
            "departamento": dep,
            "provincia": prov,
            "distrito": dist
        })

        print(f"[OK] {u6} -> {xlsx_path}")

    # 6) Escribir catálogo para la web/uso posterior
    cat_df = pd.DataFrame(catalog_rows)
    if not cat_df.empty:
        cat_df = cat_df.sort_values(["departamento","provincia","distrito","slug","ubigeo_gestor"])
        # dejar rutas relativas limpias
        root_prefix = Path(".").resolve().as_posix() + "/"
        cat_df["excel_relpath"] = cat_df["excel_relpath"].str.replace(root_prefix, "", regex=False)
        cat_df.to_csv(out_cat, index=False, encoding="utf-8")
        print(f"[OK] Catálogo: {out_cat.resolve()} (items: {len(cat_df)})")
    else:
        print("[Aviso] No se generó catálogo porque no hubo items.")

if __name__ == "__main__":
    main()
