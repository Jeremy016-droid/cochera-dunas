"""
main.py — Backend FastAPI del Sistema de Cochera
Ejecutar:  uvicorn backend.main:app --reload
Docs:      http://127.0.0.1:8000/docs
"""
import hashlib
from datetime import date, datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .database import db_session
from .schemas import (
    TipoVehiculoOut,
    PropietarioIn, PropietarioOut,
    VehiculoIn, VehiculoOut,
    BloqueIn, BloqueOut,
    PagoIn, PagoOut,
    LoginIn, UsuarioOut,
    DashboardOut,
)

app = FastAPI(
    title="Sistema de Cochera API",
    version="1.0.0",
    description="API local para gestión de estacionamiento y pagos.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # En prod: restringir al dominio del frontend
    allow_methods=["*"],
    allow_headers=["*"],
)

def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


# ══════════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════════

@app.post("/auth/login", response_model=UsuarioOut, tags=["Auth"])
def login(body: LoginIn):
    """Verifica credenciales y devuelve datos del usuario."""
    with db_session() as con:
        row = con.execute(
            "SELECT * FROM USUARIO WHERE username = ? AND passwordHash = ?",
            (body.username, _sha256(body.password))
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")
    return dict(row)


# ══════════════════════════════════════════════════════════════
#  TIPOS DE VEHÍCULO
# ══════════════════════════════════════════════════════════════

@app.get("/tipos-vehiculo", response_model=List[TipoVehiculoOut], tags=["Catálogos"])
def listar_tipos():
    with db_session() as con:
        rows = con.execute("SELECT * FROM TIPO_VEHICULO ORDER BY nombre").fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
#  PROPIETARIOS
# ══════════════════════════════════════════════════════════════

@app.post("/propietarios", response_model=PropietarioOut, status_code=201, tags=["Propietarios"])
def crear_propietario(body: PropietarioIn):
    with db_session() as con:
        cur = con.execute(
            "INSERT INTO PROPIETARIO (nombre, numCelular, email, direccion) VALUES (?,?,?,?)",
            (body.nombre, body.numCelular, body.email, body.direccion)
        )
        row = con.execute("SELECT * FROM PROPIETARIO WHERE idProp=?", (cur.lastrowid,)).fetchone()
    return dict(row)

@app.get("/propietarios", response_model=List[PropietarioOut], tags=["Propietarios"])
def buscar_propietarios(q: Optional[str] = Query(None)):
    sql = "SELECT * FROM PROPIETARIO"
    params: list = []
    if q:
        sql += " WHERE nombre LIKE ? OR numCelular LIKE ?"
        params = [f"%{q}%", f"%{q}%"]
    with db_session() as con:
        rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
#  VEHÍCULOS
# ══════════════════════════════════════════════════════════════

@app.post("/vehiculos", response_model=VehiculoOut, status_code=201, tags=["Vehículos"])
def registrar_vehiculo(body: VehiculoIn):
    with db_session() as con:
        existe = con.execute("SELECT placa FROM VEHICULO WHERE placa=?", (body.placa,)).fetchone()
        if existe:
            raise HTTPException(400, f"La placa {body.placa} ya está registrada.")
        tipo = con.execute("SELECT idTipo FROM TIPO_VEHICULO WHERE idTipo=?", (body.idTipo,)).fetchone()
        if not tipo:
            raise HTTPException(404, "Tipo de vehículo no encontrado.")
        con.execute(
            """INSERT INTO VEHICULO (placa, idTipo, marcaModelo, color, idProp, limiteDeuda, esFrecuente)
               VALUES (?,?,?,?,?,?,?)""",
            (body.placa, body.idTipo, body.marcaModelo, body.color,
             body.idProp, body.limiteDeuda, int(body.esFrecuente))
        )
    return _get_vehiculo(body.placa)

@app.get("/vehiculos/{placa}", response_model=VehiculoOut, tags=["Vehículos"])
def obtener_vehiculo(placa: str):
    return _get_vehiculo(placa.upper())

@app.get("/vehiculos", response_model=List[VehiculoOut], tags=["Vehículos"])
def buscar_vehiculos(q: Optional[str] = Query(None)):
    """Busca por placa o nombre del propietario."""
    sql = """
        SELECT V.*, T.nombre AS tipoNombre, P.nombre AS propNombre,
               COALESCE((SELECT SUM(precio) FROM BLOQUE
                         WHERE placa=V.placa AND estado='pendiente'), 0) AS deudaTotal
        FROM VEHICULO V
        JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo
        LEFT JOIN PROPIETARIO P ON V.idProp=P.idProp
    """
    params: list = []
    if q:
        sql += " WHERE V.placa LIKE ? OR P.nombre LIKE ?"
        params = [f"%{q}%", f"%{q}%"]
    with db_session() as con:
        rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]

