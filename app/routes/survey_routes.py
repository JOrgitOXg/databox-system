# app/routes/survey_routes.py
from flask import Blueprint
from app.controllers.survey_controller import (
    get_dashboard_data,
    handle_create_survey,
    handle_edit_survey,
    get_survey_data,
    handle_public_survey,
    handle_submit_survey,
    handle_delete_survey,
    get_survey_stats
)

# Crear Blueprint para rutas de encuestas
survey_bp = Blueprint('survey', __name__)

# Definir rutas con nombres explícitos
survey_bp.route('/dashboard', endpoint='dashboard')(get_dashboard_data)
survey_bp.route('/create', methods=['GET', 'POST'], endpoint='create_survey')(handle_create_survey)
survey_bp.route('/edit/<survey_id>', methods=['GET', 'POST'], endpoint='edit_survey')(handle_edit_survey)
survey_bp.route('/view/<survey_id>', endpoint='view_survey')(get_survey_data)
survey_bp.route('/public/<survey_id>', methods=['GET', 'POST'], endpoint='public_survey')(handle_public_survey)
survey_bp.route('/submit/<survey_id>', methods=['GET', 'POST'], endpoint='submit_survey')(handle_submit_survey)
survey_bp.route('/delete/<survey_id>', methods=['GET', 'POST'], endpoint='delete_survey')(handle_delete_survey)
survey_bp.route('/stats/<survey_id>', methods=['GET', 'POST'], endpoint='stats')(get_survey_stats)