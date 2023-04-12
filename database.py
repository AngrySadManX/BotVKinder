import psycopg2


class Database:
    def __init__(self, dbname, user, password, host, port):
        self.dbname = dbname
        self.user = user
        self.password = password
        self.host = host
        self.port = port
        self.conn = None

    def connect(self):
        self.conn = psycopg2.connect(
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port
        )

    def create_table(self):
        self.connect()
        cur = self.conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS candidate (id serial PRIMARY KEY, vk_id integer UNIQUE, '
                    'vk_url varchar);')
        self.conn.commit()
        cur.close()

    def save_candidate(self, vk_id, vk_url):
        self.connect()
        cur = self.conn.cursor()
        cur.execute('INSERT INTO candidate (vk_id, vk_url) VALUES (%s, %s);', (vk_id, vk_url))
        self.conn.commit()
        cur.close()

    def check_candidate(self, vk_id):
        self.connect()
        cur = self.conn.cursor()
        cur.execute('SELECT vk_id FROM candidate WHERE vk_id = %s', (vk_id,))
        result = cur.fetchone()
        cur.close()
        if result:
            return True
        else:
            return False

    def delete_table(self):
        self.connect()
        cur = self.conn.cursor()
        cur.execute('DROP TABLE IF EXISTS candidate;')
        self.conn.commit()
        cur.close()

    def disconnect(self):
        self.conn.close()
