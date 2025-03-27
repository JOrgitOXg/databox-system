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
            
            # Obtener número real de respuestas
            responses_count = len(list(db.collection('survey_responses')
                                  .where('survey_id', '==', survey.id)
                                  .stream()))
            
            # Usar el mayor entre el campo responses y el conteo real
            survey_data['responses'] = max(responses_count, survey_data.get('responses', 0))
            
            if 'createdAt' in survey_data:
                if hasattr(survey_data['createdAt'], 'strftime'):
                    survey_data['createdAt'] = survey_data['createdAt'].strftime('%d/%m/%Y')
                else:
                    survey_data['createdAt'] = "Fecha no disponible"
            
            surveys.append(survey_data)
        
        # Ordenar por fecha de creación (más reciente primero)
        surveys.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
        
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
        
        # Validaciones
        if not title or len(title.strip()) < 3:
            flash('El título debe tener al menos 3 caracteres', 'error')
            return render_template('create_survey.html')
            
        # Procesar las preguntas
        processed_questions = []
        for i, (q_text, q_type) in enumerate(zip(questions, question_types)):
            if not q_text or len(q_text.strip()) < 5:
                flash('Cada pregunta debe tener al menos 5 caracteres', 'error')
                return render_template('create_survey.html')
                
            question_data = {
                'text': q_text.strip(),
                'type': q_type
            }
            
            if q_type == 'multiple':
                options = [opt.strip() for opt in question_options[i].split(',') if opt.strip()]
                if len(options) < 2:
                    flash('Las preguntas de opción múltiple deben tener al menos 2 opciones', 'error')
                    return render_template('create_survey.html')
                question_data['options'] = options
            
            processed_questions.append(question_data)
        
        if not processed_questions:
            flash('Debes agregar al menos una pregunta', 'error')
            return render_template('create_survey.html')
        
        try:
            # Crear encuesta con contador inicializado a 0
            survey_data = {
                'title': title.strip(),
                'description': description.strip() if description else '',
                'questions': processed_questions,
                'owner': session['user']['uid'],
                'createdAt': datetime.now(),
                'responses': 0,
                'updatedAt': datetime.now()
            }
            
            db.collection('surveys').add(survey_data)
            flash('Encuesta creada exitosamente', 'success')
            return redirect(url_for('dashboard'))
        except Exception as e:
            flash(f'Error al crear encuesta: {str(e)}', 'error')
    
    return render_template('create_survey.html')

