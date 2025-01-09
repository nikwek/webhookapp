# app/routes/automation.py
@bp.route('/create-automation', methods=['POST'])
def create_automation():
    if not session.get('user_id'):
        return jsonify({"error": "Unauthorized"}), 403
    
    name = request.json.get('name', 'Unnamed Automation')
        
    automation = Automation(
        automation_id=Automation.generate_automation_id(),
        name=name,
        user_id=session['user_id']
    )
    db.session.add(automation)
    db.session.commit()

    template = {
        "automation_id": automation.automation_id,
        "ticker": "{{ticker}}",
        "action": "{{strategy.order.action}}",
        "timestamp": "{{time}}"
    }

    return jsonify({
        "automation_id": automation.automation_id,
        "webhook_url": f"{request.url_root}webhook",
        "template": template
    })