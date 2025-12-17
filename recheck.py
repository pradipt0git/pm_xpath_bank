from flask import Blueprint, render_template, request, jsonify
import subprocess
import sys
import os
import time
import signal
import csv
from datetime import datetime

recheck_bp = Blueprint('recheck', __name__)

# Global variable to store the recheck process
recheck_process = None

@recheck_bp.route('/recheck', methods=['GET'])
def recheck_page():
    """Render the recheck page"""
    return render_template('recheck.html')

@recheck_bp.route('/launch_recheck', methods=['POST'])
def launch_recheck():
    """Launch Selenium browser with the first page URL"""
    global recheck_process
    
    try:
        data = request.json
        url = data.get('url')
        
        if not url:
            return jsonify({'status': 'error', 'message': 'URL is required'}), 400
        
        # Update config.json with the URL
        config_path = 'config.json'
        import json
        config = {'load_url': url}
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=4)
        
        # Start main.py with the URL in recheck mode
        python_path = '.venv/Scripts/python.exe' if os.path.exists('.venv/Scripts/python.exe') else sys.executable
        recheck_process = subprocess.Popen(
            [python_path, 'main.py', '--url', url, '--recheck'],
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
        )
        
        return jsonify({'status': 'success', 'message': f'Browser launched with URL: {url}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@recheck_bp.route('/stop_recheck', methods=['POST'])
def stop_recheck():
    """Stop the recheck process by sending Ctrl+C twice"""
    global recheck_process
    
    try:
        if not recheck_process or recheck_process.poll() is not None:
            return jsonify({'status': 'error', 'message': 'No recheck process running'}), 400
        
        # Create stop file flag
        stop_file = 'stop_capture.flag'
        with open(stop_file, 'w') as f:
            f.write('stop')
        
        # Wait for graceful shutdown
        try:
            recheck_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Force terminate if graceful shutdown fails
            if sys.platform == 'win32':
                # On Windows, use taskkill to terminate process tree
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(recheck_process.pid)], 
                             capture_output=True)
            else:
                recheck_process.kill()
            recheck_process.wait()
        
        # Clean up stop file
        if os.path.exists(stop_file):
            os.remove(stop_file)
        
        recheck_process = None
        return jsonify({'status': 'success', 'message': 'Recheck stopped'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@recheck_bp.route('/get_current_url', methods=['GET'])
def get_current_url():
    """Get the current URL from the Selenium browser"""
    try:
        url_file = 'current_url.txt'
        if os.path.exists(url_file):
            with open(url_file, 'r') as f:
                current_url = f.read().strip()
            return jsonify({'status': 'success', 'url': current_url})
        else:
            return jsonify({'status': 'error', 'message': 'No active browser session'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@recheck_bp.route('/validate_xpaths', methods=['POST'])
def validate_xpaths():
    """Validate if XPaths exist in the current page and log to CSV report"""
    try:
        data = request.json
        xpaths_data = data.get('xpaths_data', [])  # List of {xpath, name, page_url}
        
        if not xpaths_data:
            return jsonify({'status': 'error', 'message': 'No xpaths provided'}), 400
        
        # Extract just the xpaths for validation
        xpaths = [item['xpath'] for item in xpaths_data]
        
        # Create a validation request file
        validation_file = 'xpath_validation_request.json'
        result_file = 'xpath_validation_result.json'
        
        # Clean up old result file
        if os.path.exists(result_file):
            os.remove(result_file)
        
        # Write validation request
        import json
        with open(validation_file, 'w') as f:
            json.dump({'xpaths': xpaths}, f)
        
        # Wait for result file to be created (with timeout)
        timeout = 5
        start_time = time.time()
        while not os.path.exists(result_file):
            if time.time() - start_time > timeout:
                return jsonify({'status': 'error', 'message': 'Validation timeout'}), 500
            time.sleep(0.1)
        
        # Read result
        with open(result_file, 'r') as f:
            result = json.load(f)
        
        # Clean up files
        if os.path.exists(validation_file):
            os.remove(validation_file)
        if os.path.exists(result_file):
            os.remove(result_file)
        
        # Write to CSV report
        write_validation_report(xpaths_data, result)
        
        return jsonify({'status': 'success', 'results': result})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

def write_validation_report(xpaths_data, results):
    """Write validation results to date-wise CSV report"""
    try:
        # Create reports folder if not exists
        reports_folder = 'reports'
        if not os.path.exists(reports_folder):
            os.makedirs(reports_folder)
        
        # Get current date for filename
        current_date = datetime.now().strftime('%Y-%m-%d')
        csv_filename = os.path.join(reports_folder, f'{current_date}.csv')
        
        # Check if file exists to determine if we need headers
        file_exists = os.path.exists(csv_filename)
        
        # Open CSV file in append mode
        with open(csv_filename, 'a', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['page_url', 'element_name', 'element_xpath', 'is_exist', 'checked_date_time']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            # Write header if file is new
            if not file_exists:
                writer.writeheader()
            
            # Get current timestamp
            checked_datetime = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Write each validation result
            for item in xpaths_data:
                xpath = item['xpath']
                is_exist = 'yes' if results.get(xpath, False) else 'no'
                
                writer.writerow({
                    'page_url': item.get('page_url', ''),
                    'element_name': item.get('name', ''),
                    'element_xpath': xpath,
                    'is_exist': is_exist,
                    'checked_date_time': checked_datetime
                })
    except Exception as e:
        print(f"Error writing validation report: {e}")
