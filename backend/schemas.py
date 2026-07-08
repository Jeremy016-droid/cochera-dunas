"""
schemas.py — Modelos Pydantic para request/response (PostgreSQL snake_case)
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


# ── TIPO_VEHICULO ─────────────────────────────────────────────
class TipoVehiculoOut(BaseModel):
    id_tipo: int
    nombre: str
    tarifa: float


# ── PROPIETARIO ───────────────────────────────────────────────
class PropietarioIn(BaseModel):
    nombre: str
    dni: Optional[str] = None
    num_celular: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None

class PropietarioOut(PropietarioIn):
    id_prop: int


# ── VEHICULO ──────────────────────────────────────────────────
class VehiculoIn(BaseModel):
    placa: str
    id_tipo: int
    marca_modelo: Optional[str] = None
    color: Optional[str] = None
    id_prop: Optional[int] = None
    limite_deuda: float = 100.0
    es_frecuente: bool = False

class VehiculoOut(BaseModel):
    placa: str
    id_tipo: int
    marca_modelo: Optional[str] = None
    color: Optional[str] = None
    id_prop: Optional[int] = None
    limite_deuda: float
    es_frecuente: bool
    tipo_nombre: Optional[str] = None
    prop_nombre: Optional[str] = None
    prop_dni: Optional[str] = None
    prop_celular: Optional[str] = None
    deuda_total: float = 0.0


# ── BLOQUE ────────────────────────────────────────────────────
class BloqueIn(BaseModel):
    placa: str
    fecha: date
    tipo_bloque: str
    responsable_pago: Optional[str] = None

class BloqueOut(BaseModel):
    id_bloque: int
    placa: str
    fecha: date
    tipo_bloque: str
    precio: float
    estado: str
    responsable_pago: Optional[str] = None
    creado_en: datetime
    tipo_nombre: Optional[str] = None


# ── PAGO ──────────────────────────────────────────────────────
class PagoIn(BaseModel):
    ids_bloques: List[int]
    metodo_pago: str
    id_operador: int
    tipo_comprobante: str = "boleta"     # 'boleta' | 'factura'
    num_documento: Optional[str] = None  # DNI (8 dig.) si boleta, RUC (11 dig.) si factura
    observacion: Optional[str] = None

class PagoOut(BaseModel):
    id_pago: int
    fecha_pago: datetime
    monto_total: float
    metodo_pago: str
    id_operador: int
    tipo_comprobante: str = "boleta"
    num_documento: Optional[str] = None
    observacion: Optional[str] = None
    bloques_cubiertos: List[int] = []


# ── USUARIO / AUTH ────────────────────────────────────────────
class LoginIn(BaseModel):
    username: str
    password: str

class UsuarioOut(BaseModel):
    id_usuario: int
    nombre: str
    username: str
    rol: str


# ── DASHBOARD ─────────────────────────────────────────────────
class DashboardOut(BaseModel):
    vehiculos_presentes: int
    ingresos_turno: float
    deuda_total: float
    bloques_pendientes: int
