from flask import Blueprint

artist_bp = Blueprint('artist', __name__)

from . import routes