#!/usr/bin/env python3
"""
Script para corrigir o problema de transação abortada na função check_log_table()

O problema ocorre quando check_log_table() deixa uma transação em estado abortado,
causando erro "current transaction is aborted" na próxima operação (create_distribution_tables).
"""

import os
import sys
import re
from pathlib import Path

def fix_check_log_table_function():
    """
    Corrige a função check_log_table() para melhor gerenciamento de transações
    """
    fingerv7_path = Path("d:/dataradio/finger_vpn/app/fingerv7.py")
    
    if not fingerv7_path.exists():
        print(f"Erro: Arquivo {fingerv7_path} não encontrado")
        return False
    
    # Ler o arquivo
    with open(fingerv7_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Backup do arquivo original
    backup_path = fingerv7_path.with_suffix('.py.backup')
    with open(backup_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Backup criado: {backup_path}")
    
    # Encontrar e substituir a função check_log_table
    # Padrão para encontrar a função completa
    pattern = r'(def check_log_table\(\):.*?)(except Exception as e:.*?logger\.error\(.*?return False)'
    
    # Nova implementação com melhor gerenciamento de transações
    new_function = '''def check_log_table():
    logger.info(
        f"Verificando se a tabela de logs '{DB_TABLE_NAME}' existe no banco de dados..."
    )
    conn = None
    try:
        conn = get_db_pool().get_connection_sync()
        with conn.cursor() as cursor:
            # Verificar se a tabela existe
            cursor.execute(
                f"SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = '{DB_TABLE_NAME}')"
            )
            table_exists = cursor.fetchone()[0]

            if not table_exists:
                logger.error(
                    f"A tabela de logs '{DB_TABLE_NAME}' não existe no banco de dados!"
                )
                # Listar tabelas disponíveis
                cursor.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
                )
                tables = [row[0] for row in cursor.fetchall()]
                logger.info(f"Tabelas disponíveis no banco: {tables}")

                # Criar tabela automaticamente para evitar erros
                try:
                    logger.info(
                        f"Tentando criar a tabela '{DB_TABLE_NAME}' automaticamente..."
                    )
                    # Corrigir a formatação da string SQL multi-linha
                    create_table_sql = """
CREATE TABLE {} (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,
    time TIME NOT NULL,
    name VARCHAR(255) NOT NULL,
    artist VARCHAR(255) NOT NULL,
    song_title VARCHAR(255) NOT NULL,
    isrc VARCHAR(50),
    cidade VARCHAR(100),
    estado VARCHAR(50),
    regiao VARCHAR(50),
    segmento VARCHAR(100),
    label VARCHAR(255),
    genre VARCHAR(100),
    identified_by VARCHAR(10),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
                    """.format(
                        DB_TABLE_NAME
                    )  # Usar .format() para inserir o nome da tabela
                    cursor.execute(create_table_sql)
                    conn.commit()
                    logger.info(f"Tabela '{DB_TABLE_NAME}' criada com sucesso!")
                    return True
                except Exception as e:
                    logger.error(f"Erro ao criar a tabela '{DB_TABLE_NAME}': {e}")
                    try:
                        conn.rollback()
                    except Exception:
                        pass  # Ignorar erros de rollback
                    logger.info(
                        "Considere criar a tabela manualmente com o seguinte comando SQL:"
                    )
                    return False
            else:
                # Verificar as colunas da tabela (garantir indentação correta aqui)
                cursor.execute(
                    f"SELECT column_name, data_type, column_default FROM information_schema.columns WHERE table_name = '{DB_TABLE_NAME}'"
                )
                columns_info = {
                    row[0].lower(): {"type": row[1], "default": row[2]}
                    for row in cursor.fetchall()
                }
                logger.info(
                    f"Tabela '{DB_TABLE_NAME}' existe com as seguintes colunas: {list(columns_info.keys())}"
                )
                columns = list(columns_info.keys())

                # --- Ajuste da coluna 'identified_by' --- (garantir indentação correta)
                col_identified_by = "identified_by"

                if col_identified_by in columns:
                    current_info = columns_info[col_identified_by]
                    needs_alter = False
                    alter_parts = []
                    if (
                        not current_info["type"].startswith("character varying")
                        or "(10)" not in current_info["type"]
                    ):
                        alter_parts.append(
                            f"ALTER COLUMN {col_identified_by} TYPE VARCHAR(10)"
                        )
                        needs_alter = True
                    if current_info["default"] is not None:
                        if "null::" not in str(current_info["default"]).lower():
                            alter_parts.append(
                                f"ALTER COLUMN {col_identified_by} DROP DEFAULT"
                            )
                            needs_alter = True

                    if needs_alter:
                        try:
                            alter_sql = f"ALTER TABLE {DB_TABLE_NAME} { ', '.join(alter_parts) };"
                            logger.info(
                                f"Alterando coluna '{col_identified_by}': {alter_sql}"
                            )
                            cursor.execute(alter_sql)
                            conn.commit()
                            logger.info(
                                f"Coluna '{col_identified_by}' alterada com sucesso."
                            )
                        except Exception as e:
                            logger.error(
                                f"Erro ao alterar coluna '{col_identified_by}': {e}"
                            )
                            try:
                                conn.rollback()
                            except Exception:
                                pass  # Ignorar erros de rollback
                else:
                    try:
                        logger.info(
                            f"Adicionando coluna '{col_identified_by}' (VARCHAR(10)) à tabela '{DB_TABLE_NAME}'..."
                        )
                        add_sql = f"ALTER TABLE {DB_TABLE_NAME} ADD COLUMN {col_identified_by} VARCHAR(10);"
                        cursor.execute(add_sql)
                        conn.commit()
                        logger.info(
                            f"Coluna '{col_identified_by}' adicionada com sucesso."
                        )
                        columns.append(col_identified_by)  # Adiciona à lista local
                    except Exception as e:
                        logger.error(
                            f"Erro ao adicionar coluna '{col_identified_by}': {e}"
                        )
                        try:
                            conn.rollback()
                        except Exception:
                            pass  # Ignorar erros de rollback

                # --- Remoção da coluna 'identified_by_server' --- (garantir indentação correta)
                col_to_remove = "identified_by_server"
                if col_to_remove in columns:
                    try:
                        logger.info(
                            f"Removendo coluna obsoleta '{col_to_remove}' da tabela '{DB_TABLE_NAME}'..."
                        )
                        drop_sql = f"ALTER TABLE {DB_TABLE_NAME} DROP COLUMN {col_to_remove};"
                        cursor.execute(drop_sql)
                        conn.commit()
                        logger.info(
                            f"Coluna '{col_to_remove}' removida com sucesso."
                        )
                        columns.remove(col_to_remove)  # Remove da lista local
                    except Exception as e:
                        logger.error(
                            f"Erro ao remover coluna '{col_to_remove}': {e}"
                        )
                        try:
                            conn.rollback()
                        except Exception:
                            pass  # Ignorar erros de rollback

                # Verificar colunas essenciais (garantir indentação correta)
                required_columns = ["date", "time", "name", "artist", "song_title"]
                missing_columns = [
                    col for col in required_columns if col not in columns
                ]

                if missing_columns:
                    logger.error(
                        f"A tabela '{DB_TABLE_NAME}' existe, mas não possui as colunas necessárias: {missing_columns}"
                    )
                    return False  # Este return está dentro do else, está correto

                # Mostrar algumas linhas da tabela para diagnóstico (garantir indentação correta)
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {DB_TABLE_NAME}")
                    count = cursor.fetchone()[0]
                    logger.info(
                        f"A tabela '{DB_TABLE_NAME}' contém {count} registros."
                    )
                except Exception as e:
                    logger.error(
                        f"Erro ao consultar dados da tabela '{DB_TABLE_NAME}': {e}"
                    )

                logger.info(
                    f"Tabela de logs '{DB_TABLE_NAME}' verificada com sucesso!"
                )
                return True  # Este return está dentro do else, está correto

    except Exception as e:
        logger.error(
            f"Erro ao verificar tabela de logs: {e}", exc_info=True
        )  # Add exc_info
        # Garantir que a transação seja finalizada adequadamente
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass  # Ignorar erros de rollback
        return False
    finally:
        # Garantir que a conexão seja fechada adequadamente
        if conn:
            try:
                conn.close()
            except Exception:
                pass  # Ignorar erros de fechamento'''
    
    # Substituir a função no conteúdo
    # Primeiro, vamos encontrar o início da função
    start_pattern = r'def check_log_table\(\):'
    start_match = re.search(start_pattern, content)
    
    if not start_match:
        print("Erro: Função check_log_table() não encontrada")
        return False
    
    # Encontrar o final da função (próxima função ou final do arquivo)
    start_pos = start_match.start()
    
    # Procurar pela próxima função ou final do arquivo
    end_pattern = r'\n\n\n# Fila para enviar ao Shazamio \(RESTAURADO\)'
    end_match = re.search(end_pattern, content[start_pos:])
    
    if end_match:
        end_pos = start_pos + end_match.start()
    else:
        print("Erro: Não foi possível encontrar o final da função")
        return False
    
    # Substituir a função
    new_content = content[:start_pos] + new_function + content[end_pos:]
    
    # Escrever o arquivo modificado
    with open(fingerv7_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"Função check_log_table() corrigida com sucesso em {fingerv7_path}")
    return True

def main():
    print("Corrigindo problema de transação abortada...")
    
    if fix_check_log_table_function():
        print("\n✅ Correção aplicada com sucesso!")
        print("\nMudanças realizadas:")
        print("1. Melhor gerenciamento de transações na função check_log_table()")
        print("2. Adicionado try/except para rollback em caso de erro")
        print("3. Garantido fechamento adequado de conexões")
        print("4. Prevenção de transações abortadas que causam erro na create_distribution_tables()")
        print("\nReinicie o serviço finger para aplicar as mudanças.")
    else:
        print("\n❌ Erro ao aplicar correção")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main())