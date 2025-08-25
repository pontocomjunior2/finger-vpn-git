#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

def analyze_duplicates_history():
    """Analisa o histórico de duplicatas para entender sua origem."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD'),
            database=os.getenv('POSTGRES_DB'),
            port=os.getenv('POSTGRES_PORT')
        )
        cursor = conn.cursor()
        
        print("=== ANÁLISE HISTÓRICA DE DUPLICATAS ===")
        
        # 1. Verificar quando as constraints foram criadas
        print("\n1. VERIFICANDO HISTÓRICO DE CONSTRAINTS:")
        cursor.execute("""
            SELECT schemaname, tablename, attname, n_distinct, correlation
            FROM pg_stats 
            WHERE tablename = 'music_log' 
              AND attname IN ('name', 'artist', 'song_title', 'isrc')
            ORDER BY attname
        """)
        
        stats = cursor.fetchall()
        if stats:
            print("Estatísticas das colunas:")
            for stat in stats:
                print(f"  {stat[2]}: {stat[3]} valores distintos")
        
        # 2. Analisar distribuição temporal das duplicatas
        print("\n2. DISTRIBUIÇÃO TEMPORAL DAS DUPLICATAS:")
        cursor.execute("""
            WITH duplicates AS (
                SELECT name, isrc, date, COUNT(*) as count
                FROM music_log 
                WHERE isrc IS NOT NULL AND isrc != ''
                GROUP BY name, isrc, date
                HAVING COUNT(*) > 1
            )
            SELECT 
                DATE_TRUNC('month', date) as month,
                COUNT(*) as duplicate_days,
                SUM(count) as total_duplicates
            FROM duplicates
            GROUP BY DATE_TRUNC('month', date)
            ORDER BY month DESC
            LIMIT 12
        """)
        
        temporal_dist = cursor.fetchall()
        if temporal_dist:
            print("Distribuição por mês:")
            for dist in temporal_dist:
                print(f"  {dist[0].strftime('%Y-%m')}: {dist[1]} dias com duplicatas, {dist[2]} duplicatas totais")
        
        # 3. Verificar se há diferenças nos campos que não estão na constraint
        print("\n3. ANÁLISE DE CAMPOS NÃO INCLUÍDOS NA CONSTRAINT:")
        cursor.execute("""
            SELECT name, artist, song_title, date, time,
                   COUNT(*) as count,
                   COUNT(DISTINCT isrc) as distinct_isrcs,
                   COUNT(DISTINCT identified_by) as distinct_identified_by,
                   COUNT(DISTINCT cidade) as distinct_cidades
            FROM music_log 
            WHERE name = 'Top FM 104,1 - SP'
            GROUP BY name, artist, song_title, date, time
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            LIMIT 5
        """)
        
        field_analysis = cursor.fetchall()
        if field_analysis:
            print("Registros com mesma chave única mas campos diferentes:")
            for analysis in field_analysis:
                print(f"  {analysis[1]} - {analysis[2]} ({analysis[3]} {analysis[4]})")
                print(f"    Ocorrências: {analysis[5]} | ISRCs distintos: {analysis[6]} | Identified_by distintos: {analysis[7]} | Cidades distintas: {analysis[8]}")
        else:
            print("  ✅ Não há registros com mesma chave única mas campos diferentes.")
        
        # 4. Verificar se há registros com ISRC NULL vs não-NULL
        print("\n4. ANÁLISE DE REGISTROS COM ISRC NULL vs NÃO-NULL:")
        cursor.execute("""
            SELECT name, artist, song_title, date, time,
                   COUNT(*) as total_count,
                   COUNT(CASE WHEN isrc IS NULL OR isrc = '' THEN 1 END) as null_isrc_count,
                   COUNT(CASE WHEN isrc IS NOT NULL AND isrc != '' THEN 1 END) as non_null_isrc_count
            FROM music_log 
            WHERE name = 'Top FM 104,1 - SP'
            GROUP BY name, artist, song_title, date, time
            HAVING COUNT(*) > 1
               AND COUNT(CASE WHEN isrc IS NULL OR isrc = '' THEN 1 END) > 0
               AND COUNT(CASE WHEN isrc IS NOT NULL AND isrc != '' THEN 1 END) > 0
            ORDER BY total_count DESC
            LIMIT 5
        """)
        
        null_analysis = cursor.fetchall()
        if null_analysis:
            print("Registros com ISRC NULL e não-NULL:")
            for analysis in null_analysis:
                print(f"  {analysis[1]} - {analysis[2]} ({analysis[3]} {analysis[4]})")
                print(f"    Total: {analysis[5]} | NULL: {analysis[6]} | Não-NULL: {analysis[7]}")
        else:
            print("  ✅ Não há registros mistos (NULL e não-NULL) para mesma chave.")
        
        # 5. Verificar padrões de ISRC
        print("\n5. ANÁLISE DE PADRÕES DE ISRC:")
        cursor.execute("""
            SELECT isrc, COUNT(*) as count, COUNT(DISTINCT name) as distinct_radios
            FROM music_log 
            WHERE isrc IS NOT NULL AND isrc != ''
            GROUP BY isrc
            ORDER BY count DESC
            LIMIT 10
        """)
        
        isrc_patterns = cursor.fetchall()
        if isrc_patterns:
            print("Top 10 ISRCs mais frequentes:")
            for pattern in isrc_patterns:
                print(f"  {pattern[0]}: {pattern[1]} ocorrências em {pattern[2]} rádios")
        
        # 6. Verificar se há problema com encoding ou caracteres especiais
        print("\n6. ANÁLISE DE CARACTERES ESPECIAIS:")
        cursor.execute("""
            SELECT name, artist, song_title, 
                   LENGTH(name) as name_len,
                   LENGTH(artist) as artist_len,
                   LENGTH(song_title) as title_len,
                   COUNT(*) as count
            FROM music_log 
            WHERE (name LIKE '%  %' OR artist LIKE '%  %' OR song_title LIKE '%  %')
               OR (name != TRIM(name) OR artist != TRIM(artist) OR song_title != TRIM(song_title))
            GROUP BY name, artist, song_title
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            LIMIT 5
        """)
        
        encoding_issues = cursor.fetchall()
        if encoding_issues:
            print("Possíveis problemas de encoding/espaços:")
            for issue in encoding_issues:
                print(f"  '{issue[0]}' - '{issue[1]}' - '{issue[2]}'")
                print(f"    Tamanhos: {issue[3]}, {issue[4]}, {issue[5]} | Ocorrências: {issue[6]}")
        else:
            print("  ✅ Não há problemas aparentes de encoding ou espaços extras.")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Erro ao analisar histórico de duplicatas: {e}")

if __name__ == "__main__":
    analyze_duplicates_history()