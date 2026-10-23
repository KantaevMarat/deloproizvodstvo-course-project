"""Учебная ИС «Делопроизводство». Только локальный однопользовательский запуск."""
import argparse
from contextlib import contextmanager
from datetime import date
from html import escape
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import sqlite3
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent
DB = ROOT / 'documents.sqlite3'


@contextmanager
def connect(db=DB):
    connection = sqlite3.connect(db)
    connection.row_factory = sqlite3.Row
    connection.execute('''CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL, correspondent TEXT NOT NULL,
        kind TEXT NOT NULL, assignee TEXT NOT NULL,
        deadline TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'Новый')''')
    connection.execute('''CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, document_id INTEGER NOT NULL,
        event TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def register(title, correspondent, kind, assignee, deadline, db=DB):
    values = [title.strip(), correspondent.strip(), kind.strip(),
              assignee.strip(), deadline.strip()]
    if any(not value or len(value) > 200 for value in values):
        raise ValueError('Все поля обязательны, длина не более 200 символов.')
    if kind not in {'Входящий', 'Исходящий', 'Внутренний'}:
        raise ValueError('Недопустимый вид документа.')
    date.fromisoformat(deadline)
    with connect(db) as connection:
        cursor = connection.execute('''INSERT INTO documents
            (title, correspondent, kind, assignee, deadline)
            VALUES (?, ?, ?, ?, ?)''', values)
        identifier = cursor.lastrowid
        connection.execute('INSERT INTO history(document_id, event) VALUES (?, ?)',
                           (identifier, 'Зарегистрирован'))
    return identifier


def change_status(identifier, status, db=DB):
    transitions = {'Новый': 'В работе', 'В работе': 'Исполнен'}
    with connect(db) as connection:
        row = connection.execute('SELECT status FROM documents WHERE id=?',
                                 (identifier,)).fetchone()
        if row is None:
            raise ValueError('Документ не найден.')
        if transitions.get(row['status']) != status:
            raise ValueError('Недопустимый переход состояния.')
        connection.execute('UPDATE documents SET status=? WHERE id=?',
                           (status, identifier))
        connection.execute('INSERT INTO history(document_id,event) VALUES (?,?)',
                           (identifier, status))


def records(query='', db=DB):
    with connect(db) as connection:
        return connection.execute('''SELECT * FROM documents
            WHERE instr(lower(title), lower(?)) > 0 ORDER BY id''',
                                  (query,)).fetchall()


def seed():
    if records():
        return
    register('Запрос коммерческого предложения', 'ООО Альфа', 'Входящий',
             'Менеджер', '2026-10-28')
    register('Приказ об инвентаризации', 'Администрация', 'Внутренний',
             'Секретарь', '2026-10-30')
    register('Ответ на запрос', 'ООО Бета', 'Исходящий',
             'Руководитель', '2026-10-25')
    change_status(1, 'В работе')
    change_status(3, 'В работе')
    change_status(3, 'Исполнен')


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query).get('q', [''])[0]
        rows = records(query)
        table = ''
        for row in rows:
            next_status = {'Новый': 'В работе', 'В работе': 'Исполнен'}.get(row['status'])
            action = ''
            if next_status:
                action = (f'<form method="post" action="/status">'
                          f'<input type="hidden" name="id" value="{row["id"]}">'
                          f'<button name="status" value="{next_status}">{next_status}</button></form>')
            table += '<tr>' + ''.join(f'<td>{escape(str(row[key]))}</td>' for key in
                      ['id', 'title', 'kind', 'assignee', 'deadline', 'status']) + f'<td>{action}</td></tr>'
        html = '''<!doctype html><meta charset="utf-8"><title>Делопроизводство</title>
        <style>body{font:16px Arial;background:#f3f5f7;color:#15263a;margin:40px auto;max-width:1200px}
        h1{font-size:32px}table{width:100%;border-collapse:collapse;background:white}
        th,td{text-align:left;padding:14px;border-bottom:1px solid #dce2e8}th{background:#e1e8ef}
        form{margin:12px 0}input,select,button{padding:10px;margin:4px;border:1px solid #adb9c5;border-radius:4px}
        button{background:#174c72;color:white;cursor:pointer}.note{color:#526576}section{margin:25px 0}
        </style><h1>Делопроизводство</h1><p>Регистрация и контроль исполнения документов</p>
        <p class="note">Учебный локальный прототип · Кантаев Марат Эльбрусович · Без многопользовательской авторизации</p>
        <form><input name="q" placeholder="Поиск по теме"><button>Найти</button><a href="/">Все документы</a></form>
        <table><tr><th>№</th><th>Тема</th><th>Вид</th><th>Исполнитель</th><th>Срок</th><th>Статус</th><th>Действие</th></tr>'''
        html += table + '''</table><section><h2>Регистрация документа</h2><form method="post" action="/register">
        <input name="title" placeholder="Тема" required><input name="correspondent" placeholder="Корреспондент" required>
        <select name="kind"><option>Входящий</option><option>Исходящий</option><option>Внутренний</option></select>
        <input name="assignee" placeholder="Исполнитель" required><input name="deadline" type="date" required>
        <button>Зарегистрировать</button></form></section><p class="note">Последовательность: Новый → В работе → Исполнен. Все изменения сохраняются в журнале.</p>'''
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(html.encode('utf8'))

    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 10000:
                raise ValueError('Неверный размер запроса.')
            data = {key: value[0] for key, value in parse_qs(
                self.rfile.read(length).decode('utf8')).items()}
            if self.path == '/register':
                register(*(data[key] for key in
                           ['title', 'correspondent', 'kind', 'assignee', 'deadline']))
            elif self.path == '/status':
                change_status(int(data['id']), data['status'])
            else:
                raise ValueError('Неизвестная операция.')
        except (ValueError, KeyError) as error:
            self.send_error(400, 'Invalid input', str(error))
            return
        self.send_response(303)
        self.send_header('Location', '/')
        self.end_headers()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    seed()
    print(f'Откройте http://127.0.0.1:{args.port}', flush=True)
    HTTPServer(('127.0.0.1', args.port), Handler).serve_forever()

