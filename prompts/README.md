# Prompts

Тези prompt-и са работни инструкции за конкретен агент; не са канонични проектни правила и не се обработват като memory записи.

- [`agent-bootstrap.md`](agent-bootstrap.md) — селективно четене и подготовка преди задача.
- [`memory-curator.md`](memory-curator.md) — дневен Dreamer run, snapshot, result и owner review.
- [`task-closeout.md`](task-closeout.md) — кратък closeout с доказателства и memory действия.

Променяйте prompt, когато се промени договорът на runner-а или процесът на проекта, и сверявайте командите с `scripts/project_memory.py` и [`docs/operations/dreamer-setup.md`](../docs/operations/dreamer-setup.md).