# Ruta para editar encuestas
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
            
            # Validaciones
            if not title or len(title.strip()) < 3:
                flash('El título debe tener al menos 3 caracteres', 'error')
                return render_template('create_survey.html', survey=survey)
                
            # Procesar las preguntas
            processed_questions = []
            for i, (q_text, q_type) in enumerate(zip(questions, question_types)):
                if not q_text or len(q_text.strip()) < 5:
                    flash('Cada pregunta debe tener al menos 5 caracteres', 'error')
                    return render_template('create_survey.html', survey=survey)
                    
                question_data = {
                    'text': q_text.strip(),
                    'type': q_type
                }
                
                if q_type == 'multiple':
                    options = [opt.strip() for opt in question_options[i].split(',') if opt.strip()]
                    if len(options) < 2:
                        flash('Las preguntas de opción múltiple deben tener al menos 2 opciones', 'error')
                        return render_template('create_survey.html', survey=survey)
                    question_data['options'] = options
                
                processed_questions.append(question_data)
            
            if not processed_questions:
                flash('Debes agregar al menos una pregunta', 'error')
                return render_template('create_survey.html', survey=survey)
            
            try:
                survey_ref.update({
                    'title': title.strip(),
                    'description': description.strip() if description else '',
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

# Ruta para ver encuesta
@app.route('/survey/<survey_id>')
@login_required
def view_survey(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        
        if not survey_doc.exists:
            flash('La encuesta no existe', 'error')
            return redirect(url_for('dashboard'))
        
        survey = survey_doc.to_dict()
        
        # Verificar si el usuario es el dueño o si es pública
        if survey['owner'] != session['user']['uid']:
            flash('No tienes permiso para ver esta encuesta', 'error')
            return redirect(url_for('dashboard'))
        
        survey['id'] = survey_id
        
        # Formatear fecha
        if 'createdAt' in survey:
            if hasattr(survey['createdAt'], 'strftime'):
                survey['createdAt'] = survey['createdAt'].strftime('%d/%m/%Y a las %H:%M')
            else:
                survey['createdAt'] = "Fecha no disponible"
        
        # Obtener estadísticas de respuestas
        responses_ref = db.collection('survey_responses').where('survey_id', '==', survey_id).stream()
        response_count = len(list(responses_ref))
        
        return render_template('survey.html', 
                            survey=survey,
                            response_count=response_count)
    except Exception as e:
        flash(f'Error al cargar encuesta: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

# Ruta para enviar respuestas
@app.route('/submit-survey/<survey_id>', methods=['POST'])
@login_required
def submit_survey(survey_id):
    try:
        # Verificar si la encuesta existe
        survey_ref = db.collection('surveys').document(survey_id)
        survey = survey_ref.get()
        if not survey.exists:
            flash('La encuesta no existe', 'error')
            return redirect(url_for('dashboard'))

        # Verificar si el usuario ya respondió
        existing_response = db.collection('survey_responses') \
                            .where('survey_id', '==', survey_id) \
                            .where('user_id', '==', session['user']['uid']) \
                            .limit(1) \
                            .get()

        if len(existing_response) > 0:
            flash('Ya has respondido esta encuesta anteriormente', 'warning')
            return redirect(url_for('dashboard'))

        # Procesar respuestas
        responses = []
        for key, value in request.form.items():
            if key.startswith('question_'):
                question_num = key.split('_')[1]
                responses.append({
                    'question_number': int(question_num),
                    'response': value
                })

        # Guardar respuestas
        response_data = {
            'survey_id': survey_id,
            'user_id': session['user']['uid'],
            'responses': responses,
            'submitted_at': datetime.now(),
            'user_name': session['user'].get('name', 'Anónimo')
        }

        db.collection('survey_responses').add(response_data)

        # Actualizar contador de respuestas (transacción atómica)
        def update_counter(transaction):
            survey_snap = survey_ref.get(transaction=transaction)
            current_count = survey_snap.get('responses', 0)
            transaction.update(survey_ref, {
                'responses': current_count + 1,
                'updatedAt': datetime.now()
            })

        db.run_transaction(update_counter)

        flash('¡Tus respuestas han sido registradas!', 'success')
        return redirect(url_for('dashboard'))

    except Exception as e:
        flash(f'Error al procesar respuestas: {str(e)}', 'error')
        return redirect(url_for('view_survey', survey_id=survey_id))

# Ruta para eliminar encuesta
@app.route('/delete-survey/<survey_id>', methods=['POST'])
@login_required
def delete_survey(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        
        if not survey_doc.exists or survey_doc.to_dict()['owner'] != session['user']['uid']:
            flash('No tienes permiso para eliminar esta encuesta', 'error')
            return redirect(url_for('dashboard'))
        
        # Eliminar respuestas asociadas
        responses = db.collection('survey_responses') \
                     .where('survey_id', '==', survey_id) \
                     .stream()
        
        batch = db.batch()
        deleted_count = 0
        
        for response in responses:
            batch.delete(response.reference)
            deleted_count += 1
            if deleted_count % 400 == 0:  # Límite de operaciones por batch
                batch.commit()
                batch = db.batch()
        
        if deleted_count > 0:
            batch.commit()
        
        # Eliminar la encuesta
        survey_ref.delete()
        
        flash(f'Encuesta eliminada correctamente (junto con {deleted_count} respuestas)', 'success')
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f'Error al eliminar encuesta: {str(e)}', 'error')
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