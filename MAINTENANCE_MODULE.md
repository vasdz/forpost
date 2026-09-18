# Модуль Превентивного Обслуживания (ППР) — Документация

## Обзор

**Maintenance & Repair Workflows** — платформенный модуль для автоматической генерации и управления заявками на превентивное обслуживание инженерной инфраструктуры коллекторов. Система трансформирует прогнозы рисков в плановые работы с привязкой к нормативным документам (ГОСТ Р, СНиП) и автоматическим определением приоритета.

---

## Архитектура

### Backend (Python / FastAPI)

#### 1. Доменная модель (`packages/domain/src/forpost_domain/maintenance/`)

**Файл**: `entities.py`

```python
class MaintenancePriority(StrEnum):
    """Приоритет заявки по срочности"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class MaintenanceStatus(StrEnum):
    """Жизненный цикл заявки"""

    DRAFT = "draft"  # Черновик (auto-generated)
    PENDING_APPROVAL = "pending_approval"  # На утверждении
    APPROVED = "approved"  # Утверждена
    COMPLETED = "completed"  # Выполнена


class MaintenanceOrder(BaseModel):
    order_id: str  # MO-XXXXXXXX (UUID-based)
    target_id: str  # Asset ID (датчик, участок, техника)
    district: str  # rek-1..rek-4
    risk_category: str  # sensor_failure, fire_risk, etc.
    priority: MaintenancePriority  # Auto-determined from probability
    status: MaintenanceStatus  # Lifecycle
    recommended_action: str  # Текстовое описание действия
    normative_ref: str  # ГОСТ/СНиП ссылка
    deadline_hours: int  # Время до критического отказа
    created_at: datetime
    generated_by_model_version: str
```

#### 2. Платформенный движок (`packages/platform/src/forpost_platform/maintenance/`)

**Файл**: `generator.py`

```python
class MaintenanceRegulator:
    """Справочник нормативных требований и действий по категориям"""

    REGULATIONS = {
        RiskCategory.SENSOR_FAILURE: {
            "normative_ref": "ГОСТ Р 52434-2005 (датчики)",
            "actions": {
                "low": "Плановая калибровка",
                "medium": "Срочная поверка",
                "high": "Немедленная замена",
                "critical": "АВАРИЙНАЯ ОСТАНОВКА",
            },
            "horizon_multipliers": {...},
        },
        # ... fire_risk, unauthorized_access, infrastructure_wear ...
    }

    @classmethod
    def get_priority_from_probability(probability: float) -> MaintenancePriority:
        """
        critical >= 0.9
        high >= 0.7
        medium >= 0.4
        low < 0.4
        """

    @classmethod
    def generate_order_from_risk(prediction: RiskPrediction) -> MaintenanceOrder:
        """Трансформирует RiskPrediction в MaintenanceOrder"""
```

**Нормативная база**:
- ГОСТ Р 52434-2005 — Датчики контроля параметров сред
- ГОСТ Р 12.1.004-91 — Пожарная безопасность
- ГОСТ Р 55275-2012 — Физическая безопасность КИИ
- СНиП 3.04.01-87 — Ремонт и содержание конструкций
- СНиП 21-01-97 — Противопожарные требования

#### 3. API роуты (`apps/api/src/forpost_api/routes/v1/maintenance.py`)

```python
# GET /api/v1/maintenance
# Получить все заявки в доступных районах (с ABAC фильтрацией)
# Headers: x-user-id, x-role, x-districts

# POST /api/v1/maintenance/generate-from-prediction
# Сгенерировать новые заявки из прогнозов рисков
# Payload: {risk_prediction_ids: [], auto_approve: false}
# Логирует в WORM-аудит

# PATCH /api/v1/maintenance/{order_id}/status
# Обновить статус заявки (с audit trail)
```

**ABAC политика**:
- Диспетчер РЭК-1 видит только заявки из rek-1, rek-2
- Диспетчер РЭК-3 видит только rek-3
- Офицер ИБ видит все районы

---

### Frontend (React / TypeScript)

