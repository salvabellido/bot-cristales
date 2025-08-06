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
# FUNCIONES
# ========================
def cargar_precios_desde_pdf(pdf_path):
    descripcion_actual = None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for line in page.extract_text().split('\n'):
                line = line.strip()
                if not line:
                    continue
                precio_match = re.search(r"(\d{1,3}(?:\.\d{3})*,\d{2})", line)
                codigo_match = re.match(r"^[A-Z0-9]{3,6}$", line)
                if "MOD." in line or "PSAS" in line or "PUERTA" in line or "LUNETA" in line or "VENTANA" in line:
                    descripcion_actual = line
                elif codigo_match:
                    codigo_actual = codigo_match.group(0)
                elif precio_match and descripcion_actual:
                    precio = float(precio_match.group(1).replace('.', '').replace(',', '.'))
                    cursor.execute("INSERT OR REPLACE INTO precios VALUES (?, ?, ?)",
                                   (codigo_actual, descripcion_actual, precio))
                    cursor.execute("INSERT OR IGNORE INTO inventario (codigo, stock) VALUES (?, 0)", (codigo_actual,))
                    descripcion_actual = None
    conn.commit()

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
        cursor.execute(f"SELECT * FROM precios WHERE {where_clause} LIMIT 5")
        resultados = cursor.fetchall()
        return jsonify(resultados)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

# ✅ Render necesita esto
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
