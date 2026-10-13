---
{"document":"dreamer-setup","status":"draft","owner":"<project-owner>","last_reviewed":"<YYYY-MM-DD>"}
---

# Настройване на дневния Dreamer

Тази страница описва договора между проектен scheduler, runner-а и агента. Разширената политика е в [`memory/DREAMER_POLICY.md`](../../memory/DREAMER_POLICY.md). Файловият шаблон не създава активна задача в scheduler и не твърди, че моделът е семантично правилен.

## Един собственик и дневен график

Конкретният проект избира един scheduler owner, локална часова зона, локален час и изпълнител. Графикът е веднъж дневно по местното време на проекта. Уведомяването е failure-only и при значима промяна, завършване или нужда от действие; непромененото състояние не изпраща съобщение. Параметрите се записват в `memory/config.json`:

```json
{
  "version": 1,
  "schedule": {
    "frequency": "daily",
    "timezone": null,
    "local_time": null,
    "owner": null
  },
  "review": {"episode_days": null}
}
```

`null` означава, че проектът още не е настроил стойността. Файловият runner е включен в пакета; scheduler-ът и връзката му с избрания агент се настройват външно. Пакетът сам не планира работа.

## Първо изпълнение

1. Попълнете `PROJECT.md`, `AGENTS.md`, `docs/00-index.md`, `memory/README.md`, `memory/SCHEMA.md` и `memory/config.json`.
2. Изберете scheduler owner и потвърдете локалната часова зона и час.
3. Изпълнете `python scripts/project_memory.py validate`.
4. Стартирайте `python scripts/project_memory.py begin`. Командата взема lock, създава `memory/dreamer/work/RUN_ID/snapshot.json` и `result.json`, и отпечатва run ID.
5. Snapshot-ът съдържа пълен manifest с хешове на всички реални входни записи и съдържанието на записите, които са променени след последния успешен checkpoint или са due/open. Каноничните документи се четат при нужда и са вън от memory входния manifest.
6. Агентът чете snapshot и началния `result.json`, след което редактира само `result.json`.
7. Агентът попълва валиден `status`, непразно `summary`, пълен `reviewed_ids` при успех и предложенията по схемата на резултата по-долу. `memory/SCHEMA.md` описва Markdown записите в паметта.
8. Изпълнете `python scripts/project_memory.py finish --run-id RUN_ID`.

Не е нужно да има входни записи: zero-input run може да завърши с кратък summary и празен `reviewed_ids` и `proposals`. Не е необходим автоматичен модел за такъв run.

## Схема на резултата

Началният файл има `status: "pending"` и `reviewed_ids: []`. Агентът съзнателно го променя на `success`, `partial` или `failed` и попълва непразен `summary`. При `success` `reviewed_ids` трябва да съдържа всички ID от snapshot-а, които изискват преглед; при `partial` или `failed` summary описва какво остава.

```json
{
  "run_id": "RUN_ID",
  "status": "success",
  "summary": "Кратък резултат от run-а.",
  "reviewed_ids": ["episode-001"],
  "proposals": [
    {
      "kind": "fact",
      "title": "Кратко заглавие",
      "source_ids": ["episode-001"],
      "body": "Предложение с обхват и доказателство."
    }
  ]
}
```

`kind` е един от `fact`, `procedure`, `contradiction`, `duplicate`, `archive`. Предложението е кандидат за преглед, не автоматично активно правило.

## Успешен finish

`finish` проверява result schema, статуса, непразния summary, допустимите ID и пълния `reviewed_ids` при success. Проверява и че пълният входен manifest и хешовете от snapshot-а са непроменени: добавяне, редактиране или изтриване на реален запис по време на run-а означава failure без checkpoint. След успешна проверка runner-ът записва детерминирани изходи:

- `memory/dreamer/reports/RUN_ID.json`;
- `memory/dreamer/proposals/ID.json`, където `ID` е детерминиран hash на предложението.

Checkpoint-ът се премества само при `success`, след commit на отчета и предложенията. При `partial`, `failed` или прекъсване checkpoint-ът остава от предишния успешен run, така че следващият `begin` да опита входа отново. Генерираните отчети и предложения не се връщат като следващ вход.

## Едновременен run, abort и възстановяване

- Един lock допуска само един run за проект. Втори `begin` спира с конфликт; lock-ът не се краде автоматично.
- `python scripts/project_memory.py abort --run-id RUN_ID` освобождава активния run без checkpoint.
- `python scripts/project_memory.py recover --run-id RUN_ID --confirm-stopped --max-age-minutes N` е изрично възстановяване за потвърдено спряно изпълнение. `N` трябва да е положително. Използвайте го само след проверка, че процесът действително не работи; runner-ът не може сам да докаже това.
- Не използвайте `recover`, за да прекъснете жив run или да заобиколите конфликт.

## Дневна процедура

Scheduler owner стартира `begin` веднъж дневно. Агентът чете snapshot-а, попълва result-а и извиква `finish`. При грешка се запазва доказателство и се изпраща уведомяване според политиката. При липса на промяна runner-ът може да завърши с zero-input result без notification. Няма автоматичен self-trigger от генерираните файлове.

## Ограничения

Runner-ът проверява структура, manifest, хешове и форма на резултата. Той не доказва, че предложен факт е истина, че skill е безопасен или че семантичното решение е правилно. Тези решения остават предмет на owner review според [`docs/governance/`](../governance/README.md).
