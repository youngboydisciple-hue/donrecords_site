from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from datetime import datetime, date, time
from . import artist_bp
from app import db
from models import User, UserRole, SessionBooking, SessionStatus, Message
from werkzeug.utils import secure_filename
import os


# Decorator to restrict access to artist role
def artist_required(f):
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != UserRole.ARTIST:
            flash('Access denied. Artist privileges required.', 'danger')
            return redirect(url_for('main.index'))
        if not current_user.is_approved:
            flash('Your artist account is pending approval.', 'warning')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


@artist_bp.route('/dashboard')
@login_required
@artist_required
def dashboard():
    """Artist dashboard home"""
    # Get upcoming sessions
    upcoming_sessions = SessionBooking.query.filter_by(
        artist_id=current_user.id
    ).filter(
        SessionBooking.session_date >= date.today(),
        SessionBooking.status != SessionStatus.CANCELLED
    ).order_by(SessionBooking.session_date, SessionBooking.start_time).limit(5).all()
    
    # Get unread messages count
    unread_messages_count = Message.query.filter_by(
        recipient_id=current_user.id,
        is_read=False
    ).count()
    
    # Get all producers for booking sessions
    producers = User.query.filter_by(role=UserRole.PRODUCER, is_approved=True).all()
    
    return render_template('artist/dashboard.html',
                           upcoming_sessions=upcoming_sessions,
                           unread_messages_count=unread_messages_count,
                           producers=producers,
                           title="Artist Dashboard")


@artist_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@artist_required
def profile():
    """Artist profile management"""
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
        return redirect(url_for('artist.profile'))
    
    return render_template('artist/profile.html', title="Artist Profile")


