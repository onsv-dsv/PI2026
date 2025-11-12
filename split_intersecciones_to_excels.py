# -*- coding: utf-8 -*-
"""
split_intersecciones_to_excels.py

Lee el CSV de intersecciones priorizadas (en ./Intersecciones/Interseccion_priorizada.csv),
calcula ubigeo_gestor (provincial => XXYY01) y genera un Excel por cada ubigeo_gestor
en ./Intersecciones/excels/. También crea un catálogo para la web:
./Intersecciones/intersecciones_catalog.csv

- Usa ./data/municipalidades_catalog.csv para traer nombres oficiales
  (departamento, provincia, distrito) y slug (si existe).
- Excluye de los Excels estas columnas (si existen, case-insensitive):
  - tipo_redvial
  - competencia_via / competencia_vial
  - competencia_administrativa

Uso:
  python split_intersecciones_to_excels.py \
    --input ./Intersecciones/Interseccion_priorizada.csv \
    --muni-catalog ./data/municipalidades_catalog.csv \
    --out-dir ./Intersecciones/excels \
    --out-catalog ./Intersecciones/intersecciones_catalog.csv
"""

from pathlib import Path
import argparse
import pandas as pd
import re

# -----------------------------------
# Config por defecto (rutas)
# -----------------------------------
DEFAULT_INPUT = "./Intersecciones/Interseccion_priorizada.csv"
DEFAULT_MUNI  = "./data/municipalidades_catalog.csv"
DEFAULT_OUTD  = "./Intersecciones/excels"
DEFAULT_OUTC  = "./Intersecciones/intersecciones_catalog.csv"

# columnas a excluir (insensible a mayúsculas/acentos)
DROP_COLS = {"tipo_redvial", "competencia_via", "competencia_vial", "competencia_administrativa"}

# -----------------------------------
# Utilitarios
# -----------------------------------
def norm(s: str) -> str:
    s = str(s or "").strip().lower()
    return (s.replace("á","a").replace("é","e").replace("í","i")
             .replace("ó","o").replace("ú","u").replace("ñ","n"))

def to_ubigeo6(x):
    if pd.isna(x): return None
    s = "".join(ch for ch in str(x).strip() if ch.isdigit())
    return s.zfill(6)[:6] if s else None

def compute_gestor(ubigeo, competencia_text):
    """Si competencia es provincial => XXYY01; caso contrario, se queda XXYYZZ."""
    u = to_ubigeo6(ubigeo)
    if not u: return None
    c = norm(competencia_text)
    # heurística para "provincial"
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
    # Simple: reemplaza espacios por guiones bajos y elimina caracteres problemáticos
    name = name.strip().replace(" ", "_")
    name = re.sub(r"[^A-Za-z0-9_\-\.ÁÉÍÓÚáéíóúÑñ]", "", name)
    # evita nombres vacíos
    return name or "SIN_NOMBRE"

# -----------------------------------
# Core
# -----------------------------------
def main():
    ap = argparse.ArgumentParser(description="Split de Intersecciones priorizadas a Excels por ubigeo_gestor.")
    ap.add_argument("--input",       default=DEFAULT_INPUT, help="CSV de intersecciones priorizadas.")
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

    # 1) Leer intersecciones
    inter_df = read_csv_smart(input_path)

    # 2) Detectar columnas base
    col_ubi = pick_col(inter_df, "ubigeo","ubigeo_gestor","iddist","ubigeo_ie", required=True)
    col_comp = pick_col(inter_df, "competencia_vial","competencia_via")  # opcional

    # 3) Calcular ubigeo_gestor
    inter_df = inter_df.copy()
    if col_comp:
        inter_df["ubigeo_gestor"] = [
            compute_gestor(inter_df.at[i, col_ubi], inter_df.at[i, col_comp])
            for i in inter_df.index
        ]
    else:
        inter_df["ubigeo_gestor"] = inter_df[col_ubi].map(to_ubigeo6)

    inter_df["ubigeo_gestor"] = inter_df["ubigeo_gestor"].astype(str)

    # 4) Cargar catálogo de municipalidades
    muni = pd.read_csv(muni_path, dtype=str).fillna("")
    # Normalizar clave de unión
    if "ubigeo_gestor" not in muni.columns:
        if "ubigeo" in muni.columns:
            muni = muni.rename(columns={"ubigeo": "ubigeo_gestor"})
        else:
            muni["ubigeo_gestor"] = ""
    for need in ["departamento","provincia","distrito","slug"]:
        if need not in muni.columns:
            muni[need] = ""

    # 5) Iterar por cada ubigeo_gestor válido y exportar Excel
    keys = sorted(set(u for u in inter_df["ubigeo_gestor"].dropna() if u))
    catalog_rows = []

    # preparar set para dropeo de columnas (normalizado)
    drop_norm = {norm(c) for c in DROP_COLS}

    for u6 in keys:
        sub = inter_df[inter_df["ubigeo_gestor"] == u6].copy()
        if sub.empty:
            continue

        # Eliminar columnas no deseadas (case/acentos-insensible)
        cols_keep = [c for c in sub.columns if norm(c) not in drop_norm]
        sub = sub[cols_keep]

        # Traer nombres oficiales desde catálogo
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

    # 6) Escribir catálogo (para la web/uso posterior)
    cat_df = pd.DataFrame(catalog_rows)
    if not cat_df.empty:
        # ordenar bonito
        cat_df = cat_df.sort_values(["departamento","provincia","distrito","slug","ubigeo_gestor"])
        # rutas relativas desde la raíz (por prolijidad)
        root_prefix = Path(".").resolve().as_posix() + "/"
        cat_df["excel_relpath"] = cat_df["excel_relpath"].str.replace(root_prefix, "", regex=False)
        cat_df.to_csv(out_cat, index=False, encoding="utf-8")
        print(f"[OK] Catálogo: {out_cat.resolve()} (items: {len(cat_df)})")
    else:
        print("[Aviso] No se generó catálogo porque no hubo items.")

if __name__ == "__main__":
    main()
