#!/usr/bin/env python3
import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def check_duplicates():
    """Verifica duplicatas no banco de dados."""
    try:
        conn = psycopg2.connect(
            host=os.getenv('POSTGRES_HOST'),
            user=os.getenv('POSTGRES_USER'),
            password=os.getenv('POSTGRES_PASSWORD'),
            database=os.getenv('POSTGRES_DB'),
            port=os.getenv('POSTGRES_PORT')
        )
        cursor = conn.cursor()
        
        print("=== VERIFICAÇÃO DE DUPLICATAS NO BANCO DE DADOS ===")
        
        # 1. Verificar duplicatas por ISRC e rádio
        cursor.execute("""
            SELECT name, isrc, COUNT(*) as count 
            FROM music_log 
            WHERE isrc IS NOT NULL AND isrc != '' 
            GROUP BY name, isrc 
            HAVING COUNT(*) > 1 
            ORDER BY count DESC 
            LIMIT 20
        """)
        
        duplicates = cursor.fetchall()
        print(f"\n1. DUPLICATAS POR ISRC E RÁDIO:")
        print(f"   Total de duplicatas encontradas: {len(duplicates)}")
        
        if duplicates:
            print("   Top 20 duplicatas:")
            for i, dup in enumerate(duplicates, 1):
                print(f"   {i:2d}. Rádio: {dup[0][:30]:<30} | ISRC: {dup[1]} | Ocorrências: {dup[2]}")
        else:
            print("   ✅ Nenhuma duplicata encontrada!")
        
        # 2. Verificar duplicatas recentes (últimas 24 horas)
        cursor.execute("""
            SELECT name, isrc, COUNT(*) as count 
            FROM music_log 
            WHERE isrc IS NOT NULL AND isrc != '' 
              AND date >= CURRENT_DATE - INTERVAL '1 day'
            GROUP BY name, isrc 
            HAVING COUNT(*) > 1 
            ORDER BY count DESC 
            LIMIT 10
        """)
        
        recent_duplicates = cursor.fetchall()
        print(f"\n2. DUPLICATAS RECENTES (últimas 24h):")
        print(f"   Total de duplicatas recentes: {len(recent_duplicates)}")
        
        if recent_duplicates:
            print("   Duplicatas recentes:")
            for i, dup in enumerate(recent_duplicates, 1):
                print(f"   {i:2d}. Rádio: {dup[0][:30]:<30} | ISRC: {dup[1]} | Ocorrências: {dup[2]}")
        else:
            print("   ✅ Nenhuma duplicata recente encontrada!")
        
        # 3. Verificar estatísticas gerais
        cursor.execute("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(DISTINCT CONCAT(name, '|', isrc)) as unique_combinations,
                COUNT(*) - COUNT(DISTINCT CONCAT(name, '|', isrc)) as duplicate_count
            FROM music_log 
            WHERE isrc IS NOT NULL AND isrc != ''
        """)
        
        stats = cursor.fetchone()
        print(f"\n3. ESTATÍSTICAS GERAIS:")
        print(f"   Total de registros com ISRC: {stats[0]}")
        print(f"   Combinações únicas (rádio + ISRC): {stats[1]}")
        print(f"   Registros duplicados: {stats[2]}")
        
        if stats[2] > 0:
            duplicate_percentage = (stats[2] / stats[0]) * 100
            print(f"   Percentual de duplicatas: {duplicate_percentage:.2f}%")
        
        # 4. Verificar duplicatas por timestamp próximo (mesmo minuto)
        cursor.execute("""
            SELECT name, isrc, 
                   date, time,
                   COUNT(*) as count
            FROM music_log 
            WHERE isrc IS NOT NULL AND isrc != ''
            GROUP BY name, isrc, date, time
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            LIMIT 10
        """)
        
        time_duplicates = cursor.fetchall()
        print(f"\n4. DUPLICATAS NO MESMO MINUTO:")
        print(f"   Total de duplicatas no mesmo minuto: {len(time_duplicates)}")
        
        if time_duplicates:
            print("   Duplicatas simultâneas:")
            for i, dup in enumerate(time_duplicates, 1):
                print(f"   {i:2d}. Rádio: {dup[0][:30]:<30} | ISRC: {dup[1]} | Minuto: {dup[2]} | Ocorrências: {dup[3]}")
        else:
            print("   ✅ Nenhuma duplicata simultânea encontrada!")
        
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Erro ao verificar duplicatas: {e}")

if __name__ == "__main__":
    check_duplicates()