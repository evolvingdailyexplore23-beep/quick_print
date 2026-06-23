import os
import io
import uuid
import random
import sqlite3
from flask import Flask, render_template, request, send_file, after_this_request

app = Flask(__name__)


# ==========================================
UPLOAD_FOLDER = 'uploads'
# 允許上傳的副檔名
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "txt", "png", "jpg", "jpeg"}
# 限制檔案大小 20 MB
MAX_FILE_SIZE = 20 * 1024 * 1024

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE

DB_NAME = "database.db"

# 確保 uploads 資料夾存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# 檢查副檔名是否合法的輔助函式
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


# ----------------------------------------------------------------
# 初始化資料庫，建立用來永久保存檔案資訊的資料表
# ----------------------------------------------------------------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            original_name TEXT NOT NULL,
            saved_name TEXT NOT NULL,
            pickup_code TEXT NOT NULL UNIQUE
        )
    """)
    conn.commit()
    conn.close()


# ----------------------------------------------------------------
# 資料庫專用的輔助函式（查詢、新增與刪除）
# ----------------------------------------------------------------
def get_file_by_code(pickup_code):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT original_name, saved_name FROM files WHERE pickup_code = ?", (pickup_code,))
    row = cursor.fetchone()
    conn.close()
    return row

def save_file_to_db(original_name, saved_name, pickup_code):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO files (original_name, saved_name, pickup_code)
        VALUES (?, ?, ?)
    """, (original_name, saved_name, pickup_code))
    conn.commit()
    conn.close()

def delete_file_from_db(pickup_code):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM files WHERE pickup_code = ?", (pickup_code,))
    conn.commit()
    conn.close()


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "沒有檔案區塊"
    
    file = request.files['file']
    if file.filename == '':
        return "未選擇檔案"
    
    # 副檔名類型檢查
    if not allowed_file(file.filename):
        return """
        <div style="font-family: Arial; text-align: center; margin-top: 50px; color: #dc3545;">
            <h2>❌ 檔案格式不允許！</h2>
            <p>請上傳：pdf、doc、docx、txt、png、jpg、jpeg 格式的檔案。</p>
            <a href="/" style="text-decoration: none; color: #007BFF;">← 返回首頁</a>
        </div>
        """
    
    if file:
        original_filename = file.filename
        ext = os.path.splitext(original_filename)[1]
        
        # 用亂數 UUID 重命名
        safe_filename = f"{uuid.uuid4().hex}{ext}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        file.save(file_path)
        
        # 【取件碼生成】確保 4 位數不重複
        while True:
            code = f"{random.randint(0, 9999):04d}"
            if get_file_by_code(code) is None:
                break
        
        # 將資料存入 SQLite 資料庫
        save_file_to_db(original_filename, safe_filename, code)
        
        return f"""
        <div style="font-family: Arial; text-align: center; margin-top: 50px;">
            <h2 style="color: #28a745;">🎉 檔案【{original_filename}】上傳成功！</h2>
            <p style="font-size: 18px;">請記下您的影印取件碼（已透過限制檢查並存入資料庫）：</p>
            <div style="font-size: 48px; font-weight: bold; color: #007BFF; letter-spacing: 5px; margin: 20px 0;">{code}</div>
            <p style="color: #666;">去影印店打開網頁，輸入這 4 個數字即可下載。</p>
            <a href="/" style="text-decoration: none; color: #007BFF;">← 返回首頁</a>
        </div>
        """

@app.route('/download', methods=['POST'])
def download_file():
    user_code = request.form.get('code', '').strip()

    # 取件碼格式檢查
    if not user_code.isdigit() or len(user_code) != 4:
        return """
        <div style="font-family: Arial; text-align: center; margin-top: 50px; color: #dc3545;">
            <h2>❌ 取件碼格式錯誤！</h2>
            <p>請輸入 4 位數純數字取件碼。</p>
            <a href="/" style="text-decoration: none; color: #007BFF;">← 返回首頁重試</a>
        </div>
        """

    db_row = get_file_by_code(user_code)
    
    if db_row is not None:
        original_filename, target_filename = db_row
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], target_filename)
        
        # 將檔案讀進記憶體
        with open(file_path, 'rb') as f:
            file_data = io.BytesIO(f.read())
            
        # 刪除檔案 + 註銷資料庫紀錄
        @after_this_request
        def remove_file(response):
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                delete_file_from_db(user_code)
                print(f"🎉【資安驗證成功】硬碟檔案與 DB 紀錄 {target_filename} 已徹底雙重銷毀！")
            except Exception as e:
                print(f"銷毀檔案或資料庫紀錄時出錯: {e}")
            return response
        
        return send_file(
            file_data,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=original_filename
        )
    else:
        return """
        <div style="font-family: Arial; text-align: center; margin-top: 50px; color: #dc3545;">
            <h2>❌ 取件碼錯誤、已過期或檔案已被下載銷毀！</h2>
            <p>本站採取單次下載即銷毀機制，確保您的隱私安全。</p>
            <a href="/" style="text-decoration: none; color: #007BFF;">← 返回首頁重試</a>
        </div>
        """

# 處理 Flask 內建的大檔案阻擋報錯
@app.errorhandler(413)
def request_entity_too_large(error):
    return """
    <div style="font-family: Arial; text-align: center; margin-top: 50px; color: #dc3545;">
        <h2>❌ 檔案過大！</h2>
        <p>本站限制臨時傳輸檔案最大為 20 MB，請壓縮後重新上傳。</p>
        <a href="/" style="text-decoration: none; color: #007BFF;">← 返回首頁</a>
    </div>
    """, 413

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
