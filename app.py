from flask import Flask, render_template, redirect, url_for, request, flash, session
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, auth
from firebase_admin import firestore

from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            flash('Por favor inicia sesión primero', 'error')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

@app.route('/')
def home():
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            user = auth.get_user_by_email(email)
            session['user'] = {
                'uid': user.uid,
                'email': user.email,
                'name': user.display_name or email.split('@')[0]
            }
            flash('Inicio de sesión exitoso', 'success')
            return redirect(url_for('dashboard'))
        except auth.UserNotFoundError:
            flash('Usuario no encontrado', 'error')
        except Exception as e:
            flash(f'Error al iniciar sesión: {str(e)}', 'error')
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        full_name = request.form.get('fullName')
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            user = auth.create_user(
                email=email,
                password=password,
                display_name=full_name
            )
            
            db.collection('users').document(user.uid).set({
                'fullName': full_name,
                'email': email,
                'createdAt': datetime.now()
            })
            
            session['user'] = {
                'uid': user.uid,
                'email': user.email,
                'name': full_name
            }
            
            flash('Registro exitoso', 'success')
            return redirect(url_for('dashboard'))
        except auth.EmailAlreadyExistsError:
            flash('Este email ya está registrado', 'error')
        except Exception as e:
            flash(f'Error en el registro: {str(e)}', 'error')
    return render_template('register.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        try:
            auth.generate_password_reset_link(email)
            flash('Se ha enviado un correo con instrucciones', 'success')
            return redirect(url_for('login'))
        except auth.UserNotFoundError:
            flash('No existe una cuenta con este email', 'error')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
    return render_template('forgot_password.html')

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        surveys_ref = db.collection('surveys').where('owner', '==', session['user']['uid']).stream()
        surveys = []
        
        for survey in surveys_ref:
            survey_data = survey.to_dict()
            survey_data['id'] = survey.id
            if 'createdAt' in survey_data:
                if hasattr(survey_data['createdAt'], 'date'):
                    survey_data['createdAt'] = survey_data['createdAt'].date().strftime('%d/%m/%Y')
                else:
                    survey_data['createdAt'] = "Fecha no disponible"
            surveys.append(survey_data)
        
        return render_template('dashboard.html', 
                            user_name=session['user']['name'],
                            surveys=surveys)
    except Exception as e:
        flash(f'Error al cargar dashboard: {str(e)}', 'error')
        return redirect(url_for('login'))

@app.route('/create-survey', methods=['GET', 'POST'])
@login_required
def create_survey():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        questions = [q for q in request.form.getlist('questions[]') if q.strip()]
        
        if not questions:
            flash('Debes agregar al menos una pregunta', 'error')
            return render_template('create_survey.html')
        
        try:
            db.collection('surveys').add({
                'title': title,
                'description': description,
                'questions': questions,
                'owner': session['user']['uid'],
                'createdAt': datetime.now(),
                'responses': 0
            })
            flash('Encuesta creada exitosamente', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error al crear encuesta: {str(e)}', 'error')
    
    return render_template('create_survey.html')

@app.route('/survey/<survey_id>')
@login_required
def view_survey(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey = survey_ref.get().to_dict()
        
        if not survey or survey['owner'] != session['user']['uid']:
            flash('Encuesta no encontrada', 'error')
            return redirect(url_for('dashboard'))
        
        if 'createdAt' in survey:
            if hasattr(survey['createdAt'], 'strftime'):
                survey['createdAt'] = survey['createdAt'].strftime('%d/%m/%Y a las %H:%M')
            else:
                survey['createdAt'] = "Fecha no disponible"
        
        return render_template('survey.html', survey=survey)
    except Exception as e:
        flash(f'Error al cargar encuesta: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    try:
        if 'user' in session:
            db.collection('users').document(session['user']['uid']).update({
                'lastLogout': datetime.now()
            })
    except Exception as e:
        print(f"Error al actualizar lastLogout: {str(e)}")
    
    session.pop('user', None)
    flash('Sesión cerrada correctamente', 'success')
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)