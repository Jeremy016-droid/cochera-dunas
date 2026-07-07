"""
main.py — Backend FastAPI del Sistema de Cochera (PostgreSQL/Supabase)
"""
import hashlib
import pathlib
from contextlib import asynccontextmanager
from datetime import date, datetime
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

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

BASE_DIR = pathlib.Path(__file__).parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crear tablas si no existen en Supabase
    with db_session() as (cur, con):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS TIPO_VEHICULO (
                idTipo   SERIAL PRIMARY KEY,
                nombre   VARCHAR(50) NOT NULL UNIQUE,
                tarifa   NUMERIC(6,2) NOT NULL CHECK(tarifa >= 0)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS USUARIO (
                idUsuario    SERIAL PRIMARY KEY,
                nombre       VARCHAR(100) NOT NULL,
                username     VARCHAR(50) NOT NULL UNIQUE,
                passwordHash VARCHAR(256) NOT NULL,
                rol          VARCHAR(20) NOT NULL CHECK(rol IN ('operador','presidenta'))
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS PROPIETARIO (
                idProp    SERIAL PRIMARY KEY,
                nombre    VARCHAR(100) NOT NULL,
                numCelular VARCHAR(20),
                email     VARCHAR(100),
                direccion VARCHAR(200)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS VEHICULO (
                placa        VARCHAR(10) PRIMARY KEY,
                idTipo       INTEGER NOT NULL REFERENCES TIPO_VEHICULO(idTipo),
                marcaModelo  VARCHAR(100),
                color        VARCHAR(30),
                idProp       INTEGER REFERENCES PROPIETARIO(idProp),
                limiteDeuda  NUMERIC(8,2) NOT NULL DEFAULT 100.0 CHECK(limiteDeuda >= 0),
                esFrecuente  BOOLEAN NOT NULL DEFAULT FALSE
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS BLOQUE (
                idBloque        SERIAL PRIMARY KEY,
                placa           VARCHAR(10) NOT NULL REFERENCES VEHICULO(placa),
                fecha           DATE NOT NULL,
                tipoBloque      VARCHAR(6) NOT NULL CHECK(tipoBloque IN ('DIA','NOCHE')),
                precio          NUMERIC(6,2) NOT NULL CHECK(precio >= 0),
                estado          VARCHAR(10) NOT NULL DEFAULT 'pendiente'
                                CHECK(estado IN ('pendiente','pagado','anulado')),
                responsablePago VARCHAR(100),
                creadoEn        TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS PAGO (
                idPago      SERIAL PRIMARY KEY,
                fechaPago   TIMESTAMP NOT NULL DEFAULT NOW(),
                montoTotal  NUMERIC(8,2) NOT NULL CHECK(montoTotal >= 0),
                metodoPago  VARCHAR(10) NOT NULL CHECK(metodoPago IN ('efectivo','yape')),
                idOperador  INTEGER NOT NULL REFERENCES USUARIO(idUsuario),
                observacion VARCHAR(300)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS PAGO_BLOQUE (
                idPago   INTEGER NOT NULL REFERENCES PAGO(idPago),
                idBloque INTEGER NOT NULL REFERENCES BLOQUE(idBloque),
                PRIMARY KEY (idPago, idBloque)
            );
        """)

        # Insertar tipos de vehiculo si no existen
        cur.execute("SELECT COUNT(*) as n FROM TIPO_VEHICULO")
        row = cur.fetchone()
        if row["count"] == 0:
            cur.execute("""
                INSERT INTO TIPO_VEHICULO (nombre, tarifa) VALUES
                ('Moto', 3.00), ('Auto', 5.00), ('Camioneta', 5.00),
                ('Minivan', 5.00), ('Combi', 8.00), ('Custer', 8.00),
                ('Bus', 10.00), ('Camion', 10.00)
                ON CONFLICT (nombre) DO NOTHING;
            """)

        # Insertar usuarios por defecto si no existen
        cur.execute("SELECT COUNT(*) as n FROM USUARIO")
        row = cur.fetchone()
        if row["count"] == 0:
            def sha256(t): return hashlib.sha256(t.encode()).hexdigest()
            cur.execute("""
                INSERT INTO USUARIO (nombre, username, passwordHash, rol) VALUES
                (%s, %s, %s, %s), (%s, %s, %s, %s)
                ON CONFLICT (username) DO NOTHING
            """, (
                'Operador 1', 'operador', sha256('operador123'), 'operador',
                'Presidenta',  'presidenta', sha256('presidenta123'), 'presidenta',
            ))
    yield


app = FastAPI(
    title="Sistema de Cochera API",
    version="1.0.0",
    description="API para gestión de estacionamiento y pagos.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    with db_session() as (cur, con):
        cur.execute(
            "SELECT * FROM USUARIO WHERE username = %s AND passwordHash = %s",
            (body.username, _sha256(body.password))
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")
    return dict(row)


# ══════════════════════════════════════════════════════════════
#  TIPOS DE VEHÍCULO
# ══════════════════════════════════════════════════════════════

@app.get("/tipos-vehiculo", response_model=List[TipoVehiculoOut], tags=["Catálogos"])
def listar_tipos():
    with db_session() as (cur, con):
        cur.execute("SELECT * FROM TIPO_VEHICULO ORDER BY nombre")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
#  PROPIETARIOS
# ══════════════════════════════════════════════════════════════

@app.post("/propietarios", response_model=PropietarioOut, status_code=201, tags=["Propietarios"])
def crear_propietario(body: PropietarioIn):
    with db_session() as (cur, con):
        cur.execute(
            "INSERT INTO PROPIETARIO (nombre, numCelular, email, direccion) VALUES (%s,%s,%s,%s) RETURNING *",
            (body.nombre, body.numCelular, body.email, body.direccion)
        )
        row = cur.fetchone()
    return dict(row)


@app.get("/propietarios", response_model=List[PropietarioOut], tags=["Propietarios"])
def buscar_propietarios(q: Optional[str] = Query(None)):
    sql = "SELECT * FROM PROPIETARIO"
    params: list = []
    if q:
        sql += " WHERE nombre ILIKE %s OR numCelular ILIKE %s"
        params = [f"%{q}%", f"%{q}%"]
    with db_session() as (cur, con):
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
#  VEHÍCULOS
# ══════════════════════════════════════════════════════════════

@app.post("/vehiculos", response_model=VehiculoOut, status_code=201, tags=["Vehículos"])
def registrar_vehiculo(body: VehiculoIn):
    with db_session() as (cur, con):
        cur.execute("SELECT placa FROM VEHICULO WHERE placa=%s", (body.placa,))
        if cur.fetchone():
            raise HTTPException(400, f"La placa {body.placa} ya está registrada.")
        cur.execute("SELECT idTipo FROM TIPO_VEHICULO WHERE idTipo=%s", (body.idTipo,))
        if not cur.fetchone():
            raise HTTPException(404, "Tipo de vehículo no encontrado.")
        cur.execute(
            """INSERT INTO VEHICULO (placa, idTipo, marcaModelo, color, idProp, limiteDeuda, esFrecuente)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (body.placa, body.idTipo, body.marcaModelo, body.color,
             body.idProp, body.limiteDeuda, body.esFrecuente)
        )
    return _get_vehiculo(body.placa)


@app.get("/vehiculos/{placa}", response_model=VehiculoOut, tags=["Vehículos"])
def obtener_vehiculo(placa: str):
    return _get_vehiculo(placa.upper())


@app.get("/vehiculos", response_model=List[VehiculoOut], tags=["Vehículos"])
def buscar_vehiculos(q: Optional[str] = Query(None)):
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
        sql += " WHERE V.placa ILIKE %s OR P.nombre ILIKE %s"
        params = [f"%{q}%", f"%{q}%"]
    with db_session() as (cur, con):
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(r) for r in rows]


def _get_vehiculo(placa: str) -> dict:
    with db_session() as (cur, con):
        cur.execute("""
            SELECT V.*, T.nombre AS tipoNombre, P.nombre AS propNombre,
                   COALESCE((SELECT SUM(precio) FROM BLOQUE
                             WHERE placa=V.placa AND estado='pendiente'), 0) AS deudaTotal
            FROM VEHICULO V
            JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo
            LEFT JOIN PROPIETARIO P ON V.idProp=P.idProp
            WHERE V.placa=%s
        """, (placa,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, f"Vehículo {placa} no encontrado.")
    return dict(row)


# ══════════════════════════════════════════════════════════════
#  BLOQUES
# ══════════════════════════════════════════════════════════════

@app.post("/bloques", response_model=BloqueOut, status_code=201, tags=["Bloques"])
def crear_bloque(body: BloqueIn):
    with db_session() as (cur, con):
        cur.execute(
            "SELECT V.placa, T.tarifa FROM VEHICULO V JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo WHERE V.placa=%s",
            (body.placa,)
        )
        veh = cur.fetchone()
        if not veh:
            raise HTTPException(404, f"Vehículo {body.placa} no registrado.")

        precio = veh["tarifa"]

        cur.execute(
            "SELECT COALESCE(SUM(precio),0) AS total FROM BLOQUE WHERE placa=%s AND estado='pendiente'",
            (body.placa,)
        )
        deuda = cur.fetchone()["total"]
        cur.execute("SELECT limiteDeuda FROM VEHICULO WHERE placa=%s", (body.placa,))
        limite = cur.fetchone()["limiteDeuda"]
        if deuda + precio > limite * 1.5:
            raise HTTPException(409, f"Deuda acumulada (S/{deuda:.2f}) supera el límite permitido (S/{limite:.2f}).")

        cur.execute(
            """INSERT INTO BLOQUE (placa, fecha, tipoBloque, precio, estado, responsablePago)
               VALUES (%s,%s,%s,%s,'pendiente',%s) RETURNING idBloque""",
            (body.placa, body.fecha.isoformat(), body.tipoBloque, precio, body.responsablePago)
        )
        id_bloque = cur.fetchone()["idbloque"]

        cur.execute("""
            SELECT B.*, T.nombre AS tipoNombre
            FROM BLOQUE B
            JOIN VEHICULO V ON B.placa=V.placa
            JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo
            WHERE B.idBloque=%s
        """, (id_bloque,))
        row = cur.fetchone()
    return dict(row)


@app.patch("/bloques/{id_bloque}/anular", response_model=BloqueOut, tags=["Bloques"])
def anular_bloque(id_bloque: int):
    with db_session() as (cur, con):
        cur.execute("SELECT * FROM BLOQUE WHERE idBloque=%s", (id_bloque,))
        bloque = cur.fetchone()
        if not bloque:
            raise HTTPException(404, "Bloque no encontrado.")
        if bloque["estado"] != "pendiente":
            raise HTTPException(400, f"Solo se puede anular un bloque 'pendiente' (estado actual: {bloque['estado']}).")
        cur.execute("UPDATE BLOQUE SET estado='anulado' WHERE idBloque=%s", (id_bloque,))
        cur.execute("""
            SELECT B.*, T.nombre AS tipoNombre
            FROM BLOQUE B JOIN VEHICULO V ON B.placa=V.placa
            JOIN TIPO_VEHICULO T ON V.idTipo=T.idTipo
            WHERE B.idBloque=%s
        """, (id_bloque,))
        row = cur.fetchone()
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
        sql += " AND B.placa=%s"; params.append(placa.upper())
    if estado:
        sql += " AND B.estado=%s"; params.append(estado)
    if fecha:
        sql += " AND B.fecha=%s"; params.append(fecha.isoformat())
    sql += " ORDER BY B.creadoEn DESC"
    with db_session() as (cur, con):
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(r) for r in rows]


# ══════════════════════════════════════════════════════════════
#  PAGOS
# ══════════════════════════════════════════════════════════════

@app.post("/pagos", response_model=PagoOut, status_code=201, tags=["Pagos"])
def registrar_pago(body: PagoIn):
    with db_session() as (cur, con):
        placeholders = ",".join(["%s"] * len(body.idsBloques))
        cur.execute(
            f"SELECT * FROM BLOQUE WHERE idBloque IN ({placeholders})",
            body.idsBloques
        )
        bloques = cur.fetchall()
        if len(bloques) != len(body.idsBloques):
            raise HTTPException(404, "Uno o más bloques no encontrados.")
        for b in bloques:
            if b["estado"] != "pendiente":
                raise HTTPException(400, f"Bloque {b['idbloque']} no está en estado 'pendiente'.")

        monto = sum(b["precio"] for b in bloques)

        cur.execute(
            """INSERT INTO PAGO (montoTotal, metodoPago, idOperador, observacion)
               VALUES (%s,%s,%s,%s) RETURNING idPago""",
            (monto, body.metodoPago, body.idOperador, body.observacion)
        )
        id_pago = cur.fetchone()["idpago"]

        for b in bloques:
            cur.execute("INSERT INTO PAGO_BLOQUE (idPago, idBloque) VALUES (%s,%s)", (id_pago, b["idbloque"]))
            cur.execute("UPDATE BLOQUE SET estado='pagado' WHERE idBloque=%s", (b["idbloque"],))

        cur.execute("SELECT * FROM PAGO WHERE idPago=%s", (id_pago,))
        row = cur.fetchone()
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
        sql += " AND fechaPago::date >= %s"; params.append(fecha_ini.isoformat())
    if fecha_fin:
        sql += " AND fechaPago::date <= %s"; params.append(fecha_fin.isoformat())
    if metodo:
        sql += " AND metodoPago=%s"; params.append(metodo)
    sql += " ORDER BY fechaPago DESC"
    with db_session() as (cur, con):
        cur.execute(sql, params)
        pagos = cur.fetchall()
        result = []
        for p in pagos:
            cur.execute("SELECT idBloque FROM PAGO_BLOQUE WHERE idPago=%s", (p["idpago"],))
            bloques = cur.fetchall()
            result.append({**dict(p), "bloquesCubiertos": [b["idbloque"] for b in bloques]})
    return result


# ══════════════════════════════════════════════════════════════
#  LIBRO DE DEUDAS
# ══════════════════════════════════════════════════════════════

@app.get("/deudas", tags=["Deudas"])
def libro_deudas(q: Optional[str] = Query(None)):
    sql = """
        SELECT
            V.placa, V.limiteDeuda, V.esFrecuente,
            T.nombre AS tipoNombre, P.nombre AS propNombre, P.numCelular,
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
        sql += " AND (V.placa ILIKE %s OR P.nombre ILIKE %s)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " GROUP BY V.placa, V.limiteDeuda, V.esFrecuente, T.nombre, P.nombre, P.numCelular HAVING COALESCE(SUM(CASE WHEN B.estado='pendiente' THEN B.precio ELSE 0 END),0) > 0 ORDER BY deudaTotal DESC"

    with db_session() as (cur, con):
        cur.execute(sql, params)
        rows = cur.fetchall()

    result = []
    for r in rows:
        d = dict(r)
        deuda = float(d["deudaTotal"])
        limite = float(d["limiteDeuda"])
        d["alerta"] = "rojo" if deuda > limite else "naranja" if deuda > limite * 0.8 else "normal"
        result.append(d)
    return result


# ══════════════════════════════════════════════════════════════
#  DASHBOARD
# ══════════════════════════════════════════════════════════════

@app.get("/dashboard", response_model=DashboardOut, tags=["Dashboard"])
def dashboard():
    hoy = date.today().isoformat()
    hora = datetime.now().hour
    turno = "NOCHE" if (hora >= 18 or hora < 8) else "DIA"

    with db_session() as (cur, con):
        cur.execute(
            "SELECT COUNT(DISTINCT placa) AS n FROM BLOQUE WHERE fecha=%s AND tipoBloque=%s AND estado='pendiente'",
            (hoy, turno)
        )
        presentes = cur.fetchone()["n"]

        cur.execute(
            "SELECT COALESCE(SUM(montoTotal),0) AS total FROM PAGO WHERE fechaPago::date=%s",
            (hoy,)
        )
        ingresos = cur.fetchone()["total"]

        cur.execute("SELECT COALESCE(SUM(precio),0) AS total FROM BLOQUE WHERE estado='pendiente'")
        deuda_total = cur.fetchone()["total"]

        cur.execute("SELECT COUNT(*) AS n FROM BLOQUE WHERE estado='pendiente'")
        pendientes = cur.fetchone()["n"]

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
