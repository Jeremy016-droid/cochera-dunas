"""
main.py — Backend FastAPI del Sistema de Cochera (PostgreSQL/Supabase)
"""
import hashlib
import pathlib
import re
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
    with db_session() as (cur, con):
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tipo_vehiculo (
                id_tipo  SERIAL PRIMARY KEY,
                nombre   VARCHAR(50) NOT NULL UNIQUE,
                tarifa   NUMERIC(6,2) NOT NULL CHECK(tarifa >= 0)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS usuario (
                id_usuario    SERIAL PRIMARY KEY,
                nombre        VARCHAR(100) NOT NULL,
                username      VARCHAR(50) NOT NULL UNIQUE,
                password_hash VARCHAR(256) NOT NULL,
                rol           VARCHAR(20) NOT NULL CHECK(rol IN ('operador','presidenta'))
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS propietario (
                id_prop     SERIAL PRIMARY KEY,
                nombre      VARCHAR(100) NOT NULL,
                num_celular VARCHAR(20),
                email       VARCHAR(100),
                direccion   VARCHAR(200)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS vehiculo (
                placa        VARCHAR(10) PRIMARY KEY,
                id_tipo      INTEGER NOT NULL REFERENCES tipo_vehiculo(id_tipo),
                marca_modelo VARCHAR(100),
                color        VARCHAR(30),
                id_prop      INTEGER REFERENCES propietario(id_prop),
                limite_deuda NUMERIC(8,2) NOT NULL DEFAULT 100.0 CHECK(limite_deuda >= 0),
                es_frecuente BOOLEAN NOT NULL DEFAULT FALSE
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS bloque (
                id_bloque        SERIAL PRIMARY KEY,
                placa            VARCHAR(10) NOT NULL REFERENCES vehiculo(placa),
                fecha            DATE NOT NULL,
                tipo_bloque      VARCHAR(6) NOT NULL CHECK(tipo_bloque IN ('DIA','NOCHE')),
                precio           NUMERIC(6,2) NOT NULL CHECK(precio >= 0),
                estado           VARCHAR(10) NOT NULL DEFAULT 'pendiente'
                                 CHECK(estado IN ('pendiente','pagado','anulado')),
                responsable_pago VARCHAR(100),
                creado_en        TIMESTAMP NOT NULL DEFAULT NOW()
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pago (
                id_pago     SERIAL PRIMARY KEY,
                fecha_pago  TIMESTAMP NOT NULL DEFAULT NOW(),
                monto_total NUMERIC(8,2) NOT NULL CHECK(monto_total >= 0),
                metodo_pago VARCHAR(10) NOT NULL CHECK(metodo_pago IN ('efectivo','yape')),
                id_operador INTEGER NOT NULL REFERENCES usuario(id_usuario),
                observacion VARCHAR(300)
            );
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pago_bloque (
                id_pago   INTEGER NOT NULL REFERENCES pago(id_pago),
                id_bloque INTEGER NOT NULL REFERENCES bloque(id_bloque),
                PRIMARY KEY (id_pago, id_bloque)
            );
        """)
        cur.execute("SELECT COUNT(*) FROM tipo_vehiculo")
        if list(cur.fetchone().values())[0] == 0:
            cur.execute("""
                INSERT INTO tipo_vehiculo (nombre, tarifa) VALUES
                ('Moto',3.00),('Auto',5.00),('Camioneta',5.00),
                ('Minivan',5.00),('Combi',8.00),('Custer',8.00),
                ('Bus',10.00),('Camion',10.00)
                ON CONFLICT (nombre) DO NOTHING;
            """)
        # ── Migraciones incrementales (tablas ya existentes en Supabase) ──
        cur.execute("ALTER TABLE propietario ADD COLUMN IF NOT EXISTS dni VARCHAR(8);")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_propietario_dni ON propietario(dni);")
        cur.execute("ALTER TABLE pago ADD COLUMN IF NOT EXISTS tipo_comprobante VARCHAR(10) NOT NULL DEFAULT 'boleta';")
        cur.execute("ALTER TABLE pago ADD COLUMN IF NOT EXISTS num_documento VARCHAR(11);")
        cur.execute("SELECT COUNT(*) FROM usuario")
        if list(cur.fetchone().values())[0] == 0:
            def sha256(t): return hashlib.sha256(t.encode()).hexdigest()
            cur.execute("""
                INSERT INTO usuario (nombre, username, password_hash, rol) VALUES
                (%s,%s,%s,%s),(%s,%s,%s,%s) ON CONFLICT (username) DO NOTHING
            """, ('Operador 1','operador',sha256('operador123'),'operador',
                  'Presidenta','presidenta',sha256('presidenta123'),'presidenta'))
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


# ══ AUTH ══════════════════════════════════════════════════════
@app.post("/auth/login", response_model=UsuarioOut, tags=["Auth"])
def login(body: LoginIn):
    with db_session() as (cur, con):
        cur.execute(
            "SELECT * FROM usuario WHERE username=%s AND password_hash=%s",
            (body.username, _sha256(body.password))
        )
        row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Credenciales inválidas.")
    return dict(row)


# ══ TIPOS VEHICULO ════════════════════════════════════════════
@app.get("/tipos-vehiculo", response_model=List[TipoVehiculoOut], tags=["Catálogos"])
def listar_tipos():
    with db_session() as (cur, con):
        cur.execute("SELECT * FROM tipo_vehiculo ORDER BY nombre")
        rows = cur.fetchall()
    return [dict(r) for r in rows]


# ══ PROPIETARIOS ══════════════════════════════════════════════
@app.post("/propietarios", response_model=PropietarioOut, status_code=201, tags=["Propietarios"])
def crear_propietario(body: PropietarioIn):
    with db_session() as (cur, con):
        if body.dni:
            cur.execute("SELECT * FROM propietario WHERE dni=%s", (body.dni,))
            existente = cur.fetchone()
            if existente:
                raise HTTPException(400, f"Ya existe un propietario con DNI {body.dni} ({existente['nombre']}).")
        cur.execute(
            "INSERT INTO propietario (nombre, dni, num_celular, email, direccion) VALUES (%s,%s,%s,%s,%s) RETURNING *",
            (body.nombre, body.dni, body.num_celular, body.email, body.direccion)
        )
        row = cur.fetchone()
    return dict(row)

@app.get("/propietarios", response_model=List[PropietarioOut], tags=["Propietarios"])
def buscar_propietarios(q: Optional[str] = Query(None)):
    sql = "SELECT * FROM propietario"
    params = []
    if q:
        sql += " WHERE nombre ILIKE %s OR num_celular ILIKE %s OR dni ILIKE %s"
        params = [f"%{q}%", f"%{q}%", f"%{q}%"]
    with db_session() as (cur, con):
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(r) for r in rows]


# ══ VEHICULOS ═════════════════════════════════════════════════
@app.post("/vehiculos", response_model=VehiculoOut, status_code=201, tags=["Vehículos"])
def registrar_vehiculo(body: VehiculoIn):
    with db_session() as (cur, con):
        cur.execute("SELECT placa FROM vehiculo WHERE placa=%s", (body.placa,))
        if cur.fetchone():
            raise HTTPException(400, f"La placa {body.placa} ya está registrada.")
        cur.execute("SELECT id_tipo FROM tipo_vehiculo WHERE id_tipo=%s", (body.id_tipo,))
        if not cur.fetchone():
            raise HTTPException(404, "Tipo de vehículo no encontrado.")
        cur.execute(
            "INSERT INTO vehiculo (placa,id_tipo,marca_modelo,color,id_prop,limite_deuda,es_frecuente) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (body.placa,body.id_tipo,body.marca_modelo,body.color,body.id_prop,body.limite_deuda,body.es_frecuente)
        )
    return _get_vehiculo(body.placa)

@app.get("/vehiculos/{placa}", response_model=VehiculoOut, tags=["Vehículos"])
def obtener_vehiculo(placa: str):
    return _get_vehiculo(placa.upper())

@app.get("/vehiculos", response_model=List[VehiculoOut], tags=["Vehículos"])
def buscar_vehiculos(q: Optional[str] = Query(None), id_prop: Optional[int] = Query(None)):
    sql = """
        SELECT V.*, T.nombre AS tipo_nombre, P.nombre AS prop_nombre,
               P.dni AS prop_dni, P.num_celular AS prop_celular,
               COALESCE((SELECT SUM(precio) FROM bloque WHERE placa=V.placa AND estado='pendiente'),0) AS deuda_total
        FROM vehiculo V
        JOIN tipo_vehiculo T ON V.id_tipo=T.id_tipo
        LEFT JOIN propietario P ON V.id_prop=P.id_prop
        WHERE 1=1
    """
    params = []
    if q:
        sql += " AND (V.placa ILIKE %s OR P.nombre ILIKE %s OR P.dni ILIKE %s)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if id_prop:
        sql += " AND V.id_prop=%s"
        params.append(id_prop)
    with db_session() as (cur, con):
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(r) for r in rows]

def _get_vehiculo(placa: str) -> dict:
    with db_session() as (cur, con):
        cur.execute("""
            SELECT V.*, T.nombre AS tipo_nombre, P.nombre AS prop_nombre,
                   P.dni AS prop_dni, P.num_celular AS prop_celular,
                   COALESCE((SELECT SUM(precio) FROM bloque WHERE placa=V.placa AND estado='pendiente'),0) AS deuda_total
            FROM vehiculo V
            JOIN tipo_vehiculo T ON V.id_tipo=T.id_tipo
            LEFT JOIN propietario P ON V.id_prop=P.id_prop
            WHERE V.placa=%s
        """, (placa,))
        row = cur.fetchone()
    if not row:
        raise HTTPException(404, f"Vehículo {placa} no encontrado.")
    return dict(row)


# ══ BLOQUES ═══════════════════════════════════════════════════
@app.post("/bloques", response_model=BloqueOut, status_code=201, tags=["Bloques"])
def crear_bloque(body: BloqueIn):
    with db_session() as (cur, con):
        cur.execute(
            "SELECT V.placa, T.tarifa FROM vehiculo V JOIN tipo_vehiculo T ON V.id_tipo=T.id_tipo WHERE V.placa=%s",
            (body.placa,)
        )
        veh = cur.fetchone()
        if not veh:
            raise HTTPException(404, f"Vehículo {body.placa} no registrado.")
        precio = float(veh["tarifa"])
        cur.execute("SELECT COALESCE(SUM(precio),0) AS total FROM bloque WHERE placa=%s AND estado='pendiente'", (body.placa,))
        deuda = float(cur.fetchone()["total"])
        cur.execute("SELECT limite_deuda FROM vehiculo WHERE placa=%s", (body.placa,))
        limite = float(cur.fetchone()["limite_deuda"])
        if deuda + precio > limite * 1.5:
            raise HTTPException(409, f"Deuda acumulada (S/{deuda:.2f}) supera el límite (S/{limite:.2f}).")
        cur.execute(
            "INSERT INTO bloque (placa,fecha,tipo_bloque,precio,estado,responsable_pago) VALUES (%s,%s,%s,%s,'pendiente',%s) RETURNING id_bloque",
            (body.placa, body.fecha.isoformat(), body.tipo_bloque, precio, body.responsable_pago)
        )
        id_bloque = cur.fetchone()["id_bloque"]
        cur.execute("""
            SELECT B.*, T.nombre AS tipo_nombre
            FROM bloque B JOIN vehiculo V ON B.placa=V.placa
            JOIN tipo_vehiculo T ON V.id_tipo=T.id_tipo
            WHERE B.id_bloque=%s
        """, (id_bloque,))
        row = cur.fetchone()
    return dict(row)

@app.patch("/bloques/{id_bloque}/anular", response_model=BloqueOut, tags=["Bloques"])
def anular_bloque(id_bloque: int):
    with db_session() as (cur, con):
        cur.execute("SELECT * FROM bloque WHERE id_bloque=%s", (id_bloque,))
        bloque = cur.fetchone()
        if not bloque:
            raise HTTPException(404, "Bloque no encontrado.")
        if bloque["estado"] != "pendiente":
            raise HTTPException(400, f"Estado actual: {bloque['estado']}.")
        cur.execute("UPDATE bloque SET estado='anulado' WHERE id_bloque=%s", (id_bloque,))
        cur.execute("""
            SELECT B.*, T.nombre AS tipo_nombre
            FROM bloque B JOIN vehiculo V ON B.placa=V.placa
            JOIN tipo_vehiculo T ON V.id_tipo=T.id_tipo
            WHERE B.id_bloque=%s
        """, (id_bloque,))
        row = cur.fetchone()
    return dict(row)

@app.get("/bloques", response_model=List[BloqueOut], tags=["Bloques"])
def listar_bloques(placa: Optional[str]=None, estado: Optional[str]=None, fecha: Optional[date]=None):
    sql = """
        SELECT B.*, T.nombre AS tipo_nombre
        FROM bloque B JOIN vehiculo V ON B.placa=V.placa
        JOIN tipo_vehiculo T ON V.id_tipo=T.id_tipo WHERE 1=1
    """
    params = []
    if placa:
        sql += " AND B.placa=%s"; params.append(placa.upper())
    if estado:
        sql += " AND B.estado=%s"; params.append(estado)
    if fecha:
        sql += " AND B.fecha=%s"; params.append(fecha.isoformat())
    sql += " ORDER BY B.creado_en DESC"
    with db_session() as (cur, con):
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [dict(r) for r in rows]


# ══ PAGOS ═════════════════════════════════════════════════════
def _validar_comprobante(tipo_comprobante: str, num_documento: Optional[str]):
    tipo_comprobante = (tipo_comprobante or "boleta").lower()
    if tipo_comprobante not in ("boleta", "factura"):
        raise HTTPException(400, "tipo_comprobante debe ser 'boleta' o 'factura'.")
    if tipo_comprobante == "boleta" and num_documento:
        if not re.fullmatch(r"\d{8}", num_documento):
            raise HTTPException(400, "Para boleta, num_documento debe ser un DNI de 8 dígitos.")
    if tipo_comprobante == "factura":
        if not num_documento or not re.fullmatch(r"\d{11}", num_documento):
            raise HTTPException(400, "Para factura, num_documento debe ser un RUC de 11 dígitos.")
    return tipo_comprobante

@app.post("/pagos", response_model=PagoOut, status_code=201, tags=["Pagos"])
def registrar_pago(body: PagoIn):
    tipo_comprobante = _validar_comprobante(body.tipo_comprobante, body.num_documento)
    with db_session() as (cur, con):
        placeholders = ",".join(["%s"] * len(body.ids_bloques))
        cur.execute(f"SELECT * FROM bloque WHERE id_bloque IN ({placeholders})", body.ids_bloques)
        bloques = cur.fetchall()
        if len(bloques) != len(body.ids_bloques):
            raise HTTPException(404, "Uno o más bloques no encontrados.")
        for b in bloques:
            if b["estado"] != "pendiente":
                raise HTTPException(400, f"Bloque {b['id_bloque']} no está pendiente.")
        monto = sum(float(b["precio"]) for b in bloques)
        cur.execute(
            "INSERT INTO pago (monto_total,metodo_pago,id_operador,tipo_comprobante,num_documento,observacion) "
            "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id_pago",
            (monto, body.metodo_pago, body.id_operador, tipo_comprobante, body.num_documento, body.observacion)
        )
        id_pago = cur.fetchone()["id_pago"]
        for b in bloques:
            cur.execute("INSERT INTO pago_bloque (id_pago,id_bloque) VALUES (%s,%s)", (id_pago, b["id_bloque"]))
            cur.execute("UPDATE bloque SET estado='pagado' WHERE id_bloque=%s", (b["id_bloque"],))
        cur.execute("SELECT * FROM pago WHERE id_pago=%s", (id_pago,))
        row = cur.fetchone()
    return {**dict(row), "bloques_cubiertos": body.ids_bloques}

@app.get("/pagos", response_model=List[PagoOut], tags=["Pagos"])
def listar_pagos(fecha_ini: Optional[date]=None, fecha_fin: Optional[date]=None, metodo: Optional[str]=None):
    sql = "SELECT * FROM pago WHERE 1=1"
    params = []
    if fecha_ini:
        sql += " AND fecha_pago::date>=%s"; params.append(fecha_ini.isoformat())
    if fecha_fin:
        sql += " AND fecha_pago::date<=%s"; params.append(fecha_fin.isoformat())
    if metodo:
        sql += " AND metodo_pago=%s"; params.append(metodo)
    sql += " ORDER BY fecha_pago DESC"
    with db_session() as (cur, con):
        cur.execute(sql, params)
        pagos = cur.fetchall()
        result = []
        for p in pagos:
            cur.execute("SELECT id_bloque FROM pago_bloque WHERE id_pago=%s", (p["id_pago"],))
            bloques = cur.fetchall()
            result.append({**dict(p), "bloques_cubiertos": [b["id_bloque"] for b in bloques]})
    return result


# ══ DEUDAS ════════════════════════════════════════════════════
@app.get("/deudas", tags=["Deudas"])
def libro_deudas(q: Optional[str] = Query(None)):
    sql = """
        SELECT V.placa, V.limite_deuda, V.es_frecuente,
               T.nombre AS tipo_nombre, P.nombre AS prop_nombre, P.num_celular, P.dni,
               COALESCE(SUM(CASE WHEN B.estado='pendiente' THEN B.precio ELSE 0 END),0) AS deuda_total,
               COUNT(CASE WHEN B.estado='pendiente' THEN 1 END) AS bloques_pendientes,
               MIN(CASE WHEN B.estado='pendiente' THEN B.creado_en END) AS deuda_desde
        FROM vehiculo V
        JOIN tipo_vehiculo T ON V.id_tipo=T.id_tipo
        LEFT JOIN propietario P ON V.id_prop=P.id_prop
        LEFT JOIN bloque B ON V.placa=B.placa
        WHERE 1=1
    """
    params = []
    if q:
        sql += " AND (V.placa ILIKE %s OR P.nombre ILIKE %s OR P.dni ILIKE %s)"
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    sql += " GROUP BY V.placa,V.limite_deuda,V.es_frecuente,T.nombre,P.nombre,P.num_celular,P.dni HAVING COALESCE(SUM(CASE WHEN B.estado='pendiente' THEN B.precio ELSE 0 END),0)>0 ORDER BY deuda_total DESC"
    with db_session() as (cur, con):
        cur.execute(sql, params)
        rows = cur.fetchall()
    result = []
    ahora = datetime.now()
    for r in rows:
        d = dict(r)
        deuda = float(d["deuda_total"])
        limite = float(d["limite_deuda"])
        d["alerta"] = "rojo" if deuda > limite else "naranja" if deuda > limite * 0.8 else "normal"
        desde = d.pop("deuda_desde")
        d["dias_deuda"] = (ahora - desde).days if desde else 0
        result.append(d)
    return result


# ══ DASHBOARD ═════════════════════════════════════════════════
@app.get("/dashboard", response_model=DashboardOut, tags=["Dashboard"])
def dashboard():
    hoy = date.today().isoformat()
    turno = "NOCHE" if (datetime.now().hour >= 18 or datetime.now().hour < 8) else "DIA"
    with db_session() as (cur, con):
        cur.execute("SELECT COUNT(DISTINCT placa) AS n FROM bloque WHERE fecha=%s AND tipo_bloque=%s AND estado='pendiente'", (hoy, turno))
        presentes = cur.fetchone()["n"]
        cur.execute("SELECT COALESCE(SUM(monto_total),0) AS total FROM pago WHERE fecha_pago::date=%s", (hoy,))
        ingresos = cur.fetchone()["total"]
        cur.execute("SELECT COALESCE(SUM(precio),0) AS total FROM bloque WHERE estado='pendiente'")
        deuda_total = cur.fetchone()["total"]
        cur.execute("SELECT COUNT(*) AS n FROM bloque WHERE estado='pendiente'")
        pendientes = cur.fetchone()["n"]
    return {"vehiculos_presentes": presentes, "ingresos_turno": ingresos, "deuda_total": deuda_total, "bloques_pendientes": pendientes}


# ══ REPORTES ══════════════════════════════════════════════════
@app.get("/reportes/turno", tags=["Reportes"])
def reporte_turno(fecha: date = Query(...), turno: str = Query(...)):
    with db_session() as (cur, con):
        cur.execute("""
            SELECT B.placa, V.marca_modelo, T.nombre AS tipo_nombre,
                   P.monto_total, P.metodo_pago, U.nombre AS operador,
                   P.fecha_pago, P.observacion
            FROM pago P
            JOIN pago_bloque PB ON P.id_pago=PB.id_pago
            JOIN bloque B ON PB.id_bloque=B.id_bloque
            JOIN vehiculo V ON B.placa=V.placa
            JOIN tipo_vehiculo T ON V.id_tipo=T.id_tipo
            JOIN usuario U ON P.id_operador=U.id_usuario
            WHERE B.fecha=%s AND B.tipo_bloque=%s
            GROUP BY P.id_pago,B.placa,V.marca_modelo,T.nombre,P.monto_total,P.metodo_pago,U.nombre,P.fecha_pago,P.observacion
            ORDER BY P.fecha_pago
        """, (fecha.isoformat(), turno))
        pagos = cur.fetchall()
        cur.execute("""
            SELECT P.metodo_pago, COALESCE(SUM(P.monto_total),0) AS total
            FROM pago P JOIN pago_bloque PB ON P.id_pago=PB.id_pago
            JOIN bloque B ON PB.id_bloque=B.id_bloque
            WHERE B.fecha=%s AND B.tipo_bloque=%s GROUP BY P.metodo_pago
        """, (fecha.isoformat(), turno))
        subtotales = cur.fetchall()
    return {"fecha": fecha.isoformat(), "turno": turno, "pagos": [dict(r) for r in pagos], "subtotales": {r["metodo_pago"]: r["total"] for r in subtotales}}

@app.get("/reportes/semanal", tags=["Reportes"])
def reporte_semanal(fecha_ini: date = Query(...), fecha_fin: date = Query(...)):
    with db_session() as (cur, con):
        cur.execute("""
            SELECT fecha_pago::date AS dia, metodo_pago, SUM(monto_total) AS total
            FROM pago WHERE fecha_pago::date BETWEEN %s AND %s
            GROUP BY dia, metodo_pago ORDER BY dia
        """, (fecha_ini.isoformat(), fecha_fin.isoformat()))
        rows = cur.fetchall()
    ef = sum(float(r["total"]) for r in rows if r["metodo_pago"]=="efectivo")
    yp = sum(float(r["total"]) for r in rows if r["metodo_pago"]=="yape")
    return {"periodo": {"inicio": fecha_ini.isoformat(), "fin": fecha_fin.isoformat()}, "detalleDiario": [dict(r) for r in rows], "totalEfectivo": ef, "totalYape": yp, "granTotal": ef+yp}


# ══ FRONTEND ══════════════════════════════════════════════════
@app.get("/")
def root():
    return RedirectResponse("/login.html")

app.mount("/", StaticFiles(directory=str(BASE_DIR)), name="static")
