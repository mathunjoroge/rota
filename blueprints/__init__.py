from flask import Blueprint

auth = Blueprint('auth', __name__)

from blueprints import routes