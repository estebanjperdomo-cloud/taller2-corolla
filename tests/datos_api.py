"""Respuestas de ejemplo con la misma forma que la API de Carroya.

Los nombres de los campos son los que usa la API real (revisados el 9 de
noviembre de 2026): 'find-filters' devuelve count, pages y results con los
anuncios en 'superHighlights'; 'find-vehicle-detail' devuelve {'data': {...}}.
Los valores son inventados.
"""

ID_1 = "bf713f5c-91fb-4d07-b30b-85b805ef8621"
ID_2 = "2d84cf8e-88c8-4c63-9e37-e6b08fc65a53"


def tarjeta(id_anuncio=ID_1, anio=2025, precio=116900000, ciudad="MEDELLIN", modelo="Corolla",
            version="1.8 CVT SEG", accesorios=""):
    return {
        "id": id_anuncio, "year": anio, "title": f"Toyota {modelo} {anio}", "status": "usado", "sold": "N",
        "price": precio, "brand": "Toyota", "model": modelo, "city": ciudad, "kilometers": 14000,
        "cmodeloint": anio, "cprecioint": precio, "clinea2": version, "ctipocaja": "Automática",
        "ccombustible": "Híbrido", "ctipomoneda": "PESO", "caccesorios": accesorios,
        "cofrecidopor": "Particular", "csellername": "Nombre Vendedor", "cselleremail": "x@y.com",
        "cplaca": "ABC123", "detail": "https://www.carroya.comalle/usado/toyota/corolla/2025/medellín/x.do",
    }


def busqueda(tarjetas, count=None, pages=1):
    return {
        "count": len(tarjetas) if count is None else count, "pages": pages, "seo": {},
        "results": {"filter-city": [{"name": "Medellín", "count": 3}], "filter-brand": [{"name": "Toyota"}],
                    "superHighlights": tarjetas, "megaHighlights": [], "latestReleases": []},
    }


def detalle(id_anuncio=ID_1, **cambios):
    datos = {
        "id": id_anuncio, "title": "Toyota Corolla", "status": "usado", "price": 116900000,
        "brand": "Toyota", "brandCode": "99", "model": "Corolla", "version": "1.8 CVT SEG", "year": 2025,
        "kilometers": 14000, "cylindrical": 18, "box": "Automática", "fuel": "Híbrido", "steering_system": "",
        "plate": "ABC123", "plate_city": "Medellín", "city": "Medellin", "cityCode": "05001", "color": "Gris",
        "armored": False, "code_carroya": id_anuncio, "accessories": [], "featured": 1, "sold": "N",
        "comments": "Único dueño. Llamar al 3001234567", "seller": {"name": "Nombre Vendedor", "whatsapp": "300"},
        "publicationStatus": "Publicado", "fechapublicacion": "2026-11-10T00:20:06.000+0000",
        "images": [{"image": "https://carroya-commons.avaldigitallabs.com/x.jpg"}],
    }
    datos.update(cambios)
    return {"data": datos, "loginContact": False}
