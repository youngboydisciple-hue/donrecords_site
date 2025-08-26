from datetime import datetime
from flask import current_app
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db, login_manager
import enum
import os
import json


class UserRole(enum.Enum):
    ADMIN = 'admin'
    PRODUCER = 'producer'
    ARTIST = 'artist'
    USER = 'user'  # Regular user/fan


class OrderStatus(enum.Enum):
    PENDING = 'pending'
    PAID = 'paid'
    SHIPPED = 'shipped'
    DELIVERED = 'delivered'
    CANCELLED = 'cancelled'


class TransactionStatus(enum.Enum):
    PENDING = 'pending'
    COMPLETED = 'completed'
    FAILED = 'failed'
    REFUNDED = 'refunded'


class PaymentMethod(enum.Enum):
    PAYPAL = 'paypal'
    MPESA = 'mpesa'


class SessionStatus(enum.Enum):
    REQUESTED = 'requested'
    CONFIRMED = 'confirmed'
    COMPLETED = 'completed'
    CANCELLED = 'cancelled'


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    role = db.Column(db.Enum(UserRole), default=UserRole.USER)
    is_active = db.Column(db.Boolean, default=False)  # For email verification
    is_approved = db.Column(db.Boolean, default=False)  # For admin approval
    
    # Profile information
    first_name = db.Column(db.String(64))
    last_name = db.Column(db.String(64))
    bio = db.Column(db.Text)
    profile_image = db.Column(db.String(255))
    phone_number = db.Column(db.String(20))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_login = db.Column(db.DateTime)
    
  # Relationships
    beats = db.relationship('Beat', backref='producer', lazy='dynamic')
    merchandise = db.relationship('Merchandise', backref='seller', lazy='dynamic')
    blog_posts = db.relationship('BlogPost', backref='author', lazy='dynamic')
    orders = db.relationship('Order', backref='customer', lazy='dynamic')
    sent_messages = db.relationship('Message', foreign_keys='Message.sender_id', backref='sender', lazy='dynamic')
    received_messages = db.relationship('Message', foreign_keys='Message.recipient_id', backref='recipient', lazy='dynamic')
    
    #specify which foreign key to use
    artist_sessions = db.relationship('SessionBooking', 
                                    foreign_keys='SessionBooking.artist_id',
                                    backref='artist', 
                                    lazy='dynamic')
    
    producer_sessions = db.relationship('SessionBooking',
                                      foreign_keys='SessionBooking.producer_id', 
                                      backref='producer',
                                      lazy='dynamic')
    
    @property
    def password(self):
        raise AttributeError('password is not a readable attribute')
    
    @password.setter
    def password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def verify_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_full_name(self):
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        return self.username
    
    def __repr__(self):
        return f'<User {self.username}> - {self.role.value}'


class Beat(db.Model):
    __tablename__ = 'beats'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    audio_file = db.Column(db.String(255), nullable=False)  # Path to audio file
    cover_image = db.Column(db.String(255))  # Path to cover image
    bpm = db.Column(db.Integer)  # Beats per minute
    key = db.Column(db.String(10))  # Musical key
    genre = db.Column(db.String(50))
    tags = db.Column(db.String(255))  # Comma-separated tags
    is_featured = db.Column(db.Boolean, default=False)
    is_published = db.Column(db.Boolean, default=True)
    play_count = db.Column(db.Integer, default=0)
    download_count = db.Column(db.Integer, default=0)
    
    # Foreign keys
    producer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    order_items = db.relationship('OrderItem', backref='beat', lazy='dynamic')
    
    def get_tags_list(self):
        return [tag.strip() for tag in self.tags.split(',')] if self.tags else []
    
    def increment_play_count(self):
        self.play_count += 1
        db.session.commit()
    
    def increment_download_count(self):
        self.download_count += 1
        db.session.commit()
    
    def __repr__(self):
        return f'<Beat {self.title}> by {self.producer.username}'


class Merchandise(db.Model):
    __tablename__ = 'merchandise'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(255))  # Path to image
    category = db.Column(db.String(50))
    stock_quantity = db.Column(db.Integer, default=0)
    is_featured = db.Column(db.Boolean, default=False)
    is_published = db.Column(db.Boolean, default=True)
    
    # Foreign keys
    seller_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    order_items = db.relationship('OrderItem', backref='merchandise', lazy='dynamic')
    
    def update_stock(self, quantity_change):
        self.stock_quantity += quantity_change
        db.session.commit()
    
    def __repr__(self):
        return f'<Merchandise {self.name}> - ${self.price}'


