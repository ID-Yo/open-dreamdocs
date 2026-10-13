---
{
  "id": "skill-example-build",
  "type": "procedural",
  "status": "proposed",
  "project": "example",
  "scope": "build",
  "created_at": "2026-09-24T10:10:00Z",
  "source": [
    "id:ep-example-build"
  ],
  "owner": "example-owner",
  "version": 1,
  "last_verified": null,
  "success_count": 1,
  "failure_count": 0
}
---

# Учебен кандидат за процедура

## Trigger
Неуспешен build.

## Preconditions
Read-only достъп до конфигурация и безопасни логове.

## Стъпки
1. Прочети точната грешка.
2. Сравни build командата и runtime версията с project конфигурацията.
3. Предложи най-малката поправка.

## Проверка
Build и съответният тест минават. Deployment се изпълнява само в разрешения обхват на конкретна задача.

Един измислен успех илюстрира candidate, не оправдава автоматично приемане.
