from flask import Flask, render_template, request, jsonify, session, redirect, url_for, flash
import yt_dlp
import sqlite3
import os

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # Change this in production

# Database Setup
DB_NAME = "site.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    # Settings table: Stores Ads and Pinned Message
    c.execute('''CREATE TABLE IF NOT EXISTS settings 
                 (id INTEGER PRIMARY KEY, pinned_msg TEXT, ad_code_1 TEXT, ad_code_2 TEXT)''')
    
    # Migration: Add popup_msg column if not exists
    try:
        c.execute("ALTER TABLE settings ADD COLUMN popup_msg TEXT")
    except sqlite3.OperationalError:
        pass # Column likely already exists

    # Notes table: Admin notepad
    c.execute('''CREATE TABLE IF NOT EXISTS notes 
                 (id INTEGER PRIMARY KEY, content TEXT)''')
    
    # Initialize default settings if empty
    c.execute('SELECT count(*) FROM settings')
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO settings (pinned_msg, ad_code_1, ad_code_2, popup_msg) VALUES (?, ?, ?, ?)", 
                  ("Welcome to YT Stream!", "", "", ""))
        conn.commit()
    
    # Initialize default note if empty
    c.execute('SELECT count(*) FROM notes')
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO notes (content) VALUES (?)", ("Write your notes here...",))
        conn.commit()
        
    conn.close()

init_db()

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

# --- Routes ---

@app.route('/')
def index():
    conn = get_db_connection()
    settings = conn.execute('SELECT * FROM settings').fetchone()
    conn.close()
    return render_template('index.html', settings=settings)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if 'user' not in session:
        return render_template('admin.html', logged_in=False)

    conn = get_db_connection()
    settings = conn.execute('SELECT * FROM settings').fetchone()
    note = conn.execute('SELECT * FROM notes').fetchone()
    conn.close()
    
    return render_template('admin.html', logged_in=True, settings=settings, note=note)

@app.route('/login', methods=['POST'])
def login():
    username = request.form.get('username')
    password = request.form.get('password')
    
    if username == "admin" and password == "admin123":
        session['user'] = username
        return redirect(url_for('admin'))
    else:
        return render_template('admin.html', logged_in=False, error="Invalid credentials")

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('admin'))

@app.route('/admin/update_settings', methods=['POST'])
def update_settings():
    if 'user' not in session:
        return redirect(url_for('admin'))
        
    pinned_msg = request.form.get('pinned_msg')
    popup_msg = request.form.get('popup_msg')
    ad_code_1 = request.form.get('ad_code_1')
    ad_code_2 = request.form.get('ad_code_2')
    
    conn = get_db_connection()
    conn.execute('UPDATE settings SET pinned_msg = ?, popup_msg = ?, ad_code_1 = ?, ad_code_2 = ? WHERE id = 1', 
                 (pinned_msg, popup_msg, ad_code_1, ad_code_2))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/admin/save_note', methods=['POST'])
def save_note():
    if 'user' not in session:
        return redirect(url_for('admin'))
        
    content = request.form.get('content')
    
    conn = get_db_connection()
    conn.execute('UPDATE notes SET content = ? WHERE id = 1', (content,))
    conn.commit()
    conn.close()
    
    return redirect(url_for('admin'))

@app.route('/robots.txt')
def robots():
    return "User-agent: *\nDisallow: /admin\nAllow: /", 200, {'Content-Type': 'text/plain'}

@app.route('/sitemap.xml')
def sitemap():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
        <url>
            <loc>http://127.0.0.1:5000/</loc>
            <lastmod>2026-01-20</lastmod>
            <changefreq>daily</changefreq>
            <priority>1.0</priority>
        </url>
    </urlset>"""
    return xml, 200, {'Content-Type': 'application/xml'}

import requests
from flask import Response, stream_with_context
import urllib.parse

# ... (Existing code) ...

@app.route('/proxy_download')
def proxy_download():
    url = request.args.get('url')
    title = request.args.get('title')
    ext = request.args.get('ext')
    
    if not url or not title or not ext:
        return "Missing parameters", 400

    # Sanitize title
    safe_title = "".join([c for c in title if c.isalpha() or c.isdigit() or c==' ' or c=='_']).rstrip()
    filename = f"{safe_title}.{ext}"
    
    try:
        req = requests.get(url, stream=True)
        
        headers = {
            'Content-Disposition': f'attachment; filename="{filename}"',
            'Content-Type': req.headers.get('Content-Type'),
        }
        if req.headers.get('Content-Length'):
            headers['Content-Length'] = req.headers.get('Content-Length')

        return Response(
            stream_with_context(req.iter_content(chunk_size=1024 * 1024)), # 1MB chunks
            headers=headers
        )
    except Exception as e:
        return f"Error downloading file: {str(e)}", 500

@app.route('/get_info', methods=['POST'])
# ... (rest of get_info) ...
def get_info():
    url = request.json.get('url')
    if not url:
        return jsonify({"error": "URL එකක් ඇතුළත් කරන්න"}), 400

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            audio_formats = []
            video_formats = []
            other_formats = []

            for f in info.get('formats', []):
                # Calculate file size
                filesize = f.get('filesize') or f.get('filesize_approx')
                if filesize:
                    filesize = round(filesize / 1048576, 1) # MB
                else:
                    filesize = "N/A"

                # Common data
                format_data = {
                    'quality': f.get('format_note', 'N/A'),
                    'ext': f.get('ext'),
                    'url': f.get('url'),
                    'filesize': filesize,
                    'format_id': f.get('format_id')
                }

                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')

                if vcodec == 'none' and acodec != 'none':
                    # Audio Only
                    format_data['quality'] = f"{f.get('abr', 'N/A')}kbps" # Use bitrate for audio
                    audio_formats.append(format_data)
                elif vcodec != 'none':
                    # Video (Progressive or DASH)
                    if acodec == 'none':
                        format_data['note'] = "Video Only (No Sound)"
                    else:
                        format_data['note'] = "Video + Audio"
                    video_formats.append(format_data)
                else:
                    # Other
                    other_formats.append(format_data)

            # Sort formats (optional but good for UX)
            # Audio by bitrate (high to low), Video by resolution (high to low)
            # This is a simple reverse sort since yt-dlp usually provides them somewhat ordered
            audio_formats.reverse() 
            video_formats.reverse()

            return jsonify({
                'title': info.get('title'),
                'thumbnail': info.get('thumbnail'),
                'formats': {
                    'audio': audio_formats,
                    'video': video_formats,
                    'other': other_formats
                }
            })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)