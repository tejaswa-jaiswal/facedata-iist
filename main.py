from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import os
import shutil
import sqlite3
import uuid
import re
from pathlib import Path

# --- Configuration (can override with environment variables) ---
DATA_FOLDER = os.getenv("DATA_FOLDER", "data")       # default relative 'data' folder
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")  # default relative 'uploads' folder
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTS = {".png", ".jpg", ".jpeg"}

# Ensure directories exist
Path(DATA_FOLDER).mkdir(parents=True, exist_ok=True)
Path(UPLOAD_FOLDER).mkdir(parents=True, exist_ok=True)

app = FastAPI(title="IIST Face Recognition Attendance")

# Serve preview images and saved data (optional, careful with exposing raw data in production)
app.mount("/uploads", StaticFiles(directory=UPLOAD_FOLDER), name="uploads")
app.mount("/data", StaticFiles(directory=DATA_FOLDER), name="data")

# --- Database setup (SQLite) ---
DB_PATH = str(Path(DATA_FOLDER) / "attendance.db")
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()
cursor.execute('''
    CREATE TABLE IF NOT EXISTS students (
        enrollment TEXT PRIMARY KEY,
        image_count INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
''')
conn.commit()

# --- Helpers ---
def sanitize_enrollment(raw: str) -> str:
    """
    Uppercase alphanumeric + underscore + hyphen only.
    Removes characters that could be used for path traversal, spaces, etc.
    """
    if not raw:
        return ""
    # keep uppercase letters, digits, underscore, hyphen
    cleaned = re.sub(r'[^A-Z0-9_-]', '', raw.upper())
    return cleaned

def count_images_in_folder(folder: Path) -> int:
    return sum(1 for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ALLOWED_EXTS)

