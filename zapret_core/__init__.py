# zapret_core — ядро zapret-simple (бывший service_manager.py, разбитый по модулям).
# Публичный API переэкспортируется фасадом service_manager.py:
#   import service_manager  ->  from zapret_core.<module> import <func>
# Внешний код (zapret_pyside.py, тесты) импортирует service_manager как раньше.