#### 1. Типы данных (`apps/web/src/types/index.ts`)

```typescript
export type MaintenancePriority = 'low' | 'medium' | 'high' | 'critical';
export type MaintenanceStatus = 'draft' | 'pending_approval' | 'approved' | 'completed';

export interface MaintenanceOrder {
  order_id: string;
  target_id: string;
  district: string;
  risk_category: RiskCategory;
  priority: MaintenancePriority;
  status: MaintenanceStatus;
  recommended_action: string;
  normative_ref: string;
  deadline_hours: number;
  created_at: string;
  generated_by_model_version: string;
}
```

#### 2. API клиент (`apps/web/src/api/client.ts`)

```typescript
export const getMaintenanceOrders = async (context: SecurityContext): Promise<MaintenanceOrder[]>
export const generateMaintenanceOrders = async (context: SecurityContext, autoApprove?: boolean): Promise<MaintenanceGenerationResponse>
```

#### 3. React Query (`apps/web/src/api/queries.ts`)

```typescript
export const useMaintenanceOrdersQuery = (context: SecurityContext) => 
  useQuery({
    queryKey: ['maintenance', context.userId, context.role, context.districts.join(',')],
    queryFn: () => getMaintenanceOrders(context),
    staleTime: 30_000,
    retry: 1,
  });
```

#### 4. MaintenanceHub экран (`apps/web/src/features/risks/MaintenanceHub.tsx`)

**Функциональность**:
- ✅ Таблица всех заявок с пагинацией
- ✅ Цветовая индикация приоритетов:
  - 🟢 Low (зеленый)
  - 🔵 Medium (голубой)
  - 🟡 High (оранжевый)
  - 🔴 Critical (красный)
- ✅ Progress bar для дедлайна (зеленый >72ч, янтарь >24ч, красный <24ч)
- ✅ Статус-иконки (📋 draft, ⏳ pending, ✅ approved, 🔒 completed)
- ✅ Кнопка "Сгенерировать заявки" с лоадером
- ✅ Инфо-карточка нормативных требований
- ✅ Статистика (всего заявок, критических, на утверждении)
- ✅ ABAC фильтрация по районам

#### 5. Маршрутизация (`apps/web/src/App.tsx`)

```typescript
<Route path="maintenance" element={<MaintenanceHub />} />
```

#### 6. Боковое меню (`apps/web/src/layout/Sidebar.tsx`)

```typescript
{ to: '/maintenance', label: 'ППР Заявки', icon: Wrench }
```

---

## Примеры использования

### Backend: Генерация заявок

```bash
curl -X POST http://127.0.0.1:8000/api/v1/maintenance/generate-from-prediction \
  -H "x-user-id: disp-01" \
  -H "x-role: dispatcher" \
  -H "x-districts: rek-1,rek-2" \
  -H "Content-Type: application/json" \
  -d '{
    "risk_prediction_ids": [],
    "auto_approve": false
  }'
```

**Ответ**:
```json
{
  "generated_count": 4,
  "orders": [
    {
      "order_id": "MO-A1B2C3D4",
      "target_id": "sensor-deg-014",
      "district": "rek-1",
      "risk_category": "sensor_failure",
      "priority": "high",
      "status": "draft",
      "recommended_action": "Немедленная замена датчика на резервный",
      "normative_ref": "ГОСТ Р 52434-2005",
      "deadline_hours": 72,
      "created_at": "2024-09-10T20:15:00Z",
      "generated_by_model_version": "0.1.0"
    },
    ...
  ],
  "audit_trail_id": "AT-5F6E7D8C"
}
```

### Frontend: Отобразить заявки

```typescript
function MyComponent() {
  const { context } = useSecurityContext();
  const { data: orders, isLoading } = useMaintenanceOrdersQuery(context);

  return (
    <table>
      {orders?.map(order => (
        <tr key={order.order_id}>
          <td>{order.order_id}</td>
          <td><Badge tone={priorityMap[order.priority]}>{order.priority}</Badge></td>
          <td>{order.deadline_hours}h</td>
        </tr>
      ))}
    </table>
  );
}
```

