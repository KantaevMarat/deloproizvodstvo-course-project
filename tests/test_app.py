import tempfile
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import register, records, change_status, connect

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / 'test.sqlite'
    def tearDown(self):
        self.tmp.cleanup()
    def create(self):
        return register('Письмо', 'ООО Тест', 'Входящий', 'Секретарь', '2026-10-30', self.db)
    def test_registration_and_search(self):
        self.create()
        self.assertEqual(len(records('Письмо', self.db)), 1)
        self.assertEqual(len(records('Нет', self.db)), 0)
    def test_full_workflow_and_history(self):
        i = self.create()
        change_status(i, 'В работе', self.db)
        change_status(i, 'Исполнен', self.db)
        self.assertEqual(records('', self.db)[0]['status'], 'Исполнен')
        with connect(self.db) as c:
            self.assertEqual(c.execute('SELECT count(*) FROM history').fetchone()[0], 3)
    def test_forbidden_transition(self):
        i = self.create()
        with self.assertRaises(ValueError):change_status(i, 'Исполнен', self.db)
    def test_invalid_date(self):
        with self.assertRaises(ValueError):register('A','B','Входящий','C','2026-02-30',self.db)
    def test_empty_title(self):
        with self.assertRaises(ValueError):register(' ','B','Входящий','C','2026-10-30',self.db)
    def test_unknown_document(self):
        with self.assertRaises(ValueError):change_status(999,'В работе',self.db)
    def test_sql_text_is_data(self):
        register("'; DROP TABLE documents;--",'B','Входящий','C','2026-10-30',self.db)
        self.assertEqual(len(records('', self.db)),1)
if __name__ == '__main__':unittest.main()
