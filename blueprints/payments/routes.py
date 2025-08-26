from flask import render_template, redirect, url_for, flash, request, session, current_app, jsonify
from flask_login import login_required, current_user
from datetime import datetime
import os
import json
import uuid
from . import payments_bp
from app import db
from models import Order, OrderItem, Transaction, TransactionStatus, PaymentMethod, Beat, Merchandise, OrderStatus, SessionBooking, Message, User


@payments_bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    """Checkout page for cart items"""
    cart_items = session.get('cart', [])
    
    if not cart_items:
        flash('Your cart is empty', 'warning')
        return redirect(url_for('main.cart'))
    
    # Calculate cart total
    total = 0
    cart_contents = []
    
    for item in cart_items:
        if item['type'] == 'beat':
            product = Beat.query.get(item['id'])
            if product and product.is_published:
                cart_contents.append({
                    'id': product.id,
                    'type': 'beat',
                    'name': product.title,
                    'price': product.price,
                    'image': product.cover_image,
                    'quantity': item['quantity']
                })
                total += product.price * item['quantity']
        elif item['type'] == 'merchandise':
            product = Merchandise.query.get(item['id'])
            if product and product.is_published:
                cart_contents.append({
                    'id': product.id,
                    'type': 'merchandise',
                    'name': product.name,
                    'price': product.price,
                    'image': product.image,
                    'quantity': item['quantity']
                })
                total += product.price * item['quantity']
    
    if request.method == 'POST':
        # Validate user is logged in
        if not current_user.is_authenticated:
            flash('Please login to complete your purchase', 'warning')
            return redirect(url_for('auth.login', next=url_for('payments.checkout')))
        
        # Get form data
        shipping_address = request.form.get('shipping_address')
        shipping_city = request.form.get('shipping_city')
        shipping_country = request.form.get('shipping_country')
        shipping_postal_code = request.form.get('shipping_postal_code')
        payment_method = request.form.get('payment_method')
        notes = request.form.get('notes')
        
        # Validate required fields
        if not all([shipping_address, shipping_city, shipping_country, shipping_postal_code, payment_method]):
            flash('All shipping fields are required', 'danger')
            return render_template('payments/checkout.html',
                                  cart_contents=cart_contents,
                                  total=total,
                                  payment_methods=PaymentMethod,
                                  title="Checkout")
        
        # Create new order
        order = Order(
            customer_id=current_user.id,
            total_amount=total,
            shipping_address=shipping_address,
            shipping_city=shipping_city,
            shipping_country=shipping_country,
            shipping_postal_code=shipping_postal_code,
            shipping_fee=0.0,  # Can be calculated based on location
            notes=notes,
            status=OrderStatus.PENDING
        )
        
        # Generate order number
        order.generate_order_number()
        
        db.session.add(order)
        db.session.flush()  # Get order ID without committing
        
        # Add order items
        for item in cart_contents:
            order_item = OrderItem(
                order_id=order.id,
                quantity=item['quantity'],
                price=item['price'],
                item_type=item['type']
            )
            
            if item['type'] == 'beat':
                order_item.beat_id = item['id']
            elif item['type'] == 'merchandise':
                order_item.merchandise_id = item['id']
                # Update merchandise stock
                merch = Merchandise.query.get(item['id'])
                if merch:
                    merch.update_stock(-item['quantity'])
            
            db.session.add(order_item)
        
        # Create transaction record
        transaction = Transaction(
            order_id=order.id,
            transaction_id=str(uuid.uuid4()),
            amount=total,
            currency='USD',
            status=TransactionStatus.PENDING,
            payment_method=PaymentMethod(payment_method)
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        # Clear cart
        session['cart'] = []
        
        # Redirect to payment processing
        return redirect(url_for('payments.process_payment', 
                                transaction_id=transaction.transaction_id))
    
    return render_template('payments/checkout.html',
                          cart_contents=cart_contents,
                          total=total,
                          payment_methods=PaymentMethod,
                          title="Checkout")


@payments_bp.route('/process-payment/<string:transaction_id>')
@login_required
def process_payment(transaction_id):
    """Process payment for a transaction"""
    transaction = Transaction.query.filter_by(transaction_id=transaction_id).first_or_404()
    order = transaction.order
    
    # Ensure user owns this order
    if order.customer_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('main.index'))
    
    # Check if already processed
    if transaction.status != TransactionStatus.PENDING:
        flash('This transaction has already been processed', 'info')
        return redirect(url_for('payments.payment_complete', transaction_id=transaction.transaction_id))
    
    # Determine which payment processor to use
    if transaction.payment_method == PaymentMethod.PAYPAL:
        return render_template('payments/paypal.html',
                              transaction=transaction,
                              order=order,
                              title="PayPal Payment")
    elif transaction.payment_method == PaymentMethod.MPESA:
        return render_template('payments/mpesa.html',
                              transaction=transaction,
                              order=order,
                              title="M-Pesa Payment")
    else:
        flash('Unsupported payment method', 'danger')
        return redirect(url_for('main.index'))


