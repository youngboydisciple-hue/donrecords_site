from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from datetime import datetime, date, time
from werkzeug.utils import secure_filename
import os
import uuid

from . import producer_bp
from app import db
from models import User, UserRole, Beat, SessionBooking, SessionStatus, Message


# Decorator to restrict access to producer role
def producer_required(f):
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != UserRole.PRODUCER:
            flash('Access denied. Producer privileges required.', 'danger')
            return redirect(url_for('main.index'))
        if not current_user.is_approved:
            flash('Your producer account is pending approval.', 'warning')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


@producer_bp.route('/dashboard')
@login_required
@producer_required
def dashboard():
    """Producer dashboard home"""
    # Get upcoming sessions
    upcoming_sessions = SessionBooking.query.filter_by(
        producer_id=current_user.id
    ).filter(
        SessionBooking.session_date >= date.today(),
        SessionBooking.status != SessionStatus.CANCELLED
    ).order_by(SessionBooking.session_date, SessionBooking.start_time).limit(5).all()
    
    # Get pending session requests
    pending_sessions = SessionBooking.query.filter_by(
        producer_id=current_user.id,
        status=SessionStatus.REQUESTED
    ).count()
    
    # Get unread messages count
    unread_messages_count = Message.query.filter_by(
        recipient_id=current_user.id,
        is_read=False
    ).count()
    
    # Get beats count and stats
    beats_count = Beat.query.filter_by(producer_id=current_user.id).count()
    published_beats = Beat.query.filter_by(producer_id=current_user.id, is_published=True).count()
    
    # Get total plays and downloads
    total_plays = db.session.query(db.func.sum(Beat.play_count)).filter_by(producer_id=current_user.id).scalar() or 0
    total_downloads = db.session.query(db.func.sum(Beat.download_count)).filter_by(producer_id=current_user.id).scalar() or 0
    
    # Get recent beats
    recent_beats = Beat.query.filter_by(producer_id=current_user.id).order_by(Beat.created_at.desc()).limit(5).all()
    
    return render_template('producer/dashboard.html',
                           upcoming_sessions=upcoming_sessions,
                           pending_sessions=pending_sessions,
                           unread_messages_count=unread_messages_count,
                           beats_count=beats_count,
                           published_beats=published_beats,
                           total_plays=total_plays,
                           total_downloads=total_downloads,
                           recent_beats=recent_beats,
                           title="Producer Dashboard")


@producer_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@producer_required
def profile():
    """Producer profile management"""
    if request.method == 'POST':
        # Update profile information
        current_user.first_name = request.form.get('first_name')
        current_user.last_name = request.form.get('last_name')
        current_user.bio = request.form.get('bio')
        current_user.phone_number = request.form.get('phone_number')
        
        # Handle profile image upload
        if 'profile_image' in request.files and request.files['profile_image'].filename:
            file = request.files['profile_image']
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                # Create unique filename
                unique_filename = f"{current_user.id}_{int(datetime.utcnow().timestamp())}_{filename}"
                file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'profile_images', unique_filename)
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                
                file.save(file_path)
                current_user.profile_image = f"uploads/profile_images/{unique_filename}"
        
        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('producer.profile'))
    
    return render_template('producer/profile.html', title="Producer Profile")


@producer_bp.route('/beats')
@login_required
@producer_required
def beats():
    """View all producer's beats"""
    page = request.args.get('page', 1, type=int)
    
    pagination = Beat.query.filter_by(producer_id=current_user.id).order_by(
        Beat.created_at.desc()).paginate(page=page, per_page=10, error_out=False)
    
    beats = pagination.items
    
    return render_template('producer/beats.html',
                           beats=beats,
                           pagination=pagination,
                           title="My Beats")


