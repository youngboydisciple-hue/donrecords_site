from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from datetime import datetime
from functools import wraps
from . import admin_bp
from app import db
import os
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from models import User, UserRole, Beat, Merchandise, Order, OrderStatus, BlogPost, SessionBooking, SessionStatus, Message


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != UserRole.ADMIN:
            flash('Access denied. Admin privileges required.', 'danger')
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    """Admin dashboard home"""
    # Get counts for various entities
    users_count = User.query.count()
    pending_users = User.query.filter_by(is_approved=False).filter(
        User.role != UserRole.USER).count()
    beats_count = Beat.query.count()
    merchandise_count = Merchandise.query.count()
    orders_count = Order.query.count()
    pending_orders = Order.query.filter_by(status=OrderStatus.PENDING).count()
    sessions_count = SessionBooking.query.count()
    pending_sessions = SessionBooking.query.filter_by(status=SessionStatus.REQUESTED).count()
    
    # Get recent orders
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    
    # Get unread messages count
    unread_messages_count = Message.query.filter_by(
        recipient_id=current_user.id,
        is_read=False
    ).count()
    
    return render_template('admin/dashboard.html',
                           users_count=users_count,
                           pending_users=pending_users,
                           beats_count=beats_count,
                           merchandise_count=merchandise_count,
                           orders_count=orders_count,
                           pending_orders=pending_orders,
                           sessions_count=sessions_count,
                           pending_sessions=pending_sessions,
                           recent_orders=recent_orders,
                           unread_messages_count=unread_messages_count,
                           title="Admin Dashboard")


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    """View all users"""
    page = request.args.get('page', 1, type=int)
    role_filter = request.args.get('role')
    approval_filter = request.args.get('approval')
    
    query = User.query
    
    if role_filter and role_filter in [role.value for role in UserRole]:
        query = query.filter_by(role=UserRole(role_filter))
    
    if approval_filter:
        is_approved = approval_filter == 'approved'
        query = query.filter_by(is_approved=is_approved)
    
    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False)
    
    users = pagination.items
    
    return render_template('admin/users.html',
                           users=users,
                           pagination=pagination,
                           role_filter=role_filter,
                           approval_filter=approval_filter,
                           roles=UserRole,
                           title="Manage Users")


@admin_bp.route('/user/<int:user_id>')
@login_required
@admin_required
def user_detail(user_id):
    """View user details"""
    user = User.query.get_or_404(user_id)
    return render_template('admin/user_detail.html',
                           user=user,
                           title=f"User: {user.username}")


@admin_bp.route('/user/<int:user_id>/approve', methods=['GET', 'POST'])
@login_required
@admin_required
def approve_user(user_id):
    """Approve a user account"""
    user = User.query.get_or_404(user_id)
    
    if user.is_approved:
        flash('User is already approved', 'info')
    else:
        user.is_approved = True
        db.session.commit()
        
        # Send notification message to user
        message = Message(
            subject="Your Account Has Been Approved",
            body="Your account has been approved by an administrator. You now have full access to all features.",
            sender_id=current_user.id,
            recipient_id=user.id
        )
        db.session.add(message)
        db.session.commit()
        
        flash('User has been approved successfully', 'success')
    
    return redirect(url_for('admin.user_detail', user_id=user_id))


@admin_bp.route('/orders')
@login_required
@admin_required
def orders():
    """View all orders"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status')
    
    query = Order.query
    
    if status_filter and status_filter in [status.value for status in OrderStatus]:
        query = query.filter_by(status=OrderStatus(status_filter))
    
    pagination = query.order_by(Order.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False)
    
    orders = pagination.items
    
    return render_template('admin/orders.html',
                           orders=orders,
                           pagination=pagination,
                           status_filter=status_filter,
                           statuses=OrderStatus,
                           title="Manage Orders")


@admin_bp.route('/order/<string:order_number>')
@login_required
@admin_required
def order_detail(order_number):
    """View order details"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    return render_template('admin/order_detail.html',
                           order=order,
                           title=f"Order: {order.order_number}")


