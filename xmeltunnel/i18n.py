"""Tiny translation layer: English text is the key, Russian is looked up in RU.

tr("Tunnel is up") -> "Туннель поднят" when the language is Russian.
Placeholders use str.format: tr("Exit: {ip}", ip=...).
"""

from __future__ import annotations

LANGS = {"en": "English", "ru": "Русский"}
_lang = "en"


def system_language() -> str:
    try:
        import ctypes

        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
        return "ru" if primary == 0x19 else "en"
    except Exception:  # noqa: BLE001 — not Windows or no access: English
        return "en"


def set_language(code: str | None) -> None:
    global _lang
    _lang = code if code in LANGS else system_language()


def language() -> str:
    return _lang


def tr(text: str, **kw) -> str:
    out = RU.get(text, text) if _lang == "ru" else text
    return out.format(**kw) if kw else out


REMOVE_EN = ("XmelTunnel will undo everything it changed on this PC:\n"
             "• the PAC address in Windows proxy settings (your previous one comes back)\n"
             "• the Claude Code proxy in ~/.claude/settings.json\n"
             "• autostart\n"
             "• its own settings and log\n\n"
             "Your server is not touched. After that just delete XmelTunnel.exe.\n\nContinue?")

RU = {
    # general
    "Overview": "Обзор",
    "ms": "мс",
    "Chosen sites and apps go through your server, everything else stays as is":
        "Выбранные сайты и приложения идут через твой сервер, остальное — как обычно",
    "Check exit": "Проверить выход",
    "Reconnect": "Переподключить",
    "Check now": "Проверить сейчас",
    "Settings…": "Настройки…",
    "Log": "Журнал",
    "Open": "Открыть",
    "Quit": "Выход",
    "Cancel": "Отмена",
    "Save": "Сохранить",
    "Close": "Закрыть",
    "Delete": "Удалить",
    "OK": "Понятно",
    "Minimize": "Свернуть",
    "Maximize": "Развернуть",
    "Restore": "Вернуть как было",
    # hero
    "Everything goes through your server": "Всё идёт через твой сервер",
    "No profiles turned on": "Ни один профиль не включён",
    "Checking the exit…": "Проверяю выход…",
    "VPN is off": "VPN выключен",
    "No connection to the server": "Нет связи с сервером",
    "Exit is not your server": "Выход не через твой сервер",
    "Something goes around the tunnel": "Что-то идёт мимо туннеля",
    "Server is not set up yet": "Сервер ещё не настроен",
    "expected exit: {ip}": "ожидаемый выход: {ip}",
    "tunnel up {ago}": "туннель поднят {ago}",
    "checked {ago}": "проверено {ago}",
    "checking…": "проверяю…",
    "tunnel is down": "туннель не поднят",
    "{n} s ago": "{n} с назад",
    "{n} min ago": "{n} мин назад",
    "{h} h {m} min ago": "{h} ч {m} мин назад",
    # status card
    "Status": "Состояние",
    "SSH tunnel": "SSH-туннель",
    "Proxy on server": "Прокси на сервере",
    "PAC file": "PAC-файл",
    "on ({name})": "включён ({name})",
    "not found — turn your VPN on": "не найден — включи VPN",
    "connected": "подключён",
    "no connection, retrying…": "нет связи, переподключаюсь…",
    "answers on :{port}": "отвечает на :{port}",
    "error: {err}": "ошибка: {err}",
    "served on :{port}": "раздаётся на :{port}",
    "port does not answer": "порт не отвечает",
    "off in Windows": "выключен в Windows",
    "no profiles on": "профили выключены",
    # profiles card
    "Profiles": "Профили",
    "Add profile…": "Добавить профиль…",
    "Edit…": "Изменить…",
    "{n} domains": "доменов: {n}",
    "not running": "не запущено",
    "through the tunnel": "через туннель",
    "goes direct, around the tunnel": "идёт напрямую, мимо туннеля",
    "partly direct, around the tunnel": "частично напрямую, мимо туннеля",
    "running · no connections yet": "запущено · пока без соединений",
    "running · profile is off": "запущено · профиль выключен",
    "goes direct · profile is off": "идёт напрямую · профиль выключен",
    " · {n} processes": " · процессов: {n}",
    "Start with Windows": "Запускать вместе с Windows",
    "Turn a profile on to send its sites through your server.":
        "Включи профиль — его сайты пойдут через твой сервер.",
    "Claude Code picks the change up in new sessions.": "Claude Code подхватит изменение в новых сессиях.",
    # problems
    "VPN is off: turn it on, the server is reachable only through it.":
        "VPN выключен: включи его, до сервера можно достучаться только через него.",
    "No connection to the server: the SSH tunnel does not come up.":
        "Нет связи с сервером: SSH-туннель не поднимается.",
    "The tunnel is up, but the exit is not your server ({ip}).":
        "Туннель есть, но выход не через твой сервер ({ip}).",
    "{app} talks to {profile} directly, around your server.":
        "{app} ходит к {profile} напрямую, мимо твоего сервера.",
    " Restart it if you turned the profile on just now.": " Перезапусти его, если включил профиль только что.",
    "{app} goes direct: the {profile} profile is off.": "{app} идёт напрямую: профиль {profile} выключен.",
    "{apps} started, but {problem}": "Запущено {apps}, но {problem}",
    # settings / setup
    "Server": "Сервер",
    "Server (IP, user@host or ~/.ssh/config alias)": "Сервер (IP, user@host или алиас из ~/.ssh/config)",
    "SSH port": "Порт SSH",
    "SSH key file": "Файл SSH-ключа",
    "Proxy port on the server": "Порт прокси на сервере",
    "Proxy port on this PC": "Порт прокси на этом ПК",
    "PAC file port": "Порт PAC-файла",
    "Language": "Язык",
    "Warn when the VPN is off": "Предупреждать, если VPN выключен",
    "VPN adapter (regular expression)": "VPN-адаптер (регулярное выражение)",
    "Only needed if your server is reachable only through a VPN.":
        "Нужно, только если твой сервер доступен лишь через VPN.",
    "Check connection": "Проверить связь",
    "Install proxy on the server": "Установить прокси на сервер",
    "Checking…": "Проверяю…",
    "Installing…": "Устанавливаю…",
    "Set up the server": "Настроить сервер",
    "Set up": "Настроить",
    "XmelTunnel needs a Linux server you can reach over SSH with a key.":
        "Нужен Linux-сервер, на который ты заходишь по SSH-ключу.",
    "The proxy listens only inside the server, nothing new is opened to the internet.":
        "Прокси слушает только внутри сервера, наружу ничего нового не открывается.",
    "SSH works, the proxy answers. Exit IP: {ip}": "SSH работает, прокси отвечает. IP выхода: {ip}",
    "SSH works, but there is no proxy on port {port}. Press «Install proxy on the server».":
        "SSH работает, но прокси на порту {port} нет. Нажми «Установить прокси на сервер».",
    "SSH failed: {err}": "Не удалось подключиться по SSH: {err}",
    "Proxy installed and answers. Exit IP: {ip}": "Прокси установлен и отвечает. IP выхода: {ip}",
    "Install failed: {err}": "Установка не удалась: {err}",
    "Server: IP, user@host or an alias from ~/.ssh/config.": "Сервер: IP, user@host или алиас из ~/.ssh/config.",
    "{field}: a number from 1 to 65535.": "{field}: число от 1 до 65535.",
    "SSH key: file not found ({path}).": "Ключ SSH: файл не найден ({path}).",
    "The two local ports must differ.": "Локальные порты не должны совпадать.",
    "Settings": "Настройки",
    # profile editor
    "Profile": "Профиль",
    "New profile": "Новый профиль",
    "Name": "Название",
    "Domains (one per line, subdomains included)": "Домены (по одному в строке, поддомены включаются)",
    "Start from a preset": "Начать с заготовки",
    "Empty": "Пустой",
    "Not domains: {items}": "Не похоже на домены: {items}",
    "Add at least one domain.": "Добавь хотя бы один домен.",
    "Watched apps": "Отслеживаемые приложения",
    "none — leaks are not checked for this profile": "нет — утечки для этого профиля не проверяются",
    "Delete profile «{name}»?": "Удалить профиль «{name}»?",
    "My sites": "Мои сайты",
    # tray / quit
    "Profile «{name}»": "Профиль «{name}»",
    "While XmelTunnel is closed, nobody serves the PAC file and Windows sends apps directly, "
    "around your server.\n\nQuit anyway?":
        "Пока XmelTunnel закрыт, PAC-файл никто не раздаёт, и Windows пустит приложения напрямую, "
        "мимо твоего сервера.\n\nВсё равно выйти?",
    "XmelTunnel keeps working in the tray.": "XmelTunnel продолжает работать в трее.",
    # removal
    "Remove from this PC…": "Удалить с этого ПК…",
    REMOVE_EN:
        "XmelTunnel вернёт всё, что менял на этом ПК:\n"
        "• адрес PAC в настройках прокси Windows (вернётся прежний)\n"
        "• прокси Claude Code в ~/.claude/settings.json\n"
        "• автозапуск\n"
        "• свои настройки и журнал\n\n"
        "Сервер не трогается. После этого просто удали XmelTunnel.exe.\n\nПродолжить?",
    "Done. XmelTunnel has removed its traces and will close now. Delete XmelTunnel.exe yourself.":
        "Готово: XmelTunnel убрал за собой следы и сейчас закроется. Сам XmelTunnel.exe удали вручную.",
    "Remove": "Удалить",
}