@producer_bp.route('/beat/new', methods=['GET', 'POST'])
@login_required
@producer_required
def new_beat():
    """Create a new beat"""
    if request.method == 'POST':
        title = request.form.get('title')
        description = request.form.get('description')
        price = request.form.get('price', type=float)
        bpm = request.form.get('bpm', type=int)
        key = request.form.get('key')
        genre = request.form.get('genre')
        tags = request.form.get('tags')
        is_published = 'is_published' in request.form
        is_featured = 'is_featured' in request.form
        
        # Validate required fields
        if not all([title, price]):
            flash('Title and price are required', 'danger')
            return redirect(url_for('producer.new_beat'))
        
        # Handle audio file upload
        if 'audio_file' not in request.files or not request.files['audio_file'].filename:
            flash('Audio file is required', 'danger')
            return redirect(url_for('producer.new_beat'))
        
        audio_file = request.files['audio_file']
        if not allowed_audio_file(audio_file.filename):
            flash('Invalid audio file format. Allowed formats: mp3, wav, ogg', 'danger')
            return redirect(url_for('producer.new_beat'))
        
        # Save audio file
        audio_filename = secure_filename(audio_file.filename)
        unique_audio_filename = f"{uuid.uuid4().hex}_{audio_filename}"
        audio_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'beats', unique_audio_filename)
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(audio_path), exist_ok=True)
        
        audio_file.save(audio_path)
        
        # Handle cover image upload
        cover_image_path = None
        if 'cover_image' in request.files and request.files['cover_image'].filename:
            cover_image = request.files['cover_image']
            if allowed_image_file(cover_image.filename):
                cover_filename = secure_filename(cover_image.filename)
                unique_cover_filename = f"{uuid.uuid4().hex}_{cover_filename}"
                cover_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'covers', unique_cover_filename)
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(cover_path), exist_ok=True)
                
                cover_image.save(cover_path)
                cover_image_path = f"uploads/covers/{unique_cover_filename}"
        
        # Create new beat
        new_beat = Beat(
            title=title,
            description=description,
            price=price,
            audio_file=f"uploads/beats/{unique_audio_filename}",
            cover_image=cover_image_path,
            bpm=bpm,
            key=key,
            genre=genre,
            tags=tags,
            is_published=is_published,
            is_featured=is_featured,
            producer_id=current_user.id
        )
        
        db.session.add(new_beat)
        db.session.commit()
        
        flash('Beat created successfully', 'success')
        return redirect(url_for('producer.beats'))
    
    return render_template('producer/beat_form.html',
                           title="New Beat",
                           beat=None)


@producer_bp.route('/beat/<int:beat_id>/edit', methods=['GET', 'POST'])
@login_required
@producer_required
def edit_beat(beat_id):
    """Edit an existing beat"""
    beat = Beat.query.filter_by(id=beat_id, producer_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        beat.title = request.form.get('title')
        beat.description = request.form.get('description')
        beat.price = request.form.get('price', type=float)
        beat.bpm = request.form.get('bpm', type=int)
        beat.key = request.form.get('key')
        beat.genre = request.form.get('genre')
        beat.tags = request.form.get('tags')
        beat.is_published = 'is_published' in request.form
        beat.is_featured = 'is_featured' in request.form
        
        # Handle audio file upload if provided
        if 'audio_file' in request.files and request.files['audio_file'].filename:
            audio_file = request.files['audio_file']
            if allowed_audio_file(audio_file.filename):
                # Delete old file if exists
                if beat.audio_file:
                    old_path = os.path.join(current_app.root_path, 'static', beat.audio_file)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                # Save new file
                audio_filename = secure_filename(audio_file.filename)
                unique_audio_filename = f"{uuid.uuid4().hex}_{audio_filename}"
                audio_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'beats', unique_audio_filename)
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(audio_path), exist_ok=True)
                
                audio_file.save(audio_path)
                beat.audio_file = f"uploads/beats/{unique_audio_filename}"
        
        # Handle cover image upload if provided
        if 'cover_image' in request.files and request.files['cover_image'].filename:
            cover_image = request.files['cover_image']
            if allowed_image_file(cover_image.filename):
                # Delete old file if exists
                if beat.cover_image:
                    old_path = os.path.join(current_app.root_path, 'static', beat.cover_image)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                
                # Save new file
                cover_filename = secure_filename(cover_image.filename)
                unique_cover_filename = f"{uuid.uuid4().hex}_{cover_filename}"
                cover_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'covers', unique_cover_filename)
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(cover_path), exist_ok=True)
                
                cover_image.save(cover_path)
                beat.cover_image = f"uploads/covers/{unique_cover_filename}"
        
        db.session.commit()
        flash('Beat updated successfully', 'success')
        return redirect(url_for('producer.beats'))
    
    return render_template('producer/beat_form.html',
                           title="Edit Beat",
                           beat=beat)


@producer_bp.route('/beat/<int:beat_id>/delete', methods=['POST'])
@login_required
@producer_required
def delete_beat(beat_id):
    """Delete a beat"""
    beat = Beat.query.filter_by(id=beat_id, producer_id=current_user.id).first_or_404()
    
    # Delete associated files
    if beat.audio_file:
        audio_path = os.path.join(current_app.root_path, 'static', beat.audio_file)
        if os.path.exists(audio_path):
            os.remove(audio_path)
    
    if beat.cover_image:
        cover_path = os.path.join(current_app.root_path, 'static', beat.cover_image)
        if os.path.exists(cover_path):
            os.remove(cover_path)
    
    db.session.delete(beat)
    db.session.commit()
    
    flash('Beat deleted successfully', 'success')
    return redirect(url_for('producer.beats'))


