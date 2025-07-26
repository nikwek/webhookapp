"""Debug routes for testing template loading."""

from flask import Blueprint, current_app, render_template_string
from flask_security import auth_required

template_debug = Blueprint('template_debug', __name__)

@template_debug.route('/debug/template-test')
@auth_required()
def test_template_loading():
    """Test if our custom email templates are being loaded correctly."""
    
    try:
        # Try to render our custom confirmation template
        from flask import render_template
        
        # Test context similar to what Flask-Security-Too would use
        test_context = {
            'user': {'email': 'test@example.com'},
            'confirmation_link': 'http://example.com/confirm/test-token'
        }
        
        # Try to render the HTML template
        html_content = render_template('security/email/confirmation_instructions.html', **test_context)
        
        # Try to render the text template  
        text_content = render_template('security/email/confirmation_instructions.txt', **test_context)
        
        return f"""
        <h2>Template Loading Test</h2>
        <h3>HTML Template Content (first 500 chars):</h3>
        <pre>{html_content[:500]}...</pre>
        
        <h3>Text Template Content (first 500 chars):</h3>
        <pre>{text_content[:500]}...</pre>
        
        <h3>Template Loader Info:</h3>
        <pre>Template folders: {current_app.jinja_env.loader.searchpath if hasattr(current_app.jinja_env.loader, 'searchpath') else 'Not available'}</pre>
        """
        
    except Exception as e:
        return f"<h2>Template Loading Error:</h2><pre>{str(e)}</pre>"
