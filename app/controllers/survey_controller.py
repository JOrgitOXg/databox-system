from flask import request, session, flash, redirect, url_for, render_template
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.cloud.firestore import Increment
from datetime import datetime
import re

# Obtener instancia de Firestore
db = firestore.client()

def get_dashboard_data():
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
        return redirect(url_for('auth.login'))

def handle_create_survey():
    if request.method != 'POST':
        return render_template('create_survey.html')
    
    title = request.form.get('title')
    description = request.form.get('description')
    questions = request.form.getlist('questions[]')
    question_types = request.form.getlist('question_types[]')
    question_options = request.form.getlist('question_options[]')
    is_public = request.form.get('is_public') == 'on'
    
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
        return redirect(url_for('survey.dashboard'))
    except Exception as e:
        flash(f'Error al crear encuesta: {str(e)}', 'error')
    
    return render_template('create_survey.html')

def handle_edit_survey(survey_id):
    try:
        # Verificar permisos y obtener encuesta
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        
        if not survey_doc.exists:
            flash('La encuesta no existe', 'error')
            return redirect(url_for('survey.dashboard'))
        
        survey_data = survey_doc.to_dict()
        if survey_data['owner'] != session['user']['uid']:
            flash('No tienes permiso para editar esta encuesta', 'error')
            return redirect(url_for('survey.dashboard'))
        
        # Preparar datos para el template
        survey = {
            'id': survey_id,
            'title': survey_data.get('title', ''),
            'description': survey_data.get('description', ''),
            'questions': survey_data.get('questions', []),
            'is_public': survey_data.get('is_public', False)
        }

        if request.method == 'POST':
            # Obtener datos del formulario
            form_data = {
                'title': request.form.get('title', '').strip(),
                'description': request.form.get('description', '').strip(),
                'is_public': request.form.get('is_public') == 'on',
                'questions': [],
                'question_types': request.form.getlist('question_types[]'),
                'question_options': request.form.getlist('question_options[]')
            }

            if len(form_data['title']) < 3:
                flash('El título debe tener al menos 3 caracteres', 'error')
                survey.update(form_data)
                return render_template('create_survey.html', survey=survey)

            # Procesar preguntas
            try:
                questions_text = request.form.getlist('questions[]')
                for i, (q_text, q_type) in enumerate(zip(questions_text, form_data['question_types'])):
                    q_text = q_text.strip()
                    if len(q_text) < 5:
                        flash(f'La pregunta {i+1} debe tener al menos 5 caracteres', 'error')
                        raise ValueError('Pregunta muy corta')
                    
                    question = {
                        'text': q_text,
                        'type': q_type
                    }
                    
                    if q_type == 'multiple':
                        options = [opt.strip() for opt in form_data['question_options'][i].split(',') if opt.strip()]
                        if len(options) < 2:
                            flash(f'La pregunta {i+1} (opción múltiple) debe tener al menos 2 opciones', 'error')
                            raise ValueError('Opciones insuficientes')
                        question['options'] = options
                    
                    form_data['questions'].append(question)
                
                if not form_data['questions']:
                    flash('Debe haber al menos una pregunta', 'error')
                    raise ValueError('Sin preguntas')
                
                # Actualizar en Firestore
                update_data = {
                    'title': form_data['title'],
                    'description': form_data['description'],
                    'questions': form_data['questions'],
                    'is_public': form_data['is_public'],
                    'updatedAt': datetime.now()
                }
                
                survey_ref.update(update_data)
                flash('Encuesta actualizada correctamente', 'success')
                return redirect(url_for('survey.view_survey', survey_id=survey_id))
                
            except Exception as e:
                survey.update({
                    'title': form_data['title'],
                    'description': form_data['description'],
                    'questions': form_data['questions'],
                    'is_public': form_data['is_public']
                })
                return render_template('create_survey.html', survey=survey)
        
        return render_template('create_survey.html', survey=survey)
        
    except Exception as e:
        flash(f'Error inesperado: {str(e)}', 'error')
        return redirect(url_for('survey.dashboard'))

