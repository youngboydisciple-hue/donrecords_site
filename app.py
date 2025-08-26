import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from config import config
from markupsafe import Markup

# Initialize extensions
db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# Initialize migrate as None, will be set up in create_app
migrate = Migrate()




def create_admin_user():
    """Create default admin user if it doesn't exist"""
    from models import User, UserRole
    
    # Check if admin user already exists
    admin_user = User.query.filter_by(role=UserRole.ADMIN).first()
    
    if not admin_user:
        # Get admin credentials from environment variables or use defaults
        admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@gmail.com')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')  
        admin_first_name = os.environ.get('ADMIN_FIRST_NAME', 'Admin')
        admin_last_name = os.environ.get('ADMIN_LAST_NAME', 'User')
        
        # Create admin user
        admin_user = User(
            username=admin_username,
            email=admin_email,
            role=UserRole.ADMIN,
            is_active=True,
            is_approved=True,
            first_name=admin_first_name,
            last_name=admin_last_name,
            bio="System Administrator"
        )
        admin_user.password = admin_password  # This will hash the password
        
        try:
            db.session.add(admin_user)
            db.session.commit()
            print(f"✅ Admin user created successfully!")
            print(f"   Username: {admin_username}")
            print(f"   Email: {admin_email}")
            print(f"   Password: {admin_password}")
            print(" ⚠️ Please change the default password after first login!")
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error creating admin user: {e}")
    else:
        print(f"ℹ️ Admin user already exists: {admin_user.username}")


def create_app(config_name=None):
    # Create and configure the app
    app = Flask(__name__)
    
    # Load configuration
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    app.config.from_object(config[config_name])
    config[config_name].init_app(app)
    
    # Initialize extensions with app
    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)  # Correct way to initialize Migrate
    
    # Import models here to ensure they're registered with SQLAlchemy AND Flask-Login
    from models import (User, Beat, Merchandise, Order, OrderItem,
                        Transaction, BlogPost, SessionBooking, Message)
    
    # Register the user loader function
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    def nl2br(value):
        """Convert newlines to <br> tags"""
        if not value:
            return value
        from markupsafe import escape
        value = escape(value)
        value = value.replace('\n', Markup('<br>\n'))
        return Markup(value)

       
    
    # Ensure upload directory exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    
    # Register blueprints
    from blueprints.main import main_bp
    from blueprints.auth import auth_bp
    from blueprints.artist import artist_bp
    from blueprints.producer import producer_bp
    from blueprints.admin import admin_bp
    from blueprints.payments import payments_bp
    
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(artist_bp, url_prefix='/artist')
    app.register_blueprint(producer_bp, url_prefix='/producer')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(payments_bp, url_prefix='/payments')
    app.jinja_env.filters['nl2br'] = nl2br
    
    # Create database tables and admin user
    with app.app_context():
        try:
            # Create all database tables
            db.create_all()
            print("✅ Database tables created successfully!")
            
            # Create admin user
            create_admin_user()
            
        except Exception as e:
            print(f"❌ Error during database initialization: {e}")
    
    # Shell context
    @app.shell_context_processor
    def make_shell_context():
        return dict(
            db=db, User=User, Beat=Beat, Merchandise=Merchandise,
            Order=Order, OrderItem=OrderItem, Transaction=Transaction,
            BlogPost=BlogPost, SessionBooking=SessionBooking, Message=Message
        )
    
    # Template globals
    @app.context_processor
    def inject_template_vars():
        from datetime import datetime
        return {
            'now': datetime.utcnow(),
            'current_year': datetime.utcnow().year,
            'app_name': 'Don Records',
            'app_version': '1.0.0'
        }
    
    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)


#israel@gmail.com israel2025 -user
#admin@donrecords.com admin123 -admin
#kingdon@gmail.com kingdon2025 -producer
#prof@gmail.com  prof2025-Artist

