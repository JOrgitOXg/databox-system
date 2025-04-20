class Config:
    # Configuración de la aplicación
    SECRET_KEY = "tu_clave_secreta_aqui"
    
    # Firebase Web API Key para operaciones del lado del cliente
    FIREBASE_WEB_API_KEY = "AIzaSyAWePs8l11z6KMrPfg-VbUK9KVrlcieczs"
    
    # URLs para operaciones de autenticación
    RESET_PASSWORD_URL = "https://identitytoolkit.googleapis.com/v1/accounts:sendOobCode"
    SIGN_IN_URL = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    FIREBASE_CREDENTIALS_PATH = 'serviceAccountKey.json'
    # Modo Debug
    DEBUG = True