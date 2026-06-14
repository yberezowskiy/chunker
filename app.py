from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import sqlite3
from datetime import datetime
import json
import uuid

# Импортируем наши процессоры
from processors.file_processor import FileProcessor
from processors.chunker import RAGChunker
from processors.exporter import ResultExporter

# Инициализация Flask приложения
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-change-this'  # Измените в продакшене!

# Создаем абсолютный путь для базы данных
basedir = os.path.abspath(os.path.dirname(__file__))
database_dir = os.path.join(basedir, 'database')
os.makedirs(database_dir, exist_ok=True)  # Создаем папку если её нет
database_path = os.path.join(database_dir, 'users.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{database_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Конфигурация загрузок и скачиваний
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static', 'uploads')
app.config['DOWNLOAD_FOLDER'] = os.path.join(basedir, 'static', 'downloads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Максимальный размер файла 16MB

# Создаем папки если их нет
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

# Инициализация базы данных
db = SQLAlchemy(app)

# Инициализация системы логина
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Инициализация процессоров
file_processor = FileProcessor()
chunker = RAGChunker()
exporter = ResultExporter()
exporter.set_download_directory(app.config['DOWNLOAD_FOLDER'])

# Глобальное хранилище для результатов (в реальном приложении использовать Redis)
processing_results = {}

# Модель пользователя (обновленная версия)
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(120), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())
    role = db.Column(db.String(20), default='user')  # 'user', 'admin', 'moderator'
    
    # Связь с логами
    logs = db.relationship('UserLog', backref='user', lazy=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f'<User {self.username}>'

# Модель логов пользователей (для отслеживания NDA)
class UserLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    action = db.Column(db.String(200), nullable=False)  # Тип действия
    filename = db.Column(db.String(200), nullable=True)  # Имя файла (если есть)
    file_size = db.Column(db.Integer, nullable=True)     # Размер файла
    ip_address = db.Column(db.String(45), nullable=True) # IP адрес
    user_agent = db.Column(db.Text, nullable=True)       # User agent браузера
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    
    def __repr__(self):
        return f'<UserLog {self.user_id}: {self.action}>'

# Загрузка пользователя для Flask-Login
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Функция для логирования действий пользователей
def log_user_action(user_id, action, filename=None, file_size=None):
    """Логирует действия пользователя для отслеживания NDA"""
    try:
        log_entry = UserLog(
            user_id=user_id,
            action=action,
            filename=filename,
            file_size=file_size,
            ip_address=request.remote_addr if request else None,
            user_agent=request.headers.get('User-Agent') if request else None
        )
        db.session.add(log_entry)
        db.session.commit()
        print(f"✅ Лог записан: User {user_id} - {action}")
    except Exception as e:
        print(f"❌ Ошибка логирования: {e}")
        db.session.rollback()

# Создание таблиц
with app.app_context():
    try:
        db.create_all()
        print("✅ База данных создана успешно!")
        
        # Обновляем существующих пользователей - делаем первого админом
        first_user = User.query.filter_by(id=1).first()
        if first_user and first_user.role != 'admin':
            first_user.role = 'admin'
            db.session.commit()
            print("✅ Первый пользователь назначен администратором")
    except Exception as e:
        print(f"❌ Ошибка создания базы данных: {e}")

# Маршруты
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        # Проверка существующего пользователя
        if User.query.filter_by(username=username).first():
            flash('Пользователь с таким именем уже существует!')
            return redirect(url_for('register'))
        
        if User.query.filter_by(email=email).first():
            flash('Пользователь с таким email уже существует!')
            return redirect(url_for('register'))
        
        # Создание нового пользователя
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        # Логируем регистрацию
        log_user_action(user.id, "Регистрация нового пользователя")
        
        flash('Регистрация успешна! Теперь вы можете войти.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            # Логируем вход
            log_user_action(user.id, "Вход в систему")
            flash('Вы успешно вошли в систему!')
            return redirect(url_for('dashboard'))
        else:
            flash('Неверное имя пользователя или пароль!')
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    # Получаем последние 10 действий пользователя
    user_logs = UserLog.query.filter_by(user_id=current_user.id)\
                            .order_by(UserLog.timestamp.desc())\
                            .limit(10).all()
    return render_template('dashboard.html', user=current_user, logs=user_logs)

@app.route('/logout')
@login_required
def logout():
    # Логируем выход
    log_user_action(current_user.id, "Выход из системы")
    logout_user()
    flash('Вы вышли из системы!')
    return redirect(url_for('index'))

# Новый маршрут для загрузки файлов
@app.route('/upload', methods=['POST'])
@login_required
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Файл не найден'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Файл не выбран'}), 400
    
    if file:
        try:
            # Сохраняем файл
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            
            # Получаем размер файла
            file_size = os.path.getsize(filepath)
            
            # Логируем загрузку файла (ВАЖНО для NDA)
            log_user_action(
                current_user.id, 
                f"Загрузка файла: {filename}", 
                filename=filename, 
                file_size=file_size
            )
            
            # Обрабатываем файл
            result = file_processor.process_file(filepath, filename)
            
            if result['success']:
                # Генерируем уникальный ID для результатов
                result_id = str(uuid.uuid4())
                
                # Сохраняем результаты в памяти
                processing_results[result_id] = {
                    'file_data': result['data'],
                    'is_json_mode': result['is_json_mode'],
                    'fields': result.get('fields', []),
                    'sample': result.get('sample', []),
                    'source_filename': filename,
                    'chunks': None,
                    'user_id': current_user.id
                }
                
                return jsonify({
                    'success': True,
                    'message': result.get('message', 'Файл успешно обработан'),
                    'is_json_mode': result['is_json_mode'],
                    'fields': result.get('fields', []),
                    'sample': result.get('sample', [])[:3],
                    'filename': filename,
                    'size': file_size,
                    'result_id': result_id
                })
            else:
                return jsonify({
                    'success': False,
                    'error': result['error']
                })
            
        except Exception as e:
            log_user_action(current_user.id, f"Ошибка загрузки файла: {str(e)}")
            return jsonify({'error': f'Ошибка загрузки: {str(e)}'}), 500
    
    return jsonify({'error': 'Ошибка загрузки файла'}), 400

# Маршрут для автоматической настройки параметров
@app.route('/auto_tune', methods=['POST'])
@login_required
def auto_tune():
    try:
        data = request.get_json()
        sample_data = data.get('sample', [])
        mapping_config = data.get('mapping', {})
        
        settings = chunker.auto_tune_settings(sample_data, mapping_config)
        
        return jsonify({
            'success': True,
            'settings': settings
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

# Маршрут для чанкинга данных
@app.route('/chunk', methods=['POST'])
@login_required
def chunk_data():
    try:
        data = request.get_json()
        result_id = data.get('result_id')
        mapping_config = data.get('mapping', {})
        template_type = data.get('template', 'universal')
        chunk_size = data.get('chunk_size', 800)
        chunk_overlap = data.get('chunk_overlap', 80)
        
        # Проверяем, есть ли результаты обработки
        if result_id not in processing_results:
            return jsonify({
                'success': False,
                'error': 'Результаты обработки не найдены'
            })
        
        result_data = processing_results[result_id]
        
        # Проверяем права доступа
        if result_data['user_id'] != current_user.id:
            return jsonify({
                'success': False,
                'error': 'Доступ запрещен'
            })
        
        file_data = result_data['file_data']
        source_filename = result_data['source_filename']
        
        # Выполняем чанкинг
        chunks = chunker.normalize_and_chunk(
            file_data, 
            mapping_config, 
            template_type, 
            chunk_size, 
            chunk_overlap,
            source_filename
        )
        
        # Сохраняем чанки в результатах
        processing_results[result_id]['chunks'] = chunks
        
        # Логируем успешную обработку
        log_user_action(
            current_user.id, 
            f"Успешный чанкинг файла: {source_filename} ({len(chunks)} чанков)"
        )
        
        return jsonify({
            'success': True,
            'chunks': chunks[:50],
            'total_chunks': len(chunks),
            'message': f'Обработано успешно! Создано {len(chunks)} чанков.',
            'result_id': result_id
        })
        
    except Exception as e:
        error_msg = f"Ошибка чанкинга: {str(e)}"
        log_user_action(current_user.id, error_msg)
        return jsonify({
            'success': False,
            'error': error_msg
        })

# Маршрут для экспорта результатов
@app.route('/export/<format>/<result_id>', methods=['POST'])
@login_required
def export_results(format, result_id):
    try:
        # Проверяем, есть ли результаты
        if result_id not in processing_results:
            return jsonify({'success': False, 'error': 'Результаты не найдены'})
        
        result_data = processing_results[result_id]
        
        # Проверяем права доступа
        if result_data['user_id'] != current_user.id:
            return jsonify({'success': False, 'error': 'Доступ запрещен'})
        
        # Получаем чанки
        chunks = result_data.get('chunks')
        if not chunks:
            return jsonify({'success': False, 'error': 'Нет данных для экспорта'})
        
        # Получаем параметры экспорта
        data = request.get_json()
        for_rag = data.get('for_rag', False)
        source_filename = result_data.get('source_filename', 'chunks')
        
        # Экспортируем в нужный формат
        if format == 'json':
            file_path = exporter.export_to_json(chunks, source_filename, for_rag)
        elif format == 'txt':
            file_path = exporter.export_to_txt(chunks, source_filename, for_rag)
        elif format == 'docx':
            file_path = exporter.export_to_docx(chunks, source_filename, for_rag)
        elif format == 'pdf':
            file_path = exporter.export_to_pdf(chunks, source_filename, for_rag)
        else:
            return jsonify({'success': False, 'error': 'Неподдерживаемый формат'})
        
        # Логируем экспорт
        log_user_action(
            current_user.id, 
            f"Экспорт результатов: {source_filename} в формате {format.upper()}"
        )
        
        # Возвращаем имя файла для скачивания
        filename = os.path.basename(file_path)
        return jsonify({
            'success': True,
            'filename': filename,
            'message': f'Файл успешно создан: {filename}'
        })
        
    except Exception as e:
        error_msg = f"Ошибка экспорта: {str(e)}"
        log_user_action(current_user.id, error_msg)
        return jsonify({
            'success': False,
            'error': error_msg
        })

# Маршрут для скачивания файла
@app.route('/download/<filename>')
@login_required
def download_file(filename):
    try:
        # Проверяем, что файл существует
        file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
        if not os.path.exists(file_path):
            return jsonify({'error': 'Файл не найден'}), 404
        
        # Логируем скачивание
        log_user_action(current_user.id, f"Скачивание файла: {filename}")
        
        return send_file(file_path, as_attachment=True)
        
    except Exception as e:
        log_user_action(current_user.id, f"Ошибка скачивания: {str(e)}")
        return jsonify({'error': 'Ошибка при скачивании файла'}), 500

# Маршрут для просмотра логов администратором
@app.route('/admin/logs')
@login_required
def admin_logs():
    # Проверка прав администратора
    if current_user.id != 1 and current_user.role != 'admin':
        flash('Доступ запрещен!')
        return redirect(url_for('dashboard'))
    
    # В реальном приложении здесь должна быть проверка прав администратора
    logs = UserLog.query.order_by(UserLog.timestamp.desc()).limit(50).all()
    return render_template('admin_logs.html', logs=logs)

# Маршрут для просмотра пользователей (администрирование)
@app.route('/admin/users')
@login_required
def admin_users():
    # Проверка прав администратора 
    if current_user.id != 1 and current_user.role != 'admin':
        flash('Доступ запрещен! Только администратор может просматривать пользователей.')
        return redirect(url_for('dashboard'))
    
    # Получаем всех пользователей
    users = User.query.all()
    
    # Считаем количество действий для каждого пользователя
    user_stats = {}
    for user in users:
        user_stats[user.id] = UserLog.query.filter_by(user_id=user.id).count()
    
    return render_template('admin_users.html', users=users, user_stats=user_stats)

# Маршрут для редактирования пользователя
@app.route('/admin/user/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_user(user_id):
    # Проверка прав администратора
    if current_user.id != 1 and current_user.role != 'admin':
        flash('Доступ запрещен!')
        return redirect(url_for('dashboard'))
    
    # Получаем пользователя для редактирования
    user = User.query.get_or_404(user_id)
    
    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_email = request.form.get('email', '').strip()
        new_role = request.form.get('role', user.role)
        new_password = request.form.get('new_password', '').strip()
        
        # Проверки
        if not new_username:
            flash('Имя пользователя не может быть пустым!')
            return render_template('edit_user.html', user=user)
        
        if not new_email:
            flash('Email не может быть пустым!')
            return render_template('edit_user.html', user=user)
        
        # Проверяем, не занят ли новый username
        if new_username != user.username:
            existing_user = User.query.filter_by(username=new_username).first()
            if existing_user:
                flash('Пользователь с таким именем уже существует!')
                return render_template('edit_user.html', user=user)
        
        # Проверяем, не занят ли новый email
        if new_email != user.email:
            existing_user = User.query.filter_by(email=new_email).first()
            if existing_user:
                flash('Пользователь с таким email уже существует!')
                return render_template('edit_user.html', user=user)
        
        # Проверяем, нельзя ли понизить самого себя
        if user_id == current_user.id and new_role != 'admin':
            flash('Вы не можете понизить свою роль!')
            return render_template('edit_user.html', user=user)
        
        # Сохраняем изменения
        old_username = user.username
        old_email = user.email
        old_role = user.role
        
        user.username = new_username
        user.email = new_email
        user.role = new_role
        
        # Меняем пароль если указан
        if new_password:
            user.set_password(new_password)
        
        db.session.commit()
        
        # Логируем изменение
        changes = []
        if old_username != new_username:
            changes.append(f"username '{old_username}' -> '{new_username}'")
        if old_email != new_email:
            changes.append(f"email '{old_email}' -> '{new_email}'")
        if old_role != new_role:
            changes.append(f"role '{old_role}' -> '{new_role}'")
        if new_password:
            changes.append("пароль изменен")
        
        if changes:
            log_user_action(current_user.id, f"Админ изменил данные пользователя {old_username} (ID: {user_id}): {', '.join(changes)}")
        
        flash(f'Данные пользователя {new_username} успешно обновлены!')
        return redirect(url_for('admin_users'))
    
    return render_template('edit_user.html', user=user)

# Маршрут для удаления пользователя
@app.route('/admin/user/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    # Проверка прав администратора
    if current_user.id != 1 and current_user.role != 'admin':
        flash('Доступ запрещен!')
        return redirect(url_for('dashboard'))
    
    # Нельзя удалить админа (себя)
    if user_id == 1:
        flash('Нельзя удалить администратора!')
        return redirect(url_for('admin_users'))
    
    # Получаем пользователя для удаления
    user = User.query.get_or_404(user_id)
    username = user.username
    
    # Удаляем связанные логи
    UserLog.query.filter_by(user_id=user_id).delete()
    
    # Удаляем пользователя
    db.session.delete(user)
    db.session.commit()
    
    # Логируем удаление
    log_user_action(current_user.id, f"Админ удалил пользователя {username} (ID: {user_id})")
    
    flash(f'Пользователь {username} успешно удален!')
    return redirect(url_for('admin_users'))

# Запуск приложения
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