def get_survey_data(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        
        if not survey_doc.exists:
            flash('La encuesta no existe', 'error')
            return redirect(url_for('survey.dashboard'))
        
        survey = survey_doc.to_dict()
        
        # Verificar permisos
        if survey['owner'] != session['user']['uid']:
            flash('No tienes permiso para ver esta encuesta', 'error')
            return redirect(url_for('survey.dashboard'))
        
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
            
            if 'submitted_at' in resp_data:
                if hasattr(resp_data['submitted_at'], 'strftime'):
                    resp_data['formatted_date'] = resp_data['submitted_at'].strftime('%d/%m/%Y %H:%M:%S')
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
        return redirect(url_for('survey.dashboard'))

def handle_public_survey(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        
        if not survey_doc.exists:
            flash('La encuesta no existe', 'error')
            return redirect(url_for('auth.login'))
        
        survey = survey_doc.to_dict()
        survey['id'] = survey_id
        
        # Verificar si es pública
        if not survey.get('is_public', False):
            flash('Esta encuesta no está disponible públicamente', 'error')
            return redirect(url_for('auth.login'))
        
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
                'responses': Increment(1),
                'updatedAt': datetime.now()
            })

            return render_template('thank_you.html')

        
        return render_template('public_survey.html', survey=survey)
    except Exception as e:
        flash(f'Error al cargar encuesta: {str(e)}', 'error')
        return redirect(url_for('auth.login'))

def handle_submit_survey(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey = survey_ref.get()
        
        if not survey.exists:
            flash('La encuesta no existe', 'error')
            return redirect(url_for('survey.dashboard'))

        # Verificar si ya respondió
        existing_response = db.collection('survey_responses').where(
            filter=FieldFilter('survey_id', '==', survey_id)
        ).where(
            filter=FieldFilter('user_id', '==', session['user']['uid'])
        ).limit(1).get()

        if len(existing_response) > 0:
            flash('Ya has respondido esta encuesta anteriormente', 'warning')
            return redirect(url_for('survey.view_survey', survey_id=survey_id))

        # Procesar respuestas
        responses = []
        for key, value in request.form.items():
            if key.startswith('question_'):
                question_num = int(key.split('_')[1])
                if not value:
                    flash('Por favor responde todas las preguntas', 'error')
                    return redirect(url_for('survey.view_survey', survey_id=survey_id))
                responses.append({
                    'question_number': question_num,
                    'response': value
                })

        # Validar todas las preguntas
        survey_data = survey.to_dict()
        if len(responses) != len(survey_data.get('questions', [])):
            flash('Por favor responde todas las preguntas', 'error')
            return redirect(url_for('survey.view_survey', survey_id=survey_id))

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
            'responses': Increment(1),
            'updatedAt': datetime.now()
        })

        flash('¡Tus respuestas han sido registradas!', 'success')
        return redirect(url_for('survey.view_survey', survey_id=survey_id))

    except Exception as e:
        flash(f'Error al procesar respuestas: {str(e)}', 'error')
        return redirect(url_for('survey.view_survey', survey_id=survey_id))

def handle_delete_survey(survey_id):
    try:
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        
        if not survey_doc.exists or survey_doc.to_dict()['owner'] != session['user']['uid']:
            flash('No tienes permiso para eliminar esta encuesta', 'error')
            return redirect(url_for('survey.dashboard'))
        
        # Eliminar respuestas asociadas
        responses = db.collection('survey_responses').where(
            filter=FieldFilter('survey_id', '==', survey_id)
        ).stream()
        
        batch = db.batch()
        deleted_count = 0
        
        for response in responses:
            batch.delete(response.reference)
            deleted_count += 1
            if deleted_count % 400 == 0:
                batch.commit()
                batch = db.batch()
        
        if deleted_count > 0:
            batch.commit()
        
        # Eliminar encuesta
        survey_ref.delete()
        
        flash(f'Encuesta eliminada correctamente (junto con {deleted_count} respuestas)', 'success')
        return redirect(url_for('survey.dashboard'))
    except Exception as e:
        flash(f'Error al eliminar encuesta: {str(e)}', 'error')
        return redirect(url_for('survey.view_survey', survey_id=survey_id))

def get_survey_stats(survey_id):
    try:
        # Obtener la encuesta con verificación de propiedad
        survey_ref = db.collection('surveys').document(survey_id)
        survey_doc = survey_ref.get()
        if not survey_doc.exists or survey_doc.to_dict().get('owner') != session['user']['uid']:
            flash('Acceso no autorizado', 'error')
            return redirect(url_for('survey.dashboard'))

        survey = survey_doc.to_dict()
        survey['id'] = survey_id

        
        # Obtener respuestas con manejo seguro de datos
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

        # Procesamiento estadístico
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

            # Preguntas abiertas
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

        # Validación final de datos
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
        return redirect(url_for('survey.view_survey', survey_id=survey_id))