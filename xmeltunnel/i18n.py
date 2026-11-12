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
        "Выбранные сайты и приложения идут через ваш сервер, остальное — как обычно",
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
    "Everything goes through your server": "Всё идёт через ваш сервер",
    "No profiles turned on": "Ни один профиль не включён",
    "Checking the exit…": "Проверяю выход…",
    "VPN is off": "VPN выключен",
    "No connection to the server": "Нет связи с сервером",
    "Exit is not your server": "Выход не через ваш сервер",
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
    "not found — turn your VPN on": "не найден — включите VPN",
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
        "Включите профиль — его сайты пойдут через ваш сервер.",
    "Claude Code picks the change up in new sessions.": "Claude Code подхватит изменение в новых сессиях.",
    # problems
    "VPN is off: turn it on, the server is reachable only through it.":
        "VPN выключен: включите его, до сервера можно достучаться только через него.",
    "No connection to the server: the SSH tunnel does not come up.":
        "Нет связи с сервером: SSH-туннель не поднимается.",
    "The tunnel is up, but the exit is not your server ({ip}).":
        "Туннель есть, но выход не через ваш сервер ({ip}).",
    "{app} talks to {profile} directly, around your server.":
        "{app} ходит к {profile} напрямую, мимо вашего сервера.",
    " Restart it if you turned the profile on just now.": " Перезапустите его, если только что включили профиль.",
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
        "Нужно, только если ваш сервер доступен лишь через VPN.",
    "Check connection": "Проверить связь",
    "Install proxy on the server": "Установить прокси на сервер",
    "Checking…": "Проверяю…",
    "Installing…": "Устанавливаю…",
    "Set up the server": "Настроить сервер",
    "Set up": "Настроить",
    "XmelTunnel needs a Linux server you can reach over SSH with a key.":
        "Нужен Linux-сервер, на который вы заходите по SSH-ключу.",
    "The proxy listens only inside the server, nothing new is opened to the internet.":
        "Прокси слушает только внутри сервера, наружу ничего нового не открывается.",
    "SSH works, the proxy answers. Exit IP: {ip}": "SSH работает, прокси отвечает. IP выхода: {ip}",
    "SSH works, but there is no proxy on port {port}. Press «Install proxy on the server».":
        "SSH работает, но прокси на порту {port} нет. Нажмите «Установить прокси на сервер».",
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
    "Add at least one domain.": "Добавьте хотя бы один домен.",
    "Watched apps": "Отслеживаемые приложения",
    "none — leaks are not checked for this profile": "нет — утечки для этого профиля не проверяются",
    "Delete profile «{name}»?": "Удалить профиль «{name}»?",
    "My sites": "Мои сайты",
    # tray / quit
    "Profile «{name}»": "Профиль «{name}»",
    "While XmelTunnel is closed, nobody serves the PAC file and Windows sends apps directly, "
    "around your server.\n\nQuit anyway?":
        "Пока XmelTunnel закрыт, PAC-файл никто не раздаёт, и Windows пустит приложения напрямую, "
        "мимо вашего сервера.\n\nВсё равно выйти?",
    "XmelTunnel keeps working in the tray.": "XmelTunnel продолжает работать в трее.",
    # removal
    "Remove from this PC…": "Удалить с этого ПК…",
    REMOVE_EN:
        "XmelTunnel вернёт всё, что менял на этом ПК:\n"
        "• адрес PAC в настройках прокси Windows (вернётся прежний)\n"
        "• прокси Claude Code в ~/.claude/settings.json\n"
        "• автозапуск\n"
        "• свои настройки и журнал\n\n"
        "Сервер не трогается. После этого просто удалите XmelTunnel.exe.\n\nПродолжить?",
    "Done. XmelTunnel has removed its traces and will close now. Delete XmelTunnel.exe yourself.":
        "Готово: XmelTunnel убрал за собой следы и сейчас закроется. Сам XmelTunnel.exe удалите вручную.",
    "Remove": "Удалить",
    # routing mode
    "Routing mode": "Режим маршрутов",
    "Lists…": "Списки…",
    "Retry": "Повторить",
    "Check": "Проверить",
    "Direct": "Напрямую",
    "Through the VPN": "Через VPN",
    "Through your server": "Через ваш сервер",
    "no answer ({err})": "нет ответа ({err})",
    "not installed": "не установлен",
    "Downloading sing-box… {pct}%": "Скачиваю sing-box… {pct}%",
    "Starting… confirm the admin rights request": "Запускаю… подтвердите запрос прав администратора",
    "On: everything direct, the lists through the VPN ({vpn}) and your server.":
        "Включён: всё напрямую, списки — через VPN ({vpn}) и ваш сервер.",
    "Off. Turn on to send the whole PC direct and only the listed programs and sites "
    "through the VPN or your server. Needs admin rights.":
        "Выключен. Включите, и весь ПК пойдёт напрямую, а через VPN или ваш сервер — только программы "
        "и сайты из списков. Нужны права администратора.",
    "Could not download sing-box: {err}": "Не удалось скачать sing-box: {err}",
    "Normal network adapter not found.": "Не нашёл обычный сетевой адаптер.",
    "VPN is off: turn it on (TUN mode) and press Retry.":
        "VPN выключен: включите его (режим TUN) и нажмите «Повторить».",
    "Your server part is not installed: Lists… → Install on the server.":
        "Серверная часть не установлена: «Списки…» → «Установить на сервер».",
    "Admin rights were not given.": "Права администратора не выданы.",
    "sing-box did not start": "sing-box не запустился",
    "stopped": "остановлен",
    "VPN disconnected: {err}": "VPN отключился: {err}",
    "The VPN disconnects together with XmelTunnel.\n\nQuit anyway?":
        "VPN отключится вместе с XmelTunnel.\n\nВсё равно выйти?",
    "The whole PC goes direct, through your normal connection. Only what is listed goes "
    "through the VPN or through your server. One entry per line: a program (name.exe), "
    "a folder (every program inside it), a domain (subdomains included) or an IP/subnet. "
    "Programs and folders are more reliable than domains: all their traffic goes, "
    "including voice and game UDP. # starts a comment.":
        "Весь ПК идёт напрямую, через обычный интернет. Через VPN или ваш сервер идёт только то, "
        "что в списках. Одна запись в строке: программа (имя.exe), папка (все программы в ней), "
        "домен (поддомены включаются) или IP/подсеть. Программы и папки надёжнее доменов: идёт весь "
        "их трафик, включая голос и UDP игр. # — комментарий.",
    "Your VPN client must be on, in TUN mode.": "VPN-клиент должен быть включён в режиме TUN.",
    "Over the VPN, then out from your server.": "Через VPN, а дальше — выход с вашего сервера.",
    "Shadowsocks port on the server": "Порт Shadowsocks на сервере",
    "Install on the server": "Установить на сервер",
    "installed": "установлен",
    "not installed — needed only for the «through your server» list":
        "не установлен — нужен только для списка «через ваш сервер»",
    "Installing… (up to a few minutes)": "Устанавливаю… (до нескольких минут)",
    "Not understood: {items}": "Не понял: {items}",
    "Shadowsocks is installed on port {port}. If your hosting has its own firewall "
    "in the control panel, open TCP and UDP {port} there.":
        "Shadowsocks установлен на порт {port}. Если у хостинга есть свой файрвол в панели управления, "
        "откройте там TCP и UDP {port}.",
    # updates
    "Version {v} is available. Open XmelTunnel to update.": "Вышла версия {v}. Откройте XmelTunnel, чтобы обновиться.",
    "Could not download the update: {err}": "Не удалось скачать обновление: {err}",
    "Could not install the update: {err}": "Не удалось установить обновление: {err}",
    "Connecting the VPN will ask for admin rights again after the restart.":
        "После перезапуска подключение VPN снова попросит права администратора.",
    "Update": "Обновить",
    "Update XmelTunnel to {v}? It downloads from GitHub, checks the checksum and restarts.":
        "Обновить XmelTunnel до {v}? Новая версия скачается с GitHub, проверится по контрольной сумме, "
        "и программа перезапустится.",
    "Downloading the update… {pct}%": "Скачиваю обновление… {pct}%",
    "Installing the update…": "Устанавливаю обновление…",
    "Update to {v}": "Обновить до {v}",
    "Checking for updates…": "Проверяю обновления…",
    "Update check failed — retry": "Не удалось проверить обновления — повторить",
    "Up to date": "Последняя версия",
    "Check for updates": "Проверить обновления",
    "Check for updates automatically": "Проверять обновления автоматически",
    # routing lists
    "Your normal connection.": "Ваш обычный интернет.",
    "One entry per line: a program (name.exe), a folder (every program inside it), a domain "
    "(subdomains included) or an IP/subnet. Programs and folders are more reliable than "
    "domains: all their traffic goes, including voice and game UDP. If an entry is in several "
    "lists, the leftmost wins. # starts a comment.":
        "Одна запись в строке: программа (имя.exe), папка (все программы в ней), домен (поддомены включаются) "
        "или IP/подсеть. Программы и папки надёжнее доменов: идёт весь их трафик, включая голос и UDP игр. "
        "Если запись есть в нескольких списках, побеждает левый. # — комментарий.",
    "Everything else goes": "Всё остальное идёт",
    "+ Program…": "+ Программа…",
    "+ Folder…": "+ Папка…",
    "+ Running…": "+ Запущенная…",
    "Choose a program": "Выберите программу",
    "Programs (*.exe)": "Программы (*.exe)",
    "Choose a folder: every program inside it": "Выберите папку: пойдут все программы в ней",
    "nothing found": "ничего не найдено",
    "direct": "напрямую",
    "through the VPN": "через VPN",
    "through your server": "через ваш сервер",
    "On: everything not listed goes {where}; VPN adapter: {vpn}.":
        "Включён: всё, чего нет в списках, идёт {where}; адаптер VPN: {vpn}.",
    # settings: app tab
    "Server": "Сервер",
    "App": "Программа",
    "As in Windows": "Как в Windows",
    "Dark": "Тёмная",
    "Light": "Светлая",
    "Theme": "Тема",
    "Interface scale": "Масштаб интерфейса",
    "Language and scale apply after a restart.": "Язык и масштаб применяются после перезапуска.",
    "Start and connection": "Запуск и подключение",
    "Start minimized to the tray": "Запускать свёрнутым в трей",
    "Connect the VPN at start if it was connected": "Подключать VPN при запуске, если он был подключён",
    "The close button hides to the tray (otherwise it quits)": "Крестик сворачивает в трей (иначе — закрывает программу)",
    "Show notifications": "Показывать уведомления",
    "The SSH tunnel always connects by itself while XmelTunnel runs.":
        "SSH-туннель подключается сам, пока XmelTunnel запущен.",
    # first run / no server
    "Profiles need your server: set it up in Settings.": "Профилям нужен ваш сервер: настройте его в «Настройках».",
    "Working without a server": "Работаю без сервера",
    "Profiles need it; the VPN works without it.": "Он нужен профилям; VPN работает и без него.",
    "no server": "без сервера",
    "latest": "последняя версия",
    "could not check for updates": "не удалось проверить обновления",
    "Update check failed: {err}": "Не удалось проверить обновления: {err}",
    "Quick start": "Быстрый старт",
    "Welcome to XmelTunnel": "Добро пожаловать в XmelTunnel",
    "Pick what to start with. Both can be used together, and everything can be changed later in Settings.":
        "Выберите, с чего начать. Можно пользоваться и тем, и другим сразу, а поменять всё можно потом в настройках.",
    "Routing on top of my VPN": "Маршруты поверх моего VPN",
    "Your VPN client (Happ, v2rayN, WireGuard…) stays on. XmelTunnel decides what goes direct, "
    "what through the VPN and what through your server. No server needed.":
        "Ваш VPN-клиент (Happ, v2rayN, WireGuard…) остаётся включённым, а XmelTunnel решает, что идёт напрямую, "
        "что через VPN, а что через ваш сервер. Свой сервер не обязателен.",
    "My server for chosen sites": "Свой сервер для выбранных сайтов",
    "Chosen sites and apps (Claude, ChatGPT…) go through your own Linux server over SSH. "
    "Needs a server you reach with an SSH key.":
        "Выбранные сайты и приложения (Claude, ChatGPT…) идут через ваш Linux-сервер по SSH. "
        "Нужен сервер, на который вы заходите по SSH-ключу.",
    "Set up": "Настроить",
    "Later": "Позже",
    # small UI fixes
    "VPN adapter": "Адаптер VPN",
    "Automatically (Happ, v2rayN, WireGuard, Amnezia…)": "Автоматически (Happ, v2rayN, WireGuard, Amnezia…)",
    "Own rule: {rule}": "Своё правило: {rule}",
    "Hide apps": "Скрыть приложения",
    "Show apps": "Показать приложения",
    "Server: {host}": "Сервер: {host}",
    "Server: not set up": "Сервер: не настроен",
    "SSH: {server}, local proxy 127.0.0.1:{port}. Click to open Settings.":
        "SSH: {server}, локальный прокси 127.0.0.1:{port}. Нажмите, чтобы открыть настройки.",
    "Click to set up a server in Settings.": "Нажмите, чтобы настроить сервер в настройках.",
    "Restarting with the new settings…": "Перезапускаю с новыми настройками…",
    # unified profiles
    "Profiles decide what goes through your server, the VPN or direct":
        "Профили решают, что идёт через ваш сервер, через VPN или напрямую",
    "For the VPN": "Для VPN",
    "Programs, folders and subnets of «through your server» profiles go by Shadowsocks: "
    "install it once. Sites work without it.":
        "Программы, папки и подсети из профилей «через ваш сервер» идут по Shadowsocks: установите его один раз. "
        "Сайтам он не нужен.",
    "Goes": "Куда идёт",
    "What goes": "Что идёт",
    "One entry per line: a site (subdomains included), a program (name.exe), a folder "
    "(every program inside it) or an IP/subnet. # starts a comment.":
        "Одна запись в строке: сайт (поддомены включаются), программа (имя.exe), папка (все программы в ней) "
        "или IP/подсеть. # — комментарий.",
    "Works while the VPN is connected.": "Работает, пока VPN подключён.",
    "Sites go through your server always; programs, folders and subnets — while the VPN is connected.":
        "Сайты идут через ваш сервер всегда, а программы, папки и подсети — пока VPN подключён.",
    "Sites go through your server always, no admin rights needed.":
        "Сайты идут через ваш сервер всегда, права администратора не нужны.",
    "Add at least one site, program or folder.": "Добавьте хотя бы один сайт, программу или папку.",
    "Often blocked": "Часто блокируемое",
    "No profiles go through your server": "Через ваш сервер профили не идут",
    "sites: {n}": "сайтов: {n}",
    "programs: {n}": "программ: {n}",
    "subnets: {n}": "подсетей: {n}",
    "Part of this profile works only while the VPN is connected.":
        "Часть этого профиля работает, только пока VPN подключён.",
    "Everything else": "Всё остальное",
    "On: profiles decide, everything else goes {where}; VPN adapter: {vpn}.":
        "Включён: решают профили, всё остальное идёт {where}; адаптер VPN: {vpn}.",
    "Off. Turn on to route the whole PC by the profiles: programs, folders and sites go through "
    "the VPN, your server or direct. Needs admin rights.":
        "Выключен. Включите, и весь ПК пойдёт по профилям: программы, папки и сайты — через VPN, ваш сервер "
        "или напрямую. Нужны права администратора.",
    "A profile that is on sends its sites and programs where it says.":
        "Включённый профиль отправляет свои сайты и программы туда, куда указано.",
    # start without UAC
    "Do not ask for admin rights every time the VPN connects":
        "Не спрашивать права администратора при каждом подключении VPN",
    "«Do not ask»: Windows asks once now and registers the «XmelTunnel Routing» task in the Task "
    "Scheduler. Keep in mind that any program running as you can then connect the VPN "
    "with admin rights too.":
        "«Не спрашивать»: Windows спросит один раз сейчас, и в Планировщике заданий появится задача "
        "«XmelTunnel Routing». Учтите: тогда любая программа, запущенная от вашего имени, тоже сможет "
        "подключать VPN с правами администратора.",
    "Waiting for the admin rights prompt…": "Жду подтверждения прав администратора…",
    "Windows did not confirm the change (admin rights were not given?).":
        "Windows не подтвердила изменение (права администратора не выданы?).",
    # server through the VPN
    "My server is reachable only through the VPN": "Мой сервер доступен только через VPN",
    "Turn on if your server is blocked where you are: XmelTunnel then connects to it through "
    "the VPN adapter and warns you when the VPN is off.":
        "Включите, если ваш сервер заблокирован там, где вы находитесь: XmelTunnel будет подключаться к нему "
        "через адаптер VPN и предупредит, если VPN выключен.",
    # overview 2: two hero cards
    "Profiles need your server": "Профилям нужен ваш сервер",
    "Server is not set up": "Сервер не настроен",
    "Something goes around your server": "Что-то идёт мимо вашего сервера",
    "Server is connected": "Сервер подключён",
    "Your server": "Ваш сервер",
    "Server": "Сервер",
    "Routing works": "Маршруты работают",
    "Not every path answers": "Не все пути отвечают",
    "Profiles decide, everything else goes {where}. VPN adapter: {vpn}.":
        "Решают профили, всё остальное идёт {where}. Адаптер VPN: {vpn}.",
    "Starting the routing mode…": "Запускаю режим маршрутов…",
    "The routing mode did not start": "Режим маршрутов не запустился",
    "Routing mode is off": "Режим маршрутов выключен",
    "Turn it on to route the whole PC by the profiles: programs, folders and sites go through "
    "the VPN, your server or direct. Needs admin rights.":
        "Включите, и весь ПК пойдёт по профилям: программы, папки и сайты — через VPN, ваш сервер или напрямую. "
        "Нужны права администратора.",
    "Everything not in a profile": "Всё, чего нет в профилях",
    "VPN and routing": "VPN и маршруты",
    "Works while the VPN is connected; otherwise the rest goes as Windows decides.":
        "Работает, пока VPN подключён; иначе остальное идёт так, как решает Windows.",
    "Sites of «through your server» profiles go through it. The VPN works without it.":
        "Через него идут сайты профилей «через ваш сервер». VPN работает и без него.",
    "latest version": "последняя версия",
    # built-in VPN client
    "VPN servers": "Серверы VPN",
    "Country": "Страна",
    "Protocol": "Протокол",
    "Latency": "Задержка",
    "Real exit": "Реальный выход",
    "Subscription": "Подписка",
    "never": "никогда",
    "just now": "только что",
    "{h} h ago": "{h} ч назад",
    "A subscription link (https://…) or server links (vless://, vmess://, trojan://, ss://, hysteria2://, tuic://)":
        "Ссылка подписки (https://…) или ссылки серверов (vless://, vmess://, trojan://, ss://, hysteria2://, tuic://)",
    "Add": "Добавить",
    "Search by name or address": "Поиск по названию или адресу",
    "All protocols": "Все протоколы",
    "All countries": "Все страны",
    "Only working": "Только рабочие",
    "Check shown": "Проверить показанные",
    "Delete selected": "Удалить выбранные",
    "Use the selected one": "Использовать выбранный",
    "added by hand": "добавлен вручную",
    "The name says {a}, but traffic really exits in {b}.": "В названии {a}, но трафик на самом деле выходит в {b}.",
    "{used:.1f} of {total:.0f} GB": "{used:.1f} из {total:.0f} ГБ",
    "until {date}": "до {date}",
    "servers: {n}": "серверов: {n}",
    "Automatically: fastest in {country}": "Автоматически: самый быстрый ({country})",
    "Automatically: the fastest": "Автоматически: самый быстрый",
    "automatically, the fastest": "автоматически, самый быстрый",
    "automatically, the fastest in {country}": "автоматически, самый быстрый ({country})",
    "Servers: {n}, shown: {m}": "Серверов: {n}, показано: {m}",
    "In use: {name}": "Используется: {name}",
    "Checking… {done} of {total}": "Проверяю… {done} из {total}",
    "Updating subscriptions…": "Обновляю подписки…",
    "Check failed: {err}": "Проверка не удалась: {err}",
    "Subscription added, loading its servers…": "Подписка добавлена, загружаю её серверы…",
    "Servers added: {n}.": "Добавлено серверов: {n}.",
    "Delete the selected servers: {n}?": "Удалить выбранные серверы ({n})?",
    "Delete the subscription and its servers?": "Удалить подписку и её серверы?",
    "Your VPN client (Happ, v2rayN…)": "Ваш VPN-клиент (Happ, v2rayN…)",
    "XmelTunnel servers": "Серверы XmelTunnel",
    "Servers…": "Серверы…",
    "No servers yet: press «Servers…» and add a subscription or links.":
        "Серверов пока нет: нажмите «Серверы…» и добавьте подписку или ссылки.",
    "Server: automatically, the fastest of {n}": "Сервер: автоматически, самый быстрый из {n}",
    "Server: automatically, the fastest in {country}": "Сервер: автоматически, самый быстрый ({country})",
    "Server: {name}": "Сервер: {name}",
    "Server: —": "Сервер: —",
    "Profiles decide, everything else goes {where}.": "Решают профили, всё остальное идёт {where}.",
    "No VPN server chosen: open «Servers…» and add some.": "VPN-сервер не выбран: откройте «Серверы…» и добавьте серверы.",
    "no servers in the answer": "в ответе нет серверов",
    "the service answered 404: the link is wrong or works only in its own app":
        "сервис ответил 404: ссылка неверна или работает только в его собственном приложении",
    "the service answered {code}": "сервис ответил {code}",
    # VPN source, clearer
    "Your VPN client": "ваш VPN-клиент",
    "Server from a subscription": "сервер из подписки",
    "Add a subscription or server links…": "Добавить подписку или ссылки серверов…",
    "The fastest of {n} servers": "Самый быстрый из {n} серверов",
    "The fastest in {country}": "Самый быстрый: {country}",
    "Choose a server…": "Выбрать сервер…",
    "Adapter: {name}": "Адаптер: {name}",
    "No VPN client adapter found — turn your VPN client on.": "Адаптер VPN-клиента не найден — включите VPN-клиент.",
    "Choose a VPN server": "Выбор VPN-сервера",
    "VPN goes through": "VPN идёт через",
    # ping, clearer
    "Ping": "Пинг",
    "Check ping": "Проверить пинг",
    "A real request through every shown server: the ping is the time it takes, the real exit is where traffic "
    "comes out. Not a knock on the port.":
        "Настоящий запрос через каждый показанный сервер: пинг — сколько он занял, реальный выход — где трафик "
        "выходит в интернет. Не просто стук в порт.",
    "Median of 3 real requests through the server. Click to sort.":
        "Середина из 3 настоящих запросов через сервер. Нажмите, чтобы отсортировать.",
    "the fastest in {country}": "самый быстрый ({country})",
    "the fastest of {n}": "самый быстрый из {n}",
    "Automatically: {where}": "Автоматически: {where}",
    "ping not checked yet": "пинг ещё не проверен",
    "built-in client": "встроенный клиент",
    # access for friends
    "Sharing": "Общий доступ",
    "Share…": "Поделиться…",
    "Share your server: personal links, traffic, limits":
        "Поделиться вашим сервером: личные ссылки, трафик, ограничения",
    "Status": "Состояние",
    "Traffic": "Трафик",
    "Limit": "Лимит",
    "Valid until": "Действует до",
    "Online": "В сети",
    "Port": "Порт",
    "now": "сейчас",
    "New person": "Новый пользователь",
    "no limit": "без ограничений",
    "days": "дн.",
    "GB": "ГБ",
    "MB": "МБ",
    "KB": "КБ",
    "B": "Б",
    "Valid for": "Срок",
    "Traffic limit": "Лимит трафика",
    "Create the link": "Создать ссылку",
    "Link for {name}": "Ссылка для {name}",
    "Send this link to {name}. It works in XmelTunnel («Choose a VPN server» → Add), Happ, v2rayN and other "
    "clients. Anyone with the link can use it: send it privately.":
        "Отправьте эту ссылку {name}. Она работает в XmelTunnel («Выбор VPN-сервера» → «Добавить»), Happ, v2rayN "
        "и других клиентах. Пользоваться ею может любой, у кого она есть: отправляйте лично.",
    "Copy": "Скопировать",
    "Copied": "Скопировано",
    "Each person gets a personal link: their own key and port on your server, no SSH or root. Guests cannot "
    "reach the server itself or local addresses, and mail ports are closed. Their traffic leaves from your "
    "server's IP: complaints about it would come to you.":
        "Каждый человек получает личную ссылку: свой ключ и порт на вашем сервере, без SSH и root. Гостям закрыт "
        "доступ к самому серверу и локальным адресам, почтовые порты тоже закрыты. Их трафик выходит с IP вашего "
        "сервера: жалобы на него придут вам.",
    "Add a person…": "Добавить человека…",
    "Copy the link": "Скопировать ссылку",
    "Rename…": "Переименовать…",
    "Pause / resume": "Пауза / возобновить",
    "Refresh": "Обновить",
    "First install Shadowsocks: Settings → Server → «Install on the server».":
        "Сначала установите Shadowsocks: «Настройки» → «Сервер» → «Установить на сервер».",
    "Choose a person in the list first.": "Сначала выберите человека в списке.",
    "Asking the server…": "Спрашиваю сервер…",
    "Could not reach the server: {err}": "Не удалось связаться с сервером: {err}",
    "People: {n}, online now: {m}.": "Людей: {n}, сейчас в сети: {m}.",
    "Paused now (time or traffic ran out): {names}.": "Поставлены на паузу (кончился срок или трафик): {names}.",
    "Saving on the server…": "Сохраняю на сервере…",
    "The server did not accept the change: {err}": "Сервер не принял изменение: {err}",
    "paused: time is up": "пауза: срок истёк",
    "paused: traffic is used up": "пауза: трафик исчерпан",
    "paused": "пауза",
    "active": "активен",
    "online ({n})": "в сети ({n})",
    "seen {ago}": "был {ago}",
    "Adding {name}…": "Добавляю: {name}…",
    "Rename": "Переименовать",
    "New name": "Новое имя",
    "Remove {name}? Their link stops working at once.": "Удалить {name}? Ссылка сразу перестанет работать.",
    "No free ports left (100 people at most).": "Свободных портов не осталось (не больше 100 человек).",
    "Guest": "Гость",
    "Connect to these servers through my VPN client (when they are blocked where I am)":
        "Подключаться к этим серверам через мой VPN-клиент (если там, где я, они заблокированы)",
    "Person": "Имя",
    "{n} days": "{n} дн.",
    "For example, Pete": "Например, Петя",
    "not connected yet": "ещё не подключался",
    # quick start 2
    "VPN from a subscription": "VPN по подписке",
    "Paste a subscription link or server links (VLESS, VMess, Trojan, Shadowsocks, Hysteria2, TUIC). XmelTunnel "
    "checks every server for real and picks the fastest.":
        "Вставьте ссылку подписки или ссылки серверов (VLESS, VMess, Trojan, Shadowsocks, Hysteria2, TUIC). "
        "XmelTunnel честно проверит каждый сервер и выберет самый быстрый.",
    "Rules on top of your VPN": "Правила поверх вашего VPN",
    "Happ, v2rayN or another VPN client stays on. Profiles decide what goes through the VPN, what direct, and what "
    "through your server: games direct, YouTube through the VPN, and so on.":
        "Happ, v2rayN или другой VPN-клиент остаётся включённым, а профили решают, что идёт через VPN, что напрямую, "
        "а что через ваш сервер: игры напрямую, YouTube через VPN и так далее.",
    "Your own server": "Свой сервер",
    "Chosen sites and apps (Claude, ChatGPT…) go through your Linux server over SSH. From there you can also share "
    "it: friends get personal links.":
        "Выбранные сайты и приложения (Claude, ChatGPT…) идут через ваш Linux-сервер по SSH. Им можно и поделиться: "
        "друзья получат личные ссылки.",
    "Pick where to start. All of it works together, and everything can be changed later.":
        "Выберите, с чего начать. Всё это работает вместе, а поменять можно потом.",
    "Connect through my VPN client": "Подключаться через мой VPN-клиент",
    "Turn on if these servers are blocked where you are: XmelTunnel will reach them through Happ, v2rayN or another "
    "VPN client that is running.":
        "Включите, если эти серверы у вас заблокированы: XmelTunnel будет подключаться к ним через запущенный "
        "Happ, v2rayN или другой VPN-клиент.",
    # VPN connect, server by a link
    "VPN": "VPN",
    "Paths": "Пути",
    "Shown while the VPN is connected.": "Видны, пока VPN подключён.",
    "VPN is connected": "VPN подключён",
    "Connected, but not every path answers": "Подключён, но не все пути отвечают",
    "Connecting…": "Подключаю…",
    "The VPN did not connect": "VPN не подключился",
    "VPN is disconnected": "VPN отключён",
    "Connect to route the whole PC by the profiles. While disconnected, only the sites of «through your server» "
    "profiles go through your server.":
        "Подключите, и весь ПК пойдёт по профилям. Пока VPN отключён, через ваш сервер идут только сайты профилей "
        "«через ваш сервер».",
    "Connect": "Подключить",
    "Disconnect": "Отключить",
    "VPN connected": "VPN подключён",
    "Link proxy": "Прокси по ссылке",
    "My own server (SSH key)": "Свой сервер (SSH-ключ)",
    "By a link": "По ссылке",
    "Paste the link someone shared with you (or any ss://, vless://, trojan://… link). XmelTunnel then uses that "
    "server as «Your server»: for the sites of «through your server» profiles, Claude Code and the VPN's «server» "
    "path. No SSH and no admin rights needed.":
        "Вставьте ссылку, которой с вами поделились (или любую ss://, vless://, trojan://…). XmelTunnel будет "
        "использовать этот сервер как «Ваш сервер»: для сайтов профилей «через ваш сервер», Claude Code и пути "
        "«Сервер» в VPN. Без SSH и без прав администратора.",
    "{proto} server {host}:{port} · «{name}»": "Сервер {proto} {host}:{port} · «{name}»",
    "Not a server link: {err}": "Это не ссылка на сервер: {err}",
    "Connection": "Подключение",
    "Send this link to {name}. In XmelTunnel it goes to Settings → Server → «By a link» (your server for their "
    "sites and apps) or to «Choose a VPN server» → Add (a VPN server); it also works in Happ and v2rayN. Anyone with "
    "the link can use it: send it privately.":
        "Отправьте эту ссылку {name}. В XmelTunnel её можно вставить в «Настройки» → «Сервер» → «По ссылке» (сервер для "
        "сайтов и программ из профилей) или в «Выбор VPN-сервера» → «Добавить» (как VPN-сервер). Работает и в Happ, "
        "v2rayN. Пользоваться ею может любой, у кого она есть: отправляйте лично.",
    # pages and server connect
    "Updates": "Обновления",
    "Server is disconnected": "Сервер отключён",
    "Waiting for the VPN": "Ждёт VPN",
    "The server waits for the VPN: it is reachable only through it.":
        "Сервер ждёт VPN: до него можно достучаться только через VPN.",
    "Sites of «through your server» profiles go direct until you connect it again.":
        "Сайты профилей «через ваш сервер» идут напрямую, пока вы его снова не подключите.",
    "Check the connection": "Проверить связь",
    "Checks right now that sites go out through your server: asks Cloudflare which IP and country it sees, and how "
    "long that takes.":
        "Сразу проверяет, что сайты выходят через ваш сервер: спрашивает у Cloudflare, какой IP и страну он видит, "
        "и сколько это занимает.",
    "Undo changes": "Отменить изменения",
    "Saved.": "Сохранено.",
    "What XmelTunnel did and what went wrong: useful when something does not work.":
        "Что делал XmelTunnel и что пошло не так: пригодится, если что-то не работает.",
    "Open the file": "Открыть файл",
    "Open the folder": "Открыть папку",
    "The log is empty.": "Журнал пуст.",
    "XmelTunnel updates itself from its GitHub releases; every file is checked by its checksum before it is installed.":
        "XmelTunnel обновляется сам из релизов на GitHub; каждый файл перед установкой сверяется по контрольной сумме.",
    "installed version": "установленная версия",
    "portable version": "портативная версия",
    "running from source": "запущен из исходников",
    "Running from source: update with git.": "Запущен из исходников: обновляйте через git.",
    "Version {v} is available.": "Доступна версия {v}.",
    "This is the latest version.": "Это последняя версия.",
    "Not checked yet.": "Ещё не проверялось.",
}
