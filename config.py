# config.py
import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(24)
    SQLALCHEMY_DATABASE_URI = f'sqlite:///{os.path.join(basedir, "var", "app-instance", "webhook.db")}'
    SQLALCHEMY_TRACK_MODIFICATIONS = False