):
    with db_session() as (cur, con):
        cur.execute("""
            SELECT B.placa, V.marcaModelo, T.nombre AS tipoNombre,
                   P.montoTotal, P.metodoPago, U.nombre AS operador,
                   P.fechaPago, P.observacion
            FROM PAGO P
            JOIN PAGO_BLOQUE PB ON P.idPago=PB.idPago
            JOIN BLOQUE B ON PB.idBloque=B.idBloque
            JOIN VEHICULO V ON B.placa=V.placa
            JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo
            JOIN USUARIO U ON P.idOperador=U.idUsuario
            WHERE B.fecha=%s AND B.tipoBloque=%s
            GROUP BY P.idPago, B.placa, V.marcaModelo, T.nombre, P.montoTotal,
                     P.metodoPago, U.nombre, P.fechaPago, P.observacion
            ORDER BY P.fechaPago
        """, (fecha.isoformat(), turno))
        pagos = cur.fetchall()

        cur.execute("""
            SELECT P.metodoPago, COALESCE(SUM(P.montoTotal),0) AS total
            FROM PAGO P
            JOIN PAGO_BLOQUE PB ON P.idPago=PB.idPago
            JOIN BLOQUE B ON PB.idBloque=B.idBloque
            WHERE B.fecha=%s AND B.tipoBloque=%s
            GROUP BY P.metodoPago
        """, (fecha.isoformat(), turno))
        subtotales = cur.fetchall()

    return {
        "fecha": fecha.isoformat(),
        "turno": turno,
        "pagos": [dict(r) for r in pagos],
        "subtotales": {r["metodoPago"]: r["total"] for r in subtotales},
    }


@app.get("/reportes/semanal", tags=["Reportes"])
def reporte_semanal(
    fecha_ini: date = Query(...),
    fecha_fin: date = Query(...),
):
    with db_session() as (cur, con):
        cur.execute("""
            SELECT fechaPago::date AS dia, metodoPago, SUM(montoTotal) AS total
            FROM PAGO
            WHERE fechaPago::date BETWEEN %s AND %s
            GROUP BY dia, metodoPago
            ORDER BY dia
        """, (fecha_ini.isoformat(), fecha_fin.isoformat()))
        rows = cur.fetchall()

    total_efectivo = sum(float(r["total"]) for r in rows if r["metodoPago"] == "efectivo")
    total_yape     = sum(float(r["total"]) for r in rows if r["metodoPago"] == "yape")

    return {
        "periodo": {"inicio": fecha_ini.isoformat(), "fin": fecha_fin.isoformat()},
        "detalleDiario": [dict(r) for r in rows],
        "totalEfectivo": total_efectivo,
        "totalYape": total_yape,
        "granTotal": total_efectivo + total_yape,
    }


# ══════════════════════════════════════════════════════════════
#  FRONTEND
# ══════════════════════════════════════════════════════════════

@app.get("/")
def root():
    return RedirectResponse("/login.html")

app.mount("/", StaticFiles(directory=str(BASE_DIR)), name="static")
