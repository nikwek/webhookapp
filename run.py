# run.py
from app import create_app

app = create_app()

if __name__ == '__main__':
    ssl_context = None
    if app.config.get('SSL_ENABLED', False):
        ssl_context = (app.config['SSL_CERT'], app.config['SSL_KEY'])
    
    app.run(
        host='0.0.0.0', 
        port=5001, 
        ssl_context=ssl_context,
        debug=app.config.get('DEBUG', False)
    )
