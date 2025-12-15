# XPath Collector

This is a Python Selenium application to collect xpaths from web pages by clicking on elements.

## Setup

1. Download Microsoft Edge WebDriver from https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/
2. Place `msedgedriver.exe` in the `driver` folder.
3. Edit `config.json` to set the `load_url` to the desired URL.
4. Run `run_web.bat` to start the web interface, or `run.bat` to start directly.

## Usage

### Web Interface (Recommended)
- Run `run_web.bat` to start the web app.
- Open http://127.0.0.1:5000 in your browser.
- The load URL from `config.json` will be displayed.
- Edit the URL if needed.
- Click "Start Capture" to launch the XPath collector with the specified URL.
- The Selenium browser will open, and you can click elements to capture XPaths.

### Direct Run
- Run `run.bat` to start the application directly with the URL from `config.json`.
- The application will open the URL in Edge browser.
- Click on any element on the page.
- Xpaths will be captured and saved to `output_folder/<domain>.json`.
- Press Ctrl+C in the terminal to stop.

## Output

The JSON file contains page objects with URL, name, and list of xpaths for clicked elements.