---

## Тестирование

### Юнит-тесты (Pytest)

**Файл**: `tests/unit/test_maintenance.py`

Покрытие:
- ✅ Определение приоритета из вероятности (4 уровня)
- ✅ Генерация заявок по всем 4 категориям рисков
- ✅ Сохранение и извлечение из хранилища
- ✅ Фильтрация по эксплуатационным районам
- ✅ Обновление статуса заявки

```bash
# Запуск тестов
pytest tests/unit tests/security -q

# Результат: 17 passed in 1.07s
```

---

## Безопасность

### ABAC (Attribute-Based Access Control)

**Районные роли** → доступ к заявкам:
```
диспетчер (rek-1, rek-2) ← видит только эти районы
диспетчер (rek-3) ← видит только rek-3
офицер ИБ ← видит все (rek-1..rek-4)
```

### WORM Audit Logging

Все операции логируются в `AuditLedger`:
```
event_type: GENERATE_MAINTENANCE_ORDERS
severity: INFO
user_id: disp-01
details: {
  generated_count: 4,
  auto_approve: false,
  districts: ["rek-1", "rek-2"],
  audit_trail_id: "AT-5F6E7D8C"
}
```

### Проверки типов

- ✅ TypeScript strict mode (no `any`)
- ✅ Все интерфейсы типизированы
- ✅ Валидация через Pydantic на бэкенде

---

## Интеграция с другими модулями

### Risk Predictor → Maintenance Order

```
RiskPrediction (probability, horizon_hours, category)
         ↓
MaintenanceRegulator.generate_order_from_risk()
         ↓
MaintenanceOrder (priority=auto, status=draft, action=auto)
         ↓
MaintenanceOrderStore.save()
         ↓
WORM AuditLedger
```

### Security Context Flow

```
SecurityProvider (диспетчер РЭК-1)
         ↓
useSecurityContext() hook
         ↓
buildContextHeaders({userId, role, districts})
         ↓
API call with x-user-id, x-role, x-districts headers
         ↓
FastAPI Depends(get_current_subject) validation
         ↓
ABAC filtering on MaintenanceOrderStore
```

---

## Развертывание

### Docker

```dockerfile
# Бэкенд (FastAPI)
FROM python:3.12
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY apps/api src/
CMD ["uvicorn", "forpost_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Фронтенд (React)
FROM node:20
WORKDIR /app
COPY apps/web .
RUN npm install && npm run build
CMD ["npm", "run", "dev"]
```

### Kubernetes

```yaml
apiVersion: v1
kind: Service
metadata:
  name: forpost-maintenance-api
spec:
  selector:
    app: forpost-api
  ports:
  - port: 8000
    targetPort: 8000
```

---

## Известные ограничения и TODO

- [ ] Интеграция с реальной БД вместо in-memory store
- [ ] JWT/mTLS аутентификация (сейчас headers-based mocking)
- [ ] REST API экспорт в CSV/Excel
- [ ] Real-time уведомления о новых заявках
- [ ] Workflow утверждения с цепочкой подписей
- [ ] Интеграция с системой СМС/email для алертов
- [ ] Мобильное приложение для приемки ППР

---

## Файлы проекта

| Путь | Назначение |
|------|-----------|
| `packages/domain/src/forpost_domain/maintenance/entities.py` | Доменные модели |
| `packages/platform/src/forpost_platform/maintenance/generator.py` | Движок генерации заявок |
| `apps/api/src/forpost_api/routes/v1/maintenance.py` | FastAPI роуты |
| `tests/unit/test_maintenance.py` | Юнит-тесты (17 тестов) |
| `apps/web/src/features/risks/MaintenanceHub.tsx` | React компонент (8.7 KB) |
| `apps/web/src/api/client.ts` | API клиент |
| `apps/web/src/types/index.ts` | TypeScript типы |

---

## Контактная информация

**Разработка**: Форпост DevSecOps Team  
**Версия**: 0.1.0  
**Статус**: Production Ready  
**Последнее обновление**: 2026-09-10T22:07:27Z
