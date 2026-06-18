"""
schemas.py — Modelos Pydantic para request / response
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime


# ── TIPO_VEHICULO ─────────────────────────────────────────────
class TipoVehiculoOut(BaseModel):
    idTipo: int
    nombre: str
    tarifa: float


# ── PROPIETARIO ───────────────────────────────────────────────
class PropietarioIn(BaseModel):
    nombre: str
    numCelular: Optional[str] = None
    email: Optional[str] = None
    direccion: Optional[str] = None

class PropietarioOut(PropietarioIn):
    idProp: int


# ── VEHICULO ──────────────────────────────────────────────────
class VehiculoIn(BaseModel):
    placa: str = Field(..., min_length=5, max_length=10)
    idTipo: int
    marcaModelo: Optional[str] = None
    color: Optional[str] = None
    idProp: Optional[int] = None
    limiteDeuda: float = 100.0
    esFrecuente: bool = False

class VehiculoOut(VehiculoIn):
    tipoNombre: Optional[str] = None
    propNombre: Optional[str] = None
    deudaTotal: float = 0.0


# ── BLOQUE ────────────────────────────────────────────────────
class BloqueIn(BaseModel):
    placa: str
    fecha: date
    tipoBloque: str = Field(..., pattern="^(DIA|NOCHE)$")
    responsablePago: Optional[str] = None
    # precio se calcula automáticamente desde TIPO_VEHICULO

class BloqueOut(BaseModel):
    idBloque: int
    placa: str
    fecha: date
    tipoBloque: str
    precio: float
    estado: str
    responsablePago: Optional[str]
    creadoEn: datetime
    tipoNombre: Optional[str] = None


# ── PAGO ──────────────────────────────────────────────────────
class PagoIn(BaseModel):
    idsBloques: List[int]
    metodoPago: str = Field(..., pattern="^(efectivo|yape)$")
    idOperador: int
    observacion: Optional[str] = None

class PagoOut(BaseModel):
    idPago: int
    fechaPago: datetime
    montoTotal: float
    metodoPago: str
    idOperador: int
    observacion: Optional[str]
    bloquesCubiertos: List[int] = []


# ── USUARIO / AUTH ────────────────────────────────────────────
class LoginIn(BaseModel):
    username: str
    password: str

class UsuarioOut(BaseModel):
    idUsuario: int
    nombre: str
    username: str
    rol: str


# ── DASHBOARD ─────────────────────────────────────────────────
class DashboardOut(BaseModel):
    vehiculosPresentes: int
    ingresosTurno: float
    deudaTotal: float
    bloquesPendientes: int