@admin_bp.route('/order/<string:order_number>/update-status', methods=['POST'])
@login_required
@admin_required
def update_order_status(order_number):
    """Update order status"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    new_status = request.form.get('status')
    notes = request.form.get('notes')
    
    if new_status not in [status.value for status in OrderStatus]:
        flash('Invalid status', 'danger')
        return redirect(url_for('admin.order_detail', order_number=order.order_number))
    
    # Update order
    old_status = order.status
    order.status = OrderStatus(new_status)
    if notes:
        order.notes = notes
    
    # Update timestamps based on status
    if order.status == OrderStatus.PAID and old_status != OrderStatus.PAID:
        order.paid_at = datetime.utcnow()
    elif order.status == OrderStatus.SHIPPED and old_status != OrderStatus.SHIPPED:
        order.shipped_at = datetime.utcnow()
    elif order.status == OrderStatus.DELIVERED and old_status != OrderStatus.DELIVERED:
        order.delivered_at = datetime.utcnow()
    
    db.session.commit()
    
    # Send notification to customer
    message = Message(
        subject=f"Order {order.order_number} Status Update",
        body=f"Your order status has been updated to: {order.status.value.upper()}\n\n" +
             (f"Notes: {notes}" if notes else ""),
        sender_id=current_user.id,
        recipient_id=order.customer_id
    )
    db.session.add(message)
    db.session.commit()
    
    flash('Order status updated successfully', 'success')
    return redirect(url_for('admin.order_detail', order_number=order.order_number))


@admin_bp.route('/sessions')
@login_required
@admin_required
def sessions():
    """View all session bookings"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status')
    
    query = SessionBooking.query
    
    if status_filter and status_filter in [status.value for status in SessionStatus]:
        query = query.filter_by(status=SessionStatus(status_filter))
    
    pagination = query.order_by(SessionBooking.session_date.desc()).paginate(
        page=page, per_page=10, error_out=False)
    
    sessions = pagination.items
    
    return render_template('admin/sessions.html',
                           sessions=sessions,
                           pagination=pagination,
                           status_filter=status_filter,
                           statuses=SessionStatus,
                           title="Manage Sessions")


@admin_bp.route('/session/<int:session_id>')
@login_required
@admin_required
def session_detail(session_id):
    """View session details"""
    session = SessionBooking.query.get_or_404(session_id)
    artist = User.query.get_or_404(session.artist_id)
    producer = User.query.get_or_404(session.producer_id)
    
    return render_template('admin/session_detail.html',
                           session=session,
                           artist=artist,
                           producer=producer,
                           title=f"Session on {session.session_date}")


@admin_bp.route('/profile', methods=['GET', 'POST'])
@login_required
@admin_required
def profile():
    """Admin profile management"""
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
                
                # Save the file
                file.save(file_path)
                
                # Update user profile image path
                current_user.profile_image = os.path.join('uploads', 'profile_images', unique_filename)
        
        db.session.commit()
        flash('Profile updated successfully', 'success')
        return redirect(url_for('admin.profile'))
    
    return render_template('admin/profile.html', title="My Profile")


@admin_bp.route('/messages')
@login_required
@admin_required
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
    
    return render_template('admin/messages.html',
                           messages=messages,
                           pagination=pagination,
                           filter_type=filter_type,
                           title="My Messages")


@admin_bp.route('/message/<int:message_id>')
@login_required
@admin_required
def message_detail(message_id):
    """View message details"""
    message = Message.query.get_or_404(message_id)
    
    # Check if user is allowed to view this message
    if message.sender_id != current_user.id and message.recipient_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('admin.messages'))
    
    # Mark as read if current user is the recipient
    if message.recipient_id == current_user.id and not message.is_read:
        message.mark_as_read()
    
    return render_template('admin/message_detail.html',
                           message=message,
                           title="Message Details")


