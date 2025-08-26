import psycopg2


def test_streams():
    conn = psycopg2.connect(
        host='104.234.173.96',
        user='postgres',
        password='Conquista@@2',
        database='music_log',
        port=5432
    )
    
    cur = conn.cursor()
    
    # Contar total de streams
    cur.execute('SELECT COUNT(*) as total_streams FROM streams;')
    total = cur.fetchone()[0]
    print(f'Total de streams disponíveis: {total}')
    
    # Mostrar alguns exemplos
    cur.execute('SELECT id, name, url FROM streams LIMIT 5;')
    print('\nExemplos de streams:')
    for row in cur.fetchall():
        print(f'ID: {row[0]}, Nome: {row[1]}, URL: {row[2]}')
    
    conn.close()

if __name__ == '__main__':
    test_streams()