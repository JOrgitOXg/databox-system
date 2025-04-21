from flask import Flask
from app.config import Config
import firebase_admin
from firebase_admin import credentials

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Inicializar Firebase si no está ya inicializado
    try:
        firebase_admin.get_app()
    except ValueError:
        cred = credentials.Certificate(app.config['FIREBASE_CREDENTIALS_PATH'])
        firebase_admin.initialize_app(cred)
    
    # Registrar blueprints
    from app.routes.auth_routes import auth_bp
    from app.routes.survey_routes import survey_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(survey_bp, url_prefix='/survey')
    
    # Ruta raíz que redirecciona a login
    @app.route('/')
    def index():
        from flask import redirect, url_for
        return redirect(url_for('auth.login'))
    
    return app