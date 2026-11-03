import cv2
import numpy as np
import base64
import os
import datetime
import ssl
import socket
import ipaddress
import webbrowser
import threading
import time
from flask import Flask, render_template, Response, request
from flask_sock import Sock

# --- IMPORTACIONES PARA CERTIFICADO ---
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

app = Flask(__name__)
sock = Sock(app)

# Variable global para guardar el último frame recibido
current_frame = None

def obtener_ip_local():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

def generar_certificado():
    cert_path, key_path = "cert.pem", "key.pem"
    if os.path.exists(cert_path) and os.path.exists(key_path):
        return # Ya existe

    print("Generando certificado SSL...")
    ip_local = obtener_ip_local()
    
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with open(key_path, "wb") as f:
        f.write(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        ))

    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, u"MultiCAM"),
    ])
    
    san_list = [
        x509.DNSName(u"localhost"),
        x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        x509.IPAddress(ipaddress.ip_address(ip_local))
    ]

    cert = x509.CertificateBuilder().subject_name(subject).issuer_name(issuer).public_key(
        key.public_key()
    ).serial_number(x509.random_serial_number()).not_valid_before(
        datetime.datetime.utcnow()
    ).not_valid_after(
        datetime.datetime.utcnow() + datetime.timedelta(days=365)
    ).add_extension(
        x509.SubjectAlternativeName(san_list), critical=False,
    ).sign(key, hashes.SHA256())
    
    with open(cert_path, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    print("Certificado generado correctamente.")

# --- RUTAS ---

@app.route('/')
def index():
    """Página donde se ve el video en la PC."""
    return render_template('index.html')

@app.route('/camera')
def camera():
    """Página que abre el celular para transmitir."""
    return render_template('camera.html')

def generar_mjpeg():
    """Genera el stream de video para la página web."""
    global current_frame
    while True:
        if current_frame is not None:
            # Convertir el frame actual a JPEG
            ret, buffer = cv2.imencode('.jpg', current_frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
            if ret:
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.05) # ~20 FPS máximo

@app.route('/video_feed')
def video_feed():
    """Ruta que entrega el video MJPEG."""
    return Response(generar_mjpeg(), mimetype='multipart/x-mixed-replace; boundary=frame')

@sock.route('/ws')
def receive_video(ws):
    """WebSocket que recibe los frames del celular."""
    global current_frame
    print("Celular conectado. Recibiendo video...")
    try:
        while True:
            data = ws.receive()
            if data is None:
                break
            
            if isinstance(data, str):
                if ',' in data:
                    data = data.split(',')[1]
                img_bytes = base64.b64decode(data)
            else:
                img_bytes = data

            np_arr = np.frombuffer(img_bytes, np.uint8)
            frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
            
            if frame is not None:
                current_frame = frame
    except Exception:
        pass
    finally:
        print("Celular desconectado.")

if __name__ == '__main__':
    generar_certificado()
    ip_local = obtener_ip_local()
    
    # Abrir navegador automáticamente
    def abrir_navegador():
        time.sleep(1.5)
        webbrowser.open("https://localhost:5000/")
    
    threading.Thread(target=abrir_navegador, daemon=True).start()
    print('=' * 50)
    print("MonoCam Steam versión 1.0")
    print("Desarrollado por Totir Deloper - MIT License")
    print ("Link del código fuente: https://github.com/TotirDeloper/MonoCam-Stream")
    print("\n" + "="*50)
    print("SERVIDOR INICIADO")
    print(f"Ver video en PC: https://localhost:5000/")
    print(f"Link para el celular: https://{ip_local}:5000/camera")
    print("="*50 + "\n")
    
    # Silenciar errores de SSL de desconexión
    import logging
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

    app.run(
        host='0.0.0.0', 
        port=5000, 
        threaded=True, 
        ssl_context=('cert.pem', 'key.pem')
    )