@artist_bp.route('/sessions')
@login_required
@artist_required
def sessions():
    """View all artist's session bookings"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status')
    
    query = SessionBooking.query.filter_by(artist_id=current_user.id)
    
    if status_filter and status_filter in [status.value for status in SessionStatus]:
        query = query.filter_by(status=SessionStatus(status_filter))
    
    # Order by date and time, most recent first
    pagination = query.order_by(SessionBooking.session_date.desc(), 
                               SessionBooking.start_time.desc()).paginate(
        page=page, per_page=10, error_out=False)
    
    sessions = pagination.items
    
    return render_template('artist/sessions.html',
                           sessions=sessions,
                           pagination=pagination,
                           status_filter=status_filter,
                           session_statuses=SessionStatus,
                           title="My Sessions")


@artist_bp.route('/book-session', methods=['GET', 'POST'])
@login_required
@artist_required
def book_session():
    """Book a new session with a producer"""
    if request.method == 'POST':
        producer_id = request.form.get('producer_id', type=int)
        session_date_str = request.form.get('session_date')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        purpose = request.form.get('purpose')
        
        # Validate inputs
        if not all([producer_id, session_date_str, start_time_str, end_time_str, purpose]):
            flash('All fields are required', 'danger')
            return redirect(url_for('artist.book_session'))
        
        # Parse date and times
        try:
            session_date = datetime.strptime(session_date_str, '%Y-%m-%d').date()
            start_time = datetime.strptime(start_time_str, '%H:%M').time()
            end_time = datetime.strptime(end_time_str, '%H:%M').time()
            
            # Validate date and times
            if session_date < date.today():
                flash('Session date cannot be in the past', 'danger')
                return redirect(url_for('artist.book_session'))
            
            if start_time >= end_time:
                flash('End time must be after start time', 'danger')
                return redirect(url_for('artist.book_session'))
        except ValueError:
            flash('Invalid date or time format', 'danger')
            return redirect(url_for('artist.book_session'))
        
        # Check if producer exists and is approved
        producer = User.query.filter_by(id=producer_id, role=UserRole.PRODUCER, is_approved=True).first()
        if not producer:
            flash('Selected producer is not available', 'danger')
            return redirect(url_for('artist.book_session'))
        
        # Check for scheduling conflicts
        conflicts = SessionBooking.query.filter(
            SessionBooking.producer_id == producer_id,
            SessionBooking.session_date == session_date,
            SessionBooking.status != SessionStatus.CANCELLED
        ).filter(
            # Check for time overlap
            ((SessionBooking.start_time <= start_time) & (SessionBooking.end_time > start_time)) |
            ((SessionBooking.start_time < end_time) & (SessionBooking.end_time >= end_time)) |
            ((SessionBooking.start_time >= start_time) & (SessionBooking.end_time <= end_time))
        ).first()
        
        if conflicts:
            flash('The selected time slot is not available', 'danger')
            return redirect(url_for('artist.book_session'))
        
        # Calculate session price (2 hours minimum)
        duration_hours = (datetime.combine(date.today(), end_time) - 
                          datetime.combine(date.today(), start_time)).seconds / 3600
        duration_hours = max(2, duration_hours)  # Minimum 2 hours
        price = duration_hours * 50  # $50 per hour
        
        # Create new session booking
        new_session = SessionBooking(
            session_date=session_date,
            start_time=start_time,
            end_time=end_time,
            purpose=purpose,
            price=price,
            artist_id=current_user.id,
            producer_id=producer_id,
            status=SessionStatus.REQUESTED
        )
        
        db.session.add(new_session)
        db.session.commit()
        
        # Notify producer via message
        message = Message(
            subject="New Session Booking Request",
            body=f"You have a new session booking request from {current_user.get_full_name()} for {session_date_str} from {start_time_str} to {end_time_str}.\n\nPurpose: {purpose}",
            sender_id=current_user.id,
            recipient_id=producer_id
        )
        
        db.session.add(message)
        db.session.commit()
        
        flash('Session booking request submitted successfully', 'success')
        return redirect(url_for('artist.sessions'))
    
    # Get all producers for the form
    producers = User.query.filter_by(role=UserRole.PRODUCER, is_approved=True).all()
    
    return render_template('artist/book_session.html',
                           producers=producers,
                           min_date=date.today().strftime('%Y-%m-%d'),
                           title="Book a Session")


@artist_bp.route('/session/<int:session_id>')
@login_required
@artist_required
def session_detail(session_id):
    """View details of a specific session"""
    session = SessionBooking.query.filter_by(id=session_id, artist_id=current_user.id).first_or_404()
    producer = User.query.get_or_404(session.producer_id)
    
    return render_template('artist/session_detail.html',
                           session=session,
                           producer=producer,
                           title=f"Session on {session.session_date}")


@artist_bp.route('/cancel-session/<int:session_id>', methods=['POST'])
@login_required
@artist_required
def cancel_session(session_id):
    """Cancel a session booking"""
    session = SessionBooking.query.filter_by(id=session_id, artist_id=current_user.id).first_or_404()
    
    # Only allow cancellation if session is not already cancelled or completed
    if session.status in [SessionStatus.CANCELLED, SessionStatus.COMPLETED]:
        flash('Cannot cancel a session that is already completed or cancelled', 'danger')
        return redirect(url_for('artist.session_detail', session_id=session_id))
    
    # Update session status
    session.status = SessionStatus.CANCELLED
    db.session.commit()
    
    # Notify producer
    message = Message(
        subject="Session Booking Cancelled",
        body=f"The session booking for {session.session_date} from {session.start_time} to {session.end_time} has been cancelled by the artist.",
        sender_id=current_user.id,
        recipient_id=session.producer_id
    )
    
    db.session.add(message)
    db.session.commit()
    
    flash('Session cancelled successfully', 'success')
    return redirect(url_for('artist.sessions'))


@artist_bp.route('/messages')
@login_required
@artist_required
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
    
    return render_template('artist/messages.html',
                           messages=messages,
                           pagination=pagination,
                           filter_type=filter_type,
                           title="My Messages")


@artist_bp.route('/message/<int:message_id>')
@login_required
@artist_required
def message_detail(message_id):
    """View a specific message"""
    message = Message.query.filter(
        (Message.id == message_id) &
        ((Message.sender_id == current_user.id) | (Message.recipient_id == current_user.id))
    ).first_or_404()
    
    # Mark as read if current user is recipient
    if message.recipient_id == current_user.id and not message.is_read:
        message.mark_as_read()
    
    return render_template('artist/message_detail.html',
                           message=message,
                           title="Message Details")


@artist_bp.route('/send-message', methods=['GET', 'POST'])
@login_required
@artist_required
def send_message():
    """Send a new message"""
    if request.method == 'POST':
        recipient_id = request.form.get('recipient_id', type=int)
        subject = request.form.get('subject')
        body = request.form.get('body')
        
        if not all([recipient_id, subject, body]):
            flash('All fields are required', 'danger')
            return redirect(url_for('artist.send_message'))
        
        # Validate recipient
        recipient = User.query.filter(
            User.id == recipient_id,
            User.role.in_([UserRole.PRODUCER, UserRole.ADMIN])
        ).first()
        
        if not recipient:
            flash('Invalid recipient', 'danger')
            return redirect(url_for('artist.send_message'))
        
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
        return redirect(url_for('artist.messages', filter='sent'))
    
    # Get all producers and admins as potential recipients
    recipients = User.query.filter(
        User.role.in_([UserRole.PRODUCER, UserRole.ADMIN]),
        User.is_approved == True
    ).all()
    
    # Check if we're replying to a message
    reply_to = request.args.get('reply_to', type=int)
    original_message = None
    if reply_to:
        original_message = Message.query.filter_by(id=reply_to, recipient_id=current_user.id).first()
    
    return render_template('artist/send_message.html',
                           recipients=recipients,
                           original_message=original_message,
                           title="Send Message")


# Helper function to check allowed file extensions
def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS