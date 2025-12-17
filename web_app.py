from flask import Flask, request, render_template, jsonify, send_file
import subprocess
import json
import os
import signal
import sys
from collections import OrderedDict
import csv
import io
from recheck import recheck_bp

app = Flask(__name__)

# Register recheck blueprint
app.register_blueprint(recheck_bp)

# Global variable to store the process
capture_process = None

@app.route('/', methods=['GET'])
def index():
    config_path = 'config.json'
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            config = json.load(f)
        default_url = config.get('load_url', 'https://www.google.com')
    else:
        default_url = 'https://www.google.com'
    return render_template('index.html', default_url=default_url)

@app.route('/start_capture', methods=['POST'])
def start_capture():
    global capture_process
    
    if capture_process and capture_process.poll() is None:
        return jsonify({'status': 'error', 'message': 'Capture already running'}), 400
    
    url = request.json.get('url')
    if not url:
        return jsonify({'status': 'error', 'message': 'URL is required'}), 400
    
    # Update config.json with new URL
    config_path = 'config.json'
    config = {'load_url': url}
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=4)
    
    # Start main.py with the URL
    try:
        python_path = '.venv/Scripts/python.exe' if os.path.exists('.venv/Scripts/python.exe') else sys.executable
        capture_process = subprocess.Popen(
            [python_path, 'main.py', '--url', url],
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
        )
        return jsonify({'status': 'success', 'message': f'Capture started for {url}'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/stop_capture', methods=['POST'])
def stop_capture():
    global capture_process
    
    if not capture_process or capture_process.poll() is not None:
        return jsonify({'status': 'error', 'message': 'No capture process running'}), 400
    
    try:
        # Create stop file flag
        stop_file = 'stop_capture.flag'
        with open(stop_file, 'w') as f:
            f.write('stop')
        
        # Wait for graceful shutdown
        try:
            capture_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Force terminate if graceful shutdown fails
            if sys.platform == 'win32':
                # On Windows, use taskkill to terminate process tree
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(capture_process.pid)], 
                             capture_output=True)
            else:
                capture_process.kill()
            capture_process.wait()
        
        # Clean up stop file
        if os.path.exists(stop_file):
            os.remove(stop_file)
        
        capture_process = None
        return jsonify({'status': 'success', 'message': 'Capture stopped'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/status', methods=['GET'])
def get_status():
    global capture_process
    is_running = capture_process is not None and capture_process.poll() is None
    return jsonify({'running': is_running})

@app.route('/list_json_files', methods=['GET'])
def list_json_files():
    output_folder = 'output_folder'
    if not os.path.exists(output_folder):
        return jsonify({'files': []})
    
    files = [f for f in os.listdir(output_folder) if f.endswith('.json')]
    return jsonify({'files': sorted(files)})

@app.route('/load_json/<filename>', methods=['GET'])
def load_json(filename):
    filepath = os.path.join('output_folder', filename)
    if not os.path.exists(filepath):
        return jsonify({'status': 'error', 'message': 'File not found'}), 404
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            # Preserve order by using object_pairs_hook
            data = json.load(f, object_pairs_hook=OrderedDict)
        return jsonify({'status': 'success', 'data': data})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/update_xpath', methods=['POST'])
def update_xpath():
    try:
        data = request.json
        filename = data.get('filename')
        page_url = data.get('page_url')
        xpath_index = data.get('xpath_index')
        name = data.get('name')
        final_xpath = data.get('final_xpath')
        
        filepath = os.path.join('output_folder', filename)
        if not os.path.exists(filepath):
            return jsonify({'status': 'error', 'message': 'File not found'}), 404
        
        with open(filepath, 'r') as f:
            json_data = json.load(f)
        
        if page_url not in json_data:
            return jsonify({'status': 'error', 'message': 'Page URL not found'}), 404
        
        if xpath_index >= len(json_data[page_url]['xpaths']):
            return jsonify({'status': 'error', 'message': 'XPath index out of range'}), 404
        
        json_data[page_url]['xpaths'][xpath_index]['name'] = name
        json_data[page_url]['xpaths'][xpath_index]['final_xpath'] = final_xpath
        
        with open(filepath, 'w') as f:
            json.dump(json_data, f, indent=4)
        
        return jsonify({'status': 'success', 'message': 'XPath updated successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/delete_xpath', methods=['POST'])
def delete_xpath():
    try:
        data = request.json
        filename = data.get('filename')
        page_url = data.get('page_url')
        xpath_index = data.get('xpath_index')
        
        filepath = os.path.join('output_folder', filename)
        if not os.path.exists(filepath):
            return jsonify({'status': 'error', 'message': 'File not found'}), 404
        
        with open(filepath, 'r') as f:
            json_data = json.load(f)
        
        if page_url not in json_data:
            return jsonify({'status': 'error', 'message': 'Page URL not found'}), 404
        
        if xpath_index >= len(json_data[page_url]['xpaths']):
            return jsonify({'status': 'error', 'message': 'XPath index out of range'}), 404
        
        # Delete the xpath at the specified index
        del json_data[page_url]['xpaths'][xpath_index]
        
        # If no xpaths left for this page, remove the parent page entry
        if len(json_data[page_url]['xpaths']) == 0:
            del json_data[page_url]
        
        with open(filepath, 'w') as f:
            json.dump(json_data, f, indent=4)
        
        return jsonify({'status': 'success', 'message': 'XPath deleted successfully'})
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/download_csv/<filename>', methods=['GET'])
def download_csv(filename):
    filepath = os.path.join('output_folder', filename)
    if not os.path.exists(filepath):
        return jsonify({'status': 'error', 'message': 'File not found'}), 404
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            json_data = json.load(f, object_pairs_hook=OrderedDict)
        
        # Create CSV in memory
        output = io.StringIO()
        csv_writer = csv.writer(output)
        
        # Write header
        csv_writer.writerow(['Page URL', 'Page Name', 'Element Name', 'Final XPath', 'Created On'])
        
        # Write data rows
        for page_url, page_data in json_data.items():
            page_name = page_data.get('page_name', '')
            if page_data.get('xpaths'):
                for xpath_entry in page_data['xpaths']:
                    csv_writer.writerow([
                        page_url,
                        page_name,
                        xpath_entry.get('name', ''),
                        xpath_entry.get('final_xpath', ''),
                        xpath_entry.get('created_on', '')
                    ])
        
        # Prepare response
        output.seek(0)
        csv_filename = filename.replace('.json', '.csv')
        
        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=csv_filename
        )
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)