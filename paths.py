import os


def get_user_documents_base():
    """
    Devuelve la ruta base:
    C:\\Users\\<user>\\Documents\\SaraPsicologa
    """
    base = os.path.join(
        os.path.expanduser("~"),
        "Documents",
        "SaraPsicologa",
    )
    os.makedirs(base, exist_ok=True)
    return base


def get_facturas_dir():
    base = get_user_documents_base()
    facturas = os.path.join(base, "Facturas")
    os.makedirs(facturas, exist_ok=True)
    return facturas


def get_historias_dir():
    base = get_user_documents_base()
    historias = os.path.join(base, "Historias")
    os.makedirs(historias, exist_ok=True)
    return historias

def get_documentos_dir():
    base = get_user_documents_base()
    documentos = os.path.join(base, "Documentos")
    os.makedirs(documentos, exist_ok=True)
    return documentos