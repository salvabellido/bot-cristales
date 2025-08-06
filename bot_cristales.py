import os
import sqlite3
import pdfplumber
import re
from flask import Flask, request, jsonify


DB_NAME = "cristales.db"

conn = sqlite3.connect(DB_NAME)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS precios (
    codigo TEXT PRIMARY KEY,
    descripcion TEXT,
    precio REAL
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS inventario (
    codigo TEXT PRIMARY KEY,
    stock INTEGER DEFAULT 0,
    FOREIGN KEY (codigo) REFERENCES precios(codigo)
)''')

conn.commit()

# ========================
# 1. FUNCION PARA LEER PDF Y CARGAR DATOS
# ========================
def cargar_precios_desde_pdf(pdf_path):
    descripcion_actual = None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            for line in text.split('\n'):
                line = line.strip()
                if not line:
                    continue
                
                # Detectar precio (formato con punto como separador de miles y coma como decimal)
                precio_match = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})", line)
                
                # Detectar código (alfanumérico, 3 a 6 caracteres)
                codigo_match = re.match(r"^[A-Z0-9]{3,6}$", line)
                
                if "MOD." in line or "PSAS" in line or "PUERTA" in line or "LUNETA" in line or "VENTANA" in line:
                    descripcion_actual = line
                elif codigo_match:
                    codigo_actual = codigo_match.group(0)
                elif precio_match and descripcion_actual:
                    precio_str = precio_match.group(1).replace('.', '').replace(',', '.')
                    precio = float(precio_str)
                    cursor.execute("INSERT OR REPLACE INTO precios VALUES (?, ?, ?)",
                                   (codigo_actual, descripcion_actual, precio))
                    cursor.execute("INSERT OR IGNORE INTO inventario (codigo, stock) VALUES (?, 0)", (codigo_actual,))
                    descripcion_actual = None  # reset para la próxima entrada
    conn.commit()
    print("✅ Lista de precios cargada correctamente.")

# ========================
# 2. BUSCAR CRISTAL
# ========================
def buscar_cristal(consulta):
    palabras = consulta.lower().split()
    where_clause = " AND ".join([f"lower(descripcion) LIKE '%{p}%'" for p in palabras])
    query = f"SELECT * FROM precios WHERE {where_clause}"
    cursor.execute(query)
    resultados = cursor.fetchall()
    if resultados:
        for r in resultados:
            print(f"✅ Código: {r[0]} | {r[1]} | Precio: ${r[2]:,.2f}")
    else:
        print("❌ No se encontró ningún cristal con esos datos.")

# ========================
# 3. INVENTARIO
# ========================
def actualizar_inventario(codigo, cantidad):
    cursor.execute("UPDATE inventario SET stock = stock + ? WHERE codigo = ?", (cantidad, codigo))
    conn.commit()
    cursor.execute("SELECT stock FROM inventario WHERE codigo = ?", (codigo,))
    stock = cursor.fetchone()
    if stock:
        print(f"📦 Stock actualizado: {codigo} ahora tiene {stock[0]} unidades.")
    else:
        print("❌ Código no encontrado en inventario.")

def mostrar_stock(codigo):
    cursor.execute("SELECT stock FROM inventario WHERE codigo = ?", (codigo,))
    stock = cursor.fetchone()
    if stock:
        print(f"📦 Stock de {codigo}: {stock[0]} unidades.")
    else:
        print("❌ Código no encontrado en inventario.")

# ========================
# USO DE EJEMPLO
# ========================
# cargar_precios_desde_pdf("ListaPreciosFavicurAutomotor MARZO 2025.pdf")
# buscar_cristal("parabrisas toyota corolla 2017")
# actualizar_inventario("1063", 5)
# mostrar_stock("1063")
from flask import Flask, request, jsonify

# Inicializa la aplicación Flask
app = Flask(__name__)

# Ruta principal: muestra mensaje de prueba
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.form
    mensaje = data.get("Body", "").strip()
    respuesta = "❌ No encontré resultados."

    if mensaje.lower().startswith("buscar"):
        query = mensaje[6:].strip()
        try:
            palabras = query.lower().split()
            where_clause = " AND ".join([f"lower(descripcion) LIKE '%{p}%'" for p in palabras])
            cursor.execute(f"SELECT * FROM precios WHERE {where_clause} LIMIT 3")
            resultados = cursor.fetchall()
            if resultados:
                respuesta = "\n".join([f"✅ {r[0]} | {r[1]} | ${r[2]:,.2f}" for r in resultados])
        except Exception as e:
            respuesta = f"⚠️ Error interno: {e}"

    twiml = f"<?xml version='1.0'?><Response><Message>{respuesta}</Message></Response>"
    return Response(twiml, mimetype='application/xml')