@payments_bp.route('/payment-webhook', methods=['POST'])
def payment_webhook():
    """Webhook for payment processor callbacks"""
    # This would be implemented based on the specific payment processor
    # For demonstration, we'll simulate a successful payment
    
    data = request.json
    transaction_id = data.get('transaction_id')
    status = data.get('status')
    
    if not transaction_id:
        return jsonify({'error': 'Missing transaction ID'}), 400
    
    transaction = Transaction.query.filter_by(transaction_id=transaction_id).first()
    if not transaction:
        return jsonify({'error': 'Transaction not found'}), 404
    
    # Update transaction status
    if status == 'completed':
        transaction.status = TransactionStatus.COMPLETED
        transaction.order.status = OrderStatus.PAID
        transaction.order.paid_at = datetime.utcnow()
        
        # Save payment details
        transaction.set_payment_details(data)
        
        db.session.commit()
        
        # Notify customer
        message = Message(
            subject=f"Order {transaction.order.order_number} Payment Confirmed",
            body=f"Your payment for order {transaction.order.order_number} has been confirmed. Thank you for your purchase!",
            sender_id=1,  # Admin user ID
            recipient_id=transaction.order.customer_id
        )
        db.session.add(message)
        db.session.commit()
        
        return jsonify({'success': True}), 200
    elif status == 'failed':
        transaction.status = TransactionStatus.FAILED
        db.session.commit()
        return jsonify({'success': True}), 200
    else:
        return jsonify({'error': 'Invalid status'}), 400


@payments_bp.route('/payment-complete/<string:transaction_id>')
@login_required
def payment_complete(transaction_id):
    """Payment completion page"""
    transaction = Transaction.query.filter_by(transaction_id=transaction_id).first_or_404()
    order = transaction.order
    
    # Ensure user owns this order
    if order.customer_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('main.index'))
    
    return render_template('payments/payment_complete.html',
                          transaction=transaction,
                          order=order,
                          title="Payment Complete")


@payments_bp.route('/my-orders')
@login_required
def my_orders():
    """View user's orders"""
    page = request.args.get('page', 1, type=int)
    status_filter = request.args.get('status')
    
    query = Order.query.filter_by(customer_id=current_user.id)
    
    if status_filter and status_filter in [status.value for status in OrderStatus]:
        query = query.filter_by(status=OrderStatus(status_filter))
    
    pagination = query.order_by(Order.created_at.desc()).paginate(
        page=page, per_page=10, error_out=False)
    
    orders = pagination.items
    
    return render_template('payments/my_orders.html',
                           orders=orders,
                           pagination=pagination,
                           status_filter=status_filter,
                           statuses=OrderStatus,
                           title="My Orders")


@payments_bp.route('/order/<string:order_number>')
@login_required
def order_detail(order_number):
    """View order details"""
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    
    # Ensure user owns this order
    if order.customer_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('main.index'))
    
    return render_template('payments/order_detail.html',
                           order=order,
                           title=f"Order: {order.order_number}")


