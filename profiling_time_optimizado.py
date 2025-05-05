import cProfile
import pstats
import io
from app import create_app
from app.config import Config
from firebase_admin import firestore
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, auth
from collections import defaultdict

app = create_app()
db = firestore.client()

if not firebase_admin._apps:
    cred = credentials.Certificate("serviceAccountKey.json")
    firebase_admin.initialize_app(cred)

def profile_login():
    email = "jorge.pimentel630@gmail.com"
    password = "jorge664."
    
    try:
        user = auth.get_user_by_email(email)
        user_ref = db.collection('users').where('email', '==', email).limit(1).get()
        
        if user_ref:
            user_data = user_ref[0].to_dict()
            full_name = user_data.get('fullName', user.email.split('@')[0])
        else:
            full_name = user.email.split('@')[0]
            db.collection('users').document(user.uid).set({
                'uid': user.uid,
                'email': user.email,
                'fullName': full_name,
                'createdAt': datetime.now()
            })
        
        db.collection('users').document(user.uid).update({
            'lastLogin': datetime.now()
        })
        
        return True
    except Exception as e:
        print(f"Error en login: {str(e)}")
        return False

def profile_create_survey():
    try:
        survey_data = {
            'title': "Encuesta de perfilado",
            'description': "Encuesta para pruebas de rendimiento",
            'questions': [
                {'text': "¿Cómo calificarías nuestro servicio?", 'type': "rating"},
                {'text': "¿Qué características te gustaría ver?", 'type': "open"},
                {'text': "¿Recomendarías este servicio?", 'type': "multiple"}
            ],
            'owner': "test_user_id",
            'createdAt': datetime.now(),
            'responses': 0,
            'updatedAt': datetime.now(),
            'is_public': True
        }
        
        doc_ref = db.collection('surveys').add(survey_data)
        print(f"Encuesta creada con ID: {doc_ref[1].id}")
        return True
    except Exception as e:
        print(f"Error creando encuesta: {str(e)}")
        return False

def profile_process_responses():
    try:
        survey_id = "PAmkaY9eZohrXajCslKy"
        now = datetime.now()

        batch = db.batch()
        for i in range(1, 101):
            response_data = {
                'survey_id': survey_id,
                'user_info': {
                    'name': f"Usuario {i}",
                    'age': 20 + (i % 40),
                    'city': "Ciudad Ejemplo"
                },
                'responses': [
                    {'question_number': 1, 'response': f"Respuesta abierta {i}"},
                    {'question_number': 2, 'response': "si" if i % 3 == 0 else "no"},
                    {'question_number': 3, 'response': str((i % 5) + 1)}
                ],
                'submitted_at': now,
                'is_anonymous': True
            }
            new_ref = db.collection('survey_responses').document()
            batch.set(new_ref, response_data)

        batch.commit()

        db.collection('surveys').document(survey_id).update({
            'responses': firestore.firestore.SERVER_TIMESTAMP,
            'updatedAt': now
        })

        return True
    except Exception as e:
        print(f"Error procesando respuestas: {str(e)}")
        return False


def profile_generate_stats():
    try:
        survey_id = "PAmkaY9eZohrXajCslKy"
        survey_doc = db.collection('surveys').document(survey_id).get()
        if not survey_doc.exists:
            print("La encuesta no existe.")
            return False

        survey = survey_doc.to_dict()
        questions = survey.get('questions', [])
        num_questions = len(questions)

        question_stats = [{'responses': [], 'counts': defaultdict(int), 'ratings': []} for _ in questions]

        responses_stream = db.collection('survey_responses').where('survey_id', '==', survey_id).stream()
        for resp in responses_stream:
            resp_data = resp.to_dict()
            for answer in resp_data.get('responses', []):
                qn = int(answer.get('question_number', 0)) - 1
                if not (0 <= qn < num_questions):
                    continue

                response = str(answer.get('response', ''))
                q_type = questions[qn].get('type')

                if q_type == 'open':
                    question_stats[qn]['responses'].append(response)
                elif q_type == 'multiple':
                    question_stats[qn]['counts'][response] += 1
                elif q_type == 'rating':
                    try:
                        rating = int(response)
                        if 1 <= rating <= 5:
                            question_stats[qn]['ratings'].append(rating)
                    except ValueError:
                        continue

        stats = {'questions': []}
        for i, q in enumerate(questions):
            q_type = q.get('type')
            result = {
                'text': q.get('text'),
                'type': q_type
            }

            if q_type == 'open':
                result['responses'] = question_stats[i]['responses']
            elif q_type == 'multiple':
                result['counts'] = dict(question_stats[i]['counts'])
            elif q_type == 'rating':
                ratings = question_stats[i]['ratings']
                if ratings:
                    avg = sum(ratings) / len(ratings)
                    dist = {str(n): ratings.count(n) for n in range(1, 6)}
                    result.update({
                        'average': avg,
                        'count': len(ratings),
                        'distribution': dist
                    })
                else:
                    result.update({
                        'average': 0,
                        'count': 0,
                        'distribution': {}
                    })

            stats['questions'].append(result)

        print("Estadísticas generadas correctamente")
        return stats

    except Exception as e:
        print(f"Error generando estadísticas: {str(e)}")
        return False

def run_all_operations():
    """Función que ejecuta todas las operaciones a perfilar"""
    print("Ejecutando todas las operaciones...")
    profile_login()
    profile_create_survey()
    profile_process_responses()
    profile_generate_stats()
    print("Todas las operaciones completadas")

if __name__ == '__main__':
    # Iniciar perfilado de todas las funciones
    profiler = cProfile.Profile()
    profiler.enable()
    
    run_all_operations()
    
    profiler.disable()
    
    # Resultados en un archivo
    output_file = "full_profile_optimizado.prof"
    profiler.dump_stats(output_file)
    print(f"\nPerfilado completo guardado en: {output_file}")
    
    # Mostrar resumen en consola
    print("\nResumen estadístico:")
    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream).sort_stats('cumulative')
    stats.print_stats()
    print(stream.getvalue())
    
    print("\nPara visualización avanzada ejecuta:")
    print(f"snakeviz {output_file}")