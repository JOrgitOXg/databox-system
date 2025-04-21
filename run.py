from app import create_app
from firebase_admin import credentials, auth, firestore
import firebase_admin

app = create_app()

# Configuración de Firebase (solo si aún no se ha inicializado)
if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

db = firestore.client()

if __name__ == '__main__':
    app.run(debug=True)
