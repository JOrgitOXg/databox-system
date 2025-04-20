from flask import request, session, flash, redirect, url_for, render_template
from firebase_admin import auth, firestore
from app.config import Config
import requests
from datetime import datetime

# Obtener instancia de Firestore
db = firestore.client()

def handle_login():
    if request.method != 'POST':
        return render_template('index.html')
    
    email = request.form.get('email')
    password = request.form.get('password')
    
    if not email or not password:
        flash('Por favor ingresa tanto el email como la contraseña', 'error')
        return redirect(url_for('auth.login'))
    
    try:
        # Autenticar con Firebase
        firebase_auth_url = f"{Config.SIGN_IN_URL}?key={Config.FIREBASE_WEB_API_KEY}"
        auth_payload = {
            "email": email,
            "password": password,
            "returnSecureToken": True
        }
        
        response = requests.post(firebase_auth_url, json=auth_payload)
        response_data = response.json()
        
        if response.status_code != 200:
            error_msg = response_data.get('error', {}).get('message', 'Error desconocido')
            
            # Mapeo de errores de Firebase a mensajes personalizados
            error_messages = {
                "EMAIL_NOT_FOUND": "No existe una cuenta con este email",
                "INVALID_PASSWORD": "Contraseña incorrecta",
                "USER_DISABLED": "Esta cuenta ha sido deshabilitada",
                "TOO_MANY_ATTEMPTS_TRY_LATER": "Demasiados intentos fallidos. Intenta más tarde",
                "INVALID_EMAIL": "El formato del email no es válido"
            }
            
            flash_message = error_messages.get(error_msg, "Error al iniciar sesión. Por favor intenta nuevamente")
            flash(flash_message, 'error')
            return redirect(url_for('auth.login'))
        
        # Si la autenticación fue exitosa
        user_id = response_data.get('localId')
        user = auth.get_user(user_id)
        
        # Obtener datos del usuario de Firestore
        user_ref = db.collection('users').where('email', '==', email).limit(1).get()
        
        if user_ref:
            user_data = user_ref[0].to_dict()
            full_name = user_data.get('fullName', user.email.split('@')[0])
        else:
            # Si no existe en Firestore, crear registro
            full_name = user.email.split('@')[0]
            db.collection('users').document(user.uid).set({
                'uid': user.uid,
                'email': user.email,
                'fullName': full_name,
                'createdAt': datetime.now()
            })
        
        session['user'] = {
            'uid': user.uid,
            'email': user.email,
            'name': full_name
        }
        
        # Actualizar lastLogin
        db.collection('users').document(user.uid).update({
            'lastLogin': datetime.now()
        })
        
        flash('Inicio de sesión exitoso', 'success')
        return redirect(url_for('survey.dashboard'))
        
    except Exception as e:
        flash('Ocurrió un error inesperado al iniciar sesión', 'error')
        return redirect(url_for('auth.login'))

def handle_register():
    if request.method != 'POST':
        return render_template('register.html')
    
    full_name = request.form.get('fullName')
    email = request.form.get('email')
    password = request.form.get('password')
    
    try:
        # Verificar si el email ya existe
        existing_users = auth.get_user_by_email(email)
        flash('Este email ya está registrado', 'error')
        return redirect(url_for('auth.register'))
    except auth.UserNotFoundError:
        try:
            user = auth.create_user(
                email=email,
                password=password,
                display_name=full_name
            )
            
            # Guardar en Firestore
            user_data = {
                'uid': user.uid,
                'fullName': full_name,
                'email': email,
                'createdAt': datetime.now(),
                'lastLogin': datetime.now(),
                'lastLogout': None
            }
            
            db.collection('users').document(user.uid).set(user_data)
            
            session['user'] = {
                'uid': user.uid,
                'email': user.email,
                'name': full_name
            }
            
            flash('Registro exitoso', 'success')
            return redirect(url_for('survey.dashboard'))
        except Exception as e:
            flash(f'Error en el registro: {str(e)}', 'error')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('auth.register'))

def handle_forgot_password():
    if request.method != 'POST':
        return render_template('forgot_password.html')
    
    email = request.form.get('email')
    try:
        # Verificar si el email existe
        auth.get_user_by_email(email)
        
        # Configurar la solicitud para enviar el correo de restablecimiento
        payload = {
            'requestType': 'PASSWORD_RESET',
            'email': email
        }
        
        # Parámetros de la solicitud
        params = {
            'key': Config.FIREBASE_WEB_API_KEY
        }
        
        # Enviar la solicitud a Firebase
        response = requests.post(Config.RESET_PASSWORD_URL, params=params, json=payload)
        
        # Verificar si hubo errores
        if response.status_code != 200:
            error_data = response.json()
            flash(f'Error al enviar el correo: {error_data.get("error", {}).get("message", "Error desconocido")}', 'error')
            return redirect(url_for('auth.forgot_password'))
        
        flash('Se ha enviado un correo con instrucciones para restablecer tu contraseña', 'success')
        return redirect(url_for('auth.login'))
        
    except auth.UserNotFoundError:
        flash('No existe una cuenta con este email', 'error')
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
    
    return redirect(url_for('auth.forgot_password'))

def handle_reset_password():
    if request.method == 'POST':
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        oob_code = request.form.get('oobCode')
        
        if not new_password or not confirm_password:
            flash('Por favor completa todos los campos', 'error')
            return render_template('reset_password.html', oobCode=oob_code)
            
        if new_password != confirm_password:
            flash('Las contraseñas no coinciden', 'error')
            return render_template('reset_password.html', oobCode=oob_code)
            
        if len(new_password) < 6:
            flash('La contraseña debe tener al menos 6 caracteres', 'error')
            return render_template('reset_password.html', oobCode=oob_code)
            
        try:
            # Configurar la solicitud para restablecer la contraseña
            payload = {
                'oobCode': oob_code,
                'newPassword': new_password
            }
            
            # Parámetros de la solicitud
            params = {
                'key': Config.FIREBASE_WEB_API_KEY
            }
            
            # Enviar la solicitud a Firebase
            reset_url = "https://identitytoolkit.googleapis.com/v1/accounts:resetPassword"
            response = requests.post(reset_url, params=params, json=payload)
            
            # Verificar si hubo errores
            if response.status_code != 200:
                error_data = response.json()
                flash(f'Error al restablecer la contraseña: {error_data.get("error", {}).get("message", "Error desconocido")}', 'error')
                return render_template('reset_password.html', oobCode=oob_code)
            
            flash('Tu contraseña ha sido restablecida correctamente. Ahora puedes iniciar sesión.', 'success')
            return redirect(url_for('auth.login'))
            
        except Exception as e:
            flash(f'Error al restablecer la contraseña: {str(e)}', 'error')
            return render_template('reset_password.html', oobCode=oob_code)
    
    oob_code = request.args.get('oobCode')
    if not oob_code:
        flash('El enlace de restablecimiento no es válido', 'error')
        return redirect(url_for('auth.forgot_password'))
        
    return render_template('reset_password.html', oobCode=oob_code)

def handle_logout():
    try:
        if 'user' in session:
            # Actualizar lastLogout
            db.collection('users').document(session['user']['uid']).update({
                'lastLogout': datetime.now()
            })
    except Exception as e:
        print(f"Error al actualizar lastLogout: {str(e)}")
    
    session.pop('user', None)
    flash('Sesión cerrada correctamente', 'success')
    return redirect(url_for('auth.login'))