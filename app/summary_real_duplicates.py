#!/usr/bin/env python3
"""
Resumo das duplicatas reais encontradas no sistema.
"""

import os

import psycopg2
from dotenv import load_dotenv

# Carregar variáveis de ambiente
load_dotenv()

# Configurações do banco de dados
DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
    "database": os.getenv("POSTGRES_DB", "music_log"),
    "user": os.getenv("POSTGRES_USER", "postgres"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
}

# Janela de prevenção de duplicatas (em segundos)
DUPLICATE_PREVENTION_WINDOW = int(os.getenv("DUPLICATE_PREVENTION_WINDOW_SECONDS", 900))


def connect_db():
    """Conecta ao banco de dados PostgreSQL."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Erro ao conectar ao banco: {e}")
        return None


def get_duplicate_summary():
    """Gera resumo das duplicatas reais."""
    conn = connect_db()
    if not conn:
        return

    try:
        cursor = conn.cursor()

        print("=== RESUMO DE DUPLICATAS REAIS ===")
        print(
            f"Janela de prevenção: {DUPLICATE_PREVENTION_WINDOW} segundos ({DUPLICATE_PREVENTION_WINDOW/60:.1f} minutos)"
        )
        print()

        # Contar duplicatas reais (dentro da janela de tempo)
        cursor.execute(
            """
        SELECT COUNT(*) as real_duplicates
        FROM (
            SELECT 
                name, artist, song_title, date,
                EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) as time_diff_seconds
            FROM music_log 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY name, artist, song_title, date
            HAVING COUNT(*) > 1 AND EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) < %s
        ) duplicates;
        """,
            (DUPLICATE_PREVENTION_WINDOW,),
        )

        real_duplicates_count = cursor.fetchone()[0]

        # Contar total de grupos com múltiplas ocorrências
        cursor.execute(
            """
        SELECT COUNT(*) as total_multiple_groups
        FROM (
            SELECT name, artist, song_title, date
            FROM music_log 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY name, artist, song_title, date
            HAVING COUNT(*) > 1
        ) groups;
        """
        )

        total_multiple_groups = cursor.fetchone()[0]

        # Estatísticas por faixa de tempo
        cursor.execute(
            """
        SELECT 
            CASE 
                WHEN time_diff_seconds < 60 THEN '< 1 minuto'
                WHEN time_diff_seconds < 300 THEN '1-5 minutos'
                WHEN time_diff_seconds < 900 THEN '5-15 minutos'
                WHEN time_diff_seconds < 1800 THEN '15-30 minutos'
                WHEN time_diff_seconds < 3600 THEN '30-60 minutos'
                ELSE '> 1 hora'
            END as faixa_tempo,
            COUNT(*) as quantidade
        FROM (
            SELECT 
                EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) as time_diff_seconds
            FROM music_log 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY name, artist, song_title, date
            HAVING COUNT(*) > 1
        ) time_analysis
        GROUP BY 
            CASE 
                WHEN time_diff_seconds < 60 THEN '< 1 minuto'
                WHEN time_diff_seconds < 300 THEN '1-5 minutos'
                WHEN time_diff_seconds < 900 THEN '5-15 minutos'
                WHEN time_diff_seconds < 1800 THEN '15-30 minutos'
                WHEN time_diff_seconds < 3600 THEN '30-60 minutos'
                ELSE '> 1 hora'
            END
        ORDER BY 
            MIN(time_diff_seconds);
        """
        )

        time_distribution = cursor.fetchall()

        print(
            f"🚨 DUPLICATAS REAIS (< {DUPLICATE_PREVENTION_WINDOW/60:.1f} min): {real_duplicates_count:,}"
        )
        print(
            f"📊 TOTAL DE GRUPOS COM MÚLTIPLAS OCORRÊNCIAS: {total_multiple_groups:,}"
        )

        if total_multiple_groups > 0:
            percentage_real = (real_duplicates_count / total_multiple_groups) * 100
            print(f"📈 PORCENTAGEM DE DUPLICATAS REAIS: {percentage_real:.2f}%")

        print("\n=== DISTRIBUIÇÃO POR FAIXA DE TEMPO ===")
        for faixa, quantidade in time_distribution:
            print(f"{faixa}: {quantidade:,} grupos")

        # Top rádios com mais duplicatas reais
        print("\n=== TOP 10 RÁDIOS COM MAIS DUPLICATAS REAIS ===")
        cursor.execute(
            """
        SELECT 
            name as radio_name,
            COUNT(*) as duplicatas_reais
        FROM (
            SELECT 
                name, artist, song_title, date,
                EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) as time_diff_seconds
            FROM music_log 
            WHERE date >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY name, artist, song_title, date
            HAVING COUNT(*) > 1 AND EXTRACT(EPOCH FROM (MAX(time) - MIN(time))) < %s
        ) duplicates
        GROUP BY name
        ORDER BY COUNT(*) DESC
        LIMIT 10;
        """,
            (DUPLICATE_PREVENTION_WINDOW,),
        )

        top_radios = cursor.fetchall()
        for i, (radio, count) in enumerate(top_radios, 1):
            print(f"{i:2d}. {radio}: {count} duplicatas reais")

    except Exception as e:
        print(f"Erro durante a análise: {e}")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    get_duplicate_summary()