# --- Routes ---
@app.get("/", response_class=HTMLResponse)
async def upload_form():
    # Minimal changes: make layout responsive and keep header image big (image src unchanged).
    return """
<!DOCTYPE html>
<html>
<head>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>IIST Face Recognition Attendance</title>
    <style>
        /* Basic reset */
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: #222; min-height: 100vh; padding: 16px; }

        /* Wrapper */
        .wrapper { max-width: 960px; margin: 0 auto; }

        /* Header - keep image big */
        .header {
            display: flex;
            align-items: center;
            gap: 20px;
            padding: 20px;
            background: rgba(255,255,255,0.04);
            border-radius: 12px;
        }
        /* Keep the image big and responsive. DO NOT CHANGE SRC in HTML. */
        .header img {
            width: 60vw;            /* large on small screens */
            max-width: 600px;       /* cap on large screens */
            height: auto;           /* preserve aspect ratio */
            border-radius: 8px;
            border: 4px solid rgba(255,255,255,0.3);
            object-fit: cover;
            display: block;
        }
        .header-text { flex: 1; min-width: 0; }
        .header-text h2 { font-size: 1.25rem; color: #fff; margin-bottom: 6px; }
        .header-text p { color: rgba(255,255,255,0.95); font-size: 0.95rem; }

        /* Card */
        .card {
            background: #fff;
            padding: 20px;
            border-radius: 12px;
            margin-top: 20px;
        }

        h1 { font-size: 1.125rem; margin-bottom: 12px; text-align: center; color: #2c3e50; }

        /* Enrollment */
        .enrollment-section { padding: 12px; border-radius: 8px; background: linear-gradient(135deg,#f8f9fa,#e9ecef); margin-bottom: 12px; text-align: center; border: 2px solid #3498db; }
        .enrollment-input { width: 300px; max-width: 100%; padding: 12px; font-size: 16px; border: 2px solid #3498db; border-radius: 8px; text-align: center; font-weight: 600; }

        /* Stats and upload */
        .stats { display: flex; justify-content: space-between; gap: 12px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }
        .stats .count { font-size: 1.5rem; font-weight: 700; color: #27ae60; }
        .upload-area {
            border: 3px dashed #3498db;
            border-radius: 12px;
            padding: 28px;
            text-align: center;
            background: #f8f9fa;
            cursor: pointer;
        }
        .upload-area.small { padding: 16px; }

        input[type="file"] { display: none; }

        button {
            background: linear-gradient(135deg, #3498db, #2980b9);
            color: #fff;
            padding: 12px 24px;
            border: none;
            border-radius: 24px;
            font-size: 16px;
            cursor: pointer;
            font-weight: 600;
        }
        button:disabled { background: #bdc3c7; cursor: not-allowed; }

        /* Gallery */
        .gallery { margin-top: 18px; display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 12px; }
        .gallery img { width: 100%; height: 120px; object-fit: cover; border-radius: 8px; display: block; }

        .instructions { margin-top: 12px; padding: 12px; background: #d4edda; border-radius: 8px; border-left: 4px solid #27ae60; font-size: 14px; }

        /* Responsive tweaks */
        @media (max-width: 900px) {
            .header { flex-direction: column; align-items: center; text-align: center; }
            .header img { width: 80vw; max-width: 600px; }
            .header-text { width: 100%; }
        }
        @media (max-width: 480px) {
            body { padding: 10px; }
            .header img { width: 90vw; max-width: 520px; }
            .enrollment-input { width: 100%; font-size: 15px; padding: 10px; }
            .upload-area { padding: 18px; }
            .gallery img { height: 100px; }
        }
    </style>
</head>
<body>
    <div class="wrapper">
        <div class="header">
            <img src="https://indoreinstitute.com//wp-content/uploads/2024/11/iist-scaled.webp"
                 alt="IIST Indore"
                 onerror="this.src='https://images.unsplash.com/photo-1523050854058-8df90110c9f1?w=400&h=120&fit=crop'">
            <div class="header-text">
                <h2>Indore Institute of Science and Technology</h2>
                <p>Face Recognition Attendance System</p>
            </div>
        </div>

        <div class="card">
            <h1>📸 Upload Face Images (Max 10 per Student)</h1>

            <form id="uploadForm" enctype="multipart/form-data">
                <div class="enrollment-section">
                    <label style="font-size: 16px; font-weight: 600; color: #2c3e50; display:block; margin-bottom:8px;">
                        Student Enrollment No:
                    </label>
                    <input type="text" id="enrollmentNo" class="enrollment-input" placeholder="Enter your enrollment number" maxlength="20" required>
                </div>

                <div class="stats">
                    <div>Uploaded Images: <span class="count" id="count">0</span>/10</div>
                    
                </div>

                <div class="upload-area" onclick="document.getElementById('fileInput').click()">
                    <p style="font-size: 18px; margin-bottom: 6px;">📷 Click or Drag & Drop Face Photos</p>
                    <p style="font-size: 14px; color: #7f8c8d;">JPG, PNG • Max 5MB each • Clear face, various angles</p>
                </div>
                <input id="fileInput" type="file" multiple accept="image/*">
                <div style="text-align: center; margin-top: 18px;">
                    <button type="submit" id="submitBtn" disabled>🚀 Process Images for Attendance System</button>
                </div>
            </form>

            <div id="gallery" class="gallery"></div>
            <div class="instructions">
                <strong>💡 Pro Tips for Best Recognition:</strong><br>
                • Upload 8-10 photos per student (front, left/right profiles, different lighting)<br>
            </div>
        </div>
    </div>

    <script>
        let imageCount = 0;
        let currentEnrollment = '';
        const gallery = document.getElementById('gallery');
        const countEl = document.getElementById('count');
        const enrollmentInput = document.getElementById('enrollmentNo');
        const submitBtn = document.getElementById('submitBtn');
        const uploadArea = document.querySelector('.upload-area');

        document.getElementById('fileInput').addEventListener('change', handleFiles);

        enrollmentInput.addEventListener('input', function() {
            currentEnrollment = this.value.trim().toUpperCase();
            this.value = currentEnrollment;
            submitBtn.disabled = !currentEnrollment;
        });

        ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(event => {
            uploadArea.addEventListener(event, preventDefaults, false);
        });
        ['dragenter', 'dragover'].forEach(event => {
            uploadArea.addEventListener(event, highlight, false);
        });
        ['dragleave', 'drop'].forEach(event => {
            uploadArea.addEventListener(event, unhighlight, false);
        });
        uploadArea.addEventListener('drop', handleDrop, false);

        function preventDefaults(e) { e.preventDefault(); e.stopPropagation(); }
        function highlight(e) { uploadArea.classList.add('dragover'); }
        function unhighlight(e) { uploadArea.classList.remove('dragover'); }

        function handleDrop(e) {
            const dt = e.dataTransfer;
            const files = dt.files;
            handleFiles({target: {files}});
        }

        function handleFiles(e) {
            const files = Array.from(e.target.files).slice(0, 10 - imageCount);
            files.forEach(file => uploadFile(file));
        }

        async function uploadFile(file) {
            if (imageCount >= 10 || !currentEnrollment) {
                alert('Enter enrollment number and max 10 images!');
                return;
            }
            const formData = new FormData();
            formData.append('file', file);
            formData.append('enrollment', currentEnrollment);

            try {
                const response = await fetch('/upload/', { method: 'POST', body: formData });
                if (!response.ok) {
                    const txt = await response.text();
                    throw new Error(txt || 'Upload failed');
                }
                const result = await response.json();
                addToGallery(result.filename, result.url, currentEnrollment);
                imageCount++;
                countEl.textContent = imageCount;
            } catch (error) {
                alert('Upload failed: ' + error);
            }
        }

        function addToGallery(filename, url, enrollment) {
            const imgContainer = document.createElement('div');
            imgContainer.style.position = 'relative';
            const img = document.createElement('img');
            img.src = url;
            img.alt = filename;
            img.title = filename;
            img.loading = 'lazy';
            imgContainer.appendChild(img);
            gallery.appendChild(imgContainer);
        }

        document.getElementById('uploadForm').addEventListener('submit', e => {
            e.preventDefault();
            if (!currentEnrollment) {
                alert('Please enter Enrollment Number first!');
                return;
            }
            if (imageCount === 0) {
                alert('Please upload at least 1 image');
                return;
            }
            alert(`✅ ${imageCount} images saved and ready for face recognition training!`);
        });
    </script>
</body>
</html>
    """

