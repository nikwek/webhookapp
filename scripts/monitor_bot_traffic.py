#!/usr/bin/env python3
"""Monitor bot traffic to the registration endpoint via nginx logs."""

import re
import subprocess
from collections import defaultdict
from datetime import datetime

def parse_nginx_log_line(line):
    """Parse nginx log line and extract relevant information."""
    # Nginx log format: IP - - [timestamp] "METHOD /path HTTP/1.1" status size "referer" "user-agent"
    pattern = r'(\S+) - - \[(.*?)\] "(\S+) (\S+) \S+" (\d+) \S+ "([^"]*)" "([^"]*)"'
    match = re.match(pattern, line)
    
    if match:
        return {
            'ip': match.group(1),
            'timestamp': match.group(2),
            'method': match.group(3),
            'path': match.group(4),
            'status': int(match.group(5)),
            'referer': match.group(6),
            'user_agent': match.group(7)
        }
    return None

def is_likely_bot(user_agent):
    """Detect if user agent is likely a bot."""
    bot_indicators = [
        'bot', 'crawler', 'spider', 'scraper', 'curl', 'wget', 'python',
        'requests', 'http', 'scanner', 'monitor', 'check', 'test'
    ]
    user_agent_lower = user_agent.lower()
    return any(indicator in user_agent_lower for indicator in bot_indicators)

def monitor_register_traffic():
    """Monitor traffic to /register endpoint."""
    print("Monitoring /register traffic from nginx logs...")
    print("=" * 60)
    
    # Check if nginx log file exists
    import os
    log_file = '/var/log/nginx/access.log'
    if not os.path.exists(log_file):
        print("❌ Nginx access log not found at /var/log/nginx/access.log")
        print("This script should be run on the production server (Raspberry Pi) where nginx is running.")
        print("\nTo run on your Raspberry Pi:")
        print("1. SSH into your Pi: ssh nik@your-pi-ip")
        print("2. Navigate to the app directory: cd /home/nik/webhookapp")
        print("3. Run: python3 scripts/monitor_bot_traffic.py")
        print("\n📊 Alternative: Check Google Analytics for bot traffic:")
        print("- Events → 'registration_attempt' (blocked attempts)")
        print("- Events → 'registration_page_visit' (page visits)")
        print("- Compare 'form_start' vs 'form_submit' for bot behavior")
        return
    
    try:
        # Get recent nginx access logs
        result = subprocess.run(
            ['sudo', 'tail', '-n', '1000', log_file],
            capture_output=True, text=True, check=True
        )
        
        register_requests = []
        bot_requests = []
        ip_counts = defaultdict(int)
        
        for line in result.stdout.strip().split('\n'):
            if '/register' in line:
                parsed = parse_nginx_log_line(line)
                if parsed:
                    register_requests.append(parsed)
                    ip_counts[parsed['ip']] += 1
                    
                    if is_likely_bot(parsed['user_agent']):
                        bot_requests.append(parsed)
        
        print(f"Total /register requests: {len(register_requests)}")
        print(f"Likely bot requests: {len(bot_requests)}")
        print()
        
        if register_requests:
            print("Recent /register requests:")
            print("-" * 60)
            for req in register_requests[-10:]:  # Show last 10
                bot_flag = "🤖" if is_likely_bot(req['user_agent']) else "👤"
                print(f"{bot_flag} {req['timestamp']} | {req['ip']} | {req['method']} | {req['status']}")
                print(f"   UA: {req['user_agent'][:80]}...")
                print()
        
        if len(ip_counts) > 1:
            print("Top IPs accessing /register:")
            print("-" * 30)
            for ip, count in sorted(ip_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
                print(f"{ip}: {count} requests")
    
    except subprocess.CalledProcessError as e:
        print(f"Error accessing nginx logs: {e}")
        print("Make sure you have sudo access to /var/log/nginx/access.log")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    monitor_register_traffic()