class Order(db.Model):
    __tablename__ = 'orders'
    
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(20), unique=True, index=True)
    status = db.Column(db.Enum(OrderStatus), default=OrderStatus.PENDING)
    total_amount = db.Column(db.Float, nullable=False)
    shipping_address = db.Column(db.Text)
    shipping_city = db.Column(db.String(100))
    shipping_country = db.Column(db.String(100))
    shipping_postal_code = db.Column(db.String(20))
    shipping_fee = db.Column(db.Float, default=0.0)
    notes = db.Column(db.Text)
    
    # Foreign keys
    customer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    paid_at = db.Column(db.DateTime)
    shipped_at = db.Column(db.DateTime)
    delivered_at = db.Column(db.DateTime)
    
    # Relationships
    items = db.relationship('OrderItem', backref='order', lazy='dynamic', cascade='all, delete-orphan')
    transactions = db.relationship('Transaction', backref='order', lazy='dynamic')
    
    def generate_order_number(self):
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        random_suffix = os.urandom(3).hex()
        self.order_number = f"DR{timestamp}{random_suffix}"
    
    def calculate_total(self):
        items_total = sum(item.subtotal for item in self.items)
        self.total_amount = items_total + self.shipping_fee
        db.session.commit()
    
    def __repr__(self):
        return f'<Order {self.order_number}> - {self.status.value}'


class OrderItem(db.Model):
    __tablename__ = 'order_items'
    
    id = db.Column(db.Integer, primary_key=True)
    quantity = db.Column(db.Integer, default=1)
    price = db.Column(db.Float, nullable=False)  # Price at time of purchase
    item_type = db.Column(db.String(20))  # 'beat' or 'merchandise'
    
    # Foreign keys
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    beat_id = db.Column(db.Integer, db.ForeignKey('beats.id'), nullable=True)
    merchandise_id = db.Column(db.Integer, db.ForeignKey('merchandise.id'), nullable=True)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @property
    def subtotal(self):
        return self.price * self.quantity
    
    def __repr__(self):
        if self.item_type == 'beat':
            return f'<OrderItem: Beat {self.beat.title}> x{self.quantity}'
        else:
            return f'<OrderItem: Merch {self.merchandise.name}> x{self.quantity}'


class Transaction(db.Model):
    __tablename__ = 'transactions'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(db.String(100), unique=True, index=True)  # External transaction ID
    amount = db.Column(db.Float, nullable=False)
    currency = db.Column(db.String(3), default='USD')
    status = db.Column(db.Enum(TransactionStatus), default=TransactionStatus.PENDING)
    payment_method = db.Column(db.Enum(PaymentMethod))
    payment_details = db.Column(db.Text)  # JSON string with payment details
    
    # Foreign keys
    order_id = db.Column(db.Integer, db.ForeignKey('orders.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_payment_details(self, details_dict):
        self.payment_details = json.dumps(details_dict)
    
    def get_payment_details(self):
        if self.payment_details:
            return json.loads(self.payment_details)
        return {}
    
    def __repr__(self):
        return f'<Transaction {self.transaction_id}> - {self.status.value}'


class BlogPost(db.Model):
    __tablename__ = 'blog_posts'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(250), unique=True, index=True)
    content = db.Column(db.Text, nullable=False)
    excerpt = db.Column(db.Text)
    featured_image = db.Column(db.String(255))
    is_published = db.Column(db.Boolean, default=True)
    is_featured = db.Column(db.Boolean, default=False)
    view_count = db.Column(db.Integer, default=0)
    
    # Foreign keys
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    published_at = db.Column(db.DateTime)
    
    def increment_view_count(self):
        self.view_count += 1
        db.session.commit()
    
    def __repr__(self):
        return f'<BlogPost {self.title}> by {self.author.username}'


class SessionBooking(db.Model):
    __tablename__ = 'session_bookings'
    
    id = db.Column(db.Integer, primary_key=True)
    session_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    purpose = db.Column(db.Text)
    status = db.Column(db.Enum(SessionStatus), default=SessionStatus.REQUESTED)
    price = db.Column(db.Float, nullable=False)
    is_paid = db.Column(db.Boolean, default=False)
    notes = db.Column(db.Text)
    
    # Foreign keys
    artist_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    producer_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<SessionBooking {self.session_date}> - {self.status.value}'


class Message(db.Model):
    __tablename__ = 'messages'
    
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100))
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    
    # Foreign keys
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    recipient_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read_at = db.Column(db.DateTime)
    
    def mark_as_read(self):
        self.is_read = True
        self.read_at = datetime.utcnow()
        db.session.commit()
    
    def __repr__(self):
        return f'<Message {self.subject}> from {self.sender.username} to {self.recipient.username}'