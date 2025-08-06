import sqlite3
import pdfplumber
import re
import os
from flask import Flask, request, jsonify, Response

# ========================
# BASE DE DATOS
# ========================
DB_NAME = "cristales.db"
conn = sqlite3.connect(DB_NAME, check_same_thread=False)
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
# LECTOR PDF OPTIMIZADO
# ========================
def cargar_precios_desde_pdf(pdf_path):
    cursor.execute("SELECT COUNT(*) FROM precios")
    if cursor.fetchone()[0] > 0:
        print("ℹ️ La base de datos ya contiene registros, no se recargará el PDF.")
        return

    print(f"📄 Cargando datos desde {pdf_path}...")
    batch = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                texto = page.extract_text()
                if not texto:
                    continue
                for linea in texto.split('\n'):
                    linea = linea.strip()
                    if not linea:
                        continue
                    precio_match = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})", linea)
                    if precio_match:
                        precio = float(precio_match.group(1).replace('.', '').replace(',', '.'))
                        partes = linea.split()
                        codigo = partes[0][:10]
                        descripcion = linea
                        batch.append((codigo, descripcion, precio))
                        cursor.execute("INSERT OR IGNORE INTO inventario (codigo, stock) VALUES (?, 0)", (codigo,))
                        if len(batch) >= 1000:
                            cursor.executemany("INSERT OR REPLACE INTO precios VALUES (?, ?, ?)", batch)
                            conn.commit()
                            batch.clear()
                print(f"✅ Página {page_num} procesada")
        if batch:
            cursor.executemany("INSERT OR REPLACE INTO precios VALUES (?, ?, ?)", batch)
            conn.commit()
        print("✅ Carga finalizada con éxito")
    except Exception as e:
        print(f"⚠️ Error al procesar PDF: {e}")

# ✅ Cargar solo si existe el PDF y la DB está vacía
db_pdf = "ListaPreciosFavicurAutomotor MARZO 2025.pdf"
if os.path.exists(db_pdf):
    cargar_precios_desde_pdf(db_pdf)
else:
    print(f"⚠️ PDF no encontrado: {db_pdf}")

# ========================
# FLASK APP
# ========================
app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot de Cristales activo"

@app.route("/buscar", methods=["GET"])
def api_buscar():
    q = request.args.get("q")
    if not q:
        return jsonify({"error": "Falta parámetro q"}), 400
    try:
        palabras = q.lower().split()
        where_clause = " AND ".join([f"lower(descripcion) LIKE '%{p}%'" for p in palabras])
        cursor.execute(f"SELECT * FROM precios WHERE {where_clause} LIMIT 10")
        resultados = cursor.fetchall()
        return jsonify(resultados)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ========================
# WEBHOOK WHATSAPP (BÚSQUEDA + INVENTARIO)
# ========================
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.form
    mensaje = data.get("Body", "").strip()
    respuesta = "❌ No entendí tu solicitud. Usa: buscar <modelo>, stock <codigo>, agregar <codigo> <cant>, restar <codigo> <cant>."

    if mensaje.lower().startswith("buscar"):
        query = mensaje[6:].strip()
        try:
            palabras = query.lower().split()
            where_clause = " AND ".join([f"lower(descripcion) LIKE '%{p}%'" for p in palabras])
            cursor.execute(f"SELECT * FROM precios WHERE {where_clause} LIMIT 5")
            resultados = cursor.fetchall()
            if resultados:
                respuesta = "\n".join([f"✅ {r[0]} | {r[1]} | ${r[2]:,.2f}" for r in resultados])
            else:
                respuesta = "❌ No se encontraron resultados."
        except Exception as e:
            respuesta = f"⚠️ Error interno: {e}"

    elif mensaje.lower().startswith("stock"):
        codigo = mensaje[5:].strip()
        cursor.execute("SELECT stock FROM inventario WHERE codigo=?", (codigo,))
        stock = cursor.fetchone()
        if stock:
            respuesta = f"📦 Stock de {codigo}: {stock[0]} unidades."
        else:
            respuesta = "❌ Código no encontrado."

    elif mensaje.lower().startswith("agregar"):
        partes = mensaje.split()
        if len(partes) == 3 and partes[2].isdigit():
            codigo, cantidad = partes[1], int(partes[2])
            cursor.execute("UPDATE inventario SET stock = stock + ? WHERE codigo=?", (cantidad, codigo))
            if cursor.rowcount > 0:
                conn.commit()
                cursor.execute("SELECT stock FROM inventario WHERE codigo=?", (codigo,))
                nuevo_stock = cursor.fetchone()[0]
                respuesta = f"✅ Stock actualizado: {codigo} ahora tiene {nuevo_stock} unidades."
            else:
                respuesta = "❌ Código no encontrado."
        else:
            respuesta = "⚠️ Usa: agregar <codigo> <cantidad>"

    elif mensaje.lower().startswith("restar"):
        partes = mensaje.split()
        if len(partes) == 3 and partes[2].isdigit():
            codigo, cantidad = partes[1], int(partes[2])
            cursor.execute("SELECT stock FROM inventario WHERE codigo=?", (codigo,))
            stock = cursor.fetchone()
            if stock:
                nuevo_stock = max(0, stock[0] - cantidad)
                cursor.execute("UPDATE inventario SET stock=? WHERE codigo=?", (nuevo_stock, codigo))
                conn.commit()
                respuesta = f"📉 Stock actualizado: {codigo} ahora tiene {nuevo_stock} unidades."
            else:
                respuesta = "❌ Código no encontrado."
        else:
            respuesta = "⚠️ Usa: restar <codigo> <cantidad>"

    twiml = f"<?xml version='1.0'?><Response><Message>{respuesta}</Message></Response>"
    return Response(twiml, mimetype='application/xml')

# ✅ Render usa puerto dinámico
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)