import sqlite3

from dbutil import connect

class SequenceManager:
    def __init__(self, db_path):
        self.db_path = db_path

    def get_or_create_sequence(self, name):
        """Return the ID for a named sequence, creating it if needed."""
        return self.create_sequence(name)

    def create_sequence(self, name):
        """Create a new sequence container."""
        conn = connect(self.db_path)
        cur = conn.cursor()
        try:
            cur.execute("INSERT INTO sequences (name) VALUES (?)", (name,))
            seq_id = cur.lastrowid
            conn.commit()
            return seq_id
        except sqlite3.IntegrityError:
            cur.execute("SELECT id FROM sequences WHERE name = ?", (name,))
            return cur.fetchone()[0]
        finally:
            conn.close()

    def add_step(self, sequence_id, step_num, template_path, delay_hours, subject=""):
        """Add or update a step in the sequence."""
        conn = connect(self.db_path)
        cur = conn.cursor()
        # Check if exists
        cur.execute("SELECT id FROM sequence_steps WHERE sequence_id = ? AND step_number = ?", (sequence_id, step_num))
        row = cur.fetchone()
        
        if row:
            cur.execute("""
                UPDATE sequence_steps 
                SET template_path = ?, delay_hours = ?, subject = ?
                WHERE id = ?
            """, (template_path, delay_hours, subject, row[0]))
        else:
            cur.execute("""
                INSERT INTO sequence_steps (sequence_id, step_number, template_path, delay_hours, subject)
                VALUES (?, ?, ?, ?, ?)
            """, (sequence_id, step_num, template_path, delay_hours, subject))
            
        conn.commit()
        conn.close()

    def get_sequence_steps(self, sequence_id):
        """Fetch all steps for a sequence, ordered by step_number."""
        conn = connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM sequence_steps WHERE sequence_id = ? ORDER BY step_number ASC", (sequence_id,))
        steps = [dict(r) for r in cur.fetchall()]
        conn.close()
        return steps

    def get_sequences(self):
        conn = connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT * FROM sequences")
        rows = cur.fetchall()
        conn.close()
        return rows

    def get_sequence_steps_count(self, sequence_id):
        conn = connect(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sequence_steps WHERE sequence_id = ?", (sequence_id,))
        count = cur.fetchone()[0]
        conn.close()
        return count
