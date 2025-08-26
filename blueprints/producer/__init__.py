from flask import Blueprint

producer_bp = Blueprint('producer', __name__)

from . import routes