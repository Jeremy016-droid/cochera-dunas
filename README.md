# Sistema de Cochera — Backend FastAPI

## Estructura del proyecto

```
cochera/
├── db/
│   ├── schema.sql      ← Definición de tablas SQLite
│   ├── init_db.py      ← Crea cochera.db y usuarios de prueba
│   └── cochera.db      ← Se genera al ejecutar init_db.py
├── backend/
│   ├── main.py         ← FastAPI: todos los endpoints
│   ├── database.py     ← Conexión SQLite
│   └── schemas.py      ← Modelos Pydantic
├── requirements.txt
└── README.md
```

## Instalación (una sola vez)

```bash
# 1. Crear entorno virtual
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Mac/Linux

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Crear la base de datos
python db/init_db.py
```

## Ejecutar el servidor

```bash
uvicorn backend.main:app --reload
```

Abrir en el navegador: http://127.0.0.1:8000/docs

## Usuarios de prueba

| usuario     | contraseña      | rol        |
|-------------|-----------------|------------|
| operador    | operador123     | operador   |
| presidenta  | presidenta123   | presidenta |

---

## Endpoints disponibles

### Auth
| Método | Ruta             | Descripción           |
|--------|------------------|-----------------------|
| POST   | /auth/login      | Login por usuario/clave |

### Catálogos
| Método | Ruta               | Descripción                  |
|--------|--------------------|------------------------------|
| GET    | /tipos-vehiculo    | Lista tipos y tarifas        |

### Vehículos
| Método | Ruta                  | Descripción                        |
|--------|-----------------------|------------------------------------|
| POST   | /vehiculos            | Registrar vehículo nuevo           |
| GET    | /vehiculos            | Buscar por placa o propietario     |
| GET    | /vehiculos/{placa}    | Detalle con deuda total            |

### Bloques
| Método | Ruta                         | Descripción                    |
|--------|------------------------------|--------------------------------|
| POST   | /bloques                     | Registrar ingreso (nuevo bloque)|
| GET    | /bloques                     | Listar con filtros             |
| PATCH  | /bloques/{id}/anular         | Anular bloque                  |

### Pagos
| Método | Ruta    | Descripción                            |
|--------|---------|----------------------------------------|
| POST   | /pagos  | Registrar pago (cubre 1 o más bloques) |
| GET    | /pagos  | Listar pagos con filtros de fecha      |

### Deudas
| Método | Ruta     | Descripción                          |
|--------|----------|--------------------------------------|
| GET    | /deudas  | Libro de deudas con alertas          |

### Dashboard
| Método | Ruta        | Descripción               |
|--------|-------------|---------------------------|
| GET    | /dashboard  | Métricas del turno activo |

### Reportes
| Método | Ruta                | Descripción                      |
|--------|---------------------|----------------------------------|
| GET    | /reportes/turno     | Pagos y subtotales por turno     |
| GET    | /reportes/semanal   | Balance semanal efectivo/Yape    |

---

