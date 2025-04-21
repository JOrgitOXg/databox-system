# app/routes/auth_routes.py
from flask import Blueprint
from app.controllers.auth_controller import (
    handle_login, 
    handle_register, 
    handle_forgot_password, 
    handle_reset_password,
    handle_logout
)

# Crear Blueprint para rutas de autenticación
auth_bp = Blueprint('auth', __name__)

# Definir rutas con nombres explícitos
auth_bp.route('/login', methods=['GET', 'POST'], endpoint='login')(handle_login)
auth_bp.route('/register', methods=['GET', 'POST'], endpoint='register')(handle_register)
auth_bp.route('/forgot-password', methods=['GET', 'POST'], endpoint='forgot_password')(handle_forgot_password)
auth_bp.route('/reset-password', methods=['GET', 'POST'], endpoint='reset_password')(handle_reset_password)
auth_bp.route('/logout', endpoint='logout')(handle_logout)