@admin_bp.route('/send-message', methods=['GET', 'POST'])
@login_required
@admin_required
def send_message():
    """Send a new message"""
    if request.method == 'POST':
        recipient_id = request.form.get('recipient_id', type=int)
        subject = request.form.get('subject')
        body = request.form.get('body')
        
        if not all([recipient_id, subject, body]):
            flash('All fields are required', 'danger')
            return redirect(url_for('admin.send_message'))
        
        # Validate recipient exists
        recipient = User.query.get(recipient_id)
        if not recipient:
            flash('Invalid recipient', 'danger')
            return redirect(url_for('admin.send_message'))
        
        # Create new message
        message = Message(
            subject=subject,
            body=body,
            sender_id=current_user.id,
            recipient_id=recipient_id
        )
        db.session.add(message)
        db.session.commit()
        
        flash('Message sent successfully', 'success')
        return redirect(url_for('admin.messages'))
    
    # Get all users for recipient selection
    users = User.query.filter(User.id != current_user.id).all()
    
    # Check if this is a reply to an existing message
    reply_to = request.args.get('reply_to', type=int)
    original_message = None
    if reply_to:
        original_message = Message.query.get(reply_to)
    
    return render_template('admin/send_message.html',
                           users=users,
                           original_message=original_message,
                           title="Send Message")

@admin_bp.route('/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(user_id):
    """Edit user details"""
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        # Update user information
        user.first_name = request.form.get('first_name')
        user.last_name = request.form.get('last_name')
        user.email = request.form.get('email')
        user.bio = request.form.get('bio')
        user.phone_number = request.form.get('phone_number')
        
        # Handle role change (be careful with this!)
        new_role = request.form.get('role')
        if new_role and new_role in [role.value for role in UserRole]:
            user.role = UserRole(new_role)
        
        # Handle approval status
        is_approved = request.form.get('is_approved') == 'on'
        user.is_approved = is_approved
        
        try:
            db.session.commit()
            flash('User updated successfully', 'success')
            return redirect(url_for('admin.user_detail', user_id=user_id))
        except Exception as e:
            db.session.rollback()
            flash('An error occurred while updating the user', 'danger')
            current_app.logger.error(f"Error updating user {user_id}: {str(e)}")
    
    return render_template('admin/edit_user.html',
                           user=user,
                           roles=UserRole,
                           title=f"Edit User: {user.username}")

@admin_bp.route('/user/<int:user_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(user_id):
    """Delete a user account"""
    user = User.query.get_or_404(user_id)
    
    # Prevent admin from deleting themselves
    if user.id == current_user.id:
        flash('You cannot delete your own account', 'danger')
        return redirect(url_for('admin.users'))
    
    # Prevent deletion of other admins (optional security measure)
    if user.role == UserRole.ADMIN:
        flash('Cannot delete admin accounts', 'danger')
        return redirect(url_for('admin.users'))
    
    try:
        # Handle related data before deletion
        # Delete related messages
        Message.query.filter(
            (Message.sender_id == user_id) | (Message.recipient_id == user_id)
        ).delete()
        
        # Handle orders - you might want to keep orders for business records
        # but remove the customer reference
        Order.query.filter_by(customer_id=user_id).update({'customer_id': None})
        
        # Handle session bookings
        SessionBooking.query.filter(
            (SessionBooking.artist_id == user_id) | (SessionBooking.producer_id == user_id)
        ).delete()
        
        # Delete the user
        db.session.delete(user)
        db.session.commit()
        
        flash(f'User {user.username} has been deleted successfully', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('An error occurred while deleting the user', 'danger')
        current_app.logger.error(f"Error deleting user {user_id}: {str(e)}")
    
    return redirect(url_for('admin.users'))


# Alternative route that shows a confirmation page first (recommended for better UX)
@admin_bp.route('/user/<int:user_id>/delete-confirm')
@login_required
@admin_required
def delete_user_confirm(user_id):
    """Show confirmation page before deleting user"""
    user = User.query.get_or_404(user_id)
    
    # Prevent admin from deleting themselves
    if user.id == current_user.id:
        flash('You cannot delete your own account', 'danger')
        return redirect(url_for('admin.users'))
    
    # Prevent deletion of other admins
    if user.role == UserRole.ADMIN:
        flash('Cannot delete admin accounts', 'danger')
        return redirect(url_for('admin.users'))
    
    return render_template('admin/delete_user_confirm.html',
                           user=user,
                           title=f"Delete User: {user.username}")


def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS