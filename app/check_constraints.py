#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def check_constraints():
    """Verifica as constraints da tabela music_log."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD'),
            database=os.getenv('POSTGRES_DB'),
            port=os.getenv('POSTGRES_PORT')
        )
        cursor = conn.cursor()
        
        print("=== CONSTRAINTS DA TABELA music_log ===")
        
        # Verificar constraints
        cursor.execute("""
            SELECT conname, contype, pg_get_constraintdef(oid) 
            FROM pg_constraint 
            WHERE conrelid = 'music_log'::regclass
        """)
        
        constraints = cursor.fetchall()
        
        if constraints:
            print("Constraints encontradas:")
            for i, constraint in enumerate(constraints, 1):
                print(f"  {i}. Nome: {constraint[0]}")
                print(f"     Tipo: {constraint[1]}")
                print(f"     Definição: {constraint[2]}")
                print()
        else:
            print("Nenhuma constraint encontrada.")
        
        # Verificar índices
        print("=== ÍNDICES DA TABELA music_log ===")
        cursor.execute("""
            SELECT indexname, indexdef 
            FROM pg_indexes 
            WHERE tablename = 'music_log'
        """)
        
        indexes = cursor.fetchall()
        
        if indexes:
            print("Índices encontrados:")
            for i, index in enumerate(indexes, 1):
                print(f"  {i}. Nome: {index[0]}")
                print(f"     Definição: {index[1]}")
                print()
        else:
            print("Nenhum índice encontrado.")
        
        # Verificar algumas duplicatas específicas
        print("=== ANÁLISE DE DUPLICATAS ESPECÍFICAS ===")
        cursor.execute("""
            SELECT name, artist, song_title, date, time, COUNT(*) as count
            FROM music_log 
            WHERE name = 'Top FM 104,1 - SP' 
              AND isrc = 'ISRC não disponível'
            GROUP BY name, artist, song_title, date, time
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            LIMIT 5
        """)
        
        specific_dups = cursor.fetchall()
        
        if specific_dups:
            print("Duplicatas específicas encontradas:")
            for dup in specific_dups:
                print(f"  Rádio: {dup[0]}")
                print(f"  Artista: {dup[1]}")
                print(f"  Música: {dup[2]}")
                print(f"  Data: {dup[3]} | Hora: {dup[4]}")
                print(f"  Ocorrências: {dup[5]}")
                print()
        else:
            print("Nenhuma duplicata específica encontrada para análise.")
        
        # Verificar se a constraint UNIQUE está funcionando
        print("=== TESTE DE CONSTRAINT UNIQUE ===")
        try:
            # Tentar inserir um registro duplicado
            cursor.execute("""
                INSERT INTO music_log (name, artist, song_title, date, time)
                VALUES ('TESTE_CONSTRAINT', 'TESTE_ARTIST', 'TESTE_SONG', CURRENT_DATE, CURRENT_TIME)
            """)
            
            # Tentar inserir o mesmo registro novamente
            cursor.execute("""
                INSERT INTO music_log (name, artist, song_title, date, time)
                VALUES ('TESTE_CONSTRAINT', 'TESTE_ARTIST', 'TESTE_SONG', CURRENT_DATE, CURRENT_TIME)
            """)
            
            print("⚠️  ATENÇÃO: Constraint UNIQUE não está funcionando! Inserção duplicada foi permitida.")
            
            # Limpar registros de teste
            cursor.execute("DELETE FROM music_log WHERE name = 'TESTE_CONSTRAINT'")
            conn.commit()
            
        except psycopg2.IntegrityError as e:
            print("✅ Constraint UNIQUE está funcionando corretamente.")
            print(f"   Erro capturado: {e}")
            conn.rollback()
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Erro ao verificar constraints: {e}")

if __name__ == "__main__":
    check_constraints()