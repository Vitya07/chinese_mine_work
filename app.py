from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

# Инициализация приложения
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key'  # Для управления сессиями
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'  # SQLite для простоты
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'  # Перенаправление на страницу входа, если неавторизован

### Модели

# Пользователь
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    documents = db.relationship('Document', backref='owner', lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# Слово
class Word(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    word = db.Column(db.String(100), nullable=False)
    meaning = db.Column(db.String(500), nullable=False)
    character_id = db.Column(db.Integer, db.ForeignKey('character.id'), nullable=False)

# Документ
class Document(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    characters = db.relationship('Character', backref='document', lazy=True)  # Связь с иероглифами

# Уникальные иероглифы
class Character(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    symbol = db.Column(db.String(1), nullable=False)  # Один символ (иероглиф)
    document_id = db.Column(db.Integer, db.ForeignKey('document.id'), nullable=False)
    is_new = db.Column(db.Boolean, default=True)  # Новый атрибут
    created_at = db.Column(db.DateTime, default=datetime.utcnow)  # Время создания
    
### Вспомогательные функции
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def extract_unique_characters(text):
    # Извлекаем все уникальные иероглифы, игнорируя пробелы и запятые
    return set(char for char in text if char.strip())

### Маршруты

# Главная страница
@app.route('/')
@login_required
def home():
    documents = Document.query.filter_by(user_id=current_user.id).all()
    return render_template('home.html', documents=documents)

# Регистрация
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if User.query.filter_by(username=username).first():
            flash('Имя пользователя уже существует')
            return redirect(url_for('register'))

        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash('Регистрация успешна! Войдите в систему.')
        return redirect(url_for('login'))
    
    return render_template('register.html')

# Вход
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('home'))
        flash('Неправильное имя пользователя или пароль')
    
    return render_template('login.html')

# Выход
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# Создание документа
@app.route('/document/create', methods=['GET', 'POST'])
@login_required
def create_document():
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        new_document = Document(title=title, content=content, user_id=current_user.id)
        db.session.add(new_document)
        db.session.commit()

        # Извлекаем и сохраняем уникальные иероглифы
        characters = extract_unique_characters(content)
        for char in characters:
            new_char = Character(symbol=char, document_id=new_document.id)
            db.session.add(new_char)

        db.session.commit()
        flash('Документ успешно создан!')
        return redirect(url_for('home'))
    
    return render_template('create_document.html')

# Просмотр документа
@app.route('/document/view/<int:doc_id>', methods=['GET'])
@login_required
def view_document(doc_id):
    document = Document.query.get_or_404(doc_id)

    # Проверяем, что текущий пользователь — владелец документа
    if document.owner != current_user:
        flash('У вас нет прав на просмотр этого документа.')
        return redirect(url_for('home'))

    # Очищаем содержание от пробелов и запятых
    cleaned_content = document.content.replace(' ', '').replace(',', '')

    # Получаем уникальные иероглифы из очищенного содержания, сохраняя порядок
    unique_characters = []
    seen = set()
    for char in cleaned_content:
        if char not in seen:
            seen.add(char)
            unique_characters.append(char)

    new_chars = []
    old_chars = []

    # Определяем, какие иероглифы новые
    for symbol in unique_characters:
        char = Character.query.filter_by(symbol=symbol, document_id=doc_id).first()
        if char:
            # Проверяем, если у иероглифа есть атрибут created_at
            if hasattr(char, 'created_at'):
                char.is_new = (char.created_at > datetime.utcnow() - timedelta(days=1))
            else:
                char.is_new = False  # или другое значение по умолчанию, если created_at отсутствует
            
            if char.is_new:
                new_chars.append(char)
            else:
                old_chars.append(char)

    return render_template('view_document.html', document=document, new_chars=new_chars, old_chars=old_chars)

#Редактирование документа
@app.route('/document/edit/<int:doc_id>', methods=['GET', 'POST'])
@login_required
def edit_document(doc_id):
    document = Document.query.get_or_404(doc_id)

    # Проверяем, что текущий пользователь — владелец документа
    if document.owner != current_user:
        flash('У вас нет прав на редактирование этого документа.')
        return redirect(url_for('home'))

    if request.method == 'POST':
        # Получаем данные из формы
        title = request.form.get('title')
        content = request.form.get('content')

        # Проверка наличия необходимых данных
        if title and content:
            document.title = title
            document.content = content

            # Обновляем иероглифы
            Character.query.filter_by(document_id=doc_id).delete()
            unique_characters = []
            seen = set()
            for char in content:
                if char not in seen and char.strip():  # Игнорируем пробелы
                    seen.add(char)
                    unique_characters.append(char)

            for char in unique_characters:
                new_char = Character(symbol=char, document_id=doc_id)
                db.session.add(new_char)

            db.session.commit()
            flash('Документ успешно обновлён!')
            return redirect(url_for('view_document', doc_id=doc_id))  # Переход на страницу просмотра документа
        else:
            flash('Пожалуйста, заполните все поля.')

    return render_template('edit_document.html', document=document)




# Удаление документа
@app.route('/document/delete/<int:doc_id>', methods=['POST', 'GET'])
@login_required
def delete_document(doc_id):
    document = Document.query.get_or_404(doc_id)

    # Проверяем, что текущий пользователь — владелец документа
    if document.owner != current_user:
        flash('У вас нет прав на удаление этого документа.')
        return redirect(url_for('home'))

    if request.method == 'POST':
        # Удаляем все связанные иероглифы перед удалением документа
        Character.query.filter_by(document_id=doc_id).delete()
        db.session.delete(document)
        db.session.commit()
        flash('Документ успешно удалён!')
        return redirect(url_for('home'))

    return render_template('confirm_delete.html', document=document)  # Отправка на страницу подтверждения удаления


# Добавление слова
@app.route('/word/add', methods=['GET', 'POST'])
@login_required
def add_word():
    if request.method == 'POST':
        word = request.form['word']
        meaning = request.form['meaning']
        character_symbol = request.form['character']

        # Создаём новый иероглиф
        new_character = Character(symbol=character_symbol, document_id=None)  # Привязка к документу не нужна на этом этапе
        db.session.add(new_character)
        db.session.commit()

        new_word = Word(word=word, meaning=meaning, character_id=new_character.id)
        db.session.add(new_word)
        db.session.commit()
        flash('Слово успешно добавлено!')
        return redirect(url_for('home'))

    return render_template('add_word.html')

@app.route('/document/<int:doc_id>/delete_characters', methods=['POST'])
@login_required
def delete_characters(doc_id):
    document = Document.query.get_or_404(doc_id)

    # Проверяем, что текущий пользователь — владелец документа
    if document.owner != current_user:
        flash('У вас нет прав на удаление иероглифов из этого документа.')
        return redirect(url_for('view_document', doc_id=doc_id))

    characters_to_delete = request.form.getlist('characters_to_delete')

    if characters_to_delete:
        # Список всех символов, которые мы собираемся удалить
        symbols_to_delete = []
        for char_id in characters_to_delete:
            char = Character.query.get(char_id)
            if char and char.document_id == doc_id:
                symbols_to_delete.append(char.symbol)
                
                # Удаляем связанные слова
                words_to_delete = Word.query.filter_by(character_id=char.id).all()
                for word in words_to_delete:
                    db.session.delete(word)  # Удаляем слово
                
                db.session.delete(char)  # Удаляем иероглиф

        db.session.commit()  # Подтверждаем изменения
        flash('Выбранные иероглифы и их слова успешно удалены.')

        # Обновляем содержание документа
        update_document_content(document, symbols_to_delete)

    else:
        flash('Ничего не выбрано для удаления.')

    return redirect(url_for('view_document', doc_id=doc_id))

def update_document_content(document, symbols_to_delete):
    # Получаем текущее содержание документа
    current_content = document.content

    # Удаляем иероглифы из содержания
    for symbol in symbols_to_delete:
        current_content = current_content.replace(symbol, '')

    # Удаляем лишние пробелы
    current_content = ' '.join(current_content.split())

    # Обновляем содержание документа
    document.content = current_content
    db.session.commit()  # Сохраняем изменения в документе


### Запуск приложения
