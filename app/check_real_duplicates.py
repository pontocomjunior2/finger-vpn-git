#!/usr/bin/env python3
"""
Script para verificar duplicatas reais no banco de dados.
Duplicatas são consideradas apenas quando a mesma música é identificada
mais de uma vez simultaneamente na MESMA RÁDIO em um intervalo inferior
ao definido em DUPLICATE_PREVENTION_WINDOW_SECONDS.
"""

import os
import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do banco de dados
DB_CONFIG = {
    'host': os.getenv('POSTGRES_HOST', 'localhost'),
    'port': os.getenv('POSTGRES_PORT', '5432'),
    'database': os.getenv('POSTGRES_DB', 'music_log'),
    'user': os.getenv('POSTGRES_USER', 'postgres'),
    'password': os.getenv('POSTGRES_PASSWORD', '')
}

# Janela de prevenção de duplicatas (em segundos)
DUPLICATE_PREVENTION_WINDOW = int(os.getenv('DUPLICATE_PREVENTION_WINDOW_SECONDS', 900))

def connect_db():
    """Conecta ao banco de dados PostgreSQL."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Erro ao conectar ao banco: {e}")
        return None

def check_real_duplicates():
    """Verifica duplicatas reais baseadas na definição correta."""
    conn = connect_db()
    if not conn:
        return
    
    try:
        cursor = conn.cursor()
        
        print("=== VERIFICAÇÃO DE DUPLICATAS REAIS ===")
        print(f"Janela de prevenção: {DUPLICATE_PREVENTION_WINDOW} segundos ({DUPLICATE_PREVENTION_WINDOW/60:.1f} minutos)")
        print()
        
        # Query para encontrar duplicatas reais
        # Músicas da mesma rádio, mesmo artista e título, dentro da janela de tempo
        query = """
        WITH duplicates AS (
            SELECT 
                name as radio_name,
                artist,
                song_title,
                date,
                COUNT(*) as occurrences,
                MIN(time) as first_occurrence,
                MAX(time) as last_occurrence,
                EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) as time_diff_seconds
            FROM music_log 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY name, artist, song_title, date
            HAVING COUNT(*) > 1
        )
        SELECT 
            radio_name,
            artist,
            song_title,
            date,
            occurrences,
            first_occurrence,
            last_occurrence,
            time_diff_seconds
        FROM duplicates 
        WHERE time_diff_seconds < %s
        ORDER BY time_diff_seconds ASC, occurrences DESC
        LIMIT 50;
        """
        
        cursor.execute(query, (DUPLICATE_PREVENTION_WINDOW,))
        real_duplicates = cursor.fetchall()
        
        if real_duplicates:
            print(f"🚨 DUPLICATAS REAIS ENCONTRADAS: {len(real_duplicates)}")
            print()
            
            for i, dup in enumerate(real_duplicates, 1):
                radio, artist, title, date, count, first, last, diff = dup
                print(f"{i}. Rádio: {radio}")
                print(f"   Música: {artist} - {title}")
                print(f"   Data: {date}")
                print(f"   Ocorrências: {count}")
                print(f"   Primeira: {first}")
                print(f"   Última: {last}")
                print(f"   Diferença: {diff:.1f}s ({diff/60:.1f}min)")
                print()
        else:
            print("✅ NENHUMA DUPLICATA REAL ENCONTRADA nos últimos 30 dias!")
            print("O sistema está funcionando corretamente.")
        
        # Estatísticas gerais
        print("\n=== ESTATÍSTICAS GERAIS ===")
        
        # Total de registros únicos por rádio/data
        cursor.execute("""
        SELECT 
            COUNT(*) as total_groups,
            SUM(CASE WHEN cnt > 1 THEN 1 ELSE 0 END) as groups_with_multiple,
            SUM(CASE WHEN cnt > 1 THEN cnt ELSE 0 END) as total_multiple_records
        FROM (
            SELECT 
                name, artist, song_title, date,
                COUNT(*) as cnt
            FROM music_log 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY name, artist, song_title, date
        ) grouped;
        """)
        
        stats = cursor.fetchone()
        total_groups, groups_with_multiple, total_multiple = stats
        
        print(f"Total de grupos únicos (rádio+música+data): {total_groups:,}")
        print(f"Grupos com múltiplas ocorrências: {groups_with_multiple:,}")
        print(f"Total de registros em grupos múltiplos: {total_multiple:,}")
        
        if groups_with_multiple > 0:
            percentage = (groups_with_multiple / total_groups) * 100
            print(f"Porcentagem de grupos com múltiplas ocorrências: {percentage:.2f}%")
        
        # Verificar distribuição de diferenças de tempo
        print("\n=== DISTRIBUIÇÃO DE DIFERENÇAS DE TEMPO ===")
        cursor.execute("""
        SELECT 
            CASE 
                WHEN diff_seconds < 60 THEN '< 1 minuto'
                WHEN diff_seconds < 300 THEN '1-5 minutos'
                WHEN diff_seconds < 900 THEN '5-15 minutos'
                WHEN diff_seconds < 1800 THEN '15-30 minutos'
                WHEN diff_seconds < 3600 THEN '30-60 minutos'
                ELSE '> 1 hora'
            END as time_range,
            COUNT(*) as count
        FROM (
            SELECT 
                EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) as diff_seconds
            FROM music_log 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY name, artist, song_title, date
            HAVING COUNT(*) > 1
        ) time_diffs
        GROUP BY 
            CASE 
                WHEN diff_seconds < 60 THEN '< 1 minuto'
                WHEN diff_seconds < 300 THEN '1-5 minutos'
                WHEN diff_seconds < 900 THEN '5-15 minutos'
                WHEN diff_seconds < 1800 THEN '15-30 minutos'
                WHEN diff_seconds < 3600 THEN '30-60 minutos'
                ELSE '> 1 hora'
            END
        ORDER BY 
            CASE 
                WHEN diff_seconds < 60 THEN 1
                WHEN diff_seconds < 300 THEN 2
                WHEN diff_seconds < 900 THEN 3
                WHEN diff_seconds < 1800 THEN 4
                WHEN diff_seconds < 3600 THEN 5
                ELSE 6
            END;
        """)
        
        time_distribution = cursor.fetchall()
        for time_range, count in time_distribution:
            print(f"{time_range}: {count:,} grupos")
        
    except Exception as e:
        print(f"Erro durante a verificação: {e}")
    finally:
        cursor.close()
        conn.close()

if __name__ == "__main__":
    check_real_duplicates()