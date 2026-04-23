from fastapi import FastAPI, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import date, datetime
import time
import requests
import os

# --- 1. CREDENCIALES INVISIBLES (VARIABLES DE ENTORNO) ---
DB_URL = os.getenv("DB_URL")
engine = create_engine(DB_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# --- 2. TABLAS ---
class Foto(Base):
    __tablename__ = "fotos"
    id = Column(Integer, primary_key=True, index=True)
    url = Column(String)
    descripcion = Column(String)

class EstadoApp(Base):
    __tablename__ = "estado_app"
    id = Column(Integer, primary_key=True)
    emocion = Column(String, default="Felices de estar juntos 🥰")
    te_extrano_count = Column(Integer, default=0)
    fecha_reinicio = Column(String, default=date.today().isoformat())
    pet_hambre = Column(Float, default=20.0)
    pet_felicidad = Column(Float, default=80.0)
    ultima_interaccion = Column(String, default=datetime.now().isoformat())

Base.metadata.create_all(bind=engine)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# --- 3. LÓGICA DE TIEMPO REAL ---
def procesar_logica_tiempo(estado):
    ahora = datetime.now()
    hoy = date.today().isoformat()
    
    if estado.fecha_reinicio != hoy:
        estado.te_extrano_count = 0
        estado.fecha_reinicio = hoy

    ultima_vez = datetime.fromisoformat(estado.ultima_interaccion)
    horas_pasadas = (ahora - ultima_vez).total_seconds() / 3600
    
    if horas_pasadas > 0:
        estado.pet_hambre = min(100, estado.pet_hambre + (horas_pasadas * 3))
        estado.pet_felicidad = max(0, estado.pet_felicidad - (horas_pasadas * 2))
        estado.ultima_interaccion = ahora.isoformat()

# --- 4. RUTAS BLINDADAS ---
@app.get("/data_inicial")
def obtener_todo():
    db = SessionLocal()
    try:
        estado = db.query(EstadoApp).first()
        if not estado:
            estado = EstadoApp()
            db.add(estado)
        procesar_logica_tiempo(estado)
        db.commit()
        db.refresh(estado)
        fotos = db.query(Foto).all()
        return {
            "fotos": [{"id": f.id, "url": f.url, "descripcion": f.descripcion} for f in fotos],
            "estado": {
                "emocion": estado.emocion,
                "te_extrano": estado.te_extrano_count,
                "pet": {"hambre": round(estado.pet_hambre), "felicidad": round(estado.pet_felicidad)}
            }
        }
    finally:
        db.close()

@app.post("/te-extrano")
def sumar_te_extrano():
    db = SessionLocal()
    try:
        estado = db.query(EstadoApp).first()
        procesar_logica_tiempo(estado)
        estado.te_extrano_count += 1
        db.commit()
        return {"count": estado.te_extrano_count}
    finally:
        db.close()

@app.post("/cuidar-mascota")
def cuidar_mascota(accion: str = Form(...)):
    db = SessionLocal()
    try:
        estado = db.query(EstadoApp).first()
        procesar_logica_tiempo(estado)
        if accion == "alimentar":
            estado.pet_hambre = max(0, estado.pet_hambre - 30)
            estado.pet_felicidad = min(100, estado.pet_felicidad + 10)
        elif accion == "jugar":
            estado.pet_felicidad = min(100, estado.pet_felicidad + 30)
            estado.pet_hambre = min(100, estado.pet_hambre + 15)
        elif accion == "dormir":
            estado.pet_felicidad = min(100, estado.pet_felicidad + 15)
        
        estado.ultima_interaccion = datetime.now().isoformat()
        db.commit()
        return {"hambre": round(estado.pet_hambre), "felicidad": round(estado.pet_felicidad)}
    finally:
        db.close()

@app.post("/subir-foto")
async def subir_foto(archivo: UploadFile = File(...), descripcion: str = Form(...)):
    file_bytes = await archivo.read()
    nombre_unico = f"{int(time.time())}_{archivo.filename.replace(' ', '_')}"
    url_storage = f"{SUPABASE_URL}/storage/v1/object/fotos-recuerdos/{nombre_unico}"
    headers = {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": archivo.content_type}
    
    respuesta = requests.post(url_storage, headers=headers, data=file_bytes)
    if respuesta.status_code >= 400:
        return {"status": "error", "detalle": "Error al subir a Supabase."}
    
    public_url = f"{SUPABASE_URL}/storage/v1/object/public/fotos-recuerdos/{nombre_unico}"
    db = SessionLocal()
    try:
        nueva = Foto(url=public_url, descripcion=descripcion)
        db.add(nueva)
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()

@app.delete("/borrar-foto/{foto_id}")
def borrar_foto(foto_id: int):
    db = SessionLocal()
    try:
        foto = db.query(Foto).filter(Foto.id == foto_id).first()
        if foto:
            nombre_archivo = foto.url.split("/")[-1]
            url_storage = f"{SUPABASE_URL}/storage/v1/object/fotos-recuerdos/{nombre_archivo}"
            requests.delete(url_storage, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
            db.delete(foto)
            db.commit()
        return {"status": "ok"}
    finally:
        db.close()

@app.post("/actualizar-estado")
def actualizar_estado(nueva_emocion: str = Form(...)):
    db = SessionLocal()
    try:
        estado = db.query(EstadoApp).first()
        estado.emocion = nueva_emocion
        db.commit()
        return {"status": "ok"}
    finally:
        db.close()