-- ============================================================
--  SISTEMA DE COCHERA — Esquema SQLite
--  Fase local · Mayo 2026
-- ============================================================

PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- ------------------------------------------------------------
-- 1. TIPO_VEHICULO
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS TIPO_VEHICULO (
    idTipo  INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre  TEXT    NOT NULL UNIQUE,          -- Moto, Auto, Camioneta…
    tarifa  REAL    NOT NULL CHECK(tarifa >= 0)
);

INSERT OR IGNORE INTO TIPO_VEHICULO (nombre, tarifa) VALUES
    ('Moto',      3.00),
    ('Auto',      5.00),
    ('Camioneta', 5.00),
    ('Minivan',   5.00),
    ('Combi',     8.00),
    ('Custer',    8.00),
    ('Bus',      10.00),
    ('Camión',   10.00);

-- ------------------------------------------------------------
-- 2. USUARIO
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS USUARIO (
    idUsuario    INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre       TEXT    NOT NULL,
    username     TEXT    NOT NULL UNIQUE,
    passwordHash TEXT    NOT NULL,
    rol          TEXT    NOT NULL CHECK(rol IN ('operador', 'presidenta'))
);

-- ------------------------------------------------------------
-- 3. PROPIETARIO
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PROPIETARIO (
    idProp    INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre    TEXT NOT NULL,
    numCelular TEXT,
    email     TEXT,
    direccion TEXT
);

-- ------------------------------------------------------------
-- 4. VEHICULO
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS VEHICULO (
    placa        TEXT PRIMARY KEY,
    idTipo       INTEGER NOT NULL REFERENCES TIPO_VEHICULO(idTipo),
    marcaModelo  TEXT,
    color        TEXT,
    idProp       INTEGER REFERENCES PROPIETARIO(idProp),
    limiteDeuda  REAL    NOT NULL DEFAULT 100.0 CHECK(limiteDeuda >= 0),
    esFrecuente  INTEGER NOT NULL DEFAULT 0 CHECK(esFrecuente IN (0, 1))
);

-- ------------------------------------------------------------
-- 5. BLOQUE
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS BLOQUE (
    idBloque        INTEGER PRIMARY KEY AUTOINCREMENT,
    placa           TEXT    NOT NULL REFERENCES VEHICULO(placa),
    fecha           DATE    NOT NULL,
    tipoBloque      TEXT    NOT NULL CHECK(tipoBloque IN ('DIA', 'NOCHE')),
    precio          REAL    NOT NULL CHECK(precio >= 0),
    estado          TEXT    NOT NULL DEFAULT 'pendiente'
                            CHECK(estado IN ('pendiente', 'pagado', 'anulado')),
    responsablePago TEXT,                -- chofer / propietario / otro
    creadoEn        DATETIME NOT NULL DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_bloque_placa  ON BLOQUE(placa);
CREATE INDEX IF NOT EXISTS idx_bloque_estado ON BLOQUE(estado);

-- ------------------------------------------------------------
-- 6. PAGO
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PAGO (
    idPago      INTEGER PRIMARY KEY AUTOINCREMENT,
    fechaPago   DATETIME NOT NULL DEFAULT (datetime('now', 'localtime')),
    montoTotal  REAL     NOT NULL CHECK(montoTotal >= 0),
    metodoPago  TEXT     NOT NULL CHECK(metodoPago IN ('efectivo', 'yape')),
    idOperador  INTEGER  NOT NULL REFERENCES USUARIO(idUsuario),
    observacion TEXT
);

-- ------------------------------------------------------------
-- 7. PAGO_BLOQUE  (tabla intermedia M:N)
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS PAGO_BLOQUE (
    idPago   INTEGER NOT NULL REFERENCES PAGO(idPago),
    idBloque INTEGER NOT NULL REFERENCES BLOQUE(idBloque),
    PRIMARY KEY (idPago, idBloque)
);
