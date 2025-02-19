# run.py
from app import create_app

app = create_app()

@app.after_request
def after_request(response):
    response.headers["ngrok-skip-browser-warning"] = "true"
    return response

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=True)