@payments_bp.route('/pay-session/<int:session_id>', methods=['GET', 'POST'])
@login_required
def pay_session(session_id):
    """Pay for a session booking"""
    session_booking = SessionBooking.query.get_or_404(session_id)
    
    # Ensure user owns this session
    if session_booking.artist_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('main.index'))
    
    # Check if already paid
    if session_booking.is_paid:
        flash('This session has already been paid for', 'info')
        return redirect(url_for('artist.session_detail', session_id=session_id))
    
    if request.method == 'POST':
        payment_method = request.form.get('payment_method')
        
        if not payment_method:
            flash('Payment method is required', 'danger')
            return redirect(url_for('payments.pay_session', session_id=session_id))
        
        # Create transaction record
        transaction = Transaction(
            amount=session_booking.price,
            currency='USD',
            status=TransactionStatus.PENDING,
            payment_method=PaymentMethod(payment_method),
            transaction_id=str(uuid.uuid4()),
            payment_details=json.dumps({
                'session_id': session_id,
                'type': 'session_payment'
            })
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        # Redirect to payment processing
        return redirect(url_for('payments.process_session_payment', 
                                transaction_id=transaction.transaction_id))
    
    return render_template('payments/pay_session.html',
                          session=session_booking,
                          payment_methods=PaymentMethod,
                          title="Pay for Session")


@payments_bp.route('/process-session-payment/<string:transaction_id>')
@login_required
def process_session_payment(transaction_id):
    """Process payment for a session"""
    transaction = Transaction.query.filter_by(transaction_id=transaction_id).first_or_404()
    
    # Get session ID from payment details
    payment_details = transaction.get_payment_details()
    session_id = payment_details.get('session_id')
    
    if not session_id:
        flash('Invalid transaction', 'danger')
        return redirect(url_for('main.index'))
    
    session_booking = SessionBooking.query.get_or_404(session_id)
    
    # Ensure user owns this session
    if session_booking.artist_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('main.index'))
    
    # Check if already processed
    if transaction.status != TransactionStatus.PENDING:
        flash('This transaction has already been processed', 'info')
        return redirect(url_for('payments.session_payment_complete', transaction_id=transaction.transaction_id))
    
    # Determine which payment processor to use
    if transaction.payment_method == PaymentMethod.PAYPAL:
        return render_template('payments/paypal_session.html',
                              transaction=transaction,
                              session=session_booking,
                              title="PayPal Payment")
    elif transaction.payment_method == PaymentMethod.MPESA:
        return render_template('payments/mpesa_session.html',
                              transaction=transaction,
                              session=session_booking,
                              title="M-Pesa Payment")
    else:
        flash('Unsupported payment method', 'danger')
        return redirect(url_for('main.index'))


@payments_bp.route('/session-payment-webhook', methods=['POST'])
def session_payment_webhook():
    """Webhook for session payment processor callbacks"""
    # This would be implemented based on the specific payment processor
    # For demonstration, we'll simulate a successful payment
    
    data = request.json
    transaction_id = data.get('transaction_id')
    status = data.get('status')
    
    if not transaction_id:
        return jsonify({'error': 'Missing transaction ID'}), 400
    
    transaction = Transaction.query.filter_by(transaction_id=transaction_id).first()
    if not transaction:
        return jsonify({'error': 'Transaction not found'}), 404
    
    # Get session ID from payment details
    payment_details = transaction.get_payment_details()
    session_id = payment_details.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'Invalid transaction'}), 400
    
    session_booking = SessionBooking.query.get(session_id)
    if not session_booking:
        return jsonify({'error': 'Session not found'}), 404
    
    # Update transaction status
    if status == 'completed':
        transaction.status = TransactionStatus.COMPLETED
        session_booking.is_paid = True
        
        # Save payment details
        transaction.set_payment_details(data)
        
        db.session.commit()
        
        # Notify artist and producer
        artist = User.query.get(session_booking.artist_id)
        producer = User.query.get(session_booking.producer_id)
        
        # Message to artist
        artist_message = Message(
            subject=f"Session Payment Confirmed",
            body=f"Your payment for the session on {session_booking.session_date} has been confirmed.",
            sender_id=1,  # Admin user ID
            recipient_id=artist.id
        )
        db.session.add(artist_message)
        
        # Message to producer
        producer_message = Message(
            subject=f"Session Payment Received",
            body=f"Payment has been received for the session with {artist.get_full_name()} on {session_booking.session_date}.",
            sender_id=1,  # Admin user ID
            recipient_id=producer.id
        )
        db.session.add(producer_message)
        
        db.session.commit()
        
        return jsonify({'success': True}), 200
    elif status == 'failed':
        transaction.status = TransactionStatus.FAILED
        db.session.commit()
        return jsonify({'success': True}), 200
    else:
        return jsonify({'error': 'Invalid status'}), 400


@payments_bp.route('/session-payment-complete/<string:transaction_id>')
@login_required
def session_payment_complete(transaction_id):
    """Session payment completion page"""
    transaction = Transaction.query.filter_by(transaction_id=transaction_id).first_or_404()
    
    # Get session ID from payment details
    payment_details = transaction.get_payment_details()
    session_id = payment_details.get('session_id')
    
    if not session_id:
        flash('Invalid transaction', 'danger')
        return redirect(url_for('main.index'))
    
    session_booking = SessionBooking.query.get_or_404(session_id)
    
    # Ensure user owns this session
    if session_booking.artist_id != current_user.id:
        flash('Access denied', 'danger')
        return redirect(url_for('main.index'))
    
    return render_template('payments/session_payment_complete.html',
                          transaction=transaction,
                          session=session_booking,
                          title="Payment Complete")