def _get_vehiculo(placa: str) -> dict:
    with db_session() as con:
        row = con.execute("""
            SELECT V.*, T.nombre AS tipoNombre, P.nombre AS propNombre,
                   COALESCE((SELECT SUM(precio) FROM BLOQUE
                             WHERE placa=V.placa AND estado='pendiente'), 0) AS deudaTotal
            FROM VEHICULO V
            JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo
            LEFT JOIN PROPIETARIO P ON V.idProp=P.idProp
            WHERE V.placa=?
        """, (placa,)).fetchone()
    if not row:
        raise HTTPException(404, f"Vehículo {placa} no encontrado.")
    return dict(row)


# ══════════════════════════════════════════════════════════════
#  BLOQUES
# ══════════════════════════════════════════════════════════════

@app.post("/bloques", response_model=BloqueOut, status_code=201, tags=["Bloques"])
def crear_bloque(body: BloqueIn):
    """Registra el ingreso de un vehículo (genera un bloque 'pendiente')."""
    with db_session() as con:
        veh = con.execute(
            "SELECT V.placa, T.tarifa FROM VEHICULO V JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo WHERE V.placa=?",
            (body.placa,)
        ).fetchone()
        if not veh:
            raise HTTPException(404, f"Vehículo {body.placa} no registrado.")

        precio = veh["tarifa"]

        # Verificar tope de deuda antes de crear
        deuda = con.execute(
            "SELECT COALESCE(SUM(precio),0) AS total FROM BLOQUE WHERE placa=? AND estado='pendiente'",
            (body.placa,)
        ).fetchone()["total"]
        limite = con.execute("SELECT limiteDeuda FROM VEHICULO WHERE placa=?", (body.placa,)).fetchone()["limiteDeuda"]
        if deuda + precio > limite * 1.5:   # bloqueo suave — el operador puede forzar desde el front
            raise HTTPException(409, f"Deuda acumulada (S/{deuda:.2f}) supera el límite permitido (S/{limite:.2f}).")

        cur = con.execute(
            """INSERT INTO BLOQUE (placa, fecha, tipoBloque, precio, estado, responsablePago)
               VALUES (?,?,?,?,?,?)""",
            (body.placa, body.fecha.isoformat(), body.tipoBloque,
             precio, "pendiente", body.responsablePago)
        )
        row = con.execute("""
            SELECT B.*, T.nombre AS tipoNombre
            FROM BLOQUE B
            JOIN VEHICULO V ON B.placa=V.placa
            JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo
            WHERE B.idBloque=?
        """, (cur.lastrowid,)).fetchone()
    return dict(row)

@app.patch("/bloques/{id_bloque}/anular", response_model=BloqueOut, tags=["Bloques"])
def anular_bloque(id_bloque: int):
    """Anula un bloque (vehículo retirado antes de mitad del turno)."""
    with db_session() as con:
        bloque = con.execute("SELECT * FROM BLOQUE WHERE idBloque=?", (id_bloque,)).fetchone()
        if not bloque:
            raise HTTPException(404, "Bloque no encontrado.")
        if bloque["estado"] != "pendiente":
            raise HTTPException(400, f"Solo se puede anular un bloque 'pendiente' (estado actual: {bloque['estado']}).")
        con.execute("UPDATE BLOQUE SET estado='anulado' WHERE idBloque=?", (id_bloque,))
        row = con.execute("""
            SELECT B.*, T.nombre AS tipoNombre
            FROM BLOQUE B JOIN VEHICULO V ON B.placa=V.placa
            JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo
            WHERE B.idBloque=?
        """, (id_bloque,)).fetchone()
    return dict(row)

@app.get("/bloques", response_model=List[BloqueOut], tags=["Bloques"])
def listar_bloques(
    placa: Optional[str] = None,
    estado: Optional[str] = None,
    fecha: Optional[date] = None,
):
    sql = """
        SELECT B.*, T.nombre AS tipoNombre
        FROM BLOQUE B JOIN VEHICULO V ON B.placa=V.placa
        JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo
        WHERE 1=1
    """
    params: list = []
    if placa:
        sql += " AND B.placa=?"; params.append(placa.upper())
    if estado:
        sql += " AND B.estado=?"; params.append(estado)
    if fecha:
        sql += " AND B.fecha=?"; params.append(fecha.isoformat())
    sql += " ORDER BY B.creadoEn DESC"
    with db_session() as con:
        rows = con.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
#  PAGOS
# ══════════════════════════════════════════════════════════════

@app.post("/pagos", response_model=PagoOut, status_code=201, tags=["Pagos"])
def registrar_pago(body: PagoIn):
    """Registra un pago (normal, parcial o adelantado) y marca bloques como 'pagado'."""
    with db_session() as con:
        # Validar bloques
        placeholders = ",".join("?" * len(body.idsBloques))
        bloques = con.execute(
            f"SELECT * FROM BLOQUE WHERE idBloque IN ({placeholders})",
            body.idsBloques
        ).fetchall()
        if len(bloques) != len(body.idsBloques):
            raise HTTPException(404, "Uno o más bloques no encontrados.")
        for b in bloques:
            if b["estado"] != "pendiente":
                raise HTTPException(400, f"Bloque {b['idBloque']} no está en estado 'pendiente' (estado: {b['estado']}).")

        monto = sum(b["precio"] for b in bloques)

        # Insertar PAGO
        cur = con.execute(
            """INSERT INTO PAGO (montoTotal, metodoPago, idOperador, observacion)
               VALUES (?,?,?,?)""",
            (monto, body.metodoPago, body.idOperador, body.observacion)
        )
        id_pago = cur.lastrowid

        # PAGO_BLOQUE + actualizar estado
        for b in bloques:
            con.execute("INSERT INTO PAGO_BLOQUE (idPago, idBloque) VALUES (?,?)", (id_pago, b["idBloque"]))
            con.execute("UPDATE BLOQUE SET estado='pagado' WHERE idBloque=?", (b["idBloque"],))

        row = con.execute("SELECT * FROM PAGO WHERE idPago=?", (id_pago,)).fetchone()
    return {**dict(row), "bloquesCubiertos": body.idsBloques}

@app.get("/pagos", response_model=List[PagoOut], tags=["Pagos"])
def listar_pagos(
    fecha_ini: Optional[date] = None,
    fecha_fin: Optional[date] = None,
    metodo: Optional[str] = None,
):
    sql = "SELECT * FROM PAGO WHERE 1=1"
    params: list = []
    if fecha_ini:
        sql += " AND DATE(fechaPago)>=?"; params.append(fecha_ini.isoformat())
    if fecha_fin:
        sql += " AND DATE(fechaPago)<=?"; params.append(fecha_fin.isoformat())
    if metodo:
        sql += " AND metodoPago=?"; params.append(metodo)
    sql += " ORDER BY fechaPago DESC"
    with db_session() as con:
        pagos = con.execute(sql, params).fetchall()
        result = []
        for p in pagos:
            bloques = con.execute(
                "SELECT idBloque FROM PAGO_BLOQUE WHERE idPago=?", (p["idPago"],)
            ).fetchall()
            result.append({**dict(p), "bloquesCubiertos": [b["idBloque"] for b in bloques]})
    return result


# ══════════════════════════════════════════════════════════════
#  LIBRO DE DEUDAS
# ══════════════════════════════════════════════════════════════

@app.get("/deudas", tags=["Deudas"])
def libro_deudas(q: Optional[str] = Query(None)):
    """Lista vehículos con bloques pendientes + nivel de alerta."""
    sql = """
        SELECT
            V.placa,
            V.limiteDeuda,
            V.esFrecuente,
            T.nombre  AS tipoNombre,
            P.nombre  AS propNombre,
            P.numCelular,
            COALESCE(SUM(CASE WHEN B.estado='pendiente' THEN B.precio ELSE 0 END), 0) AS deudaTotal,
            COUNT(CASE WHEN B.estado='pendiente' THEN 1 END) AS bloquesPendientes
        FROM VEHICULO V
        JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo
        LEFT JOIN PROPIETARIO P ON V.idProp=P.idProp
        LEFT JOIN BLOQUE B ON V.placa=B.placa
        WHERE 1=1
    """
    params: list = []
    if q:
        sql += " AND (V.placa LIKE ? OR P.nombre LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " GROUP BY V.placa HAVING deudaTotal > 0 ORDER BY deudaTotal DESC"

    with db_session() as con:
        rows = con.execute(sql, params).fetchall()

    result = []
    for r in rows:
        d = dict(r)
        deuda = d["deudaTotal"]
        limite = d["limiteDeuda"]
        if deuda > limite:
            d["alerta"] = "rojo"
        elif deuda > limite * 0.8:
            d["alerta"] = "naranja"
        else:
            d["alerta"] = "normal"
        result.append(d)
    return result


