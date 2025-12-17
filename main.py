import json
import os
import ssl
from urllib.parse import urlparse
from selenium import webdriver
from selenium.webdriver.edge.service import Service
from selenium.webdriver.edge.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import websockets
import asyncio
import threading
import signal
import os
import sys
from datetime import datetime

stop_flag = False
recheck_mode = False

injected_urls = set()

def signal_handler(sig, frame):
    global stop_flag
    print("Signal received", flush=True)
    stop_flag = True

signal.signal(signal.SIGINT, signal_handler)

import argparse

def get_domain(url):
    parsed = urlparse(url)
    return parsed.netloc

def get_xpath(element):
    # Get relative xpath
    relative_xpath = element.get_attribute('data-relative-xpath') or ''
    # Get full xpath
    full_xpath = element.get_attribute('data-full-xpath') or ''
    # Get css selector
    css_selector = element.get_attribute('data-css-selector') or ''
    return {
        'relative_xpath': relative_xpath,
        'full_xpath': full_xpath,
        'css_selector': css_selector
    }

def get_final_xpath(visual):
    for key in ['tag_text', 'tag_contains', 'text', 'placeholder', 'value', 'accessibility', 'name', 'href', 'src', 'alt', 'title']:
        if visual.get(key):
            return visual[key]
    return ''

