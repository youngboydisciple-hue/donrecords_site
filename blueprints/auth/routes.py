from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash
from datetime import datetime
from . import auth_bp
from app import db
from models import User, UserRole
from .forms import LoginForm, RegistrationForm, ResetPasswordRequestForm, ResetPasswordForm


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    """User login route"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        
        if user and user.verify_password(form.password.data):
            if not user.is_active:
                flash('Account not activated. Please check your email for activation instructions.', 'warning')
                return render_template('auth/login.html', form=form, title="Login")
            
            if not user.is_approved and user.role != UserRole.USER:
                flash('Your account is pending approval by an administrator.', 'warning')
                return render_template('auth/login.html', form=form, title="Login")
            
            login_user(user, remember=form.remember.data)
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            next_page = request.args.get('next')
            if next_page:
                return redirect(next_page)
            
            # Redirect based on role
            if user.role == UserRole.ADMIN:
                return redirect(url_for('admin.dashboard'))
            elif user.role == UserRole.PRODUCER:
                return redirect(url_for('producer.dashboard'))
            elif user.role == UserRole.ARTIST:
                return redirect(url_for('artist.dashboard'))
            else:
                return redirect(url_for('main.index'))
        else:
            flash('Invalid email or password', 'danger')
    
    return render_template('auth/login.html', form=form, title="Login")


@auth_bp.route('/logout')
def logout():
    """User logout route"""
    logout_user()
    flash('You have been logged out', 'info')
    return redirect(url_for('main.index'))


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    """User registration route"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        # Check if email already exists
        if User.query.filter_by(email=form.email.data.lower()).first():
            flash('Email already registered', 'danger')
            return render_template('auth/register.html', form=form, title="Register")
        
        # Check if username already exists
        if User.query.filter_by(username=form.username.data).first():
            flash('Username already taken', 'danger')
            return render_template('auth/register.html', form=form, title="Register")
        
        # Create new user
        user = User(
            username=form.username.data,
            email=form.email.data.lower(),
            password=form.password.data,
            role=UserRole(form.role.data),
            is_active=True,  # Set to False if email verification is implemented
            is_approved=form.role.data == UserRole.USER.value  # Auto-approve regular users
        )
        
        db.session.add(user)
        db.session.commit()
        
        # Send email verification here if needed
        
        if user.role == UserRole.USER:
            flash('Registration successful! You can now log in.', 'success')
            return redirect(url_for('auth.login'))
        else:
            flash('Registration successful! Your account is pending approval by an administrator.', 'info')
            return redirect(url_for('auth.login'))
    
    return render_template('auth/register.html', form=form, title="Register")


@auth_bp.route('/reset-password-request', methods=['GET', 'POST'])
def reset_password_request():
    """Request password reset route"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    form = ResetPasswordRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user:
            # Send password reset email here
            pass
        
        flash('If your email is registered, you will receive instructions to reset your password.', 'info')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password_request.html', form=form, title="Reset Password")


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    """Reset password with token route"""
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    
    # Verify token and get user
    # user = User.verify_reset_token(token)
    # if not user:
    #     flash('Invalid or expired token', 'warning')
    #     return redirect(url_for('auth.reset_password_request'))
    
    form = ResetPasswordForm()
    if form.validate_on_submit():
        # user.password = form.password.data
        # db.session.commit()
        flash('Your password has been reset. You can now log in.', 'success')
        return redirect(url_for('auth.login'))
    
    return render_template('auth/reset_password.html', form=form, title="Reset Password")


@auth_bp.route('/profile')
@login_required
def profile():
    """User profile route"""
    # Redirect to role-specific profile
    if current_user.role == UserRole.ADMIN:
        return redirect(url_for('admin.profile'))
    elif current_user.role == UserRole.PRODUCER:
        return redirect(url_for('producer.profile'))
    elif current_user.role == UserRole.ARTIST:
        return redirect(url_for('artist.profile'))
    else:
        # Regular user profile
        return render_template('auth/profile.html', title="My Profile")