import re
from flask import Flask, render_template, redirect, url_for, request, flash, session
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, auth, firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore import Increment  # Importación añadida
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
            # Verificar si el email ya existe
            existing_users = auth.get_user_by_email(email)
            flash('Este email ya está registrado', 'error')
            return redirect(url_for('register'))
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
                return redirect(url_for('dashboard'))
            except Exception as e:
                flash(f'Error en el registro: {str(e)}', 'error')
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
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
        # Actualizar datos del usuario en sesión
        user_ref = db.collection('users').document(session['user']['uid']).get()
        if user_ref.exists:
            user_data = user_ref.to_dict()
            session['user']['name'] = user_data.get('fullName', session['user']['email'].split('@')[0])
        
        surveys_ref = db.collection('surveys').where(
            filter=FieldFilter('owner', '==', session['user']['uid'])
        ).stream()
        
        surveys = []
        for survey in surveys_ref:
            survey_data = survey.to_dict()
            survey_data['id'] = survey.id
            
            # Obtener conteo de respuestas
            responses_ref = db.collection('survey_responses').where(
                filter=FieldFilter('survey_id', '==', survey.id)
            ).stream()
            response_count = len(list(responses_ref))
            
            survey_data['responses'] = response_count
            
            # Formateo de fecha
            if 'createdAt' in survey_data:
                if hasattr(survey_data['createdAt'], 'strftime'):
                    survey_data['createdAt'] = survey_data['createdAt'].strftime('%d/%m/%Y')
                else:
                    survey_data['createdAt'] = "Fecha no disponible"
            
            surveys.append(survey_data)
        
        # Ordenar por fecha de creación
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
        is_public = request.form.get('is_public') == 'on'
        
        # Validaciones
        if not title or len(title.strip()) < 3:
            flash('El título debe tener al menos 3 caracteres', 'error')
            return render_template('create_survey.html')
            
        # Procesar preguntas
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
            # Crear encuesta
            survey_data = {
                'title': title.strip(),
                'description': description.strip() if description else '',
                'questions': processed_questions,
                'owner': session['user']['uid'],
                'createdAt': datetime.now(),
                'responses': 0,
                'updatedAt': datetime.now(),
                'is_public': is_public
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
            is_public = request.form.get('is_public') == 'on'
            
            # Validaciones
            if not title or len(title.strip()) < 3:
                flash('El título debe tener al menos 3 caracteres', 'error')
                return render_template('create_survey.html', survey=survey)
                
            # Procesar preguntas
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
                    'updatedAt': datetime.now(),
                    'is_public': is_public
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
        
        # Verificar permisos
        if survey['owner'] != session['user']['uid']:
            flash('No tienes permiso para ver esta encuesta', 'error')
            return redirect(url_for('dashboard'))
        
        survey['id'] = survey_id
        
        # Obtener el conteo de respuestas
        responses_ref = db.collection('survey_responses').where(
            filter=FieldFilter('survey_id', '==', survey_id)
        ).stream()
        
        response_count = len(list(responses_ref))
        
        # Obtener las respuestas para mostrar
        responses_ref = db.collection('survey_responses').where(
            filter=FieldFilter('survey_id', '==', survey_id)
        ).stream()
        
        responses = []
        for resp in responses_ref:
            resp_data = resp.to_dict()
            if resp_data.get('is_anonymous'):
                resp_data['user_name'] = resp_data.get('user_info', {}).get('name', 'Anónimo')
            else:
                resp_data['user_name'] = resp_data.get('user_name', 'Usuario registrado')
            
            # Formatear fecha de respuesta
            if 'submitted_at' in resp_data:
                if hasattr(resp_data['submitted_at'], 'strftime'):
                    resp_data['formatted_date'] = resp_data['submitted_at'].strftime('%d/%m/%Y %H:%M')
                else:
                    resp_data['formatted_date'] = str(resp_data['submitted_at'])
            else:
                resp_data['formatted_date'] = "Fecha no disponible"
            
            responses.append(resp_data)
        
        return render_template('survey.html', 
                            survey=survey,
                            responses=responses,
                            response_count=response_count)
    except Exception as e:
        flash(f'Error al cargar encuesta: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

# Ruta para encuesta pública
@app.route('/public-survey/<survey_id>', methods=['GET', 'POST'])
def public_survey(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        
        if not survey_doc.exists:
            flash('La encuesta no existe', 'error')
            return redirect(url_for('home'))
        
        survey = survey_doc.to_dict()
        survey['id'] = survey_id
        
        # Verificar si es pública
        if not survey.get('is_public', False):
            flash('Esta encuesta no está disponible públicamente', 'error')
            return redirect(url_for('home'))
        
        if request.method == 'POST':
            # Procesar datos del usuario
            user_name = request.form.get('user_name')
            user_age = request.form.get('user_age')
            user_city = request.form.get('user_city')
            
            if not user_name or not user_age or not user_city:
                flash('Por favor completa todos tus datos personales', 'error')
                return render_template('public_survey.html', survey=survey)
            
            # Procesar respuestas
            responses = []
            for key, value in request.form.items():
                if key.startswith('question_'):
                    question_num = int(key.split('_')[1])
                    if not value:
                        flash('Por favor responde todas las preguntas', 'error')
                        return render_template('public_survey.html', survey=survey)
                    responses.append({
                        'question_number': question_num,
                        'response': value
                    })
            
            # Validar todas las preguntas respondidas
            if len(responses) != len(survey.get('questions', [])):
                flash('Por favor responde todas las preguntas', 'error')
                return render_template('public_survey.html', survey=survey)
            
            # Guardar respuesta
            response_data = {
                'survey_id': survey_id,
                'user_info': {
                    'name': user_name,
                    'age': user_age,
                    'city': user_city
                },
                'responses': responses,
                'submitted_at': datetime.now(),
                'is_anonymous': True
            }

            db.collection('survey_responses').add(response_data)

            # Actualizar contador con incremento atómico
            survey_ref.update({
                'responses': Increment(1),  # Sin el prefijo firestore.
                'updatedAt': datetime.now()
            })

            flash('¡Gracias por responder nuestra encuesta!', 'success')
            return redirect(url_for('home'))
        
        return render_template('public_survey.html', survey=survey)
    except Exception as e:
        flash(f'Error al cargar encuesta: {str(e)}', 'error')
        return redirect(url_for('home'))

# Ruta para enviar respuestas (usuarios registrados)
@app.route('/submit-survey/<survey_id>', methods=['POST'])
@login_required
def submit_survey(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey = survey_ref.get()
        
        if not survey.exists:
            flash('La encuesta no existe', 'error')
            return redirect(url_for('dashboard'))

        # Verificar si ya respondió
        existing_response = db.collection('survey_responses').where(
            filter=FieldFilter('survey_id', '==', survey_id)
        ).where(
            filter=FieldFilter('user_id', '==', session['user']['uid'])
        ).limit(1).get()

        if len(existing_response) > 0:
            flash('Ya has respondido esta encuesta anteriormente', 'warning')
            return redirect(url_for('dashboard'))

        # Procesar respuestas
        responses = []
        for key, value in request.form.items():
            if key.startswith('question_'):
                question_num = int(key.split('_')[1])
                if not value:
                    flash('Por favor responde todas las preguntas', 'error')
                    return redirect(url_for('view_survey', survey_id=survey_id))
                responses.append({
                    'question_number': question_num,
                    'response': value
                })

        # Validar todas las preguntas
        survey_data = survey.to_dict()
        if len(responses) != len(survey_data.get('questions', [])):
            flash('Por favor responde todas las preguntas', 'error')
            return redirect(url_for('view_survey', survey_id=survey_id))

        # Guardar respuesta
        response_data = {
            'survey_id': survey_id,
            'user_id': session['user']['uid'],
            'responses': responses,
            'submitted_at': datetime.now(),
            'user_name': session['user'].get('name', 'Usuario registrado')
        }

        db.collection('survey_responses').add(response_data)

        # Actualizar contador con incremento atómico
        survey_ref.update({
            'responses': Increment(1),  # Sin el prefijo firestore.
            'updatedAt': datetime.now()
        })

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
        responses = db.collection('survey_responses').where(
            filter=FieldFilter('survey_id', '==', survey_id)
        ).stream()
        
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
        
        # Eliminar encuesta
        survey_ref.delete()
        
        flash(f'Encuesta eliminada correctamente (junto con {deleted_count} respuestas)', 'success')
        return redirect(url_for('dashboard'))
    except Exception as e:
        flash(f'Error al eliminar encuesta: {str(e)}', 'error')
        return redirect(url_for('view_survey', survey_id=survey_id))

# Ruta para estadisticas de la encuesta
@app.route('/survey-stats/<survey_id>')
@login_required
def survey_stats(survey_id):
    try:
        # 1. Obtener la encuesta con verificación de propiedad
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        if not survey_doc.exists or survey_doc.to_dict().get('owner') != session['user']['uid']:
            flash('Acceso no autorizado', 'error')
            return redirect(url_for('dashboard'))

        survey = survey_doc.to_dict()
        survey['id'] = survey_id  # ← Esto es crítico para que funcione survey.id en la plantilla

        
        # 2. Obtener respuestas con manejo seguro de datos
        responses = []
        for resp in db.collection('survey_responses').where('survey_id', '==', survey_id).stream():
            resp_data = resp.to_dict()
            # Limpieza de datos
            clean_responses = []
            for answer in resp_data.get('responses', []):
                clean_answer = {
                    'question_number': int(answer.get('question_number', 0)),
                    'response': str(answer.get('response', ''))
                }
                clean_responses.append(clean_answer)
            
            resp_data['responses'] = clean_responses
            responses.append(resp_data)

        if not responses:
            flash('No hay respuestas suficientes', 'warning')
            return redirect(url_for('view_survey', survey_id=survey_id))

        # 3. Procesamiento estadístico seguro
        stats = {'questions': []}
        
        for i, question in enumerate(survey.get('questions', [])):
            q_data = {
                'text': str(question.get('text', '')),
                'type': str(question.get('type', '')),
                'stats': None
            }

            # Preguntas de opción múltiple
            if question['type'] == 'multiple':
                options = [str(opt) for opt in question.get('options', [])]
                counts = {opt: 0 for opt in options}
                
                for resp in responses:
                    for ans in resp['responses']:
                        if ans['question_number'] == i+1 and ans['response'] in counts:
                            counts[ans['response']] += 1
                
                q_data['stats'] = {
                    'type': 'bar',
                    'labels': list(counts.keys()),
                    'data': list(counts.values())
                }

            # Preguntas de rating
            elif question['type'] == 'rating':
                ratings = [0] * 5
                for resp in responses:
                    for ans in resp['responses']:
                        if ans['question_number'] == i+1:
                            try:
                                rating = int(float(ans['response']))
                                if 1 <= rating <= 5:
                                    ratings[rating-1] += 1
                            except (ValueError, TypeError):
                                continue
                
                q_data['stats'] = {
                    'type': 'bar',
                    'labels': ['1', '2', '3', '4', '5'],
                    'data': ratings
                }

            # Preguntas abiertas (versión simplificada)
            elif question['type'] == 'open':
                word_counts = {}
                for resp in responses:
                    for ans in resp['responses']:
                        if ans['question_number'] == i+1:
                            words = re.findall(r'\b\w{4,}\b', ans['response'].lower())  # Palabras de 4+ letras
                            for word in words:
                                word_counts[word] = word_counts.get(word, 0) + 1
                
                if word_counts:
                    top_words = sorted(word_counts.items(), key=lambda x: x[1], reverse=True)[:7]
                    q_data['stats'] = {
                        'type': 'pie',
                        'labels': [w[0] for w in top_words],
                        'data': [w[1] for w in top_words]
                    }

            stats['questions'].append(q_data)

        # 4. Validación final de datos
        import json
        try:
            json.dumps(stats)  # Prueba de serialización
        except TypeError as e:
            print(f"Datos no serializables: {e}")
            raise

        return render_template('survey_stats.html',
                            survey=survey,
                            stats=stats,
                            response_count=len(responses))

    except Exception as e:
        print(f"Error en survey_stats: {str(e)}")
        flash('Error al procesar estadísticas', 'error')
        return redirect(url_for('view_survey', survey_id=survey_id))

# Ruta para cerrar sesión
@app.route('/logout')
def logout():
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
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)