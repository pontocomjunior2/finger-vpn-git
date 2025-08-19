# Esquema da Tabela music_log

## Estrutura da Tabela

A tabela `music_log` armazena registros de músicas identificadas pelo sistema. Abaixo está a estrutura atual da tabela:

| Coluna | Tipo | Descrição |
|--------|------|----------|
| id | serial | Identificador único do registro (chave primária) |
| name | text | Nome da rádio/stream |
| artist | text | Nome do artista |
| song_title | text | Título da música |
| date | date | Data da identificação (YYYY-MM-DD) |
| time | time | Hora da identificação (HH:MM:SS) |
| identified_by | text | ID do servidor que identificou a música |
| ip_address | text | Endereço IP do servidor (opcional) |
| port | text | Porta do servidor (opcional) |
| isrc | text | Código ISRC da música (opcional) |
| cidade | text | Cidade da rádio (opcional) |
| estado | text | Estado da rádio (opcional) |
| regiao | text | Região da rádio (opcional) |
| segmento | text | Segmento da rádio (opcional) |
| label | text | Gravadora da música (opcional) |
| genre | text | Gênero da música (opcional) |

## Restrições

A tabela possui uma restrição de unicidade nas colunas:
- `name`
- `artist`
- `song_title`
- `date`
- `time`

Isso impede a inserção de registros duplicados para a mesma música na mesma rádio no mesmo momento.

## Notas Importantes

- A coluna `identified_by` é usada para rastrear qual servidor identificou a música.
- Não existe uma coluna `server_id` na tabela. Qualquer referência a `server_id` deve ser mapeada para `identified_by`.
- Os campos opcionais podem ser nulos ou vazios.

## Alterações Recentes

**2025-08-19**: Corrigido erro de inserção que tentava usar a coluna inexistente `server_id`. A query de inserção foi atualizada para usar `identified_by` em vez de `server_id`.

## Exemplos de Uso

### Inserção de Registro

```sql
INSERT INTO music_log (name, artist, song_title, date, time, identified_by, ip_address, port)
VALUES ('Rádio XYZ', 'Artista', 'Título da Música', '2025-08-19', '12:34:56', '1', '192.168.1.1', '8080')
ON CONFLICT (name, artist, song_title, date, time) DO NOTHING
RETURNING id;
```

### Consulta de Registros por Servidor

```sql
SELECT date, time, name, artist, song_title
FROM music_log
WHERE identified_by = '1'
ORDER BY date DESC, time DESC
LIMIT 5;
```