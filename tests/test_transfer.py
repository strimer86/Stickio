"""Экспорт/импорт заметок и ручные копии базы (services/transfer.py)."""
import json
import os
import tempfile
import unittest

from database.database import Database
from models.note import Note
from services import transfer


def make_note(note_id=1, content="<p>привет</p>", **overrides):
    fields = dict(
        id=note_id,
        content=content,
        background_color="#AABBCC",
        text_color="#112233",
        font_size=22,
        bold=True,
        opacity=0.8,
        x=300,
        y=400,
        width=420,
        height=260,
    )
    fields.update(overrides)
    return Note(**fields)


class BuildExportTests(unittest.TestCase):
    def test_export_carries_all_visual_fields(self):
        data = transfer.build_export([make_note()])
        self.assertEqual(data["format"], "stickio-notes")
        self.assertEqual(data["version"], transfer.EXPORT_VERSION)

        record = data["notes"][0]
        for name in transfer.EXPORT_FIELDS:
            self.assertIn(name, record)
        self.assertEqual(record["background_color"], "#AABBCC")
        self.assertEqual(record["font_size"], 22)
        self.assertTrue(record["bold"])

    def test_id_is_not_exported(self):
        # id первичный ключ: при импорте заметки должны стать новыми, иначе
        # они конфликтовали бы с уже существующими.
        record = transfer.build_export([make_note(note_id=77)])["notes"][0]
        self.assertNotIn("id", record)

    def test_export_is_json_serialisable(self):
        text = json.dumps(transfer.build_export([make_note()]), ensure_ascii=False)
        self.assertIn("привет", text)


class ParseExportTests(unittest.TestCase):
    def test_round_trip_preserves_values(self):
        original = make_note()
        data = json.loads(
            json.dumps(transfer.build_export([original]), ensure_ascii=False)
        )
        (fields,) = transfer.parse_export(data)
        for name in transfer.EXPORT_FIELDS:
            self.assertEqual(fields[name], getattr(original, name), name)

    def test_foreign_json_rejected(self):
        with self.assertRaises(transfer.TransferError):
            transfer.parse_export({"notes": []})
        with self.assertRaises(transfer.TransferError):
            transfer.parse_export([1, 2, 3])

    def test_newer_version_rejected(self):
        data = transfer.build_export([make_note()])
        data["version"] = transfer.EXPORT_VERSION + 1
        with self.assertRaises(transfer.TransferError) as ctx:
            transfer.parse_export(data)
        self.assertIn("более новой версией", str(ctx.exception))

    def test_empty_file_rejected(self):
        data = transfer.build_export([])
        with self.assertRaises(transfer.TransferError):
            transfer.parse_export(data)

    def test_broken_value_rejected(self):
        data = transfer.build_export([make_note()])
        data["notes"][0]["font_size"] = "большой"
        with self.assertRaises(transfer.TransferError) as ctx:
            transfer.parse_export(data)
        self.assertIn("font_size", str(ctx.exception))

    def test_missing_optional_fields_get_defaults(self):
        # Файл от старой версии может не знать про какие-то поля — импорт
        # обязан работать, подставив умолчания модели.
        fields = transfer.note_from_dict({"content": None})
        self.assertEqual(fields, {"content": ""})

    def test_read_from_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "notes.json")
            transfer.write_text(
                path,
                json.dumps(transfer.build_export([make_note()]), ensure_ascii=False),
            )
            (fields,) = transfer.read_export_file(path)
            self.assertEqual(fields["background_color"], "#AABBCC")

    def test_read_garbage_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "notes.json")
            transfer.write_text(path, "не json")
            with self.assertRaises(transfer.TransferError):
                transfer.read_export_file(path)

    def test_read_missing_file(self):
        with self.assertRaises(transfer.TransferError):
            transfer.read_export_file(os.path.join("нет", "такого.json"))


class HtmlExportTests(unittest.TestCase):
    def test_plain_text_strips_html(self):
        text = transfer.plain_text("<p>первая</p><p>вторая</p>")
        self.assertIn("первая", text)
        self.assertIn("вторая", text)
        self.assertNotIn("<p>", text)

    def test_html_escapes_user_text(self):
        # В заметке может быть что угодно — вставленный HTML не должен
        # исполняться в браузере.
        markup = transfer.build_html(
            [make_note(content="<p>&lt;script&gt;alert(1)&lt;/script&gt;</p>")]
        )
        self.assertNotIn("<script>", markup)
        self.assertIn("&lt;script&gt;", markup)

    def test_html_has_one_card_per_note(self):
        markup = transfer.build_html([make_note(1), make_note(2, content="<p>два</p>")])
        self.assertEqual(markup.count('class="note"'), 2)

    def test_empty_note_marked(self):
        markup = transfer.build_html([make_note(content="")])
        self.assertIn("(пусто)", markup)


class BackupTests(unittest.TestCase):
    def test_backup_copies_notes(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Database(path=os.path.join(tmp, "notes.db"))
            try:
                note_id = db.create_note(content="<p>важное</p>")
                dest = os.path.join(tmp, "copy.db")
                transfer.backup_database(db, dest)
            finally:
                db.close()

            copy = Database(path=dest)
            try:
                notes = copy.get_all_notes()
                self.assertEqual([n.id for n in notes], [note_id])
                self.assertEqual(notes[0].content, "<p>важное</p>")
            finally:
                copy.close()


class DefaultNameTests(unittest.TestCase):
    def test_default_name_has_date_and_extension(self):
        name = transfer.default_export_name("json")
        self.assertTrue(name.startswith("Stickio_"))
        self.assertTrue(name.endswith(".json"))


if __name__ == "__main__":
    unittest.main()