async def ws_handler(websocket):
    global data, output_file, check_event, stop_event
    try:
        async for message in websocket:
            click_data = json.loads(message)
            page_url = click_data.get('page_url')
            page_name = click_data.get('page_name')
            page_key = page_url
            if page_key not in data:
                # Calculate next display_order
                max_order = 0
                for page_data in data.values():
                    if 'display_order' in page_data:
                        max_order = max(max_order, page_data['display_order'])
                
                data[page_key] = {
                    'page_url': page_url,
                    'page_full_url': page_url,
                    'page_name': page_name,
                    'display_order': max_order + 1,
                    'xpaths': []
                }
            xpath_entry = {
                'name': click_data['name'],
                'visual_xpath': click_data['visual_xpath'],
                'relative_xpath': click_data['relative_xpath'],
                'full_xpath': click_data['full_xpath'],
                'css_selector': click_data['css_selector'],
                'custom_xpath': '',
                'final_xpath': get_final_xpath(click_data['visual_xpath']),
                'created_on': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            if not any(entry.get('final_xpath') == xpath_entry['final_xpath'] for entry in data[page_key]['xpaths']):
                data[page_key]['xpaths'].append(xpath_entry)
                with open(output_file, 'w') as f:
                    json.dump(data, f, indent=4)
                print(f"Captured xpath for element: {click_data['name']} on {page_name}")
                check_event.set()  # Trigger monitoring
    except websockets.exceptions.ConnectionClosed:
        pass  # Expected when browser closes
    except Exception as e:
        print(f"WebSocket error: {e}")

async def start_ws_server():
    global stop_event
    print("Starting WebSocket server", flush=True)
    ssl_context = None
    if os.path.exists('cert.pem') and os.path.exists('key.pem'):
        try:
            ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            ssl_context.load_cert_chain('cert.pem', 'key.pem')
            print("Using SSL for WebSocket", flush=True)
        except Exception as e:
            print(f"Failed to load SSL cert: {e}, using plain WebSocket", flush=True)
            ssl_context = None
    else:
        print("SSL cert not found, using plain WebSocket", flush=True)
    server = await websockets.serve(ws_handler, "localhost", 8765, ssl=ssl_context)
    print("WebSocket server started", flush=True)
    while not stop_event.is_set():
        await asyncio.sleep(0.1)
    print("Stop event received, closing server", flush=True)
    server.close()
    print("Server closed", flush=True)

def start_ws_server_thread():
    asyncio.run(start_ws_server())

def monitor_url_thread(driver, stop_event):
    """Monitor current URL and write to file for recheck page synchronization"""
    url_file = 'current_url.txt'
    while not stop_event.is_set():
        try:
            current_url = driver.current_url
            with open(url_file, 'w') as f:
                f.write(current_url)
        except:
            pass  # Ignore errors if driver is closed
        time.sleep(0.5)  # Update every 500ms
    # Clean up file on exit
    if os.path.exists(url_file):
        os.remove(url_file)

def validate_xpaths_thread(driver, stop_event):
    """Monitor for XPath validation requests and validate them"""
    request_file = 'xpath_validation_request.json'
    result_file = 'xpath_validation_result.json'
    
    while not stop_event.is_set():
        try:
            if os.path.exists(request_file):
                # Read validation request
                with open(request_file, 'r') as f:
                    request_data = json.load(f)
                
                xpaths = request_data.get('xpaths', [])
                results = {}
                
                # Validate each XPath
                for xpath in xpaths:
                    try:
                        elements = driver.find_elements(By.XPATH, xpath)
                        results[xpath] = len(elements) > 0
                    except:
                        results[xpath] = False
                
                # Write results
                with open(result_file, 'w') as f:
                    json.dump(results, f)
                
                # Remove request file
                os.remove(request_file)
        except:
            pass  # Ignore errors
        time.sleep(0.2)  # Check every 200ms
    
    # Clean up files on exit
    if os.path.exists(request_file):
        os.remove(request_file)
    if os.path.exists(result_file):
        os.remove(result_file)

def inject_click_listener(driver):
    recheck_flag = 'true' if recheck_mode else 'false'
    script = f"""
    console.log('[XPath Collector] Injection script running');
    window.recheckMode = {recheck_flag};
    if (!window.clickListenerInjected) {{
        console.log('[XPath Collector] Listener not yet injected, setting up...');
        if (!window.ws && !window.recheckMode) {{
            console.log('[XPath Collector] Creating WebSocket connection');
            window.ws = new WebSocket('ws://localhost:8765');
            window.ws.onopen = () => console.log('[XPath Collector] WebSocket CONNECTED');
            window.ws.onmessage = (e) => console.log('[XPath Collector] Server message:', e.data);
            window.ws.onerror = (e) => console.error('[XPath Collector] WebSocket ERROR:', e);
            window.ws.onclose = () => console.log('[XPath Collector] WebSocket CLOSED');
        }} else {{
            console.log('[XPath Collector] WebSocket already exists or recheck mode, state:', window.ws ? window.ws.readyState : 'N/A');
        }}
        document.addEventListener('click', function(event) {{
            console.log('[XPath Collector] Click detected on:', event.target.tagName);
            var element = event.target;
            var relativeXpath = getRelativeXPath(element);
            var fullXpath = getFullXPath(element);
            var cssSelector = getCSSSelector(element);
            element.setAttribute('data-relative-xpath', relativeXpath);
            element.setAttribute('data-full-xpath', fullXpath);
            element.setAttribute('data-css-selector', cssSelector);
            
            var tagName = element.tagName.toLowerCase();
            var elementText = element.textContent ? element.textContent.trim() : '';
            var innerText = element.innerText ? element.innerText.trim() : '';
            var displayText = innerText || elementText;
            
            var clickData = {{
                name: displayText || element.getAttribute('aria-label') || element.getAttribute('name') || element.getAttribute('placeholder') || element.getAttribute('value') || element.getAttribute('title') || element.getAttribute('alt') || tagName,
                visual_xpath: {{
                    text: displayText ? "//*[text()='" + displayText.replace(/'/g, "\\\\'") + "']" : '',
                    tag_text: displayText ? "//" + tagName + "[text()='" + displayText.replace(/'/g, "\\\\'") + "']" : '',
                    tag_contains: displayText ? "//" + tagName + "[contains(text(),'" + displayText.substring(0, 50).replace(/'/g, "\\\\'") + "')]" : '',
                    placeholder: element.getAttribute('placeholder') ? "//*[@placeholder='" + element.getAttribute('placeholder').replace(/'/g, "\\\\'") + "']" : '',
                    value: element.getAttribute('value') ? "//*[@value='" + element.getAttribute('value').replace(/'/g, "\\\\'") + "']" : '',
                    accessibility: element.getAttribute('aria-label') ? "//*[@aria-label='" + element.getAttribute('aria-label').replace(/'/g, "\\\\'") + "']" : '',
                    name: element.getAttribute('name') ? "//*[@name='" + element.getAttribute('name').replace(/'/g, "\\\\'") + "']" : '',
                    href: element.getAttribute('href') ? "//*[@href='" + element.getAttribute('href').replace(/'/g, "\\\\'") + "']" : '',
                    src: element.getAttribute('src') ? "//*[@src='" + element.getAttribute('src').replace(/'/g, "\\\\'") + "']" : '',
                    alt: element.getAttribute('alt') ? "//*[@alt='" + element.getAttribute('alt').replace(/'/g, "\\\\'") + "']" : '',
                    title: element.getAttribute('title') ? "//*[@title='" + element.getAttribute('title').replace(/'/g, "\\\\'") + "']" : ''
                }},
                relative_xpath: relativeXpath,
                full_xpath: fullXpath,
                css_selector: cssSelector,
                page_url: window.location.href,
                page_name: document.title
            }};
            
            if (window.recheckMode) {{
                console.log('[XPath Collector] Recheck mode - click ignored');
                return;
            }}
            
            if (window.ws && window.ws.readyState === WebSocket.OPEN) {{
                console.log('[XPath Collector] Sending data to server:', clickData.name);
                window.ws.send(JSON.stringify(clickData));
            }} else {{
                console.error('[XPath Collector] WebSocket not ready. State:', window.ws ? window.ws.readyState : 'null');
            }}
        }}, true);
        window.clickListenerInjected = true;
        console.log('[XPath Collector] Click listener INSTALLED');
    }} else {{
        console.log('[XPath Collector] Listener already installed, skipping');
    }}

    function getRelativeXPath(element) {{
        if (element.id) return '//*[@id="' + element.id + '"]';
        if (element.className) return '//' + element.tagName.toLowerCase() + '[@class="' + element.className + '"]';
        var path = [];
        while (element.nodeType === Node.ELEMENT_NODE) {{
            var selector = element.nodeName.toLowerCase();
            if (element.id) {{
                selector += '[@id="' + element.id + '"]';
                path.unshift(selector);
                break;
            }} else {{
                var sibling = element.previousSibling;
                var nth = 1;
                while (sibling) {{
                    if (sibling.nodeType === Node.ELEMENT_NODE && sibling.nodeName.toLowerCase() === selector) nth++;
                    sibling = sibling.previousSibling;
                }}
                if (nth !== 1) selector += '[' + nth + ']';
            }}
            path.unshift(selector);
            element = element.parentNode;
        }}
        return path.length ? '/' + path.join('/') : '';
    }}

    function getFullXPath(element) {{
        var path = [];
        while (element.nodeType === Node.ELEMENT_NODE) {{
            var selector = element.nodeName.toLowerCase();
            if (element.id) {{
                selector += '[@id="' + element.id + '"]';
                path.unshift(selector);
                break;
            }} else {{
                var sibling = element.previousSibling;
                var nth = 1;
                while (sibling) {{
                    if (sibling.nodeType === Node.ELEMENT_NODE && sibling.nodeName.toLowerCase() === selector) nth++;
                    sibling = sibling.previousSibling;
                }}
                if (nth !== 1) selector += '[' + nth + ']';
            }}
            path.unshift(selector);
            element = element.parentNode;
        }}
        return '/' + path.join('/');
    }}

    function getCSSSelector(element) {{
        if (element.id) return '#' + element.id;
        if (element.className) return element.tagName.toLowerCase() + '.' + element.className.split(' ').join('.');
        return element.tagName.toLowerCase();
    }}
    """
    driver.execute_script(script)

def main():
    import os
    global data, output_file, check_event, stop_event
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', help='URL to load')
    parser.add_argument('--recheck', action='store_true', help='Recheck mode - disable XPath capture')
    args = parser.parse_args()
    
    global recheck_mode
    recheck_mode = args.recheck

    with open('config.json', 'r') as f:
        config = json.load(f)
    load_url = args.url if args.url else config['load_url']
    domain = get_domain(load_url)
    output_file = os.path.join('output_folder', f'{domain}.json')

    # Load existing data if file exists
    if os.path.exists(output_file):
        try:
            with open(output_file, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError:
            data = {}
    else:
        data = {}

    check_event = threading.Event()
    stop_event = threading.Event()

    # Start WebSocket server
    ws_thread = threading.Thread(target=start_ws_server_thread)
    ws_thread.daemon = False  # Changed to False to allow proper shutdown
    ws_thread.start()
    time.sleep(0.1)  # Give server time to start

    # Setup Edge driver
    edge_options = Options()
    edge_options.add_argument("--disable-web-security")
    edge_options.add_argument("--disable-features=VizDisplayCompositor")
    service = Service(executable_path=os.path.join('driver', 'msedgedriver.exe'))
    driver = webdriver.Edge(service=service, options=edge_options)

    driver.get(load_url)
    inject_click_listener(driver)
    injected_urls.add(load_url)
    
    # Start URL monitoring thread now that driver is ready
    url_monitor_thread = threading.Thread(target=monitor_url_thread, args=(driver, stop_event))
    url_monitor_thread.daemon = True
    url_monitor_thread.start()
    
    # Start XPath validation thread
    validation_thread = threading.Thread(target=validate_xpaths_thread, args=(driver, stop_event))
    validation_thread.daemon = True
    validation_thread.start()

    page_url = driver.current_url
    page_name = driver.title

    if recheck_mode:
        print(f"RECHECK MODE: Page loaded: {page_name} - {page_url}")
        print("RECHECK MODE: XPath capture is DISABLED. Navigate to validate existing XPaths.")
    else:
        print(f"Page loaded: {page_name} - {page_url}")
        print("Click on elements to capture xpaths. Press Ctrl+C to stop.")

    handled_windows = [driver.current_window_handle]

    last_check_time = time.time()
    stop_file = 'stop_capture.flag'
    # Remove stop file if exists from previous run
    if os.path.exists(stop_file):
        os.remove(stop_file)
    
    while True:
        # Check for stop flag from signal or file
        if stop_flag or os.path.exists(stop_file):
            if os.path.exists(stop_file):
                os.remove(stop_file)
            break
        if check_event.wait(0.1):
            check_event.clear()
            # Re-inject listener on every click to handle page refreshes
            current_url = driver.current_url
            inject_click_listener(driver)
            if current_url not in injected_urls:
                injected_urls.add(current_url)
                print(f"New URL detected: {driver.title} - {current_url}")
        
        # Lightweight check every 3 seconds for page refresh (no window switching)
        current_time = time.time()
        if current_time - last_check_time >= 3:
            last_check_time = current_time
            try:
                current_window = driver.current_window_handle
                handles = driver.window_handles
                
                # Check for new tabs
                for handle in handles:
                    if handle not in handled_windows:
                        driver.switch_to.window(handle)
                        inject_click_listener(driver)
                        handled_windows.append(handle)
                        print(f"New tab detected and injected: {driver.title}")
                        driver.switch_to.window(current_window)
                
                # Check if listener exists in current window
                has_listener = driver.execute_script("return window.clickListenerInjected === true;")
                if not has_listener:
                    inject_click_listener(driver)
                    print(f"Re-injected after page refresh: {driver.title}")
            except:
                pass  # Ignore errors during navigation

    print("Loop exited", flush=True)
    # Shutdown sequence
    print("Stopping...", flush=True)
    
    # Close driver first
    try:
        driver.quit()
        print("Driver quit", flush=True)
    except:
        pass
    
    # Stop WebSocket server
    stop_event.set()
    print("Stop event set", flush=True)
    
    # Wait for thread with timeout
    ws_thread.join(timeout=3.0)
    if ws_thread.is_alive():
        print("Thread did not join within timeout", flush=True)
    else:
        print("Thread joined", flush=True)
    
    print("Stopped.", flush=True)
    sys.exit(0)

if __name__ == "__main__":
    main()