# ══════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════

@app.get("/dashboard", response_model=DashboardOut, tags=["Dashboard"])
def dashboard():
    """Métricas del turno activo."""
    hoy = date.today().isoformat()
    hora = datetime.now().hour
    turno = "NOCHE" if (hora >= 18 or hora < 8) else "DIA"

    with db_session() as con:
        presentes = con.execute(
            "SELECT COUNT(DISTINCT placa) AS n FROM BLOQUE WHERE fecha=? AND tipoBloque=? AND estado='pendiente'",
            (hoy, turno)
        ).fetchone()["n"]

        ingresos = con.execute(
            """SELECT COALESCE(SUM(P.montoTotal),0) AS total
               FROM PAGO P
               WHERE DATE(P.fechaPago)=?""",
            (hoy,)
        ).fetchone()["total"]

        deuda_total = con.execute(
            "SELECT COALESCE(SUM(precio),0) AS total FROM BLOQUE WHERE estado='pendiente'"
        ).fetchone()["total"]

        pendientes = con.execute(
            "SELECT COUNT(*) AS n FROM BLOQUE WHERE estado='pendiente'"
        ).fetchone()["n"]

    return {
        "vehiculosPresentes": presentes,
        "ingresosTurno": ingresos,
        "deudaTotal": deuda_total,
        "bloquesPendientes": pendientes,
    }


# ══════════════════════════════════════════════════════════════
#  REPORTES
# ══════════════════════════════════════════════════════════════

@app.get("/reportes/turno", tags=["Reportes"])
def reporte_turno(
    fecha: date = Query(...),
    turno: str = Query(..., pattern="^(DIA|NOCHE)$"),
):
    """Tabla de pagos del turno + deudas activas filtradas por turno/fecha."""
    with db_session() as con:
        pagos = con.execute("""
            SELECT
                B.placa,
                V.marcaModelo,
                T.nombre AS tipoNombre,
                P.montoTotal,
                P.metodoPago,
                U.nombre AS operador,
                P.fechaPago,
                P.observacion
            FROM PAGO P
            JOIN PAGO_BLOQUE PB ON P.idPago=PB.idPago
            JOIN BLOQUE B ON PB.idBloque=B.idBloque
            JOIN VEHICULO V ON B.placa=V.placa
            JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo
            JOIN USUARIO U ON P.idOperador=U.idUsuario
            WHERE B.fecha=? AND B.tipoBloque=?
            GROUP BY P.idPago
            ORDER BY P.fechaPago
        """, (fecha.isoformat(), turno)).fetchall()

        subtotales = con.execute("""
            SELECT metodoPago, COALESCE(SUM(P.montoTotal),0) AS total
            FROM PAGO P
            JOIN PAGO_BLOQUE PB ON P.idPago=PB.idPago
            JOIN BLOQUE B ON PB.idBloque=B.idBloque
            WHERE B.fecha=? AND B.tipoBloque=?
            GROUP BY metodoPago
        """, (fecha.isoformat(), turno)).fetchall()

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
    """Balance semanal de ingresos por método de pago."""
    with db_session() as con:
        rows = con.execute("""
            SELECT DATE(fechaPago) AS dia, metodoPago, SUM(montoTotal) AS total
            FROM PAGO
            WHERE DATE(fechaPago) BETWEEN ? AND ?
            GROUP BY dia, metodoPago
            ORDER BY dia
        """, (fecha_ini.isoformat(), fecha_fin.isoformat())).fetchall()
        total_efectivo = sum(r["total"] for r in rows if r["metodoPago"] == "efectivo")
        total_yape     = sum(r["total"] for r in rows if r["metodoPago"] == "yape")

    return {
        "periodo": {"inicio": fecha_ini.isoformat(), "fin": fecha_fin.isoformat()},
        "detalleDiario": [dict(r) for r in rows],
        "totalEfectivo": total_efectivo,
        "totalYape": total_yape,
        "granTotal": total_efectivo + total_yape,
    }