@app.post("/upload/")
async def upload_image(file: UploadFile = File(...), enrollment: str = Form(...)):
    # Validate enrollment and sanitize
    if not enrollment:
        raise HTTPException(status_code=400, detail="Enrollment number required")
    enrollment_clean = sanitize_enrollment(enrollment)
    if not enrollment_clean:
        raise HTTPException(status_code=400, detail="Invalid enrollment (allowed: letters, digits, underscore, hyphen)")

    # Validate extension
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="Only PNG/JPG/JPEG allowed")

    # Read file bytes to enforce size limit
    try:
        contents = await file.read()  # async read of UploadFile
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to read uploaded file")

    if len(contents) > MAX_FILE_BYTES:
        raise HTTPException(status_code=400, detail="File too large (max 5MB)")

    # Student folder under DATA_FOLDER
    student_folder = Path(DATA_FOLDER) / enrollment_clean
    student_folder.mkdir(parents=True, exist_ok=True)

    # Count existing images
    image_count = count_images_in_folder(student_folder)
    if image_count >= 10:
        raise HTTPException(status_code=400, detail="Maximum 10 images per student")

    filename = f"{image_count+1:02d}{ext}"
    filepath = student_folder / filename

    # Write to disk
    try:
        with open(filepath, "wb") as f:
            f.write(contents)
    except Exception:
        raise HTTPException(status_code=500, detail="Failed to save file")

    # Update DB
    try:
        cursor.execute('INSERT OR IGNORE INTO students (enrollment, image_count) VALUES (?, 0)', (enrollment_clean,))
        cursor.execute('UPDATE students SET image_count = image_count + 1 WHERE enrollment = ?', (enrollment_clean,))
        conn.commit()
    except Exception:
        # rollback on failure (best-effort)
        conn.rollback()
        # try to remove file we just wrote
        try:
            filepath.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail="Database error")

    # Create preview copy in UPLOAD_FOLDER with a unique name (to avoid cache collisions)
    preview_name = f"{uuid.uuid4()}_{filename}"
    preview_file = Path(UPLOAD_FOLDER) / preview_name
    try:
        shutil.copy2(filepath, preview_file)
    except Exception:
        # non-fatal: still return saved path but note preview may be unavailable
        preview_name = None

    preview_path = f"/uploads/{preview_name}" if preview_name else None

    return {"filename": filename, "url": preview_path, "path": str(filepath), "enrollment": enrollment_clean}

@app.get("/students")
async def list_students():
    cursor.execute('SELECT enrollment, image_count FROM students')
    return [{"enrollment": row[0], "image_count": row[1]} for row in cursor.fetchall()]

# Run with: uvicorn app:app --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
