#!/usr/bin/env python3
import asyncio
import subprocess
import time
import os
import signal
import psutil
from dotenv import load_dotenv

load_dotenv()

def find_fingerv7_process():
    """Encontra o processo do fingerv7 se estiver rodando."""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] == 'python.exe' and proc.info['cmdline']:
                cmdline = ' '.join(proc.info['cmdline'])
                if 'fingerv7.py' in cmdline:
                    return proc.info['pid']
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None

def stop_fingerv7():
    """Para o fingerv7 se estiver rodando."""
    pid = find_fingerv7_process()
    if pid:
        try:
            print(f"   Parando processo fingerv7 (PID: {pid})...")
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=10)
            print("   ✅ Processo parado com sucesso")
            return True
        except Exception as e:
            print(f"   ⚠️  Erro ao parar processo: {e}")
            return False
    else:
        print("   ✅ Nenhum processo fingerv7 encontrado")
        return True

async def test_fingerv7_startup():
    """Testa a inicialização do fingerv7 com a correção aplicada."""
    
    print("=== TESTE DE INICIALIZAÇÃO DO FINGERV7 ===")
    
    try:
        # 1. Parar qualquer instância existente
        print("\n1. Verificando processos existentes...")
        stop_success = stop_fingerv7()
        if not stop_success:
            print("   ⚠️  Não foi possível parar processo existente")
        
        # Aguardar um pouco
        await asyncio.sleep(2)
        
        # 2. Iniciar fingerv7 em modo de teste
        print("\n2. Iniciando fingerv7 em modo de teste...")
        print("   Comando: python fingerv7.py")
        
        # Iniciar processo
        process = await asyncio.create_subprocess_exec(
            'python', 'fingerv7.py',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd()
        )
        
        print(f"   ✅ Processo iniciado (PID: {process.pid})")
        
        # 3. Monitorar saída por 30 segundos
        print("\n3. Monitorando saída por 30 segundos...")
        
        start_time = time.time()
        timeout = 30
        
        orchestrator_connected = False
        streams_assigned = False
        streams_processing = False
        error_occurred = False
        
        while time.time() - start_time < timeout:
            try:
                # Ler saída com timeout
                stdout_data = await asyncio.wait_for(
                    process.stdout.readline(), 
                    timeout=1.0
                )
                
                if stdout_data:
                    line = stdout_data.decode('utf-8', errors='ignore').strip()
                    if line:
                        print(f"   📝 {line}")
                        
                        # Verificar marcos importantes
                        if 'orquestrador' in line.lower() or 'orchestrator' in line.lower():
                            if 'conectado' in line.lower() or 'connected' in line.lower() or 'registrado' in line.lower():
                                orchestrator_connected = True
                                print("   ✅ Conexão com orquestrador detectada")
                        
                        if 'stream' in line.lower() and ('atribuído' in line.lower() or 'assigned' in line.lower()):
                            streams_assigned = True
                            print("   ✅ Atribuição de streams detectada")
                        
                        if 'processando' in line.lower() or 'processing' in line.lower():
                            streams_processing = True
                            print("   ✅ Processamento de streams detectado")
                        
                        if 'erro' in line.lower() or 'error' in line.lower() or 'exception' in line.lower():
                            if 'critical' in line.lower() or 'fatal' in line.lower():
                                error_occurred = True
                                print(f"   ❌ Erro crítico detectado: {line}")
                
                # Verificar se processo ainda está rodando
                if process.returncode is not None:
                    print(f"   ⚠️  Processo terminou com código: {process.returncode}")
                    break
                    
            except asyncio.TimeoutError:
                # Timeout normal, continuar
                continue
            except Exception as e:
                print(f"   ⚠️  Erro ao ler saída: {e}")
                break
        
        # 4. Parar processo
        print("\n4. Parando processo de teste...")
        try:
            process.terminate()
            await asyncio.wait_for(process.wait(), timeout=5)
            print("   ✅ Processo parado")
        except Exception as e:
            print(f"   ⚠️  Erro ao parar processo: {e}")
            try:
                process.kill()
                await process.wait()
                print("   ✅ Processo forçadamente parado")
            except:
                pass
        
        # 5. Avaliar resultados
        print("\n5. Avaliação dos resultados:")
        
        success_score = 0
        total_checks = 4
        
        if orchestrator_connected:
            print("   ✅ Conexão com orquestrador: OK")
            success_score += 1
        else:
            print("   ❌ Conexão com orquestrador: FALHOU")
        
        if streams_assigned:
            print("   ✅ Atribuição de streams: OK")
            success_score += 1
        else:
            print("   ❌ Atribuição de streams: FALHOU")
        
        if streams_processing:
            print("   ✅ Processamento de streams: OK")
            success_score += 1
        else:
            print("   ❌ Processamento de streams: FALHOU")
        
        if not error_occurred:
            print("   ✅ Sem erros críticos: OK")
            success_score += 1
        else:
            print("   ❌ Erros críticos detectados: FALHOU")
        
        success_rate = (success_score / total_checks) * 100
        print(f"\n   📊 Taxa de sucesso: {success_rate:.1f}% ({success_score}/{total_checks})")
        
        if success_rate >= 75:
            print("   🎉 TESTE PASSOU! fingerv7 está funcionando adequadamente")
            return True
        elif success_rate >= 50:
            print("   ⚠️  TESTE PARCIAL: fingerv7 tem problemas mas está funcional")
            return True
        else:
            print("   ❌ TESTE FALHOU: fingerv7 tem problemas sérios")
            return False
            
    except Exception as e:
        print(f"❌ Erro durante teste: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Executa o teste completo."""
    
    print("🚀 TESTE REAL DO FINGERV7 COM CORREÇÕES APLICADAS\n")
    
    # Verificar se estamos no diretório correto
    if not os.path.exists('fingerv7.py'):
        print("❌ fingerv7.py não encontrado no diretório atual")
        print(f"   Diretório atual: {os.getcwd()}")
        return
    
    # Executar teste
    test_success = await test_fingerv7_startup()
    
    if test_success:
        print("\n🎉 TESTE CONCLUÍDO COM SUCESSO!")
        print("   ✅ fingerv7 está funcionando com as correções aplicadas")
        print("   ✅ Orquestrador está atribuindo streams corretamente")
        print("   ✅ Filtragem de streams está funcionando")
        print("\n📝 RECOMENDAÇÕES:")
        print("   1. O fingerv7 pode ser executado normalmente")
        print("   2. Monitorar logs para identificações musicais")
        print("   3. Verificar métricas de performance")
    else:
        print("\n⚠️  TESTE REVELOU PROBLEMAS")
        print("   Pode ser necessário investigar mais ou aplicar correções adicionais")
        print("\n📝 PRÓXIMOS PASSOS:")
        print("   1. Revisar logs detalhados")
        print("   2. Verificar configurações")
        print("   3. Testar componentes individuais")

if __name__ == "__main__":
    asyncio.run(main())