@producer_bp.route('/sessions')
@login_required
@producer_required
def sessions():
    """View all producer's session bookings"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status')
    
    query = SessionBooking.query.filter_by(producer_id=current_user.id)
    
    if status_filter and status_filter in [status.value for status in SessionStatus]:
        query = query.filter_by(status=SessionStatus(status_filter))
    
    # Order by date and time, most recent first
    pagination = query.order_by(SessionBooking.session_date.desc(), 
                               SessionBooking.start_time.desc()).paginate(
        page=page, per_page=10, error_out=False)
    
    sessions = pagination.items
    
    return render_template('producer/sessions.html',
                           sessions=sessions,
                           pagination=pagination,
                           status_filter=status_filter,
                           session_statuses=SessionStatus,
                           title="Session Bookings")


@producer_bp.route('/session/<int:session_id>')
@login_required
@producer_required
def session_detail(session_id):
    """View details of a specific session"""
    session = SessionBooking.query.filter_by(id=session_id, producer_id=current_user.id).first_or_404()
    artist = User.query.get_or_404(session.artist_id)
    
    return render_template('producer/session_detail.html',
                           session=session,
                           artist=artist,
                           title=f"Session on {session.session_date}")


@producer_bp.route('/session/<int:session_id>/update-status', methods=['POST'])
@login_required
@producer_required
def update_session_status(session_id):
    """Update session status"""
    session = SessionBooking.query.filter_by(id=session_id, producer_id=current_user.id).first_or_404()
    new_status = request.form.get('status')
    notes = request.form.get('notes')
    
    if new_status not in [status.value for status in SessionStatus]:
        flash('Invalid status', 'danger')
        return redirect(url_for('producer.session_detail', session_id=session_id))
    
    # Update session
    session.status = SessionStatus(new_status)
    if notes:
        session.notes = notes
    
    db.session.commit()
    
    # Notify artist
    message = Message(
        subject=f"Session Status Updated: {session.status.value.capitalize()}",
        body=f"Your session booking for {session.session_date.strftime('%B %d, %Y')} from {session.start_time.strftime('%I:%M %p')} to {session.end_time.strftime('%I:%M %p')} has been updated to {session.status.value.capitalize()}.\n\n{notes if notes else ''}",
        sender_id=current_user.id,
        recipient_id=session.artist_id
    )
    
    db.session.add(message)
    db.session.commit()
    
    flash('Session status updated successfully', 'success')
    return redirect(url_for('producer.session_detail', session_id=session_id))


@producer_bp.route('/messages')
@login_required
@producer_required
def messages():
    """View all messages"""
    page = request.args.get('page', 1, type=int)
    filter_type = request.args.get('filter', 'received')
    
    if filter_type == 'sent':
        query = Message.query.filter_by(sender_id=current_user.id)
    else:  # received
        query = Message.query.filter_by(recipient_id=current_user.id)
    
    pagination = query.order_by(Message.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False)
    
    messages = pagination.items
    
    return render_template('producer/messages.html',
                           messages=messages,
                           pagination=pagination,
                           filter_type=filter_type,
                           title="My Messages")


@producer_bp.route('/message/<int:message_id>')
@login_required
@producer_required
def message_detail(message_id):
    """View a specific message"""
    message = Message.query.filter(
        (Message.id == message_id) &
        ((Message.sender_id == current_user.id) | (Message.recipient_id == current_user.id))
    ).first_or_404()
    
    # Mark as read if current user is recipient
    if message.recipient_id == current_user.id and not message.is_read:
        message.mark_as_read()
    
    return render_template('producer/message_detail.html',
                           message=message,
                           title="Message Details")


@producer_bp.route('/send-message', methods=['GET', 'POST'])
@login_required
@producer_required
def send_message():
    """Send a new message"""
    if request.method == 'POST':
        recipient_id = request.form.get('recipient_id', type=int)
        subject = request.form.get('subject')
        body = request.form.get('body')
        
        if not all([recipient_id, subject, body]):
            flash('All fields are required', 'danger')
            return redirect(url_for('producer.send_message'))
        
        # Validate recipient
        recipient = User.query.filter(
            User.id == recipient_id,
            User.role.in_([UserRole.ARTIST, UserRole.ADMIN])
        ).first()
        
        if not recipient:
            flash('Invalid recipient', 'danger')
            return redirect(url_for('producer.send_message'))
        
        # Create and send message
        message = Message(
            subject=subject,
            body=body,
            sender_id=current_user.id,
            recipient_id=recipient_id
        )
        
        db.session.add(message)
        db.session.commit()
        
        flash('Message sent successfully', 'success')
        return redirect(url_for('producer.messages', filter='sent'))
    
    # Get all artists and admins as potential recipients
    recipients = User.query.filter(
        User.role.in_([UserRole.ARTIST, UserRole.ADMIN]),
        User.is_approved == True
    ).all()
    
    # Check if we're replying to a message
    reply_to = request.args.get('reply_to', type=int)
    original_message = None
    if reply_to:
        original_message = Message.query.filter_by(id=reply_to, recipient_id=current_user.id).first()
    
    return render_template('producer/send_message.html',
                           recipients=recipients,
                           original_message=original_message,
                           title="Send Message")


# Helper functions for file uploads
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_audio_file(filename):
    ALLOWED_EXTENSIONS = {'mp3', 'wav', 'ogg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS