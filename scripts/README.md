# Проверка и Dreamer lifecycle

Нужен е Python 3.11+; няма външни библиотеки. [project_memory.py](project_memory.py) валидира records/config/links и управлява lock, snapshot, reports/proposals и checkpoint. Не извиква LLM, не инсталира scheduler, не доказва истинността на фактите.

```text
python scripts/project_memory.py validate
python scripts/project_memory.py begin
python scripts/project_memory.py finish --run-id ID
python scripts/project_memory.py abort --run-id ID
python scripts/project_memory.py recover --run-id ID --max-age-minutes 1440 --confirm-stopped
python scripts/project_memory.py --root PATH validate
python -B -m unittest discover -s tests -v
```

Глобалният --root е преди командата. begin създава pending result; агентът го попълва по [политиката](../memory/DREAMER_POLICY.md). Exit: 0 success, 1 partial/failed, 2 invalid input/runtime error. validate разрешава null scheduler fields за непопълнен шаблон и ги отчита като scheduler_configured=false.

Валидаторът проверява познати категории памет, всички локални Markdown връзки извън work, правилни source IDs/file refs, duplicate IDs, статуси, структуриран frontmatter, dates и checkpoint. HTTPS и ref: източници се проверяват от преглеждащия агент/човек. CLI не изпълнява входен текст. Добавяне на нов тип памет изисква промяна на кода и тестовете.
