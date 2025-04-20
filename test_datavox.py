import pytest
from run import app, db
from datetime import datetime, timezone
from firebase_admin import auth, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

# Configuración de pytest
@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        with app.app_context():
            yield client

# Datos de prueba
TEST_USER = {
    'email': 'testuser@example.com',
    'password': 'TestPass123',
    'fullName': 'Test User'
}

TEST_SURVEY = {
    'title': 'Test Survey',
    'description': 'This is a test survey',
    'questions': [
        {'text': 'Question 1', 'type': 'open'},
        {'text': 'Question 2', 'type': 'multiple', 'options': ['Option A', 'Option B']},
        {'text': 'Question 3', 'type': 'rating'}
    ],
    'is_public': True
}

# Funciones de alerta
from firebase_admin._auth_utils import EmailAlreadyExistsError

def create_test_user(email=None, name=None):
    data = TEST_USER.copy()
    if email:
        data['email'] = email
    if name:
        data['fullName'] = name

    try:
        user = auth.create_user(
            email=data['email'],
            password=data['password'],
            display_name=data['fullName']
        )
    except EmailAlreadyExistsError:
        # Si ya existe, lo buscamos
        user = auth.get_user_by_email(data['email'])

    # Asegurarnos de que en Firestore haya un documento
    db.collection('users').document(user.uid).set({
        'uid': user.uid,
        'email': data['email'],
        'fullName': data['fullName'],
        'createdAt': datetime.now(timezone.utc)
    }, merge=True)

    return user

def delete_test_user(user):
    """Elimina un usuario de prueba"""
    try:
        if user:
            auth.delete_user(user.uid)
            db.collection('users').document(user.uid).delete()
    except Exception as e:
        print(f"Warning: Error deleting test user: {str(e)}")

def create_test_survey(user_id):
    """Crea una encuesta de prueba"""
    try:
        survey_data = TEST_SURVEY.copy()
        survey_data['owner'] = user_id
        survey_data['createdAt'] = datetime.now(timezone.utc)
        survey_ref = db.collection('surveys').add(survey_data)
        return survey_ref[1].id
    except Exception as e:
        pytest.fail(f"Error creating test survey: {str(e)}")

def delete_test_survey(survey_id):
    """Elimina una encuesta de prueba"""
    try:
        if survey_id:
            db.collection('surveys').document(survey_id).delete()
    except Exception as e:
        print(f"Warning: Error deleting test survey: {str(e)}")

# PRUEBAS FALLIDAS PARA HACER LA PRUEBA

def test_registro_fallido_email_invalido(client):
    """PRUEBA QUE FALLARÁ: Registro con email inválido"""
    response = client.post('/auth/register', data={
        'fullName': 'Usuario Test',
        'email': 'email-invalido',  # Email mal formado
        'password': 'TestPass123'
    }, follow_redirects=True)
    
    # Esta fallará porque el sistema debería rechazar el email inválido
    assert b'Registro exitoso' in response.data  # Falla porque el registro no debería pasar

def test_creacion_encuesta_fallida_sin_preguntas(client):
    """PRUEBA QUE FALLARÁ: Creación de encuesta sin preguntas"""
    user = create_test_user()
    with client.session_transaction() as sess:
        sess['user'] = {
            'uid': user.uid,
            'email': user.email,
            'name': user.display_name
        }
    
    response = client.post('/survey/create', data={
        'title': 'Encuesta inválida',
        'description': 'Esta encuesta no tiene preguntas',
        'questions[]': [],  # No hay preguntas
        'question_types[]': [],
        'question_options[]': []
    }, follow_redirects=True)
    
    # Fallará porque que el sistema rechace encuestas sin preguntas
    assert b'Encuesta creada exitosamente' in response.data

def test_reset_password_fallido_contraseña_corta(client):
    """PRUEBA QUE FALLARÁ: Restablecimiento con contraseña muy corta"""
    response = client.post('/auth/reset-password', data={
        'oobCode': 'codigo-test',
        'new_password': '123',  # Contraseña muy corta
        'confirm_password': '123'
    }, follow_redirects=True)
    
    # Fallará el sistema debería rechazar contraseñas demasiado cortas
    assert b'Contrase\xc3\xb1a restablecida' in response.data

# PRUEBAS QUE SI PASASN

