# Формат на записите

Всеки реален запис е Markdown с **JSON object между два реда `---`**. JSON е подмножество на YAML 1.2; избран е, за да има точен parser със стандартния Python. Произволен YAML, comments, trailing commas и duplicate keys не се поддържат. Шаблоните са в [templates](../templates/README.md).

## Общи полета

`id`, `type`, `status`, `project`, `scope`, `created_at`, `source`. ID е стабилен, уникален, с малки латински букви/цифри/точка/тире/долна черта. Всички записи в пакета принадлежат на една проектна идентичност. Времето включва timezone. Източниците са непразен масив:

- `id:ep-example` — друг реален запис; ID трябва да съществува, включително в архива.
- `file:docs/architecture/system-overview.md` — съществуващ файл спрямо корена.
- `https://...` — външен източник; валидаторът не го отваря.
- `ref:issue-123@commit-sha` — външна или неизвличаема идентичност; човекът/агентът проверява доказателството.

Форматът гарантира проследимост, не истинност. Source текстът и metadata не трябва да съдържат токени, лични данни или секрети.

| Папка | type | status |
|---|---|---|
| episodes | episodic | active, archived |
| facts | semantic | proposed, active, disputed, superseded, archived |
| procedural | procedural | proposed, active, deprecated, archived |
| contradictions | contradiction | open, resolved, archived |

Архивът запазва оригиналния type и терминален status. `pinned: true` изключва автоматично предложение за архивиране.

## Факти и методи

Изискват `owner`. При `active` изискват `last_verified` и `accepted_by` с реално доказателство за приемане; Dreamer не може сам да ги активира. Предложение може да има `last_verified: null`. `review_after` е дата YYYY-MM-DD или null, избрана според темата.

`supersedes` и `superseded_by` съдържат реални ID без префикс; `superseded` изисква наследник. Методът има положителна `version`, неотрицателни `success_count` и `failure_count`. Броят успехи не е автоматично разрешение за изпълнение или приемане.

## Retrieval

Четете само релевантни записи. Архиви, superseded/deprecated записи, templates, examples и Dreamer work/reports/proposals не са активни факти. Предложение служи за преглед, никога за оперативна инструкция. Кодът на шаблона валидира и избира вход за Dreamer; не предоставя семантична търсачка или embeddings.
