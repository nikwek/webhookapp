# app/models/portfolio.py
from app import db
from datetime import datetime, timezone

class Portfolio(db.Model):
    __tablename__ = 'portfolios'
    
    id = db.Column(db.Integer, primary_key=True)
    portfolio_id = db.Column(db.String(100), nullable=False)  # Coinbase's portfolio ID
    name = db.Column(db.String(100), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    exchange = db.Column(db.String(50), default='coinbase', nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    # Add the relationship
    user = db.relationship('User', backref=db.backref('portfolios', lazy=True))
    
    def __init__(self, portfolio_id, name, user_id, exchange='coinbase'):
        self.portfolio_id = portfolio_id
        self.name = name
        self.user_id = user_id
        self.exchange = exchange

    def is_connected(self):
        """Check if portfolio has any active automation connections"""
        return bool(ExchangeCredentials.query.filter_by(
            portfolio_id=self.id,
            exchange='coinbase'
        ).first())