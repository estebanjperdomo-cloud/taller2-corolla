"""Monitor de Toyota Corolla 2022 a 2026 en Carroya (Taller 2). Punto de entrada único.

Uso:  python taller.py <comando> [opciones]

Instalación y prueba
  verificar               revisa que todo esté listo y dice qué falta
  demo                    seis días simulados, sin internet (datos/demo)
  probar-correo           envía un correo corto para comprobar la cuenta

Cada paso del taller por separado (por defecto en modo prueba)
  paso1                   busca todos los enlaces en Carroya y descarga cada anuncio
  paso3                   procesa los archivos del día en la base consolidada
  consultar               muestra las consultas del paso 2 sobre la base
  paso6                   distribución de precios, gráfica y posibles gangas
  paso7                   arma y envía el correo del día
  log                     resumen de los logs del paso 5 (todos los modos)

Lo que corre solo cada día (paso 4)
  recolectar              8:00, pasos 1, 3 y 6 seguidos
  correo                  11:00, paso 7
  programar               crea las dos tareas diarias en el Mac (launchd)
  estado-programacion     muestra si las tareas están cargadas y su última salida
  probar-programacion X   lanza ya la tarea X (recolectar o correo) como lo haría el Mac
  desprogramar            quita las tareas (el 22 de noviembre)

Entrega (paso 8)
  reconstruir             rehace la base desde los archivos diarios (prueba de idempotencia)
  exportar                base en CSV y Excel y log consolidado
  entregar                arma entrega_taller2_corolla.zip y dice qué falta

Modos. Todo comando manual usa el modo prueba salvo que se escriba --modo oficial.
Las tareas programadas usan --programado, que elige el modo según la fecha.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from corolla import configuracion as config

SEPARADOR = "-" * 72


def _cargar_env() -> None:
    try:  # variables del archivo .env (SMTP_USER, SMTP_PASSWORD, EMAIL_TO...)
        from dotenv import load_dotenv
        load_dotenv(config.RAIZ_PROYECTO / ".env")
    except ImportError:
        pass


def _modo(args, programado_permitido: bool = False) -> str | None:
    if getattr(args, "modo", None):
        return args.modo
    if programado_permitido and getattr(args, "programado", False):
        return config.modo_programado(config.hoy())
    return "prueba"


def _imprimir(datos) -> None:
    print(json.dumps(datos, ensure_ascii=False, indent=2, default=str))


# --- Instalación y prueba --------------------------------------------------------------------
def cmd_verificar(args) -> int:
    from corolla.verificacion import FALTA, resumen_periodo, verificar
    filas = verificar(red=not args.sin_red, navegador=not args.sin_navegador)
    for estado, que, como in filas:
        print(f"[{estado:5}] {que}")
        if como:
            print(f"        {como}")
    print(SEPARADOR)
    print(resumen_periodo())
    faltan = sum(1 for f in filas if f[0] == FALTA)
    print("Todo listo." if not faltan else f"Hay {faltan} cosa(s) por arreglar antes de seguir.")
    return 1 if faltan else 0


def cmd_demo(args) -> int:
    from corolla.simulacion import ejecutar_demo
    rutas = ejecutar_demo(args.dias)
    print(SEPARADOR)
    print(f"Listo. Los archivos de la demostración quedaron en {rutas.base}")
    print("Para ver el correo del primer día en el navegador:")
    print(f"  open {rutas.correos_dia(config.PERIODO_INICIO)}/*.html")
    return 0


def cmd_probar_correo(args) -> int:
    from email.message import EmailMessage
    from email.utils import format_datetime, make_msgid
    import os
    from corolla.paso7_correo import enviar
    mensaje = EmailMessage()
    mensaje["Subject"] = "[PRUEBA] Monitor Corolla · prueba de envío"
    mensaje["From"] = os.environ.get("EMAIL_FROM") or os.environ.get("SMTP_USER") or ""
    mensaje["To"] = os.environ.get("EMAIL_TO") or ""
    mensaje["Date"] = format_datetime(config.ahora())
    mensaje["Message-ID"] = make_msgid(domain="corolla.monitor")
    mensaje.set_content(f"Si recibió este correo, la cuenta quedó bien configurada.\n"
                        f"Enviado el {config.fecha_larga(config.hoy())} a las {config.ahora():%H:%M:%S} "
                        f"({config.NOMBRE_ZONA}).")
    estado, detalle = enviar(mensaje, intentos=1)
    print(f"Correo de prueba {estado}: {detalle}")
    if estado != "enviado":
        print("Revise SMTP_USER, SMTP_PASSWORD (contraseña de aplicación) y EMAIL_TO en el archivo .env")
    return 0 if estado == "enviado" else 1


# --- Pasos por separado ------------------------------------------------------------------------
def cmd_paso1(args) -> int:
    from corolla import flujo
    from corolla.paso1_navegador import NavegadorCarroya
    rutas = config.Rutas(_modo(args))
    dia = flujo.Dia(rutas, config.hoy(), nueva=True)
    try:
        fuente = (lambda: NavegadorCarroya(con_ventana=True)) if args.visible else None
        manifiesto = flujo.correr_paso1(dia, crear_fuente=fuente, max_anuncios=args.max_anuncios)
    finally:
        dia.bitacora.cerrar()
    print(SEPARADOR)
    print(f"Paso 1 en modo {rutas.modo}. Carroya reporta {manifiesto['total_reportado_por_carroya']} anuncios "
          f"en {manifiesto['paginas_esperadas']} páginas; se leyeron {len(manifiesto['paginas_leidas'])}.")
    print(f"Búsqueda completa: {'sí' if manifiesto['busqueda_completa'] else 'no, ' + str(manifiesto['motivo_busqueda_incompleta'])}")
    print(f"Enlaces que cumplen los criterios: {manifiesto['enlaces_que_cumplen_criterios']} "
          f"({manifiesto['anuncios_nuevos_para_el_sistema']} nuevos para el sistema, "
          f"{len(manifiesto['descartados_por_criterios'])} descartados por no cumplir).")
    print(f"Descargas: {manifiesto['descargas']}")
    print(f"Archivos: {rutas.enlaces(dia.fecha)}\n          {rutas.datos(dia.fecha)}")
    return 0 if manifiesto["paginas_esperadas"] is not None else 1


def cmd_paso3(args) -> int:
    from corolla import flujo
    rutas = config.Rutas(_modo(args))
    dia = flujo.Dia(rutas, args.fecha or config.hoy(), nueva=False)
    try:
        metricas = flujo.correr_paso3(dia)
    finally:
        dia.bitacora.cerrar()
    print(SEPARADOR)
    _imprimir(metricas)
    return 0 if metricas else 1


def cmd_consultar(args) -> int:
    import pandas as pd
    from corolla.paso2_base_de_datos import consultar
    rutas = config.Rutas(_modo(args))
    if not rutas.bd.exists():
        print(f"Todavía no existe la base {rutas.bd}. Corra primero el paso 1 y el paso 3.")
        return 1
    pd.set_option("display.width", 160)
    pd.set_option("display.max_columns", 20)
    for titulo, tabla in consultar(rutas.bd, args.id).items():
        print(SEPARADOR)
        print(f"{titulo}  ({len(tabla)} filas; se muestran {min(len(tabla), args.filas)})")
        print(tabla.head(args.filas).to_string(index=False) if len(tabla) else "  (sin filas)")
    return 0


def cmd_paso6(args) -> int:
    from corolla import flujo
    from corolla import formato
    rutas = config.Rutas(_modo(args))
    fecha = args.fecha or config.hoy()
    dia = flujo.Dia(rutas, fecha, nueva=False)
    try:
        resumen = flujo.correr_paso6(dia)
        if all(e["estado"] != "pendiente" for e in dia.estado["etapas"].values()):
            flujo.cerrar_dia(dia)
    finally:
        dia.bitacora.cerrar()
    print(SEPARADOR)
    stats = resumen.get("estadisticas") or {}
    if stats:
        print(f"Precios válidos del día: {stats.get('n')}. Mediana {formato.millones(stats.get('mediana'))}, "
              f"Q1 {formato.millones(stats.get('q1'))}, Q3 {formato.millones(stats.get('q3'))}.")
    else:
        print(f"Sin estadísticas: {resumen.get('motivo_sin_grafica') or 'no hay precios válidos'}")
    alertas = resumen.get("alertas") or []
    print(f"Posibles gangas: {len(alertas)} (nuevas hoy: {len(resumen.get('alertas_nuevas') or [])}).")
    for alerta in alertas:
        print(f"  * {alerta.get('url')}\n    {alerta.get('explicacion')}")
    print(f"Gráfica: {resumen.get('grafica') or 'no se generó'}")
    print(f"Tabla completa: {rutas.reporte(fecha)}")
    return 0


def cmd_paso7(args) -> int:
    from corolla import flujo
    rutas = config.Rutas(_modo(args, programado_permitido=True))
    resultado = flujo.ejecutar_correo(rutas, args.fecha or config.hoy(), enviar=not args.sin_enviar,
                                      origen="programado" if getattr(args, "programado", False) else "manual")
    print(SEPARADOR)
    _imprimir(resultado)
    print(f"Para ver la copia del correo:  open \"{resultado['copia'].replace('.eml', '.html')}\"")
    return 0 if resultado["estado"] == "enviado" or args.sin_enviar else 1


def cmd_log(args) -> int:
    from corolla.paso5_bitacora import leer_registros
    fecha = (args.fecha or config.hoy()).isoformat()
    modos = [args.modo] if args.modo else ["oficial", "prueba"]
    hubo = False
    for modo in modos:
        rutas = config.Rutas(modo)
        registros = [r for r in leer_registros(rutas.logs) if r.get("fecha_reporte") == fecha]
        if not registros:
            continue
        hubo = True
        print(SEPARADOR)
        print(f"Modo {modo}, día {fecha}")
        for r in registros:
            print(f"  {r['inicio'][11:19]} {r['run_id']:<30} {r['etapa']:<19} {r['estado']:<17} {r['duracion_s']:>7} s")
            metricas = {k: r.get(k) for k in ("enlaces_encontrados", "anuncios_nuevos", "descargas_exitosas",
                                               "descargas_fallidas", "descargas_pendientes", "registros_agregados",
                                               "registros_actualizados", "registros_sin_cambios",
                                               "anuncios_unicos", "posibles_gangas_nuevas", "correo_estado")
                        if r.get(k) is not None}
            if metricas:
                print("      " + ", ".join(f"{k}={v}" for k, v in metricas.items()))
            if r.get("errores"):
                print(f"      errores: {r['errores']}")
    if not hubo:
        print(f"No hay logs del {fecha} en {', '.join(modos)}.")
    return 0


# --- Lo que corre cada día ------------------------------------------------------------------
def cmd_recolectar(args) -> int:
    from corolla import flujo
    modo = _modo(args, programado_permitido=True)
    if modo is None:
        print(f"{config.ahora():%Y-%m-%d %H:%M} El periodo oficial terminó el {config.PERIODO_FIN}. "
              "No se ejecuta nada. Puede quitar la programación con: python taller.py desprogramar")
        return 0
    rutas = config.Rutas(modo)
    estado = flujo.ejecutar_recoleccion(rutas, config.hoy(), max_anuncios=args.max_anuncios,
                                        origen="programado" if args.programado else "manual")
    print(SEPARADOR)
    _imprimir({"modo": modo, "estado": estado["estado"], "metricas": estado["metricas"],
               "errores": estado["errores"]})
    return 0 if estado["estado"] != "fallida" else 1


def cmd_correo(args) -> int:
    if _modo(args, programado_permitido=True) is None:
        print(f"{config.ahora():%Y-%m-%d %H:%M} El periodo oficial terminó el {config.PERIODO_FIN}. No se envía correo.")
        return 0
    return cmd_paso7(args)


def cmd_programar(args) -> int:
    from corolla import paso4_programacion as p4
    p4.instalar()
    print(SEPARADOR)
    print("Próximas ejecuciones:")
    for linea in p4.proximas_ejecuciones():
        print(f"  * {linea}")
    print("Revise con: python taller.py estado-programacion")
    return 0


def cmd_estado_programacion(args) -> int:
    from corolla import paso4_programacion as p4
    for fila in p4.estado():
        print(SEPARADOR)
        print(f"{fila['tarea']}  cargada={'sí' if fila['cargada'] else 'no'}  hora del Mac={fila['hora_local']}")
        print(f"  estado={fila['estado']}  veces ejecutada={fila['veces_ejecutada']}  "
              f"último código de salida={fila['ultimo_codigo_salida']}")
        print(f"  salida en {fila['archivo_salida']}")
        for linea in fila["ultimas_lineas"]:
            print(f"    | {linea}")
    print(SEPARADOR)
    print("Próximas ejecuciones:")
    for linea in p4.proximas_ejecuciones():
        print(f"  * {linea}")
    return 0


def cmd_probar_programacion(args) -> int:
    from corolla import paso4_programacion as p4
    p4.probar("recoleccion" if args.tarea == "recolectar" else "correo")
    print("Revise en unos minutos con: python taller.py estado-programacion  y  python taller.py log")
    return 0


def cmd_desprogramar(args) -> int:
    from corolla import paso4_programacion as p4
    p4.desinstalar()
    return 0


# --- Entrega ------------------------------------------------------------------------------------
def cmd_reconstruir(args) -> int:
    from corolla.paso3_actualizacion import reconstruir_desde_archivos
    rutas = config.Rutas(_modo(args))
    for fila in reconstruir_desde_archivos(rutas.bd, rutas.diarios):
        print({k: fila.get(k) for k in ("fecha", "registros_agregados", "registros_actualizados",
                                        "registros_sin_cambios", "anuncios_unicos")})
    return 0


def cmd_exportar(args) -> int:
    from corolla.paso8_entrega import exportar_todo
    rutas = config.Rutas(_modo(args))
    destino = config.RAIZ_PROYECTO / "entrega" if rutas.modo == "oficial" else rutas.base / "exportado"
    for ruta in exportar_todo(rutas, destino):
        print(ruta)
    return 0


def cmd_entregar(args) -> int:
    from corolla.paso8_entrega import empaquetar
    zip_, faltantes = empaquetar()
    print(SEPARADOR)
    print(f"Zip listo en {zip_} ({zip_.stat().st_size / 1e6:.1f} MB).")
    if faltantes:
        print("Todavía falta:")
        for linea in faltantes:
            print(f"  * {linea}")
    else:
        print("La lista de revisión está completa.")
    return 0


# --- Argumentos ------------------------------------------------------------------------------
def _fecha(texto: str) -> date:
    return date.fromisoformat(texto)


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python taller.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="comando", required=True, metavar="comando")
    modo = argparse.ArgumentParser(add_help=False)
    modo.add_argument("--modo", choices=config.MODOS, help="prueba (por defecto), oficial o demo")
    fecha = argparse.ArgumentParser(add_help=False)
    fecha.add_argument("--fecha", type=_fecha, help="día AAAA-MM-DD (por defecto hoy)")
    programado = argparse.ArgumentParser(add_help=False)
    programado.add_argument("--programado", action="store_true",
                            help="lo usan las tareas del Mac. Elige el modo según la fecha")

    p = sub.add_parser("verificar", help="revisa que todo esté listo")
    p.add_argument("--sin-red", action="store_true", help="no revisar la conexión a internet")
    p.add_argument("--sin-navegador", action="store_true", help="no abrir Chromium")
    p.set_defaults(funcion=cmd_verificar)
    p = sub.add_parser("demo", help="seis días simulados sin internet")
    p.add_argument("--dias", type=int, default=6)
    p.set_defaults(funcion=cmd_demo)
    sub.add_parser("probar-correo", help="envía un correo corto de prueba").set_defaults(funcion=cmd_probar_correo)

    p = sub.add_parser("paso1", parents=[modo], help="busca y descarga en Carroya")
    p.add_argument("--max-anuncios", type=int, help="descargar solo N fichas (prueba rápida)")
    p.add_argument("--visible", action="store_true", help="mostrar la ventana del navegador")
    p.set_defaults(funcion=cmd_paso1)
    sub.add_parser("paso3", parents=[modo, fecha], help="actualiza la base con los archivos del día") \
        .set_defaults(funcion=cmd_paso3)
    p = sub.add_parser("consultar", parents=[modo], help="consultas del paso 2")
    p.add_argument("--id", help="limitar a un anuncio")
    p.add_argument("--filas", type=int, default=8, help="filas que se muestran por consulta")
    p.set_defaults(funcion=cmd_consultar)
    sub.add_parser("paso6", parents=[modo, fecha], help="análisis de precios y gangas").set_defaults(funcion=cmd_paso6)
    p = sub.add_parser("paso7", parents=[modo, fecha], help="arma y envía el correo")
    p.add_argument("--sin-enviar", action="store_true", help="solo guardar la copia")
    p.set_defaults(funcion=cmd_paso7)
    sub.add_parser("log", parents=[modo, fecha], help="resumen de logs").set_defaults(funcion=cmd_log)

    p = sub.add_parser("recolectar", parents=[modo, programado], help="8:00, pasos 1, 3 y 6")
    p.add_argument("--max-anuncios", type=int, help="descargar solo N fichas (prueba rápida)")
    p.set_defaults(funcion=cmd_recolectar)
    p = sub.add_parser("correo", parents=[modo, fecha, programado], help="11:00, paso 7")
    p.add_argument("--sin-enviar", action="store_true", help="solo guardar la copia")
    p.set_defaults(funcion=cmd_correo)
    sub.add_parser("programar", help="crea las tareas diarias en el Mac").set_defaults(funcion=cmd_programar)
    sub.add_parser("estado-programacion", help="estado de las tareas del Mac") \
        .set_defaults(funcion=cmd_estado_programacion)
    p = sub.add_parser("probar-programacion", help="lanza ya una tarea programada")
    p.add_argument("tarea", choices=("recolectar", "correo"))
    p.set_defaults(funcion=cmd_probar_programacion)
    sub.add_parser("desprogramar", help="quita las tareas del Mac").set_defaults(funcion=cmd_desprogramar)

    sub.add_parser("reconstruir", parents=[modo], help="rehace la base desde los archivos diarios") \
        .set_defaults(funcion=cmd_reconstruir)
    sub.add_parser("exportar", parents=[modo], help="CSV, Excel y log consolidado").set_defaults(funcion=cmd_exportar)
    sub.add_parser("entregar", help="arma el zip de la entrega").set_defaults(funcion=cmd_entregar)
    return parser


def main(argv: list[str] | None = None) -> int:
    _cargar_env()
    for salida in (sys.stdout, sys.stderr):
        if hasattr(salida, "reconfigure"):
            salida.reconfigure(encoding="utf-8")
    args = construir_parser().parse_args(argv)
    try:
        return args.funcion(args)
    except (RuntimeError, FileNotFoundError) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
