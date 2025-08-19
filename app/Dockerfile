# Usar uma imagem base Python 3.11 slim baseada no Debian Bookworm
FROM python:3.11-slim-bookworm

# Instalar dependências do sistema: ffmpeg (essencial) e ca-certificates (para HTTPS)
# Limpar cache do apt para reduzir o tamanho da imagem
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Definir o diretório de trabalho dentro do container
WORKDIR /app

# Copiar apenas o arquivo de dependências primeiro para aproveitar o cache do Docker
COPY requirements.txt .

# Instalar as dependências Python
# --no-cache-dir reduz o tamanho da imagem
# --upgrade pip garante que estamos usando a última versão do pip
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar o resto do código da aplicação para o diretório de trabalho
COPY fingerv7.py .
COPY db_pool.py .
COPY async_queue.py .
COPY __init__.py .
# Se você usa o streams.json como fallback inicial, copie-o também:
# COPY streams.json .

# Definir variáveis de ambiente padrão
# PYTHONUNBUFFERED garante que os logs do Python apareçam imediatamente
ENV PYTHONUNBUFFERED=1
# Definir um caminho padrão para os segmentos DENTRO do container
ENV SEGMENTS_DIR=/app/segments

# Criar o diretório de segmentos e o usuário não-root para execução
# Dar permissão ao usuário no diretório da aplicação
RUN mkdir -p /app/segments && \
    adduser --disabled-password --gecos "" appuser && \
    chown -R appuser:appuser /app

# Mudar para o usuário não-root
USER appuser

# Comando para executar a aplicação quando o container iniciar
CMD ["python", "fingerv7.py"]