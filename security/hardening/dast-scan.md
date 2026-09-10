\# Инструкция проведения DAST-сканирования (OWASP ZAP)



Для автоматического сканирования работающего контура API используется контейнер OWASP ZAP Baseline:



```bash

docker run -t --network="host" zaproxy/zap-stable zap-api-scan.py \\

&#x20; -t http://localhost:8000/openapi.json \\

&#x20; -f openapi \\

&#x20; -r report\_zap.html