def test_user_registration(client):
    """Prueba el registro de un nuevo usuario"""
    # Eliminar usuario de prueba si existe
    try:
        user = auth.get_user_by_email(TEST_USER['email'])
        delete_test_user(user)
    except auth.UserNotFoundError:
        pass
    
    response = client.post('/auth/register', data={
        'fullName': TEST_USER['fullName'],
        'email': TEST_USER['email'],
        'password': TEST_USER['password']
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Registro exitoso' in response.data
    
    # Verificar que el usuario existe en Firebase Auth
    user = auth.get_user_by_email(TEST_USER['email'])
    assert user.email == TEST_USER['email']
    
    # Verificar que los datos están en Firestore
    user_ref = db.collection('users').where(
        filter=FieldFilter('email', '==', TEST_USER['email'])
    ).limit(1).get()
    
    assert len(user_ref) == 1
    assert user_ref[0].to_dict()['fullName'] == TEST_USER['fullName']
    
    # Limpieza
    delete_test_user(user)

def test_user_login(client):
    """Prueba el inicio de sesión de un usuario"""
    # Crear usuario de prueba
    user = create_test_user()
    
    response = client.post('/auth/login', data={
        'email': TEST_USER['email'],
        'password': TEST_USER['password']
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Inicio de sesi\xc3\xb3n exitoso' in response.data
    
    # Limpieza
    delete_test_user(user)

def test_invalid_login(client):
    """Prueba el inicio de sesión con credenciales inválidas"""
    response = client.post('/auth/login', data={
        'email': 'nonexistent@example.com',
        'password': 'wrongpassword'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Contrase\xc3\xb1a incorrecta' in response.data or b'Error al iniciar sesi\xc3\xb3n' in response.data

def test_create_survey_authenticated(client):
    """Prueba la creación de una encuesta por un usuario autenticado"""
    # Crear usuario y hacer login
    user = create_test_user()
    with client.session_transaction() as sess:
        sess['user'] = {
            'uid': user.uid,
            'email': user.email,
            'name': user.display_name
        }
    
    response = client.post('/survey/create', data={
        'title': 'Test Survey',
        'description': 'Test Description',
        'questions[]': ['Question 1', 'Question 2'],
        'question_types[]': ['open', 'multiple'],
        'question_options[]': ['', 'Option 1, Option 2'],
        'is_public': 'on'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Encuesta creada exitosamente' in response.data
    
    # Verificar que la encuesta se creó en Firestore
    survey_ref = db.collection('surveys').where(
        filter=FieldFilter('owner', '==', user.uid)
    ).limit(1).get()
    
    assert len(survey_ref) == 1
    survey_data = survey_ref[0].to_dict()
    assert survey_data['title'] == 'Test Survey'
    
    # Limpieza
    delete_test_survey(survey_ref[0].id)
    delete_test_user(user)

def test_public_survey_access(client):
    """Prueba el acceso a una encuesta pública"""
    # Crear usuario y encuesta pública
    user = create_test_user()
    survey_id = create_test_survey(user.uid)
    
    # Hacer la encuesta pública
    db.collection('surveys').document(survey_id).update({'is_public': True})
    
    response = client.get(f'/survey/public/{survey_id}')
    assert response.status_code == 200
    assert b'Test Survey' in response.data
    
    # Limpieza
    delete_test_survey(survey_id)
    delete_test_user(user)

def test_survey_submission(client):
    """Prueba el envío de respuestas a una encuesta"""
    # Crear usuario y encuesta
    user = create_test_user()
    survey_id = create_test_survey(user.uid)
    
    # Enviar respuestas
    response = client.post(f'/survey/public/{survey_id}', data={
        'user_name': 'Test Respondent',
        'user_age': '25',
        'user_city': 'Test City',
        'question_1': 'Open response',
        'question_2': 'Option A',
        'question_3': '4'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Gracias por participar' in response.data
    
    # Verificar que las respuestas se guardaron
    responses_ref = db.collection('survey_responses').where(
        filter=FieldFilter('survey_id', '==', survey_id)
    ).get()
    
    assert len(responses_ref) == 1
    assert responses_ref[0].to_dict()['user_info']['name'] == 'Test Respondent'
    
    # Limpieza
    for resp in responses_ref:
        resp.reference.delete()
    delete_test_survey(survey_id)
    delete_test_user(user)

def test_survey_validation(client):
    """Prueba la validación al crear una encuesta"""
    user = create_test_user()
    with client.session_transaction() as sess:
        sess['user'] = {
            'uid': user.uid,
            'email': user.email,
            'name': user.display_name
        }
    
    # Intentar crear encuesta sin título
    response = client.post('/survey/create', data={
        'title': '',
        'description': 'Test Description',
        'questions[]': ['Question 1'],
        'question_types[]': ['open'],
        'question_options[]': ['']
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'El t\xc3\xadtulo debe tener al menos 3 caracteres' in response.data
    
    # Limpieza
    delete_test_user(user)

def test_password_reset_validation(client):
    """Prueba la validación al restablecer contraseña"""
    # Simular token OOB (out-of-band)
    test_oob_code = "testOobCode"
    
    # Contraseñas no coinciden
    response = client.post('/auth/reset-password', data={
        'oobCode': test_oob_code,
        'new_password': 'newpass123',
        'confirm_password': 'differentpass'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'Las contrase\xc3\xb1as no coinciden' in response.data
    
    # Contraseña muy corta
    response = client.post('/auth/reset-password', data={
        'oobCode': test_oob_code,
        'new_password': '123',
        'confirm_password': '123'
    }, follow_redirects=True)
    
    assert response.status_code == 200
    assert b'La contrase\xc3\xb1a debe tener al menos 6 caracteres' in response.data

def test_survey_stats_calculation(client):
    """Prueba el cálculo de estadísticas de encuestas"""
    user = create_test_user()
    survey_id = create_test_survey(user.uid)
    
    # Agregar respuestas de prueba
    responses = [
        {
            'survey_id': survey_id,
            'user_id': user.uid,
            'responses': [
                {'question_number': 1, 'response': 'Respuesta abierta 1'},
                {'question_number': 2, 'response': 'Option A'},
                {'question_number': 3, 'response': '4'}
            ],
            'submitted_at': datetime.now(timezone.utc)
        },
        {
            'survey_id': survey_id,
            'user_id': user.uid,
            'responses': [
                {'question_number': 1, 'response': 'Otra respuesta'},
                {'question_number': 2, 'response': 'Option B'},
                {'question_number': 3, 'response': '5'}
            ],
            'submitted_at': datetime.now(timezone.utc)
        }
    ]
    
    for resp in responses:
        db.collection('survey_responses').add(resp)
    
    with client.session_transaction() as sess:
        sess['user'] = {
            'uid': user.uid,
            'email': user.email,
            'name': user.display_name
        }
    
    response = client.get(f'/survey/stats/{survey_id}')
    assert response.status_code == 200
    
    # Verificar que se muestran los datos correctamente
    assert b'Estad\xc3\xadsticas' in response.data
    assert b'Option A' in response.data or b'Option B' in response.data
    
    # Limpieza
    responses_ref = db.collection('survey_responses').where(
        filter=FieldFilter('survey_id', '==', survey_id)
    ).get()
    
    for resp in responses_ref:
        resp.reference.delete()
    delete_test_survey(survey_id)
    delete_test_user(user)

def test_unauthorized_survey_access(client):
    """Prueba el acceso no autorizado a una encuesta"""
    # Crear usuario 1 y encuesta
    user1 = create_test_user()
    survey_id = create_test_survey(user1.uid)
    
    # Crear usuario 2 con email y nombre diferente
    user2 = create_test_user(email='user2@example.com', name='User 2')
    
    # Intentar acceder a la encuesta del usuario 1 como usuario 2
    with client.session_transaction() as sess:
        sess['user'] = {
            'uid': user2.uid,
            'email': user2.email,
            'name': user2.display_name
        }
    
    response = client.get(f'/survey/view/{survey_id}', follow_redirects=True)
    assert response.status_code == 200
    assert b'No tienes permiso' in response.data
    
    # Limpieza
    delete_test_survey(survey_id)
    delete_test_user(user1)
    delete_test_user(user2)

def test_nonexistent_route(client):
    """Prueba el manejo de rutas inexistentes"""
    response = client.get('/nonexistent-route')
    assert response.status_code == 404

def test_database_error_handling(client, monkeypatch):
    """Prueba el manejo de errores de base de datos"""
    # Simular un error en la base de datos
    def mock_collection(*args, **kwargs):
        raise Exception("Simulated database error")
    
    monkeypatch.setattr(db, 'collection', mock_collection)
    
    # Simular usuario en sesión sin intentar crearlo en la BD
    test_user = {
        'uid': 'testuid123',
        'email': 'test@example.com',
        'name': 'Test User'
    }
    
    with client.session_transaction() as sess:
        sess['user'] = test_user
    
    response = client.get('survey/dashboard', follow_redirects=True)
    assert response.status_code == 200
    assert b'Error al cargar dashboard' in response.data