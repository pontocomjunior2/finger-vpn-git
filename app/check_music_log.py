#!/usr/bin/env python3

import os

import psycopg2
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do banco de dados
DB_HOST = os.getenv("POSTGRES_HOST")
DB_USER = os.getenv("POSTGRES_USER")
DB_PASSWORD = os.getenv("POSTGRES_PASSWORD")
DB_NAME = os.getenv("POSTGRES_DB")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")

# Conectar ao banco de dados
conn = psycopg2.connect(
    host=DB_HOST,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME,
    port=DB_PORT
)

# Criar cursor
cur = conn.cursor()

# Executar consulta para obter os últimos 100 registros
print("\nConsultando os últimos 100 registros da tabela music_log...")
cur.execute("""
    SELECT date, time, name, artist, song_title 
    FROM music_log 
    ORDER BY date DESC, time DESC 
    LIMIT 100
""")

# Exibir resultados
rows = cur.fetchall()
if rows:
    print(f"\nÚltimos {len(rows)} registros:")
    for i, row in enumerate(rows, 1):
        print(f"{i}. Data: {row[0]}, Hora: {row[1]}, Rádio: {row[2]}, Artista: {row[3]}, Música: {row[4]}")
else:
    print("Nenhum registro encontrado.")

# Fechar conexão
cur.close()
conn.close()