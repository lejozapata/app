# test_cie11_api.py
# Ejecuta este archivo como módulo para que funcionen los imports relativos:
#   cd E:\SaraPsicologa
#   python -m app.test_cie11_api
#
# Requisitos:
# - Tabla configuracion_cie11 con release, client_id, client_secret (enc::...)
# - decrypt_str funcionando
# - cie11_api.py leyendo config desde BD

import json

from .cie11_api import CIE11Client
from .db import get_connection


def _debug_configuracion_cie11():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT release, client_id, client_secret, habilitado FROM configuracion_cie11 WHERE id = 1"
    )
    row = cur.fetchone()
    conn.close()

    print("\n[DEBUG] configuracion_cie11 (RAW desde BD):")
    if not row:
        print("  -> No existe fila id=1")
        return

    release, client_id, secret_enc, habilitado = row
    print("  release:", release)
    print("  client_id:", client_id)
    print("  client_secret empieza con:", (secret_enc or "")[:10])
    print("  habilitado:", habilitado)

    # Probar decrypt
    try:
        from .crypto_utils import decrypt_str

        secret_plain = decrypt_str(secret_enc) if secret_enc else None
        print("  decrypt_str OK:", "SI" if secret_plain else "NO (None/vacío)")
        if secret_plain:
            print("  secret_plain length:", len(secret_plain))
    except Exception as ex:
        print("  decrypt_str ERROR:", repr(ex))


def main():
    _debug_configuracion_cie11()

    print("\n[TEST] Instanciando CIE11Client() (lee config desde BD)...")
    try:
        c = CIE11Client(language="es", require_enabled=False)  # pon True si quieres exigir habilitado
        print("  OK -> release_id usado:", c.release_id)
    except Exception as ex:
        print("  ERROR creando cliente:", repr(ex))
        return

    # 1) Test token
    print("\n[TEST] Solicitando token...")
    try:
        token = c._get_token()
        print("  OK -> token len:", len(token))
    except Exception as ex:
        print("  ERROR token:", repr(ex))
        return

    # 2) Test search (términos comunes)
    for q in ["depresivo", "ansiedad", "estado emocional", "insomnio"]:
        print(f"\n[TEST] search(q='{q}')")
        try:
            res = c.search(q)
            print("  resultados:", len(res))
            for it in res[:5]:
                print("   -", it.code, "|", it.title)
        except Exception as ex:
            print("  ERROR search:", repr(ex))

    # 3) Test get_entity del primer resultado con URI (si existe)
    print("\n[TEST] get_entity() con el primer resultado de 'ansiedad'...")
    try:
        res = c.search("ansiedad")
        if not res:
            print("  No hubo resultados.")
            return
        ent = res[0]
        print("  Primer hit:", ent.code, ent.title)
        det = c.get_entity(ent.uri)
        print("  Detalle:", det.code, det.title)
        print("  Desc:", (det.description or "")[:120], "...")
    except Exception as ex:
        print("  ERROR get_entity:", repr(ex))


if __name__ == "__main__":
    main()
