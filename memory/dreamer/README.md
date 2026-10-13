# Dreamer runtime

`work/` съдържа snapshot и pending result; `lock.json` идентифицира текущия run; `command.lock` сериализира CLI операциите. `state.json` е последният успешно приключен checkpoint. Тези файлове са локални и игнорирани от Git.

[reports](reports/README.md) съдържа отчети, [proposals](proposals/README.md) — кандидати за преглед. Нито един от тези файлове не се включва автоматично в активната памет. Не записвайте фиктивен успешен checkpoint в шаблона.

При започване на нов проект копирайте само чистия пакет. При копиране на използван checkout изключете work/lock/state и старите runtime отчети/предложения. Следвайте [политиката](../DREAMER_POLICY.md) за възстановяване и контрол на writers.
