from flask import Flask, render_template, redirect, url_for, request, flash, session
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, auth, firestore
from config import Config

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = Config.SECRET_KEY

# Configuración de Firebase
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Función para requerir inicio de sesión
def login_required(f):
    def wrapper(*args, **kwargs):
        if 'user' not in session:
            flash('Por favor inicia sesión primero', 'error')
            return redirect(url_for('login', next=request.url))
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper

# Ruta principal
@app.route('/')
def home():
    return redirect(url_for('login'))

# Ruta de inicio de sesión
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

# Ruta de registro
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

# Ruta de olvido de contraseña
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

# Ruta del dashboard
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

# Ruta para crear encuestas
@app.route('/create-survey', methods=['GET', 'POST'])
@login_required
def create_survey():
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        questions = request.form.getlist('questions[]')
        question_types = request.form.getlist('question_types[]')
        question_options = request.form.getlist('question_options[]')
        
        # Procesar las preguntas
        processed_questions = []
        for i, (q_text, q_type) in enumerate(zip(questions, question_types)):
            question_data = {
                'text': q_text,
                'type': q_type
            }
            
            if q_type == 'multiple':
                options = [opt.strip() for opt in question_options[i].split(',') if opt.strip()]
                question_data['options'] = options
            
            processed_questions.append(question_data)
        
        if not processed_questions:
            flash('Debes agregar al menos una pregunta', 'error')
            return render_template('create_survey.html')
        
        try:
            db.collection('surveys').add({
                'title': title,
                'description': description,
                'questions': processed_questions,
                'owner': session['user']['uid'],
                'createdAt': datetime.now(),
                'responses': 0
            })
            flash('Encuesta creada exitosamente', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error al crear encuesta: {str(e)}', 'error')
    
    return render_template('create_survey.html')

# Ruta para editar una encuesta
@app.route('/edit-survey/<survey_id>', methods=['GET', 'POST'])
@login_required
def edit_survey(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        
        if not survey_doc.exists or survey_doc.to_dict()['owner'] != session['user']['uid']:
            flash('No tienes permiso para editar esta encuesta', 'error')
            return redirect(url_for('dashboard'))
        
        survey = survey_doc.to_dict()
        survey['id'] = survey_id
        
        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            questions = request.form.getlist('questions[]')
            question_types = request.form.getlist('question_types[]')
            question_options = request.form.getlist('question_options[]')
            
            # Procesar las preguntas
            processed_questions = []
            for i, (q_text, q_type) in enumerate(zip(questions, question_types)):
                question_data = {
                    'text': q_text,
                    'type': q_type
                }
                
                if q_type == 'multiple':
                    options = [opt.strip() for opt in question_options[i].split(',') if opt.strip()]
                    question_data['options'] = options
                
                processed_questions.append(question_data)
            
            if not processed_questions:
                flash('Debes agregar al menos una pregunta', 'error')
                return render_template('create_survey.html', survey=survey)
            
            try:
                survey_ref.update({
                    'title': title,
                    'description': description,
                    'questions': processed_questions,
                    'updatedAt': datetime.now()
                })
                flash('Encuesta actualizada exitosamente', 'success')
                return redirect(url_for('view_survey', survey_id=survey_id))
            except Exception as e:
                flash(f'Error al actualizar encuesta: {str(e)}', 'error')
        
        return render_template('create_survey.html', survey=survey)
    except Exception as e:
        flash(f'Error al cargar encuesta para edición: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

# Ruta para ver una encuesta
@app.route('/survey/<survey_id>')
@login_required
def view_survey(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        
        if not survey_doc.exists or survey_doc.to_dict()['owner'] != session['user']['uid']:
            flash('Encuesta no encontrada', 'error')
            return redirect(url_for('dashboard'))
        
        survey = survey_doc.to_dict()
        survey['id'] = survey_id
        
        if 'createdAt' in survey:
            if hasattr(survey['createdAt'], 'strftime'):
                survey['createdAt'] = survey['createdAt'].strftime('%d/%m/%Y a las %H:%M')
            else:
                survey['createdAt'] = "Fecha no disponible"
        
        return render_template('survey.html', survey=survey)
    except Exception as e:
        flash(f'Error al cargar encuesta: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

# Ruta para eliminar una encuesta
@app.route('/delete-survey/<survey_id>', methods=['POST'])
@login_required
def delete_survey(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        
        if not survey_doc.exists or survey_doc.to_dict()['owner'] != session['user']['uid']:
            flash('No tienes permiso para eliminar esta encuesta', 'error')
            return redirect(url_for('dashboard'))
        
        # Primero eliminamos las respuestas asociadas
        responses = db.collection('survey_responses')\
                     .where('survey_id', '==', survey_id)\
                     .stream()
        
        for response in responses:
            response.reference.delete()
        
        # Luego eliminamos la encuesta
        survey_ref.delete()
        
        flash('Encuesta eliminada exitosamente', 'success')
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f'Error al eliminar encuesta: {str(e)}', 'error')
        return redirect(url_for('view_survey', survey_id=survey_id))

# Ruta para enviar respuestas a una encuesta
@app.route('/submit-survey/<survey_id>', methods=['POST'])
@login_required
def submit_survey(survey_id):
    try:
        # Obtener las respuestas del formulario
        responses = request.form.to_dict()
        
        # Procesar las respuestas
        processed_responses = []
        for key, value in responses.items():
            if key.startswith('question_'):
                question_num = key.split('_')[1]
                processed_responses.append({
                    'question_number': question_num,
                    'response': value
                })
        
        # Verificar si el usuario ya respondió
        responses_ref = db.collection('survey_responses')
        existing_response = responses_ref.where('survey_id', '==', survey_id)\
                                       .where('user_id', '==', session['user']['uid'])\
                                       .limit(1)\
                                       .get()
        
        if existing_response:
            flash('Ya has respondido esta encuesta', 'warning')
            return redirect(url_for('dashboard'))

        # Guardar respuestas
        responses_ref.add({
            'survey_id': survey_id,
            'user_id': session['user']['uid'],
            'responses': processed_responses,
            'submitted_at': datetime.now()
        })

        # Actualización transaccional del contador de respuestas
        survey_ref = db.collection('surveys').document(survey_id)

        # Iniciar una transacción para actualizar el contador de respuestas
        transaction = db.transaction()
        def update_counter(transaction):
            snapshot = survey_ref.get(transaction=transaction)
            current_responses = snapshot.get('responses', 0)
            transaction.update(survey_ref, {'responses': current_responses + 1})

        # Ejecutar la transacción
        transaction.call(update_counter)

        flash('¡Respuestas enviadas correctamente!', 'success')
        return redirect(url_for('dashboard'))
    
    except Exception as e:
        flash(f'Error al enviar respuestas: {str(e)}', 'error')
        return redirect(url_for('view_survey', survey_id=survey_id))

# Ruta para cerrar sesión
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