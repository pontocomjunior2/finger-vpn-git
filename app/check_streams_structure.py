#!/usr/bin/env python3
import psycopg2


def check_streams_structure():
    conn = psycopg2.connect(
        host='104.234.173.96',
        user='postgres',
        password='Conquista@@2',
        database='music_log',
        port=5432
    )
    
    cur = conn.cursor()
    
    # Verificar estrutura da tabela
    cur.execute("""
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns 
        WHERE table_name = 'streams' 
        ORDER BY ordinal_position
    """)
    
    print('Estrutura da tabela streams:')
    print('Campo | Tipo | Tamanho | Nullable')
    print('-' * 40)
    for row in cur.fetchall():
        column_name, data_type, max_length, nullable = row
        length_str = f'({max_length})' if max_length else ''
        print(f'{column_name} | {data_type}{length_str} | {nullable}')
    
    # Verificar alguns registros para entender os dados
    print('\nExemplos de dados:')
    cur.execute('SELECT * FROM streams LIMIT 3')
    rows = cur.fetchall()
    
    # Obter nomes das colunas
    cur.execute("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name = 'streams' 
        ORDER BY ordinal_position
    """)
    columns = [row[0] for row in cur.fetchall()]
    
    print('Colunas:', ', '.join(columns))
    for i, row in enumerate(rows):
        print(f'Registro {i+1}:', dict(zip(columns, row)))
    
    conn.close()

if __name__ == '__main__':
    check_streams_structure()